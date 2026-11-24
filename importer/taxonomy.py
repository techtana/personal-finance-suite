"""Categories the importer may assign, and keyword rules that need no AI.

The allowed set is the user's own categories (Settings -> Categories) plus this
starter set. The AI must pick from that list (the JSON schema enforces it), and
a commit creates any starter category that is used but not yet in the table.
"""

from __future__ import annotations

import re

# slug, label, type (income | expense | both), colour
STARTER_CATEGORIES = [
    ("salary", "Salary", "income", "#10b981"),
    ("bonus", "Bonus", "income", "#06b6d4"),
    ("interest", "Interest & dividends", "income", "#14b8a6"),
    ("refund", "Refunds", "income", "#22c55e"),
    ("other_income", "Other income", "income", "#84cc16"),
    ("groceries", "Groceries", "expense", "#f97316"),
    ("dining", "Dining & coffee", "expense", "#fb923c"),
    ("transport", "Transport & fuel", "expense", "#3b82f6"),
    ("utilities", "Utilities & phone", "expense", "#f59e0b"),
    ("rent", "Rent", "expense", "#ef4444"),
    ("housing", "Home & maintenance", "expense", "#b91c1c"),
    ("insurance", "Insurance", "expense", "#a855f7"),
    ("health", "Health", "expense", "#ec4899"),
    ("shopping", "Shopping", "expense", "#8b5cf6"),
    ("subscriptions", "Subscriptions", "expense", "#6366f1"),
    ("entertainment", "Entertainment", "expense", "#d946ef"),
    ("travel", "Travel", "expense", "#0ea5e9"),
    ("education", "Education", "expense", "#0891b2"),
    ("gifts", "Gifts & donations", "expense", "#f43f5e"),
    ("fees", "Bank fees", "expense", "#64748b"),
    ("taxes", "Taxes", "expense", "#475569"),
    ("debt", "Debt payments", "expense", "#dc2626"),
    ("misc", "Misc", "expense", "#6b7280"),
    ("transfer", "Transfer between accounts", "both", "#94a3b8"),
    ("investment", "Savings & investing", "both", "#7c3aed"),
]

# Rules checked in order; first match wins. direction: "in", "out" or None (either).
_KEYWORDS: list[tuple[str, str | None, str]] = [
    ("transfer", None, r"\b(?:online |mobile |internal |bank )?(?:transfer|xfer|trnsfr)\b(?! fee)"),
    ("transfer", None, r"\bpayment,? thank you\b|\bautopay(?:ment)?\b|\bauto ?pay\b|\bcard ?payment\b|"
                       r"\bcredit card (?:payment|pmt)\b|\b(?:chase|amex|citi|discover|capital one|card) (?:e-?payment|epay|pmt)\b"),
    ("salary", "in", r"\bpayroll\b|\bdir(?:ect)? ?dep(?:osit)?\b|\bsalary\b|\bwages\b|\b(?:adp|gusto|paychex) "),
    ("interest", "in", r"\binterest (?:paid|payment|credit|earned)\b|\bint(?:erest)? earned\b|\bdividend\b|\bdiv(?:idend)? reinv"),
    ("refund", "in", r"\brefund\b|\breturn(?:ed)? (?:credit|item)\b|\breversal\b|\bcash ?back\b|\bchargeback\b"),
    ("other_income", "in", r"\b(?:mobile|remote|atm|branch|check|cash) deposit\b|\bdeposit\b"),
    ("fees", "out", r"\b(?:overdraft|nsf|atm|monthly service|maintenance|foreign transaction|wire|late) fee\b|\bservice charge\b"),
    ("taxes", "out", r"\birs\b|\busataxpymt\b|\btax payment\b|\bfranchise tax\b|\bdept of revenue\b"),
    ("debt", "out", r"\bmortgage\b|\bloan (?:pmt|payment)\b|\bstudent loan\b|\bnavient\b|\bnelnet\b|\bmohela\b"),
    ("rent", "out", r"\brent\b|\bapartments?\b|\bproperty management\b|\bleasing office\b"),
    ("groceries", "out", r"\bwhole foods\b|\bsafeway\b|\bkroger\b|\btrader joe|\baldi\b|\bqfc\b|\bpublix\b|\bwegmans\b|"
                         r"\bsprouts\b|\binstacart\b|\bfred meyer\b|\bh-e-b\b|\bgrocery\b|\bgroceries\b|\bsupermarket\b|\bpcc\b"),
    ("dining", "out", r"\bstarbucks\b|\bmcdonald|\bchipotle\b|\bdoordash\b|\buber ?eats\b|\bgrubhub\b|\brestaurant\b|"
                      r"\bcafe\b|\bcoffee\b|\bpizza\b|\bbakery\b|\bbistro\b|\bdiner\b|\bsubway\b|\btaco\b|\bsushi\b|\bburger"),
    ("transport", "out", r"\buber\b(?! ?eats)|\blyft\b|\bshell\b|\bchevron\b|\bexxon|\bmobil\b|\barco\b|\bvalero\b|\bfuel\b|"
                         r"\bgas station\b|\bparking\b|\bpark ?mobile\b|\btoll\b|\btransit\b|\bmetro\b|\borca\b|\bclipper\b|\bamtrak\b"),
    ("utilities", "out", r"\benergy\b|\belectric\b|\bpg&e\b|\bcomcast\b|\bxfinity\b|\bverizon\b|\bat&t\b|\bt-mobile\b|"
                         r"\bwater\b|\bsewer\b|\binternet\b|\butilit(?:y|ies)\b|\bpuget sound\b|\bcon ?ed\b|\bspectrum\b"),
    ("subscriptions", "out", r"\bnetflix\b|\bspotify\b|\bhulu\b|\bdisney ?\+|\bdisney plus\b|\bapple\.com/bill\b|\byoutube\b|"
                             r"\bpatreon\b|\badobe\b|\bicloud\b|\bdropbox\b|\bprime video\b|\bhbo ?max\b|\baudible\b|\bsubscription\b"),
    ("insurance", "out", r"\binsurance\b|\bgeico\b|\bstate farm\b|\bprogressive\b|\ballstate\b|\blemonade\b"),
    ("health", "out", r"\bpharmacy\b|\bcvs\b|\bwalgreens\b|\bdental\b|\bdentist\b|\bclinic\b|\bhospital\b|\bmedical\b|\boptometr"),
    ("travel", "out", r"\bairlines?\b|\bdelta air\b|\bunited air\b|\balaska air\b|\bsouthwest\b|\bhotel\b|\bmarriott\b|\bhilton\b|"
                      r"\bairbnb\b|\bexpedia\b|\bbooking\.com\b"),
    ("entertainment", "out", r"\bcinema\b|\bamc theat|\bsteam games\b|\bsteampowered\b|\bticketmaster\b|\bplaystation\b|\bnintendo\b"),
    ("shopping", "out", r"\bamazon\b|\bamzn\b|\btarget\b|\bwalmart\b|\bbest buy\b|\bikea\b|\bebay\b|\bcostco\b|\bhome depot\b|\blowe'?s\b"),
]
_COMPILED = [(cat, direction, re.compile(rx, re.I)) for cat, direction, rx in _KEYWORDS]

