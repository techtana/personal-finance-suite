from flask import Blueprint

api_bp = Blueprint("api", __name__)

# Import and register API blueprints
from api.accounts import bp as accounts_bp
from api.transactions import bp as transactions_bp
from api.equity import bp as equity_bp
from api.projection import bp as projection_bp
from api.settings import bp as settings_bp
from api.snapshots import bp as snapshots_bp
from api.rules import bp as rules_bp
from api.changes import bp as changes_bp

api_bp.register_blueprint(accounts_bp)
api_bp.register_blueprint(transactions_bp)
api_bp.register_blueprint(equity_bp)
api_bp.register_blueprint(projection_bp)
api_bp.register_blueprint(settings_bp)
api_bp.register_blueprint(snapshots_bp)
api_bp.register_blueprint(rules_bp)
api_bp.register_blueprint(changes_bp)

