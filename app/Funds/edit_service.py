"""
Edit fund / share and share class (Task 12)
===========================================

Shared, product-scoped edit logic behind:

  PATCH /api/v1/funds/<id>                      PATCH /api/v1/shares/<id>
  PATCH /api/v1/funds/<id>/classes/<class_id>   PATCH /api/v1/shares/<id>/classes/<class_id>
  GET   /api/v1/funds/<id>/edit-context         GET   /api/v1/shares/<id>/edit-context

Rules enforced here (server side, regardless of what the UI shows):

* Role: the same role that can create funds/shares/share classes today
  (super_admin — see app/Funds/routes.py::_create_fund_impl).
* Product (FUNDS/SHARES) is immutable. A body that tries to change it is
  rejected; a fund/class reached through the other product's URL 404s.
* Validation mirrors creation (name/code required and trimmed, currency from
  the per-product allow-list) plus: name unique (case-insensitive, the DB
  constraint is global), fund code unique within the product, class code
  unique (DB constraint).
* Currency of a share class may only change while it has no deposits,
  batches, holdings, NAV history or valuation reports. Otherwise 409
  CURRENCY_LOCKED, unless a super_admin sends
  ``confirm_currency_override: true`` — figures are NOT converted, and the
  override gets its own audit entry.
* Deactivating a fund/class that still has open batches is rejected (409
  DEACTIVATION_BLOCKED) with the blocking batches listed.
* Renaming a fund cascades the denormalized ``fund_name`` copies (investments,
  withdrawals, pending emails, performance, pro-rata rows, legacy per-batch
  funds) so grouping keeps working. It is blocked when the fund already has
  epoch-ledger rows, because those are hash-chained over the fund name.
* Optimistic concurrency: callers send the ``version`` they loaded (from the
  edit-context endpoint); if the row changed since, 409 VERSION_CONFLICT.
* Every successful edit writes one insert-only AuditLog row (who, when, IP,
  old/new value per changed field) in the SAME transaction as the edit.
"""

import hashlib
import json
from datetime import datetime, timezone

from flask import request, jsonify, make_response, has_request_context
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import func, or_, select

from app.database.database import db
from app.database.product_type import FUNDS, SHARES
from app.Batch.core_fund import CoreFund
from app.Batch.model import Batch
from app.Funds.share_class import ShareClass

# Per-product currency allow-list — identical to the one creation uses
# (app/Funds/routes.py::CURRENCIES_BY_PRODUCT). Kept here as the single
# definition; routes.py imports it from this module.
# Shares (DPRP): deposits are taken in the class currency (USD by default —
# first entry is the create-form default); deployment converts them to NGN.
CURRENCIES_BY_PRODUCT = {FUNDS: ("KES", "USD"), SHARES: ("USD", "NGN", "KES")}

# Roles allowed to edit — same as create today.
EDIT_ROLES = ("super_admin",)
# Only this role may override a locked currency.
CURRENCY_OVERRIDE_ROLES = ("super_admin",)

FUND_NAME_MAX = 100
FUND_CODE_MAX = 50
DESCRIPTION_MAX = 1000
CLASS_NAME_MAX = 100
CLASS_CODE_MAX = 20


# ─────────────────────────── helpers ───────────────────────────

def _resp(status, message, **extra):
    body = {"status": status, "message": message}
    body.update(extra)
    return make_response(jsonify(body), status)


def resolve_current_user():
    """
    Resolve the JWT identity to a User. Login tokens use the user's email as
    identity (app/Admin/model.py::generate_auth_token) while some tests use
    the numeric id — accept both.
    """
    from app.Admin.model import User

    identity = get_jwt_identity()
    if isinstance(identity, dict):
        identity = identity.get("email") or identity.get("id")
    if identity is None:
        return None
    if isinstance(identity, int) or (isinstance(identity, str) and identity.strip().isdigit()):
        return db.session.query(User).filter(User.id == int(identity)).first()
    if isinstance(identity, str) and identity.strip():
        return db.session.query(User).filter(func.lower(User.email) == identity.strip().lower()).first()
    return None


