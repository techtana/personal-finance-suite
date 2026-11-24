"""Run an import: read -> classify -> extract -> categorize -> check -> stage for review.

Then, on the user's say-so, commit the reviewed rows to the ledger, or undo a
commit. The AI is only ever called through importer.ai_tools, and nothing it
returns reaches the database without the user's review.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

from flask import current_app

from importer import ai_tools, documents, equity, statements
from importer.categorize import categorize
from importer.core import REVIEW_FLAGS, Ctx, ImportFailure, Proposal
from importer.extract import UnsupportedFile, load_document
from importer.llm import LLMError, get_client
from importer.matching import refresh_matches, suggest_account
from importer.parsing import parse_date
from importer.taxonomy import STARTER_CATEGORIES, allowed_categories, fits_direction

log = logging.getLogger(__name__)

MAPPING_KEYS = ("date_col", "description_col", "amount_col", "debit_col", "credit_col", "balance_col",
                "category_col", "direction_col", "id_col", "memo_col", "date_format", "sign_convention")
FREQUENCIES = ("weekly", "biweekly", "monthly", "quarterly", "annually")


class ImportWaiting(Exception):
    """The file needs AI, and the only AI that can read it is a home computer that is off."""


class CommitError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _models():
    import models

    return models


# ── processing ─────────────────────────────────────────────────────────────────

def process_batch(batch_id: str) -> None:
    m = _models()
    db = m.db
    batch = db.session.get(m.ImportBatch, batch_id)
    if batch is None:
        return
    app = current_app._get_current_object()
    llm = get_client(app, "batch")
    status = llm.status() if llm.enabled else {"ok": False, "error": llm.blocked_reason}
    settings = m.Settings.query.first()
    locale = (settings.locale if settings else "en-US") or "en-US"
    accounts = m.Account.query.filter_by(is_active=True).all()
    previous = batch.extracted or {}
    overrides = (batch.mapping or {}).get("override") or {}

    def stage(text):
        batch.stage = text
        db.session.commit()

    ctx = Ctx(llm=llm, ai_ok=bool(status.get("ok")), prefer_dayfirst=not locale.lower().startswith("en-us"),
              accounts=accounts, account=db.session.get(m.Account, batch.account_id) if batch.account_id else None,
              filename=batch.filename, stage=stage, overrides=overrides)
    ctx.ai_reason = status.get("error")
    ctx.warnings = [w for w in (batch.warnings or []) if w.get("sticky")]  # notes made at upload time
    batch.rows = []  # re-reading replaces earlier proposals
    batch.status, batch.error, batch.created = "processing", None, None
    db.session.flush()
    try:
        stage("Reading the file")
        if not batch.stored_path or not os.path.exists(batch.stored_path):
            raise ImportFailure("The uploaded file is no longer on disk; drop it again.")
        with open(batch.stored_path, "rb") as f:
            doc = load_document(f.read(), batch.filename)
        batch.file_kind = doc.kind
        from_photo = False
        if doc.images and not doc.text:
            if not ctx.ai_ok and status.get("waiting"):
                raise ImportWaiting()
            if not ctx.ai_ok:
                raise ImportFailure("Reading photos and scanned PDFs needs the local AI, which isn't available: "
                                    f"{ctx.ai_reason}")
            texts = []
            for i, img in enumerate(doc.images):
                stage("Reading the photo with the local AI" +
                      (f" (page {i + 1} of {len(doc.images)})" if len(doc.images) > 1 else ""))
                try:
                    texts.append(ai_tools.transcribe(llm, img))
                except LLMError as e:
                    raise ImportFailure(f"The local AI couldn't read the photo: {e}")
            doc.text = "\n\n".join(texts)
            from_photo = True
            ctx.extracted["transcript"] = doc.text
        elif doc.text and doc.kind in ("text", "pdf"):
            ctx.extracted["text_preview"] = doc.text[:8000]

        stage("Working out what kind of document this is")
        doc_type = batch.doc_type if batch.doc_type_forced and batch.doc_type else documents.classify(doc, ctx)
        batch.doc_type = doc_type
        allowed = allowed_categories(m.Category.query.all())
        rules = m.Rule.query.filter_by(is_active=True).all()

        if doc_type == "statement":
            stage("Reading transactions")
            if doc.ofx:
                proposals = statements.from_ofx(doc.ofx, ctx)
            elif doc.tables:
                proposals = statements.from_table(doc.tables[0], ctx)
            else:
                proposals = statements.from_text(doc.text, ctx)
        elif doc_type == "receipt":
            proposals = documents.from_receipt(doc.text, ctx, allowed)
        elif doc_type == "payslip":
            proposals = documents.from_payslip(doc.text, ctx, rules)
        elif doc_type == "equity":
            stage("Reading the grant notice")
            proposals = equity.from_grant_notice(doc.text, ctx, m.Rule.query.filter_by(rule_type="rsu").all())
        else:
            proposals = []
            ctx.warn("Couldn't tell whether this is a statement, a receipt or a pay stub. Pick the type above and "
                     "re-read.")

        if overrides.get("flip_signs"):
            for p in proposals:
                if p.target in ("change_event", "rule") and p.amount is not None:
                    p.amount = -p.amount
        if from_photo:
            for p in proposals:
                p.flag("from_photo", 0.9)

        learned = {r.merchant_key: r.category for r in m.ImportMerchantRule.query.all()}
        cache = dict(previous.get("category_cache") or {})
        categorize(proposals, ctx, allowed, learned, cache)
        if doc_type == "statement":
            proposals += statements.suggest_rules(proposals, rules, batch.account_id)
        ctx.extracted["category_cache"] = cache

        if not batch.account_id:
            _suggest_account(batch, doc, ctx, accounts)

        batch.rows = [_to_row(p, i) for i, p in enumerate(proposals)]
        db.session.flush()
        stage("Checking for duplicates and transfers")
        refresh_matches(batch)
        batch.status = "review"
    except ImportWaiting:
        # Not a failure: api/ai.py reads the file as soon as the home computer connects.
        batch.status, batch.error = "waiting", None
    except (ImportFailure, UnsupportedFile) as e:
        batch.status, batch.error = "failed", str(e)
    except Exception as e:  # keep the batch visible with a message instead of a stuck spinner
        log.exception("import %s failed", batch_id)
        batch.status, batch.error = "failed", f"Unexpected error while reading the file: {e}"
    finally:
        batch.mapping = {**(ctx.mapping or {}), "override": overrides or None}
        batch.extracted = ctx.extracted
        batch.warnings = ctx.warnings
        batch.ai_usage = llm.usage()
        batch.stage = None
        db.session.commit()


def _suggest_account(batch, doc, ctx, accounts):
    m = _models()
    acct, why = None, None
    if ctx.suggested_account_id:
        acct = m.db.session.get(m.Account, ctx.suggested_account_id)
        why = "you picked it last time for this kind of file"
    elif doc.ofx:
        acct, why = suggest_account(accounts, last4=(doc.ofx.get("account_id") or "")[-4:] or None,
                                    institution=doc.ofx.get("org"), filename=batch.filename)
    else:
        acct, why = suggest_account(accounts, last4=ctx.extracted.get("account_hint"),
                                    institution=ctx.extracted.get("account_text"), filename=batch.filename)
    if acct and acct.is_active:
        batch.account_id = acct.id
        ctx.info(f"Account set to {acct.name} because {why}. Change it above if that's wrong.")


def _to_row(p: Proposal, i: int):
    m = _models()
    raw = {}
    if isinstance(p.raw, dict):
        raw = {k: v for k, v in p.raw.items() if k in ("cells", "line", "n", "fitid", "trntype")}
        if p.raw.get("kind") == "rsu_grant":
            raw = dict(p.raw)
    if p.explicit_account:
        raw["explicit_account"] = True
    return m.ImportRow(
        position=i, target=p.target, date=p.date, description=(p.description or "")[:200], amount=p.amount,
        category=p.category, category_source=p.category_source, account_id=p.account_id, frequency=p.frequency,
        confidence=round(p.confidence, 2), flags=list(p.flags), merchant_key=(p.merchant_key or "")[:100] or None,
        external_id=(p.external_id or None), note=p.note, raw=raw or None,
    )


# ── review edits ───────────────────────────────────────────────────────────────

def _update_grant_row(row, data: dict) -> None:
    """A grant row: the ticker (never in the document), its name, and whether to import it."""
    raw = dict(row.raw or {})
    if "ticker" in data:
        ticker = re.sub(r"[^A-Z0-9.\-]", "", str(data["ticker"] or "").upper())[:12]
        raw["ticker"] = ticker
    if "description" in data:
        row.description = str(data["description"] or "")[:200] or row.description
    if "action" in data:
        if data["action"] not in ("import", "skip"):
            raise CommitError("action must be import or skip")
        row.action = data["action"]
    row.raw = raw
    row.user_edited = True


def update_row(batch, row, data: dict) -> None:
    m = _models()
    if batch.status != "review":
        raise CommitError("Rows can only be changed while the import is in review.", 409)
    allowed = allowed_categories(m.Category.query.all())
    if row.target == "rsu_grant":
        _update_grant_row(row, data)
        refresh_matches(batch)
        m.db.session.commit()
        return
    if "amount" in data:
        try:
            row.amount = int(data["amount"]) if data["amount"] is not None else None
        except (TypeError, ValueError):
            raise CommitError("amount must be whole cents")
        row.flags = [f for f in row.flags if f not in ("unparsed_amount", "missing_amount", "zero_amount")]
        if row.amount == 0:
            row.flags = row.flags + ["zero_amount"]
    if "date" in data:
        iso = parse_date(data["date"], "%Y-%m-%d") if data["date"] else None
        if data["date"] and not iso:
            raise CommitError("date must be YYYY-MM-DD")
        row.date = iso
        row.flags = [f for f in row.flags if f not in ("unparsed_date", "missing_date", "ambiguous_date")]
        if not iso:
            row.flags = row.flags + ["missing_date"]
    if "description" in data:
        row.description = str(data["description"] or "")[:200]
    if "category" in data:
        cat = data["category"] or None
        if cat is not None and cat not in allowed:
            raise CommitError(f"unknown category {cat!r}")
        if cat is not None and not fits_direction(cat, row.amount, allowed):
            raise CommitError(f"{allowed[cat]['label']} is an income category; this row is money out")
        row.category, row.category_source = cat, "user"
        row.flags = [f for f in row.flags if f not in ("uncategorized", "low_confidence")]
        if data.get("apply_to_merchant") and row.merchant_key:
            for other in batch.rows:
                if other.id != row.id and other.merchant_key == row.merchant_key and other.target == row.target \
                        and other.category_source != "user" and fits_direction(cat or "misc", other.amount, allowed):
                    other.category, other.category_source = cat, "user"
                    other.flags = [f for f in other.flags if f not in ("uncategorized", "low_confidence")]
    if "account_id" in data:
        acct = data["account_id"] or None
        if acct and not m.db.session.get(m.Account, acct):
            raise CommitError("unknown account")
        row.account_id = acct
    if "frequency" in data:
        if data["frequency"] not in FREQUENCIES:
            raise CommitError("frequency must be one of " + ", ".join(FREQUENCIES))
        row.frequency = data["frequency"]
    if "action" in data:
        if data["action"] not in ("import", "skip"):
            raise CommitError("action must be import or skip")
        row.action = data["action"]
        row.user_edited = True
    refresh_matches(batch)
    m.db.session.commit()


def set_batch_account(batch, account_id):
    m = _models()
    if batch.status not in ("review", "failed"):
        raise CommitError("The account can only be changed before the import is committed.", 409)
    if account_id and not m.db.session.get(m.Account, account_id):
        raise CommitError("unknown account")
    batch.account_id = account_id or None
    refresh_matches(batch)
    m.db.session.commit()


def prepare_reprocess(batch, *, doc_type=None, mapping=None, flip_signs=None) -> None:
    """Store the user's corrections; the caller then queues process_batch."""
    m = _models()
    if batch.status == "committed":
        raise CommitError("Undo the import before re-reading the file.", 409)
    override = dict((batch.mapping or {}).get("override") or {})
    if doc_type:
        if doc_type not in ("statement", "receipt", "payslip", "equity"):
            raise CommitError("doc_type must be statement, receipt, payslip or equity")
        batch.doc_type, batch.doc_type_forced = doc_type, True
    if mapping is not None:
        clean = {}
        for k in MAPPING_KEYS:
            v = mapping.get(k)
            if k in ("date_format", "sign_convention"):
                clean[k] = v or None
            else:
                clean[k] = int(v) if v not in (None, "", -1, "-1") else None
        override["mapping"] = clean
    if flip_signs:
        override["flip_signs"] = not override.get("flip_signs", False)
    batch.mapping = {**(batch.mapping or {}), "override": override or None}
    batch.status, batch.stage = "processing", "Waiting to start"
    m.db.session.commit()


