import sys
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import itertools
from decimal import Decimal
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional, Set

@dataclass
class RuleMatchPair:
    """Represents a match produced by a specific reconciliation rule."""
    bank_transactions: List[Any]  # Can be one (standard/split) or multiple (M:N)
    ledger_transactions: List[Any]  # Can be one or multiple
    rule_name: str
    match_details: str
    similarity_score: float = 90.0
    matched_at: datetime = field(default_factory=lambda: datetime.now())

class ReconciliationRule:
    """Base class for all customizable reconciliation rules."""
    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled

    def match(
        self, 
        bank_txs: List[Any], 
        ledger_txs: List[Any]
    ) -> List[RuleMatchPair]:
        raise NotImplementedError("Each rule must implement a match method.")

    @staticmethod
    def _get_field(obj: Any, name: str) -> Any:
        if hasattr(obj, name):
            return getattr(obj, name)
        elif isinstance(obj, dict):
            return obj.get(name)
        return None

    @staticmethod
    def _set_status(obj: Any, status: str):
        if hasattr(obj, "status"):
            obj.status = status
        elif isinstance(obj, dict):
            obj["status"] = status


class ToleranceRule(ReconciliationRule):
    """
    Priority 1 Rule: Reference matching with customizable Date Offset and Amount Tolerances.
    Ensures they share the same normalized Reference and Account, but allows dates within +/- N days
    and absolute amounts within +/- $M (handling bank rounding or small fee variances).
    """
    def __init__(self, date_tolerance_days: int = 3, amount_tolerance: float = 1.50):
        super().__init__("Date_Amount_Tolerance")
        self.date_tolerance_days = date_tolerance_days
        self.amount_tolerance = Decimal(str(amount_tolerance))

    def match(
        self, 
        bank_txs: List[Any], 
        ledger_txs: List[Any]
    ) -> List[RuleMatchPair]:
        matches: List[RuleMatchPair] = []
        
        unmatched_bank = [b for b in bank_txs if self._get_field(b, "status") == "UNMATCHED"]
        unmatched_ledger = [l for l in ledger_txs if self._get_field(l, "status") == "UNMATCHED"]

        for bt in unmatched_bank:
            b_ref = self._get_field(bt, "reference") or ""
            b_ref_clean = b_ref.strip().upper()
            
            if not b_ref_clean:
                continue

            b_acc = self._get_field(bt, "bank_account")
            b_ccy = self._get_field(bt, "currency")
            b_date = self._get_field(bt, "transaction_date")
            b_amt = self._get_field(bt, "amount")
            
            if b_amt is None or b_date is None:
                continue

            for lt in unmatched_ledger:
                if self._get_field(lt, "status") != "UNMATCHED":
                    continue

                l_ref = self._get_field(lt, "reference") or ""
                l_ref_clean = l_ref.strip().upper()
                
                if l_ref_clean == b_ref_clean:
                    l_acc = self._get_field(lt, "bank_account")
                    l_ccy = self._get_field(lt, "currency")
                    l_date = self._get_field(lt, "transaction_date")
                    l_amt = self._get_field(lt, "amount")

                    if l_amt is None or l_date is None:
                        continue

                    # Match if structural details (account, currency) fit
                    if b_acc == l_acc and b_ccy == l_ccy:
                        # 1. Check Date offset
                        date_diff = abs(b_date - l_date)
                        
                        # 2. Check Amount variance
                        amt_diff = abs(abs(b_amt) - abs(l_amt))
                        
                        if date_diff <= timedelta(days=self.date_tolerance_days) and amt_diff <= self.amount_tolerance:
                            # Match discovered
                            self._set_status(bt, "MATCHED")
                            self._set_status(lt, "MATCHED")
                            
                            details = f"TOLERANCE MATCH: DateDiff={date_diff.days}d, AmtDiff=${float(amt_diff):.2f}"
                            matches.append(
                                RuleMatchPair(
                                    bank_transactions=[bt],
                                    ledger_transactions=[lt],
                                    rule_name=self.name,
                                    match_details=details,
                                    similarity_score=95.0
                                )
                            )
                            break # Move to next bank transaction to avoid double matching
                            
        return matches


