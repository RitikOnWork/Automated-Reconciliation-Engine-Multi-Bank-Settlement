import sys
import json
import hashlib
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
import app.db.base
from app.models.audit import AuditLog

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

GENESIS_SALT = "6a09e667f3bcc908b2fb1366ea957d3e3cd1e157e36614b533e46c761b626e6c"

class ImmutableAuditLogger:
    """
    Core service implementing cryptographic hash-chaining (ledger blockchain)
    for compliance audit logging and database tamper detection.
    """

    @staticmethod
    def serialize_value(val: Any) -> str:
        """Standardizes dictionary/object serialization to prevent dictionary-ordering variance."""
        if val is None:
            return ""
        if isinstance(val, (dict, list)):
            return json.dumps(val, sort_keys=True, separators=(',', ':'))
        return str(val)

    @classmethod
    def calculate_hash(
        cls,
        action: str,
        table_name: Optional[str],
        record_id: Optional[int],
        old_value: Optional[str],
        new_value: Optional[str],
        timestamp: datetime,
        performed_by: str,
        ip_address: Optional[str],
        comments: Optional[str],
        previous_hash: Optional[str]
    ) -> str:
        """
        Computes a SHA-256 fingerprint for the audit log entry.
        Guarantees exact character ordering by joining fields with specific boundaries.
        """
        if timestamp:
            # Force naive datetime objects to be treated as UTC without shift conversion
            ts_utc = timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)
            ts_str = ts_utc.isoformat()
        else:
            ts_str = ""
        
        payload_components = [
            str(action or ""),
            str(table_name or ""),
            str(record_id or ""),
            cls.serialize_value(old_value),
            cls.serialize_value(new_value),
            ts_str,
            str(performed_by or ""),
            str(ip_address or ""),
            str(comments or ""),
            str(previous_hash or GENESIS_SALT)
        ]
        
        payload_str = "||".join(payload_components)
        return hashlib.sha256(payload_str.encode('utf-8')).hexdigest()

    @classmethod
    def log_action(
        cls,
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
        Pushes a new event to the compliance audit ledger.
        Fetches the previous transaction block to calculate and append the linked SHA-256 hash.
        """
        # Retrieve the latest audit log to establish the previous hash link
        latest_log = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        prev_hash = latest_log.hash if latest_log else GENESIS_SALT

        # Convert dictionary values to standardized JSON strings
        old_str = cls.serialize_value(old_value) if old_value else None
        new_str = cls.serialize_value(new_value) if new_value else None
        utc_now = datetime.now(timezone.utc)

        # Calculate cryptographic hash signature
        rec_hash = cls.calculate_hash(
            action=action,
            table_name=table_name,
            record_id=record_id,
            old_value=old_str,
            new_value=new_str,
            timestamp=utc_now,
            performed_by=performed_by,
            ip_address=ip_address,
            comments=comments,
            previous_hash=prev_hash
        )

        log_entry = AuditLog(
            action=action,
            table_name=table_name,
            record_id=record_id,
            old_value=old_str,
            new_value=new_str,
            timestamp=utc_now,
            performed_by=performed_by,
            ip_address=ip_address,
            comments=comments,
            previous_hash=prev_hash,
            hash=rec_hash
        )

        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry

    @classmethod
    def verify_chain(cls, db: Session) -> Dict[str, Any]:
        """
        Scans all audit log blocks, recomputes each SHA-256 checksum,
        verifies correct chaining sequence, and reports database tampering.
        """
        logs = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
        
        is_valid = True
        tampered_ids = []
        errors = []
        expected_prev_hash = GENESIS_SALT

        for i, log in enumerate(logs):
            # 1. Verify previous_hash link match
            if log.previous_hash != expected_prev_hash:
                is_valid = False
                tampered_ids.append(log.id)
                errors.append({
                    "record_id": log.id,
                    "error_type": "BROKEN_LINK_CHAIN",
                    "details": f"Block link mismatch at Index {log.id}. Stored previous: '{log.previous_hash[:10]}...', Expected: '{expected_prev_hash[:10]}...'"
                })

            # 2. Re-serialize data fields exactly as they exist in DB
            computed_hash = cls.calculate_hash(
                action=log.action,
                table_name=log.table_name,
                record_id=log.record_id,
                old_value=log.old_value,
                new_value=log.new_value,
                timestamp=log.timestamp,
                performed_by=log.performed_by,
                ip_address=log.ip_address,
                comments=log.comments,
                previous_hash=log.previous_hash
            )

            # 3. Verify computed hash signature matches stored DB hash
            if log.hash != computed_hash:
                is_valid = False
                if log.id not in tampered_ids:
                    tampered_ids.append(log.id)
                errors.append({
                    "record_id": log.id,
                    "error_type": "SIGNATURE_MUTATED",
                    "details": f"Signature mismatch at Index {log.id}. Stored hash: '{log.hash[:10]}...', Computed: '{computed_hash[:10]}...'"
                })

            # Set current hash as the expected parent hash for the next block
            expected_prev_hash = log.hash

        return {
            "is_valid": is_valid,
            "block_count": len(logs),
            "tampered_record_ids": tampered_ids,
            "errors": errors
        }

def run_audit_logger_tests():
    """Self-contained SQLite integration test showcasing audit ledger immutability and tamper detection."""
    print("=" * 100)
    print("🛡️ RUNNING IMMUTABLE COMPLIANCE AUDIT LEDGER SIMULATOR")
    print("=" * 100)

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.db.base import Base
    except ImportError as e:
        print(f"Failed to load SQLAlchemy dependency components: {e}")
        return

    # 1. Setup in-memory SQLite database environment
    test_engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    db = SessionLocal()

    print("Seeding compliance actions into ledger chain...")
    
    # Block 1
    ImmutableAuditLogger.log_action(
        db=db,
        action="STATEMENT_UPLOAD",
        performed_by="operator_dan",
        table_name="raw_transactions",
        record_id=1,
        new_value={"filename": "MT940_MAY.txt", "size": "104 KB"},
        comments="Ingested monthly statement bank postings"
    )

    # Block 2
    ImmutableAuditLogger.log_action(
        db=db,
        action="RECONCILIATION_RUN",
        performed_by="system_cron",
        comments="Automatic match run discovered 124 matches, raised 14 exceptions"
    )

    # Block 3
    ImmutableAuditLogger.log_action(
        db=db,
        action="EXCEPTION_RESOLVE",
        performed_by="compliance_officer_sally",
        table_name="exceptions",
        record_id=45,
        old_value={"status": "OPEN", "discrepancy": "$1.20"},
        new_value={"status": "RESOLVED", "discrepancy": "$0.00"},
        comments="Approved small clearing fee discrepancy"
    )

    print("Verifying Initial Compliance Chain Integrity...")
    res = ImmutableAuditLogger.verify_chain(db)
    print(f"  └─ Block Count    : {res['block_count']}")
    print(f"  └─ Ledger Status  : {'🟢 SECURE / VERIFIED' if res['is_valid'] else '🔴 CORRUPTED'}")
    print(f"  └─ Errors Detected: {len(res['errors'])}")
    assert res["is_valid"] == True

    print("\n" + "-" * 100)
    print("😈 SIMULATING MOCK DATABASE INJECTION ATTACK (DIRECT ROW TAMPERING)")
    print("-" * 100)
    
    # Fetch Block 2 and directly update comments bypassing the logging engine API
    malicious_row = db.query(AuditLog).filter(AuditLog.id == 2).first()
    print(f"Original Block 2 Comments: '{malicious_row.comments}'")
    
    malicious_row.comments = "Automatic match run discovered 1000 matches (HACKED STATEMENT DATA)"
    db.commit()
    print(f"Mutated Block 2 Comments : '{malicious_row.comments}'")

    print("\nRe-scanning and Verifying Compliance Chain Integrity after direct manipulation...")
    res_tampered = ImmutableAuditLogger.verify_chain(db)
    print(f"  └─ Block Count    : {res_tampered['block_count']}")
    print(f"  └─ Ledger Status  : {'🟢 SECURE / VERIFIED' if res_tampered['is_valid'] else '🔴 COMPLIANCE WARNING: TAMPERING DETECTED!'}")
    print(f"  └─ Corrupted IDs  : {res_tampered['tampered_record_ids']}")
    print(f"  └─ Broken Blocks  :")
    
    for err in res_tampered["errors"]:
        print(f"     ├── [Record ID {err['record_id']} - {err['error_type']}]")
        print(f"     └── Details: {err['details']}")

    assert res_tampered["is_valid"] == False
    print("=" * 100)

if __name__ == "__main__":
    run_audit_logger_tests()
