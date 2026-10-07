"""
Fund and Share Class Management Routes

Handles fund creation and share class management for the NAV-based system.
"""

from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity
from types import SimpleNamespace
from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass
from app.Funds.investor_shares import InvestorShares
from app.Investments.model import (
    Withdrawal,
    Investment,
    PendingEmail,
    FINAL_WITHDRAWAL_STATUSES,
    WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
    WITHDRAWAL_STATUS_PENDING,
)
from sqlalchemy import func, distinct
from sqlalchemy.exc import IntegrityError
from app.utils.statement_theme import resolve_product_type

funds_v1 = Blueprint("funds_v1", __name__, url_prefix='/')

# ==================== ROLE-BASED ACCESS CONTROL ====================

def _require_super_admin():
    """
    Check that the current JWT identity is a super_admin user.
    Returns (user, None) on success, or (None, error_response) on failure.
    """
    from app.Admin.model import User

    try:
        identity = get_jwt_identity()
        user = db.session.query(User).filter(User.id == identity).first()
        if not user:
            return None, make_response(
                jsonify({"status": 403, "message": "User not found"}), 403
            )
        if user.role != "super_admin":
            return None, make_response(
                jsonify({"status": 403, "message": "Super admin access required"}), 403
            )
        return user, None
    except Exception as e:
        return None, make_response(
            jsonify({"status": 401, "message": f"Authentication error: {str(e)}"}), 401
        )

# ==================== FUND MANAGEMENT ====================

@funds_v1.route('/api/v1/funds', methods=['POST'])
@jwt_required()
def create_fund():
    """
    Create a new fund (SUPER ADMIN ONLY).
    Request: { "fund_name": "Axiom", "fund_code": "AXM" }
    Response: { "status": 201, "data": { "id": 1, "fund_name": "Axiom", "fund_code": "AXM", "is_active": true } }
    """
    user, error_response = _require_super_admin()
    if error_response:
        return error_response

    try:
        data = request.get_json()
        if not data or not data.get('fund_name'):
            return make_response(jsonify({"status": 400, "message": "fund_name is required"}), 400)

        fund_name = data['fund_name'].strip()
        fund_code = data.get('fund_code', fund_name[:3].upper()).strip()

        # Check if fund already exists
        existing = db.session.query(CoreFund).filter(
            db.func.lower(CoreFund.fund_name) == fund_name.lower()
        ).first()
        if existing:
            return make_response(jsonify({"status": 409, "message": "Fund already exists"}), 409)

        fund = CoreFund(fund_name=fund_name, fund_code=fund_code, is_active=True)
        db.session.add(fund)
        db.session.commit()

        return make_response(jsonify({
            "status": 201,
            "data": {
                "id": fund.id,
                "fund_name": fund.fund_name,
                "fund_code": fund.fund_code,
                "is_active": fund.is_active
            }
        }), 201)

    except IntegrityError:
        db.session.rollback()
        return make_response(jsonify({"status": 409, "message": "Fund code already exists"}), 409)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@funds_v1.route('/api/v1/funds/<int:fund_id>', methods=['PATCH'])
@jwt_required()
def update_fund(fund_id):
    """
    Update fund details (SUPER ADMIN ONLY).
    Request: { "fund_name": "Axiom Updated", "fund_code": "AXM2", "is_active": true }
    Response: { "status": 200, "data": { "id": 1, "fund_name": "...", "fund_code": "...", "is_active": true } }
    """
    user, error_response = _require_super_admin()
    if error_response:
        return error_response

    try:
        data = request.get_json() or {}
        if not data:
            return make_response(jsonify({"status": 400, "message": "Request body is required"}), 400)

        fund = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not fund:
            return make_response(jsonify({"status": 404, "message": "Fund not found"}), 404)

        changed = False

        if "fund_name" in data and data["fund_name"] is not None:
            fund_name = str(data["fund_name"]).strip()
            if not fund_name:
                return make_response(jsonify({"status": 400, "message": "fund_name cannot be empty"}), 400)

            # Check if new name conflicts with existing fund
            existing = db.session.query(CoreFund).filter(
                db.func.lower(CoreFund.fund_name) == fund_name.lower(),
                CoreFund.id != fund_id
            ).first()
            if existing:
                return make_response(jsonify({"status": 409, "message": "Fund name already exists"}), 409)

            fund.fund_name = fund_name
            changed = True

        if "fund_code" in data and data["fund_code"] is not None:
            fund_code = str(data["fund_code"]).strip().upper()
            if not fund_code:
                return make_response(jsonify({"status": 400, "message": "fund_code cannot be empty"}), 400)

            # Check if new code conflicts with existing fund
            existing = db.session.query(CoreFund).filter(
                CoreFund.fund_code == fund_code,
                CoreFund.id != fund_id
            ).first()
            if existing:
                return make_response(jsonify({"status": 409, "message": "Fund code already exists"}), 409)

            fund.fund_code = fund_code
            changed = True

        if "is_active" in data and data["is_active"] is not None:
            fund.is_active = bool(data["is_active"])
            changed = True

        if not changed:
            return make_response(jsonify({"status": 400, "message": "No updatable fields provided"}), 400)

        db.session.add(fund)
        db.session.commit()

        return make_response(jsonify({
            "status": 200,
            "message": "Fund updated successfully",
            "data": {
                "id": fund.id,
                "fund_name": fund.fund_name,
                "fund_code": fund.fund_code,
                "is_active": fund.is_active
            }
        }), 200)

    except IntegrityError:
        db.session.rollback()
        return make_response(jsonify({"status": 409, "message": "Fund code already exists"}), 409)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@funds_v1.route('/api/v1/funds/<int:fund_id>', methods=['DELETE'])
