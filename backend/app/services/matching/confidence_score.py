import sys
import math
from decimal import Decimal
from datetime import date, datetime
from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional
from rapidfuzz.distance import JaroWinkler
from rapidfuzz import fuzz

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

@dataclass
class ScoreBreakdown:
    """Contains individual field-level similarity scores and weights."""
    ref_score: float
    ref_weight: float
    amt_score: float
    amt_weight: float
    date_score: float
    date_weight: float
    desc_score: float
    desc_weight: float
    acc_score: float
    acc_weight: float
    ccy_score: float
    ccy_weight: float
    final_score: float
    classification: str  # "AUTO_MATCH", "MANUAL_REVIEW", "EXCEPTION"


class ConfidenceScoringEngine:
    """
    Evaluates individual bank and ledger transaction pairs, calculating
    a normalized confidence score strictly between 0.0 and 1.0 using field-level weights.
    Directs pairs to Auto-Match, Manual Review, or Exception queues.
    """
    def __init__(
        self,
        weight_reference: float = 0.35,
        weight_amount: float = 0.25,
        weight_date: float = 0.15,
        weight_description: float = 0.15,
        weight_account: float = 0.05,
        weight_currency: float = 0.05,
        auto_match_threshold: float = 0.85,
        manual_review_threshold: float = 0.60,
        date_decay_rate: float = 0.15
    ):
        self.auto_match_threshold = auto_match_threshold
        self.manual_review_threshold = manual_review_threshold
        self.date_decay_rate = date_decay_rate

        # Normalize weights to sum to exactly 1.0
        total_weight = (
            weight_reference + weight_amount + weight_date +
            weight_description + weight_account + weight_currency
        )
        self.w_ref = weight_reference / total_weight
        self.w_amt = weight_amount / total_weight
        self.w_date = weight_date / total_weight
        self.w_desc = weight_description / total_weight
        self.w_acc = weight_account / total_weight
        self.w_ccy = weight_currency / total_weight

    @staticmethod
    def _get_field(obj: Any, name: str) -> Any:
        if hasattr(obj, name):
            return getattr(obj, name)
        elif isinstance(obj, dict):
            return obj.get(name)
        return None

    def _score_reference(self, ref1: str, ref2: str) -> float:
        r1 = str(ref1 or "").strip().upper()
        r2 = str(ref2 or "").strip().upper()

        if not r1 or not r2:
            return 0.0

        if r1 == r2:
            return 1.0

        # Substring/prefix starts-with matches
        if r1.startswith(r2) or r2.startswith(r1):
            return 0.85

        # Fuzzy Jaro-Winkler character transposition metric
        jw = float(JaroWinkler.similarity(r1, r2))
        return jw if jw >= 0.70 else 0.0

    def _score_amount(self, amt1: Any, amt2: Any) -> float:
        if amt1 is None or amt2 is None:
            return 0.0

        try:
            a1 = abs(Decimal(str(amt1)))
            a2 = abs(Decimal(str(amt2)))
        except Exception:
            return 0.0

        if a1 == a2:
            return 1.0

        # Absolute difference tolerance score (small clearing discrepancies or bank fee adjustments)
        diff_abs = abs(a1 - a2)
        if diff_abs <= Decimal("1.50"):
            return 0.80

        # Percent discrepancy linear decay score (if >= 5% variance, score drops to 0.0)
        diff_pct = (diff_abs / max(a1, a2, Decimal("1.0"))) * 100
        decay_score = 1.0 - (float(diff_pct) / 5.0)
        return max(0.0, decay_score)

    def _score_date(self, date1: Any, date2: Any) -> float:
        if date1 is None or date2 is None:
            return 0.0

        # Convert strings to standard date objects if necessary
        d1 = date1 if isinstance(date1, (date, datetime)) else datetime.strptime(str(date1).strip(), "%Y-%m-%d").date()
        d2 = date2 if isinstance(date2, (date, datetime)) else datetime.strptime(str(date2).strip(), "%Y-%m-%d").date()

        days = abs((d1 - d2).days)
        # Exponential Date Decay Model: e^(-lambda * dt)
        return math.exp(-self.date_decay_rate * days)

    def _score_description(self, desc1: str, desc2: str) -> float:
        d1 = str(desc1 or "").strip().lower()
        d2 = str(desc2 or "").strip().lower()

        if not d1 or not d2:
            return 0.0

        ts_ratio = float(fuzz.token_set_ratio(d1, d2)) / 100.0
        jw_similarity = float(JaroWinkler.similarity(d1, d2))
        
        # Combined string similarity
        return (0.6 * ts_ratio) + (0.4 * jw_similarity)

    def _score_binary(self, val1: Any, val2: Any) -> float:
        v1 = str(val1 or "").strip().upper()
        v2 = str(val2 or "").strip().upper()
        return 1.0 if v1 == v2 and v1 != "" else 0.0

    def evaluate(self, bank_tx: Any, ledger_tx: Any) -> ScoreBreakdown:
        """
        Performs field-level evaluations and aggregates the final confidence score.
        Categorizes classifications based on thresholds.
        """
        # Calculate raw field-level scores
        s_ref = self._score_reference(
            self._get_field(bank_tx, "reference"), 
            self._get_field(ledger_tx, "reference")
        )
        s_amt = self._score_amount(
            self._get_field(bank_tx, "amount"), 
            self._get_field(ledger_tx, "amount")
        )
        s_date = self._score_date(
            self._get_field(bank_tx, "transaction_date"), 
            self._get_field(ledger_tx, "transaction_date")
        )
        s_desc = self._score_description(
            self._get_field(bank_tx, "description"), 
            self._get_field(ledger_tx, "description")
        )
        s_acc = self._score_binary(
            self._get_field(bank_tx, "bank_account"), 
            self._get_field(ledger_tx, "bank_account")
        )
        s_ccy = self._score_binary(
            self._get_field(bank_tx, "currency"), 
            self._get_field(ledger_tx, "currency")
        )

        # Aggregate weighted score
        final_score = (
            (self.w_ref * s_ref) +
            (self.w_amt * s_amt) +
            (self.w_date * s_date) +
            (self.w_desc * s_desc) +
            (self.w_acc * s_acc) +
            (self.w_ccy * s_ccy)
        )

        # Threshold classification routing
        if final_score >= self.auto_match_threshold:
            classification = "AUTO_MATCH"
        elif final_score >= self.manual_review_threshold:
            classification = "MANUAL_REVIEW"
        else:
            classification = "EXCEPTION"

        return ScoreBreakdown(
            ref_score=round(s_ref, 4), ref_weight=round(self.w_ref, 4),
            amt_score=round(s_amt, 4), amt_weight=round(self.w_amt, 4),
            date_score=round(s_date, 4), date_weight=round(self.w_date, 4),
            desc_score=round(s_desc, 4), desc_weight=round(self.w_desc, 4),
            acc_score=round(s_acc, 4), acc_weight=round(self.w_acc, 4),
            ccy_score=round(s_ccy, 4), ccy_weight=round(self.w_ccy, 4),
            final_score=round(final_score, 4),
            classification=classification
        )