def require_role(roles=EDIT_ROLES):
    """Returns (user, None) or (None, error_response)."""
    try:
        user = resolve_current_user()
    except Exception as e:  # pragma: no cover - defensive
        db.session.rollback()
        return None, _resp(401, f"Authentication error: {e}")
    if not user:
        return None, _resp(403, "User not found")
    if user.role not in roles:
        return None, _resp(403, "You do not have permission to edit this. Super admin access required.")
    return user, None


def _version(payload):
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def fund_version(fund):
    return _version({
        "id": fund.id,
        "fund_name": fund.fund_name,
        "fund_code": fund.fund_code,
        "description": fund.description,
        "is_active": bool(fund.is_active),
        "product_type": fund.product_type,
        "updated_at": fund.updated_at.isoformat() if fund.updated_at else None,
    })


def share_class_version(sc):
    return _version({
        "id": sc.id,
        "core_fund_id": sc.core_fund_id,
        "class_name": sc.class_name,
        "class_code": sc.class_code,
        "currency": sc.currency,
        "is_active": bool(sc.is_active),
        "product_type": sc.product_type,
    })


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("active", "true", "1", "yes"):
            return True
        if v in ("inactive", "false", "0", "no"):
            return False
    raise ValueError("must be Active or Inactive")


def _fund_scope(fund):
    from app.Investments.model import Investment

    return or_(
        Investment.fund_id == fund.id,
        (Investment.fund_id == None) & (func.lower(Investment.fund_name) == (fund.fund_name or "").lower()),  # noqa: E711
    )


def _batch_label(b):
    return b.batch_name or f"Batch #{b.id}"


def fund_open_batches(fund):
    """Open (still accepting deposits) batches linked to the fund, via its
    share classes or via deposits that belong to it."""
    from app.Investments.model import Investment

    class_ids = [cid for (cid,) in db.session.query(ShareClass.id).filter(ShareClass.core_fund_id == fund.id).all()]
    batch_ids_from_inv = select(Investment.batch_id).where(
        _fund_scope(fund), Investment.batch_id.isnot(None)
    ).distinct()
    conds = [Batch.id.in_(batch_ids_from_inv)]
    if class_ids:
        conds.append(Batch.share_class_id.in_(class_ids))
    return db.session.query(Batch).filter(Batch.is_open == True, or_(*conds)).order_by(Batch.id).all()  # noqa: E712


def class_open_batches(sc):
    return db.session.query(Batch).filter(
        Batch.share_class_id == sc.id, Batch.is_open == True  # noqa: E712
    ).order_by(Batch.id).all()


def share_class_currency_blockers(sc):
    """Human-readable reasons the class's currency is locked (empty = free)."""
    from app.Investments.model import Investment
    from app.Funds.investor_shares import InvestorShares
    from app.Funds.nav_history import NavHistory
    from app.Reports.model import ReportRun

    checks = [
        (db.session.query(func.count(Investment.id)).filter(Investment.share_class_id == sc.id).scalar() or 0, "deposit"),
        (db.session.query(func.count(Batch.id)).filter(Batch.share_class_id == sc.id).scalar() or 0, "linked batch"),
        (db.session.query(func.count(InvestorShares.id)).filter(InvestorShares.share_class_id == sc.id).scalar() or 0, "investor holding"),
        (db.session.query(func.count(NavHistory.id)).filter(NavHistory.share_class_id == sc.id).scalar() or 0, "NAV history entry"),
        (db.session.query(func.count(ReportRun.id)).filter(ReportRun.share_class_id == sc.id).scalar() or 0, "valuation report run"),
    ]
    if sc.current_nav is not None:
        checks.append((1, "current NAV value"))
    return [f"{n} {label}{'' if n == 1 or label.endswith('value') else 's'}" for n, label in checks if n]


def fund_has_ledger_rows(fund):
    from app.Investments.model import EpochLedger

    return (db.session.query(func.count(EpochLedger.id)).filter(
        func.lower(EpochLedger.fund_name) == (fund.fund_name or "").lower()
    ).scalar() or 0) > 0


