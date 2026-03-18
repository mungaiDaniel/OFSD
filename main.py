from flask import Flask
from flask_cors import CORS
from config import DevelopmentConfig as Config
from app.database.database import db
from flask_jwt_extended import JWTManager
from datetime import timedelta
from app.Admin.route import user_v1
from app.Batch.route import batch_v1
from app.Batch.fund_routes import fund_v1
from app.Investments.route import investment_v1
from app.Performance.route import performance_v1
from app.Valuation.route import valuation_v1
from app.Reports.route import reports_v1



def create_app(config_filename):
        app = Flask(__name__)
        app.config.from_object(config_filename)
        app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=1)
        app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=1)
        JWTManager(app)
        CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})
        db.init_app(app)
        app.app_context().push()
        db.create_all()
        
        # Register blueprints
        app.register_blueprint(user_v1)
        app.register_blueprint(batch_v1)
        app.register_blueprint(investment_v1)
        app.register_blueprint(fund_v1)
        app.register_blueprint(performance_v1)
        app.register_blueprint(valuation_v1)
        app.register_blueprint(reports_v1)
        
        return app

app = create_app(config_filename=Config)

if __name__ == "__main__":  
    app.run(debug=True, port=5000)