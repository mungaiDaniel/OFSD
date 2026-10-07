from main import app
from app.database.database import db
from app.Batch.core_fund import CoreFund
from app.Investments.model import Investment
from sqlalchemy import or_, func, distinct
import traceback

with app.app_context():
    try:
        funds = db.session.query(CoreFund).filter(CoreFund.is_active == True).order_by(CoreFund.fund_name.asc()).all()
        print('funds count', len(funds))
        for f in funds[:5]:
            print('fund', f.id, repr(f.fund_name))
            investments = db.session.query(Investment).filter(
                or_(
                    Investment.fund_id == f.id,
                    (Investment.fund_id == None) & (func.lower(Investment.fund_name) == f.fund_name.lower())
                )
            ).all()
            print(' inv count', len(investments))
            inv_count = db.session.query(func.count(distinct(Investment.internal_client_code))).filter(
                or_(
                    Investment.fund_id == f.id,
                    (Investment.fund_id == None) & (func.lower(Investment.fund_name) == f.fund_name.lower())
                )
            ).scalar() or 0
            print(' distinct inv', inv_count)
    except Exception:
        traceback.print_exc()
