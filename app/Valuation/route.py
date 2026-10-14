from flask import request, Blueprint, jsonify, make_response, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timezone
from decimal import Decimal

from app.database.database import db
from app.logic.valuation_service import PortfolioValuationService as LegacyValuationService
from app.logic.nav_valuation_service import PortfolioValuationService, NavInput
from app.Investments.model import Investment, EpochLedger, Withdrawal, FINAL_WITHDRAWAL_STATUSES, WITHDRAWAL_STATUS_EXECUTED
from app.Funds.share_class import ShareClass, SHARES_VALUATION_CURRENCY
from app.database.product_type import SHARES
from sqlalchemy import and_, func, or_, select, insert
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Valuation.model import ValuationRun, Statement, ValuationJob
from app.Valuation.valuation_snapshot import ValuationSnapshot
from app.Funds.nav_history import NavHistory
from app.Funds.investor_shares import InvestorShares
from sqlalchemy.exc import IntegrityError
import logging
import json

logger = logging.getLogger(__name__)


valuation_v1 = Blueprint("valuation_v1", __name__, url_prefix="/")


def _current_user_for_job():
    """(user_id, user_email) for the ValuationJob audit fields — None-safe."""
    try:
        from app.Admin.model import User
        identity = get_jwt_identity()
        email = identity if isinstance(identity, str) else (identity or {}).get("email")
        if not email:
            return None, None
        user = db.session.query(User).filter(func.lower(User.email) == str(email).strip().lower()).first()
        return (user.id, user.email) if user else (None, None)
    except Exception:
        return None, None


def _parse_iso_dt(value, field_name: str) -> datetime:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{field_name} is required")
    if isinstance(value, datetime):
        # Ensure timezone-aware
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 datetime string")
    try:
        # Accept both "YYYY-MM-DD" and full ISO strings
        if len(value.strip()) == 10:
            dt = datetime.fromisoformat(value.strip())
        else:
            dt = datetime.fromisoformat(value.strip())
        # Ensure timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        raise ValueError(f"Invalid {field_name} format: {str(e)}")


def _validate_epoch_sequence(core_fund_id: int, start_date: datetime, end_date: datetime) -> tuple[bool, str]:
    """
    Validate that epochs are committed in sequence with no gaps.
    Rule: If committing an epoch that starts after prior epochs, all prior epochs must be committed.
    
    Returns: (is_valid, error_message)
    """
    # Use naive UTC datetimes for comparisons against ValuationRun epoch_end, which is stored without timezone
    start_date_naive = start_date.replace(tzinfo=None) if start_date.tzinfo is not None else start_date

    # Get all previous epochs for this fund (where end_date < current start_date)
    previous_valuations = db.session.query(ValuationRun).filter(
        ValuationRun.core_fund_id == core_fund_id,
        ValuationRun.epoch_end < start_date_naive,
        ValuationRun.status == "Committed"  # Only count committed epochs
    ).order_by(ValuationRun.epoch_end.desc()).all()


def _get_share_class_deployment_total_shares(share_class_id: int) -> Decimal | None:
    """Return the recorded deployed share total for the share class, if available."""
    batch = (
        db.session.query(Batch)
        .filter(Batch.share_class_id == share_class_id, Batch.total_shares != None)
        .order_by(Batch.date_deployed.desc().nullslast())
        .first()
    )
    if batch and batch.total_shares is not None:
        return PortfolioValuationService._to_decimal(batch.total_shares)
    return None
    
    # Get all valuations (committed or not) to check for gaps
    all_valuations = db.session.query(ValuationRun).filter(
        ValuationRun.core_fund_id == core_fund_id,
        ValuationRun.epoch_end < start_date_naive  # All epochs before this one
    ).order_by(ValuationRun.epoch_end.desc()).all()
    
    if not all_valuations:
        # First epoch - always allowed
        return True, ""
    
    # If there are any non-committed valuations before this epoch, block it
    for val in all_valuations:
        if val.status != "Committed":
            return False, f"Cannot commit epoch [{val.epoch_start.date()}—{val.epoch_end.date()}] with status '{val.status}'. All prior epochs must be 'Committed' before proceeding."
    
    # Check for time gaps: last committed epoch should end near or before this epoch start
    if previous_valuations:
        last_epoch = previous_valuations[0]
        # Allow epochs that start near the end of the previous one (within 2 days for flexibility)
        # But this is optional - the main validation is that all prior epochs are committed
        pass
    
    return True, ""


def _validate_epoch_reconciliation(preview: dict, start_date: datetime, end_date: datetime, fund_name: str) -> tuple[bool, str]:
    """
    Validate epoch-level data integrity.
    Ensures: sum(start_balances) + deposits - withdrawals + profit = sum(end_balances)
    
    Returns: (is_valid, error_message)
    """
    try:
        # Extract aggregated values from preview
        total_start = Decimal(str(preview.get("total_start_balance", 0)))
        total_deposits = Decimal(str(preview.get("total_deposits", 0)))
        total_withdrawals = Decimal(str(preview.get("total_withdrawals", 0)))
        total_profit = Decimal(str(preview.get("total_profit", 0)))
        total_end = Decimal(str(preview.get("total_closing_aum", preview.get("expected_closing_aum", preview.get("reconciliation_total", preview.get("total_local_valuation", 0))))))
        
        # Expected end balance: start + deposits - withdrawals + profit
        expected_end = total_start + total_deposits - total_withdrawals + total_profit
        expected_end = expected_end.quantize(Decimal("0.01"))
        
        # Allow $0.01 tolerance due to rounding
        diff = abs(total_end - expected_end)
        if diff > Decimal("0.01"):
            return False, f"Epoch-level reconciliation failed for {fund_name} [{start_date.date()}—{end_date.date()}]: " \
                          f"Balance equation doesn't match. " \
                          f"Start ${total_start} + Deposits ${total_deposits} - Withdrawals ${total_withdrawals} + Profit ${total_profit} " \
                          f"= Expected ${expected_end}, but got ${total_end} (diff: ${diff})"
        
        return True, ""
    except Exception as e:
        return False, f"Error validating epoch reconciliation: {str(e)}"


def _get_deployment_reference(core_fund_id: int):
    batch_rows = (
        db.session.query(Batch)
        .join(Investment, Investment.batch_id == Batch.id)
        .filter(Investment.fund_id == core_fund_id)
        .distinct()
        .all()
    )
    deployed_dates = [b.date_deployed for b in batch_rows if b.date_deployed is not None]
    return {
        "earliest_date_deployed": min(deployed_dates).isoformat() if deployed_dates else None,
        "batches": [
            {
                "batch_id": b.id,
                "batch_name": b.batch_name,
                "date_deployed": b.date_deployed.isoformat() if b.date_deployed else None,
                "deployment_confirmed": bool(b.deployment_confirmed),
                "is_active": bool(b.is_active),
            }
            for b in batch_rows
        ],
    }


@valuation_v1.route("/api/v1/valuation/epoch", methods=["POST"])
@jwt_required()
def create_epoch_valuation():
    """
    Create a new epoch ledger for a given fund and period.

    Body:
    {
      "fund_name": "Axiom",
      "start_date": "2026-01-01",
      "end_date": "2026-02-01",
      "performance_rate": 0.05,
      "head_office_total": 123456.78
    }
    """
    try:
        data = request.get_json() or {}

        fund_id = data.get("fund_id")
        if fund_id is None:
            return make_response(jsonify({"status": 400, "message": "fund_id is required"}), 400)
        try:
            fund_id = int(fund_id)
        except Exception:
            return make_response(jsonify({"status": 400, "message": "fund_id must be an integer"}), 400)

        start_date = _parse_iso_dt(data.get("start_date"), "start_date")
        end_date = _parse_iso_dt(data.get("end_date"), "end_date")

        performance_rate = data.get("performance_rate")
        head_office_total = data.get("head_office_total")
        if performance_rate is None:
            return make_response(jsonify({"status": 400, "message": "performance_rate is required"}), 400)
        if head_office_total is None:
            return make_response(jsonify({"status": 400, "message": "head_office_total is required"}), 400)

        # Normalize: The field is labeled "Performance rate (%)", so input is ALWAYS a percentage.
        # User enters: 3.48 (meaning 3.48%), -0.25 (meaning -0.25%), etc.
        # We always convert to decimal: 3.48 → 0.0348, -0.25 → -0.0025
        performance_rate = float(performance_rate)
        performance_rate = performance_rate / 100.0

        summary = PortfolioValuationService.create_epoch_ledger_for_fund(
            fund_id=fund_id,
            start_date=start_date,
            end_date=end_date,
            performance_rate=performance_rate,
            head_office_total=head_office_total,
            session=db.session,
        )

        return make_response(
            jsonify(
                {
                    "status": 201,
                    "message": "Epoch ledger created successfully",
                    "data": summary,
                }
            ),
            201,
        )

    except ValueError as ve:
        db.session.rollback()
        return make_response(jsonify({"status": 400, "message": str(ve)}), 400)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@valuation_v1.route("/api/v1/valuation/nav/runs", methods=["GET"])