# ── commit / undo ──────────────────────────────────────────────────────────────

def commit_batch(batch, force: bool = False) -> dict:
    m = _models()
    db = m.db
    if batch.status != "review":
        raise CommitError("This import isn't waiting for review.", 409)
    if batch.doc_type == "statement" and not batch.account_id:
        raise CommitError("Choose which account this statement belongs to.")
    newly = refresh_matches(batch)
    if newly and not force:
        db.session.commit()
        raise CommitError(f"{newly} row(s) now match entries already in your data, probably from another import. "
                          "They've been unticked; check them and import again.", 409)
    created = {"change_events": [], "snapshots": [], "rules": [], "categories": [], "learned": 0}
    bad = []
    for r in batch.rows:
        if r.action != "import":
            continue
        acct = r.account_id or batch.account_id
        if r.target == "change_event":
            if not r.date or not r.amount:
                bad.append(r)
                continue
            obj = m.ChangeEvent(date=r.date, description=r.description or "(imported)", amount=r.amount,
                                account_id=acct, category=r.category, change_type="imported",
                                note=_note(r, batch))
            key = "change_events"
        elif r.target == "snapshot":
            if not acct or not r.date or r.amount is None or r.amount < 0:
                bad.append(r)
                continue
            obj = m.Snapshot(entity_type="cash", entity_id=acct, date=r.date, value=r.amount,
                             note=f"Balance from {batch.filename}"[:500])
            key = "snapshots"
        elif r.target == "rsu_grant":
            g = r.raw or {}
            if not g.get("ticker"):
                raise CommitError("Enter the stock's ticker for the RSU grant (it isn't in the document).")
            if not g.get("vests"):
                bad.append(r)
                continue
            settings = m.Settings.query.first()
            rule = m.Rule(
                name=r.description, rule_type="rsu", start_date=g.get("grant_date") or r.date,
                end_date=None, schedule=[{"date": v["date"], "shares": v["shares"]} for v in g["vests"]],
                config={"ticker": g["ticker"], "total_shares": g.get("total_shares"), "grant_date": g.get("grant_date"),
                        "grant_number": g.get("grant_number"), "company": g.get("company"), "price_at_grant": 0,
                        "withholding_rate": settings.default_withholding_rate if settings else 2200,
                        "schedule_source": "document"},
                note=_note(r, batch),
            )
            db.session.add(rule)
            db.session.flush()
            r.created_id = rule.id
            created["rules"].append(rule.id)
            continue
        elif r.target == "rule":
            if not r.date or not r.amount or r.frequency not in FREQUENCIES:
                bad.append(r)
                continue
            obj = m.Rule(name=(r.description or "Imported rule")[:100], rule_type="income" if r.amount > 0 else "expense",
                         account_id=acct, amount=abs(r.amount), frequency=r.frequency, start_date=r.date,
                         category=r.category, note=r.note)
            key = "rules"
        else:
            continue
        db.session.add(obj)
        db.session.flush()
        r.created_id = obj.id
        created[key].append(obj.id)
    if bad:
        db.session.rollback()
        raise CommitError(f"{len(bad)} ticked row(s) are missing a date, an amount or an account. Fix or untick them.")

    existing = {c.slug for c in m.Category.query.all()}
    starter = {s: (label, typ, color) for s, label, typ, color in STARTER_CATEGORIES}
    used = {r.category for r in batch.rows if r.action == "import" and r.category} - existing
    for slug in sorted(used):
        if slug in starter:
            label, typ, color = starter[slug]
            db.session.add(m.Category(slug=slug, label=label, type=typ, color=color))
            created["categories"].append(slug)

    learned = {}
    for r in batch.rows:
        if r.target == "change_event" and r.category_source == "user" and r.category and r.merchant_key:
            learned[r.merchant_key] = r.category
    for key, cat in learned.items():
        rule = m.ImportMerchantRule.query.filter_by(merchant_key=key).first()
        if rule:
            rule.category, rule.hits = cat, rule.hits + 1
        else:
            db.session.add(m.ImportMerchantRule(merchant_key=key, category=cat, hits=1))
    created["learned"] = len(learned)

    mp = batch.mapping or {}
    if mp.get("signature") and mp.get("source") in ("rules", "ai", "user", "saved"):
        saved = {k: mp.get(k) for k in MAPPING_KEYS}
        if (mp.get("override") or {}).get("flip_signs") and saved.get("amount_col") is not None:
            saved["sign_convention"] = ("positive_is_money_out" if saved.get("sign_convention") != "positive_is_money_out"
                                        else "negative_is_money_out")
        prof = m.ImportProfile.query.filter_by(signature=mp["signature"]).first()
        if prof:
            prof.mapping, prof.uses, prof.account_id = saved, prof.uses + 1, batch.account_id or prof.account_id
        else:
            db.session.add(m.ImportProfile(signature=mp["signature"], headers=mp.get("headers") or [], mapping=saved,
                                           account_id=batch.account_id, uses=1))

    batch.status = "committed"
    batch.committed_at = datetime.utcnow().isoformat(timespec="seconds")
    batch.created = created
    db.session.commit()
    return created


