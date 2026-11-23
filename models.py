from datetime import datetime
from sqlalchemy import JSON, Boolean, Integer, String, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def generate_id():
    """Generate a nanoid-like ID."""
    from nanoid import generate
    return generate()


def get_iso_date():
    """Return current date as ISO string."""
    return datetime.utcnow().date().isoformat()


def get_iso_datetime():
    """Return current datetime as ISO string."""
    return datetime.utcnow().isoformat()


class Settings(db.Model):
    """Single-row app configuration."""

    __tablename__ = "settings"

    id = db.Column(Integer, primary_key=True, default=1)
    currency = db.Column(String(3), nullable=False, default="USD")
    locale = db.Column(String(10), nullable=False, default="en-US")
    fiscal_year_start_month = db.Column(Integer, nullable=False, default=1)
    default_withholding_rate = db.Column(Integer, nullable=False, default=2200)
    divergence_thresholds = db.Column(JSON, nullable=False, default=lambda: {})
    schema_version = db.Column(Integer, nullable=False, default=1)


class Category(db.Model):
    """User-defined income/expense categories."""

    __tablename__ = "categories"

    slug = db.Column(String(50), primary_key=True)
    label = db.Column(String(100), nullable=False)
    type = db.Column(String(20), nullable=False)  # 'income' | 'expense' | 'both'
    color = db.Column(String(7), nullable=False)  # hex color

    # Relationships
    one_time_txns = relationship("OneTimeTxn", backref="category_obj")
    recurring_txns = relationship("RecurringTxn", backref="category_obj")
    blanket_expenses = relationship("BlanketExpense", backref="category_obj")


class Account(db.Model):
    """Bank, brokerage, retirement, or property account."""

    __tablename__ = "accounts"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    name = db.Column(String(100), nullable=False)
    type = db.Column(String(30), nullable=False)  # checking, savings, brokerage, retirement_401k, etc.
    institution = db.Column(String(100), nullable=False)
    currency = db.Column(String(3), nullable=False, default="USD")
    current_balance = db.Column(Integer, nullable=False, default=0)
    last_updated_date = db.Column(String(10), nullable=False, default=get_iso_date)
    linked_loan_id = db.Column(String(21), ForeignKey("loans.id"), nullable=True)
    is_active = db.Column(Boolean, nullable=False, default=True)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)

    # Relationships
    one_time_txns = relationship("OneTimeTxn", backref="account")
    recurring_txns = relationship("RecurringTxn", backref="account")
    snapshots = relationship("AccountSnapshot", backref="account", cascade="all, delete-orphan")
    rsu_grants = relationship("RSUGrant", backref="account")
    espp_plans = relationship("ESPPPlan", backref="account")
    linked_loan = relationship("Loan", foreign_keys=[linked_loan_id])


class Loan(db.Model):
    """Mortgage, auto, student, personal, or HELOC liability."""

    __tablename__ = "loans"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    name = db.Column(String(100), nullable=False)
    type = db.Column(String(30), nullable=False)  # mortgage, auto, student, personal, heloc, other
    institution = db.Column(String(100), nullable=False)
    original_balance = db.Column(Integer, nullable=False)
    current_balance = db.Column(Integer, nullable=False)
    interest_rate = db.Column(Integer, nullable=False)  # annual rate × 10000
    monthly_payment = db.Column(Integer, nullable=False)
    start_date = db.Column(String(10), nullable=False)
    payoff_date = db.Column(String(10), nullable=False)
    last_updated_date = db.Column(String(10), nullable=False, default=get_iso_date)
    linked_account_id = db.Column(String(21), ForeignKey("accounts.id"), nullable=True)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)

    # Relationships
    linked_account = relationship("Account", foreign_keys=[linked_account_id])


class OneTimeTxn(db.Model):
    """Single past or future income/expense."""

    __tablename__ = "one_time_txns"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    type = db.Column(String(10), nullable=False)  # 'income' | 'expense'
    amount = db.Column(Integer, nullable=False)
    date = db.Column(String(10), nullable=False)
    category = db.Column(String(50), ForeignKey("categories.slug"), nullable=False)
    account_id = db.Column(String(21), ForeignKey("accounts.id"), nullable=False)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)


class RecurringTxn(db.Model):
    """Repeating income/expense at fixed cadence."""

    __tablename__ = "recurring_txns"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    type = db.Column(String(10), nullable=False)  # 'income' | 'expense'
    amount = db.Column(Integer, nullable=False)
    frequency = db.Column(String(20), nullable=False)  # daily, weekly, biweekly, monthly, quarterly, annually
    start_date = db.Column(String(10), nullable=False)
    end_date = db.Column(String(10), nullable=True)
    category = db.Column(String(50), ForeignKey("categories.slug"), nullable=False)
    account_id = db.Column(String(21), ForeignKey("accounts.id"), nullable=False)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)


