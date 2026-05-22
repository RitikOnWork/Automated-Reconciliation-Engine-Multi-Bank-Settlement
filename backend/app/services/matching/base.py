from abc import ABC, abstractmethod
from typing import List, Tuple
from sqlalchemy.orm import Session
from app.models.match import MatchResult
from app.models.transaction import NormalizedTransaction


class BaseMatcher(ABC):
    @abstractmethod
    def reconcile(
        self, 
        db: Session, 
        bank_txs: List[NormalizedTransaction], 
        ledger_txs: List[NormalizedTransaction]
    ) -> List[Tuple[NormalizedTransaction, NormalizedTransaction, float, str]]:
        """
        Executes matching logic.
        Returns a list of tuples representing paired transactions:
        [
            (bank_transaction, ledger_transaction, similarity_score, rule_applied)
        ]
        """
        pass