@jwt_required()
def delete_fund(fund_id):
    """
    Delete/deactivate a fund (SUPER ADMIN ONLY).
    Soft deletes by setting is_active=False.
    Response: { "status": 200, "message": "Fund deactivated" }
    """
    user, error_response = _require_super_admin()
    if error_response:
        return error_response

    try:
        fund = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not fund:
            return make_response(jsonify({"status": 404, "message": "Fund not found"}), 404)

        # Check if fund has any active batches
        active_batches = db.session.query(Batch).filter(
            Batch.share_class_id.in_(
                db.session.query(ShareClass.id).filter(ShareClass.core_fund_id == fund_id)
            ),
            Batch.is_active == True
        ).count()

        if active_batches > 0:
            return make_response(jsonify({
                "status": 409,
                "message": f"Cannot delete fund with {active_batches} active batch(es). Please deactivate all batches first."
            }), 409)

        # Soft delete: deactivate the fund
        fund.is_active = False
        db.session.add(fund)

        # Also deactivate all share classes in this fund
        share_classes = db.session.query(ShareClass).filter(
            ShareClass.core_fund_id == fund_id
        ).all()
        for share_class in share_classes:
            share_class.is_active = False
            db.session.add(share_class)

        db.session.commit()

        return make_response(jsonify({
            "status": 200,
            "message": f"Fund '{fund.fund_name}' and its {len(share_classes)} share class(es) deactivated successfully"
        }), 200)

    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@funds_v1.route('/api/v1/funds/<int:fund_id>/classes', methods=['POST'])
@jwt_required()
def add_share_class(fund_id):
    """
    Add a share class to a fund (SUPER ADMIN ONLY).
    Request: { "class_name": "Class I Participating Shares", "class_code": "KES_I", "currency": "KES" }
    Response: { "status": 201, "data": { "id": 1, "core_fund_id": 1, "class_name": "...", "class_code": "KES_I", "currency": "KES" } }
    """
    user, error_response = _require_super_admin()
    if error_response:
        return error_response

    try:
        data = request.get_json()
        if not data or not all(k in data for k in ['class_name', 'class_code', 'currency']):
            return make_response(jsonify({"status": 400, "message": "class_name, class_code, and currency are required"}), 400)

        # Validate fund exists
        fund = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not fund:
            return make_response(jsonify({"status": 404, "message": "Fund not found"}), 404)

        # Validate currency
        currency = data['currency'].upper()
        if currency not in ['KES', 'USD']:
            return make_response(jsonify({"status": 400, "message": "Currency must be KES or USD"}), 400)

        class_name = data['class_name'].strip()
        class_code = data['class_code'].strip()

        # Check for duplicate class_code in this fund
        existing = db.session.query(ShareClass).filter(
            ShareClass.core_fund_id == fund_id,
            ShareClass.class_code == class_code
        ).first()
        if existing:
            return make_response(jsonify({"status": 409, "message": "Class code already exists for this fund"}), 409)

        share_class = ShareClass(
            core_fund_id=fund_id,
            class_name=class_name,
            class_code=class_code,
            currency=currency,
            is_active=True
        )
        db.session.add(share_class)
        db.session.commit()

        return make_response(jsonify({
            "status": 201,
            "data": {
                "id": share_class.id,
                "core_fund_id": share_class.core_fund_id,
                "class_name": share_class.class_name,
                "class_code": share_class.class_code,
                "currency": share_class.currency
            }
        }), 201)

    except IntegrityError:
        db.session.rollback()
        return make_response(jsonify({"status": 409, "message": "Class code already exists"}), 409)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@funds_v1.route('/api/v1/funds/<int:fund_id>/classes', methods=['GET'])
