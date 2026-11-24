import os
from flask import Flask
from flask_migrate import Migrate
from config import get_config
from sqlalchemy import inspect, text
from models import db

migrate = Migrate()


# Columns added after the first release. db.create_all() never alters an existing
# table, so they are added here for databases created before the column existed.
_ADDED_COLUMNS = [
    ("settings", "tax_profile", "JSON"),
    ("settings", "backup_config", "JSON"),
    ("rules", "tax_treatment", "VARCHAR(30)"),
    ("change_events", "tax_treatment", "VARCHAR(30)"),
    ("assets", "decided_date", "VARCHAR(10)"),
]


def _add_missing_columns():
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    for table, column, ddl in _ADDED_COLUMNS:
        if not inspector.has_table(table):
            continue
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    db.session.commit()


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
        _add_missing_columns()

    # Register blueprints
    from api import api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    from pages import pages_bp
    app.register_blueprint(pages_bp)

    from importer.cli import imports_cli
    app.cli.add_command(imports_cli)

    # Regular cloud backups (no-op when testing)
    from backup import start_scheduler
    start_scheduler(app)

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
