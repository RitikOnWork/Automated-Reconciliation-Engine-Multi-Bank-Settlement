import streamlit as st
from components.api_client import APIClient

# Page configuration
st.set_page_config(
    page_title="Automated Reconciliation Engine",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load custom CSS
try:
    with open("assets/styles.css", "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except Exception:
    pass

# Session state initialization
if "access_token" not in st.session_state:
    st.session_state["access_token"] = None
if "username" not in st.session_state:
    st.session_state["username"] = None
if "role" not in st.session_state:
    st.session_state["role"] = None

# ==============================================================================
# Authentication Guard Interface
# ==============================================================================
if not st.session_state["access_token"]:
    st.markdown("<div class='main-title'>🏦 Automated Reconciliation Engine</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Secure Backplane Financial Control Operator Portal</div>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("""
        ### Reconcile Banking Statements Instantly
        An enterprise-grade, high-fidelity platform to ingest, parse, and normalize bank movements.
        
        * **Multiformat ingestion**: Parses SWIFT MT940, ISO 20022 CAMT.053, and arbitrary CSV.
        * **Heuristic matching engines**: Combines exact fields lookup, fuzzy naration distance score checking, and custom rule-based day/amount tolerances.
        * **Immutable Audit Trail**: Complies with standard regulatory compliance regimes.
        """)
        
    with col2:
        tab_login, tab_register = st.tabs(["🔐 Sign In", "➕ Create Analyst Account"])
        
        with tab_login:
            st.markdown("### Operator Login")
            u = st.text_input("Username", key="login_u")
            p = st.text_input("Password", type="password", key="login_p")
            
            if st.button("Authenticate", use_container_width=True):
                if u and p:
                    success = APIClient.login(u, p)
                    if success:
                        # Pre-fetch profile details to grab role
                        status_code, me_data = APIClient.get("/auth/me")
                        if status_code == 200:
                            st.session_state["role"] = me_data.get("role")
                        st.toast(f"Welcome back, {u}!", icon="👋")
                        st.rerun()
                    else:
                        st.error("Authentication failed. Please verify credentials.")
                else:
                    st.warning("Please fill in both username and password fields.")
                    
        with tab_register:
            st.markdown("### Operator Registration")
            reg_u = st.text_input("Username", key="reg_u")
            reg_p = st.text_input("Password", type="password", key="reg_p")
            reg_role = st.selectbox("Role", ["analyst", "admin", "viewer"], key="reg_role")
            
            if st.button("Create Account", use_container_width=True):
                if reg_u and reg_p:
                    success = APIClient.register(reg_u, reg_p, reg_role)
                    if success:
                        st.success("Account registered successfully. Please sign in via the Login tab.")
                    else:
                        st.error("Registration failed. Username may already be taken.")
                else:
                    st.warning("Please fill in all registration fields.")

else:
    # Resolve user role if not already loaded in session state
    if not st.session_state["role"]:
        status_code, me_data = APIClient.get("/auth/me")
        if status_code == 200:
            st.session_state["role"] = me_data.get("role")

    # Sidebar Operator Console
    role_display = str(st.session_state['role']).upper() if st.session_state['role'] else "OPERATOR"
    st.sidebar.markdown(f"### 👤 Active Operator: `{st.session_state['username']}`")
    st.sidebar.markdown(f"**Clearance**: `{role_display}`")
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🔐 Sign Out", use_container_width=True):
        st.session_state["access_token"] = None
        st.session_state["username"] = None
        st.session_state["role"] = None
        st.rerun()
        
    # Main content landing
    st.markdown("<div class='main-title'>🏦 Automated Reconciliation Engine</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-subtitle'>Operational Control Panel Dashboard</div>", unsafe_allow_html=True)
    
    st.markdown("""
    ### Dashboard Quick Links
    Welcome to the financial control panel. Select one of the operations below in the sidebar to proceed:
    
    1. **📊 Operational Dashboard**: Review overall settlement statistics, KPIs, match-rates, and financial overview metrics.
    2. **📤 Upload Bank Statements**: Ingest SWIFT MT940, ISO 20022 CAMT.053 XML files, or custom CSV lists into our normalization database.
    3. **🔍 Trigger Matching Run**: Configure matching thresholds and execute automated reconciliation scripts.
    4. **⚠️ Exceptions Queue Workspace**: Manually audit, match, or write off open variances and mismatches.
    5. **📜 Compliance Audit Trails**: Retrieve immutable, read-only operational transaction logs.
    """)