def _note(r, batch) -> str:
    base = f"Imported from {batch.filename}"
    return f"{r.note} · {base}"[:1000] if r.note else base


def undo_batch(batch) -> dict:
    m = _models()
    if batch.status != "committed":
        raise CommitError("Only a committed import can be undone.", 409)
    kinds = {"change_event": m.ChangeEvent, "snapshot": m.Snapshot, "rule": m.Rule, "rsu_grant": m.Rule}
    removed = 0
    for r in batch.rows:
        if r.created_id and r.target in kinds:
            obj = m.db.session.get(kinds[r.target], r.created_id)
            if obj is not None:
                m.db.session.delete(obj)
                removed += 1
            r.created_id = None
    batch.status, batch.committed_at, batch.created = "review", None, None
    m.db.session.commit()
    return {"removed": removed}


def discard_batch(batch) -> None:
    m = _models()
    if batch.status == "committed":
        raise CommitError("Undo the import before deleting it.", 409)
    path = batch.stored_path
    m.db.session.delete(batch)
    m.db.session.commit()
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ── serialization ──────────────────────────────────────────────────────────────

def row_dict(r) -> dict:
    raw = r.raw or {}
    return {
        "id": r.id, "position": r.position, "target": r.target, "action": r.action, "date": r.date,
        "description": r.description, "amount": r.amount, "category": r.category,
        "category_source": r.category_source, "account_id": r.account_id, "frequency": r.frequency,
        "confidence": r.confidence, "flags": r.flags or [], "match": r.match, "merchant_key": r.merchant_key,
        "note": r.note, "source": raw.get("cells") or raw.get("line"), "created_id": r.created_id,
        "needs_review": bool(set(r.flags or []) & REVIEW_FLAGS),
        "grant": raw if r.target == "rsu_grant" else None,
    }


