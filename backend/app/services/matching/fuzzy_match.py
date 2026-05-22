import sys
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
from rapidfuzz.distance import Levenshtein, JaroWinkler
from rapidfuzz import fuzz

@dataclass
class FuzzyMatchPair:
    """Represents a fuzzy matched transaction pair."""
    bank_transaction: Any
    ledger_transaction: Any
    confidence_score: float
    token_set_ratio: float
    jaro_winkler: float
    levenshtein: float
    rule_applied: str
    matched_at: datetime = field(default_factory=lambda: datetime.now())

class FuzzyMatchEngine:
    """
    Advanced Fuzzy Matching Engine utilizing RapidFuzz algorithms.
    Combines Levenshtein Distance, Jaro-Winkler Similarity, and Token Set Ratio
    into a weighted match confidence score, applying strict best-candidate ranking.
    """
    def __init__(
        self,
        threshold: float = 80.0,
        weight_token_set: float = 0.4,
        weight_jaro_winkler: float = 0.4,
        weight_levenshtein: float = 0.2
    ):
        self.threshold = threshold
        self.weight_token_set = weight_token_set
        self.weight_jaro_winkler = weight_jaro_winkler
        self.weight_levenshtein = weight_levenshtein

    def calculate_scores(self, s1: str, s2: str) -> Dict[str, float]:
        """
        Calculates Levenshtein, Jaro-Winkler, and Token Set Ratio similarity scores.
        All scores are normalized to a 0.0 - 100.0 scale.
        """
        s1_clean = str(s1 or "").strip().lower()
        s2_clean = str(s2 or "").strip().lower()

        if not s1_clean or not s2_clean:
            return {
                "token_set_ratio": 0.0,
                "jaro_winkler": 0.0,
                "levenshtein": 0.0,
                "confidence_score": 0.0
            }

        # Calculate raw metrics
        ts_score = float(fuzz.token_set_ratio(s1_clean, s2_clean))
        jw_score = float(JaroWinkler.similarity(s1_clean, s2_clean) * 100.0)
        lv_score = float(Levenshtein.normalized_similarity(s1_clean, s2_clean) * 100.0)

        # Weighted composite score
        confidence = (
            (self.weight_token_set * ts_score) +
            (self.weight_jaro_winkler * jw_score) +
            (self.weight_levenshtein * lv_score)
        )

        return {
            "token_set_ratio": round(ts_score, 2),
            "jaro_winkler": round(jw_score, 2),
            "levenshtein": round(lv_score, 2),
            "confidence_score": round(confidence, 2)
        }

    @staticmethod
    def _get_field(obj: Any, name: str) -> Any:
        """Helper to get a field from a dataclass, SQLAlchemy model, or dictionary."""
        if hasattr(obj, name):
            return getattr(obj, name)
        elif isinstance(obj, dict):
            return obj.get(name)
        return None

    def reconcile(
        self,
        bank_txs: List[Any],
        ledger_txs: List[Any]
    ) -> List[FuzzyMatchPair]:
        """
        Executes fuzzy matching with ranking logic:
        1. Compares structural keys (bank_account, currency, absolute amount).
        2. Calculates weighted RapidFuzz scores on description/narration.
        3. Ranks candidates descending by confidence score.
        4. Pairs with the highest confidence candidate above the threshold, preventing double matching.
        """
        matches: List[FuzzyMatchPair] = []
        
        # Filter active unmatched transactions
        unmatched_bank = [b for b in bank_txs if self._get_field(b, "status") == "UNMATCHED"]
        unmatched_ledger = [l for l in ledger_txs if self._get_field(l, "status") == "UNMATCHED"]

        for bt in unmatched_bank:
            best_candidate = None
            best_score_data = None
            
            b_acc = self._get_field(bt, "bank_account")
            b_ccy = self._get_field(bt, "currency")
            b_amt = self._get_field(bt, "amount")
            b_desc = self._get_field(bt, "description") or ""
            
            if b_amt is None:
                continue
                
            b_abs_amt = abs(b_amt)

            # Find matching candidates using structural filters first to optimize search space
            for lt in unmatched_ledger:
                l_status = self._get_field(lt, "status")
                if l_status and l_status != "UNMATCHED":
                    continue

                l_acc = self._get_field(lt, "bank_account")
                l_ccy = self._get_field(lt, "currency")
                l_amt = self._get_field(lt, "amount")
                l_desc = self._get_field(lt, "description") or ""
                
                if l_amt is None:
                    continue

                # Structural compatibility (same account, currency, and amount)
                if b_acc == l_acc and b_ccy == l_ccy and abs(b_amt) == abs(l_amt):
                    # Compute string metrics
                    scores = self.calculate_scores(b_desc, l_desc)
                    confidence = scores["confidence_score"]

                    if confidence >= self.threshold:
                        if best_score_data is None or confidence > best_score_data["confidence_score"]:
                            best_score_data = scores
                            best_candidate = lt

            # Pair established
            if best_candidate and best_score_data:
                # Mark as MATCHED
                if hasattr(bt, "status"):
                    bt.status = "MATCHED"
                elif isinstance(bt, dict):
                    bt["status"] = "MATCHED"

                if hasattr(best_candidate, "status"):
                    best_candidate.status = "MATCHED"
                elif isinstance(best_candidate, dict):
                    best_candidate["status"] = "MATCHED"

                matches.append(
                    FuzzyMatchPair(
                        bank_transaction=bt,
                        ledger_transaction=best_candidate,
                        confidence_score=best_score_data["confidence_score"],
                        token_set_ratio=best_score_data["token_set_ratio"],
                        jaro_winkler=best_score_data["jaro_winkler"],
                        levenshtein=best_score_data["levenshtein"],
                        rule_applied=f"FUZZY_MATCH_{int(best_score_data['confidence_score'])}"
                    )
                )
                
                # Remove candidate from active pool to prevent double matching
                unmatched_ledger.remove(best_candidate)

        return matches

