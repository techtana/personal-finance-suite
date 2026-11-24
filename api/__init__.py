from flask import Blueprint

api_bp = Blueprint("api", __name__)

# Import and register API blueprints
from api.accounts import bp as accounts_bp
from api.equity import bp as equity_bp
from api.projection import bp as projection_bp
from api.settings import bp as settings_bp
from api.snapshots import bp as snapshots_bp
from api.rules import bp as rules_bp
from api.changes import bp as changes_bp
from api.taxes import bp as taxes_bp
from api.lookback import bp as lookback_bp
from api.imports import bp as imports_bp
from api.overview import bp as overview_bp
from api.assistant import bp as assistant_bp

api_bp.register_blueprint(accounts_bp)
api_bp.register_blueprint(equity_bp)
api_bp.register_blueprint(projection_bp)
api_bp.register_blueprint(settings_bp)
api_bp.register_blueprint(snapshots_bp)
api_bp.register_blueprint(rules_bp)
api_bp.register_blueprint(changes_bp)
api_bp.register_blueprint(taxes_bp)
api_bp.register_blueprint(lookback_bp)
api_bp.register_blueprint(imports_bp)
api_bp.register_blueprint(overview_bp)
api_bp.register_blueprint(assistant_bp)
