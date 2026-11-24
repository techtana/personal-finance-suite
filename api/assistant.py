"""The optional AI assistant: ask, natural-language filter, explain, draft.

Uses the same model client as the importer (local by default; LLM_PROVIDER=off
turns all of this off and the rest of the app is unaffected). The model only
chooses lookups and words answers. See engine/assistant.py for the guardrails.
"""

from flask import Blueprint, current_app, jsonify, request

from api import _data
from engine import assistant as A
from importer.llm import LLMError, get_client

bp = Blueprint("api_assistant", __name__)


def _client():
    return get_client(current_app)


def _unavailable(e):
    return jsonify({"error": f"The assistant isn't available: {e}", "unavailable": True}), 503


def _text(key, limit=500):
    return str((request.get_json(silent=True) or {}).get(key) or "").strip()[:limit]


def _context(today: str) -> A.Context:
    from api.overview import collect_insights
    from api.taxes import compute_tax_summary

    snaps = _data.snapshot_history()
    prices = _data.latest_prices(today)
    try:
        tax = compute_tax_summary(int(today[:4]), prices)
    except Exception:
        tax = None
    return A.Context(entities=_data.load_entities(snaps), snaps=snaps, rules=_data.rule_dicts(),
                     changes=_data.change_dicts(), loans=_data.loan_dicts(), prices=prices, today=today,
                     insights=collect_insights(today), tax=tax)


@bp.route("/assistant/status", methods=["GET"])
def status():
    llm = _client()
    s = llm.status()
    return jsonify({"enabled": bool(llm.enabled), "ok": bool(s.get("ok")), "provider": s.get("provider"),
                    "model": s.get("model"), "base_url": s.get("base_url"), "error": s.get("error"),
                    "remote_allowed": bool(current_app.config.get("LLM_ALLOW_REMOTE"))})


@bp.route("/assistant/ask", methods=["POST"])
def ask():
    question = _text("question")
    if not question:
        return jsonify({"error": "question is required"}), 422
    today = _data.today_iso((request.get_json(silent=True) or {}).get("today"))
    llm = _client()
    ctx = _context(today)
    names = ", ".join(e["name"] for e in ctx.entities[:30]) or "none"
    categories = ", ".join(sorted({r.get("category") for r in ctx.rules if r.get("category")})) or "none"
    tools = "\n".join(f"- {name}: {desc}" for name, (_, desc) in A.TOOLS.items())
    system = ("You route a question about the user's personal finances to exactly one lookup. "
              "Reply with JSON: the lookup name and its args. Do not answer the question yourself.\n"
              f"Today is {today}.\nLookups:\n{tools}\n"
              f"Known account, asset and loan names: {names}\nKnown categories: {categories}")
    try:
        choice = llm.chat_json([{"role": "system", "content": system}, {"role": "user", "content": question}],
                               A.ASK_SCHEMA, task="assistant_route")
        result = A.run_tool(ctx, choice)
    except LLMError as e:
        return _unavailable(e)
    except ValueError as e:
        return jsonify({"error": f"I couldn't work out what to look up ({e}). Try rephrasing."}), 422

    facts = A.facts_text(result["facts"])
    answer, worded = facts, False
    try:
        draft = llm.chat_text([
            {"role": "system", "content": "Answer the question in one to three plain sentences using only the facts "
                                          "given. Copy amounts and dates exactly. Do not add, estimate or calculate "
                                          "any number that is not in the facts. Do not give advice. Do not mention "
                                          "\"the facts\" or what is missing; just answer."},
            {"role": "user", "content": f"Question: {question}\n\nFacts:\n{facts}"}], task="assistant_answer")
        if draft and A.numbers_grounded(draft, facts, question, today):
            answer, worded = draft, True
    except LLMError:
        pass
    return jsonify({"answer": answer, "worded_by_ai": worded, "facts": result["facts"], "tool": result["tool"],
                    "args": result["args"], "href": result["href"], "model": getattr(llm, "model", None)})