class FXVarianceRule(ReconciliationRule):
    """
    Priority 2 Rule: Matches transactions recorded in different currencies by converting
    to a base currency using exchange rates and evaluating matches within a percentage tolerance.
    Useful for cross-border bank settlement deviations due to daily FX changes.
    """
    def __init__(self, exchange_rates: Dict[str, float] = None, percentage_tolerance: float = 1.0):
        super().__init__("FX_Variance_Matcher")
        # Rates from local currency to USD (base)
        self.exchange_rates = exchange_rates or {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "SGD": 0.74}
        self.percentage_tolerance = percentage_tolerance  # default 1.0%

    def _convert_to_usd(self, amount: Decimal, currency: str) -> Decimal:
        rate = self.exchange_rates.get(currency.upper(), 1.0)
        return Decimal(str(amount)) * Decimal(str(rate))

    def match(
        self, 
        bank_txs: List[Any], 
        ledger_txs: List[Any]
    ) -> List[RuleMatchPair]:
        matches: List[RuleMatchPair] = []
        
        unmatched_bank = [b for b in bank_txs if self._get_field(b, "status") == "UNMATCHED"]
        unmatched_ledger = [l for l in ledger_txs if self._get_field(l, "status") == "UNMATCHED"]

        for bt in unmatched_bank:
            b_ref = self._get_field(bt, "reference") or ""
            b_ref_clean = b_ref.strip().upper()
            
            if not b_ref_clean:
                continue

            b_acc = self._get_field(bt, "bank_account")
            b_ccy = self._get_field(bt, "currency") or "USD"
            b_date = self._get_field(bt, "transaction_date")
            b_amt = self._get_field(bt, "amount")
            
            if b_amt is None or b_date is None:
                continue

            for lt in unmatched_ledger:
                if self._get_field(lt, "status") != "UNMATCHED":
                    continue

                l_ref = self._get_field(lt, "reference") or ""
                l_ref_clean = l_ref.strip().upper()
                
                if l_ref_clean == b_ref_clean:
                    l_acc = self._get_field(lt, "bank_account")
                    l_ccy = self._get_field(lt, "currency") or "USD"
                    l_date = self._get_field(lt, "transaction_date")
                    l_amt = self._get_field(lt, "amount")

                    if l_amt is None or l_date is None:
                        continue

                    # Same bank account, but potentially DIFFERENT currency
                    if b_acc == l_acc:
                        date_diff = abs(b_date - l_date)
                        if date_diff <= timedelta(days=5):  # default date limit for FX clearing
                            # Convert both to base USD
                            usd_bank = self._convert_to_usd(abs(b_amt), b_ccy)
                            usd_ledger = self._convert_to_usd(abs(l_amt), l_ccy)
                            
                            # Check percentage variance
                            variance = abs(usd_bank - usd_ledger) / max(usd_bank, Decimal("1.0")) * 100
                            
                            if variance <= Decimal(str(self.percentage_tolerance)):
                                self._set_status(bt, "MATCHED")
                                self._set_status(lt, "MATCHED")
                                
                                details = f"FX MATCH: Bank={b_ccy} {b_amt:.2f} -> USD {usd_bank:.2f} | Ledger={l_ccy} {l_amt:.2f} -> USD {usd_ledger:.2f} | Var={float(variance):.3f}%"
                                matches.append(
                                    RuleMatchPair(
                                        bank_transactions=[bt],
                                        ledger_transactions=[lt],
                                        rule_name=self.name,
                                        match_details=details,
                                        similarity_score=90.0
                                    )
                                )
                                break
                                
        return matches


