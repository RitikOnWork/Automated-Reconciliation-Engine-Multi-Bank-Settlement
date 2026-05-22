from pydantic import BaseModel
from typing import Optional

class SecureTransactionResponse(BaseModel):
    id: int
    card_number: str
    bank_account: str
    holder_name: str
    amount: float
    currency: str

class AdminOnlyStatusResponse(BaseModel):
    status: str
    message: str
    caller: str
    role: str
