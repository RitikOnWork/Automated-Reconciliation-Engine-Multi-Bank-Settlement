from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.db.base import Base


class ExceptionQueue(Base):
    __tablename__ = "exceptions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("normalized_transactions.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="OPEN", index=True, nullable=False)  # OPEN, RESOLVED, WAIVED
    error_type = Column(String(50), index=True, nullable=False)              # amount_mismatch, missing_reference, etc.
    resolution_action = Column(String(20), nullable=True)                   # force_matched, written_off
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(50), nullable=True)
    comments = Column(Text, nullable=True)                                  # Justification string

    # Relationships
    transaction = relationship("NormalizedTransaction")
