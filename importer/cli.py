"""`flask imports ...`: run the import pipeline from a terminal.

    flask imports status
    flask imports read statement.csv --account <id> [--type receipt] [--commit]
"""

from __future__ import annotations

import hashlib
import os
import shutil

import click
from flask import current_app
from flask.cli import AppGroup

imports_cli = AppGroup("imports", help="Import statements, receipts and pay stubs from files.")


@imports_cli.command("status")
def status_cmd():
    """Show whether the local AI is reachable."""
    from importer.llm import get_client

    client = get_client(current_app, "batch")
    s = client.status() if client.enabled else {"ok": False, "error": client.blocked_reason}
    click.echo(f"provider={client.provider} url={client.base_url} model={client.model}")
    click.echo("ready" if s.get("ok") else f"not ready: {s.get('error')}")


@imports_cli.command("read")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--account", "account_id", default=None, help="Account id the file belongs to.")
@click.option("--type", "doc_type", type=click.Choice(["statement", "receipt", "payslip"]), default=None)
@click.option("--commit", "do_commit", is_flag=True, help="Commit the rows that are ticked by default.")
def read_cmd(path, account_id, doc_type, do_commit):
    """Read one file and print what would be imported."""
    from importer.parsing import fmt_cents
    from importer.pipeline import commit_batch, process_batch
    from models import ImportBatch, db

    with open(path, "rb") as f:
        data = f.read()
    name = os.path.basename(path)
    batch = ImportBatch(filename=name, file_kind="unknown", file_sha256=hashlib.sha256(data).hexdigest(),
                        file_size=len(data), account_id=account_id, doc_type=doc_type,
                        doc_type_forced=bool(doc_type), warnings=[])
    db.session.add(batch)
    db.session.flush()
    storage = current_app.config["IMPORT_STORAGE_DIR"]
    os.makedirs(storage, exist_ok=True)
    batch.stored_path = os.path.join(storage, f"{batch.id}_{name}")
    shutil.copyfile(path, batch.stored_path)
    db.session.commit()
    process_batch(batch.id)
    batch = db.session.get(ImportBatch, batch.id)
    click.echo(f"{batch.filename}: {batch.doc_type} -> {batch.status}" + (f" ({batch.error})" if batch.error else ""))
    for w in batch.warnings or []:
        click.echo(f"  [{w['level']}] {w['text']}")
    for r in batch.rows:
        mark = "x" if r.action == "import" else " "
        click.echo(f"  [{mark}] {r.target:<12} {r.date or '????-??-??'} {fmt_cents(r.amount):>12}  "
                   f"{(r.category or '-'):<14} {r.description[:48]:<48} {','.join(r.flags or [])}")
    u = batch.ai_usage or {}
    click.echo(f"  AI: {u.get('calls', 0)} call(s), {u.get('seconds', 0)}s, tasks {u.get('tasks', {})}")
    click.echo(f"  review at /import?batch={batch.id}")
    if do_commit and batch.status == "review":
        created = commit_batch(batch)
        click.echo(f"  committed: {len(created['change_events'])} transaction(s), {len(created['snapshots'])} "
                   f"balance(s), {len(created['rules'])} rule(s)")