class BlanketExpense(db.Model):
    """Catch-all monthly/weekly spending bucket."""

    __tablename__ = "blanket_expenses"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    label = db.Column(String(100), nullable=False)
    amount = db.Column(Integer, nullable=False)
    frequency = db.Column(String(20), nullable=False)  # monthly, weekly, etc.
    start_date = db.Column(String(10), nullable=False)
    end_date = db.Column(String(10), nullable=True)
    category = db.Column(String(50), ForeignKey("categories.slug"), nullable=False)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)


class RSUGrant(db.Model):
    """Equity grant with vesting schedule."""

    __tablename__ = "rsu_grants"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    label = db.Column(String(100), nullable=False)
    grant_date = db.Column(String(10), nullable=False)
    total_shares = db.Column(Integer, nullable=False)
    ticker = db.Column(String(10), nullable=False)
    price_at_grant = db.Column(Integer, nullable=True)
    vest_schedule = db.Column(JSON, nullable=False)
    withholding_rate = db.Column(Integer, nullable=False)
    account_id = db.Column(String(21), ForeignKey("accounts.id"), nullable=False)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)


class ESPPPlan(db.Model):
    """ESPP offering period with contribution and purchase details."""

    __tablename__ = "espp_plans"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    label = db.Column(String(100), nullable=False)
    offering_start_date = db.Column(String(10), nullable=False)
    offering_end_date = db.Column(String(10), nullable=False)
    contribution_mode = db.Column(String(20), nullable=False)  # 'percent' | 'fixed'
    contribution_value = db.Column(Integer, nullable=False)
    base_salary = db.Column(Integer, nullable=True)
    discount_rate = db.Column(Integer, nullable=False, default=1500)
    has_lookback = db.Column(Boolean, nullable=False, default=True)
    purchase_periods = db.Column(JSON, nullable=False)
    account_id = db.Column(String(21), ForeignKey("accounts.id"), nullable=False)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)


class AccountSnapshot(db.Model):
    """Reconciliation history per account."""

    __tablename__ = "account_snapshots"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    account_id = db.Column(String(21), ForeignKey("accounts.id"), nullable=False)
    date = db.Column(String(10), nullable=False)
    actual_balance = db.Column(Integer, nullable=False)
    predicted_balance = db.Column(Integer, nullable=False)
    delta = db.Column(Integer, nullable=False)
    resolution = db.Column(String(20), nullable=False)  # 'accepted' | 'adjusted' | 'ignored'
    adjustment_transaction_id = db.Column(String(21), ForeignKey("one_time_txns.id"), nullable=True)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)


class Asset(db.Model):
    """Unified non-cash asset tracking."""

    __tablename__ = "assets"

    # category values:
    # stock | etf | bond | treasury | reit | private_equity
    # property | vehicle | crypto | collectible | art | other

    id = db.Column(String(21), primary_key=True, default=generate_id)
    name = db.Column(String(100), nullable=False)
    category = db.Column(String(30), nullable=False)
    ticker = db.Column(String(20), nullable=True)       # for stocks / ETFs / REITs
    quantity = db.Column(Float, nullable=True)           # shares or units
    current_value = db.Column(Integer, nullable=False)   # cents (total portfolio value)
    cost_basis = db.Column(Integer, nullable=True)       # cents (total acquisition cost)
    acquired_date = db.Column(String(10), nullable=True)
    address = db.Column(Text, nullable=True)             # for property
    linked_loan_id = db.Column(String(21), ForeignKey("loans.id"), nullable=True)
    last_updated_date = db.Column(String(10), nullable=False, default=get_iso_date)
    # JSON list of scheduled future events:
    # [{id, date, type: acquire|dispose, value, funding: cash|liability|free, linked_loan_id, note}]
    scheduled_events = db.Column(JSON, nullable=False, default=list)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)

    linked_loan = relationship("Loan", foreign_keys=[linked_loan_id])


class RealEstate(db.Model):
    """Real estate property tracking."""

    __tablename__ = "real_estate"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    name = db.Column(String(100), nullable=False)
    address = db.Column(Text, nullable=True)
    purchase_price = db.Column(Integer, nullable=False)
    current_value = db.Column(Integer, nullable=False)
    purchase_date = db.Column(String(10), nullable=False)
    linked_loan_id = db.Column(String(21), ForeignKey("loans.id"), nullable=True)
    last_updated_date = db.Column(String(10), nullable=False, default=get_iso_date)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)

    linked_loan = relationship("Loan", foreign_keys=[linked_loan_id])


