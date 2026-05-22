from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, String, Text
from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(50), index=True, nullable=False)        # "STATEMENT_UPLOAD", "EXCEPTION_RESOLVE", etc.
    table_name = Column(String(50), index=True, nullable=True)     # "normalized_transactions", "exceptions", "match_results"
    record_id = Column(Integer, nullable=True)                     # Primary key of changed row
    old_value = Column(Text, nullable=True)                        # JSON snapshot before changes
    new_value = Column(Text, nullable=True)                        # JSON snapshot after changes
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    performed_by = Column(String(50), index=True, nullable=False)   # Username or "system"
    ip_address = Column(String(45), nullable=True)
    comments = Column(Text, nullable=True)
    previous_hash = Column(String(64), nullable=True)
    hash = Column(String(64), nullable=True, unique=True)
