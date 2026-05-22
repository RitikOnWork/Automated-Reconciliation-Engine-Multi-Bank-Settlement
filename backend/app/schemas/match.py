from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from app.schemas.transaction import TransactionResponse


class MatchCreate(BaseModel):
    match_type: str  # exact, fuzzy, rule_based, manual
    matching_rules_applied: Optional[str] = None
    similarity_score: float = 100.0
    resolved_by: Optional[str] = None


class MatchResponse(BaseModel):
    id: int
    match_type: str
    matched_at: datetime
    matching_rules_applied: Optional[str] = None
    similarity_score: float
    resolved_by: Optional[str] = None
    transactions: List[TransactionResponse] = []

    class Config:
        from_attributes = True