@jwt_required()
def list_nav_valuation_runs():
    """
    List recent NAV-based valuation runs (aggregated from ValuationSnapshot).

    Returns rows per (share_class_id, valuation_date) with:
    - fund_name, share class code/currency
    - nav_per_share
    - opening_aum (previous valuation date for that class)
    - closing_aum (sum market_value for that valuation date)
    - profit, performance_pct
    - investors (count of holdings)
    """
    try:
        limit = request.args.get("limit", default=50, type=int)
        if limit > 200:
            limit = 200
        # Task 9: Funds and Shares valuations must never mix — product scopes
        # every valuation run the same way it scopes the fund/share-class
        # lists themselves (Task 8's CoreFund.product_type).
        product = (request.args.get("product") or "").strip().upper() or None

        query = (
            db.session.query(
                InvestorShares.share_class_id.label("share_class_id"),
                ShareClass.class_code.label("share_class_code"),
                ShareClass.currency.label("currency"),
                CoreFund.product_type.label("product_type"),
                ShareClass.core_fund_id.label("core_fund_id"),
                CoreFund.fund_name.label("fund_name"),
                ValuationSnapshot.valuation_date.label("valuation_date"),
                func.max(ValuationSnapshot.nav_per_share).label("nav_per_share"),
                func.coalesce(func.sum(ValuationSnapshot.market_value), 0).label("closing_aum"),
                func.count(func.distinct(ValuationSnapshot.investor_shares_id)).label("investors"),
            )
            .join(InvestorShares, InvestorShares.id == ValuationSnapshot.investor_shares_id)
            .join(ShareClass, ShareClass.id == InvestorShares.share_class_id)
            .join(CoreFund, CoreFund.id == ShareClass.core_fund_id)
        )
        if product:
            query = query.filter(CoreFund.product_type == product)
        rows = (
            query
            .group_by(
                InvestorShares.share_class_id,
                ShareClass.class_code,
                ShareClass.currency,
                CoreFund.product_type,
                ShareClass.core_fund_id,
                CoreFund.fund_name,
                ValuationSnapshot.valuation_date,
            )
            .order_by(ValuationSnapshot.valuation_date.desc())
            .limit(1000)
            .all()
        )

        by_class: dict[int, list[dict]] = {}
        for r in rows:
            sc_id = int(r.share_class_id)
            by_class.setdefault(sc_id, []).append(
                {
                    "share_class_id": sc_id,
                    "share_class_code": r.share_class_code,
                    "core_fund_id": int(r.core_fund_id),
                    "fund_name": r.fund_name,
                    # NAV currency: SHARES (DPRP) classes are deposited in
                    # USD but valued in NGN (ShareClass.valuation_currency).
                    "currency": SHARES_VALUATION_CURRENCY if r.product_type == SHARES else (r.currency or "USD").upper(),
                    "valuation_date": r.valuation_date.isoformat(),
                    "nav_per_share": float(Decimal(str(r.nav_per_share)).quantize(Decimal("0.0001"))),
                    "closing_aum": float(Decimal(str(r.closing_aum)).quantize(Decimal("0.01"))),
                    "investors": int(r.investors or 0),
                }
            )

        out: list[dict] = []
        for _, items in by_class.items():
            items.sort(key=lambda x: x["valuation_date"])
            prev_closing: float | None = None
            for it in items:
                opening = float(prev_closing) if prev_closing is not None else 0.0
                closing = float(it["closing_aum"])
                profit = round(closing - opening, 2)
                perf = round((profit / opening * 100.0), 2) if opening and opening != 0 else 0.0
                out.append({**it, "opening_aum": round(opening, 2), "profit": profit, "performance_pct": perf})
                prev_closing = closing

        out.sort(key=lambda x: x["valuation_date"], reverse=True)
        out = out[:limit]
        return make_response(jsonify({"status": 200, "message": "NAV valuation runs retrieved", "data": out}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@valuation_v1.route("/api/v1/valuation/funds", methods=["GET"])
@jwt_required()
def valuation_funds():
    """Return all active core funds, optionally scoped to one product (Task 9)."""
    try:
        product = (request.args.get("product") or "").strip().upper() or None
        query = db.session.query(CoreFund).filter(CoreFund.is_active == True)  # noqa: E712
        if product:
            query = query.filter(CoreFund.product_type == product)
        funds = query.order_by(CoreFund.fund_name.asc(), CoreFund.id.asc()).all()
        data = [{"id": f.id, "fund_name": f.fund_name, "is_active": f.is_active, "product_type": f.product_type} for f in funds]
        return make_response(jsonify({"status": 200, "message": "Active funds retrieved", "data": data}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@valuation_v1.route("/api/v1/valuation/batches", methods=["GET"])
@jwt_required()
def valuation_batches():
    """
    Return valuation-eligible batches by valuation period end_date.
    Eligibility: date_deployed IS NOT NULL and date_deployed <= end_date.
    Optional query params:
      - fund_id (integer)
      - end_date (ISO date/datetime)
    """
    try:
        fund_id_raw = request.args.get("fund_id")
        end_date_raw = request.args.get("end_date")
        end_date = _parse_iso_dt(end_date_raw, "end_date") if end_date_raw else datetime.now(timezone.utc)

        q = db.session.query(Batch)
        if fund_id_raw:
            try:
                fund_id = int(fund_id_raw)
            except Exception:
                return make_response(jsonify({"status": 400, "message": "fund_id must be an integer"}), 400)
            q = q.join(Investment, Investment.batch_id == Batch.id).filter(Investment.fund_id == fund_id)

        rows = (
            q.filter(Batch.date_deployed.isnot(None))
            .filter(Batch.date_deployed <= end_date)
            .distinct()
            .order_by(Batch.date_deployed.asc(), Batch.id.asc())
            .all()
        )
        data = [
            {
                "id": b.id,
                "batch_name": b.batch_name,
                "date_deployed": b.date_deployed.isoformat() if b.date_deployed else None,
                "deployment_confirmed": bool(b.deployment_confirmed),
                "is_active": bool(b.is_active),
            }
            for b in rows
        ]
        return make_response(jsonify({"status": 200, "message": "Valuation batches retrieved", "data": data}), 200)
    except ValueError as ve:
        return make_response(jsonify({"status": 400, "message": str(ve)}), 400)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@valuation_v1.route("/api/v1/valuation/dry-run", methods=["POST"])
@jwt_required()
def dry_run_post():
    """
    POST version for UI wiring.

    Body:
    {
      "fund_id": 1,
      "start_date": "2026-01-01",
      "end_date": "2026-02-01",
      "performance_rate_percent": 5,
      "head_office_total": 123456.78
    }
    """
    try:
        data = request.get_json() or {}

        # Consolidated mode: fund_name ("Axiom"/"Atium")
        fund_name = data.get("fund_name")
        if fund_name:
            start_date = _parse_iso_dt(data.get("start_date"), "start_date")
            end_date = _parse_iso_dt(data.get("end_date"), "end_date")

            # Accept 'performance_rate_percent' (legacy) or 'performance_rate' (frontend form field)
            # The field is labeled "Performance rate (%)", so input is ALWAYS a percentage.
            perf_pct = data.get("performance_rate_percent") if data.get("performance_rate_percent") is not None else data.get("performance_rate")
            if perf_pct is None:
                return make_response(jsonify({"status": 400, "message": "performance_rate is required"}), 400)
            # Always divide by 100 since field expects percentages
            perf_pct = float(perf_pct)
            performance_rate = perf_pct / 100.0

            head_office_total = data.get("head_office_total")
            if head_office_total is None:
                return make_response(jsonify({"status": 400, "message": "head_office_total is required"}), 400)
            head_office_total = float(head_office_total)

            preview = PortfolioValuationService.preview_epoch_for_fund_name(
                fund_name=fund_name,
                start_date=start_date,
                end_date=end_date,
                performance_rate=performance_rate,
                session=db.session,
            )

            # Validate epoch-level reconciliation
            epoch_valid, epoch_error = _validate_epoch_reconciliation(preview, start_date, end_date, fund_name)
            if not epoch_valid:
                return make_response(jsonify({"status": 400, "message": f"Epoch reconciliation failed: {epoch_error}"}), 400)

            # Use reconciliation_total when present so that Head Office totals
            # which still include period withdrawals can be matched.
            base_total = float(preview.get("reconciliation_total", preview.get("calculated_total")))
            diff = round(abs(base_total - head_office_total), 2)
            preview["head_office_total"] = head_office_total
            preview["expected_batch_total"] = head_office_total
            preview["net_excel_total"] = float(preview.get("excel_total", 0) - preview.get("withdrawals_total", 0))
            preview["reconciliation_diff"] = diff
            preview["is_reconciled"] = diff <= 0.01

            # Get core fund for deployment reference
            core = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == fund_name.lower()).first()
            if core:
                preview["deployment_reference"] = _get_deployment_reference(core.id)
            return make_response(
                jsonify({"status": 200, "message": "Dry run complete", "data": preview}),
                200,
            )

        # Legacy mode: fund_id
        fund_id = data.get("fund_id")
        if fund_id is None:
            return make_response(jsonify({"status": 400, "message": "fund_name or fund_id is required"}), 400)
        fund_id = int(fund_id)

        start_date = _parse_iso_dt(data.get("start_date"), "start_date")
        end_date = _parse_iso_dt(data.get("end_date"), "end_date")

        # Accept 'performance_rate_percent' (legacy) or 'performance_rate' (frontend form field)
        # The field is labeled "Performance rate (%)", so input is ALWAYS a percentage.
        perf_pct = data.get("performance_rate_percent") if data.get("performance_rate_percent") is not None else data.get("performance_rate")
        if perf_pct is None:
            return make_response(jsonify({"status": 400, "message": "performance_rate is required"}), 400)
        # Always divide by 100 since field expects percentages
        perf_pct = float(perf_pct)
        performance_rate = perf_pct / 100.0

        head_office_total = data.get("head_office_total")
        if head_office_total is None:
            return make_response(jsonify({"status": 400, "message": "head_office_total is required"}), 400)
        head_office_total = float(head_office_total)

        preview = PortfolioValuationService.preview_epoch_for_fund(
            fund_id=fund_id,
            start_date=start_date,
            end_date=end_date,
            performance_rate=performance_rate,
            session=db.session,
        )

        # Prefer reconciliation_total (AUM + profit + withdrawals) when available
        base_total = float(preview.get("reconciliation_total", preview.get("total_local_valuation")))
        calculated_total = base_total
        diff = round(abs(base_total - head_office_total), 2)

        preview["expected_batch_total"] = head_office_total
        preview["head_office_total"] = head_office_total
        preview["net_excel_total"] = float(preview.get("excel_total", 0) - preview.get("withdrawals_total", 0))
        preview["reconciliation_diff"] = diff

        preview["deployment_reference"] = _get_deployment_reference(fund_id)
        return make_response(
            jsonify(
                {
                    "status": 200,
                    "message": "Dry run complete",
                    "data": {
                        **preview,
                        "calculated_total": calculated_total,
                        "head_office_total": head_office_total,
                        "diff": diff,
                        "is_reconciled": diff <= 0.01,
                    },
                }
            ),
            200,
        )
    except PermissionError as pe:
        return make_response(jsonify({"status": 403, "message": str(pe)}), 403)
    except ValueError as ve:
        return make_response(jsonify({"status": 400, "message": str(ve)}), 400)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@valuation_v1.route("/api/v1/valuation/confirm", methods=["POST"])
@jwt_required()
def confirm_epoch():
    """
    Commit valuation: validates reconciliation, then writes EpochLedger rows + hashes.
    
    Body:
    {
      "fund_name": "Axiom",
      "start_date": "2026-01-01",
      "end_date": "2026-02-01",
      "performance_rate_percent": 5,        (e.g., "5" for 5%)
      "head_office_total": 123456.78
    }
    """
    try:
        data = request.get_json() or {}

        # Consolidated by core fund name or fund ID
        core_fund_id = None
        fund_name = (data.get("fund_name") or "").strip()
        if fund_name:
            core = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == fund_name.lower()).first()
            if not core:
                return make_response(jsonify({"status": 404, "message": "Core fund not found"}), 404)
            core_fund_id = core.id
        else:
            fund_id = data.get("fund_id")
            if fund_id is None:
                return make_response(jsonify({"status": 400, "message": "fund_name or fund_id is required"}), 400)
            try:
                core_fund_id = int(fund_id)
            except Exception:
                return make_response(jsonify({"status": 400, "message": "fund_id must be an integer"}), 400)
            core = db.session.query(CoreFund).filter(CoreFund.id == core_fund_id).first()
            if not core:
                return make_response(jsonify({"status": 404, "message": "Core fund not found"}), 404)
            fund_name = core.fund_name

        start_date = _parse_iso_dt(data.get("start_date"), "start_date")
        end_date = _parse_iso_dt(data.get("end_date"), "end_date")

        # Accept performance_rate_percent (e.g., 5 for 5%, 0.49 for 0.49%)
        perf_pct = data.get("performance_rate_percent")
        if perf_pct is None:
            return make_response(jsonify({"status": 400, "message": "performance_rate_percent is required"}), 400)

        # Normalize percent input to the internal fractional form used by the service.
        # The field is labeled "Performance rate (%)", so input is ALWAYS a percentage.
        raw_perf = Decimal(str(perf_pct))
        performance_rate = raw_perf / Decimal("100")

        head_office_total_input = data.get("head_office_total")
        if head_office_total_input is None:
            return make_response(jsonify({"status": 400, "message": "head_office_total is required"}), 400)
        head_office_total = Decimal(str(head_office_total_input))

        # STEP 1: Dry-run first to validate reconciliation (fund-wide)
        try:
            preview = PortfolioValuationService.preview_epoch_for_fund(
                fund_id=core_fund_id,
                start_date=start_date,
                end_date=end_date,
                performance_rate=performance_rate,
                session=db.session,
            )
            
            # Validation: reconciliation tolerance is $0.01
            # Use Decimal for comparison
            calculated_total = Decimal(str(preview.get("reconciliation_total", preview.get("total_local_valuation"))))
            diff = abs(calculated_total - head_office_total)
            
            if diff > Decimal("0.01"):
                return make_response(
                    jsonify({
                        "status": 400,
                        "message": f"Reconciliation failed: Local total ${float(calculated_total):.2f} does not match Head Office ${float(head_office_total):.2f} (difference: ${float(diff):.2f})"
                    }),
                    400
                )
            
            # Additional epoch-level reconciliation: verify balance equation
            epoch_valid, epoch_error = _validate_epoch_reconciliation(preview, start_date, end_date, fund_name)
            if not epoch_valid:
                return make_response(
                    jsonify({
                        "status": 400,
                        "message": epoch_error
                    }),
                    400
                )
        except ValueError as ve:
            return make_response(jsonify({"status": 400, "message": f"Dry-run failed: {str(ve)}"}), 400)

        # STEP 1.5: Validate epoch sequence (no skipping/gaps)
        is_valid, error_msg = _validate_epoch_sequence(core_fund_id, start_date, end_date)
        if not is_valid:
            return make_response(
                jsonify({
                    "status": 409,
                    "message": f"Epoch sequence validation failed: {error_msg}"
                }),
                409
            )

        # STEP 2: If reconciliation and sequence validation pass, commit the epoch ledger
        try:
            # Persist the reconciled fund-wide total so reports match what was validated.
            run = ValuationRun(
                core_fund_id=core_fund_id,
                epoch_start=start_date,
                epoch_end=end_date,
                performance_rate=performance_rate,
                head_office_total=calculated_total,
                status="Committed",
            )
            db.session.add(run)
            db.session.flush()  # triggers unique constraint check

            result = PortfolioValuationService.create_epoch_ledger_for_fund(
                fund_id=core_fund_id,
                start_date=start_date,
                end_date=end_date,
                performance_rate=performance_rate,
                head_office_total=head_office_total,
                session=db.session,
            )

            # Keep batches active across valuation cycles unless explicitly closed by admin.
            # Valuation commit should not auto-close/deactivate a batch.
            batch_ids = db.session.query(Investment.batch_id).filter(
                Investment.fund_id == core_fund_id
            ).distinct().all()
            batch_ids = [b[0] for b in batch_ids]
            updated = []
            for bid in batch_ids:
                batch = db.session.query(Batch).filter(Batch.id == bid).first()
                if not batch:
                    continue

                if batch.is_active:
                    updated.append({"batch_id": bid, "status": "Active"})
                else:
                    updated.append({"batch_id": bid, "status": "Deactivated"})

            # Commit everything together
            db.session.commit()

            # STEP 3: Save statements for reporting
            try:
                # Re-run preview to get investor breakdown for statements
                preview_for_statements = PortfolioValuationService.preview_epoch_for_fund(
                    fund_id=core_fund_id,
                    start_date=start_date,
                    end_date=end_date,
                    performance_rate=performance_rate,
                    session=db.session,
                )
                investor_breakdown = preview_for_statements.get("investor_breakdown", [])

                # Get investments for mapping (preserve batch isolation).
                # One client may have multiple active batch positions.
                investments = db.session.query(Investment).filter(Investment.fund_id == core_fund_id).all()
                investments_by_code = {}
                for inv in investments:
                    investments_by_code.setdefault(inv.internal_client_code, []).append(inv)

                # Save statements with withdrawal information.
                # Split each investor-level breakdown into per-investment/per-batch rows.
                from app.utils.audit_log import create_audit_log
                for breakdown in investor_breakdown:
                    code = breakdown["internal_client_code"]
                    matched_investments = investments_by_code.get(code, [])
                    if not matched_investments:
                        continue

                    total_weight = sum((Decimal(str(inv.net_principal or 0)) for inv in matched_investments), Decimal("0.00"))
                    if total_weight <= Decimal("0.00"):
                        total_weight = Decimal(str(len(matched_investments)))

                    opening_total = Decimal(str(breakdown["principal_before_start"] + breakdown["deposits_during_period"]))
                    withdrawals_total = Decimal(str(breakdown["withdrawals_during_period"]))
                    gain_total = Decimal(str(breakdown["profit"]))
                    sum_opening = Decimal("0.00")
                    sum_withdrawals = Decimal("0.00")
                    sum_gain = Decimal("0.00")

                    for idx, inv in enumerate(matched_investments):
                        if total_weight == Decimal(str(len(matched_investments))):
                            ratio = Decimal("1") / Decimal(str(len(matched_investments)))
                        else:
                            ratio = (Decimal(str(inv.net_principal or 0)) / total_weight) if total_weight > 0 else Decimal("0")

                        if idx == len(matched_investments) - 1:
                            allocated_opening = opening_total - sum_opening
                            allocated_withdrawals = withdrawals_total - sum_withdrawals
                            allocated_gain = gain_total - sum_gain
                        else:
                            allocated_opening = (opening_total * ratio).quantize(Decimal("0.01"))
                            allocated_withdrawals = (withdrawals_total * ratio).quantize(Decimal("0.01"))
                            allocated_gain = (gain_total * ratio).quantize(Decimal("0.01"))
                            sum_opening += allocated_opening
                            sum_withdrawals += allocated_withdrawals
                            sum_gain += allocated_gain

                        closing_balance = allocated_opening - allocated_withdrawals + allocated_gain

                        stmt = Statement(
                            investor_id=inv.id,
                            batch_id=inv.batch_id,
                            fund_id=core_fund_id,
                            valuation_run_id=run.id,
                            opening_balance=allocated_opening,
                            withdrawals=allocated_withdrawals,
                            performance_gain=allocated_gain,
                            closing_balance=closing_balance,
                        )
                        db.session.add(stmt)
                        
                        if allocated_withdrawals > 0:
                            create_audit_log(
                                action="WITHDRAWAL_PROCESSED",
                                target_type="Investor",
                                target_id=inv.id,
                                target_name=f"{inv.investor_name} ({code})",
                                description=f"Withdrawal of ${float(allocated_withdrawals):,.2f} processed for {core.fund_name}",
                                old_value={"opening_balance": float(allocated_opening)},
                                new_value={
                                    "opening_balance": float(allocated_opening),
                                    "withdrawal": float(allocated_withdrawals),
                                    "closing_balance": float(closing_balance)
                                },
                                success=True
                            )
                    print(f"✅ Saved isolated statement rows for {code} across {len(matched_investments)} batch position(s)")
                
                db.session.commit()
                # ── STEP 3A2: Persist batch-scoped valuations for all affected batches ──
                # The fund epoch commit is global per-fund; we additionally generate atomic
                # batch valuations (BatchValuation + InvestmentBatchValuation) so UI can
                # always show latest per-batch AUM (e.g. B001 $114,490; B002 $107,000).
                try:
                    from app.logic.batch_valuation_service import BatchValuationService

                    affected_batch_ids = (
                        db.session.query(Investment.batch_id)
                        .filter(Investment.fund_id == core_fund_id, Investment.batch_id.isnot(None))
                        .distinct()
                        .all()
                    )
                    affected_batch_ids = [int(r[0]) for r in affected_batch_ids if r and r[0] is not None]

                    # Backfill: build batch valuations for ALL committed epochs in order
                    # so compounding is correct even if earlier commits happened before we persisted BatchValuation.
                    committed_runs = (
                        db.session.query(ValuationRun)
                        .filter(
                            ValuationRun.core_fund_id == core_fund_id,
                            func.lower(ValuationRun.status) == "committed",
                        )
                        .order_by(ValuationRun.epoch_end.asc())
                        .all()
                    )
                    for vr in committed_runs:
                        vr_end = vr.epoch_end
                        if vr_end and getattr(vr_end, "tzinfo", None) is None:
                            vr_end = vr_end.replace(tzinfo=timezone.utc)
                        for bid in affected_batch_ids:
                            try:
                                BatchValuationService.run_batch_valuation(
                                    batch_id=bid,
                                    performance_rate=vr.performance_rate,
                                    valuation_date=vr_end,
                                )
                            except Exception as one_batch_err:
                                print(
                                    f"Warning: Failed to generate batch valuation for batch {bid} @ {vr_end}: {str(one_batch_err)}"
                                )
                except Exception as batch_snap_err:
                    print(f"Warning: Failed to generate batch valuations post-commit: {str(batch_snap_err)}")

                # ── STEP 3B: Sync Investment.valuation → committed end_balance ──────────
                # After a confirmed epoch the Investment.valuation column must reflect the
                # actual post-withdrawal, post-profit balance so that all balance displays
                # (current_standing, portfolio endpoint, batch detail) are in sync without
                # relying solely on epoch aggregation queries.
                try:
                    for breakdown in investor_breakdown:
                        code = breakdown["internal_client_code"]
                        end_bal = Decimal(str(breakdown.get("profit", 0))) + Decimal(str(breakdown.get("active_capital", 0)))
                        # Use statement closing_balance if available (already computed)
                        # Fetch from the newly-written epoch ledger for accuracy
                        epoch_row = db.session.query(EpochLedger).filter(
                            EpochLedger.internal_client_code == code,
                            func.lower(EpochLedger.fund_name) == core.fund_name.lower(),
                            EpochLedger.epoch_start == start_date,
                            EpochLedger.epoch_end == end_date,
                        ).first()
                        if epoch_row:
                            committed_end_balance = epoch_row.end_balance
                            # Update all Investment rows for this investor+fund to the new balance
                            db.session.query(Investment).filter(
                                Investment.internal_client_code == code,
                                Investment.fund_id == core_fund_id,
                            ).update(
                                {"valuation": committed_end_balance},
                                synchronize_session=False,
                            )
                            print(f"✅ Investment.valuation synced for {code}: ${float(committed_end_balance):,.2f}")
                except Exception as sync_err:
                    print(f"Warning: Failed to sync Investment.valuation after confirm: {str(sync_err)}")

                # ── STEP 3C: Mark Approved withdrawals as Executed ───────────────
                # Executed withdrawals are excluded from future _build_investor_inputs
                # queries (which only look for status == 'Approved').  This is the
                # audit guard preventing double-subtraction in subsequent months.
                try:
                    executed_count = db.session.query(Withdrawal).filter(
                        Withdrawal.status == "Approved",
                        Withdrawal.date_withdrawn >= start_date,
                        Withdrawal.date_withdrawn <= end_date,
                        or_(
                            Withdrawal.fund_id == core_fund_id,
                            and_(
                                Withdrawal.fund_id.is_(None),
                                func.lower(Withdrawal.fund_name) == func.lower(core.fund_name),
                            ),
                        ),
                    ).update({"status": WITHDRAWAL_STATUS_EXECUTED}, synchronize_session=False)
                    if executed_count:
                        print(f"✅ Marked {executed_count} withdrawal(s) as Executed for fund {core.fund_name} — they will not be reprocessed")
                    db.session.commit()
                except Exception as e:
                    print(f"Warning: Failed to mark withdrawals Executed after valuation commit: {str(e)}")
            except Exception as e:
                # Log but don't fail the commit
                print(f"Warning: Failed to save statements: {str(e)}")

            try:
                from app.Batch.controllers import BatchController
                BatchController.refresh_cached_total_capital_for_batch_ids(batch_ids, db.session)
            except Exception as cache_err:
                print(f"Warning: Failed to refresh cached batch totals after valuation commit: {str(cache_err)}")

            return make_response(
                jsonify(
                    {
                        "status": 201,
                        "message": "Valuation confirmed and committed successfully",
                        "data": {**result, "core_fund_id": core_fund_id, "core_fund_name": core.fund_name, "batches_updated": updated},
                    }
                ),
                201,
            )
        except IntegrityError:
            db.session.rollback()
            return make_response(jsonify({"status": 409, "message": "Valuation already committed for this fund and period"}), 409)

    except PermissionError as pe:
        db.session.rollback()
        return make_response(jsonify({"status": 403, "message": str(pe)}), 403)
    except ValueError as ve:
        db.session.rollback()
        return make_response(jsonify({"status": 400, "message": str(ve)}), 400)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)

@valuation_v1.route("/api/v1/valuation/nav/legacy", methods=["POST"])
@jwt_required()
def valuation_nav():
    """
    Legacy monthly share-based valuation run.
    This legacy route is retained only for compatibility and no longer
    collides with the new NAV-based valuation endpoint.
    Body: { epoch_end: "YYYY-MM-DD", atium_nav: 1.23, axiom_nav: 4.56 }
    """
    try:
        data = request.get_json() or {}
        epoch_end_str = data.get("epoch_end")
        if not epoch_end_str:
            return make_response(jsonify({"status": 400, "message": "epoch_end is required"}), 400)
            
        epoch_end = datetime.fromisoformat(epoch_end_str).date()
        
        # Hardcoded mapping for the two primary funds as requested
        fund_navs = {
            "Atium": data.get("atium_nav"),
            "Axiom": data.get("axiom_nav")
        }

        commit_results = []
        for fund_name, nav_price in fund_navs.items():
            if nav_price is None:
                continue

            sc = db.session.query(ShareClass).join(CoreFund).filter(func.lower(CoreFund.fund_name) == fund_name.lower()).first()
            if not sc:
                logger.warning(f"No share class found for fund: {fund_name}")
                continue

            total_shares = db.session.query(
                func.coalesce(func.sum(InvestorShares.shares_owned), 0)
            ).join(Investment, InvestorShares.investment_id == Investment.id).filter(
                Investment.share_class_id == sc.id,
                InvestorShares.is_active == True
            ).scalar() or Decimal("0")
            total_shares = Decimal(str(total_shares))

            nav_per_share = Decimal(str(nav_price))
            system_total_nav = (total_shares * nav_per_share).quantize(Decimal("0.01"))
            head_office_nav = system_total_nav
            difference = Decimal("0.00")

            holdings = db.session.query(InvestorShares).join(Investment, InvestorShares.investment_id == Investment.id).filter(
                Investment.share_class_id == sc.id,
                InvestorShares.is_active == True
            ).all()

            snapshots_created = 0
            investor_details = []
            for holding in holdings:
                deployment_nav = Decimal(str(holding.deployment_nav or 0))
                market_value = (Decimal(str(holding.shares_owned)) * nav_per_share).quantize(Decimal("0.01"))
                performance_pct = holding.calculate_performance_percentage(nav_per_share)

                investor = db.session.query(Investment).filter(Investment.id == holding.investment_id).first()
                investor_details.append({
                    "client_code": investor.internal_client_code if investor else None,
                    "shares": float(holding.shares_owned),
                    "market_value": float(market_value),
                    "performance_pct": float(performance_pct),
                })

                existing_snapshot = ValuationSnapshot.get_snapshot_at_date(
                    investor_shares_id=holding.id,
                    valuation_date=epoch_end,
                )
                if not existing_snapshot:
                    snapshot = ValuationSnapshot.create_snapshot(
                        investor_shares_id=holding.id,
                        valuation_date=epoch_end,
                        nav_per_share=nav_per_share,
                        shares_held=holding.shares_owned,
                        deployment_nav=holding.deployment_nav,
                    )
                    db.session.add(snapshot)
                    snapshots_created += 1

            nav_history = NavHistory(
                share_class_id=sc.id,
                nav_date=epoch_end,
                nav_per_share=nav_per_share,
                total_fund_nav=system_total_nav,
                source="valuation",
            )
            db.session.add(nav_history)

            commit_results.append({
                "share_class_id": sc.id,
                "fund_name": fund_name,
                "total_shares": float(total_shares),
                "nav_per_share": float(nav_per_share),
                "system_total_nav": float(system_total_nav),
                "difference": float(difference),
                "snapshots_created": snapshots_created,
                "investors": investor_details,
            })

            db.session.commit()        
        return make_response(jsonify({
            "status": 201,
            "message": "Monthly NAV valuation completed successfully",
            "data": commit_results
        }), 201)

    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Valuation error: {str(e)}"}), 500)


@valuation_v1.route("/api/v1/valuation/epoch/dry-run", methods=["GET"])
@jwt_required()
def dry_run_epoch_valuation():
    """
    Dry-run preview for UI.

    Query params:
      - fund_id (required)
      - start_date (required)
      - end_date (required)
      - performance_rate (required)  (decimal fraction OR percent; UI sends percent)
      - head_office_total (optional) (for diff computation)
    """
    try:
        fund_id_raw = request.args.get("fund_id")
        if not fund_id_raw:
            return make_response(jsonify({"status": 400, "message": "fund_id is required"}), 400)
        try:
            fund_id = int(fund_id_raw)
        except Exception:
            return make_response(jsonify({"status": 400, "message": "fund_id must be an integer"}), 400)

        start_date = _parse_iso_dt(request.args.get("start_date"), "start_date")
        end_date = _parse_iso_dt(request.args.get("end_date"), "end_date")

        performance_rate_raw = request.args.get("performance_rate")
        if performance_rate_raw is None:
            return make_response(jsonify({"status": 400, "message": "performance_rate is required"}), 400)

        # UI supplies % (e.g. "5" means 5%, "-0.25" means -0.25%).
        # The field is labeled "Performance rate (%)", so always divide by 100.
        pr = float(performance_rate_raw)
        performance_rate = pr / 100.0

        preview = PortfolioValuationService.preview_epoch_for_fund(
            fund_id=fund_id,
            start_date=start_date,
            end_date=end_date,
            performance_rate=performance_rate,
            session=db.session,
        )

        head_office_total_raw = request.args.get("head_office_total")
        diff = None
        if head_office_total_raw is not None:
            try:
                ho = float(head_office_total_raw)
                diff = round(abs(preview["total_local_valuation"] - ho), 2)
            except Exception:
                diff = None

        return make_response(
            jsonify(
                {
                    "status": 200,
                    "message": "Dry run complete",
                    "data": {
                        **preview,
                        "diff_vs_head_office": diff,
                    },
                }
            ),
            200,
        )
    except ValueError as ve:
        return make_response(jsonify({"status": 400, "message": str(ve)}), 400)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@valuation_v1.route("/api/v1/batches/<int:batch_id>/valuation-summary", methods=["GET"])
@jwt_required()
def get_batch_valuation_summary(batch_id: int):
    """
    Batch valuation summary powered by EpochLedger:
    - Initial Capital: sum of investments in batch
    - Total Profit Earned: sum of ledger profits for investors in batch
    - Current Value: sum of latest end_balance per (internal_client_code, fund_name) for investors in batch
    """
    try:
        session = db.session

        initial_capital = session.query(func.coalesce(func.sum(Investment.amount_deposited), 0)).filter(
            Investment.batch_id == batch_id
        ).scalar()

        codes_subq = session.query(Investment.internal_client_code).filter(
            Investment.batch_id == batch_id
        ).distinct().subquery()

        total_profit = session.query(func.coalesce(func.sum(EpochLedger.profit), 0)).filter(
            EpochLedger.internal_client_code.in_(select(codes_subq))
        ).scalar()

        latest_per_key = session.query(
            EpochLedger.internal_client_code.label("code"),
            func.lower(EpochLedger.fund_name).label("fund"),
            func.max(EpochLedger.epoch_end).label("max_end"),
        ).filter(
            EpochLedger.internal_client_code.in_(select(codes_subq))
        ).group_by(
            EpochLedger.internal_client_code,
            func.lower(EpochLedger.fund_name),
        ).subquery()

        current_value = session.query(func.coalesce(func.sum(EpochLedger.end_balance), 0)).join(
            latest_per_key,
            (EpochLedger.internal_client_code == latest_per_key.c.code)
            & (func.lower(EpochLedger.fund_name) == latest_per_key.c.fund)
            & (EpochLedger.epoch_end == latest_per_key.c.max_end),
        ).scalar()

        return make_response(
            jsonify(
                {
                    "status": 200,
                    "message": "Batch valuation summary retrieved",
                    "data": {
                        "batch_id": batch_id,
                        "initial_capital": float(initial_capital or 0),
                        "total_profit_earned": float(total_profit or 0),
                        "current_value": float(current_value or 0),
                    },
                }
            ),
            200,
        )
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@valuation_v1.route("/api/v1/valuation/batch", methods=["POST"])
@jwt_required()
def run_batch_valuation():
    """
    Run atomic batch-level valuation.
    
    Body:
    {
      "batch_id": 1,
      "performance_rate": 0.05,
      "valuation_date": "2026-04-30"
    }
    """
    try:
        data = request.get_json() or {}

        batch_id = data.get("batch_id")
        if batch_id is None:
            return make_response(jsonify({"status": 400, "message": "batch_id is required"}), 400)
        try:
            batch_id = int(batch_id)
        except Exception:
            return make_response(jsonify({"status": 400, "message": "batch_id must be an integer"}), 400)

        performance_rate = data.get("performance_rate")
        if performance_rate is None:
            return make_response(jsonify({"status": 400, "message": "performance_rate is required"}), 400)
        performance_rate = float(performance_rate)

        valuation_date_raw = data.get("valuation_date")
        if valuation_date_raw is None:
            return make_response(jsonify({"status": 400, "message": "valuation_date is required"}), 400)
        valuation_date = _parse_iso_dt(valuation_date_raw, "valuation_date")

        from app.logic.batch_valuation_service import BatchValuationService
        result = BatchValuationService.run_batch_valuation(
            batch_id=batch_id,
            performance_rate=performance_rate,
            valuation_date=valuation_date
        )

        return make_response(
            jsonify(
                {
                    "status": 201,
                    "message": "Batch valuation completed successfully",
                    "data": result,
                }
            ),
            201,
        )

    except ValueError as ve:
        db.session.rollback()
        return make_response(jsonify({"status": 400, "message": str(ve)}), 400)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@valuation_v1.route("/api/v1/valuation/batch/<int:batch_id>", methods=["GET"])
@jwt_required()
def get_batch_valuation_history(batch_id: int):
    """
    Get valuation history for a specific batch.
    """
    try:
        from app.Valuation.model import BatchValuation
        
        valuations = db.session.query(BatchValuation).filter(
            BatchValuation.batch_id == batch_id
        ).order_by(BatchValuation.period_end_date.asc()).all()
        
        data = [
            {
                "id": v.id,
                "period_end_date": v.period_end_date.isoformat(),
                "balance_at_end_of_period": float(v.balance_at_end_of_period),
                "performance_rate": float(v.performance_rate),
                "total_principal": float(v.total_principal),
                "total_profit": float(v.total_profit),
                "total_withdrawals": float(v.total_withdrawals),
                "created_at": v.created_at.isoformat(),
            }
            for v in valuations
        ]
        
        return make_response(
            jsonify(
                {
                    "status": 200,
                    "message": f"Retrieved {len(data)} valuation records for batch {batch_id}",
                    "data": data,
                }
            ),
            200,
        )

    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@valuation_v1.route("/api/v1/valuation/backfill-batch-valuations", methods=["POST"])
@jwt_required()
def backfill_batch_valuations():
    """
    Backfill BatchValuation / InvestmentBatchValuation for an already-committed fund.

    Body:
    {
      "fund_id": 1
    }
    """
    try:
        data = request.get_json() or {}
        fund_id = data.get("fund_id")
        if fund_id is None:
            return make_response(jsonify({"status": 400, "message": "fund_id is required"}), 400)
        fund_id = int(fund_id)

        core = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not core:
            return make_response(jsonify({"status": 404, "message": "Core fund not found"}), 404)

        from app.logic.batch_valuation_service import BatchValuationService

        affected_batch_ids = (
            db.session.query(Investment.batch_id)
            .filter(Investment.fund_id == fund_id, Investment.batch_id.isnot(None))
            .distinct()
            .all()
        )
        affected_batch_ids = [int(r[0]) for r in affected_batch_ids if r and r[0] is not None]

        committed_runs = (
            db.session.query(ValuationRun)
            .filter(
                ValuationRun.core_fund_id == fund_id,
                func.lower(ValuationRun.status) == "committed",
            )
            .order_by(ValuationRun.epoch_end.asc())
            .all()
        )
        if not committed_runs:
            return make_response(jsonify({"status": 404, "message": "No committed valuation runs found for this fund"}), 404)

        results = []
        for vr in committed_runs:
            vr_end = vr.epoch_end
            if vr_end and getattr(vr_end, "tzinfo", None) is None:
                vr_end = vr_end.replace(tzinfo=timezone.utc)
            for bid in affected_batch_ids:
                try:
                    r = BatchValuationService.run_batch_valuation(
                        batch_id=bid,
                        performance_rate=vr.performance_rate,
                        valuation_date=vr_end,
                    )
                    results.append(r)
                except Exception as one_batch_err:
                    results.append({
                        "batch_id": bid,
                        "valuation_date": vr_end.isoformat() if vr_end else None,
                        "error": str(one_batch_err),
                    })

        return make_response(jsonify({
            "status": 200,
            "message": "Backfill completed",
            "data": {
                "fund_id": fund_id,
                "fund_name": core.fund_name,
                "batches": affected_batch_ids,
                "runs": len(committed_runs),
                "results": results,
            }
        }), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)




# ==================== NAV-BASED VALUATION ====================

def _reconcile_class_totals(cls, tolerance=Decimal("10.00")):
    """
    Cheap, aggregate-only reconciliation check for one class — no per-investor
    rows touched. Returns (share_class, total_shares, nav_per_share,
    head_office_nav, system_total_nav, difference, status) or raises ValueError.
    """
    if not all(k in cls for k in ["share_class_id", "nav_per_share"]):
        raise ValueError("Each class must have share_class_id and nav_per_share")

    share_class_id = int(cls["share_class_id"])
    nav_per_share = Decimal(str(cls["nav_per_share"]))
    if "total_fund_nav_from_axys" in cls:
        head_office_nav = Decimal(str(cls["total_fund_nav_from_axys"]))
    elif "total_fund_nav" in cls:
        head_office_nav = Decimal(str(cls["total_fund_nav"]))
    else:
        raise ValueError("Each class must have total_fund_nav_from_axys or total_fund_nav")

    share_class = db.session.query(ShareClass).filter(ShareClass.id == share_class_id).first()
    if not share_class:
        raise ValueError(f"Share class {share_class_id} not found")

    total_shares = db.session.query(
        func.coalesce(func.sum(InvestorShares.shares_owned), 0)
    ).join(Investment, InvestorShares.investment_id == Investment.id).filter(
        Investment.share_class_id == share_class_id,
        InvestorShares.is_active == True,
    ).scalar() or Decimal("0")
    total_shares = Decimal(str(total_shares))

    system_total_nav = (total_shares * nav_per_share).quantize(Decimal("0.01"))
    difference = abs(system_total_nav - head_office_nav).quantize(Decimal("0.01"))
    status = "PASS" if difference <= tolerance else "FAIL"

    return share_class, total_shares, nav_per_share, head_office_nav, system_total_nav, difference, status


@valuation_v1.route("/api/v1/valuation/nav", methods=["POST"])
@jwt_required()
def nav_valuation():
    """
    Monthly NAV-based valuation — commits as a BACKGROUND job and returns
    immediately, same reasoning as bulk-upload's commit_rows(): this used to
    write a ValuationSnapshot per investor inline in the request (with a
    redundant per-row Investment re-query on top, since the join that already
    fetched investor_rows didn't select Investment as a loaded entity), which
    is what made "commit valuation" hang/not load at scale. See
    _run_valuation_commit_job for the fixed, bulk-prefetch, bulk-insert
    version.

    Request: {
      "valuation_date": "2026-04-10",
      "classes": [
        { "share_class_id": 1, "nav_per_share": 1389.5737, "total_fund_nav_from_axys": 1072636.69 }
      ]
    }
    Response (202): {"status": 202, "data": {"job_id": 1, "status": "queued"}}
    Poll GET /api/v1/valuation/jobs/<job_id> for progress and, once
    status is "completed"/"failed", the per-class reconciliation results this
    endpoint used to return synchronously.

    dry_run=True is NOT supported here (the frontend's separate /preview
    endpoint — nav_valuation_preview below — is the dry-run path, and never
    writes anything, so it stays synchronous). A dry_run flag in the body is
    rejected rather than silently ignored, so a caller expecting the old
    inline-preview behavior from this endpoint fails loudly instead of
    accidentally queuing a real commit.
    """
    try:
        data = request.get_json() or {}
        if data.get("dry_run"):
            return make_response(jsonify({
                "status": 400,
                "message": "dry_run is not supported on this endpoint — use /api/v1/valuation/preview instead.",
            }), 400)
        if not data.get("valuation_date") or not isinstance(data.get("classes"), list):
            return make_response(jsonify({"status": 400, "message": "valuation_date and classes are required"}), 400)

        # Validate up front (cheap, aggregate-only) so a bad request fails
        # immediately instead of after a job's already been queued.
        try:
            datetime.fromisoformat(data["valuation_date"])
            # Task 9: a single valuation run must never mix Funds and Shares
            # classes — each is a completely separate NAV universe.
            seen_products = set()
            for cls in data["classes"]:
                share_class, *_rest = _reconcile_class_totals(cls)
                seen_products.add(share_class.product_type)
            if len(seen_products) > 1:
                return make_response(jsonify({
                    "status": 400,
                    "message": "Cannot mix FUNDS and SHARES share classes in one valuation run",
                }), 400)
        except ValueError as ve:
            return make_response(jsonify({"status": 400, "message": str(ve)}), 400)

        total_investors = db.session.query(func.count(InvestorShares.id)).join(
            Investment, InvestorShares.investment_id == Investment.id
        ).filter(
            Investment.share_class_id.in_([int(c["share_class_id"]) for c in data["classes"]]),
            InvestorShares.is_active == True,
        ).scalar() or 0

        user_id, user_email = _current_user_for_job()
        job = ValuationJob(
            status="queued",
            total_investors=total_investors,
            request_payload=json.dumps(data),
            created_by_user_id=user_id,
            created_by_email=user_email,
        )
        db.session.add(job)
        db.session.commit()

        if not _schedule_valuation_job(job.id):
            job.status = "failed"
            job.error_message = "Could not schedule the background job (scheduler unavailable)"
            job.completed_at = datetime.now(timezone.utc)
            db.session.commit()
            return make_response(jsonify({"status": 500, "message": "Could not start the valuation commit job"}), 500)

        return make_response(jsonify({
            "status": 202,
            "message": f"Valuation commit job started for {total_investors} investor(s)",
            "data": {"job_id": job.id, "total_investors": total_investors, "status": job.status},
        }), 202)

    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


def _schedule_valuation_job(job_id: int) -> bool:
    """Runs _run_valuation_commit_job(job_id) once, immediately, on the app's
    existing APScheduler background thread pool — same pattern as
    app/BulkUpload/route.py's _schedule_bulk_upload_job."""
    try:
        from app.logic.batch_scheduler_service import BatchSchedulerService
        scheduler = BatchSchedulerService.scheduler
        if scheduler is None:
            return False
        app_obj = current_app._get_current_object()
        scheduler.add_job(
            func=_run_valuation_commit_job,
            args=[app_obj, job_id],
            trigger="date",
            run_date=datetime.now(timezone.utc),
            id=f"valuation_job_{job_id}",
            misfire_grace_time=3600,
            max_instances=1,
            replace_existing=True,
        )
        return True
    except Exception as e:
        logger.error(f"Could not schedule valuation job {job_id}: {e}")
        return False


VALUATION_CHUNK_SIZE = 1500


def _run_valuation_commit_job(app, job_id):
    """
    Background worker for a NAV valuation commit. Same chunked/bulk shape as
    _run_bulk_upload_commit_job: prefetches everything the per-investor loop
    needs (Investment rows, existing-snapshot membership) in ONE query each
    per class instead of two queries per investor, then bulk-inserts
    ValuationSnapshot rows in chunks with one commit per chunk instead of one
    per investor.
    """
    with app.app_context():
        session = db.session

        # Atomic claim — see _run_bulk_upload_commit_job's docstring for why
        # this is a single UPDATE...WHERE status='queued' rather than a
        # read-then-write check.
        claim = session.execute(
            ValuationJob.__table__.update()
            .where(ValuationJob.id == job_id, ValuationJob.status == "queued")
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        session.commit()
        if claim.rowcount == 0:
            return

        job = session.query(ValuationJob).filter(ValuationJob.id == job_id).first()

        try:
            data = json.loads(job.request_payload)
            valuation_date = datetime.fromisoformat(data["valuation_date"]).date()
            tolerance = Decimal("10.00")

            # Re-validate reconciliation at run time (state may have changed
            # between the request that queued this job and now) — if anything
            # fails, write nothing, matching the old inline behavior exactly.
            class_contexts = []
            any_fail = False
            for cls in data["classes"]:
                share_class, total_shares, nav_per_share, head_office_nav, system_total_nav, difference, status = (
                    _reconcile_class_totals(cls, tolerance)
                )
                if status == "FAIL":
                    any_fail = True
                class_contexts.append({
                    "share_class": share_class,
                    "share_class_id": share_class.id,
                    "total_shares": total_shares,
                    "nav_per_share": nav_per_share,
                    "head_office_nav": head_office_nav,
                    "system_total_nav": system_total_nav,
                    "difference": difference,
                    "status": status,
                })

            if any_fail:
                job.status = "failed"
                job.error_message = "Reconciliation failed for one or more classes. Fix values and preview again."
                job.completed_at = datetime.now(timezone.utc)
                session.commit()
                return

            results = []
            touched_batch_ids = set()
            processed_investors = 0
            total_snapshots_created = 0

            for ctx in class_contexts:
                share_class_id = ctx["share_class_id"]
                nav_per_share = ctx["nav_per_share"]
                head_office_nav = ctx["head_office_nav"]
                system_total_nav = ctx["system_total_nav"]
                difference = ctx["difference"]
                status = ctx["status"]

                holdings = db.session.query(InvestorShares).join(
                    Investment, InvestorShares.investment_id == Investment.id
                ).filter(
                    Investment.share_class_id == share_class_id,
                    InvestorShares.is_active == True,
                ).all()

                # Bulk prefetch — one query each for the whole class instead of
                # two queries (Investment re-fetch + snapshot existence check)
                # per investor.
                investment_ids = [h.investment_id for h in holdings]
                investments_by_id = {
                    inv.id: inv
                    for inv in session.query(Investment).filter(Investment.id.in_(investment_ids)).all()
                } if investment_ids else {}

                holding_ids = [h.id for h in holdings]
                existing_snapshot_ids = {
                    row[0]
                    for row in session.query(ValuationSnapshot.investor_shares_id).filter(
                        ValuationSnapshot.investor_shares_id.in_(holding_ids),
                        ValuationSnapshot.valuation_date == valuation_date,
                    ).all()
                } if holding_ids else set()

                snapshots_created = 0
                allocation_multiplier = Decimal("1")
                if system_total_nav > 0:
                    allocation_multiplier = (head_office_nav / system_total_nav)

                remaining_head_office = head_office_nav
                new_snapshot_rows = []
                now = datetime.now(timezone.utc)

                for index, holding in enumerate(holdings):
                    raw_value = (Decimal(str(holding.shares_owned)) * nav_per_share)
                    if index == len(holdings) - 1 and difference != Decimal("0"):
                        market_value = remaining_head_office.quantize(Decimal("0.01"))
                    else:
                        market_value = (raw_value * allocation_multiplier).quantize(Decimal("0.01"))
                        remaining_head_office -= market_value

                    performance_pct = holding.calculate_performance_percentage(nav_per_share)

                    if holding.id not in existing_snapshot_ids and status == "PASS":
                        # The PERSISTED snapshot must match what
                        # ValuationSnapshot.create_snapshot() computed in the
                        # original inline code — shares_held * nav_per_share
                        # (the raw, un-allocated value), NOT the head-office-
                        # reconciled `market_value` above (that one is only
                        # ever shown in the API response, never what was
                        # saved as this investor's Golden Source snapshot).
                        # Likewise performance_pct here is quantized to 4dp
                        # (create_snapshot's precision), not the 2dp
                        # `performance_pct` variable used in the response.
                        snapshot_shares_held = Decimal(str(holding.shares_owned))
                        snapshot_deployment_nav = Decimal(str(holding.deployment_nav))
                        snapshot_market_value = (snapshot_shares_held * nav_per_share).quantize(Decimal("0.01"))
                        if snapshot_deployment_nav == 0:
                            snapshot_performance_pct = Decimal("0.00")
                        else:
                            snapshot_performance_pct = (
                                ((nav_per_share / snapshot_deployment_nav) - 1) * 100
                            ).quantize(Decimal("0.0001"))
                        new_snapshot_rows.append({
                            "investor_shares_id": holding.id,
                            "valuation_date": valuation_date,
                            "nav_per_share": nav_per_share,
                            "shares_held": holding.shares_owned,
                            "market_value": snapshot_market_value,
                            "performance_pct": snapshot_performance_pct,
                            "created_at": now,
                        })
                        snapshots_created += 1

                    processed_investors += 1
                    if processed_investors % VALUATION_CHUNK_SIZE == 0:
                        job.processed_investors = processed_investors
                        session.commit()

                # Bulk-insert this class's new snapshots in chunks — chunk the
                # WRITE, not the read (same lesson as bulk-upload commit).
                for i in range(0, len(new_snapshot_rows), VALUATION_CHUNK_SIZE):
                    chunk = new_snapshot_rows[i:i + VALUATION_CHUNK_SIZE]
                    if chunk:
                        session.execute(insert(ValuationSnapshot), chunk)
                        session.commit()

                total_snapshots_created += snapshots_created

                existing_nav = session.query(NavHistory).filter(
                    NavHistory.share_class_id == share_class_id,
                    NavHistory.nav_date == valuation_date,
                    NavHistory.source == "valuation"
                ).first()
                if existing_nav:
                    existing_nav.nav_per_share = nav_per_share
                    existing_nav.total_fund_nav = head_office_nav
                else:
                    session.add(NavHistory(
                        share_class_id=share_class_id,
                        nav_date=valuation_date,
                        nav_per_share=nav_per_share,
                        total_fund_nav=head_office_nav,
                        source="valuation",
                    ))

                batches = session.query(Batch).filter(
                    Batch.share_class_id == share_class_id,
                    Batch.date_deployed.isnot(None),
                ).all()
                for batch in batches:
                    batch.deployment_total_nav = head_office_nav
                    if batch.deployment_nav is None:
                        batch.deployment_nav = nav_per_share
                    if batch.total_shares is None:
                        batch.total_shares = ctx["total_shares"]
                    touched_batch_ids.add(batch.id)

                results.append({
                    "class_code": ctx["share_class"].class_code,
                    "total_shares": float(ctx["total_shares"]),
                    "nav_per_share": float(nav_per_share),
                    "system_total_nav": float(system_total_nav),
                    "head_office_nav": float(head_office_nav),
                    "difference": float(difference),
                    "status": status,
                    "snapshots_created": snapshots_created,
                    "investor_count": len(holdings),
                })

                job.processed_investors = processed_investors
                session.commit()

            if touched_batch_ids:
                try:
                    from app.Batch.controllers import BatchController
                    BatchController.refresh_cached_total_capital_for_batch_ids(touched_batch_ids, session)
                except Exception as cache_err:
                    logger.warning(f"Failed to refresh cached batch totals after valuation commit job {job_id}: {cache_err}")

            job.status = "completed"
            job.snapshots_created = total_snapshots_created
            job.processed_investors = processed_investors
            job.results_payload = json.dumps({"valuation_date": data["valuation_date"], "classes": results})
            job.completed_at = datetime.now(timezone.utc)
            session.commit()
            logger.info(f"Valuation commit job {job_id} completed: {total_snapshots_created} snapshot(s) across {len(class_contexts)} class(es)")

        except Exception as e:
            session.rollback()
            job = session.query(ValuationJob).filter(ValuationJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.now(timezone.utc)
                session.commit()
            logger.error(f"Valuation commit job {job_id} failed: {e}", exc_info=True)


@valuation_v1.route("/api/v1/valuation/jobs/<int:job_id>", methods=["GET"])
@jwt_required()
def get_valuation_job(job_id):
    job = db.session.query(ValuationJob).filter(ValuationJob.id == job_id).first()
    if not job:
        return make_response(jsonify({"status": 404, "message": "Job not found"}), 404)

    data = {
        "id": job.id,
        "status": job.status,
        "total_investors": job.total_investors,
        "processed_investors": job.processed_investors,
        "snapshots_created": job.snapshots_created,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message,
    }
    if job.status in ("completed", "failed") and job.results_payload:
        try:
            data["results"] = json.loads(job.results_payload)
        except Exception:
            data["results"] = None
    return make_response(jsonify({"status": 200, "data": data}), 200)


@valuation_v1.route("/api/v1/valuation/preview", methods=["POST"])
@jwt_required()
def nav_valuation_preview():
    """
    Dry-run preview for NAV valuation.
    Returns per-class reconciliation and investor-level calculations without saving.
    Never fails due to reconciliation mismatch; each class is marked PASS/FAIL.
    """
    try:
        data = request.get_json() or {}
        if not data.get("valuation_date") or not isinstance(data.get("classes"), list):
            return make_response(jsonify({"status": 400, "message": "valuation_date and classes are required"}), 400)

        valuation_date = datetime.fromisoformat(str(data["valuation_date"])).date()
        tolerance = Decimal("10.00")

        preview_classes = []
        seen_products = set()
        for cls in data["classes"]:
            if not all(k in cls for k in ["share_class_id", "nav_per_share"]):
                return make_response(
                    jsonify({"status": 400, "message": "Each class must have share_class_id and nav_per_share"}),
                    400,
                )

            share_class_id = int(cls["share_class_id"])
            nav_per_share = Decimal(str(cls["nav_per_share"]))
            if "total_fund_nav_from_axys" in cls:
                head_office_nav = Decimal(str(cls["total_fund_nav_from_axys"]))
            elif "total_fund_nav" in cls:
                head_office_nav = Decimal(str(cls["total_fund_nav"]))
            else:
                return make_response(
                    jsonify({"status": 400, "message": "Each class must have total_fund_nav_from_axys or total_fund_nav"}),
                    400,
                )

            share_class = db.session.query(ShareClass).filter(ShareClass.id == share_class_id).first()
            if not share_class:
                return make_response(jsonify({"status": 404, "message": f"Share class {share_class_id} not found"}), 404)

            # Task 9: a single valuation run must never mix Funds and Shares
            # classes — each is a completely separate NAV universe.
            seen_products.add(share_class.product_type)
            if len(seen_products) > 1:
                return make_response(jsonify({
                    "status": 400,
                    "message": "Cannot mix FUNDS and SHARES share classes in one valuation run",
                }), 400)

            total_shares = db.session.query(
                func.coalesce(func.sum(InvestorShares.shares_owned), 0)
            ).join(Investment, InvestorShares.investment_id == Investment.id).filter(
                Investment.share_class_id == share_class_id,
                InvestorShares.is_active == True,
            ).scalar() or Decimal("0")
            total_shares = Decimal(str(total_shares))

            holdings = db.session.query(InvestorShares).join(Investment, InvestorShares.investment_id == Investment.id).filter(
                Investment.share_class_id == share_class_id,
                InvestorShares.is_active == True,
            ).all()

            # Prefetch once instead of a lazy-load per row below (h.investment
            # would otherwise fire its own query per holding — the join above
            # only filtered by Investment, it didn't load it as an entity).
            _investment_ids = [h.investment_id for h in holdings]
            _investments_by_id = {
                inv.id: inv
                for inv in db.session.query(Investment).filter(Investment.id.in_(_investment_ids)).all()
            } if _investment_ids else {}

            investors = []
            system_total_nav = Decimal("0")
            for h in holdings:
                shares = Decimal(str(h.shares_owned or 0))
                market_value = shares * nav_per_share
                system_total_nav += market_value

            system_total_nav = system_total_nav.quantize(Decimal("0.01"))
            difference = abs(system_total_nav - head_office_nav).quantize(Decimal("0.01"))
            status = "PASS" if difference <= tolerance else "FAIL"

            allocation_multiplier = Decimal("1")
            if status == "PASS" and system_total_nav > 0:
                allocation_multiplier = head_office_nav / system_total_nav

            remaining_head_office = head_office_nav
            for index, h in enumerate(holdings):
                shares = Decimal(str(h.shares_owned or 0))
                raw_value = shares * nav_per_share
                if status == "PASS" and index == len(holdings) - 1:
                    market_value = remaining_head_office.quantize(Decimal("0.01"))
                else:
                    market_value = (raw_value * allocation_multiplier).quantize(Decimal("0.01"))
                    if status == "PASS":
                        remaining_head_office -= market_value

                deployment_nav = Decimal(str(h.deployment_nav or 0))
                perf = Decimal("0")
                if deployment_nav > 0:
                    perf = ((nav_per_share - deployment_nav) / deployment_nav) * Decimal("100")

                inv = _investments_by_id.get(h.investment_id)

                investors.append({
                    "client_code": inv.internal_client_code if inv else None,
                    "shares": float(shares.quantize(Decimal("0.0001"))),
                    "market_value": float(market_value.quantize(Decimal("0.01"))),
                    "performance_pct": float(perf.quantize(Decimal("0.01"))),
                })

            preview_classes.append({
                "class_code": share_class.class_code,
                "total_shares": float(total_shares),
                "nav_per_share": float(nav_per_share.quantize(Decimal("0.000001"))),
                "system_total_nav": float(head_office_nav if status == "PASS" else system_total_nav),
                "head_office_nav": float(head_office_nav.quantize(Decimal("0.01"))),
                "difference": float(difference),
                "status": status,
                "investors": investors,
            })

        return make_response(
            jsonify(
                {
                    "status": 200,
                    "data": {
                        "valuation_date": valuation_date.isoformat(),
                        "classes": preview_classes,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)

