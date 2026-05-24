import os
import sys
import random
import csv
import argparse
from datetime import datetime, timedelta, date, timezone
from decimal import Decimal
import xml.etree.ElementTree as ET
from xml.dom import minidom

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==============================================================================
# SYNTHETIC DATA DICTIONARIES FOR NARRATION GENERATION
# ==============================================================================
COMPANIES = [
    "Acme Corporation", "Globex Financial", "Initech Consulting", "Umbrella Corp",
    "Soylent Green Co", "Hooli Tech", "Vehement Media", "Stark Industries",
    "Wayne Enterprises", "Tyrell Biosystems", "Cyberdyne Systems", "Oscorp Tech",
    "Prestige Worldwide", "Dunder Mifflin", "Vandelay Industries", "Bluth Company"
]

TRANSACTION_TYPES = [
    "invoice payment", "clearing transfer", "vendor settlement", "operational wire",
    "payroll credit", "clearing adjustment", "service fee charge", "merchant payout"
]

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD"]

class TransactionDatasetGenerator:
    def __init__(self, size: int = 100, seed: int = 42):
        self.size = size
        random.seed(seed)
        self.bank_entries = []
        self.ledger_entries = []
        
        # Partition sizes based on proportion
        self.exact_count = int(size * 0.40)      # 40% Exact Matches
        self.fuzzy_count = int(size * 0.20)      # 20% Fuzzy Matches
        self.fx_count = int(size * 0.15)         # 15% FX Variances
        self.dup_count = int(size * 0.10)        # 10% Duplicate Cases
        self.mismatch_bank = int(size * 0.075)   # 7.5% Orphan Bank Entries
        self.mismatch_ledger = int(size * 0.075) # 7.5% Orphan Ledger Entries
        
    def generate(self):
        ref_counter = 100000
        start_date = date(2026, 5, 1)
        
        # 1. Exact Matches (Identical Reference, Amount, Currency, and Date)
        for _ in range(self.exact_count):
            ref_counter += 1
            ref = f"REF-{ref_counter}"
            amt = round(random.uniform(50.0, 50000.0), 2)
            ccy = random.choice(CURRENCIES)
            tx_date = start_date + timedelta(days=random.randint(0, 20))
            company = random.choice(COMPANIES)
            tx_type = random.choice(TRANSACTION_TYPES)
            
            narration = f"{tx_type.upper()} TO {company.upper()}"
            
            # Identical entries
            self.bank_entries.append({
                "reference": ref,
                "amount": amt,
                "currency": ccy,
                "date": tx_date,
                "description": narration,
                "bank_account": f"US893704{random.randint(1000, 9999)}05320130"
            })
            self.ledger_entries.append({
                "reference": ref,
                "amount": amt,
                "currency": ccy,
                "date": tx_date,
                "description": narration,
                "bank_account": f"US893704{random.randint(1000, 9999)}05320130"
            })

        # 2. Fuzzy Matches (Different narrations, slight date offset, or tiny discrepancies)
        for _ in range(self.fuzzy_count):
            ref_counter += 1
            ref_bank = f"REF-{ref_counter}"
            # Ledger reference might have a slight typo or format offset
            ref_ledger = ref_bank if random.random() > 0.3 else f"RF-{ref_counter}"
            
            amt = round(random.uniform(100.0, 25000.0), 2)
            ccy = random.choice(CURRENCIES)
            tx_date = start_date + timedelta(days=random.randint(0, 20))
            company = random.choice(COMPANIES)
            tx_type = random.choice(TRANSACTION_TYPES)
            
            # Narration variance: e.g. "Acme Corp Ltd" vs "Acme Corporation Inc"
            narration_bank = f"WIRE PYMT TO {company.upper()} LLC"
            narration_ledger = f"{company.upper()} OPERATIONAL SETTLE"
            
            # Date offset: bank clears 1-3 days after ledger booking
            date_ledger = tx_date
            date_bank = date_ledger + timedelta(days=random.randint(1, 3))
            
            # Tiny amount fee discrepancy in 30% of cases
            amt_bank = amt
            amt_ledger = amt
            if random.random() > 0.7:
                # Deduct bank service fee of $1.50
                amt_bank = round(amt - 1.50, 2)
            
            self.bank_entries.append({
                "reference": ref_bank,
                "amount": amt_bank,
                "currency": ccy,
                "date": date_bank,
                "description": narration_bank,
                "bank_account": f"US893704{random.randint(1000, 9999)}05320130"
            })
            self.ledger_entries.append({
                "reference": ref_ledger,
                "amount": amt_ledger,
                "currency": ccy,
                "date": date_ledger,
                "description": narration_ledger,
                "bank_account": f"US893704{random.randint(1000, 9999)}05320130"
            })

        # 3. FX Variance Matches (Different Currency Cross-Border settlements)
        # Bank clears in EUR, internal ledger booked in USD (or vice versa)
        exchange_rate = 1.085  # EUR to USD
        for _ in range(self.fx_count):
            ref_counter += 1
            ref = f"REF-FX-{ref_counter}"
            
            amt_eur = round(random.uniform(200.0, 15000.0), 2)
            # Calculated USD amount with a slight rate conversion variance (+/- 0.5%)
            var_multiplier = random.uniform(0.995, 1.005)
            amt_usd = round(amt_eur * exchange_rate * var_multiplier, 2)
            
            tx_date = start_date + timedelta(days=random.randint(0, 20))
            company = random.choice(COMPANIES)
            
            self.bank_entries.append({
                "reference": ref,
                "amount": amt_eur,
                "currency": "EUR",
                "date": tx_date + timedelta(days=2),
                "description": f"INCOMING SEPA FX FROM {company.upper()}",
                "bank_account": f"DE533704{random.randint(1000, 9999)}05320130"
            })
            self.ledger_entries.append({
                "reference": ref,
                "amount": amt_usd,
                "currency": "USD",
                "date": tx_date,
                "description": f"FOREIGN SALES BOOKING - {company.upper()}",
                "bank_account": f"US893704{random.randint(1000, 9999)}05320130"
            })

        # 4. Duplicate Cases (To test FIFO queue pairing accuracy)
        for _ in range(self.dup_count // 2):
            ref_counter += 1
            ref = f"REF-DUP-{ref_counter}"
            amt = round(random.choice([150.00, 500.00, 1200.50, 4500.00]), 2)
            ccy = "USD"
            tx_date = start_date + timedelta(days=random.randint(0, 20))
            company = random.choice(COMPANIES)
            
            # Generate 2 identical entries on both sides
            for offset_days in [0, 2]:
                self.bank_entries.append({
                    "reference": ref,
                    "amount": amt,
                    "currency": ccy,
                    "date": tx_date + timedelta(days=offset_days),
                    "description": f"BATCH PAYROLL SETTLEMENT - {company.upper()}",
                    "bank_account": f"US893704{random.randint(1000, 9999)}05320130"
                })
                self.ledger_entries.append({
                    "reference": ref,
                    "amount": amt,
                    "currency": ccy,
                    "date": tx_date + timedelta(days=offset_days),
                    "description": f"BATCH PAYROLL SETTLEMENT - {company.upper()}",
                    "bank_account": f"US893704{random.randint(1000, 9999)}05320130"
                })

        # 5. Deliberate Mismatches - Orphan Bank Entries (Cleared in Bank but missing in Ledger)
        for _ in range(self.mismatch_bank):
            ref_counter += 1
            ref = f"REF-MIS-{ref_counter}"
            amt = round(random.uniform(50.0, 8000.0), 2)
            ccy = random.choice(CURRENCIES)
            tx_date = start_date + timedelta(days=random.randint(0, 20))
            company = random.choice(COMPANIES)
            
            self.bank_entries.append({
                "reference": ref,
                "amount": amt,
                "currency": ccy,
                "date": tx_date,
                "description": f"UNRESOLVED SUSPENSE DEPOSIT - {company.upper()}",
                "bank_account": f"US893704{random.randint(1000, 9999)}05320130"
            })

        # 6. Deliberate Mismatches - Orphan Ledger Entries (Booked in Ledger but missing in Bank)
        for _ in range(self.mismatch_ledger):
            ref_counter += 1
            ref = f"REF-MIS-{ref_counter}"
            amt = round(random.uniform(50.0, 8000.0), 2)
            ccy = random.choice(CURRENCIES)
            tx_date = start_date + timedelta(days=random.randint(0, 20))
            company = random.choice(COMPANIES)
            
            self.ledger_entries.append({
                "reference": ref,
                "amount": amt,
                "currency": ccy,
                "date": tx_date,
                "description": f"PROJECTED PAYABLE accrual - {company.upper()}",
                "bank_account": f"US893704{random.randint(1000, 9999)}05320130"
            })

        # Shuffle lists to simulate randomized posting schedules
        random.shuffle(self.bank_entries)
        random.shuffle(self.ledger_entries)

    # ==============================================================================
    # EXPORTER UTILITIES
    # ==============================================================================
    def export_ledger_csv(self, file_path: str):
        """Generates standard CSV representation of internal ledgers."""
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Transaction Date", "Amount", "Currency", "Reference", "Description", "Bank Account"])
            for row in self.ledger_entries:
                writer.writerow([
                    row["date"].isoformat(),
                    row["amount"],
                    row["currency"],
                    row["reference"],
                    row["description"],
                    row["bank_account"]
                ])

    def export_bank_csv(self, file_path: str):
        """Generates standard CSV representation of bank statements."""
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Posting Date", "Transaction Amount", "Ccy", "Ref Code", "Transaction Narration", "IBAN"])
            for row in self.bank_entries:
                writer.writerow([
                    row["date"].isoformat(),
                    row["amount"],
                    row["currency"],
                    row["reference"],
                    row["description"],
                    row["bank_account"]
                ])

    def export_mt940_txt(self, file_path: str):
        """Generates compliant SWIFT MT940 statement text file."""
        lines = []
        lines.append(":20:SYNTHETIC940")
        lines.append(":25:US89370400440532013000")
        lines.append(":28C:00001")
        lines.append(":60F:C260501USD100000,00")
        
        for i, row in enumerate(self.bank_entries):
            # Formulate tag :61:
            # Date format: YYMMDD
            yy_mm_dd = row["date"].strftime("%y%m%d")
            # Sign specifier: C for Credit (deposit / positive), D for Debit (payment / negative)
            sign = "C" if row["amount"] >= 0 else "D"
            # Format decimal values using comma as SWIFT decimal separator
            amt_str = f"{abs(row['amount']):.2f}".replace(".", ",")
            
            ref = row["reference"] or "NONREF"
            
            lines.append(f":61:{yy_mm_dd}{yy_mm_dd}{sign}{amt_str}NTRF{ref}")
            # Narration tag :86:
            lines.append(f":86:{row['description']}")
            
        lines.append(":62F:C260524USD145800,20")
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def export_camt053_xml(self, file_path: str):
        """Generates compliant ISO 20022 CAMT.053 XML statement."""
        # Building the XML programmatically via templates to guarantee premium formatted tags
        xml_entries = []
        for i, row in enumerate(self.bank_entries):
            dbt_cdt_ind = "CRDT" if row["amount"] >= 0 else "DBIT"
            dt_str = row["date"].isoformat()
            
            entry = f"""        <Ntry>
          <Amt Ccy="{row['currency']}">{abs(row['amount']):.2f}</Amt>
          <CdtDbtInd>{dbt_cdt_ind}</CdtDbtInd>
          <Status>BOOK</Status>
          <BookgDt>
            <Dt>{dt_str}</Dt>
          </BookgDt>
          <ValDt>
            <Dt>{dt_str}</Dt>
          </ValDt>
          <NtryDtls>
            <TxDtls>
              <Refs>
                <EndToEndId>{row['reference']}</EndToEndId>
              </Refs>
              <RltdPties>
                <Dbtr>
                  <Nm>SYNTHETIC BANK INC</Nm>
                </Dbtr>
              </RltdPties>
              <AddtlTxInf>{row['description']}</AddtlTxInf>
            </TxDtls>
          </NtryDtls>
        </Ntry>"""
            xml_entries.append(entry)

        xml_body = "\n".join(xml_entries)
        
        xml_template = f"""<?xml version="1.0" encoding="utf-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <Stmt>
      <Id>SYNTHETIC-CAMT-001</Id>
      <CreDtTm>{datetime.now(timezone.utc).isoformat()}</CreDtTm>
      <Acct>
        <Id>
          <Othr>
            <Id>US89370400440532013000</Id>
          </Othr>
        </Id>
      </Acct>
{xml_body}
    </Stmt>
  </BkToCstmrStmt>
</Document>"""

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(xml_template)

# ==============================================================================
# MAIN EXECUTABLE COMMAND-LINE PARSER
# ==============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synthetic Reconciliation Transaction Dataset Generator")
    parser.add_argument("--size", type=int, default=100, help="Total transactions size count to generate")
    parser.add_argument("--format", type=str, default="all", choices=["all", "csv", "mt940", "camt053"], help="Export statement format type")
    parser.add_argument("--out", type=str, default="test_data", help="Output target directory folder")
    parser.add_argument("--seed", type=int, default=42, help="Randomizer seed factor")
    
    args = parser.parse_args()
    
    # Resolve directory paths
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    out_dir = os.path.join(root_dir, args.out)
    os.makedirs(out_dir, exist_ok=True)
    
    print("=" * 100)
    print("🏦 SYNTHETIC TRANSACTION DATASET GENERATOR DISPATCHER")
    print("=" * 100)
    print(f"Configured Size : {args.size} records")
    print(f"Target Directory: {out_dir}")
    print(f"Randomizer Seed : {args.seed}")
    print("-" * 100)
    
    gen = TransactionDatasetGenerator(size=args.size, seed=args.seed)
    print("Generating randomized data distributions...")
    gen.generate()
    
    # Ledger export
    ledger_path = os.path.join(out_dir, "internal_ledger_export.csv")
    gen.export_ledger_csv(ledger_path)
    print(f"🟢 Exported Internal Ledger  -> {os.path.basename(ledger_path)}")
    
    # Bank exports
    if args.format in ["all", "csv"]:
        bank_csv = os.path.join(out_dir, "bank_statement_export.csv")
        gen.export_bank_csv(bank_csv)
        print(f"🟢 Exported Bank CSV Line    -> {os.path.basename(bank_csv)}")
        
    if args.format in ["all", "mt940"]:
        bank_mt940 = os.path.join(out_dir, "bank_statement_export.txt")
        gen.export_mt940_txt(bank_mt940)
        print(f"🟢 Exported SWIFT MT940 Line -> {os.path.basename(bank_mt940)}")
        
    if args.format in ["all", "camt053"]:
        bank_camt = os.path.join(out_dir, "bank_statement_export.xml")
        gen.export_camt053_xml(bank_camt)
        print(f"🟢 Exported ISO CAMT.053 XML -> {os.path.basename(bank_camt)}")
        
    print("-" * 100)
    print("📊 GENERATED DISTRIBUTIONS BREAKDOWN SUMMARY:")
    print(f"  ├── 🟢 Exact Matches       : {gen.exact_count} cases")
    print(f"  ├── 🟡 Fuzzy Narrations   : {gen.fuzzy_count} cases")
    print(f"  ├── 💱 FX Rate Variances   : {gen.fx_count} cases")
    print(f"  ├── 👥 Duplicate Pairings  : {gen.dup_count} cases")
    print(f"  ├── 🔴 Orphan Bank entries : {gen.mismatch_bank} cases")
    print(f"  └── 🔴 Orphan Ledger entries: {gen.mismatch_ledger} cases")
    print("=" * 100)