def _audit(action, target_type, target_id, target_name, description, old_value, new_value, user):
    """Insert-only audit row added to the CURRENT transaction (committed with
    the edit itself, so an edit can never succeed without its audit trail)."""
    from app.utils.audit_log import AuditLog, get_client_ip

    log = AuditLog(
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        user_name=user.name if user else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        description=description,
        old_value=json.dumps(old_value, default=str) if old_value is not None else None,
        new_value=json.dumps(new_value, default=str) if new_value is not None else None,
        ip_address=get_client_ip(),
        user_agent=request.headers.get("User-Agent", "UNKNOWN") if has_request_context() else "SYSTEM",
        timestamp=datetime.now(timezone.utc),
        success=True,
    )
    db.session.add(log)
    return log


def serialize_fund(fund):
    return {
        "id": fund.id,
        "fund_name": fund.fund_name,
        "fund_code": fund.fund_code,
        "description": fund.description,
        "product_type": fund.product_type,
        "is_active": bool(fund.is_active),
        "version": fund_version(fund),
    }


def serialize_share_class(sc, with_lock=True):
    data = {
        "id": sc.id,
        "core_fund_id": sc.core_fund_id,
        "class_name": sc.class_name,
        "class_code": sc.class_code,
        "currency": sc.currency,
        "product_type": sc.product_type,
        "is_active": bool(sc.is_active),
        "version": share_class_version(sc),
    }
    if with_lock:
        reasons = share_class_currency_blockers(sc)
        data["currency_locked"] = bool(reasons)
        data["currency_lock_reasons"] = reasons
        data["open_batches"] = [_batch_label(b) for b in class_open_batches(sc)]
    return data


def _lock_fund(fund_id, product):
    return db.session.query(CoreFund).filter(
        CoreFund.id == fund_id, CoreFund.product_type == product
    ).with_for_update().first()


def _check_product_field(data, current_product):
    requested = data.get("product_type", data.get("product"))
    if requested is None:
        return None
    if str(requested).strip().upper() != current_product:
        return _resp(400, "Product (Funds/Shares) cannot be changed after creation.",
                     code="PRODUCT_IMMUTABLE", errors={"product_type": "Product cannot be changed."})
    return None


def _check_version(data, current_version):
    sent = data.get("version")
    if sent is None:
        return None  # older callers (scripts/tests) that predate concurrency checks
    if str(sent) != current_version:
        return _resp(409, "This record was changed by someone else since you opened the form. "
                          "Reload the page to see the latest values, then make your change again.",
                     code="VERSION_CONFLICT")
    return None


# ─────────────────────────── edit context ───────────────────────────

def get_edit_context(fund_id, product):
    user, err = require_role()
    if err:
        return err
    fund = db.session.query(CoreFund).filter(CoreFund.id == fund_id, CoreFund.product_type == product).first()
    if not fund:
        return _resp(404, "Fund not found")
    classes = db.session.query(ShareClass).filter(ShareClass.core_fund_id == fund.id).order_by(
        ShareClass.is_active.desc(), ShareClass.class_name
    ).all()
    data = {
        "fund": serialize_fund(fund),
        "allowed_currencies": list(CURRENCIES_BY_PRODUCT[product]),
        "can_override_currency": user.role in CURRENCY_OVERRIDE_ROLES,
        "open_batches": [_batch_label(b) for b in fund_open_batches(fund)],
        "rename_locked": fund_has_ledger_rows(fund),
        "share_classes": [serialize_share_class(sc) for sc in classes],
    }
    return _resp(200, "Edit context retrieved", data=data)


# ─────────────────────────── fund edit ───────────────────────────

