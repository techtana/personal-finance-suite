"""Shared types for the import pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from importer.llm import LLMClient, LLMError, LLMUnavailable


class ImportFailure(Exception):
    """Processing can't continue; the message is shown to the user."""


# Flags that make a row default to "skip" until the user ticks it.
SKIP_FLAGS = {
    "duplicate", "possible_duplicate", "transfer", "unparsed_date", "unparsed_amount", "missing_date",
    "missing_amount", "zero_amount", "pick_account", "suggestion", "older_snapshot", "negative_balance",
    "rule_exists", "card_balance",
}
# Flags that put a row in the "Needs review" filter.
REVIEW_FLAGS = {
    "low_confidence", "uncategorized", "ai_extracted", "doesnt_add_up", "ai_disagrees", "direction_unknown",
    "ambiguous_date", "possible_duplicate", "pick_account", "from_photo", "sign_guessed",
}


@dataclass
class Proposal:
    """A record the importer wants to write, before it becomes an ImportRow."""

    target: str = "change_event"          # change_event | snapshot | rule
    date: str | None = None
    description: str = ""
    amount: int | None = None             # signed cents
    category: str | None = None
    category_source: str | None = None
    account_id: str | None = None         # None = the batch's account
    frequency: str | None = None
    confidence: float = 1.0
    flags: list = field(default_factory=list)
    merchant_key: str | None = None
    external_id: str | None = None
    note: str | None = None
    raw: Any = None
    hint: str | None = None               # bank category or receipt items, for categorizing
    explicit_account: bool = False        # account_id was chosen for this row (pay stub 401k)

    def flag(self, code: str, conf: float | None = None):
        if code not in self.flags:
            self.flags.append(code)
        if conf is not None:
            self.confidence = min(self.confidence, conf)


@dataclass
class Ctx:
    """What a processing run knows: the AI client, the user's locale and accounts, notes for the user."""

    llm: LLMClient
    ai_ok: bool
    prefer_dayfirst: bool = False
    accounts: list = field(default_factory=list)
    account: Any = None
    filename: str = ""
    warnings: list = field(default_factory=list)
    stage: Callable[[str], None] = lambda text: None
    extracted: dict = field(default_factory=dict)
    mapping: dict | None = None
    overrides: dict = field(default_factory=dict)
    suggested_account_id: str | None = None
    ai_reason: str | None = None

    def warn(self, text: str):
        if not any(w["text"] == text for w in self.warnings):
            self.warnings.append({"level": "warn", "text": text})

    def info(self, text: str):
        if not any(w["text"] == text for w in self.warnings):
            self.warnings.append({"level": "info", "text": text})

    def ask(self, fn, *args, what: str = "help", **kwargs):
        """Call an AI tool; on failure note it and return None so rules carry on."""
        if not self.ai_ok:
            self.warn(f"The local AI isn't available ({self.ai_reason or 'turned off'}), so this file was read with "
                      "rules only. Check the rows closely, or re-read once the AI is running.")
            return None
        try:
            return fn(self.llm, *args, **kwargs)
        except LLMUnavailable as e:
            self.ai_ok = False
            self.warn(f"The local AI stopped responding ({e}); the rest of this file used rules only.")
        except LLMError as e:
            self.warn(f"The local AI couldn't {what}: {e}")
        return None
