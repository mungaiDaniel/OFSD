from sqlalchemy import Column, Integer, String, Boolean, DateTime, UniqueConstraint, Index, event
from app.database.database import db
from app.database.product_type import ProductTypeEnum, FUNDS, SHARES
from base_model import Base
from datetime import datetime, timezone


class CoreFund(Base, db.Model):
    """
    Core funds are the global buckets used for performance triggering:
    Axiom and Atium — plus, since Task 8, the authoritative FUNDS/SHARES
    classification itself. Set once at creation and immutable after, exactly
    like Batch.product_type / Investment.product_type (Task 1). ShareClass,
    Batch, and Investment each inherit and validate against the row above
    them in that chain (see the before_insert events on ShareClass/Batch in
    their own model files, and Investment's existing one).

    product_type is explicit when the caller provides it (this is what
    POST /api/v1/funds vs POST /api/v1/shares does — see
    app/Funds/routes.py's _create_fund_impl) — otherwise it's inferred from
    fund_name/fund_code via the same is_dangote_dprp_fund heuristic used
    everywhere else in this codebase (see _infer_product_type_if_unset
    below), so every pre-Task-8 call site that creates a CoreFund by name
    without knowing about product_type at all (tests, bulk-upload
    auto-create-fund flows, etc.) keeps behaving exactly as it did before —
    DPRP still resolves to SHARES automatically, everything else to FUNDS.
    """

    __tablename__ = "core_funds"
    __table_args__ = (
        UniqueConstraint("fund_name", name="_core_fund_name_uc"),
        Index("ix_core_funds_product_type", "product_type"),
    )

    id = Column(Integer, primary_key=True)
    fund_name = Column(String(100), nullable=False)
    fund_code = Column(String(50), nullable=True)
    product_type = Column(ProductTypeEnum, nullable=False, default=FUNDS, server_default=FUNDS)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<CoreFund {self.fund_name} product={self.product_type} active={self.is_active}>"


@event.listens_for(CoreFund, "before_insert")
def _infer_product_type_if_unset(mapper, connection, target):
    """
    Falls back to the is_dangote_dprp_fund name/code heuristic only when the
    caller didn't set product_type explicitly — see the class docstring for
    why (backward compatibility for every pre-Task-8 CoreFund creation site).
    """
    if target.product_type:
        return
    from app.utils.statement_theme import is_dangote_dprp_fund
    if is_dangote_dprp_fund([target.fund_name], [target.fund_code]):
        target.product_type = SHARES
    else:
        target.product_type = FUNDS


def get_fund_scoped_or_404(fund_id, product):
    """
    Task 8: shared lookup for every /funds/<id>... and /shares/<id>... route —
    fetches a CoreFund by id, scoped to the given product, so a FUNDS fund_id
    can never be reached through a /shares/... URL and vice versa (and a
    nonexistent id behaves identically either way: a plain 404, not a 403/400
    that would leak whether the id exists under the other product).

    Returns (fund, None) on success, or (None, error_response) to return
    directly from the caller's route function.
    """
    from flask import jsonify, make_response

    fund = CoreFund.query.filter(CoreFund.id == fund_id, CoreFund.product_type == product).first()
    if not fund:
        return None, make_response(jsonify({"status": 404, "message": "Fund not found"}), 404)
    return fund, None

