"""Checks against what is already in the database: duplicates, transfers, accounts.

Runs after processing, whenever the batch's account changes, and again right
before a commit (another file may have been committed in the meantime).
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date, timedelta

from importer.core import SKIP_FLAGS
from importer.parsing import merchant_similar

# Flags this module owns; they are recomputed on every refresh.
OWNED = {"duplicate", "possible_duplicate", "transfer", "pick_account", "older_snapshot", "rule_exists",
         "card_balance"}
_CARD_ACCOUNT = re.compile(r"(?i)credit|card|visa|mastercard|amex")
DATE_SLACK = 3  # card transactions post a day or three after the receipt date
_TRANSFERISH = re.compile(r"(?i)transfer|xfer|payment|pmt|autopay|deposit|withdrawal")


def fingerprint(account_id, row_date, amount, key, n) -> str:
    raw = f"{account_id or ''}|{row_date}|{amount}|{key or ''}|{n}"
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def default_action(row) -> str:
    return "skip" if set(row.flags or []) & SKIP_FLAGS else "import"


def refresh_matches(batch) -> int:
    """Recompute owned flags and default actions. Returns how many rows newly became duplicates."""
    from models import Account, ChangeEvent, ImportBatch, ImportRow, Rule, Snapshot, db

    acct = batch.account_id
    rows = list(batch.rows)
    before = {r.id for r in rows if {"duplicate", "possible_duplicate"} & set(r.flags or [])}
    for r in rows:
        r.flags = [f for f in (r.flags or []) if f not in OWNED]
        r.match = None

    txns = [r for r in rows if r.target == "change_event"]
    counts: Counter = Counter()
    for r in txns:
        base = (r.account_id or acct, r.date, r.amount, r.merchant_key)
        counts[base] += 1
        r.fingerprint = fingerprint(*base, counts[base]) if r.date and r.amount is not None else None

    own_created = {r.created_id for r in rows if r.created_id}
    dated = [r.date for r in txns if r.date]
    existing, imported_from = [], {}
    if dated:
        lo = (date.fromisoformat(min(dated)) - timedelta(days=DATE_SLACK)).isoformat()
        hi = (date.fromisoformat(max(dated)) + timedelta(days=DATE_SLACK)).isoformat()
        existing = [c for c in ChangeEvent.query.filter(ChangeEvent.date >= lo, ChangeEvent.date <= hi).all()
                    if c.id not in own_created]
        ids = [c.id for c in existing if c.change_type == "imported"]
        if ids:
            q = (db.session.query(ImportRow.created_id, ImportBatch.doc_type, ImportBatch.filename)
                 .join(ImportBatch, ImportRow.batch_id == ImportBatch.id)
                 .filter(ImportRow.created_id.in_(ids)))
            imported_from = {cid: (dt, fn) for cid, dt, fn in q}
    by_amount: dict[int, list] = {}
    for c in existing:
        by_amount.setdefault(c.amount, []).append(c)
    live_ids = {c.id for c in existing}

    fps = [r.fingerprint for r in txns if r.fingerprint]
    ext = [r.external_id for r in txns if r.external_id]
    prior = []
    if fps or ext:
        q = ImportRow.query.join(ImportBatch, ImportRow.batch_id == ImportBatch.id).filter(
            ImportBatch.status == "committed", ImportRow.batch_id != batch.id, ImportRow.created_id.isnot(None))
        cond = []
        if fps:
            cond.append(ImportRow.fingerprint.in_(fps))
        if ext:
            cond.append(ImportRow.external_id.in_(ext))
        prior = q.filter(db.or_(*cond)).all()
    prior_ce = {p.created_id for p in prior}
    still_there = {c.id for c in ChangeEvent.query.filter(ChangeEvent.id.in_(prior_ce)).all()} if prior_ce else set()
    by_fp = {p.fingerprint: p for p in prior if p.created_id in still_there}
    by_ext = {(p.external_id, p.batch.account_id): p for p in prior if p.external_id and p.created_id in still_there}

    claimed: set[str] = set()
    for r in txns:
        row_acct = r.account_id or acct
        hit = by_fp.get(r.fingerprint) or (by_ext.get((r.external_id, row_acct)) if r.external_id else None)
        if hit:
            r.flags = r.flags + ["duplicate"]
            r.match = {"kind": "imported", "change_id": hit.created_id, "date": hit.date,
                       "description": hit.description, "file": hit.batch.filename}
            claimed.add(hit.created_id)
            continue
        if r.date is None or r.amount is None:
            continue
        rd = date.fromisoformat(r.date)
        for c in by_amount.get(r.amount, []):
            if c.id in claimed or c.id not in live_ids:
                continue
            if abs((date.fromisoformat(c.date) - rd).days) > DATE_SLACK:
                continue
            if c.account_id and row_acct and c.account_id != row_acct:
                continue
            src = imported_from.get(c.id)
            other_doc = src[0] if src else None
            if c.change_type != "imported" or other_doc in ("receipt", "payslip") or \
                    batch.doc_type in ("receipt", "payslip") or merchant_similar(c.description, r.description):
                r.flags = r.flags + ["possible_duplicate"]
                r.match = {"kind": c.change_type, "change_id": c.id, "date": c.date, "description": c.description,
                           "file": src[1] if src else None}
                claimed.add(c.id)
                break
        if r.match:
            continue
        # The other side of a transfer already recorded in another of your accounts.
        if _TRANSFERISH.search(r.description or ""):
            for c in by_amount.get(-r.amount, []):
                if c.account_id and row_acct and c.account_id != row_acct and \
                        abs((date.fromisoformat(c.date) - rd).days) <= DATE_SLACK:
                    r.match = {"kind": "transfer", "change_id": c.id, "date": c.date, "description": c.description}
                    r.flags = r.flags + ["transfer"]
                    break

    for r in txns:
        if r.category == "transfer" and "transfer" not in r.flags:
            r.flags = r.flags + ["transfer"]

    for r in rows:
        if r.target == "snapshot":
            account = db.session.get(Account, acct) if acct else None
            if not acct:
                r.flags = r.flags + ["pick_account"]
            elif account is not None and _CARD_ACCOUNT.search(f"{account.type} {account.name}"):
                r.flags = r.flags + ["card_balance"]  # a card balance is money owed, not cash
            else:
                latest = (Snapshot.query.filter_by(entity_type="cash", entity_id=acct)
                          .order_by(Snapshot.date.desc()).first())
                if latest and r.date:
                    if latest.date == r.date and latest.value == r.amount:
                        r.flags = r.flags + ["duplicate"]
                        r.match = {"kind": "snapshot", "date": latest.date, "description": "same balance already recorded"}
                    elif latest.date > r.date:
                        r.flags = r.flags + ["older_snapshot"]
                        r.match = {"kind": "snapshot", "date": latest.date, "description": "a newer balance exists"}
        elif r.target == "rule":
            dup = [x for x in Rule.query.filter_by(is_active=True).all()
                   if x.rule_type == ("income" if (r.amount or 0) > 0 else "expense") and
                   merchant_similar(x.name, r.description)]
            if dup:
                r.flags = r.flags + ["rule_exists"]
                r.match = {"kind": "rule", "description": dup[0].name}
        elif r.target == "change_event" and r.raw and r.raw.get("explicit_account") and not r.account_id:
            r.flags = r.flags + ["pick_account"]

    for r in rows:
        if not r.user_edited:
            r.action = default_action(r)
    after = {r.id for r in rows if {"duplicate", "possible_duplicate"} & set(r.flags)}
    return len(after - before)


# ── accounts ───────────────────────────────────────────────────────────────────

def suggest_account(accounts, *, last4=None, filename=None, institution=None):
    """(account, reason) when exactly one account fits, else (None, None)."""
    if last4:
        hits = [a for a in accounts if last4 in f"{a.name} {a.note or ''} {a.institution or ''}"]
        if len(hits) == 1:
            return hits[0], f"its name mentions …{last4}"
    for label, text in (("the bank in the file", institution), ("the file name", filename)):
        if not text:
            continue
        low = text.lower()
        hits = [a for a in accounts if a.institution and len(a.institution) >= 3 and a.institution.lower() in low]
        if len(hits) == 1:
            return hits[0], f"{label} mentions {hits[0].institution}"
        hits = [a for a in accounts if a.name and a.name.lower() in low]
        if len(hits) == 1:
            return hits[0], f"{label} mentions {hits[0].name}"
    return None, None
