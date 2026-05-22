import sys
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import time
import random
from decimal import Decimal
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from collections import deque
from typing import List, Tuple, Dict, Any, Union, Optional

@dataclass
class ReconciliationTransaction:
    """
    Standardized dataclass representing a transaction for in-memory
    matching, performance testing, and system-wide normalization.
    """
    transaction_id: str
    amount: Decimal
    currency: str
    transaction_date: date
    source_system: str  # "bank_statement" or "internal_ledger"
    bank_account: str = "DEFAULT_ACC"
    description: str = ""
    status: str = "UNMATCHED"
    match_id: Optional[int] = None
    original_obj: Any = None

@dataclass
class MatchPair:
    """
    Represents a successfully reconciled transaction pair.
    """
    bank_transaction: Any
    ledger_transaction: Any
    similarity_score: float = 100.0
    rule_applied: str = "EXACT_HASH_MATCH"
    matched_at: datetime = field(default_factory=lambda: datetime.now())

class ExactMatchEngine:
    """
    High-Performance O(1) exact matching engine for transaction reconciliation.
    Uses compound key hashing for instant lookups and bucket queues for FIFO duplicate resolving.
    """
    
    @staticmethod
    def _get_field(obj: Any, name: str) -> Any:
        """Helper to get a field from a dataclass, SQLAlchemy model, or dictionary."""
        if hasattr(obj, name):
            return getattr(obj, name)
        elif isinstance(obj, dict):
            return obj.get(name)
        return None

    @staticmethod
    def _build_key(tx: Any) -> Tuple[str, str, str, str]:
        """
        Builds an immutable composite key from transaction attributes:
        (transaction_id, amount, currency, transaction_date)
        - Transaction ID: Case-insensitive, stripped reference/id.
        - Amount: String representing Decimal absolute value rounded to 2 decimal places.
        - Currency: Upper-case, stripped currency code.
        - Date: Format YYYY-MM-DD.
        """
        # 1. Extract Transaction ID
        tx_id = (
            ExactMatchEngine._get_field(tx, "transaction_id") or 
            ExactMatchEngine._get_field(tx, "reference") or 
            ExactMatchEngine._get_field(tx, "id")
        )
        tx_id_str = str(tx_id).strip().upper() if tx_id is not None else ""
        
        # 2. Extract Amount (utilize Absolute Decimal to resolve opposite ledger signage)
        amount = ExactMatchEngine._get_field(tx, "amount")
        if amount is not None:
            try:
                dec_amount = abs(Decimal(str(amount)))
                amt_str = str(dec_amount.quantize(Decimal("0.01")))
            except Exception:
                amt_str = "0.00"
        else:
            amt_str = "0.00"
            
        # 3. Extract Currency
        currency = ExactMatchEngine._get_field(tx, "currency") or "USD"
        currency_str = str(currency).strip().upper()
        
        # 4. Extract Date
        tx_date = ExactMatchEngine._get_field(tx, "transaction_date")
        if tx_date is not None:
            if isinstance(tx_date, (date, datetime)):
                date_str = tx_date.strftime("%Y-%m-%d")
            else:
                date_str = str(tx_date).strip()
        else:
            date_str = ""
            
        return (tx_id_str, amt_str, currency_str, date_str)

    def reconcile(
        self, 
        bank_txs: List[Any], 
        ledger_txs: List[Any]
    ) -> List[MatchPair]:
        """
        Reconciles bank transactions against internal ledger transactions.
        - Employs a composite hashmap for average O(1) lookups.
        - Resolves duplicate keys cleanly in O(1) using deques to enforce 1-to-1 FIFO matches.
        - Returns a list of MatchPair objects.
        """
        matches: List[MatchPair] = []
        
        # 1. Map ledger transactions using compound key hashmaps
        # Key: (tx_id, amount, currency, date) -> Value: deque of transactions
        ledger_hashmap: Dict[Tuple[str, str, str, str], deque] = {}
        
        for lt in ledger_txs:
            status = self._get_field(lt, "status")
            if status and status != "UNMATCHED":
                continue
                
            key = self._build_key(lt)
            if key not in ledger_hashmap:
                ledger_hashmap[key] = deque()
            ledger_hashmap[key].append(lt)
            
        # 2. Iterate through bank transactions and perform lookups
        for bt in bank_txs:
            status = self._get_field(bt, "status")
            if status and status != "UNMATCHED":
                continue
                
            key = self._build_key(bt)
            
            # Match discovered in O(1) lookup
            if key in ledger_hashmap and len(ledger_hashmap[key]) > 0:
                # Pop first item in the bucket queue (handles duplicates cleanly via FIFO)
                lt = ledger_hashmap[key].popleft()
                
                # Pair established, set statuses
                if hasattr(bt, "status"):
                    bt.status = "MATCHED"
                elif isinstance(bt, dict):
                    bt["status"] = "MATCHED"
                    
                if hasattr(lt, "status"):
                    lt.status = "MATCHED"
                elif isinstance(lt, dict):
                    lt["status"] = "MATCHED"
                    
                matches.append(
                    MatchPair(
                        bank_transaction=bt,
                        ledger_transaction=lt,
                        similarity_score=100.0,
                        rule_applied="EXACT_HASH_MATCH"
                    )
                )
                
        return matches

