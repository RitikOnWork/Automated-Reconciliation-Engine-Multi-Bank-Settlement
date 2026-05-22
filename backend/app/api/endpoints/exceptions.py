from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.models.transaction import NormalizedTransaction
from app.models.match import MatchResult
from app.models.exception import ExceptionQueue
from app.schemas.exception import ExceptionResolve, ExceptionResponse
from app.security import get_current_user
from app.services.audit import AuditService

router = APIRouter()


@router.get("/", response_model=List[ExceptionResponse])
def get_exceptions(
    status: str = Query("OPEN", description="OPEN, RESOLVED, WAIVED"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves the list of transactions requiring manual review/reconciliation.
    """
    return db.query(ExceptionQueue).filter(
        ExceptionQueue.status == status.upper()
    ).offset(offset).limit(limit).all()


@router.put("/{id}/resolve", response_model=ExceptionResponse)
def resolve_exception(
    id: int,
    payload: ExceptionResolve,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Manually resolves an active exception transaction entry.
    Supported actions:
    - force_matched: Pairs the exception transaction with another manual transaction ID.
    - written_off: Flag transaction as resolved directly with written explanation (e.g. small variances).
    """
    exc_item = db.query(ExceptionQueue).filter(ExceptionQueue.id == id).first()
    if not exc_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Exception record not found"
        )
        
    if exc_item.status != "OPEN":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exception is already resolved or closed"
        )

    tx1 = db.query(NormalizedTransaction).filter(NormalizedTransaction.id == exc_item.transaction_id).first()
    if not tx1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated transaction not found"
        )

    # ==========================================================================
    # Action: Manual Pairing (Force Matched)
    # ==========================================================================
    if payload.action == "force_matched":
        if not payload.matched_transaction_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="matched_transaction_id is required for force_matched action"
            )

        tx2 = db.query(NormalizedTransaction).filter(NormalizedTransaction.id == payload.matched_transaction_id).first()
        if not tx2:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target matching transaction (ID: {payload.matched_transaction_id}) not found"
            )

        if tx1.source_system == tx2.source_system:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot force-match two transactions from the same source system."
            )

        # Create standard Manual Match Record
        manual_match = MatchResult(
            match_type="manual",
            matching_rules_applied="MANUAL_OPERATOR_OVERRIDE",
            similarity_score=100.0,
            resolved_by=current_user.username
        )
        db.add(manual_match)
        db.flush()  # Pull match ID

        # Link both transactions to the new match and update status
        tx1.match_id = manual_match.id
        tx1.status = "MATCHED"
        
        tx2.match_id = manual_match.id
        tx2.status = "MATCHED"

        # Check if the paired transaction also had an open exception and resolve it
        paired_exc = db.query(ExceptionQueue).filter(
            ExceptionQueue.transaction_id == tx2.id,
            ExceptionQueue.status == "OPEN"
        ).first()
        if paired_exc:
            paired_exc.status = "RESOLVED"
            paired_exc.resolution_action = "force_matched"
            paired_exc.resolved_at = datetime.now(timezone.utc)
            paired_exc.resolved_by = current_user.username
            paired_exc.comments = f"Automatically resolved via pairing with Transaction ID: {tx1.id}. User Comment: {payload.comments}"

        # Resolve primary exception
        exc_item.status = "RESOLVED"
        exc_item.resolution_action = "force_matched"
        exc_item.resolved_at = datetime.now(timezone.utc)
        exc_item.resolved_by = current_user.username
        exc_item.comments = payload.comments

        # Log audit trail
        AuditService.log_action(
            db=db,
            action="MANUAL_MATCH_RESOLVED",
            performed_by=current_user.username,
            table_name="exceptions",
            record_id=exc_item.id,
            new_value={"matched_transaction_id": tx2.id, "match_id": manual_match.id},
            comments=f"Operator manually paired bank tx {tx1.id} and ledger tx {tx2.id}. Justification: {payload.comments}"
        )

    # ==========================================================================
    # Action: Written Off / Waived
    # ==========================================================================
    elif payload.action in ["written_off", "adjusted"]:
        # Mark transaction as matched due to waiver write-off
        tx1.status = "MATCHED"
        
        exc_item.status = "RESOLVED"
        exc_item.resolution_action = payload.action
        exc_item.resolved_at = datetime.now(timezone.utc)
        exc_item.resolved_by = current_user.username
        exc_item.comments = payload.comments

        AuditService.log_action(
            db=db,
            action="EXCEPTION_WRITTEN_OFF",
            performed_by=current_user.username,
            table_name="exceptions",
            record_id=exc_item.id,
            comments=f"Operator wrote off exception (Transaction ID: {tx1.id}). Justification: {payload.comments}"
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported resolution action: {payload.action}"
        )

    db.commit()
    db.refresh(exc_item)
    return exc_item
