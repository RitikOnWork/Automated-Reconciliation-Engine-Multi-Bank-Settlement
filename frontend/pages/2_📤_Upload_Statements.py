import streamlit as st
import pandas as pd
from components.api_client import APIClient

st.set_page_config(page_title="Statement Uploader - Reconciliation", layout="wide")

try:
    with open("assets/styles.css", "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except Exception:
    pass

# Authentication Guard
if "access_token" not in st.session_state or not st.session_state["access_token"]:
    st.warning("🔒 Unauthorized operator access. Please sign in via the home portal.")
    st.stop()

st.markdown("<div class='main-title'>📤 Statement Ingestion</div>", unsafe_allow_html=True)
st.markdown("<div class='section-subtitle'>Upload Bank Statement Files or Internal Ledgers</div>", unsafe_allow_html=True)

col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("### Upload Document")
    
    file_type = st.selectbox(
        "Ingestion Type Format", 
        ["mt940", "camt053", "csv"], 
        help="mt940: SWIFT. camt053: ISO 20022 XML. csv: Custom Spreadsheet."
    )
    
    source_system = st.selectbox(
        "Target Storage Ledger", 
        ["bank_statement", "internal_ledger"],
        help="Determine whether to upload these transactions as external bank records or internal database entries."
    )
    
    uploaded_file = st.file_uploader(
        "Select Statement File", 
        type=["txt", "xml", "csv", "sta"],
        help="Upload standard banking statements"
    )
    
    if st.button("Parse & Ingest Transactions", use_container_width=True):
        if uploaded_file is not None:
            # Setup payload data
            form_payload = {
                "file_type": file_type,
                "source_system": source_system
            }
            
            # Setup file bytes
            file_data = {
                "file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)
            }
            
            with st.spinner("Executing statement parser and normalization rules..."):
                status_code, response = APIClient.post(
                    "/transactions/upload",
                    data=form_payload,
                    files=file_data
                )
                
            if status_code == 201:
                st.success(
                    f"Successfully ingested statement! parsed {len(response)} valid "
                    f"transactions."
                )
                
                # Show preview table
                df_preview = pd.DataFrame(response)
                if not df_preview.empty:
                    st.markdown("#### Preview Ingested Records")
                    st.dataframe(
                        df_preview[["transaction_date", "amount", "currency", "reference", "description", "bank_account"]].head(10),
                        use_container_width=True
                    )
            else:
                err_msg = response.get("error", {}).get("message", "Ingestion failed.") if isinstance(response, dict) else "Parsing failed."
                st.error(f"Error Ingesting Statement: {err_msg}")
        else:
            st.warning("Please choose a file to ingest first.")

with col2:
    st.markdown("### Parsing Protocols Specs")
    st.markdown("""
    #### 🏦 SWIFT MT940 Requirements
    Standard text based statement files. The parser automatically scans for `:25:` (account identifier), `:61:` (booking line details), and `:86:` (supplementary text narration fields).

    #### 📄 ISO 20022 CAMT.053 XML Requirements
    XML files complying with structural schema `urn:iso:std:iso:20022:tech:xsd:camt.053.001.02` (or similar). Extracts rich balances, sign indicators (`CRDT`/`DBIT`), reference codes, and narrative descriptions.

    #### 📊 Spreadsheet CSV Requirements
    Comma, semicolon, or tab-delimited files. The engine automatically maps common header variations. Minimum required columns:
    * **Date**: (e.g. `Transaction Date`, `Post Date`, `Booking Date`, `tx_date`)
    * **Amount**: (e.g. `Amount`, `Value`, `Amt`, `tx_amount` - Debits must be negative)
    """)
