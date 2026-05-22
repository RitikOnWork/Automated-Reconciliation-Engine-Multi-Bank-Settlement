from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.schemas.transaction import TransactionResponse


class ExceptionResolve(BaseModel):
    action: str = Field(..., description="force_matched, written_off, adjusted")
    comments: str = Field(..., min_length=5, description="Written justification for override")
    matched_transaction_id: Optional[int] = Field(None, description="The ID to pair with (if force_matched)")


class ExceptionResponse(BaseModel):
    id: int
    transaction_id: int
    status: str
    error_type: str
    resolution_action: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    comments: Optional[str] = None
    transaction: TransactionResponse

    class Config:
        from_attributes = True