def update_fund(fund_id, product):
    from app.Investments.model import Investment, Withdrawal, PendingEmail
    from app.Performance.model import Performance
    from app.Performance.pro_rata_distribution import ProRataDistribution
    from app.Batch.fund import Fund as LegacyBatchFund
    from app.utils.statement_theme import resolve_product_type

    user, err = require_role()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    if not data:
        return _resp(400, "Request body is required")

    try:
        fund = _lock_fund(fund_id, product)
        if not fund:
            return _resp(404, "Fund not found")

        err = _check_product_field(data, fund.product_type) or _check_version(data, fund_version(fund))
        if err:
            db.session.rollback()
            return err

        errors = {}
        new = {}

        if "fund_name" in data and data["fund_name"] is not None:
            name = str(data["fund_name"]).strip()
            if not name:
                errors["fund_name"] = "Name is required."
            elif len(name) > FUND_NAME_MAX:
                errors["fund_name"] = f"Name must be at most {FUND_NAME_MAX} characters."
            else:
                new["fund_name"] = name

        if "fund_code" in data and data["fund_code"] is not None:
            code = str(data["fund_code"]).strip().upper()
            if not code:
                errors["fund_code"] = "Code is required."
            elif len(code) > FUND_CODE_MAX:
                errors["fund_code"] = f"Code must be at most {FUND_CODE_MAX} characters."
            else:
                new["fund_code"] = code

        if "description" in data:
            desc = data["description"]
            desc = (str(desc).strip() or None) if desc is not None else None
            if desc and len(desc) > DESCRIPTION_MAX:
                errors["description"] = f"Description must be at most {DESCRIPTION_MAX} characters."
            else:
                new["description"] = desc

        status_raw = data.get("is_active", data.get("status"))
        if status_raw is not None:
            try:
                new["is_active"] = _parse_bool(status_raw)
            except ValueError as e:
                errors["is_active"] = f"Status {e}."

        if errors:
            db.session.rollback()
            return _resp(400, "Please fix the highlighted fields.", errors=errors)

        old_snapshot = {
            "fund_name": fund.fund_name, "fund_code": fund.fund_code,
            "description": fund.description, "is_active": bool(fund.is_active),
        }
        changed = {k: v for k, v in new.items() if old_snapshot.get(k) != v}
        if not changed:
            db.session.rollback()
            return _resp(200, "No changes", data=serialize_fund(fund))

        # Uniqueness — name (global, case-insensitive: the DB constraint is
        # global) and code (within this product).
        if "fund_name" in changed and changed["fund_name"].lower() != (fund.fund_name or "").lower():
            if db.session.query(CoreFund.id).filter(
                func.lower(CoreFund.fund_name) == changed["fund_name"].lower(), CoreFund.id != fund.id
            ).first():
                errors["fund_name"] = "A fund or share with this name already exists."
        if "fund_code" in changed:
            if db.session.query(CoreFund.id).filter(
                func.upper(CoreFund.fund_code) == changed["fund_code"],
                CoreFund.product_type == fund.product_type,
                CoreFund.id != fund.id,
            ).first():
                errors["fund_code"] = f"Another {'share' if product == SHARES else 'fund'} already uses this code."
        if errors:
            db.session.rollback()
            return _resp(409, "Please fix the highlighted fields.", code="DUPLICATE", errors=errors)

        # Consistency: renaming must not re-classify the fund under the
        # name/code heuristic still used across the app (statement theming,
        # auto-created funds), and must not break the hash-chained ledger.
        new_name = changed.get("fund_name", fund.fund_name)
        new_code = changed.get("fund_code", fund.fund_code)
        if "fund_name" in changed or "fund_code" in changed:
            before = resolve_product_type([fund.fund_name], [fund.fund_code])
            after = resolve_product_type([new_name], [new_code])
            if before == fund.product_type and after != fund.product_type:
                db.session.rollback()
                return _resp(409, "This name/code would make the system treat it as a "
                                  f"{'Share' if after == SHARES else 'Fund'} product in other places "
                                  "(statements, uploads). Choose a name/code consistent with its product.",
                             code="CONSISTENCY", errors={"fund_code" if "fund_code" in changed else "fund_name":
                                                         "Not consistent with this product."})
        if "fund_name" in changed and fund_has_ledger_rows(fund):
            db.session.rollback()
            return _resp(409, "This name cannot be changed: the fund already has committed epoch-ledger entries, "
                              "which are hash-chained over the fund name.",
                         code="RENAME_BLOCKED", blockers=["Committed epoch-ledger entries"],
                         errors={"fund_name": "Locked because the fund has ledger history."})

        if changed.get("is_active") is False:
            open_batches = fund_open_batches(fund)
            if open_batches:
                names = [_batch_label(b) for b in open_batches]
                db.session.rollback()
                return _resp(409, f"Cannot deactivate while it has open batches: {', '.join(names)}. "
                                  "Close those batches first.",
                             code="DEACTIVATION_BLOCKED", blockers=names,
                             errors={"is_active": "Has open batches."})

        cascade_counts = {}
        if "fund_name" in changed:
            old_name = fund.fund_name
            old_lower = (old_name or "").lower()
            nm = changed["fund_name"]
            cascade_counts["investments"] = db.session.query(Investment).filter(_fund_scope(fund)).update(
                {Investment.fund_name: nm}, synchronize_session=False)
            cascade_counts["withdrawals"] = db.session.query(Withdrawal).filter(or_(
                Withdrawal.fund_id == fund.id,
                (Withdrawal.fund_id == None) & (func.lower(Withdrawal.fund_name) == old_lower),  # noqa: E711
            )).update({Withdrawal.fund_name: nm}, synchronize_session=False)
            cascade_counts["pending_emails"] = db.session.query(PendingEmail).filter(
                func.lower(PendingEmail.fund_name) == old_lower).update(
                {PendingEmail.fund_name: nm}, synchronize_session=False)
            cascade_counts["performance"] = db.session.query(Performance).filter(
                func.lower(Performance.fund_name) == old_lower).update(
                {Performance.fund_name: nm}, synchronize_session=False)
            cascade_counts["pro_rata_distributions"] = db.session.query(ProRataDistribution).filter(or_(
                ProRataDistribution.fund_id == fund.id, func.lower(ProRataDistribution.fund_name) == old_lower,
            )).update({ProRataDistribution.fund_name: nm}, synchronize_session=False)
            cascade_counts["batch_funds"] = db.session.query(LegacyBatchFund).filter(
                func.lower(LegacyBatchFund.fund_name) == old_lower).update(
                {LegacyBatchFund.fund_name: nm}, synchronize_session=False)

        for k, v in changed.items():
            setattr(fund, k, v)
        fund.updated_at = datetime.now(timezone.utc)

        noun = "share" if product == SHARES else "fund"
        desc = f"Edited {noun}: " + ", ".join(sorted(changed.keys()))
        if cascade_counts:
            desc += " | renamed denormalized copies: " + ", ".join(f"{k}={v}" for k, v in cascade_counts.items())
        _audit("UPDATE_FUND" if product == FUNDS else "UPDATE_SHARE", noun, fund.id, new_name, desc,
               {k: old_snapshot[k] for k in changed}, dict(changed), user)

        db.session.commit()
        return _resp(200, f"{noun.capitalize()} updated", data=serialize_fund(fund))
    except Exception as e:
        db.session.rollback()
        return _resp(500, f"Error: {e}")


