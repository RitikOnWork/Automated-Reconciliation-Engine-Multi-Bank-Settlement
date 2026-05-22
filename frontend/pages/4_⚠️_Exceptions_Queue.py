import streamlit as st
import pandas as pd
from components.api_client import APIClient

st.set_page_config(page_title="Manual Exceptions Workspace", layout="wide")

try:
    with open("assets/styles.css", "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except Exception:
    pass

# Authentication Guard
if "access_token" not in st.session_state or not st.session_state["access_token"]:
    st.warning("🔒 Unauthorized operator access. Please sign in via the home portal.")
    st.stop()

st.markdown("<div class='main-title'>⚠️ Exceptions Queue</div>", unsafe_allow_html=True)
st.markdown("<div class='section-subtitle'>Manual Overrides, Waiver Resolutions, and Force-Pairing Workspace</div>", unsafe_allow_html=True)

# Fetch current exceptions
status_code, exceptions = APIClient.get("/exceptions", params={"status": "OPEN", "limit": 200})

if status_code != 200:
    st.error("Failed to query open exceptions from backend.")
    st.stop()

if not exceptions:
    st.success("🎉 No active exceptions in the queue! Excellent work.")
    st.stop()

# Flatten data for presentation
flat_exceptions = []
for ex in exceptions:
    tx = ex["transaction"]
    flat_exceptions.append({
        "Exception ID": ex["id"],
        "Transaction ID": tx["id"],
        "Source Ledger": tx["source_system"],
        "Date": tx["transaction_date"],
        "Amount": float(tx["amount"]),
        "Currency": tx["currency"],
        "Reference": tx["reference"] or "",
        "Description": tx["description"] or "",
        "Account": tx["bank_account"],
        "Error Type": ex["error_type"]
    })

df_exc = pd.DataFrame(flat_exceptions)

# Display separate lists: Bank Statement vs Ledger for easy comparison
col_bank, col_ledger = st.columns(2)

with col_bank:
    st.markdown("### 🏦 Unmatched Bank Statement Records")
    df_bank = df_exc[df_exc["Source Ledger"] == "bank_statement"]
    if not df_bank.empty:
        st.dataframe(
            df_bank[["Exception ID", "Transaction ID", "Date", "Amount", "Reference", "Description", "Account"]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No open bank statement exceptions.")

with col_ledger:
    st.markdown("### 📊 Unmatched Internal Ledger Records")
    df_ledger = df_exc[df_exc["Source Ledger"] == "internal_ledger"]
    if not df_ledger.empty:
        st.dataframe(
            df_ledger[["Exception ID", "Transaction ID", "Date", "Amount", "Reference", "Description", "Account"]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No open internal ledger exceptions.")

st.markdown("---")

# Resolution form
st.markdown("### ⚙️ Resolve Exceptions Workspace")

action_col, input_col = st.columns([1, 1])

with action_col:
    # Dropdown to select exception by ID
    selected_exc_id = st.selectbox(
        "Select Exception to Resolve (ID)",
        options=df_exc["Exception ID"].tolist(),
        format_func=lambda x: f"Exception ID: {x} | Amount: ${df_exc[df_exc['Exception ID']==x]['Amount'].values[0]} | Ref: {df_exc[df_exc['Exception ID']==x]['Reference'].values[0]}"
    )
    
    action_type = st.radio(
        "Resolution Strategy",
        ["Force Match (Pair with ledger entry)", "Write Off / Waive Variance"],
        help="Force Match: Pair with another unmatched record. Write Off: Reconcile this single entry directly (e.g. currency variations)."
    )

with input_col:
    # Fetch details of selected
    selected_row = df_exc[df_exc["Exception ID"] == selected_exc_id].iloc[0]
    
    st.info(
        f"**Selected details**: Date: `{selected_row['Date']}`, "
        f"Amount: `${selected_row['Amount']:.2f}`, "
        f"Description: `'{selected_row['Description']}'`"
    )

    matched_tx_id = None
    if "Force Match" in action_type:
        matched_tx_id = st.number_input(
            "Pairing Target Transaction ID",
            min_value=1,
            step=1,
            help="Input the exact database Transaction ID of the other ledger record you wish to pair this transaction against."
        )
        
    comments = st.text_area(
        "Operational Justification Comment",
        help="Input a compliant written justification detailing why this override is being applied."
    )

    if st.button("Submit Manual Resolution Override", use_container_width=True):
        if len(comments) < 5:
            st.error("Please enter a comprehensive justification comment (minimum 5 characters).")
        else:
            action_code = "force_matched" if "Force Match" in action_type else "written_off"
            
            payload = {
                "action": action_code,
                "comments": comments,
                "matched_transaction_id": int(matched_tx_id) if matched_tx_id else None
            }
            
            with st.spinner("Writing compliant override to ledger..."):
                status_code, response = APIClient.put(f"/exceptions/{selected_exc_id}/resolve", json_data=payload)
                
            if status_code == 200:
                st.success("Override completed and audited successfully!")
                st.balloons()
                st.rerun()
            else:
                err = response.get("error", {}).get("message", "Resolution failed.") if isinstance(response, dict) else "Override failed."
                st.error(f"Error resolving variance: {err}")
