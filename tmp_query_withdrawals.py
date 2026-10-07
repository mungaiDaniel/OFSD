from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

uri = 'postgresql://postgres:username@localhost/offshow_dev'
print('URI:', uri)
try:
    engine = create_engine(uri)
    with engine.connect() as conn:
        print('connected')
        res = conn.execute(text('SELECT count(*) FROM withdrawals'))
        print('withdrawals count:', res.scalar())
        res = conn.execute(text('SELECT internal_client_code, investor_id, fund_id, fund_name, amount, date_withdrawn, status, note FROM withdrawals ORDER BY date_withdrawn DESC LIMIT 10'))
        for row in res:
            print(row)
except SQLAlchemyError as e:
    print('SQLAlchemyError:', e)
except Exception as e:
    print('ERROR:', e)
