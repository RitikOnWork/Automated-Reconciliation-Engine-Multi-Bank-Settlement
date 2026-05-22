import streamlit as st
import pandas as pd
from components.api_client import APIClient

st.set_page_config(page_title="Immutable Compliance Audit Trail", layout="wide")

try:
    with open("assets/styles.css", "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except Exception:
    pass

# Authentication Guard
if "access_token" not in st.session_state or not st.session_state["access_token"]:
    st.warning("🔒 Unauthorized operator access. Please sign in via the home portal.")
    st.stop()

st.markdown("<div class='main-title'>📜 Compliance Audit Trails</div>", unsafe_allow_html=True)
st.markdown("<div class='section-subtitle'>Immutable historical logs of all system operations, data mutability, and resolutions</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# Cryptographic Ledger Integrity Verification Console
# ------------------------------------------------------------------------------
st.markdown("## 🛡️ Ledger Cryptographic Integrity Scanner")

role = st.session_state.get("role", "viewer").lower()

col_verify, col_status = st.columns([1, 2])

with col_verify:
    st.markdown("### Control Panel")
    st.write("Scan all compliance logs, validating cryptographic SHA-256 chaining continuity and testing for external row mutations.")
    
    if role not in ["admin", "system"]:
        st.info("ℹ️ *Ledger integrity checks require administrative credentials.*")
        
    verify_button = st.button(
        "🛡️ Run Ledger Integrity Scan", 
        use_container_width=True, 
        type="primary"
    )

with col_status:
    st.markdown("### Scan Result")
    if verify_button:
        if role not in ["admin", "system"]:
            st.error(f"❌ Permission Denied: Verification is locked to administrative roles. Your current role is: `{role}`.")
        else:
            with st.spinner("Executing cryptographic ledger verification scan..."):
                status_code, verification = APIClient.post("/audit/verify")
                if status_code == 200:
                    is_valid = verification.get("is_valid", False)
                    block_count = verification.get("block_count", 0)
                    tampered_ids = verification.get("tampered_record_ids", [])
                    errors = verification.get("errors", [])
                    
                    if is_valid:
                        st.success(f"🟢 **LEDGER INTEGRITY SECURE / VERIFIED**\n\nAll {block_count} transaction log blocks are intact. Each hash links securely to its predecessor.")
                        
                        # Show beautiful metric counters
                        m1, m2 = st.columns(2)
                        m1.metric("Chained Block Count", block_count)
                        m2.metric("Security Status", "🟢 Compliant")
                    else:
                        st.error(f"🔴 **SECURITY COMPLIANCE CRITICAL: TAMPERING DETECTED!**\n\nLedger continuity has been broken! {len(tampered_ids)} record(s) failed cryptographic signature checks.")
                        
                        # Show error table
                        if errors:
                            err_df = pd.DataFrame(errors)
                            st.dataframe(err_df, use_container_width=True, hide_index=True)
                else:
                    error_msg = verification.get("detail", "Unknown error") if isinstance(verification, dict) else "Unknown backend error"
                    st.error(f"Failed to execute ledger verification: Backend returned status code {status_code} ({error_msg}).")
    else:
        st.info("System idle. Click the button on the left to execute the cryptographic signature validation scan.")

st.markdown("---")

# ------------------------------------------------------------------------------
# Fetch and Display Logs
# ------------------------------------------------------------------------------
st.markdown("## 📋 Audit Trail Event Ledger")

# Fetch audit logs
status_code, audit_logs = APIClient.get("/audit", params={"limit": 500})

if status_code != 200:
    st.error("Failed to query historical logs from compliance API.")
    st.stop()

if not audit_logs:
    st.info("No logs are currently registered. Perform statement uploads or matching runs to initiate audit trails.")
    st.stop()

# Present in a beautiful, structured table
df_audit = pd.DataFrame(audit_logs)

# Clean columns for display
display_cols = [
    "timestamp", 
    "action", 
    "performed_by", 
    "table_name", 
    "record_id", 
    "comments"
]

# Rename maps
rename_map = {
    "timestamp": "Timestamp",
    "action": "Operation Action",
    "performed_by": "Operator User",
    "table_name": "Target Table",
    "record_id": "Affected Row ID",
    "comments": "Compliance Comments / Summary"
}

# Append cryptographic hashes if they exist
if "previous_hash" in df_audit.columns:
    df_audit["Parent Hash (SHA-256)"] = df_audit["previous_hash"].apply(lambda h: f"{h[:12]}..." if isinstance(h, str) and h else "None (Genesis)")
    display_cols.append("Parent Hash (SHA-256)")
if "hash" in df_audit.columns:
    df_audit["Current Hash (SHA-256)"] = df_audit["hash"].apply(lambda h: f"{h[:12]}..." if isinstance(h, str) and h else "None")
    display_cols.append("Current Hash (SHA-256)")

df_display = df_audit[display_cols].copy()
df_display.rename(columns=rename_map, inplace=True)

# Format timestamp string
df_display["Timestamp"] = pd.to_datetime(df_display["Timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True
)

st.markdown("""
---
*Note: Compliance audit trails are secure, read-only system events captured automatically during transaction actions and manual overrides. They are hashed cryptographically and cannot be modified or deleted by dashboard operators.*
""")