# ─────────────────────────── share class edit ───────────────────────────

def update_share_class(fund_id, class_id, product):
    from app.Investments.model import Investment, PendingEmail

    user, err = require_role()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    if not data:
        return _resp(400, "Request body is required")

    try:
        fund = db.session.query(CoreFund).filter(CoreFund.id == fund_id, CoreFund.product_type == product).first()
        if not fund:
            return _resp(404, "Fund not found")
        sc = db.session.query(ShareClass).filter(
            ShareClass.id == class_id, ShareClass.core_fund_id == fund.id
        ).with_for_update().first()
        if not sc:
            return _resp(404, "Share class not found")

        err = _check_product_field(data, sc.product_type) or _check_version(data, share_class_version(sc))
        if err:
            db.session.rollback()
            return err

        errors, new = {}, {}
        if "class_name" in data and data["class_name"] is not None:
            v = str(data["class_name"]).strip()
            if not v:
                errors["class_name"] = "Class name is required."
            elif len(v) > CLASS_NAME_MAX:
                errors["class_name"] = f"Class name must be at most {CLASS_NAME_MAX} characters."
            else:
                new["class_name"] = v
        if "class_code" in data and data["class_code"] is not None:
            v = str(data["class_code"]).strip().upper()
            if not v:
                errors["class_code"] = "Class code is required."
            elif len(v) > CLASS_CODE_MAX:
                errors["class_code"] = f"Class code must be at most {CLASS_CODE_MAX} characters."
            else:
                new["class_code"] = v
        if "currency" in data and data["currency"] is not None:
            v = str(data["currency"]).strip().upper()
            allowed = CURRENCIES_BY_PRODUCT[product]
            if v not in allowed:
                errors["currency"] = f"Currency must be one of: {', '.join(allowed)}"
            else:
                new["currency"] = v
        status_raw = data.get("is_active", data.get("status"))
        if status_raw is not None:
            try:
                new["is_active"] = _parse_bool(status_raw)
            except ValueError as e:
                errors["is_active"] = f"Status {e}."
        if errors:
            db.session.rollback()
            return _resp(400, "Please fix the highlighted fields.", errors=errors)

        old_snapshot = {"class_name": sc.class_name, "class_code": sc.class_code,
                        "currency": sc.currency, "is_active": bool(sc.is_active)}
        changed = {k: v for k, v in new.items() if old_snapshot.get(k) != v}
        if not changed:
            db.session.rollback()
            return _resp(200, "No changes", data=serialize_share_class(sc))

        if "class_code" in changed and db.session.query(ShareClass.id).filter(
            func.upper(ShareClass.class_code) == changed["class_code"], ShareClass.id != sc.id
        ).first():
            db.session.rollback()
            return _resp(409, "Please fix the highlighted fields.", code="DUPLICATE",
                         errors={"class_code": "Class code already exists."})

        override_used = False
        lock_reasons = []
        if "currency" in changed:
            lock_reasons = share_class_currency_blockers(sc)
            if lock_reasons:
                wants_override = data.get("confirm_currency_override") is True
                if not wants_override or user.role not in CURRENCY_OVERRIDE_ROLES:
                    db.session.rollback()
                    return _resp(409, "Currency is locked because this share class has "
                                      f"{', '.join(lock_reasons)}.",
                                 code="CURRENCY_LOCKED", blockers=lock_reasons,
                                 can_override=user.role in CURRENCY_OVERRIDE_ROLES,
                                 errors={"currency": "Currency is locked because this has deposits/valuations."})
                override_used = True

        if changed.get("is_active") is False:
            open_batches = class_open_batches(sc)
            if open_batches:
                names = [_batch_label(b) for b in open_batches]
                db.session.rollback()
                return _resp(409, f"Cannot deactivate while it has open batches: {', '.join(names)}. "
                                  "Close those batches first.",
                             code="DEACTIVATION_BLOCKED", blockers=names,
                             errors={"is_active": "Has open batches."})

        cascade = {}
        if "class_code" in changed:
            cascade["investments_share_series"] = db.session.query(Investment).filter(
                Investment.share_class_id == sc.id
            ).update({Investment.share_series: changed["class_code"]}, synchronize_session=False)
        if "currency" in changed:
            # Relabel linked deposit/pending-email currency (pre-existing
            # behaviour of this endpoint). Amounts are NOT converted.
            inv_ids = [r[0] for r in db.session.query(Investment.id).filter(Investment.share_class_id == sc.id).all()]
            cascade["investments_currency_relabelled"] = db.session.query(Investment).filter(
                Investment.share_class_id == sc.id
            ).update({Investment.currency_type: changed["currency"]}, synchronize_session=False)
            if inv_ids:
                cascade["pending_emails_currency_relabelled"] = db.session.query(PendingEmail).filter(
                    PendingEmail.investor_id.in_(inv_ids),
                    PendingEmail.status.in_(("Pending_Confirmation", "Suppressed")),
                ).update({PendingEmail.currency_type: changed["currency"]}, synchronize_session=False)

        for k, v in changed.items():
            setattr(sc, k, v)

        desc = f"Edited share class of {fund.fund_name}: " + ", ".join(sorted(changed.keys()))
        if cascade:
            desc += " | " + ", ".join(f"{k}={v}" for k, v in cascade.items())
        _audit("UPDATE_SHARE_CLASS", "share_class", sc.id, f"{fund.fund_name} / {sc.class_code}", desc,
               {k: old_snapshot[k] for k in changed}, dict(changed), user)
        if override_used:
            _audit("SHARE_CLASS_CURRENCY_OVERRIDE", "share_class", sc.id, f"{fund.fund_name} / {sc.class_code}",
                   "Super admin overrode the currency lock. Existing figures were NOT converted. "
                   f"Lock reasons at the time: {', '.join(lock_reasons)}",
                   {"currency": old_snapshot["currency"]}, {"currency": changed["currency"]}, user)

        db.session.commit()
        return _resp(200, "Share class updated", data=serialize_share_class(sc))
    except Exception as e:
        db.session.rollback()
        return _resp(500, f"Error: {e}")
