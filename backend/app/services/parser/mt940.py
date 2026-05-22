import re
from datetime import datetime, date
from typing import Dict, List, Any, Optional
from app.services.parser.base import BaseParser


class MT940ParserError(Exception):
    """Base exception for MT940 parsing."""
    pass


class MT940ValidationError(MT940ParserError):
    """Exception raised when MT940 structural tags are missing or corrupt."""
    pass


class MT940RowParsingError(MT940ParserError):
    """Exception raised when a specific MT940 field or line fails validation."""
    pass


class MT940Parser(BaseParser):
    def __init__(self):
        self.errors: List[Dict[str, Any]] = []

        # 1. Regex patterns for standard SWIFT MT940 tags
        self.pattern_balance = re.compile(
            r"^(?P<dc>[CD])"                # C (Credit) or D (Debit)
            r"(?P<date>\d{6})"              # YYMMDD (Value Date)
            r"(?P<currency>[a-zA-Z]{3})"    # Currency code (e.g. EUR, USD, GBP)
            r"(?P<amount>\d+(?:,\d*)?)$"    # Amount (comma decimal separator)
        )

        self.pattern_61 = re.compile(
            r"^"
            r"(?P<date>\d{6})"              # YYMMDD (Transaction Date)
            r"(?P<entry_date>\d{4})?"        # MMDD (Value/Entry Date, optional)
            r"(?P<dc>RC|RD|C|D)"             # C/D/RC/RD Indicator
            r"(?P<funds_code>[a-zA-Z])?"     # Funds code (1 letter, optional)
            r"(?P<amount>\d+(?:,\d*)?)"      # Amount (comma decimal separator)
            # Transaction type code (handles standard 4-char SWIFT starting with N/F, or 3-char bank specific)
            r"(?P<tx_type>N[a-zA-Z0-9]{3}|F[a-zA-Z0-9]{3}|[a-zA-Z0-9]{3})"
            r"(?P<reference>.*)"             # Reference codes and supplementary info
            r"$"
        )

    def parse(self, file_content: bytes, filename: str = "") -> List[Dict[str, Any]]:
        """
        Parses raw MT940 statement files and returns a list of standardized transaction dictionaries.
        Complies with strict SWIFT MT940 standards for tag accumulation and multi-segment statement blocks.
        """
        content_str = file_content.decode("utf-8", errors="ignore")
        lines = content_str.splitlines()
        
        statements = self.parse_statements(lines)
        
        # Flatten all transactions from all parsed statement blocks for the caller
        all_transactions = []
        for stmt in statements:
            all_transactions.extend(stmt.get("transactions", []))
            
        return all_transactions

    def parse_statements(self, lines: List[str]) -> List[Dict[str, Any]]:
        """
        Parses multi-segment MT940 files, dividing them into statement blocks.
        Keeps track of parser errors inside self.errors.
        """
        self.errors = []
        statements = []
        
        # In-progress block state variables
        current_statement = {}
        current_transactions = []
        current_tx = None
        
        current_tag = None
        current_content = []
        
        # Helper to parse balances (:60F:, :62F:)
        def parse_bal(content: str, tag_name: str, line_no: int) -> Optional[Dict[str, Any]]:
            try:
                match = self.pattern_balance.match(content)
                if not match:
                    raise MT940RowParsingError(f"Malformed balance tag :{tag_name}: '{content}'")
                    
                dc = match.group("dc")
                date_str = match.group("date")
                currency = match.group("currency")
                amount_str = match.group("amount")
                
                amount = float(amount_str.replace(",", "."))
                if dc == "D":
                    amount = -amount
                    
                try:
                    bal_date = datetime.strptime(date_str, "%y%m%d").date()
                except ValueError:
                    bal_date = datetime.now().date()
                    
                return {
                    "status": "CREDIT" if dc == "C" else "DEBIT",
                    "date": bal_date.strftime("%Y-%m-%d"),
                    "currency": currency,
                    "amount": amount
                }
            except Exception as e:
                self.errors.append({
                    "line_number": line_no,
                    "raw_content": f":{tag_name}:{content}",
                    "error_message": str(e)
                })
                return None

        # Helper to flush a fully accumulated tag
        def flush_tag(tag: str, content_lines: List[str], line_no: int):
            nonlocal current_statement, current_transactions, current_tx
            if not tag:
                return
                
            content = "\n".join(content_lines).strip()
            
            try:
                if tag == "20":
                    # Start of a new statement segment. If we have an existing block, save it first.
                    if current_statement:
                        if current_tx:
                            current_transactions.append(current_tx)
                            current_tx = None
                        current_statement["transactions"] = current_transactions
                        statements.append(current_statement)
                        
                    current_statement = {
                        "transaction_reference": content,
                        "bank_account": "UNKNOWN_ACCOUNT",
                        "transactions": []
                    }
                    current_transactions = []
                    
                elif tag == "25":
                    if not current_statement:
                        # Auto-create block if :20: was skipped or missing
                        current_statement = {
                            "transaction_reference": "AUTO_GENERATED_REF",
                            "bank_account": content,
                            "transactions": []
                        }
                    else:
                        current_statement["bank_account"] = content
                        
                elif tag == "60F":
                    bal = parse_bal(content, "60F", line_no)
                    if bal and current_statement:
                        current_statement["opening_balance"] = bal
                        
                elif tag == "61":
                    # Flush the previous transaction in progress
                    if current_tx:
                        current_transactions.append(current_tx)
                        current_tx = None
                    
                    # Parse new statement line
                    current_tx = self._parse_tag_61(content, line_no)
                    
                elif tag == "86":
                    if current_tx:
                        # Clean multi-line descriptions into a single clean line
                        current_tx["description"] = content.replace("\n", " ").strip()
                        
                elif tag == "62F":
                    bal = parse_bal(content, "62F", line_no)
                    if bal and current_statement:
                        current_statement["closing_balance"] = bal
                        
            except Exception as e:
                self.errors.append({
                    "line_number": line_no,
                    "raw_content": f":{tag}:{content}",
                    "error_message": str(e)
                })

        # State loop over all lines
        for line_no, line in enumerate(lines, start=1):
            line_clean = line.strip()
            if not line_clean:
                continue
                
            # Regex to detect standard tag starts
            tag_match = re.match(r"^:([0-9]{2}[a-zA-Z]?):(.*)", line_clean)
            if tag_match:
                # Flush the tag we were just accumulating
                flush_tag(current_tag, current_content, line_no - 1)
                current_tag = tag_match.group(1)
                current_content = [tag_match.group(2).strip()]
            else:
                # Continuation line
                if current_tag:
                    current_content.append(line_clean)
                else:
                    # Ignore headers or envelopes like {1:...}
                    pass
                    
        # Flush the final tag and final transaction
        flush_tag(current_tag, current_content, len(lines))
        if current_tx:
            current_transactions.append(current_tx)
            
        if current_statement:
            current_statement["transactions"] = current_transactions
            statements.append(current_statement)

        # Post-Processing: Propagate Currency and Bank Account to all transactions in each block
        for stmt in statements:
            ccy = "USD"
            if "opening_balance" in stmt:
                ccy = stmt["opening_balance"]["currency"]
            elif "closing_balance" in stmt:
                ccy = stmt["closing_balance"]["currency"]
                
            acc = stmt.get("bank_account", "UNKNOWN_ACCOUNT")
            
            for tx in stmt.get("transactions", []):
                tx["currency"] = ccy
                tx["bank_account"] = acc
                
        return statements

    def _parse_tag_61(self, content: str, line_no: int) -> Dict[str, Any]:
        """
        Parses a :61: statement line according to SWIFT formats.
        Format: YYMMDD[MMDD]C|D|RC|RD[FundsCode]AmountTxTypeReference
        """
        match = self.pattern_61.match(content)
        if not match:
            raise MT940RowParsingError(f"Malformed statement line :61: '{content}'")
            
        date_str = match.group("date")
        entry_date_str = match.group("entry_date")
        dc = match.group("dc")
        funds = match.group("funds_code")
        amount_str = match.group("amount")
        tx_type = match.group("tx_type")
        ref_str = match.group("reference").strip()
        
        # Parse value date
        try:
            tx_date = datetime.strptime(date_str, "%y%m%d").date()
        except ValueError:
            raise MT940RowParsingError(f"Invalid transaction date '{date_str}'")
            
        # Parse entry date (falls back to transaction date if omitted)
        val_date = tx_date
        if entry_date_str:
            try:
                year_prefix = date_str[:2]
                val_date = datetime.strptime(f"{year_prefix}{entry_date_str}", "%y%m%d").date()
            except ValueError:
                pass
                
        # Parse amount sign
        amount = float(amount_str.replace(",", "."))
        if dc in ["D", "RD"]:
            amount = -amount
            
        # Split customer vs bank references (divided by //)
        customer_ref = ""
        bank_ref = ""
        if "//" in ref_str:
            parts = ref_str.split("//", 1)
            customer_ref = parts[0].strip()
            bank_ref = parts[1].strip()
        else:
            customer_ref = ref_str
            
        # Standardize empty references (handles common SWIFT null representations: NONREF, /NONREF, /, etc.)
        clean_ref = customer_ref.strip().upper()
        if clean_ref in ("NONREF", "/NONREF", "/NONREF/", "NONREF/", "/"):
            customer_ref = ""
            
        return {
            "transaction_date": tx_date.strftime("%Y-%m-%d"),
            "value_date": val_date.strftime("%Y-%m-%d"),
            "amount": amount,
            "currency": "USD",  # Will be overlaid by post-processing ccy
            "reference": customer_ref,
            "bank_reference": bank_ref,
            "transaction_type": tx_type,
            "description": "",
            "funds_code": funds or "",
            "bank_account": "UNKNOWN_ACCOUNT"  # Will be overlaid by post-processing acc
        }