class OtherAsset(db.Model):
    """General alternative assets (vehicles, crypto, collectibles, etc.)."""

    __tablename__ = "other_assets"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    name = db.Column(String(100), nullable=False)
    type = db.Column(String(30), nullable=False)  # vehicle, crypto, collectible, art, other
    purchase_price = db.Column(Integer, nullable=True)
    current_value = db.Column(Integer, nullable=False)
    purchase_date = db.Column(String(10), nullable=True)
    last_updated_date = db.Column(String(10), nullable=False, default=get_iso_date)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)


# ── New simplified schema (v2) ─────────────────────────────────────────────────

class Snapshot(db.Model):
    """Actual recorded value for any tracked entity at a specific date."""

    __tablename__ = "snapshots"

    # entity_type: 'cash' | 'asset' | 'liability'
    id = db.Column(String(21), primary_key=True, default=generate_id)
    entity_type = db.Column(String(20), nullable=False)
    entity_id = db.Column(String(21), nullable=False)
    date = db.Column(String(10), nullable=False)
    value = db.Column(Integer, nullable=False)   # cents, always positive
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)


class Rule(db.Model):
    """Recurring or scheduled pattern that generates projected cash-flow events.

    rule_type values:
      income   – salary, dividend, rental, interest, other income
      expense  – recurring bill, subscription, insurance, etc.
      rsu      – RSU grant (vest schedule stored in `schedule`)
      espp     – ESPP plan (purchase periods stored in `schedule`)
    """

    __tablename__ = "rules"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    name = db.Column(String(100), nullable=False)
    rule_type = db.Column(String(20), nullable=False)

    # Target entity (which account receives / pays for this rule)
    account_id = db.Column(String(21), ForeignKey("accounts.id"), nullable=True)

    # For simple recurring rules
    amount = db.Column(Integer, nullable=True)           # cents per period
    frequency = db.Column(String(20), nullable=True)     # monthly|biweekly|weekly|quarterly|annually

    start_date = db.Column(String(10), nullable=False)
    end_date = db.Column(String(10), nullable=True)
    category = db.Column(String(50), nullable=True)

    # Complex event-based schedule (RSU vest events / ESPP purchase periods)
    # RSU:  [{date, shares}]   shares in milliShares (×1000)
    # ESPP: [{start_date, end_date, estimated_purchase_amount}]
    schedule = db.Column(JSON, nullable=True)

    # Type-specific config parameters
    # RSU:  {ticker, total_shares, price_at_grant, withholding_rate,
    #        cliff_months, cliff_percent, subsequent_frequency, subsequent_percent}
    # ESPP: {offering_start_date, offering_end_date, contribution_mode,
    #        contribution_value, base_salary, discount_rate, has_lookback}
    config = db.Column(JSON, nullable=True)

    is_active = db.Column(Boolean, nullable=False, default=True)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)

    linked_account = relationship("Account", foreign_keys=[account_id])


class ChangeEvent(db.Model):
    """Manually entered one-time cash-flow event (income, expense, or adjustment).

    amount is signed: positive = net-worth gain, negative = net-worth loss.
    change_type: 'manual' (user-entered) | 'adjustment' (reconciliation entry).
    """

    __tablename__ = "change_events"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    date = db.Column(String(10), nullable=False)
    description = db.Column(String(200), nullable=False)
    amount = db.Column(Integer, nullable=False)          # cents, signed
    account_id = db.Column(String(21), ForeignKey("accounts.id"), nullable=True)
    category = db.Column(String(50), nullable=True)
    change_type = db.Column(String(20), nullable=False, default="manual")
    # For adjustments: optional link to the snapshot that revealed the discrepancy
    snapshot_id = db.Column(String(21), ForeignKey("snapshots.id"), nullable=True)
    note = db.Column(Text, nullable=True)
    created_at = db.Column(String(10), nullable=False, default=get_iso_date)
    updated_at = db.Column(String(10), nullable=False, default=get_iso_date, onupdate=get_iso_date)


# ── File import (staging area for dropped statements, receipts, pay stubs) ─────
#
# Nothing an import reads goes straight into the ledger. Every file becomes an
# ImportBatch with one ImportRow per proposed record; the user reviews them and a
# commit writes ChangeEvents / Snapshots / Rules. Undo deletes what a commit made.

