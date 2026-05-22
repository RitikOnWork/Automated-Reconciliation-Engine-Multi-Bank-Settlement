from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    source_system: str = Field(..., description="bank_statement or internal_ledger")
    transaction_date: date
    value_date: Optional[date] = None
    amount: Decimal = Field(..., description="Transaction Amount (debits are negative)")
    currency: str = Field("USD", max_length=3)
    reference: Optional[str] = None
    description: Optional[str] = None
    bank_account: str


class TransactionResponse(BaseModel):
    id: int
    source_system: str
    transaction_date: date
    value_date: Optional[date] = None
    amount: Decimal
    currency: str
    reference: Optional[str] = None
    description: Optional[str] = None
    bank_account: str
    status: str
    match_id: Optional[int] = None

    class Config:
        from_attributes = True
