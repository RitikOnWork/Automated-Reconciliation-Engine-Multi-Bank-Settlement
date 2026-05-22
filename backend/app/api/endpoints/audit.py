from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.models.audit import AuditLog
from app.schemas.audit import AuditLogResponse, VerificationResultResponse
from app.security import get_current_user
from app.services.audit_logger import ImmutableAuditLogger

router = APIRouter()


@router.get("/", response_model=List[AuditLogResponse])
def get_audit_trail_logs(
    action: Optional[str] = Query(None),
    performed_by: Optional[str] = Query(None),
    table_name: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves read-only historical operational logs for compliance audits.
    """
    query = db.query(AuditLog)
    
    if action:
        query = query.filter(AuditLog.action == action)
    if performed_by:
        query = query.filter(AuditLog.performed_by == performed_by)
    if table_name:
        query = query.filter(AuditLog.table_name == table_name)
        
    return query.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()


@router.post("/verify", response_model=VerificationResultResponse)
def verify_compliance_ledger_integrity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Runs a real-time cryptographic scanner over all compliance logs,
    validating block signature continuity and checking for database row tampering.
    """
    if current_user.role.lower() not in ["admin", "system"]:
        raise HTTPException(
            status_code=403,
            detail="Insufficient role clearance. Compliance scan requires administrative permissions."
        )
    return ImmutableAuditLogger.verify_chain(db)
