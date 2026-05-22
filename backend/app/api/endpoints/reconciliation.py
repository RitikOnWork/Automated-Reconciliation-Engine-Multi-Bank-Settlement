from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.models.transaction import NormalizedTransaction
from app.models.match import MatchResult
from app.models.exception import ExceptionQueue
from app.security import get_current_user
from app.services.matching.exact import ExactMatcher
from app.services.matching.fuzzy import FuzzyMatcher
from app.services.matching.rule_based import RuleBasedMatcher
from app.services.audit import AuditService

router = APIRouter()


@router.post("/run", status_code=status.HTTP_200_OK)
def trigger_reconciliation_run(
    fuzzy_threshold: float = Query(85.0, ge=50.0, le=100.0),
    date_tolerance_days: int = Query(3, ge=0, le=30),
    amount_tolerance: float = Query(1.50, ge=0.0, le=100.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Triggers the chained reconciliation matching engine:
    1. Exact Matcher (Reference, Account, Currency, Amount)
    2. Rule-Based Matcher (Same Reference, with customizable Date and Amount Tolerances)
    3. Fuzzy Matcher (Description likeness score validation above threshold)
    
    Any transactions remaining unmatched are automatically logged to the Exception Queue.
    """
    # 1. Load active unmatched transactions
    bank_txs = db.query(NormalizedTransaction).filter(
        NormalizedTransaction.source_system == "bank_statement",
        NormalizedTransaction.status == "UNMATCHED"
    ).all()

    ledger_txs = db.query(NormalizedTransaction).filter(
        NormalizedTransaction.source_system == "internal_ledger",
        NormalizedTransaction.status == "UNMATCHED"
    ).all()

    if not bank_txs and not ledger_txs:
        return {
            "success": True,
            "message": "No unmatched transactions available for reconciliation.",
            "summary": {"exact_matches": 0, "rule_matches": 0, "fuzzy_matches": 0, "exceptions_raised": 0}
        }

    total_exact = 0
    total_rule = 0
    total_fuzzy = 0
    total_exceptions = 0
    
    # Track all matched pairs
    matched_pairs = []

    # ==========================================================================
    # Pipeline Step 1: Exact Matching
    # ==========================================================================
    exact_matcher = ExactMatcher()
    exact_pairs = exact_matcher.reconcile(db, bank_txs, ledger_txs)
    matched_pairs.extend(exact_pairs)
    total_exact = len(exact_pairs)

    # ==========================================================================
    # Pipeline Step 2: Rule-Based Matching (Tolerances)
    # ==========================================================================
    rule_matcher = RuleBasedMatcher(
        date_tolerance_days=date_tolerance_days, 
        amount_tolerance=amount_tolerance
    )
    rule_pairs = rule_matcher.reconcile(db, bank_txs, ledger_txs)
    matched_pairs.extend(rule_pairs)
    total_rule = len(rule_pairs)

    # ==========================================================================
    # Pipeline Step 3: Fuzzy Description Matching
    # ==========================================================================
    fuzzy_matcher = FuzzyMatcher(threshold=fuzzy_threshold)
    fuzzy_pairs = fuzzy_matcher.reconcile(db, bank_txs, ledger_txs)
    matched_pairs.extend(fuzzy_pairs)
    total_fuzzy = len(fuzzy_pairs)

    # ==========================================================================
    # Persist Matches and Update Transactions
    # ==========================================================================
    for b_tx, l_tx, score, rule_applied in matched_pairs:
        # Create standard Match record
        match_record = MatchResult(
            match_type="exact" if "EXACT" in rule_applied else ("rule_based" if "TOLERANCE" in rule_applied else "fuzzy"),
            matching_rules_applied=rule_applied,
            similarity_score=score,
            resolved_by="system"
        )
        db.add(match_record)
        db.flush()  # Extract auto-incremented match ID
        
        # Link transactions to the match
        b_tx.match_id = match_record.id
        b_tx.status = "MATCHED"
        
        l_tx.match_id = match_record.id
        l_tx.status = "MATCHED"
        
        # Audit Log individual match discovery
        AuditService.log_action(
            db=db,
            action="MATCH_FOUND",
            performed_by="system",
            table_name="match_results",
            record_id=match_record.id,
            new_value={
                "bank_transaction_id": b_tx.id,
                "ledger_transaction_id": l_tx.id,
                "similarity_score": score,
                "rule": rule_applied
            },
            comments=f"Automated match discovered via {rule_applied}"
        )

    # ==========================================================================
    # Pipeline Step 4: Populate Exceptions Queue with remaining UNMATCHED
    # ==========================================================================
    remaining_bank = db.query(NormalizedTransaction).filter(
        NormalizedTransaction.source_system == "bank_statement",
        NormalizedTransaction.status == "UNMATCHED"
    ).all()

    remaining_ledger = db.query(NormalizedTransaction).filter(
        NormalizedTransaction.source_system == "internal_ledger",
        NormalizedTransaction.status == "UNMATCHED"
    ).all()

    for tx in remaining_bank + remaining_ledger:
        # Check if exception record already exists to avoid duplication
        exists = db.query(ExceptionQueue).filter(
            ExceptionQueue.transaction_id == tx.id,
            ExceptionQueue.status == "OPEN"
        ).first()
        
        if not exists:
            # Update status to EXCEPTION
            tx.status = "EXCEPTION"
            
            error_type = "unmatched_bank_entry" if tx.source_system == "bank_statement" else "unmatched_ledger_entry"
            
            exc_record = ExceptionQueue(
                transaction_id=tx.id,
                status="OPEN",
                error_type=error_type,
                comments="Failed auto-reconciliation pipelines"
            )
            db.add(exc_record)
            total_exceptions += 1

    db.commit()

    # Log overall execution summary in the audit trail
    summary_msg = (
        f"Reconciliation Run Complete. Matches found: "
        f"{total_exact} exact, {total_rule} rule-based, {total_fuzzy} fuzzy. "
        f"Pushed {total_exceptions} transactions to Exceptions queue."
    )
    AuditService.log_action(
        db=db,
        action="RECONCILIATION_RUN",
        performed_by=current_user.username,
        comments=summary_msg
    )

    return {
        "success": True,
        "message": "Reconciliation job completed successfully.",
        "summary": {
            "exact_matches": total_exact,
            "rule_matches": total_rule,
            "fuzzy_matches": total_fuzzy,
            "exceptions_raised": total_exceptions
        }
    }
