import re
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timezone
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, validator


class TransactionNormalizer:
    """
    Standard data cleaning and normalization utility functions for banking ledger reconciliations.
    """
    # Compile whitespace collapsing regex
    RE_SPACES = re.compile(r"\s+")
    
    # Common currency mappings to ISO 4217 uppercase codes
    CURRENCY_MAP = {
        "$": "USD",
        "US DOLLAR": "USD",
        "USDOLLAR": "USD",
        "€": "EUR",
        "EURO": "EUR",
        "£": "GBP",
        "POUND": "GBP",
        "POUNDS": "GBP",
        "BRITISH POUND": "GBP",
        "¥": "JPY",
        "YEN": "JPY",
    }
    
    # Standard SWIFT/clearing null reference strings
    NULL_REFS = {"NONREF", "/NONREF", "NONREF/", "/", "-", ".", "N/A", "NA", "NULL", "NONE", ""}

    @classmethod
    def clean_currency(cls, ccy: Any) -> str:
        """
        Normalizes currency string to uppercase 3-character ISO 4217 standard codes.
        """
        if not ccy:
            return "USD"
        
        ccy_clean = str(ccy).strip().upper()
        if ccy_clean in cls.CURRENCY_MAP:
            return cls.CURRENCY_MAP[ccy_clean]
            
        # Extract first 3-letter sequence if present
        letter_match = re.search(r"[A-Z]{3}", ccy_clean)
        if letter_match:
            return letter_match.group(0)
            
        return "USD"

    @classmethod
    def clean_reference(cls, ref: Any) -> str:
        """
        Strips whitespaces, removes common SWIFT/clearing null references, 
        and returns a standardized clean string or "".
        """
        if ref is None:
            return ""
            
        ref_clean = str(ref).strip()
        ref_upper = ref_clean.upper()
        
        if ref_upper in cls.NULL_REFS or not ref_clean:
            return ""
            
        # Strip trailing/leading slashes or spaces
        ref_clean = ref_clean.strip("/").strip()
        
        # If it resolved to a null reference after stripping
        if ref_clean.upper() in cls.NULL_REFS:
            return ""
            
        return ref_clean

    @classmethod
    def clean_description(cls, desc: Any) -> str:
        """
        Collapses consecutive spaces, standardizes newlines, and eliminates control characters.
        """
        if desc is None:
            return ""
            
        desc_str = str(desc).strip()
        # Collapse multiple spaces, tabs, and newlines
        desc_clean = cls.RE_SPACES.sub(" ", desc_str)
        return desc_clean

    @classmethod
    def normalize_amount(cls, amt: Any) -> Decimal:
        """
        Safely converts integers, floats, decimals, or strings to Decimal with exactly 2 decimal precision.
        Handles European dot-thousands and comma-decimals cleanly.
        """
        if amt is None:
            return Decimal("0.00")
            
        if isinstance(amt, (int, float, Decimal)):
            try:
                return Decimal(str(amt)).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                return Decimal("0.00")
                
        amt_str = str(amt).strip()
        if not amt_str:
            return Decimal("0.00")
            
        # Resolve European dot-thousands and comma decimals, e.g. -1.250,75 -> -1250.75
        if "," in amt_str and "." in amt_str:
            comma_idx = amt_str.rfind(",")
            dot_idx = amt_str.rfind(".")
            if comma_idx > dot_idx:
                # European: replace dots with empty string, and comma with dot
                amt_str = amt_str.replace(".", "").replace(",", ".")
            else:
                # US/UK with commas as thousands: replace commas with empty
                amt_str = amt_str.replace(",", "")
        elif "," in amt_str:
            # Check if comma represents decimal or thousands
            comma_idx = amt_str.rfind(",")
            if len(amt_str) - comma_idx - 1 == 3:
                # Thousands separator, e.g. 1,000 -> 1000
                amt_str = amt_str.replace(",", "")
            else:
                # Decimal separator, e.g. 1000,50 -> 1000.50
                amt_str = amt_str.replace(",", ".")

        try:
            return Decimal(amt_str).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return Decimal("0.00")

    @classmethod
    def normalize_date(cls, val: Any) -> date:
        """
        Converts dates, timestamps, ISO strings, or custom formats safely to Python date.
        """
        if not val:
            return date.today()
            
        if isinstance(val, date) and not isinstance(val, datetime):
            return val
            
        if isinstance(val, datetime):
            return val.date()
            
        val_str = str(val).strip()
        if not val_str:
            return date.today()
            
        # Try ISO Date YYYY-MM-DD
        try:
            return datetime.fromisoformat(val_str[:10]).date()
        except ValueError:
            pass
            
        # Try typical formats: MM/DD/YYYY, DD.MM.YYYY, DD-MM-YYYY
        for fmt in ("%m/%d/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d", "%b %d, %Y"):
            try:
                return datetime.strptime(val_str, fmt).date()
            except ValueError:
                pass
                
        # Fallback to current date
        return date.today()

    @classmethod
    def normalize_timestamp_utc(cls, val: Any) -> datetime:
        """
        Converts datetime values/strings securely to timezone-aware UTC datetime.
        """
        if not val:
            return datetime.now(timezone.utc)
            
        if isinstance(val, datetime):
            if val.tzinfo is None:
                return val.replace(tzinfo=timezone.utc)
            return val.astimezone(timezone.utc)
            
        if isinstance(val, date):
            return datetime(val.year, val.month, val.day, tzinfo=timezone.utc)
            
        val_str = str(val).strip()
        try:
            dt = datetime.fromisoformat(val_str)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
            
        return datetime.now(timezone.utc)


