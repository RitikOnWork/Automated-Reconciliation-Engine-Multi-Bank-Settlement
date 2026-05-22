from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import relationship
from app.db.base import Base


class MatchResult(Base):
    __tablename__ = "match_results"

    id = Column(Integer, primary_key=True, index=True)
    match_type = Column(String(20), index=True, nullable=False)  # "exact", "fuzzy", "rule_based", "manual"
    matched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    matching_rules_applied = Column(Text, nullable=True)         # JSON list or text checklist
    similarity_score = Column(Float, default=100.0)
    resolved_by = Column(String(50), nullable=True)              # Username of operator

    # Relate back to transactions involved in this match group
    transactions = relationship("NormalizedTransaction", back_populates="match")
