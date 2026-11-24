"""Give each proposed transaction a category, cheapest and surest source first.

1. learned   the category you picked for this merchant in an earlier import
2. document  what the AI read off a receipt or pay stub (it saw the items)
3. keyword   built-in merchant and keyword rules
4. bank      the category column some bank exports include
5. ai        the local model, once per merchant (not per row), from a fixed list
Anything still open is flagged "uncategorized" for you to pick.
"""

from __future__ import annotations

from statistics import median

from importer import ai_tools
from importer.core import Ctx, Proposal
from importer.taxonomy import bank_category, fits_direction, keyword_category

CONF = {"learned": 0.97, "document": 0.9, "keyword": 0.85, "bank": 0.75}
LOW_CONFIDENCE = 0.6


def categorize(proposals: list[Proposal], ctx: Ctx, allowed: dict, learned: dict, cache: dict) -> None:
    """learned: merchant_key -> slug. cache: "key|sign" -> [slug, conf] from earlier AI answers for this file."""
    pending: dict[tuple, list[Proposal]] = {}
    for p in proposals:
        if p.target != "change_event" or p.amount is None:
            continue
        slug = learned.get(p.merchant_key)
        if slug and fits_direction(slug, p.amount, allowed):
            p.category, p.category_source = slug, "learned"
            continue
        if p.category and p.category_source in ("document", "ai") and fits_direction(p.category, p.amount, allowed):
            continue
        slug = keyword_category(p.description, p.amount)
        if slug and slug in allowed and fits_direction(slug, p.amount, allowed):
            p.category, p.category_source = slug, "keyword"
            continue
        slug = bank_category(p.hint) if p.hint else None
        if slug and slug in allowed and fits_direction(slug, p.amount, allowed):
            p.category, p.category_source = slug, "bank"
            continue
        p.category = None
        pending.setdefault((p.merchant_key or p.description[:40], p.amount > 0), []).append(p)

    if not pending:
        return
    groups = list(pending.items())
    answers: dict[int, tuple[str, float]] = {}
    to_ask = []
    for i, ((key, is_in), ps) in enumerate(groups):
        hit = cache.get(f"{key}|{'in' if is_in else 'out'}")
        if hit:
            answers[i] = (hit[0], hit[1])
        else:
            amt = int(median(abs(p.amount) for p in ps)) * (1 if is_in else -1)
            to_ask.append({"i": i, "description": ps[0].description[:120], "amount": amt, "hint": ps[0].hint})
    if to_ask and ctx.ai_ok:
        ctx.stage(f"Asking the local AI to categorize {len(to_ask)} merchant(s)")
        got = ctx.ask(ai_tools.categorize, to_ask, allowed, what="categorize transactions") or {}
        for i, (slug, conf) in got.items():
            answers[i] = (slug, conf)
            key, is_in = groups[i][0]
            cache[f"{key}|{'in' if is_in else 'out'}"] = [slug, conf]
    elif to_ask:
        ctx.warn(f"{sum(len(groups[t['i']][1]) for t in to_ask)} transaction(s) have no category because the local "
                 "AI is unavailable; pick them below or re-read the file once it's running.")
    for i, (_, ps) in enumerate(groups):
        ans = answers.get(i)
        for p in ps:
            if ans and fits_direction(ans[0], p.amount, allowed):
                p.category, p.category_source = ans[0], "ai"
                conf = min(ans[1], 0.9)
                p.confidence = min(p.confidence, max(conf, 0.3))
                if conf < LOW_CONFIDENCE:
                    p.flag("low_confidence")
            else:
                p.flag("uncategorized")