@bp.route("/assistant/filter", methods=["POST"])
def nl_filter():
    """Words -> the same filter controls the user could set by hand.

    Body: {text, filters: {name: [values on offer]}, sorts: [names]}
    """
    text = _text("text", 200)
    body = request.get_json(silent=True) or {}
    if not text:
        return jsonify({"error": "text is required"}), 422
    filters = {str(k): [str(v) for v in vals][:60] for k, vals in (body.get("filters") or {}).items()
               if isinstance(vals, list) and vals}
    sorts = [str(x) for x in (body.get("sorts") or [])][:20]
    today = _data.today_iso(body.get("today"))
    system = (
        "Turn the request into a filter for a list of money entries. Reply with JSON and fill in every field.\n"
        "- filter_* fields: pick one of the allowed values only if the request clearly means it, otherwise \"\".\n"
        "- date_from / date_to: YYYY-MM-DD when the request names a period, otherwise \"\". "
        "A month means its first and last day; \"next quarter\" means the next three full months.\n"
        "- min_amount_dollars / max_amount_dollars: numbers for \"over\", \"at least\", \"under\", \"up to\", otherwise null.\n"
        "- sort: only if the request asks for an order.\n"
        "- search: leftover words that name a thing (\"gym\", \"rent\"), never numbers or dates, otherwise \"\".\n"
        f"Today is {today}.\n"
        "Example: \"expenses over $1000 in January 2027\" -> filter_type \"expense\" (if offered), "
        "min_amount_dollars 1000, date_from \"2027-01-01\", date_to \"2027-01-31\", search \"\"."
    )
    try:
        raw = _client().chat_json([{"role": "system", "content": system}, {"role": "user", "content": text}],
                                  A.filter_schema(filters, sorts), task="assistant_filter")
    except LLMError as e:
        return _unavailable(e)
    return jsonify({"filter": A.clean_filter(raw, filters, sorts), "text": text})


@bp.route("/assistant/explain", methods=["POST"])
def explain():
    """Plain-language wording of something already on screen. Adds no new numbers."""
    title, detail, basis = _text("title", 300), _text("detail", 1500), _text("basis", 600)
    if not (title or detail):
        return jsonify({"error": "nothing to explain"}), 422
    source = f"{title}\n{detail}\nBased on: {basis}"
    try:
        text = _client().chat_text([
            {"role": "system", "content": "Explain this note from a personal finance app to its owner in two or three "
                                          "plain sentences: what it means and what it is based on. Use only what is "
                                          "given, copy numbers exactly, add no new numbers and give no advice."},
            {"role": "user", "content": source}], task="assistant_explain")
    except LLMError as e:
        return _unavailable(e)
    if not A.numbers_grounded(text, source):
        return jsonify({"explanation": None,
                        "error": "The assistant's wording introduced figures that aren't on this page, so it was discarded."}), 200
    return jsonify({"explanation": text})


@bp.route("/assistant/draft", methods=["POST"])
def draft():
    """A sentence -> a pre-filled Plan form. Nothing is saved; the user reviews and saves."""
    text = _text("text", 300)
    if not text:
        return jsonify({"error": "text is required"}), 422
    today = _data.today_iso((request.get_json(silent=True) or {}).get("today"))
    system = ("Turn the sentence into one planned entry for a personal finance app. Reply with JSON. "
              "kind=rule for something that repeats, kind=change for a single dated event. "
              f"Dates are YYYY-MM-DD. Today is {today}. Copy the amount exactly as written.")
    try:
        raw = _client().chat_json([{"role": "system", "content": system}, {"role": "user", "content": text}],
                                  A.DRAFT_SCHEMA, task="assistant_draft")
    except LLMError as e:
        return _unavailable(e)
    prefill = A.clean_draft(raw, today, text)
    if not prefill:
        return jsonify({"error": "I couldn't turn that into an entry. Include what it is and an amount."}), 422
    return jsonify({"draft": prefill})