# Bank-supplied category names (Capital One, Discover, Chase card exports) -> starter slugs.
_BANK_CATEGORY = [
    (r"grocer|supermarket", "groceries"), (r"dining|restaurant|food & drink|food and drink|coffee", "dining"),
    (r"gas|fuel|auto|transport|travel/ transportation|parking|rideshare", "transport"),
    (r"utilit|phone|internet|cable", "utilities"), (r"travel|airfare|hotel|lodging", "travel"),
    (r"health|medical|pharmacy|doctor", "health"), (r"entertain|recreation", "entertainment"),
    (r"insurance", "insurance"), (r"merchandise|shopping|retail|home improvement", "shopping"),
    (r"fee|interest charge", "fees"), (r"payment|credit|transfer", "transfer"), (r"education", "education"),
    (r"gift|donation|charit", "gifts"), (r"bills|subscription|streaming", "subscriptions"),
]


_PERSON_TO_PERSON = re.compile(r"\b(?:zelle|venmo|cash ?app|paypal|wise)\b", re.I)


def keyword_category(description: str, amount: int | None) -> str | None:
    direction = None if amount is None else ("in" if amount > 0 else "out")
    p2p = bool(_PERSON_TO_PERSON.search(description or ""))
    for cat, want, rx in _COMPILED:
        if want and direction and want != direction:
            continue
        if cat == "transfer" and p2p:  # a Zelle "transfer" is usually a payment to someone else
            continue
        if rx.search(description or ""):
            return cat
    return None


def bank_category(name: str) -> str | None:
    for rx, slug in _BANK_CATEGORY:
        if re.search(rx, name or "", re.I):
            return slug
    return None


def allowed_categories(db_categories) -> dict[str, dict]:
    """slug -> {label, type} from the user's categories merged with the starter set."""
    out = {slug: {"label": label, "type": typ, "color": color} for slug, label, typ, color in STARTER_CATEGORIES}
    for c in db_categories:
        out[c.slug] = {"label": c.label, "type": c.type or "both", "color": c.color}
    return out


def fits_direction(category: str, amount: int | None, allowed: dict) -> bool:
    """Income categories can't be money out. Expense categories may be money in (a refund)."""
    info = allowed.get(category)
    if info is None:
        return False
    if amount is not None and amount < 0 and info["type"] == "income":
        return False
    return True
