import logging
from typing import Dict, List
from sqlalchemy.orm import Session
from app.models.transaction import NormalizedTransaction
from app.models.bank_config import BankConfiguration
from app.services.normalizer import TransformationPipeline

logger = logging.getLogger(__name__)


class NormalizationService:
    @staticmethod
    def normalize_and_store(
        db: Session, 
        parsed_records: List[Dict], 
        source_system: str
    ) -> List[NormalizedTransaction]:
        """
        Takes raw dictionary outputs from parsers, normalizes and validates them against 
        the canonical transaction schema, maps them to standard SQLAlchemy 
        NormalizedTransaction objects, detects and skips pre-existing duplicates, 
        and commits them to PostgreSQL.
        """
        stored_transactions = []
        
        for record in parsed_records:
            try:
                # 1. Transform and validate raw record using the Canonical Transformation Pipeline
                canonical_tx = TransformationPipeline.process_record(record, source_system)
            except Exception as e:
                # Isolate, log, and recover from validation/normalization failures per record
                logger.error(f"Failed to normalize raw record: {record}. Error: {str(e)}")
                continue

            # 2. Resolve or dynamically auto-create BankConfiguration based on parsed bank account
            account_no = canonical_tx.bank_account
            bank_cfg = db.query(BankConfiguration).filter(
                BankConfiguration.account_number == account_no
            ).first()
            
            if not bank_cfg:
                # Dynamically create configuration to avoid foreign key restrict crashes
                bank_cfg = BankConfiguration(
                    bank_name="Auto-Registered Bank",
                    account_number=account_no,
                    statement_format="csv" if "csv" in source_system else "mt940",
                    is_active=True
                )
                db.add(bank_cfg)
                db.commit()
                db.refresh(bank_cfg)

            # 3. Detect duplicate transactions using a composite unique-check logic
            # (Checking for matching account, date, amount, reference, and source_system)
            reference = canonical_tx.reference
            amount = canonical_tx.amount
            
            exists = db.query(NormalizedTransaction).filter(
                NormalizedTransaction.bank_account == account_no,
                NormalizedTransaction.transaction_date == canonical_tx.transaction_date,
                NormalizedTransaction.amount == amount,
                # Safe comparison on normalized/cleaned reference (empty string vs None)
                NormalizedTransaction.reference == reference,
                NormalizedTransaction.source_system == source_system
            ).first()
            
            if exists:
                # Skip duplicate
                continue
                
            tx = NormalizedTransaction(
                bank_config_id=bank_cfg.id,
                source_system=source_system,
                transaction_date=canonical_tx.transaction_date,
                value_date=canonical_tx.value_date,
                amount=amount,
                currency=canonical_tx.currency,
                reference=reference,
                description=canonical_tx.description,
                bank_account=account_no,
                status="UNMATCHED"
            )
            db.add(tx)
            stored_transactions.append(tx)
            
        if stored_transactions:
            db.commit()
            for tx in stored_transactions:
                db.refresh(tx)
                
        return stored_transactions


