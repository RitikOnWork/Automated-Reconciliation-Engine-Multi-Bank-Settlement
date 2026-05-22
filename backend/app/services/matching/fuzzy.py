from typing import List, Tuple
from sqlalchemy.orm import Session
from app.models.transaction import NormalizedTransaction
from app.services.matching.base import BaseMatcher
from app.services.matching.fuzzy_match import FuzzyMatchEngine


class FuzzyMatcher(BaseMatcher):
    def __init__(self, threshold: float = 80.0):
        self.threshold = threshold

    def reconcile(
        self, 
        db: Session, 
        bank_txs: List[NormalizedTransaction], 
        ledger_txs: List[NormalizedTransaction]
    ) -> List[Tuple[NormalizedTransaction, NormalizedTransaction, float, str]]:
        """
        Pairs transactions using advanced fuzzy description scoring from FuzzyMatchEngine.
        Combines Levenshtein, Jaro-Winkler, and Token Set Ratio.
        Enforces candidate ranking and prevents duplicate match bookings.
        """
        engine = FuzzyMatchEngine(threshold=self.threshold)
        pairs = engine.reconcile(bank_txs, ledger_txs)
        
        # Convert to BaseMatcher format: [(bank_tx, ledger_tx, score, rule)]
        return [
            (p.bank_transaction, p.ledger_transaction, p.confidence_score, p.rule_applied)
            for p in pairs
        ]

