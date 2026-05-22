import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Any, Optional
from app.services.parser.base import BaseParser


class CAMT053ParserError(Exception):
    """Base exception for CAMT.053 parsing."""
    pass


class CAMT053ValidationError(CAMT053ParserError):
    """Exception raised when CAMT.053 structural tags are missing or corrupt."""
    pass


class CAMT053RowParsingError(CAMT053ParserError):
    """Exception raised when a specific CAMT.053 entry or transaction fails validation."""
    pass


class CAMT053Parser(BaseParser):
    def __init__(self):
        self.errors: List[Dict[str, Any]] = []

    def parse(self, file_content: bytes, filename: str = "") -> List[Dict[str, Any]]:
        """
        Parses high-fidelity ISO 20022 XML CAMT.053 statements.
        Extracts Account ID, Booking Date, Value Date, amount signs, references, counterparty, and descriptions.
        Handles nested <TxDtls> structures and multi-namespace XSD documents gracefully.
        """
        self.errors = []
        transactions = []
        
        try:
            # Handle empty file contents
            if not file_content.strip():
                raise CAMT053ValidationError("Empty XML file content.")
                
            try:
                root = ET.fromstring(file_content)
            except ET.ParseError as e:
                raise CAMT053ValidationError(f"Invalid XML syntax: {str(e)}")

            # XML namespace resolution
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"

            # Find statements inside Document (BkToCstmrStmt -> Stmt)
            stmts = self.find_all_elems(root, ".//Stmt", ns)
            if not stmts:
                # Fallback to direct Stmt root if root is Stmt
                if root.tag.endswith("Stmt"):
                    stmts = [root]
                else:
                    raise CAMT053ValidationError("No <Stmt> elements found in CAMT.053 document.")

            for stmt_idx, stmt in enumerate(stmts, start=1):
                # 1. Resolve Account IBAN / ID
                iban = self.get_text(stmt, "Acct/Id/IBAN", ns)
                othr_id = self.get_text(stmt, "Acct/Id/Othr/Id", ns)
                bank_account = iban or othr_id or "UNKNOWN_ACCOUNT"

                # 2. Loop transaction entries (Ntry)
                entries = self.find_all_elems(stmt, "Ntry", ns)
                for entry_idx, entry in enumerate(entries, start=1):
                    try:
                        self._parse_entry(entry, bank_account, ns, stmt_idx, entry_idx, transactions)
                    except Exception as e:
                        self.errors.append({
                            "statement_index": stmt_idx,
                            "entry_index": entry_idx,
                            "raw_content": ET.tostring(entry, encoding="utf-8").decode("utf-8")[:300] + "...",
                            "error_message": str(e)
                        })

        except Exception as e:
            # Catch top-level parser validation errors
            self.errors.append({
                "statement_index": 0,
                "entry_index": 0,
                "raw_content": file_content[:300].decode("utf-8", errors="ignore") + "...",
                "error_message": f"Global parsing failure: {str(e)}"
            })

        return transactions

    def _parse_entry(
        self,
        entry: ET.Element,
        bank_account: str,
        ns: str,
        stmt_idx: int,
        entry_idx: int,
        transactions: List[Dict[str, Any]]
    ):
        """
        Parses a single XML <Ntry> element.
        Decouples nested batch payments (<TxDtls>) if present.
        """
        # Parse entry-level values (which serve as fallbacks)
        amt_str = self.get_text(entry, "Amt", ns)
        if not amt_str:
            raise CAMT053RowParsingError(f"Missing transaction amount <Amt> in Entry #{entry_idx}")
            
        try:
            entry_amount = float(amt_str)
        except ValueError:
            raise CAMT053RowParsingError(f"Invalid transaction amount format '{amt_str}' in Entry #{entry_idx}")

        # Currency
        amt_elem = self.find_elem(entry, "Amt", ns)
        entry_currency = "USD"
        if amt_elem is not None and "Ccy" in amt_elem.attrib:
            entry_currency = amt_elem.attrib["Ccy"]

        # Indicator (CRDT / DBIT)
        entry_indicator = self.get_text(entry, "CdtDbtInd", ns)
        if not entry_indicator:
            raise CAMT053RowParsingError(f"Missing Credit/Debit indicator <CdtDbtInd> in Entry #{entry_idx}")
        if entry_indicator not in ("CRDT", "DBIT"):
            raise CAMT053RowParsingError(f"Invalid Credit/Debit indicator '{entry_indicator}' in Entry #{entry_idx}")

        if entry_indicator == "DBIT":
            entry_amount = -entry_amount

        # Ingestion Dates (Booking Date and Value Date)
        booking_dt_str = self.get_text(entry, "BookgDt/Dt", ns) or self.get_text(entry, "BookgDt/DtTm", ns)
        val_dt_str = self.get_text(entry, "ValDt/Dt", ns) or self.get_text(entry, "ValDt/DtTm", ns)

        if not booking_dt_str and not val_dt_str:
            raise CAMT053RowParsingError(f"Missing booking date and value date in Entry #{entry_idx}")

        booking_date = self._parse_date(booking_dt_str or val_dt_str)
        value_date = self._parse_date(val_dt_str or booking_dt_str)

        # Look for nested Transaction Details (<TxDtls>)
        tx_details = self.find_all_elems(entry, "NtryDtls/TxDtls", ns)
        if tx_details:
            # Scenario A: Decouple nested transactions
            for tx_idx, tx in enumerate(tx_details, start=1):
                try:
                    self._parse_tx_detail(
                        tx=tx,
                        bank_account=bank_account,
                        entry_currency=entry_currency,
                        entry_indicator=entry_indicator,
                        booking_date=booking_date,
                        value_date=value_date,
                        ns=ns,
                        stmt_idx=stmt_idx,
                        entry_idx=entry_idx,
                        tx_idx=tx_idx,
                        transactions=transactions
                    )
                except Exception as e:
                    self.errors.append({
                        "statement_index": stmt_idx,
                        "entry_index": entry_idx,
                        "transaction_index": tx_idx,
                        "raw_content": ET.tostring(tx, encoding="utf-8").decode("utf-8")[:300] + "...",
                        "error_message": f"Malformed sub-transaction details: {str(e)}"
                    })
        else:
            # Scenario B: Flat transaction entry (No <TxDtls>)
            ref = (
                self.get_text(entry, "Refs/EndToEndId", ns) or 
                self.get_text(entry, "Refs/UETR", ns) or 
                self.get_text(entry, "Refs/AcctSvcrRef", ns) or 
                self.get_text(entry, "Refs/TxId", ns)
            )
            
            # Standardize empty references
            if ref.upper() in ("NONREF", "/NONREF", "NONREF/", "/"):
                ref = ""
                
            bank_ref = (
                self.get_text(entry, "Refs/AcctSvcrRef", ns) or 
                self.get_text(entry, "Refs/UETR", ns) or 
                self.get_text(entry, "Refs/TxId", ns)
            )
            if bank_ref.upper() in ("NONREF", "/NONREF", "NONREF/", "/"):
                bank_ref = ""

            description = (
                self.get_text(entry, "AddtlNtryInf", ns) or 
                self.get_text(entry, "AddtlTxInf", ns)
            )

            # Look for unstructured remittance info
            ustrd_elems = self.find_all_elems(entry, "RmtInf/Ustrd", ns)
            if ustrd_elems:
                ustrd_texts = [el.text.strip() for el in ustrd_elems if el.text]
                if ustrd_texts:
                    description = " ".join(ustrd_texts)

            # Decouple debtor/creditor counterparty info
            counterparty_name = ""
            counterparty_account = ""
            if entry_indicator == "CRDT":
                # Money received: counterparty is Debtor
                counterparty_name = self.get_text(entry, "RltdPties/Dbtr/Nm", ns)
                counterparty_account = (
                    self.get_text(entry, "RltdPties/DbtrAcct/Id/IBAN", ns) or 
                    self.get_text(entry, "RltdPties/DbtrAcct/Id/Othr/Id", ns)
                )
            else:
                # Money paid: counterparty is Creditor
                counterparty_name = self.get_text(entry, "RltdPties/Cdtr/Nm", ns)
                counterparty_account = (
                    self.get_text(entry, "RltdPties/CdtrAcct/Id/IBAN", ns) or 
                    self.get_text(entry, "RltdPties/CdtrAcct/Id/Othr/Id", ns)
                )

            transactions.append({
                "transaction_date": booking_date,
                "value_date": value_date,
                "amount": entry_amount,
                "currency": entry_currency,
                "reference": ref,
                "bank_reference": bank_ref,
                "description": description,
                "bank_account": bank_account,
                "counterparty_name": counterparty_name,
                "counterparty_account": counterparty_account
            })

    def _parse_tx_detail(
        self,
        tx: ET.Element,
        bank_account: str,
        entry_currency: str,
        entry_indicator: str,
        booking_date: str,
        value_date: str,
        ns: str,
        stmt_idx: int,
        entry_idx: int,
        tx_idx: int,
        transactions: List[Dict[str, Any]]
    ):
        """
        Parses a nested <TxDtls> sub-transaction within a batch entry.
        """
        # Detail-level Amount and Currency
        amt_str = self.get_text(tx, "Amt", ns)
        currency = entry_currency
        
        # Detail credit/debit indicator fallback
        detail_indicator = self.get_text(tx, "CdtDbtInd", ns) or entry_indicator
        
        if amt_str:
            try:
                amount = float(amt_str)
            except ValueError:
                raise CAMT053RowParsingError(f"Invalid sub-transaction amount '{amt_str}' in sub-tx #{tx_idx}")
                
            amt_elem = self.find_elem(tx, "Amt", ns)
            if amt_elem is not None and "Ccy" in amt_elem.attrib:
                currency = amt_elem.attrib["Ccy"]
        else:
            # If sub-transaction does not specify Amount, raise an error
            raise CAMT053RowParsingError(f"Sub-transaction #{tx_idx} under Entry #{entry_idx} has no specific amount.")

        if detail_indicator == "DBIT":
            amount = -amount

        # Detail-level references
        ref = (
            self.get_text(tx, "Refs/EndToEndId", ns) or 
            self.get_text(tx, "Refs/UETR", ns) or 
            self.get_text(tx, "Refs/TxId", ns)
        )
        if ref.upper() in ("NONREF", "/NONREF", "NONREF/", "/"):
            ref = ""
            
        bank_ref = (
            self.get_text(tx, "Refs/AcctSvcrRef", ns) or 
            self.get_text(tx, "Refs/UETR", ns) or 
            self.get_text(tx, "Refs/TxId", ns)
        )
        if bank_ref.upper() in ("NONREF", "/NONREF", "NONREF/", "/"):
            bank_ref = ""

        # Remittance/Description
        description = self.get_text(tx, "AddtlTxInf", ns)
        ustrd_elems = self.find_all_elems(tx, "RmtInf/Ustrd", ns)
        if ustrd_elems:
            ustrd_texts = [el.text.strip() for el in ustrd_elems if el.text]
            if ustrd_texts:
                description = " ".join(ustrd_texts)

        # Detail Counterparty Info
        counterparty_name = ""
        counterparty_account = ""
        if detail_indicator == "CRDT":
            counterparty_name = self.get_text(tx, "RltdPties/Dbtr/Nm", ns)
            counterparty_account = (
                self.get_text(tx, "RltdPties/DbtrAcct/Id/IBAN", ns) or 
                self.get_text(tx, "RltdPties/DbtrAcct/Id/Othr/Id", ns)
            )
        else:
            counterparty_name = self.get_text(tx, "RltdPties/Cdtr/Nm", ns)
            counterparty_account = (
                self.get_text(tx, "RltdPties/CdtrAcct/Id/IBAN", ns) or 
                self.get_text(tx, "RltdPties/CdtrAcct/Id/Othr/Id", ns)
            )

        transactions.append({
            "transaction_date": booking_date,
            "value_date": value_date,
            "amount": amount,
            "currency": currency,
            "reference": ref,
            "bank_reference": bank_ref,
            "description": description,
            "bank_account": bank_account,
            "counterparty_name": counterparty_name,
            "counterparty_account": counterparty_account
        })

    def _build_path(self, path_str: str, ns: str) -> str:
        if not ns:
            return path_str
        parts = path_str.split("/")
        prefixed_parts = []
        for part in parts:
            if not part or part == "." or part == "..":
                prefixed_parts.append(part)
            elif part.startswith("{"):
                prefixed_parts.append(part)
            else:
                prefixed_parts.append(f"{ns}{part}")
        return "/".join(prefixed_parts)

    def find_elem(self, parent: ET.Element, path_str: str, ns: str) -> Optional[ET.Element]:
        if parent is None:
            return None
        return parent.find(self._build_path(path_str, ns))

    def find_all_elems(self, parent: ET.Element, path_str: str, ns: str) -> List[ET.Element]:
        if parent is None:
            return []
        return parent.findall(self._build_path(path_str, ns))

    def get_text(self, parent: ET.Element, path_str: str, ns: str, default: str = "") -> str:
        elem = self.find_elem(parent, path_str, ns)
        if elem is not None and elem.text is not None:
            return elem.text.strip()
        return default

    def _parse_date(self, date_str: str) -> str:
        if not date_str:
            return datetime.now().strftime("%Y-%m-%d")
        clean_date = date_str[:10]
        try:
            dt = datetime.strptime(clean_date, "%Y-%m-%d").date()
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return datetime.now().strftime("%Y-%m-%d")
