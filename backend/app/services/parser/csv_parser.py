import csv
import io
from datetime import datetime, date
from typing import Dict, List, Generator, Any, Union
from app.services.parser.base import BaseParser


class ParserError(Exception):
    """Base exception for all statement parsers."""
    pass


class HeaderValidationError(ParserError):
    """Exception raised when CSV headers do not match required bank mappings."""
    pass


class RowParsingError(ParserError):
    """Exception raised when a specific CSV row fails validation or type casting."""
    pass


class CSVParser(BaseParser):
    def __init__(self):
        self.errors: List[Dict[str, Any]] = []

    def parse(self, file_content: bytes, filename: str = "", bank_mapping: dict = None) -> List[Dict[str, Any]]:
        """
        Backward-compatible parse method matching BaseParser signature.
        Loads the bytes into a string stream and processes it via parse_stream.
        """
        content_str = file_content.decode("utf-8", errors="ignore")
        # Split into lines to stream
        lines = content_str.splitlines()
        return list(self.parse_stream(lines, bank_mapping=bank_mapping))

    def parse_stream(
        self, 
        line_source: Any, 
        bank_mapping: dict = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Scalable streaming parser for large CSV files.
        Takes an iterable/generator of lines (bytes or strings) and yields parsed transaction dictionaries.
        Keeps track of corrupt rows in self.errors.
        """
        self.errors = []
        
        # 1. Adapt line source to decode bytes on the fly
        def decoded_lines():
            for line in line_source:
                if isinstance(line, bytes):
                    yield line.decode("utf-8", errors="ignore")
                else:
                    yield line

        lines_iter = decoded_lines()
        
        # 2. Extract configurations
        delimiter = ","
        skip_rows = 0
        has_header = True
        date_formats = None
        defaults = {}
        
        if bank_mapping:
            delimiter = bank_mapping.get("delimiter", ",")
            skip_rows = bank_mapping.get("skip_rows", 0)
            has_header = bank_mapping.get("has_header", True)
            date_formats = bank_mapping.get("date_formats", None)
            defaults = bank_mapping.get("defaults", {})

        # 3. Skip rows if specified
        for _ in range(skip_rows):
            try:
                next(lines_iter)
            except StopIteration:
                return

        # 4. Initialize CSV reader over the remaining generator
        reader = csv.reader(lines_iter, delimiter=delimiter)
        
        # 5. Extract and resolve headers
        try:
            raw_headers = next(reader)
            headers = [h.strip().lower() for h in raw_headers]
        except StopIteration:
            raise HeaderValidationError("Empty CSV source, no headers could be extracted.")

        index_map = self._resolve_headers(headers, bank_mapping)

        # 6. Stream and parse rows
        line_no = skip_rows + 1  # Track original line numbers
        for row in reader:
            line_no += 1
            if not row:
                continue
                
            # Handle row size discrepancies
            if len(row) < len(index_map):
                self.errors.append({
                    "row_number": line_no,
                    "raw_row": row,
                    "error_message": f"Row has only {len(row)} columns, expected at least {len(index_map)}"
                })
                continue

            try:
                # Parse amount
                amount_str = row[index_map["amount"]]
                amount = self._clean_amount(amount_str)

                # Parse transaction date
                date_str = row[index_map["transaction_date"]]
                tx_date = self._parse_date(date_str, date_formats)

                # Parse optional value date
                val_date = tx_date
                if "value_date" in index_map and index_map["value_date"] < len(row):
                    v_str = row[index_map["value_date"]]
                    if v_str.strip():
                        try:
                            val_date = self._parse_date(v_str, date_formats)
                        except RowParsingError:
                            pass  # Fall back to transaction date

                # Parse other metadata
                reference = ""
                if "reference" in index_map and index_map["reference"] < len(row):
                    reference = row[index_map["reference"]].strip()

                description = ""
                if "description" in index_map and index_map["description"] < len(row):
                    description = row[index_map["description"]].strip()

                bank_account = defaults.get("bank_account", "UNKNOWN_ACCOUNT")
                if "bank_account" in index_map and index_map["bank_account"] < len(row):
                    bank_account = row[index_map["bank_account"]].strip()

                currency = defaults.get("currency", "USD")
                if "currency" in index_map and index_map["currency"] < len(row):
                    c_str = row[index_map["currency"]].strip().upper()
                    if c_str:
                        currency = c_str

                yield {
                    "transaction_date": tx_date.strftime("%Y-%m-%d"),
                    "value_date": val_date.strftime("%Y-%m-%d"),
                    "amount": amount,
                    "currency": currency,
                    "reference": reference,
                    "description": description,
                    "bank_account": bank_account
                }
            except Exception as e:
                self.errors.append({
                    "row_number": line_no,
                    "raw_row": row,
                    "error_message": str(e)
                })
                continue

    def _resolve_headers(self, headers: List[str], mapping: dict = None) -> Dict[str, int]:
        aliases = {
            "transaction_date": ["date", "transaction date", "value date", "post date", "booking date", "tx_date", "dt"],
            "amount": ["amount", "transaction amount", "value", "amt", "tx_amount", "amount usd", "trx amount"],
            "reference": ["reference", "ref", "ref no", "transaction reference", "endtoendid", "payment reference", "ref_no"],
            "description": ["description", "desc", "memo", "narration", "transaction details", "additional info", "remittance info"],
            "bank_account": ["account", "account number", "iban", "bank account", "acct", "acc_no"],
            "currency": ["currency", "ccy", "curr"]
        }
        
        resolved_mapping = {}
        
        # Apply custom bank config mappings if provided
        if mapping and "column_mapping" in mapping:
            custom_map = mapping["column_mapping"]
            for std_key, expected_header in custom_map.items():
                expected_headers = [expected_header.strip().lower()] if isinstance(expected_header, str) else [h.strip().lower() for h in expected_header]
                for h in expected_headers:
                    if h in headers:
                        resolved_mapping[std_key] = headers.index(h)
                        break
                        
        # Fall back to default aliases for unmapped standard keys
        for std_key, keywords in aliases.items():
            if std_key not in resolved_mapping:
                for kw in keywords:
                    if kw in headers:
                        resolved_mapping[std_key] = headers.index(kw)
                        break
                        
        # Ensure we resolved critical fields
        required_columns = ["transaction_date", "amount"]
        missing = [col for col in required_columns if col not in resolved_mapping]
        if missing:
            raise HeaderValidationError(
                f"CSV parsing error: Could not resolve critical headers {missing}. "
                f"Found headers: {headers}. Please configure custom column mappings if required."
            )
            
        return resolved_mapping

    def _clean_amount(self, amt_str: str) -> float:
        amt_str = amt_str.strip().replace("$", "").replace("€", "").replace("£", "")
        if not amt_str:
            raise RowParsingError("Amount field is empty")

        # European format dot-thousands / comma-decimals detection
        if "," in amt_str and "." in amt_str:
            dot_idx = amt_str.rfind(".")
            comma_idx = amt_str.rfind(",")
            if comma_idx > dot_idx:
                amt_str = amt_str.replace(".", "").replace(",", ".")
            else:
                amt_str = amt_str.replace(",", "")
        elif "," in amt_str:
            parts = amt_str.split(",")
            if len(parts) == 2 and len(parts[1]) == 2:
                amt_str = amt_str.replace(",", ".")
            else:
                amt_str = amt_str.replace(",", "")

        # Retain digits, signs, decimal points
        amt_str = "".join(c for c in amt_str if c.isdigit() or c in ".-+")
        
        try:
            return float(amt_str)
        except ValueError:
            raise RowParsingError(f"Could not convert amount value '{amt_str}' to float")

    def _parse_date(self, date_str: str, date_formats: list = None) -> date:
        date_str = date_str.strip()
        if not date_str:
            raise RowParsingError("Date field is empty")
            
        formats = date_formats or [
            "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", 
            "%Y/%m/%d", "%d.%m.%Y", "%y%m%d"
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
                
        raise RowParsingError(f"Date value '{date_str}' does not match any supported format.")
