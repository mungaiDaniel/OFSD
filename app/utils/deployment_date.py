"""Resolve the deployment date shown to a client.

Clients in one batch can be deployed on different days. Batch.date_deployed is
only the EARLIEST of those dates, so documents for a single client must prefer
the client's own InvestorShares.deployment_date, then the batch's actual date,
then the batch's date_deployed.
"""
from datetime import date, datetime


def resolve_client_deployment_date(investments, batch, session=None):
    """Return a `date` (or None) for the given client's investment(s) in a batch."""
    from app.Funds.investor_shares import InvestorShares
    from app.database.database import db

    session = session or db.session
    ids = [getattr(i, "id", None) for i in (investments if isinstance(investments, (list, tuple)) else [investments])]
    ids = [i for i in ids if i is not None]
    if ids:
        own = (
            session.query(InvestorShares.deployment_date)
            .filter(InvestorShares.investment_id.in_(ids), InvestorShares.deployment_date.isnot(None))
            .order_by(InvestorShares.deployment_date.asc())
            .first()
        )
        if own and own[0]:
            return own[0]
    actual = getattr(batch, "deployment_date_actual", None)
    if actual:
        return actual
    dt = getattr(batch, "date_deployed", None)
    if isinstance(dt, datetime):
        return dt.date()
    if isinstance(dt, date):
        return dt
    return None