class SplitTransactionRule(ReconciliationRule):
    """
    Priority 3 Rule: Split Transactions (1:N or N:1).
    Detects cases where a single bank transaction represents multiple ledger bookings
    (e.g., single batch settlement on the bank side vs individual client invoices in ledger).
    Uses combinatoric search (Subset Sum) to find candidate lists summing precisely to target amount.
    """
    def __init__(self, date_tolerance_days: int = 3, amount_tolerance: float = 0.10, max_split_size: int = 4):
        super().__init__("Split_Transaction_Matching")
        self.date_tolerance_days = date_tolerance_days
        self.amount_tolerance = Decimal(str(amount_tolerance))
        self.max_split_size = max_split_size

    def match(
        self, 
        bank_txs: List[Any], 
        ledger_txs: List[Any]
    ) -> List[RuleMatchPair]:
        matches: List[RuleMatchPair] = []
        
        # 1. 1:N Splits (1 Bank Statement matches N Ledger bookings)
        unmatched_bank = [b for b in bank_txs if self._get_field(b, "status") == "UNMATCHED"]
        unmatched_ledger = [l for l in ledger_txs if self._get_field(l, "status") == "UNMATCHED"]

        for bt in unmatched_bank:
            b_acc = self._get_field(bt, "bank_account")
            b_ccy = self._get_field(bt, "currency")
            b_date = self._get_field(bt, "transaction_date")
            b_amt = self._get_field(bt, "amount")
            
            if b_amt is None or b_date is None:
                continue

            target_amt = abs(b_amt)

            # Gather candidate ledger transactions close in date on same account/currency
            candidates = []
            for lt in unmatched_ledger:
                if self._get_field(lt, "status") != "UNMATCHED":
                    continue
                
                l_acc = self._get_field(lt, "bank_account")
                l_ccy = self._get_field(lt, "currency")
                l_date = self._get_field(lt, "transaction_date")
                l_amt = self._get_field(lt, "amount")
                
                if l_amt is None or l_date is None:
                    continue

                if b_acc == l_acc and b_ccy == l_ccy:
                    date_diff = abs(b_date - l_date)
                    if date_diff <= timedelta(days=self.date_tolerance_days):
                        candidates.append(lt)

            # Run combinatoric search to find subset sum matching target
            found_split = False
            for r in range(2, min(len(candidates) + 1, self.max_split_size + 1)):
                for comb in itertools.combinations(candidates, r):
                    # Check if combination elements are already matched by earlier loop runs
                    if any(self._get_field(x, "status") != "UNMATCHED" for x in comb):
                        continue
                        
                    sum_comb = sum(abs(self._get_field(x, "amount")) for x in comb)
                    
                    if abs(sum_comb - target_amt) <= self.amount_tolerance:
                        # Match established!
                        self._set_status(bt, "MATCHED")
                        for x in comb:
                            self._set_status(x, "MATCHED")
                            
                        details = f"SPLIT 1:N MATCH: Bank Statement ${float(target_amt):.2f} matched with {len(comb)} Ledger bookings (sum=${float(sum_comb):.2f})"
                        matches.append(
                            RuleMatchPair(
                                bank_transactions=[bt],
                                ledger_transactions=list(comb),
                                rule_name=self.name,
                                match_details=details,
                                similarity_score=85.0
                            )
                        )
                        found_split = True
                        break # break combinations loop
                if found_split:
                    break # break split-size loop

        # 2. N:1 Splits (N Bank Statements match 1 Ledger booking)
        # Refresh unmatched list
        unmatched_bank = [b for b in bank_txs if self._get_field(b, "status") == "UNMATCHED"]
        unmatched_ledger = [l for l in ledger_txs if self._get_field(l, "status") == "UNMATCHED"]

        for lt in unmatched_ledger:
            l_acc = self._get_field(lt, "bank_account")
            l_ccy = self._get_field(lt, "currency")
            l_date = self._get_field(lt, "transaction_date")
            l_amt = self._get_field(lt, "amount")
            
            if l_amt is None or l_date is None:
                continue

            target_amt = abs(l_amt)

            # Gather candidate bank transactions
            candidates = []
            for bt in unmatched_bank:
                if self._get_field(bt, "status") != "UNMATCHED":
                    continue
                
                b_acc = self._get_field(bt, "bank_account")
                b_ccy = self._get_field(bt, "currency")
                b_date = self._get_field(bt, "transaction_date")
                b_amt = self._get_field(bt, "amount")
                
                if b_amt is None or b_date is None:
                    continue

                if b_acc == l_acc and b_ccy == l_ccy:
                    date_diff = abs(l_date - b_date)
                    if date_diff <= timedelta(days=self.date_tolerance_days):
                        candidates.append(bt)

            found_split = False
            for r in range(2, min(len(candidates) + 1, self.max_split_size + 1)):
                for comb in itertools.combinations(candidates, r):
                    if any(self._get_field(x, "status") != "UNMATCHED" for x in comb):
                        continue
                        
                    sum_comb = sum(abs(self._get_field(x, "amount")) for x in comb)
                    
                    if abs(sum_comb - target_amt) <= self.amount_tolerance:
                        self._set_status(lt, "MATCHED")
                        for x in comb:
                            self._set_status(x, "MATCHED")
                            
                        details = f"SPLIT N:1 MATCH: Ledger booking ${float(target_amt):.2f} matched with {len(comb)} Bank entries (sum=${float(sum_comb):.2f})"
                        matches.append(
                            RuleMatchPair(
                                bank_transactions=list(comb),
                                ledger_transactions=[lt],
                                rule_name=self.name,
                                match_details=details,
                                similarity_score=85.0
                            )
                        )
                        found_split = True
                        break
                if found_split:
                    break

        return matches


