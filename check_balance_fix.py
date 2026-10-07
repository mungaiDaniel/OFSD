from main import create_app
from config import DevelopmentConfig
app = create_app(DevelopmentConfig)
from app.database.database import db
from sqlalchemy import text

with app.app_context():
    # Check investments count and sample data
    inv_count = db.session.execute(text("SELECT COUNT(*) FROM investments")).scalar()
    print(f"Total investments: {inv_count}")
    
    if inv_count > 0:
        sample = db.session.execute(text(
            "SELECT internal_client_code, investor_name, fund_name, shares_owned, amount_deposited, current_market_value, valuation FROM investments LIMIT 5"
        )).fetchall()
        print("Sample investments:")
        for row in sample:
            print(" ", row)

    # Check batches
    batch_count = db.session.execute(text("SELECT COUNT(*) FROM batches")).scalar()
    print(f"Total batches: {batch_count}")
    if batch_count > 0:
        bcols = db.session.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='batches' ORDER BY ordinal_position"
        )).fetchall()
        print("Batches columns:", [c[0] for c in bcols])
        bsample = db.session.execute(text(
            "SELECT id, batch_name, balance_at_end_of_period, total_profit, performance_rate FROM batches LIMIT 5"
        )).fetchall()
        print("Sample batches:")
        for row in bsample:
            print(" ", row)

    # Check valuation_runs
    vr_count = db.session.execute(text("SELECT COUNT(*) FROM valuation_runs")).scalar()
    print(f"Total valuation_runs: {vr_count}")
    if vr_count > 0:
        vrcols = db.session.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='valuation_runs' ORDER BY ordinal_position"
        )).fetchall()
        print("valuation_runs columns:", [c[0] for c in vrcols])
        vrsample = db.session.execute(text(
            "SELECT * FROM valuation_runs LIMIT 5"
        )).fetchall()
        print("Sample valuation_runs:")
        for row in vrsample:
            print(" ", row)
