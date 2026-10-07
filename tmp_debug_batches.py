import main
from app.database.database import db
from app.Batch.controllers import BatchController

with main.app.app_context():
    response = BatchController.get_all_batches(db.session)
    print(type(response))
    if hasattr(response, 'get_data'):
        print(response.get_data(as_text=True))