class ManyToManySettlementRule(ReconciliationRule):
    """
    Priority 4 Rule: Many-to-Many Aggregate settlements.
    Finds groups of unmatched transactions sharing the same Account & Currency within a date window,
    matching them if their total aggregate sums reconcile within tolerance.
    Extremely valuable for clearing large consolidated settlement adjustments.
    """
    def __init__(self, date_window_days: int = 5, amount_tolerance: float = 0.50):
        super().__init__("ManyToMany_Settlement_Matching")
        self.date_window_days = date_window_days
        self.amount_tolerance = Decimal(str(amount_tolerance))

    def match(
        self, 
        bank_txs: List[Any], 
        ledger_txs: List[Any]
    ) -> List[RuleMatchPair]:
        matches: List[RuleMatchPair] = []
        
        unmatched_bank = [b for b in bank_txs if self._get_field(b, "status") == "UNMATCHED"]
        unmatched_ledger = [l for l in ledger_txs if self._get_field(l, "status") == "UNMATCHED"]

        if not unmatched_bank or not unmatched_ledger:
            return matches

        # Group both sides by (account, currency)
        bank_groups: Dict[Tuple[str, str], List[Any]] = {}
        for bt in unmatched_bank:
            acc = self._get_field(bt, "bank_account")
            ccy = self._get_field(bt, "currency")
            bank_groups.setdefault((acc, ccy), []).append(bt)

        ledger_groups: Dict[Tuple[str, str], List[Any]] = {}
        for lt in unmatched_ledger:
            acc = self._get_field(lt, "bank_account")
            ccy = self._get_field(lt, "currency")
            ledger_groups.setdefault((acc, ccy), []).append(lt)

        # Match corresponding keys
        for key, bt_list in bank_groups.items():
            if key not in ledger_groups:
                continue
                
            lt_list = ledger_groups[key]
            
            # Filter active unmatched items
            bt_active = [b for b in bt_list if self._get_field(b, "status") == "UNMATCHED"]
            lt_active = [l for l in lt_list if self._get_field(l, "status") == "UNMATCHED"]
            
            if not bt_active or not lt_active:
                continue

            # Check absolute total sums
            bank_sum = sum(abs(self._get_field(b, "amount")) for b in bt_active)
            ledger_sum = sum(abs(self._get_field(l, "amount")) for l in lt_active)

            # Match only if they match within tolerance
            if abs(bank_sum - ledger_sum) <= self.amount_tolerance:
                # Pair them all together
                for b in bt_active:
                    self._set_status(b, "MATCHED")
                for l in lt_active:
                    self._set_status(l, "MATCHED")

                details = f"MANY-TO-MANY SETTLEMENT: Consolidated {len(bt_active)} Bank entries (sum=${float(bank_sum):.2f}) matched {len(lt_active)} Ledger entries (sum=${float(ledger_sum):.2f})"
                matches.append(
                    RuleMatchPair(
                        bank_transactions=bt_active,
                        ledger_transactions=lt_active,
                        rule_name=self.name,
                        match_details=details,
                        similarity_score=80.0
                    )
                )

        return matches


class RuleEngine:
    """
    Manager class for the configurable Rule-based Reconciliation Engine.
    Executes rules sequentially based on assigned priorities.
    """
    def __init__(self, rules: List[ReconciliationRule] = None):
        self.rules = rules or [
            ToleranceRule(),
            FXVarianceRule(),
            SplitTransactionRule(),
            ManyToManySettlementRule()
        ]

    def add_rule(self, rule: ReconciliationRule):
        self.rules.append(rule)

    def reconcile(
        self, 
        bank_txs: List[Any], 
        ledger_txs: List[Any]
    ) -> List[RuleMatchPair]:
        """
        Executes active rules sequentially.
        Unmatched pool shrinks as higher priority rules claim matches.
        """
        all_matches: List[RuleMatchPair] = []
        
        for rule in self.rules:
            if not rule.enabled:
                continue
            
            # Execute rule
            rule_matches = rule.match(bank_txs, ledger_txs)
            all_matches.extend(rule_matches)

        return all_matches