def run_confidence_tests():
    print("=" * 100)
    print("📊 CONFIDENCE SCORING ENGINE - SIMULATION DEMO & TEST CASES")
    print("=" * 100)

    engine = ConfidenceScoringEngine()

    # Define various test transaction pairs representing different degrees of alignment
    test_cases = [
        (
            "Case 1: Exact Perfect Match",
            {"reference": "TX-1001", "amount": Decimal("5000.00"), "transaction_date": date(2026, 5, 22), "description": "Vendor Invoice Settlement", "bank_account": "ACC_OPS", "currency": "USD"},
            {"reference": "TX-1001", "amount": Decimal("5000.00"), "transaction_date": date(2026, 5, 22), "description": "Vendor Invoice Settlement", "bank_account": "ACC_OPS", "currency": "USD"},
        ),
        (
            "Case 2: Typos in Reference & 2 Days Date Delay (Exponential Decay)",
            {"reference": "TX-1002A", "amount": Decimal("250.00"), "transaction_date": date(2026, 5, 22), "description": "Amazon Mktp Purchase", "bank_account": "ACC_OPS", "currency": "USD"},
            {"reference": "TX-1002B", "amount": Decimal("250.00"), "transaction_date": date(2026, 5, 20), "description": "Amazon Marketplace", "bank_account": "ACC_OPS", "currency": "USD"},
        ),
        (
            "Case 3: Reference Perfect, Date Perfect, but Minor Amount Discrepancy ($1.20 bank fee)",
            {"reference": "TX-1003", "amount": Decimal("1001.20"), "transaction_date": date(2026, 5, 22), "description": "Client Wire", "bank_account": "ACC_OPS", "currency": "USD"},
            {"reference": "TX-1003", "amount": Decimal("1000.00"), "transaction_date": date(2026, 5, 22), "description": "Client Wire Payout", "bank_account": "ACC_OPS", "currency": "USD"},
        ),
        (
            "Case 4: Messy Descriptions & Missing Reference entirely (Fuzzy candidate)",
            {"reference": "", "amount": Decimal("850.00"), "transaction_date": date(2026, 5, 22), "description": "Microsoft Corp Azure Cloud Services Invoice", "bank_account": "ACC_OPS", "currency": "USD"},
            {"reference": "", "amount": Decimal("850.00"), "transaction_date": date(2026, 5, 22), "description": "MSFT Azure Bill", "bank_account": "ACC_OPS", "currency": "USD"},
        ),
        (
            "Case 5: Complete Mismatch Exception",
            {"reference": "TX-9999", "amount": Decimal("12.50"), "transaction_date": date(2026, 5, 22), "description": "Starbucks Coffee", "bank_account": "ACC_OPS", "currency": "USD"},
            {"reference": "TX-1111", "amount": Decimal("990.00"), "transaction_date": date(2026, 5, 10), "description": "Office Desk rent", "bank_account": "ACC_MKT", "currency": "EUR"},
        ),
    ]

    for label, bank, ledger in test_cases:
        print(f"\n📌 {label}")
        print("-" * 100)
        res = engine.evaluate(bank, ledger)
        
        # Display individual score breakdowns
        print(f"| {'FIELD':<12} | {'SCORE':<8} | {'WEIGHT':<8} | {'CONTRIBUTION':<12} |")
        print(f"|{'-'*14}|{'-'*10}|{'-'*10}|{'-'*14}|")
        print(f"| {'Reference':<12} | {res.ref_score:<8} | {res.ref_weight:<8} | {res.ref_score * res.ref_weight:<12.4f} |")
        print(f"| {'Amount':<12} | {res.amt_score:<8} | {res.amt_weight:<8} | {res.amt_score * res.amt_weight:<12.4f} |")
        print(f"| {'Date':<12} | {res.date_score:<8} | {res.date_weight:<8} | {res.date_score * res.date_weight:<12.4f} |")
        print(f"| {'Description':<12} | {res.desc_score:<8} | {res.desc_weight:<8} | {res.desc_score * res.desc_weight:<12.4f} |")
        print(f"| {'Account':<12} | {res.acc_score:<8} | {res.acc_weight:<8} | {res.acc_score * res.acc_weight:<12.4f} |")
        print(f"| {'Currency':<12} | {res.ccy_score:<8} | {res.ccy_weight:<8} | {res.ccy_score * res.ccy_weight:<12.4f} |")
        print(f"|{'-'*14}|{'-'*10}|{'-'*10}|{'-'*14}|")
        
        # Print status summary
        status_color = "🟢" if res.classification == "AUTO_MATCH" else ("🟡" if res.classification == "MANUAL_REVIEW" else "🔴")
        print(f"⚡ FINAL AGGREGATE MATCH INDEX: {res.final_score:.4f} (Score Range: 0.0 - 1.0)")
        print(f"📁 ROUTING CLASSIFICATION    : {status_color} {res.classification}")
        print("=" * 100)


if __name__ == "__main__":
    run_confidence_tests()
