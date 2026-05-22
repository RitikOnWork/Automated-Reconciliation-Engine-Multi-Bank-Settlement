from decimal import Decimal
from typing import List, Tuple
from sqlalchemy.orm import Session
from app.models.transaction import NormalizedTransaction
from app.services.matching.base import BaseMatcher
from app.services.matching.rule_engine import (
    RuleEngine,
    ToleranceRule,
    FXVarianceRule,
    SplitTransactionRule,
    ManyToManySettlementRule
)


class RuleBasedMatcher(BaseMatcher):
    def __init__(self, date_tolerance_days: int = 3, amount_tolerance: float = 1.50):
        self.date_tolerance_days = date_tolerance_days
        self.amount_tolerance = Decimal(str(amount_tolerance))

    def reconcile(
        self, 
        db: Session, 
        bank_txs: List[NormalizedTransaction], 
        ledger_txs: List[NormalizedTransaction]
    ) -> List[Tuple[NormalizedTransaction, NormalizedTransaction, float, str]]:
        """
        Pairs transactions using the advanced RuleEngine suite:
        - Priority 1: Date Offset & Amount Tolerances
        - Priority 2: Cross-Border FX currency rate conversions
        - Priority 3: Split transactions (1:N and N:1 combinations)
        - Priority 4: Many-to-Many aggregate settlement clearing
        """
        # Define and load configured rules in order of priority execution
        rules = [
            ToleranceRule(
                date_tolerance_days=self.date_tolerance_days, 
                amount_tolerance=float(self.amount_tolerance)
            ),
            FXVarianceRule(percentage_tolerance=1.5),
            SplitTransactionRule(
                date_tolerance_days=self.date_tolerance_days, 
                amount_tolerance=0.15
            ),
            ManyToManySettlementRule(
                date_window_days=self.date_tolerance_days + 2, 
                amount_tolerance=0.50
            )
        ]
        
        engine = RuleEngine(rules=rules)
        rule_matches = engine.reconcile(bank_txs, ledger_txs)
        
        # Flatten rule-based multi-matches (Splits, M:N) into list of 1:1 pairings
        flat_pairs = []
        for m in rule_matches:
            for b_tx in m.bank_transactions:
                for l_tx in m.ledger_transactions:
                    flat_pairs.append((b_tx, l_tx, m.similarity_score, f"{m.rule_name}: {m.match_details}"))
                    
        return flat_pairs

