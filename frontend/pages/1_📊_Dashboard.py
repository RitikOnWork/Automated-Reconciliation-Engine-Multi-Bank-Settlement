import streamlit as st
import pandas as pd
import plotly.express as px
from components.api_client import APIClient

st.set_page_config(page_title="KPI Dashboard - Reconciliation", layout="wide")

# CSS import
try:
    with open("assets/styles.css", "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except Exception:
    pass

# Authentication Guard
if "access_token" not in st.session_state or not st.session_state["access_token"]:
    st.warning("🔒 Unauthorized operator access. Please sign in via the home portal.")
    st.stop()

st.markdown("<div class='main-title'>📊 Operational Dashboard</div>", unsafe_allow_html=True)
st.markdown("<div class='section-subtitle'>High-Level KPIs & Financial Settlement Metrics</div>", unsafe_allow_html=True)

# Fetch current transaction statuses from API
status_code, transactions = APIClient.get("/transactions", params={"limit": 1000})

if status_code != 200:
    st.error("Failed to query transaction stats from backend API.")
    st.stop()

if not transactions:
    st.info("No transaction data available yet. Please upload statements to populate the metrics.")
    st.stop()

# Load into Pandas DataFrame for analysis
df = pd.DataFrame(transactions)

# Basic KPI Calculations
total_txs = len(df)
bank_txs = len(df[df["source_system"] == "bank_statement"])
ledger_txs = len(df[df["source_system"] == "internal_ledger"])

matched_count = len(df[df["status"] == "MATCHED"])
unmatched_count = len(df[df["status"] == "UNMATCHED"])
exception_count = len(df[df["status"] == "EXCEPTION"])

match_rate = (matched_count / total_txs * 100) if total_txs > 0 else 0.0

# Render KPIs using customized layouts
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="glass-card">
        <h5 style="color: #6C7A9C; margin:0;">Total Ingested</h5>
        <h2 style="color: #00C6FF; margin:0; font-size:2.2rem; font-weight:800;">{total_txs}</h2>
        <small style="color: #6C7A9C;">Bank: {bank_txs} | Ledger: {ledger_txs}</small>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="glass-card">
        <h5 style="color: #6C7A9C; margin:0;">Match Rate</h5>
        <h2 style="color: #2ed573; margin:0; font-size:2.2rem; font-weight:800;">{match_rate:.1f}%</h2>
        <small style="color: #6C7A9C;">Reconciled: {matched_count}</small>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="glass-card">
        <h5 style="color: #6C7A9C; margin:0;">Unmatched Entries</h5>
        <h2 style="color: #6C7A9C; margin:0; font-size:2.2rem; font-weight:800;">{unmatched_count}</h2>
        <small style="color: #6C7A9C;">Awaiting run</small>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="glass-card">
        <h5 style="color: #6C7A9C; margin:0;">Active Exceptions</h5>
        <h2 style="color: #ff4757; margin:0; font-size:2.2rem; font-weight:800;">{exception_count}</h2>
        <small style="color: #6C7A9C;">Requiring operator manual review</small>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Visualization Charts
chart_col1, chart_col2 = st.columns([1, 1])

with chart_col1:
    st.markdown("### Status Distribution")
    status_df = pd.DataFrame([
        {"Status": "Matched", "Count": matched_count},
        {"Status": "Unmatched", "Count": unmatched_count},
        {"Status": "Exceptions", "Count": exception_count}
    ])
    fig1 = px.pie(
        status_df, 
        values="Count", 
        names="Status", 
        color="Status",
        color_discrete_map={"Matched": "#2ed573", "Unmatched": "#747d8c", "Exceptions": "#ff4757"},
        hole=0.4
    )
    fig1.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#ffffff",
        margin=dict(t=10, b=10, l=10, r=10)
    )
    st.plotly_chart(fig1, use_container_width=True)

with chart_col2:
    st.markdown("### Transaction Volumetrics")
    source_df = pd.DataFrame([
        {"Source": "Bank Statements", "Count": bank_txs},
        {"Source": "Internal Ledgers", "Count": ledger_txs}
    ])
    fig2 = px.bar(
        source_df, 
        x="Source", 
        y="Count",
        color="Source",
        color_discrete_map={"Bank Statements": "#00C6FF", "Internal Ledgers": "#0072FF"}
    )
    fig2.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#ffffff",
        margin=dict(t=10, b=10, l=10, r=10),
        xaxis_title=None,
        yaxis_title="Total Transactions Count"
    )
    st.plotly_chart(fig2, use_container_width=True)