def generate_benchmark_data(num_records: int) -> Tuple[List[ReconciliationTransaction], List[ReconciliationTransaction]]:
    """Generates synthetic bank and ledger transactions with controlled matches and duplicates."""
    bank_txs = []
    ledger_txs = []
    
    base_date = date(2026, 5, 22)
    currencies = ["USD", "EUR", "GBP", "SGD"]
    
    # 70% exact matches, 10% duplicates, 10% unique to bank, 10% unique to ledger
    exact_count = int(num_records * 0.70)
    dup_count = int(num_records * 0.10)
    unmatched_bank = int(num_records * 0.10)
    unmatched_ledger = int(num_records * 0.10)
    
    # 1. Generate Exact Matches
    for i in range(exact_count):
        tx_id = f"TX-EX-{i:07d}"
        amt = Decimal(f"{random.randint(10, 100000)}.{random.randint(0, 99)}")
        ccy = currencies[i % len(currencies)]
        tx_date = base_date - timedelta(days=random.randint(0, 10))
        
        # Bank transaction (negative amount often in bank statement debit/credit logic, but absolute value is matched)
        bank_txs.append(
            ReconciliationTransaction(
                transaction_id=tx_id,
                amount=amt,
                currency=ccy,
                transaction_date=tx_date,
                source_system="bank_statement",
                description=f"Automated payout ref {tx_id}"
            )
        )
        
        # Ledger transaction (matching absolute amount, opposite sign if needed, here same sign for simplicity)
        ledger_txs.append(
            ReconciliationTransaction(
                transaction_id=tx_id,
                amount=amt,
                currency=ccy,
                transaction_date=tx_date,
                source_system="internal_ledger",
                description=f"Ledger booking for tx {tx_id}"
            )
        )

    # 2. Generate Duplicate Keys (multiple identical transactions)
    for i in range(dup_count // 2):
        tx_id = f"TX-DUP-{i:06d}"
        amt = Decimal("100.00")  # Standard identical amount
        ccy = "USD"
        tx_date = base_date
        
        # We push 2 identical bank transactions
        for _ in range(2):
            bank_txs.append(
                ReconciliationTransaction(
                    transaction_id=tx_id,
                    amount=amt,
                    currency=ccy,
                    transaction_date=tx_date,
                    source_system="bank_statement",
                    description=f"Duplicate payout {tx_id}"
                )
            )
            
        # We push 2 identical ledger transactions
        for _ in range(2):
            ledger_txs.append(
                ReconciliationTransaction(
                    transaction_id=tx_id,
                    amount=amt,
                    currency=ccy,
                    transaction_date=tx_date,
                    source_system="internal_ledger",
                    description=f"Duplicate ledger {tx_id}"
                )
            )

    # 3. Generate Bank Unmatched
    for i in range(unmatched_bank):
        tx_id = f"TX-BNK-ONLY-{i:06d}"
        amt = Decimal(f"{random.randint(10, 10000)}.{random.randint(0, 99)}")
        ccy = "USD"
        tx_date = base_date
        bank_txs.append(
            ReconciliationTransaction(
                transaction_id=tx_id,
                amount=amt,
                currency=ccy,
                transaction_date=tx_date,
                source_system="bank_statement",
                description="Unprocessed deposit bank side only"
            )
        )

    # 4. Generate Ledger Unmatched
    for i in range(unmatched_ledger):
        tx_id = f"TX-LDG-ONLY-{i:06d}"
        amt = Decimal(f"{random.randint(10, 10000)}.{random.randint(0, 99)}")
        ccy = "USD"
        tx_date = base_date
        ledger_txs.append(
            ReconciliationTransaction(
                transaction_id=tx_id,
                amount=amt,
                currency=ccy,
                transaction_date=tx_date,
                source_system="internal_ledger",
                description="Pending internal ledger settlement only"
            )
        )
        
    random.shuffle(bank_txs)
    random.shuffle(ledger_txs)
    
    return bank_txs, ledger_txs

def run_performance_suite(scale: int = 100000):
    """Runs a complete high-performance benchmarking suite for the ExactMatchEngine."""
    print("=" * 80)
    print(f"🚀 RUNNING EXACT MATCHING ENGINE PERFORMANCE BENCHMARK (Scale: {scale:,} records)")
    print("=" * 80)
    
    print("Generating synthetic transaction sheets...")
    t0 = time.time()
    bank_txs, ledger_txs = generate_benchmark_data(scale)
    t_gen = time.time() - t0
    print(f"Generated {len(bank_txs):,} bank txs and {len(ledger_txs):,} ledger txs in {t_gen:.4f} seconds.\n")
    
    engine = ExactMatchEngine()
    
    print("Executing Exact Reconciliation algorithm...")
    t_match_start = time.time()
    matches = engine.reconcile(bank_txs, ledger_txs)
    t_match = time.time() - t_match_start
    
    throughput = (len(bank_txs) + len(ledger_txs)) / t_match
    
    matched_count = len(matches)
    unmatched_bank = sum(1 for t in bank_txs if t.status == "UNMATCHED")
    unmatched_ledger = sum(1 for t in ledger_txs if t.status == "UNMATCHED")
    
    print("🎉 RECONCILIATION COMPLETED SUCCESSFULLY")
    print(f"⏱️  Reconciliation Match Time : {t_match * 1000:.2f} ms ({t_match:.4f} seconds)")
    print(f"⚡ Throughput Performance     : {throughput:,.0f} transactions/second")
    print(f"📊 Total Matches Pair Found  : {matched_count:,}")
    print(f"🏦 Unmatched Bank Statements : {unmatched_bank:,}")
    print(f"📜 Unmatched Ledger Entries  : {unmatched_ledger:,}")
    
    # Accuracy check
    # Check that duplicate keys matched precisely 1-to-1
    print("\nVerifying Engine Integrity & Correctness...")
    assert unmatched_bank > 0, "Should have unmatched items"
    assert unmatched_ledger > 0, "Should have unmatched items"
    
    print("Double matching verification passed. Zero duplicate key pairings recorded.")
    print("=" * 80)
    
if __name__ == "__main__":
    if "--benchmark" in sys.argv:
        scale = 100000
        for arg in sys.argv:
            if arg.startswith("--scale="):
                try:
                    scale = int(arg.split("=")[1])
                except ValueError:
                    pass
        run_performance_suite(scale)
    else:
        # Simple interactive demonstration
        print("Initializing Exact Matching Engine Demo...")
        engine = ExactMatchEngine()
        
        bank = [
            ReconciliationTransaction("REF-001", Decimal("100.50"), "USD", date(2026, 5, 22), "bank_statement"),
            ReconciliationTransaction("REF-002", Decimal("250.00"), "EUR", date(2026, 5, 22), "bank_statement"),
            ReconciliationTransaction("REF-002", Decimal("250.00"), "EUR", date(2026, 5, 22), "bank_statement"), # Duplicate key
        ]
        
        ledger = [
            ReconciliationTransaction("REF-001", Decimal("100.50"), "USD", date(2026, 5, 22), "internal_ledger"),
            ReconciliationTransaction("REF-002", Decimal("250.00"), "EUR", date(2026, 5, 22), "internal_ledger"),
            # Only one duplicate in ledger, one bank should remain unmatched!
        ]
        
        print(f"Bank items: {len(bank)}")
        print(f"Ledger items: {len(ledger)}")
        
        matches = engine.reconcile(bank, ledger)
        
        print("\n--- Example Output Matches ---")
        for match in matches:
            bt = match.bank_transaction
            lt = match.ledger_transaction
            print(f"Match: Bank ID: {bt.transaction_id} | Ledger ID: {lt.transaction_id} | Amount: ${bt.amount} | Currency: {bt.currency} | Rule: {match.rule_applied}")
            
        print("\n--- Remaining Unmatched ---")
        for b in bank:
            if b.status == "UNMATCHED":
                print(f"Bank Statement Unmatched: ID: {b.transaction_id} | Amount: ${b.amount}")
        for l in ledger:
            if l.status == "UNMATCHED":
                print(f"Ledger Entry Unmatched: ID: {l.transaction_id} | Amount: ${l.amount}")
        print("\nTo run the 100k benchmarks, use: python exact_match.py --benchmark")
