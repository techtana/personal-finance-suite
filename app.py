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
    ("snapshots", "gap_ok", "INTEGER"),
    ("snapshots", "gap_ok_at", "VARCHAR(32)"),
    ("snapshots", "gap_note", "TEXT"),
]


# Indexes for the tables that grow with years of history: imported transactions
# and recorded balances. IF NOT EXISTS makes this safe on every start.
_INDEXES = [
    ("ix_change_events_date", "change_events", "date"),
    ("ix_change_events_account_date", "change_events", "account_id, date"),
    ("ix_change_events_snapshot", "change_events", "snapshot_id"),
    ("ix_snapshots_entity_date", "snapshots", "entity_type, entity_id, date"),
]


def _add_missing_indexes():
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    for name, table, columns in _INDEXES:
        if inspector.has_table(table):
            db.session.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})"))
    db.session.commit()


def _add_missing_columns():
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    for table, column, ddl in _ADDED_COLUMNS:
        if not inspector.has_table(table):
            continue
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    db.session.commit()


def _convert_reconcile_adjustments():
    """Older versions logged a balance's unexplained difference as an adjustment entry.

    A sign-off on the balance now does that job, and its gap is worked out afresh
    from the transactions, so later imports can shrink it. Each old adjustment
    becomes a sign-off of the difference it logged, and the entry goes.
    """
    from engine import ledger
    from models import Account, ChangeEvent, Snapshot

    olds = ChangeEvent.query.filter(ChangeEvent.change_type == "adjustment", ChangeEvent.snapshot_id.isnot(None)).all()
    for c in olds:
        snap = db.session.get(Snapshot, c.snapshot_id)
        account = db.session.get(Account, c.account_id) if c.account_id else None
        if snap is not None and snap.gap_ok is None:
            owed = ledger.is_owed(account.type if account else None)
            snap.gap_ok = ledger.sign(owed) * (c.amount or 0)
            snap.gap_ok_at = c.created_at
            snap.gap_note = snap.gap_note or "Logged as an adjustment"
        db.session.delete(c)
    if olds:
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
        _add_missing_indexes()
        _convert_reconcile_adjustments()

    # Who is asking, the audit log and the stale-save check
    import audit
    audit.init_app(app)

    @app.route("/healthz")
    def healthz():
        return {"ok": True}

    # Register blueprints
    from api import api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    from pages import pages_bp
    app.register_blueprint(pages_bp)

    from importer.cli import imports_cli
    app.cli.add_command(imports_cli)

    # Files that waited for the home computer are read when it connects
    from ai.endpoints import routed_client
    from api import ai as ai_api
    app.extensions["llm_router"] = routed_client
    ai_api.init_app(app)

    from backup import backups_cli
    app.cli.add_command(backups_cli)

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