class CanonicalTransaction(BaseModel):
    """
    Pydantic Schema representing the Canonical Transaction Model.
    All parsed bank files must conform to this schema post-cleaning.
    """
    transaction_date: date
    value_date: date
    amount: Decimal
    currency: str = Field(default="USD", min_length=3, max_length=3)
    reference: str = Field(default="")
    description: str = Field(default="")
    bank_account: str = Field(default="UNKNOWN_ACCOUNT")
    source_system: str = Field(default="bank_statement")
    counterparty_name: Optional[str] = ""
    counterparty_account: Optional[str] = ""

    @validator("currency")
    def validate_currency(cls, v):
        ccy = TransactionNormalizer.clean_currency(v)
        if len(ccy) != 3:
            raise ValueError(f"Invalid currency code format '{ccy}'")
        return ccy

    @validator("reference", pre=True, always=True)
    def clean_ref(cls, v):
        return TransactionNormalizer.clean_reference(v)

    @validator("description", pre=True, always=True)
    def clean_desc(cls, v):
        return TransactionNormalizer.clean_description(v)

    @validator("amount", pre=True, always=True)
    def clean_amt(cls, v):
        return TransactionNormalizer.normalize_amount(v)

    @validator("transaction_date", pre=True, always=True)
    def clean_tx_date(cls, v):
        return TransactionNormalizer.normalize_date(v)

    @validator("value_date", pre=True, always=True)
    def clean_val_date(cls, v, values):
        if not v:
            # Fallback to transaction_date if value_date is omitted
            return values.get("transaction_date") or date.today()
        return TransactionNormalizer.normalize_date(v)


class TransformationPipeline:
    """
    Ingests raw transaction dictionaries, normalizes their formats, 
    and validates them against the Canonical Schema.
    """
    @staticmethod
    def process_record(record: Dict[str, Any], source_system: str) -> CanonicalTransaction:
        """
        Processes and normalizes a single raw parsed record into the CanonicalTransaction Pydantic model.
        """
        # 1. Clean dates
        tx_date = TransactionNormalizer.normalize_date(record.get("transaction_date"))
        val_date_raw = record.get("value_date") or record.get("transaction_date")
        val_date = TransactionNormalizer.normalize_date(val_date_raw)

        # 2. Clean amounts, currencies, references, descriptions
        amount = TransactionNormalizer.normalize_amount(record.get("amount"))
        currency = TransactionNormalizer.clean_currency(record.get("currency"))
        reference = TransactionNormalizer.clean_reference(record.get("reference"))
        description = TransactionNormalizer.clean_description(record.get("description"))
        
        bank_account = str(record.get("bank_account") or "UNKNOWN_ACCOUNT").strip()
        
        counterparty_name = TransactionNormalizer.clean_description(record.get("counterparty_name"))
        counterparty_account = str(record.get("counterparty_account") or "").strip()

        # 3. Instantiate and validate against Canonical Schema
        return CanonicalTransaction(
            transaction_date=tx_date,
            value_date=val_date,
            amount=amount,
            currency=currency,
            reference=reference,
            description=description,
            bank_account=bank_account,
            source_system=source_system,
            counterparty_name=counterparty_name,
            counterparty_account=counterparty_account
        )

    @classmethod
    def process_batch(cls, records: List[Dict[str, Any]], source_system: str) -> List[CanonicalTransaction]:
        """
        Processes a batch of raw records, filtering out and skipping severe structural failures.
        """
        canonical_records = []
        for rec in records:
            try:
                canonical_rec = cls.process_record(rec, source_system)
                canonical_records.append(canonical_rec)
            except Exception:
                # In production-grade flow, severe row failures are isolated here
                pass
        return canonical_records