@jwt_required()
def list_share_classes(fund_id):
    """
    List all share classes for a fund.
    Response: { "status": 200, "data": [{ "id": 1, "class_name": "...", "class_code": "KES_I", "currency": "KES" }, ...] }
    """
    try:
        # Validate fund exists
        fund = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not fund:
            return make_response(jsonify({"status": 404, "message": "Fund not found"}), 404)

        classes = db.session.query(ShareClass).filter(
            ShareClass.core_fund_id == fund_id,
            ShareClass.is_active == True
        ).order_by(ShareClass.class_name).all()

        data = [{
            "id": cls.id,
            "class_name": cls.class_name,
            "class_code": cls.class_code,
            "currency": cls.currency
        } for cls in classes]

        return make_response(jsonify({"status": 200, "data": data}), 200)

    except Exception as e:
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@funds_v1.route('/api/v1/funds/<int:fund_id>/classes/<int:class_id>', methods=['PATCH'])
@jwt_required()
def update_share_class(fund_id, class_id):
    """
    Update share class metadata (SUPER ADMIN ONLY).
    Body supports:
      - class_name
      - class_code
      - currency ("KES" | "USD")
    """
    user, error_response = _require_super_admin()
    if error_response:
        return error_response

    try:
        data = request.get_json() or {}
        if not data:
            return make_response(jsonify({"status": 400, "message": "Request body is required"}), 400)

        # Validate fund exists
        fund = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not fund:
            return make_response(jsonify({"status": 404, "message": "Fund not found"}), 404)

        share_class = db.session.query(ShareClass).filter(
            ShareClass.id == class_id,
            ShareClass.core_fund_id == fund_id,
            ShareClass.is_active == True
        ).first()
        if not share_class:
            return make_response(jsonify({"status": 404, "message": "Share class not found"}), 404)

        changed = False
        old_currency = (share_class.currency or "").upper().strip()

        if "class_name" in data and data["class_name"] is not None:
            class_name = str(data["class_name"]).strip()
            if not class_name:
                return make_response(jsonify({"status": 400, "message": "class_name cannot be empty"}), 400)
            share_class.class_name = class_name
            changed = True

        if "class_code" in data and data["class_code"] is not None:
            class_code = str(data["class_code"]).strip().upper()
            if not class_code:
                return make_response(jsonify({"status": 400, "message": "class_code cannot be empty"}), 400)

            existing_code = db.session.query(ShareClass).filter(
                ShareClass.class_code == class_code,
                ShareClass.id != share_class.id
            ).first()
            if existing_code:
                return make_response(jsonify({"status": 409, "message": "Class code already exists"}), 409)

            share_class.class_code = class_code
            changed = True

            # Keep linked investments aligned with class code representation.
            db.session.query(Investment).filter(
                Investment.share_class_id == share_class.id
            ).update(
                {Investment.share_series: class_code},
                synchronize_session=False
            )

        if "currency" in data and data["currency"] is not None:
            currency = str(data["currency"]).upper().strip()
            if currency not in ["KES", "USD"]:
                return make_response(jsonify({"status": 400, "message": "Currency must be KES or USD"}), 400)
            share_class.currency = currency
            changed = True

            # Keep linked investment + pending-email currency aligned with class currency.
            if currency != old_currency:
                inv_ids = [row[0] for row in db.session.query(Investment.id).filter(
                    Investment.share_class_id == share_class.id
                ).all()]
                db.session.query(Investment).filter(
                    Investment.share_class_id == share_class.id
                ).update(
                    {Investment.currency_type: currency},
                    synchronize_session=False
                )
                if inv_ids:
                    db.session.query(PendingEmail).filter(
                        PendingEmail.investor_id.in_(inv_ids),
                        PendingEmail.status.in_(("Pending_Confirmation", "Suppressed"))
                    ).update(
                        {PendingEmail.currency_type: currency},
                        synchronize_session=False
                    )

        if not changed:
            return make_response(jsonify({"status": 400, "message": "No updatable fields provided"}), 400)

        db.session.add(share_class)
        db.session.commit()

        return make_response(jsonify({
            "status": 200,
            "message": "Share class updated",
            "data": {
                "id": share_class.id,
                "core_fund_id": share_class.core_fund_id,
                "class_name": share_class.class_name,
                "class_code": share_class.class_code,
                "currency": share_class.currency,
            }
        }), 200)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@funds_v1.route('/api/v1/funds/<int:fund_id>/classes/<int:class_id>/force-update-code', methods=['PATCH'])
