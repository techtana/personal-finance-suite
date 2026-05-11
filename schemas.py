from datetime import date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class CategorySchema(BaseModel):
    slug: str
    label: str
    type: str
    color: str

    class Config:
        from_attributes = True


class AccountSchema(BaseModel):
    id: Optional[str] = None
    name: str
    type: str
    institution: str
    currency: str = "USD"
    current_balance: int
    last_updated_date: str
    linked_loan_id: Optional[str] = None
    is_active: bool = True
    note: Optional[str] = None

    class Config:
        from_attributes = True


class LoanSchema(BaseModel):
    id: Optional[str] = None
    name: str
    type: str
    institution: str
    original_balance: int
    current_balance: int
    interest_rate: int
    monthly_payment: int
    start_date: str
    payoff_date: str
    last_updated_date: str
    linked_account_id: Optional[str] = None
    note: Optional[str] = None

    class Config:
        from_attributes = True


class OneTimeTxnSchema(BaseModel):
    id: Optional[str] = None
    type: str
    amount: int
    date: str
    category: str
    account_id: str
    note: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        if v not in ("income", "expense"):
            raise ValueError("type must be 'income' or 'expense'")
        return v

    class Config:
        from_attributes = True


class RecurringTxnSchema(BaseModel):
    id: Optional[str] = None
    type: str
    amount: int
    frequency: str
    start_date: str
    end_date: Optional[str] = None
    category: str
    account_id: str
    note: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        if v not in ("income", "expense"):
            raise ValueError("type must be 'income' or 'expense'")
        return v

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v):
        valid = ("daily", "weekly", "biweekly", "monthly", "quarterly", "annually")
        if v not in valid:
            raise ValueError(f"frequency must be one of {valid}")
        return v

    class Config:
        from_attributes = True


class BlanketExpenseSchema(BaseModel):
    id: Optional[str] = None
    label: str
    amount: int
    frequency: str
    start_date: str
    end_date: Optional[str] = None
    category: str
    note: Optional[str] = None

    class Config:
        from_attributes = True


class VestEventSchema(BaseModel):
    date: str
    shares: int


class RSUGrantSchema(BaseModel):
    id: Optional[str] = None
    label: str
    grant_date: str
    total_shares: int
    ticker: str
    price_at_grant: Optional[int] = None
    vest_schedule: List[VestEventSchema]
    withholding_rate: int
    account_id: str
    note: Optional[str] = None

    class Config:
        from_attributes = True


class RSUGrantCreateSchema(BaseModel):
    label: str
    grant_date: str
    total_shares: int
    ticker: str
    price_at_grant: Optional[int] = None
    cliff_months: int
    cliff_percent: int
    subsequent_frequency: str
    subsequent_percent: int
    withholding_rate: int
    account_id: str
    note: Optional[str] = None

    @field_validator("subsequent_frequency")
    @classmethod
    def validate_frequency(cls, v):
        if v not in ("monthly", "quarterly"):
            raise ValueError("subsequent_frequency must be 'monthly' or 'quarterly'")
        return v


class PurchasePeriodSchema(BaseModel):
    start_date: str
    end_date: str
    estimated_purchase_amount: Optional[int] = None


class ESPPPlanSchema(BaseModel):
    id: Optional[str] = None
    label: str
    offering_start_date: str
    offering_end_date: str
    contribution_mode: str
    contribution_value: int
    base_salary: Optional[int] = None
    discount_rate: int = 1500
    has_lookback: bool = True
    purchase_periods: List[PurchasePeriodSchema]
    account_id: str
    note: Optional[str] = None

    class Config:
        from_attributes = True


class AccountSnapshotSchema(BaseModel):
    id: Optional[str] = None
    account_id: str
    date: str
    actual_balance: int
    predicted_balance: int
    delta: int
    resolution: str
    adjustment_transaction_id: Optional[str] = None
    note: Optional[str] = None

    class Config:
        from_attributes = True


class SettingsSchema(BaseModel):
    currency: str = "USD"
    locale: str = "en-US"
    fiscal_year_start_month: int = 1
    default_withholding_rate: int = 2200
    divergence_thresholds: Dict[str, int] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class CashFlowEventSchema(BaseModel):
    date: str
    source_id: str
    source_type: str
    type: str
    amount: int
    label: str
    category: str


class MonthlyBucketSchema(BaseModel):
    month: str
    income: int
    expenses: int
    net_cash_flow: int
    cumulative_net_worth: int
    actual_net_worth: Optional[int] = None
    events: List[CashFlowEventSchema] = Field(default_factory=list)


class ProjectionResultSchema(BaseModel):
    buckets: List[MonthlyBucketSchema]
    events: List[CashFlowEventSchema]


class ScheduledEventSchema(BaseModel):
    id: str
    date: str
    type: str               # acquire | dispose
    value: int              # cents
    funding: str = "cash"   # cash | liability | free
    linked_loan_id: Optional[str] = None
    note: Optional[str] = None


class AssetSchema(BaseModel):
    id: Optional[str] = None
    name: str
    category: str
    ticker: Optional[str] = None
    quantity: Optional[float] = None
    current_value: int
    cost_basis: Optional[int] = None
    acquired_date: Optional[str] = None
    address: Optional[str] = None
    linked_loan_id: Optional[str] = None
    last_updated_date: str
    scheduled_events: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None

    class Config:
        from_attributes = True


class RealEstateSchema(BaseModel):
    id: Optional[str] = None
    name: str
    address: Optional[str] = None
    purchase_price: int
    current_value: int
    purchase_date: str
    linked_loan_id: Optional[str] = None
    last_updated_date: str
    note: Optional[str] = None

    class Config:
        from_attributes = True


class OtherAssetSchema(BaseModel):
    id: Optional[str] = None
    name: str
    type: str
    purchase_price: Optional[int] = None
    current_value: int
    purchase_date: Optional[str] = None
    last_updated_date: str
    note: Optional[str] = None

    class Config:
        from_attributes = True


# ── v2 schemas ─────────────────────────────────────────────────────────────────

class SnapshotSchema(BaseModel):
    id: Optional[str] = None
    entity_type: str           # 'cash' | 'asset' | 'liability'
    entity_id: str
    date: str
    value: int                 # cents, always positive
    note: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class RuleSchema(BaseModel):
    id: Optional[str] = None
    name: str
    rule_type: str             # 'income' | 'expense' | 'rsu' | 'espp'
    account_id: Optional[str] = None
    amount: Optional[int] = None
    frequency: Optional[str] = None
    start_date: str
    end_date: Optional[str] = None
    category: Optional[str] = None
    schedule: Optional[List[Dict[str, Any]]] = None
    config: Optional[Dict[str, Any]] = None
    is_active: bool = True
    note: Optional[str] = None

    class Config:
        from_attributes = True


class ChangeEventSchema(BaseModel):
    id: Optional[str] = None
    date: str
    description: str
    amount: int                # cents, signed (+ = gain, - = loss)
    account_id: Optional[str] = None
    category: Optional[str] = None
    change_type: str = "manual"   # 'manual' | 'adjustment'
    snapshot_id: Optional[str] = None
    note: Optional[str] = None

    class Config:
        from_attributes = True
