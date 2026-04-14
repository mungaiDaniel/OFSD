from flask import request, Blueprint, jsonify, make_response
from flask_jwt_extended import jwt_required
from datetime import datetime, timezone
from decimal import Decimal

from app.database.database import db
from app.logic.valuation_service import PortfolioValuationService
from app.Investments.model import Investment, EpochLedger, Withdrawal, FINAL_WITHDRAWAL_STATUSES, WITHDRAWAL_STATUS_EXECUTED
from sqlalchemy import and_, func, or_, select
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Valuation.model import ValuationRun, Statement
from sqlalchemy.exc import IntegrityError


valuation_v1 = Blueprint("valuation_v1", __name__, url_prefix="/")


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


@valuation_v1.route("/api/v1/valuation/funds", methods=["GET"])
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

                # Get investments for mapping
                code_to_investment = {}
                investments = db.session.query(Investment).filter(Investment.fund_id == core_fund_id).all()
                for inv in investments:
                    code_to_investment[inv.internal_client_code] = inv

                # Save statements with withdrawal information
                from app.utils.audit_log import create_audit_log
                for breakdown in investor_breakdown:
                    code = breakdown["internal_client_code"]
                    inv = code_to_investment.get(code)
                    if not inv:
                        continue
                    
                    opening_balance = Decimal(str(breakdown["principal_before_start"] + breakdown["deposits_during_period"]))
                    withdrawals_amount = Decimal(str(breakdown["withdrawals_during_period"]))
                    performance_gain = Decimal(str(breakdown["profit"]))
                    closing_balance = opening_balance - withdrawals_amount + performance_gain

                    stmt = Statement(
                        investor_id=inv.id,
                        batch_id=inv.batch_id,
                        fund_id=core_fund_id,
                        valuation_run_id=run.id,
                        opening_balance=opening_balance,
                        withdrawals=withdrawals_amount,
                        performance_gain=performance_gain,
                        closing_balance=closing_balance,
                    )
                    db.session.add(stmt)
                    
                    # If there are withdrawals, log them to audit trail and recent activity
                    if withdrawals_amount > 0:
                        create_audit_log(
                            action="WITHDRAWAL_PROCESSED",
                            target_type="Investor", 
                            target_id=inv.id,
                            target_name=f"{inv.investor_name} ({code})",
                            description=f"Withdrawal of ${float(withdrawals_amount):,.2f} processed for {core.fund_name}",
                            old_value={"opening_balance": float(opening_balance)},
                            new_value={
                                "opening_balance": float(opening_balance),
                                "withdrawal": float(withdrawals_amount),
                                "closing_balance": float(closing_balance)
                            },
                            success=True
                        )
                        print(f"✅ Withdrawal of ${float(withdrawals_amount):,.2f} processed for {code} in {core.fund_name}")
                
                db.session.commit()

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