@jwt_required()
def force_update_share_class_code(fund_id, class_id):
    """
    FORCE UPDATE: Update share class code ONLY for deployed batches (SUPER ADMIN ONLY).
    This is a workaround to fix deployed share class codes (e.g., kes_r → kes_I)
    without affecting pending/non-deployed investments.

    Use case: A share class was created with wrong code and deployed;
    need to fix the code retroactively for that deployed share class only.

    Request body: {
      "new_class_code": "KES_I"
    }

    Response: {
      "status": 200,
      "message": "Share class code updated for deployed batches",
      "data": {
        "updated_batches": 2,
        "updated_investments": 5,
        "old_code": "kes_r",
        "new_code": "KES_I"
      }
    }
    """
    user, error_response = _require_super_admin()
    if error_response:
        return error_response

    try:
        data = request.get_json() or {}
        if "new_class_code" not in data or not data["new_class_code"]:
            return make_response(jsonify({"status": 400, "message": "new_class_code is required"}), 400)

        new_code = str(data["new_class_code"]).strip().upper()
        
        # Validate fund exists
        fund = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not fund:
            return make_response(jsonify({"status": 404, "message": "Fund not found"}), 404)

        share_class = db.session.query(ShareClass).filter(
            ShareClass.id == class_id,
            ShareClass.core_fund_id == fund_id,
            ShareClass.is_active == True
        ).first()
        if not share_class:
            return make_response(jsonify({"status": 404, "message": "Share class not found"}), 404)

        old_code = share_class.class_code
        
        # Update ONLY deployed batches for this share class
        deployed_batches = db.session.query(Batch).filter(
            Batch.share_class_id == class_id,
            Batch.deployment_confirmed == True,
        ).all()

        if not deployed_batches:
            return make_response(jsonify({
                "status": 409,
                "message": "No deployed batches found for this share class.",
            }), 409)

        updated_batch_ids = [b.id for b in deployed_batches]
        
        # Update investments in those deployed batches
        updated_inv_count = db.session.query(Investment).filter(
            Investment.batch_id.in_(updated_batch_ids)
        ).update(
            {Investment.share_series: new_code},
            synchronize_session=False
        )
        
        # Update share class code
        share_class.class_code = new_code
        db.session.add(share_class)
        db.session.commit()

        return make_response(jsonify({
            "status": 200,
            "message": "Share class code updated for deployed batches only",
            "data": {
                "updated_batches": len(deployed_batches),
                "updated_investments": updated_inv_count,
                "old_code": old_code,
                "new_code": new_code,
            }
        }), 200)
    except Exception as e:
        db.session.rollback()
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


