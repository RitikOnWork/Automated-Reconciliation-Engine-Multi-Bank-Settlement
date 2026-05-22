from sqlalchemy import Boolean, Column, Integer, JSON, String
from sqlalchemy.orm import relationship
from app.db.base import Base


class BankConfiguration(Base):
    __tablename__ = "bank_configurations"

    id = Column(Integer, primary_key=True, index=True)
    bank_name = Column(String(100), nullable=False)
    account_number = Column(String(50), unique=True, index=True, nullable=False)
    statement_format = Column(String(10), nullable=False)  # "mt940", "camt053", "csv"
    parser_rules = Column(JSON, nullable=True)             # JSON structure mapping aliases
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    raw_transactions = relationship("RawTransaction", back_populates="bank_config")
    normalized_transactions = relationship("NormalizedTransaction", back_populates="bank_config")

