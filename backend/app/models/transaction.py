from sqlalchemy import Column, Date, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import relationship
from app.db.base import Base


class NormalizedTransaction(Base):
    __tablename__ = "normalized_transactions"

    id = Column(Integer, primary_key=True, index=True)
    raw_tx_id = Column(Integer, ForeignKey("raw_transactions.id", ondelete="SET NULL"), nullable=True)
    bank_config_id = Column(Integer, ForeignKey("bank_configurations.id", ondelete="RESTRICT"), nullable=False)
    source_system = Column(String(20), index=True, nullable=False)  # "bank_statement" or "internal_ledger"
    transaction_date = Column(Date, index=True, nullable=False)
    value_date = Column(Date, nullable=True)
    amount = Column(Numeric(15, 2), index=True, nullable=False)     # Precision currency mapping
    currency = Column(String(3), default="USD", nullable=False)
    reference = Column(String(255), index=True, nullable=True)
    description = Column(Text, nullable=True)
    bank_account = Column(String(50), index=True, nullable=False)
    status = Column(String(20), default="UNMATCHED", index=True, nullable=False)  # UNMATCHED, MATCHED, EXCEPTION
    match_id = Column(Integer, ForeignKey("match_results.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    raw_transaction = relationship("RawTransaction", back_populates="normalized_transactions")
    bank_config = relationship("BankConfiguration", back_populates="normalized_transactions")
    match = relationship("MatchResult", back_populates="transactions")

    __table_args__ = (
        # Optimized B-Tree composite index for reconciliation search cascades
        Index(
            "idx_norm_tx_recon_matching",
            "bank_account", "currency", text("abs(amount)"), "status", "transaction_date"
        ),
        # Case-insensitive alphanumeric index for fast reference checks
        Index(
            "idx_norm_tx_upper_reference",
            text("upper(reference)"),
            postgresql_where=text("reference IS NOT NULL")
        ),
    )