def run_test_cases():
    """Runs standard difficult financial narration fuzzy matching test cases."""
    print("=" * 80)
    print("🔍 RUNNING FUZZY MATCHING ENGINE SIMULATED TESTING SANDBOX")
    print("=" * 80)

    test_cases = [
        ("AMZN MKTP US*1A2B3C", "AMAZON MARKETPLACE", "Amazon Marketplace debit"),
        ("TRANSFER TO A. SMITH ACC-123", "TRANS TO ALAN SMITH", "Personal transfer"),
        ("INVOICE #98765 SEC CORP", "SECURITY CORP INV-98765", "Corporate invoice billing"),
        ("WTR BILL CITY UTILITIES", "CITY OF METROPOLIS WATER BILL", "Utility payment"),
        ("PAYPAL *STEAM GAMES 888-555-0122 CA", "STEAM GAMES", "Subscription service"),
        ("MSFT *AZURE BILLING", "MICROSOFT CORP AZURE SERVICE", "Cloud server hosting"),
        ("SG CHRONOS LTD DIRECT DEBIT", "CHRONOS LIMITED PAYOUT", "Merchant debit"),
    ]

    engine = FuzzyMatchEngine()

    print(f"{'BANK NARRATION':<35} | {'LEDGER DESCRIPTION':<30} | {'CONFIDENCE':<10}")
    print("-" * 80)
    for s1, s2, desc in test_cases:
        scores = engine.calculate_scores(s1, s2)
        print(f"{s1:<35} | {s2:<30} | {scores['confidence_score']}%")
        print(f"  └─ [Metrics] TokenSet: {scores['token_set_ratio']}% | JaroWinkler: {scores['jaro_winkler']}% | Levenshtein: {scores['levenshtein']}%")
        print()

    print("=" * 80)

if __name__ == "__main__":
    if "--test-cases" in sys.argv or len(sys.argv) == 1:
        run_test_cases()
