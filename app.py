import os
from flask import Flask
from flask_migrate import Migrate
from config import get_config
from models import db


migrate = Migrate()


def create_app(config=None):
    """Flask application factory."""
    app = Flask(__name__)

    if config is None:
        config = get_config()

    app.config.from_object(config)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Create any new tables not yet covered by migrations
    with app.app_context():
        db.create_all()

    # Register blueprints
    from api import api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    from pages import pages_bp
    app.register_blueprint(pages_bp)

    # Shell context for flask shell
    @app.shell_context_processor
    def make_shell_context():
        return {"db": db}

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {"error": "not found"}, 404

    @app.errorhandler(500)
    def internal_error(error):
        return {"error": "internal server error"}, 500

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