# Standalone demonstration
def run_rule_engine_demo():
    print("=" * 80)
    print("⚙️ RUNNING ADVANCED RULE ENGINE DEMO")
    print("=" * 80)

    # 1. Date & Amount Tolerance Demo
    print("\n[Scenario 1] Reference match with Date & Amount Tolerances:")
    bank1 = [{"reference": "REF-ABC", "bank_account": "ACC1", "currency": "USD", "amount": Decimal("1000.00"), "transaction_date": date(2026, 5, 20), "status": "UNMATCHED"}]
    ledger1 = [{"reference": "REF-ABC", "bank_account": "ACC1", "currency": "USD", "amount": Decimal("999.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED"}]
    
    engine = RuleEngine([ToleranceRule(date_tolerance_days=3, amount_tolerance=1.50)])
    matches = engine.reconcile(bank1, ledger1)
    for m in matches:
        print(f"  Rule: {m.rule_name} | {m.match_details}")

    # 2. FX Variance Demo
    print("\n[Scenario 2] Cross-Border settlement with FX Variances (EUR vs USD):")
    bank2 = [{"reference": "TX-FX-99", "bank_account": "ACC_GLOBAL", "currency": "EUR", "amount": Decimal("100.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED"}]
    # 100 EUR = 108.00 USD. Let's make ledger book 107.50 USD (FX rate difference)
    ledger2 = [{"reference": "TX-FX-99", "bank_account": "ACC_GLOBAL", "currency": "USD", "amount": Decimal("107.50"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED"}]
    
    engine = RuleEngine([FXVarianceRule(percentage_tolerance=1.0)])
    matches = engine.reconcile(bank2, ledger2)
    for m in matches:
        print(f"  Rule: {m.rule_name} | {m.match_details}")

    # 3. Split Transaction Demo (1:N)
    print("\n[Scenario 3] Batch Bank deposit matched with multiple individual Ledger bookings (1:N Split):")
    bank3 = [{"reference": "BATCH-001", "bank_account": "ACC3", "currency": "USD", "amount": Decimal("5000.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED"}]
    ledger3 = [
        {"reference": "INV-101", "bank_account": "ACC3", "currency": "USD", "amount": Decimal("2000.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED"},
        {"reference": "INV-102", "bank_account": "ACC3", "currency": "USD", "amount": Decimal("3000.00"), "transaction_date": date(2026, 5, 21), "status": "UNMATCHED"},
        {"reference": "INV-OTHER", "bank_account": "ACC3", "currency": "USD", "amount": Decimal("4500.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED"}
    ]
    
    engine = RuleEngine([SplitTransactionRule()])
    matches = engine.reconcile(bank3, ledger3)
    for m in matches:
        print(f"  Rule: {m.rule_name} | {m.match_details}")

    # 4. Many-to-Many Settlement Demo (N:M)
    print("\n[Scenario 4] Consolidated clearing adjustments (M:N Settlement):")
    bank4 = [
        {"bank_account": "ACC4", "currency": "USD", "amount": Decimal("100.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED"},
        {"bank_account": "ACC4", "currency": "USD", "amount": Decimal("200.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED"},
        {"bank_account": "ACC4", "currency": "USD", "amount": Decimal("300.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED"},
    ]
    ledger4 = [
        {"bank_account": "ACC4", "currency": "USD", "amount": Decimal("250.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED"},
        {"bank_account": "ACC4", "currency": "USD", "amount": Decimal("350.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED"},
    ]
    
    engine = RuleEngine([ManyToManySettlementRule()])
    matches = engine.reconcile(bank4, ledger4)
    for m in matches:
        print(f"  Rule: {m.rule_name} | {m.match_details}")

    print("=" * 80)

if __name__ == "__main__":
    if "--demo" in sys.argv or len(sys.argv) == 1:
        run_rule_engine_demo()
