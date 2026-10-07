"""
Shared product-type classification: every batch (and the deposits/holdings in
it) is either a FUNDS or a SHARES product.

SHARES is currently only DPRP (Dangote Petroleum Refinery and Petrochemicals) —
a direct share purchase with a hard deployment cap — everything else is FUNDS.
Defined once here (rather than in app.Batch.model or app.Investments.model) so
both can import the same Enum instance; SQLAlchemy needs the identical Enum
object shared across columns to create/drop the underlying Postgres type once
instead of once per table.
"""

from sqlalchemy import Enum

FUNDS = "FUNDS"
SHARES = "SHARES"
PRODUCT_TYPES = (FUNDS, SHARES)

ProductTypeEnum = Enum(*PRODUCT_TYPES, name="product_type_enum")
