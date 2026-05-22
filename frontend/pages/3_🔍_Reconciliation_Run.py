import streamlit as st
from components.api_client import APIClient

st.set_page_config(page_title="Reconciliation Engine Matching Run", layout="wide")

try:
    with open("assets/styles.css", "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except Exception:
    pass

# Authentication Guard
if "access_token" not in st.session_state or not st.session_state["access_token"]:
    st.warning("🔒 Unauthorized operator access. Please sign in via the home portal.")
    st.stop()

st.markdown("<div class='main-title'>🔍 Execute Reconciliation</div>", unsafe_allow_html=True)
st.markdown("<div class='section-subtitle'>Configure Match Rules & Trigger Automatic Reconciliation Pipeline</div>", unsafe_allow_html=True)

col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("### Matching Pipeline Configurations")
    
    st.markdown("Adjust the matching tolerances below before executing the run:")
    
    # Matching rules tolerances input
    date_tolerance = st.slider(
        "Date Tolerance Offset (Days)", 
        min_value=0, 
        max_value=15, 
        value=3,
        help="Maximum difference in transaction booking dates to consider in rule-based tolerance checks."
    )
    
    amount_tolerance = st.number_input(
        "Amount Variance Tolerance (USD)",
        min_value=0.0,
        max_value=50.0,
        value=1.50,
        step=0.10,
        help="Maximum difference in absolute amount variances to allow for small rounding/banking fee errors."
    )
    
    fuzzy_threshold = st.slider(
        "Fuzzy Match Similarity Threshold (%)",
        min_value=50,
        max_value=100,
        value=85,
        help="Minimum similarity score required on naration/description fields to register a fuzzy match."
    )
    
    if st.button("🚀 Trigger Reconciliation Pipelines", use_container_width=True):
        params = {
            "fuzzy_threshold": float(fuzzy_threshold),
            "date_tolerance_days": date_tolerance,
            "amount_tolerance": amount_tolerance
        }
        
        with st.spinner("Executing Exact, Rule-Based, and Fuzzy matching cascades..."):
            status_code, response = APIClient.post("/reconciliation/run", json_data={}, data=params)
            
        if status_code == 200 and response.get("success"):
            st.success("Reconciliation cascade executed successfully!")
            
            # Show summary
            summary = response.get("summary", {})
            
            st.markdown("#### Execution Statistics Summary")
            
            st.markdown(f"""
            <div class="glass-card">
                <p style="margin: 4px 0;">🎯 Exact Matches Found: <strong style="color:#2ed573;">{summary.get('exact_matches', 0)} pairs</strong></p>
                <p style="margin: 4px 0;">⚙️ Rule-Based Matches (Tolerances) Found: <strong style="color:#00C6FF;">{summary.get('rule_matches', 0)} pairs</strong></p>
                <p style="margin: 4px 0;">🔍 Fuzzy Description Matches Found: <strong style="color:#ffa502;">{summary.get('fuzzy_matches', 0)} pairs</strong></p>
                <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.05); margin: 8px 0;"/>
                <p style="margin: 4px 0; color:#ff4757;">⚠️ Remaining Transactions Logged to Exceptions: <strong>{summary.get('exceptions_raised', 0)} records</strong></p>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("Review Active Exceptions Queue"):
                st.switch_page("pages/4_⚠️_Exceptions_Queue.py")
        else:
            err_msg = response.get("error", {}).get("message", "Execution failed.") if isinstance(response, dict) else "Pipeline crashed."
            st.error(f"Reconciliation job failed: {err_msg}")

with col2:
    st.markdown("### Matching Cascade Architecture")
    st.markdown("""
    When you click **Trigger**, the engine runs the following matching scripts sequentially:

    1. **🎯 Exact Reference Matcher**:
       * Direct 1:1 validation of bank account, currency, exact amount, and reference code.
       * 100% confidence match. Marks transactions as `MATCHED`.

    2. **⚙️ Rule-Based Tolerance Matcher**:
       * Operates on remaining unmatched transactions.
       * Matches transactions with identical reference codes but permits a date difference of +/- **N days** and amount variances of +/- **$M** (e.g. FX spreads or billing fees).

    3. **🔍 Fuzzy Description Matcher**:
       * Leverages token sort ratio similarity on raw descriptions and narration texts when references are missing.
       * Applies only if accounts and absolute amounts align perfectly.
    
    4. **⚠️ Exceptions Queue**:
       * Any transactions that fail all three criteria are automatically marked as `EXCEPTION` and pushed to the operator review panel.
    """)