def batch_summary(b) -> dict:
    rows = b.rows
    return {
        "id": b.id, "filename": b.filename, "file_kind": b.file_kind, "doc_type": b.doc_type, "status": b.status,
        "stage": b.stage, "account_id": b.account_id, "created_at": b.created_at, "committed_at": b.committed_at,
        "error": b.error,
        "counts": {
            "rows": len(rows),
            "to_import": sum(1 for r in rows if r.action == "import"),
            "needs_review": sum(1 for r in rows if set(r.flags or []) & REVIEW_FLAGS),
            "duplicates": sum(1 for r in rows if {"duplicate", "possible_duplicate"} & set(r.flags or [])),
        },
    }


def batch_detail(b) -> dict:
    m = _models()
    out = batch_summary(b)
    mapping = dict(b.mapping or {})
    extracted = {k: v for k, v in (b.extracted or {}).items() if k != "category_cache"}
    out.update({
        "mapping": mapping, "extracted": extracted, "warnings": b.warnings or [], "ai_usage": b.ai_usage or {},
        "created": b.created, "rows": [row_dict(r) for r in b.rows],
        "categories": [{"slug": k, **v} for k, v in sorted(allowed_categories(m.Category.query.all()).items(),
                                                            key=lambda kv: kv[1]["label"].lower())],
        "has_file": bool(b.stored_path and os.path.exists(b.stored_path)),
        "is_image": b.file_kind == "image",
        "doc_type_forced": b.doc_type_forced,
    })
    return out
