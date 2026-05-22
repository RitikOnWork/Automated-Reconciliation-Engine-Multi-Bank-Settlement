from typing import List, Tuple
from sqlalchemy.orm import Session
from app.models.transaction import NormalizedTransaction
from app.services.matching.base import BaseMatcher
from app.services.matching.exact_match import ExactMatchEngine


class ExactMatcher(BaseMatcher):
    def reconcile(
        self, 
        db: Session, 
        bank_txs: List[NormalizedTransaction], 
        ledger_txs: List[NormalizedTransaction]
    ) -> List[Tuple[NormalizedTransaction, NormalizedTransaction, float, str]]:
        """
        Pairs transactions using the high-performance ExactMatchEngine.
        Matches bank account, currency, transaction date, and transaction reference (as ID).
        Handles duplicate keys using bucket-queue FIFO popping.
        """
        engine = ExactMatchEngine()
        pairs = engine.reconcile(bank_txs, ledger_txs)
        
        # Convert to BaseMatcher output format: [(bank_tx, ledger_tx, score, rule)]
        return [
            (p.bank_transaction, p.ledger_transaction, p.similarity_score, p.rule_applied)
            for p in pairs
        ]
