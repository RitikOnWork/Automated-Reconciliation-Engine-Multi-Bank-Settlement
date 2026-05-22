from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import relationship
from app.db.base import Base


class RawTransaction(Base):
    __tablename__ = "raw_transactions"

    id = Column(Integer, primary_key=True, index=True)
    bank_config_id = Column(Integer, ForeignKey("bank_configurations.id", ondelete="RESTRICT"), nullable=False)
    filename = Column(String(255), nullable=False)
    raw_payload = Column(JSON, nullable=False)           # JSONB raw statement row/tags
    ingested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    status = Column(String(20), default="STAGED", nullable=False) # STAGED, NORMALIZED, ERROR

    # Relationships
    bank_config = relationship("BankConfiguration", back_populates="raw_transactions")
    normalized_transactions = relationship("NormalizedTransaction", back_populates="raw_transaction")

    __table_args__ = (
        # GIN index for JSONB payload queries is handled natively on postgres.
        # SQLAlchemy supports standard indexes, so we can define standard B-tree index or postgres-specific index
        Index("idx_raw_tx_config", "bank_config_id"),
    )
