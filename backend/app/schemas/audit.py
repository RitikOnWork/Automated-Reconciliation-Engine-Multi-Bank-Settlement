from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: int
    action: str
    table_name: Optional[str] = None
    record_id: Optional[int] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    timestamp: datetime
    performed_by: str
    ip_address: Optional[str] = None
    comments: Optional[str] = None
    previous_hash: Optional[str] = None
    hash: Optional[str] = None

    class Config:
        from_attributes = True


class VerificationError(BaseModel):
    record_id: int
    error_type: str
    details: str


class VerificationResultResponse(BaseModel):
    is_valid: bool
    block_count: int
    tampered_record_ids: List[int]
    errors: List[VerificationError]