@funds_v1.route('/api/v1/funds/<int:fund_id>/classes/<int:class_id>/details', methods=['GET'])
@jwt_required()
def get_share_class_details(fund_id, class_id):
    """
    Return full investor share breakdown and linked batches for a share class.
    Response includes investors list (shares, deploy NAV, cost basis, current value)
    and a batches list showing which batches belong to this class.
    """
    try:
        fund = db.session.query(CoreFund).filter(CoreFund.id == fund_id).first()
        if not fund:
            return make_response(jsonify({"status": 404, "message": "Fund not found"}), 404)

        share_class = db.session.query(ShareClass).filter(
            ShareClass.id == class_id,
            ShareClass.core_fund_id == fund_id,
        ).first()
        if not share_class:
            return make_response(jsonify({"status": 404, "message": "Share class not found"}), 404)

        current_nav = float(share_class.current_nav) if share_class.current_nav else None

        # All active investor_shares rows for this class
        rows = (
            db.session.query(InvestorShares, Investment, Batch)
            .join(Investment, InvestorShares.investment_id == Investment.id)
            .join(Batch, InvestorShares.batch_id == Batch.id)
            .filter(
                InvestorShares.share_class_id == class_id,
                InvestorShares.is_active == True,
            )
            .order_by(Investment.investor_name)
            .all()
        )

        investors_data = []
        for inv_shares, investment, batch in rows:
            shares = float(inv_shares.shares_owned)
            deploy_nav = float(inv_shares.deployment_nav)
            cost_basis = round(shares * deploy_nav, 2)
            current_value = round(shares * current_nav, 2) if current_nav else None
            gain_loss = round(current_value - cost_basis, 2) if current_value is not None else None
            investors_data.append({
                "investment_id": investment.id,
                "investor_name": investment.investor_name,
                "internal_client_code": investment.internal_client_code,
                "shares_owned": round(shares, 6),
                "deployment_nav": round(deploy_nav, 6),
                "deployment_date": inv_shares.deployment_date.isoformat() if inv_shares.deployment_date else None,
                "batch_id": batch.id,
                "batch_name": batch.batch_name,
                "cost_basis": cost_basis,
                "current_value": current_value,
                "gain_loss": gain_loss,
            })

        # Total shares: prefer InvestorShares when available, fall back to Batch.total_shares
        total_shares = sum(float(r.shares_owned) for r, _, _ in rows)
        if total_shares == 0:
            fallback = db.session.query(
                func.sum(Batch.total_shares)
            ).filter(
                Batch.share_class_id == class_id,
                Batch.total_shares.isnot(None)
            ).scalar()
            total_shares = float(fallback) if fallback else 0.0

        # Batches linked to this share class
        batches = (
            db.session.query(Batch)
            .filter(Batch.share_class_id == class_id)
            .order_by(Batch.date_deployed.desc().nullslast())
            .all()
        )

        batches_data = []
        for b in batches:
            # Per-batch shares: prefer InvestorShares, fall back to Batch.total_shares
            b_shares = db.session.query(
                func.sum(InvestorShares.shares_owned)
            ).filter(
                InvestorShares.share_class_id == class_id,
                InvestorShares.batch_id == b.id,
                InvestorShares.is_active == True,
            ).scalar()
            if not b_shares:
                b_shares = b.total_shares

            # Investor count: prefer InvestorShares join, fall back to direct Investment count
            b_inv_count = (
                db.session.query(func.count(distinct(Investment.internal_client_code)))
                .join(InvestorShares, InvestorShares.investment_id == Investment.id)
                .filter(
                    InvestorShares.share_class_id == class_id,
                    InvestorShares.batch_id == b.id,
                    InvestorShares.is_active == True,
                )
                .scalar()
            ) or 0
            if b_inv_count == 0:
                b_inv_count = (
                    db.session.query(func.count(distinct(Investment.internal_client_code)))
                    .filter(Investment.batch_id == b.id)
                    .scalar()
                ) or 0

            batches_data.append({
                "batch_id": b.id,
                "batch_name": b.batch_name,
                "total_shares": round(float(b_shares), 4) if b_shares else 0.0,
                "investor_count": b_inv_count,
                "date_deployed": b.date_deployed.isoformat() if b.date_deployed else None,
                "is_active": b.is_active,
            })

        return make_response(jsonify({
            "status": 200,
            "data": {
                "id": share_class.id,
                "class_name": share_class.class_name,
                "class_code": share_class.class_code,
                "currency": share_class.currency,
                "current_nav": current_nav,
                "total_shares": round(total_shares, 4),
                "investors": investors_data,
                "batches": batches_data,
            }
        }), 200)

    except Exception as e:
        import traceback
        print(f"ERROR get_share_class_details: {traceback.format_exc()}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)


# ============================================================================
# #1: Fund Summary Endpoint - For Dashboard & Landing Page
# ============================================================================

def compute_funds_summary_data(session=None):
    """
    Compute fund performance summary across all classes.
    Used by both GET /api/v1/funds/summary and GET /api/v1/stats/overview.
    """
    if session is None:
        session = db.session

    from app.Funds.nav_history import NavHistory
    from app.Valuation.valuation_snapshot import ValuationSnapshot
    from app.Funds.investor_shares import InvestorShares
    from sqlalchemy import inspect
    from decimal import Decimal
    from datetime import datetime, timezone
    
    def float_2dp(val):
        if val is None:
            return None
        return float(Decimal(str(val)).quantize(Decimal("0.01")))

    inspector = inspect(db.engine)
    has_valuation_snapshots = inspector.has_table("valuation_snapshots")
    
    # Get all active funds
    funds = session.query(CoreFund).filter(CoreFund.is_active == True).all()
    
    if not funds:
        return {"as_of_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "funds": []}
    
    funds_data = []
    all_valuations = []
    
    for fund in funds:
        # Get all active share classes for this fund that have at least one linked batch
        classes = session.query(ShareClass).join(
            Batch, Batch.share_class_id == ShareClass.id
        ).filter(
            ShareClass.core_fund_id == fund.id,
            ShareClass.is_active == True,
        ).distinct().all()
        
        classes_data = []
        fund_totals_by_currency = {}
        fund_invested_by_currency = {}
        fund_gain_by_currency = {}
        # Gross/Net holdings split (Overview page fund filter feature): gross
        # deposited is the raw, never-adjusted "total ever deposited" figure
        # (distinct from fund_invested_by_currency above, which is cost_basis —
        # shares × deployment NAV). Net Holdings = net principal (gross minus
        # transfer cost, entry fee, AND any oversubscription refund — see
        # fund_net_principal_after_refund_by_currency below) minus regular
        # withdrawals. This is
        # deliberately a DIFFERENT number from fund_totals_by_currency/AUM
        # (current market value) — Net Holdings is "what's still actually
        # committed", AUM is "what it's worth today"; the two only coincide
        # when nothing has moved in price since deployment.
        #
        # Note: fund_net_principal_after_refund_by_currency (and its per-class
        # "net_principal_after_refund" sibling above) is NOT the same figure as
        # the Batch Detail page's "Net Principal" stat card (total_net_principal
        # in app/Batch/controllers.py) — that one deliberately excludes the
        # oversubscription refund (it's a pre-allocation-decision figure sitting
        # between Total Deposited and Total NAV in the pipeline). This one
        # includes it, because Net Holdings needs to reconcile with AUM once
        # deployed. Same underlying fee subtraction, different scope — hence
        # the more explicit name here to avoid confusing the two.
        fund_gross_deposited_by_currency = {}
        fund_net_principal_after_refund_by_currency = {}
        fund_withdrawals_by_currency = {}
        fund_refunds_by_currency = {}
        fund_performances = []
        fund_navs = []

        # Distinct investor count for this fund — same shape as the Investor
        # Directory's authoritative count, just scoped to one fund.
        investors_count = (
            session.query(func.count(func.distinct(Investment.internal_client_code)))
            .filter(Investment.fund_id == fund.id)
            .scalar()
            or 0
        )

        for cls in classes:
            # Current price: resolve_current_price is the single source of
            # truth (see its docstring) — the latest valuation dated on/after
            # this class's most recent deployment, or that deployment's own
            # NAV if nothing's been valued since. A naive "newest NavHistory
            # row for this share class" could return a price from a stale/
            # unrelated valuation dated before deployment.
            latest_deployed_batch = (
                session.query(Batch)
                .filter(Batch.share_class_id == cls.id, Batch.date_deployed.isnot(None))
                .order_by(Batch.date_deployed.desc())
                .first()
            )
            class_deployment_date = latest_deployed_batch.date_deployed.date() if latest_deployed_batch and latest_deployed_batch.date_deployed else None
            class_deployment_nav = latest_deployed_batch.deployment_nav if latest_deployed_batch else None
            resolved_nav, resolved_nav_date, _is_fallback = NavHistory.resolve_current_price(
                cls.id, class_deployment_date, class_deployment_nav, session=session
            )
            latest_nav = SimpleNamespace(nav_per_share=resolved_nav, nav_date=resolved_nav_date) if resolved_nav is not None else None
            nav_history_rows = session.query(NavHistory).filter(
                NavHistory.share_class_id == cls.id
            ).order_by(NavHistory.nav_date.asc()).all()
            
            # Total shares: sum Batch.total_shares (always populated on deployment),
            # fall back to InvestorShares when Batch.total_shares is unavailable.
            total_shares_result = session.query(
                func.sum(Batch.total_shares).label("total")
            ).filter(
                Batch.share_class_id == cls.id,
                Batch.total_shares.isnot(None)
            ).first()
            total_shares = float_2dp(total_shares_result[0]) if total_shares_result and total_shares_result[0] else 0

            if not total_shares:
                fallback = session.query(
                    func.sum(InvestorShares.shares_owned).label("total")
                ).filter(
                    InvestorShares.share_class_id == cls.id,
                    InvestorShares.is_active == True
                ).first()
                total_shares = float_2dp(fallback[0]) if fallback and fallback[0] else 0

            # Cost basis (net invested at deployment) = Σ(shares_owned × deployment_nav) for deployed batches
            cost_basis_result = session.query(
                func.sum(InvestorShares.shares_owned * InvestorShares.deployment_nav).label("total")
            ).join(Batch, InvestorShares.batch_id == Batch.id).filter(
                InvestorShares.share_class_id == cls.id,
                Batch.date_deployed.isnot(None)
            ).first()
            cost_basis = float_2dp(cost_basis_result[0]) if cost_basis_result and cost_basis_result[0] else 0.0

            # Investor codes active in this class (deployed batches only). Used by
            # both the withdrawal and refund sums below to map withdrawals to a
            # share class. Kept as a Query (not .subquery()) so .in_() receives a
            # SELECT directly.
            active_codes_subq = (
                session.query(Investment.internal_client_code)
                .join(InvestorShares, InvestorShares.investment_id == Investment.id)
                .join(Batch, InvestorShares.batch_id == Batch.id)
                .filter(
                    InvestorShares.share_class_id == cls.id,
                    Batch.date_deployed.isnot(None),
                )
                .distinct()
            )

            # Withdrawals: subtract approved/final withdrawals from displayed AUM.
            withdrawal_sum = 0.0
            try:
                wd_sum_raw = (
                    session.query(func.coalesce(func.sum(Withdrawal.gross_amount), 0))
                    .filter(
                        Withdrawal.fund_id == fund.id,
                        Withdrawal.status.in_(FINAL_WITHDRAWAL_STATUSES),
                        Withdrawal.source != WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
                        Withdrawal.internal_client_code.in_(active_codes_subq),
                    )
                    .scalar()
                )
                withdrawal_sum = float_2dp(wd_sum_raw) if wd_sum_raw is not None else 0.0
            except Exception:
                withdrawal_sum = 0.0

            # Gross deposited: raw, never-adjusted "total ever deposited" for
            # this class — unlike cost_basis above, this doesn't exclude fees
            # or restrict to deployed batches. Investment.share_class_id is
            # set directly on each deposit row, so no join is needed.
            gross_deposited_result = session.query(
                func.coalesce(func.sum(Investment.amount_deposited), 0)
            ).filter(Investment.share_class_id == cls.id).scalar()
            gross_deposited = float_2dp(gross_deposited_result) if gross_deposited_result else 0.0

            # Net principal: gross deposited minus transfer cost, entry fee, AND
            # any oversubscription refund — the same formula as the
            # Investment.net_principal property, inlined in SQL (that property
            # can't be used directly inside a SQL expression). This is the
            # "committed" figure Net Holdings is built from below: what's left
            # after every deduction except a withdrawal actually being paid out.
            net_principal_after_refund_result = session.query(
                func.coalesce(
                    func.sum(
                        Investment.amount_deposited
                        - func.coalesce(Investment.transfer_fee_deducted, 0)
                        - func.coalesce(Investment.deployment_fee_deducted, 0)
                        - func.coalesce(Investment.oversubscription_refund_amount, 0)
                    ),
                    0,
                )
            ).filter(Investment.share_class_id == cls.id).scalar()
            net_principal_after_refund_sum = float_2dp(net_principal_after_refund_result) if net_principal_after_refund_result else 0.0

            # Refunds (DPRP-style oversubscription pro-rata) displayed on the
            # Overview dashboard as "Pending Refunds" — so this must count only
            # STILL-Pending ones. Once a refund's Withdrawal row is Approved
            # (paid out), it's no longer "pending" and should drop off this
            # figure; it was already excluded from Net Holdings from the moment
            # of deployment (net_principal_after_refund subtracts
            # oversubscription_refund_amount unconditionally, regardless of the
            # Withdrawal row's status), so removing it here doesn't change net
            # worth — it just stops double-reporting a liability that's already
            # been settled.
            refund_sum = 0.0
            try:
                refund_sum_raw = (
                    session.query(func.coalesce(func.sum(Withdrawal.gross_amount), 0))
                    .filter(
                        Withdrawal.fund_id == fund.id,
                        Withdrawal.source == WITHDRAWAL_SOURCE_OVERSUBSCRIPTION_REFUND,
                        Withdrawal.status == WITHDRAWAL_STATUS_PENDING,
                        Withdrawal.internal_client_code.in_(active_codes_subq),
                    )
                    .scalar()
                )
                refund_sum = float_2dp(refund_sum_raw) if refund_sum_raw is not None else 0.0
            except Exception:
                refund_sum = 0.0

            if latest_nav:
                current_nav = float_2dp(latest_nav.nav_per_share)
                total_nav = float_2dp(Decimal(str(total_shares)) * latest_nav.nav_per_share)
                valuation_date = latest_nav.nav_date.strftime("%Y-%m-%d")
                unrealized_gain = float_2dp(Decimal(str(total_nav or 0)) - Decimal(str(cost_basis or 0)))

                # Apply withdrawals deduction to displayed AUM/gain
                if withdrawal_sum and total_nav is not None:
                    total_nav = float_2dp(max(Decimal("0.00"), Decimal(str(total_nav)) - Decimal(str(withdrawal_sum))))
                    if unrealized_gain is not None:
                        unrealized_gain = float_2dp(Decimal(str(total_nav or 0)) - Decimal(str(cost_basis or 0)))
                
                if has_valuation_snapshots:
                    # Get latest valuation snapshot for this share class via InvestorShares
                    latest_snapshot_row = session.query(
                        ValuationSnapshot,
                        InvestorShares.deployment_nav.label("deployment_nav")
                    ).join(
                        InvestorShares,
                        ValuationSnapshot.investor_shares_id == InvestorShares.id
                    ).filter(
                        InvestorShares.share_class_id == cls.id
                    ).order_by(ValuationSnapshot.valuation_date.desc()).first()

                    if latest_snapshot_row:
                        latest_snapshot, latest_deployment_nav = latest_snapshot_row
                        performance_pct = float_2dp(latest_snapshot.performance_pct)
                        prev_nav = float_2dp(latest_deployment_nav)
                    else:
                        performance_pct = None
                        prev_nav = None
                else:
                    # Fallback: derive performance from NAV history if available
                    if nav_history_rows and len(nav_history_rows) > 1:
                        prev_nav = float_2dp(nav_history_rows[-2].nav_per_share)
                        if prev_nav and prev_nav > 0 and current_nav is not None:
                            performance_pct = float_2dp(((Decimal(str(current_nav)) - Decimal(str(prev_nav))) / Decimal(str(prev_nav))) * Decimal("100"))
                        else:
                            performance_pct = None
                    else:
                        prev_nav = None
                        performance_pct = None
                
                all_valuations.append(total_nav or 0)
                if performance_pct is not None:
                    fund_performances.append((total_nav or 0, performance_pct))
                if total_nav:
                    fund_navs.append(total_nav)
            else:
                current_nav = None
                total_nav = None
                performance_pct = None
                prev_nav = None
                valuation_date = None
                unrealized_gain = None
            
            classes_data.append({
                "id": cls.id,
                "class_name": cls.class_name,
                "class_code": cls.class_code,
                "currency": cls.currency,
                "is_active": cls.is_active,
                "total_shares": float_2dp(total_shares),
                "prev_nav": prev_nav,
                "current_nav": current_nav,
                "total_nav": total_nav,
                "total_invested": cost_basis,
                "gross_deposited": gross_deposited,
                "net_principal_after_refund": net_principal_after_refund_sum,
                "refunds": refund_sum,
                "unrealized_gain": unrealized_gain,
                "withdrawals": withdrawal_sum,
                "performance_pct": performance_pct,
                "valuation_date": valuation_date,
                "nav_history": [
                    {
                        "date": row.nav_date.strftime("%Y-%m-%d"),
                        "nav": float(row.nav_per_share),
                    }
                    for row in nav_history_rows
                ],
            })

            # Aggregate by currency
            if cls.currency not in fund_totals_by_currency:
                fund_totals_by_currency[cls.currency] = 0
            if cls.currency not in fund_invested_by_currency:
                fund_invested_by_currency[cls.currency] = 0
            if cls.currency not in fund_gain_by_currency:
                fund_gain_by_currency[cls.currency] = 0
            if cls.currency not in fund_gross_deposited_by_currency:
                fund_gross_deposited_by_currency[cls.currency] = 0
            if cls.currency not in fund_net_principal_after_refund_by_currency:
                fund_net_principal_after_refund_by_currency[cls.currency] = 0
            if cls.currency not in fund_withdrawals_by_currency:
                fund_withdrawals_by_currency[cls.currency] = 0
            if cls.currency not in fund_refunds_by_currency:
                fund_refunds_by_currency[cls.currency] = 0
            if total_nav:
                fund_totals_by_currency[cls.currency] += total_nav
            if cost_basis:
                fund_invested_by_currency[cls.currency] += float(cost_basis or 0)
            if unrealized_gain is not None:
                fund_gain_by_currency[cls.currency] += float(unrealized_gain or 0)
            fund_gross_deposited_by_currency[cls.currency] += float(gross_deposited or 0)
            fund_net_principal_after_refund_by_currency[cls.currency] += float(net_principal_after_refund_sum or 0)
            fund_withdrawals_by_currency[cls.currency] += float(withdrawal_sum or 0)
            fund_refunds_by_currency[cls.currency] += float(refund_sum or 0)

        # Net Holdings = net principal after refund (gross deposited minus
        # transfer cost, entry fee, and any oversubscription refund — see
        # fund_net_principal_after_refund_by_currency above) minus regular
        # withdrawals. Refund is NOT subtracted again here — it's already
        # netted out above — subtracting it twice would understate holdings
        # for anyone who's gone through oversubscription pro-rata. This chain
        # is reusable/not DPRP-specific: the after-refund figure reduces to
        # plain gross deposited minus fees for any fund that's never had a
        # refund event.
        fund_net_holdings_by_currency = {
            currency: float_2dp(
                Decimal(str(fund_net_principal_after_refund_by_currency.get(currency, 0)))
                - Decimal(str(fund_withdrawals_by_currency.get(currency, 0)))
            )
            for currency in fund_net_principal_after_refund_by_currency
        }
        # Gain/Loss on this page is current value (total_nav) vs. Net Holdings,
        # not the cost_basis-based fund_gain_by_currency computed per-class
        # above (that field is left untouched for anything else that reads it —
        # e.g. the per-class "unrealized_gain" values keep their existing
        # meaning). This overwrites the fund-level aggregate specifically.
        fund_gain_by_currency = {
            currency: float_2dp(
                Decimal(str(fund_totals_by_currency.get(currency, 0)))
                - Decimal(str(fund_net_holdings_by_currency.get(currency, 0)))
            )
            for currency in set(fund_totals_by_currency) | set(fund_net_holdings_by_currency)
        }
        
        # Calculate weighted performance for this fund
        weighted_perf = None
        if fund_performances:
            total_weighted = sum(nav * perf for nav, perf in fund_performances)
            total_nav_sum = sum(nav for nav, _ in fund_performances)
            if total_nav_sum > 0:
                weighted_perf = float_2dp(Decimal(str(total_weighted)) / Decimal(str(total_nav_sum)))
        
        funds_data.append({
            "id": fund.id,
            "fund_name": fund.fund_name,
            "fund_code": fund.fund_code,
            "product_type": resolve_product_type([fund.fund_name], [fund.fund_code]),
            "is_active": fund.is_active,
            "investors_count": int(investors_count),
            "classes": classes_data,
            "totals_by_currency": fund_totals_by_currency,
            "invested_by_currency": fund_invested_by_currency,
            "gain_by_currency": fund_gain_by_currency,
            "gross_deposited_by_currency": fund_gross_deposited_by_currency,
            "net_principal_after_refund_by_currency": fund_net_principal_after_refund_by_currency,
            "withdrawals_by_currency": fund_withdrawals_by_currency,
            "refunds_by_currency": fund_refunds_by_currency,
            "net_holdings_by_currency": fund_net_holdings_by_currency,
            "weighted_performance_pct": weighted_perf
        })
    
    # Determine as_of_date (most recent valuation date across all funds)
    as_of_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if has_valuation_snapshots:
        latest_valuations = session.query(ValuationSnapshot).order_by(
            ValuationSnapshot.valuation_date.desc()
        ).limit(1).all()
        if latest_valuations:
            as_of_date = latest_valuations[0].valuation_date.strftime("%Y-%m-%d")
    
    return {
        "as_of_date": as_of_date,
        "funds": funds_data
    }


@funds_v1.route('/api/v1/funds/summary', methods=['GET'])
def get_funds_summary():
    """
    #1: Get fund performance summary across all classes.
    
    Returns per-class NAV, total NAV, and performance data.
    """
    try:
        data = compute_funds_summary_data(db.session)
        return make_response(jsonify({
            "status": 200,
            "data": data
        }), 200)
    except Exception as e:
        import traceback
        print(f"ERROR in get_funds_summary: {traceback.format_exc()}")
        return make_response(jsonify({"status": 500, "message": f"Error: {str(e)}"}), 500)