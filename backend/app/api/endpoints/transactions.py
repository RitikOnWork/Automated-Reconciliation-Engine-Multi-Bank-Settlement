from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.schemas.transaction import TransactionResponse
from app.security import get_current_user
from app.services.normalization import NormalizationService
from app.services.parser.camt053 import CAMT053Parser
from app.services.parser.csv_parser import CSVParser
from app.services.parser.mt940 import MT940Parser
from app.services.audit import AuditService
from app.models.transaction import NormalizedTransaction

router = APIRouter()


@router.post("/upload", response_model=List[TransactionResponse], status_code=status.HTTP_201_CREATED)
async def upload_bank_statement(
    file_type: str = Form(..., description="mt940, camt053, csv"),
    source_system: str = Form(..., description="bank_statement, internal_ledger"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ingests and parses bank statement files or internal ledger logs.
    Supported file types: mt940 (SWIFT), camt053 (XML), csv (Spreadsheet).
    """
    file_bytes = await file.read()
    
    # 1. Resolve appropriate parser
    if file_type.lower() == "mt940":
        parser = MT940Parser()
    elif file_type.lower() == "camt053":
        parser = CAMT053Parser()
    elif file_type.lower() == "csv":
        parser = CSVParser()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: {file_type}. Supported options: mt940, camt053, csv."
        )

    # 2. Parse file content
    try:
        parsed_records = parser.parse(file_bytes, filename=file.filename)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Statement parsing failed: {str(e)}"
        )

    if not parsed_records:
        raise HTTPException(
            status_code=status.HTTP_200_OK,
            detail="Statement parsed successfully but contained 0 valid transactions or matches."
        )

    # 3. Normalize records and persist in database
    try:
        stored_records = NormalizationService.normalize_and_store(
            db=db,
            parsed_records=parsed_records,
            source_system=source_system
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to normalize and persist records: {str(e)}"
        )

    # 4. Audit trail logging
    AuditService.log_action(
        db=db,
        action="STATEMENT_UPLOADED",
        performed_by=current_user.username,
        comments=f"Uploaded {file.filename} (Type: {file_type}, Ingested: {len(stored_records)} transactions)"
    )

    return stored_records


@router.get("/", response_model=List[TransactionResponse])
def get_transactions(
    source_system: Optional[str] = Query(None, description="bank_statement, internal_ledger"),
    status: Optional[str] = Query(None, description="UNMATCHED, MATCHED, EXCEPTION"),
    bank_account: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Queries and lists normalized bank statement and ledger transactions.
    """
    query = db.query(NormalizedTransaction)
    
    if source_system:
        query = query.filter(NormalizedTransaction.source_system == source_system)
    if status:
        query = query.filter(NormalizedTransaction.status == status)
    if bank_account:
        query = query.filter(NormalizedTransaction.bank_account == bank_account)
        
    return query.order_by(NormalizedTransaction.transaction_date.desc()).offset(offset).limit(limit).all()
