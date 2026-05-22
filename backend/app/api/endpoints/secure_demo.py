from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.schemas.secure_demo import SecureTransactionResponse, AdminOnlyStatusResponse
from app.security import RoleChecker, get_current_user
from app.utils.pan_masking import mask_pan
from app.services.audit import AuditService

router = APIRouter()

# Static mock database records representing sensitive production financial details
MOCK_SECURE_DATA = [
    {
        "id": 1,
        "card_number": "4111-2222-3333-4444",
        "bank_account": "US89370400440532013000",
        "holder_name": "Acme Corporation Inc.",
        "amount": 25000.00,
        "currency": "USD"
    },
    {
        "id": 2,
        "card_number": "5555-6666-7777-8888",
        "bank_account": "GB29UKPA60161331926819",
        "holder_name": "Globex Financial Group",
        "amount": 1420500.50,
        "currency": "GBP"
    },
    {
        "id": 3,
        "card_number": "3782-822463-10005",
        "bank_account": "DE53370400440532013000",
        "holder_name": "Initech Consulting Ltd",
        "amount": 9230.15,
        "currency": "EUR"
    }
]


@router.get("/data", response_model=List[SecureTransactionResponse])
def get_secure_financial_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["admin", "analyst", "viewer"]))
):
    """
    Retrieves high-value transaction records protected under PCI-DSS compliance bounds.
    - Admin users receive raw, unmasked account details.
    - Analyst and Viewer users automatically receive masked account and PAN strings.
    - Log-access events are saved directly to the immutable cryptographic ledger.
    """
    user_role = current_user.role.lower()
    is_admin = user_role in ["admin", "system"]
    
    processed_records = []
    for record in MOCK_SECURE_DATA:
        if is_admin:
            # Admins view original raw numbers
            processed_records.append(SecureTransactionResponse(**record))
        else:
            # Mask sensitive components for analyst/viewer roles
            masked_record = record.copy()
            masked_record["card_number"] = mask_pan(record["card_number"])
            masked_record["bank_account"] = mask_pan(record["bank_account"])
            processed_records.append(SecureTransactionResponse(**masked_record))
            
    # Audit log the read action to record the user access type
    AuditService.log_action(
        db=db,
        action="SECURE_DATA_ACCESS",
        performed_by=current_user.username,
        table_name="secure_demo_data",
        comments=f"Accessed secure financial records (Role: {current_user.role}, Masked: {not is_admin})"
    )
    
    return processed_records


@router.post("/admin-only", response_model=AdminOnlyStatusResponse)
def execute_administrative_operation(
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["admin"]))
):
    """
    High-value administrative control endpoint restricted strictly to Admin users.
    Triggers administrative override workflows and records actions in the compliance log.
    """
    # Audit log this high-value admin action
    AuditService.log_action(
        db=db,
        action="ADMIN_HIGH_VALUE_OP",
        performed_by=current_user.username,
        table_name="system_config",
        comments="Executed secure administrative action on secure demo endpoint"
    )
    
    return AdminOnlyStatusResponse(
        status="success",
        message="Administrative action executed successfully under compliance control.",
        caller=current_user.username,
        role=current_user.role
    )
