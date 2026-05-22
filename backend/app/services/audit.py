from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.models.audit import AuditLog
from app.services.audit_logger import ImmutableAuditLogger


class AuditService:
    @staticmethod
    def log_action(
        db: Session,
        action: str,
        performed_by: str,
        table_name: Optional[str] = None,
        record_id: Optional[int] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        comments: Optional[str] = None
    ) -> AuditLog:
        """
        Backward-compatible facade forwarding calls to the cryptographically chained
        ImmutableAuditLogger, ensuring all application audits are immediately upgraded.
        """
        return ImmutableAuditLogger.log_action(
            db=db,
            action=action,
            performed_by=performed_by,
            table_name=table_name,
            record_id=record_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            comments=comments
        )