class ImportBatch(db.Model):
    """One dropped file and what the importer made of it."""

    __tablename__ = "import_batches"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    filename = db.Column(String(255), nullable=False)
    file_kind = db.Column(String(20), nullable=False)       # csv | xlsx | ofx | pdf | text | image | json
    file_sha256 = db.Column(String(64), nullable=False)
    file_size = db.Column(Integer, nullable=False, default=0)
    stored_path = db.Column(Text, nullable=True)            # copy of the file under instance/imports/
    doc_type = db.Column(String(20), nullable=True)         # statement | receipt | payslip | unknown
    doc_type_forced = db.Column(Boolean, nullable=False, default=False)
    account_id = db.Column(String(21), ForeignKey("accounts.id"), nullable=True)
    # processing | review | committed | failed
    status = db.Column(String(20), nullable=False, default="processing")
    stage = db.Column(String(200), nullable=True)           # progress text while processing
    mapping = db.Column(JSON, nullable=True)                # how a table's columns were read
    extracted = db.Column(JSON, nullable=True)              # receipt / pay stub fields and their checks
    warnings = db.Column(JSON, nullable=False, default=list)  # [{level: info|warn, text}]
    ai_usage = db.Column(JSON, nullable=False, default=dict)
    error = db.Column(Text, nullable=True)
    created = db.Column(JSON, nullable=True)                # ids written by the last commit
    created_at = db.Column(String(32), nullable=False, default=get_iso_datetime)
    updated_at = db.Column(String(32), nullable=False, default=get_iso_datetime, onupdate=get_iso_datetime)
    committed_at = db.Column(String(32), nullable=True)

    rows = relationship(
        "ImportRow", backref="batch", cascade="all, delete-orphan", order_by="ImportRow.position"
    )


class ImportRow(db.Model):
    """One proposed record from an import, waiting for review.

    target: change_event (amount signed, + = money in) | snapshot (amount = balance)
            | rule (amount signed per period, frequency set)
    """

    __tablename__ = "import_rows"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    batch_id = db.Column(String(21), ForeignKey("import_batches.id"), nullable=False, index=True)
    position = db.Column(Integer, nullable=False, default=0)
    target = db.Column(String(20), nullable=False, default="change_event")
    action = db.Column(String(10), nullable=False, default="import")   # import | skip
    date = db.Column(String(10), nullable=True)
    description = db.Column(String(200), nullable=False, default="")
    amount = db.Column(Integer, nullable=True)
    category = db.Column(String(50), nullable=True)
    category_source = db.Column(String(20), nullable=True)  # learned | keyword | bank | ai | document | user
    account_id = db.Column(String(21), nullable=True)       # overrides the batch account (pay stub 401k rows)
    frequency = db.Column(String(20), nullable=True)
    confidence = db.Column(Float, nullable=False, default=1.0)
    flags = db.Column(JSON, nullable=False, default=list)
    match = db.Column(JSON, nullable=True)                  # the existing entry a duplicate flag points at
    merchant_key = db.Column(String(100), nullable=True)
    fingerprint = db.Column(String(64), nullable=True, index=True)
    external_id = db.Column(String(100), nullable=True)     # OFX FITID
    note = db.Column(Text, nullable=True)
    raw = db.Column(JSON, nullable=True)                    # source cells or line, for audit
    user_edited = db.Column(Boolean, nullable=False, default=False)
    created_id = db.Column(String(21), nullable=True)       # id of the record a commit wrote


class ImportMerchantRule(db.Model):
    """Category the user chose for a merchant; applied before any AI guess."""

    __tablename__ = "import_merchant_rules"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    merchant_key = db.Column(String(100), nullable=False, unique=True)
    category = db.Column(String(50), nullable=False)
    hits = db.Column(Integer, nullable=False, default=0)
    created_at = db.Column(String(32), nullable=False, default=get_iso_datetime)
    updated_at = db.Column(String(32), nullable=False, default=get_iso_datetime, onupdate=get_iso_datetime)


class ImportProfile(db.Model):
    """Column layout of a bank export seen before, keyed by its header row."""

    __tablename__ = "import_profiles"

    id = db.Column(String(21), primary_key=True, default=generate_id)
    signature = db.Column(String(64), nullable=False, unique=True)
    headers = db.Column(JSON, nullable=False)
    mapping = db.Column(JSON, nullable=False)
    account_id = db.Column(String(21), nullable=True)
    uses = db.Column(Integer, nullable=False, default=0)
    created_at = db.Column(String(32), nullable=False, default=get_iso_datetime)
    updated_at = db.Column(String(32), nullable=False, default=get_iso_datetime, onupdate=get_iso_datetime)
