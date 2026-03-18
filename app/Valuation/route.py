from flask import request, Blueprint, jsonify, make_response
from flask_jwt_extended import jwt_required
from datetime import datetime

from app.database.database import db
from app.logic.valuation_service import PortfolioValuationService
from app.Investments.model import Investment, EpochLedger
from sqlalchemy import func, select
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Valuation.model import ValuationRun
from sqlalchemy.exc import IntegrityError


valuation_v1 = Blueprint("valuation_v1", __name__, url_prefix="/api/v1")


def _parse_iso_dt(value, field_name: str) -> datetime:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{field_name} is required")
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 datetime string")
    try:
        # Accept both "YYYY-MM-DD" and full ISO strings
        if len(value.strip()) == 10:
            return datetime.fromisoformat(value.strip())
        return datetime.fromisoformat(value.strip())
    except Exception as e:
        raise ValueError(f"Invalid {field_name} format: {str(e)}")


@valuation_v1.route("/valuation/epoch", methods=["POST"])
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


@valuation_v1.route("/valuation/funds", methods=["GET"])
@jwt_required()
def valuation_funds():
    """Return all active core funds."""
    try:
        funds = (
            db.session.query(CoreFund)
            .filter(CoreFund.is_active == True)  # noqa: E712
            .order_by(CoreFund.fund_name.asc(), CoreFund.id.asc())
            .all()
        )
        data = [{"id": f.id, "fund_name": f.fund_name, "is_active": f.is_active} for f in funds]
        return make_response(jsonify({"status": 200, "message": "Active funds retrieved", "data": data}), 200)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@valuation_v1.route("/valuation/dry-run", methods=["POST"])
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

            perf_pct = data.get("performance_rate_percent")
            if perf_pct is None:
                return make_response(jsonify({"status": 400, "message": "performance_rate_percent is required"}), 400)
            performance_rate = float(perf_pct) / 100.0

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

            diff = round(abs(float(preview["calculated_total"]) - head_office_total), 2)
            preview["head_office_total"] = head_office_total
            preview["diff"] = diff
            preview["is_reconciled"] = diff <= 0.01

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

        perf_pct = data.get("performance_rate_percent")
        if perf_pct is None:
            return make_response(jsonify({"status": 400, "message": "performance_rate_percent is required"}), 400)
        performance_rate = float(perf_pct) / 100.0

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

        calculated_total = float(preview["total_local_valuation"])
        diff = round(abs(calculated_total - head_office_total), 2)

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
    except ValueError as ve:
        return make_response(jsonify({"status": 400, "message": str(ve)}), 400)
    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@valuation_v1.route("/valuation/confirm", methods=["POST"])
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

        # Consolidated by core fund name
        fund_name = (data.get("fund_name") or "").strip()
        if not fund_name:
            return make_response(jsonify({"status": 400, "message": "fund_name is required"}), 400)

        core = db.session.query(CoreFund).filter(func.lower(CoreFund.fund_name) == fund_name.lower()).first()
        if not core:
            return make_response(jsonify({"status": 404, "message": "Core fund not found"}), 404)
        core_fund_id = core.id

        start_date = _parse_iso_dt(data.get("start_date"), "start_date")
        end_date = _parse_iso_dt(data.get("end_date"), "end_date")

        # Accept performance_rate_percent (e.g., 5 for 5%)
        perf_pct = data.get("performance_rate_percent")
        if perf_pct is None:
            return make_response(jsonify({"status": 400, "message": "performance_rate_percent is required"}), 400)
        
        # Convert percent to decimal (5 -> 0.05)
        performance_rate = float(perf_pct) / 100.0
        
        head_office_total = data.get("head_office_total")
        if head_office_total is None:
            return make_response(jsonify({"status": 400, "message": "head_office_total is required"}), 400)
        head_office_total = float(head_office_total)

        # STEP 1: Dry-run first to validate reconciliation
        try:
            preview = PortfolioValuationService.preview_epoch_for_fund(
                fund_id=core_fund_id,
                start_date=start_date,
                end_date=end_date,
                performance_rate=performance_rate,
                session=db.session,
            )
            
            calculated_total = float(preview["total_local_valuation"])
            diff = round(abs(calculated_total - head_office_total), 2)
            
            # Validation: reconciliation tolerance is $0.01
            if diff > 0.01:
                return make_response(
                    jsonify({
                        "status": 400,
                        "message": f"Reconciliation failed: Local total ${calculated_total:.2f} does not match Head Office ${head_office_total:.2f} (difference: ${diff:.2f})"
                    }),
                    400
                )
        except ValueError as ve:
            return make_response(jsonify({"status": 400, "message": f"Dry-run failed: {str(ve)}"}), 400)

        # STEP 2: If reconciliation passes, commit the epoch ledger
        try:
            run = ValuationRun(
                core_fund_id=core_fund_id,
                epoch_start=start_date,
                epoch_end=end_date,
                performance_rate=performance_rate,
                head_office_total=head_office_total,
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

            # Update statuses for all batches touched by this core fund
            batch_ids = db.session.query(Investment.batch_id).filter(
                Investment.fund_id == core_fund_id
            ).distinct().all()
            batch_ids = [b[0] for b in batch_ids]
            updated = []
            for bid in batch_ids:
                batch = db.session.query(Batch).filter(Batch.id == bid).first()
                if not batch:
                    continue
                
                # If deployment date not set, use the epoch start_date
                if batch.date_deployed is None:
                    batch.date_deployed = start_date
                
                # Now check if epoch end_date is past expected close date
                if batch.expected_close_date and end_date >= batch.expected_close_date:
                    batch.date_closed = end_date
                    batch.is_active = False
                    updated.append({"batch_id": bid, "status": "Closed"})
                else:
                    batch.is_active = True
                    updated.append({"batch_id": bid, "status": "Active"})

            # Commit everything together
            db.session.commit()

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

    except ValueError as ve:
        db.session.rollback()
        return make_response(jsonify({"status": 400, "message": str(ve)}), 400)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)

@valuation_v1.route("/valuation/epoch/dry-run", methods=["GET"])
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

        # UI supplies % (e.g. "5" means 5%). Accept both "0.05" and "5".
        pr = float(performance_rate_raw)
        performance_rate = pr / 100.0 if pr > 1 else pr

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


@valuation_v1.route("/batches/<int:batch_id>/valuation-summary", methods=["GET"])
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

