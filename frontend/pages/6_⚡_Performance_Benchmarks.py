import sys
import os
import time
from decimal import Decimal
from datetime import date, datetime
import pandas as pd
import streamlit as st
import plotly.express as px

# Add backend directory to sys.path to enable direct backend service imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../backend")))

try:
    from app.services.matching.exact_match import ExactMatchEngine, generate_benchmark_data, ReconciliationTransaction
    from app.services.matching.fuzzy_match import FuzzyMatchEngine
    from app.services.matching.rule_engine import (
        RuleEngine, ToleranceRule, FXVarianceRule, SplitTransactionRule, ManyToManySettlementRule
    )
    from app.services.matching.confidence_score import ConfidenceScoringEngine
except ImportError as e:
    st.error(f"Failed to import backend reconciliation services: {e}")
    st.stop()

st.set_page_config(page_title="High-Performance Match Engine Benchmarks", layout="wide")

# Load custom CSS
try:
    with open("assets/styles.css", "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except Exception:
    pass

# Authentication Guard
if "access_token" not in st.session_state or not st.session_state["access_token"]:
    st.warning("🔒 Unauthorized operator access. Please sign in via the home portal.")
    st.stop()

st.markdown("<div class='main-title'>⚡ High-Performance Engines & Sandbox</div>", unsafe_allow_html=True)
st.markdown("<div class='section-subtitle'>Interactive Benchmarking, Fuzzy Sandbox, Rule Simulator, and Confidence Evaluator</div>", unsafe_allow_html=True)

tab_exact, tab_fuzzy, tab_rules, tab_confidence = st.tabs([
    "🚀 Exact Match Benchmarker", 
    "🔍 Fuzzy Narration Sandbox", 
    "⚙️ Rule Simulator & Split Visualizer",
    "📊 Confidence Scorer Playground"
])

# ==============================================================================
# TAB 1: EXACT MATCH BENCHMARKER
# ==============================================================================
with tab_exact:
    st.markdown("### Exact Matching Engine Benchmark")
    st.markdown("""
    Test the limits of our composite-hashing, O(1) lookup exact matching engine.
    This benchmarker generates large synthetic sheets with complex exact matching keys and duplicate transaction entries,
    validating time complexity and throughput speed.
    """)
    
    col_bench_1, col_bench_2 = st.columns([1, 2])
    
    with col_bench_1:
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.markdown("#### Test Configurations")
        
        benchmark_scale = st.slider(
            "Transaction Sheet Size", 
            min_value=1000, 
            max_value=250000, 
            value=25000, 
            step=1000,
            help="Number of bank and ledger entries generated respectively. Total dataset size will be double."
        )
        
        run_btn = st.button("🚀 Execute Performance Test", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col_bench_2:
        if run_btn:
            with st.spinner("Generating controlled synthetic datasets..."):
                t0 = time.time()
                bank_txs, ledger_txs = generate_benchmark_data(benchmark_scale)
                t_gen = time.time() - t0
                
            st.toast("Datasets generated! Reconciling...", icon="🔄")
            
            with st.spinner("Executing O(1) hashmap matching engine..."):
                engine = ExactMatchEngine()
                t_match_start = time.time()
                matches = engine.reconcile(bank_txs, ledger_txs)
                t_match = time.time() - t_match_start
                
            total_txs = len(bank_txs) + len(ledger_txs)
            throughput = total_txs / t_match if t_match > 0 else 0
            
            # Format and display KPIs
            st.markdown("#### Performance Metrics")
            kpi1, kpi2, kpi3 = st.columns(3)
            
            kpi1.metric(
                label="⏱️ Match Execution Time", 
                value=f"{t_match * 1000:.2f} ms",
                delta=f"Gen time: {t_gen:.2f}s"
            )
            kpi2.metric(
                label="⚡ System Throughput", 
                value=f"{throughput:,.0f} tx/sec",
                delta="Linear O(N+M)"
            )
            kpi3.metric(
                label="🎯 Match Ratio", 
                value=f"{(len(matches) * 2 / total_txs) * 100:.1f}%",
                delta=f"{len(matches):,} pairs"
            )
            
            # Visual analysis
            unmatched_bank = sum(1 for t in bank_txs if t.status == "UNMATCHED")
            unmatched_ledger = sum(1 for t in ledger_txs if t.status == "UNMATCHED")
            
            chart_data = pd.DataFrame({
                "Category": ["Matched Pairs", "Unmatched Bank Txs", "Unmatched Ledger Txs"],
                "Count": [len(matches), unmatched_bank, unmatched_ledger]
            })
            
            fig = px.bar(
                chart_data, 
                x="Category", 
                y="Count", 
                color="Category",
                title=f"Reconciliation Matching Results Overview (N={total_txs:,} total records)",
                color_discrete_map={
                    "Matched Pairs": "#2ed573",
                    "Unmatched Bank Txs": "#ffa502",
                    "Unmatched Ledger Txs": "#ff4757"
                }
            )
            
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("💡 Adjust the slider scale and click **Execute Performance Test** to start benchmarking.")

# ==============================================================================
# TAB 2: FUZZY NARRATION SANDBOX
# ==============================================================================
with tab_fuzzy:
    st.markdown("### Fuzzy Narration & String Similarity Sandbox")
    st.markdown("""
    Evaluate description matching using weighted RapidFuzz distance functions.
    Adjust weight coefficients to balance between word-order changes, typos, and token groupings.
    """)
    
    col_fuz_1, col_fuz_2 = st.columns([1, 1])
    
    with col_fuz_1:
        st.markdown("#### Input Narrative Strings")
        
        bank_narration = st.text_input(
            "Bank Statement Narration", 
            value="AMZN MKTP US*1A2B3C SEATTLE CA",
            help="Raw description statement from incoming MT940 or CSV bank files."
        )
        
        ledger_narration = st.text_input(
            "Internal Ledger Description", 
            value="AMAZON MARKETPLACE CORP PAY",
            help="Reconciliation booking string in the internal ledger records."
        )
        
        st.markdown("#### Weight Configurations")
        
        w_token_set = st.slider(
            "Token Set Ratio Weight (deals with word-order splits & missing tokens)", 
            min_value=0.0, max_value=1.0, value=0.40, step=0.05
        )
        
        w_jaro = st.slider(
            "Jaro-Winkler Weight (optimal for prefix typos and short strings)", 
            min_value=0.0, max_value=1.0, value=0.40, step=0.05
        )
        
        w_lev = st.slider(
            "Levenshtein Weight (standard character-wise edit distance)", 
            min_value=0.0, max_value=1.0, value=0.20, step=0.05
        )
        
        # Verify weights sum up to 1.0 (or normalize them)
        weight_sum = w_token_set + w_jaro + w_lev
        if abs(weight_sum - 1.0) > 0.001:
            st.warning(f"⚠️ Weights sum up to {weight_sum:.2f}. They will be automatically normalized to 1.0.")
            w_ts_norm = w_token_set / weight_sum
            w_jw_norm = w_jaro / weight_sum
            w_lv_norm = w_lev / weight_sum
        else:
            w_ts_norm, w_jw_norm, w_lv_norm = w_token_set, w_jaro, w_lev
            
        fuz_threshold = st.slider("Fuzzy Match Similarity Threshold (%)", min_value=50, max_value=100, value=80, key="fuz_thresh_slider")
        
    with col_fuz_2:
        st.markdown("#### Calculated Score Evaluation")
        
        engine_fuz = FuzzyMatchEngine(
            threshold=fuz_threshold,
            weight_token_set=w_ts_norm,
            weight_jaro_winkler=w_jw_norm,
            weight_levenshtein=w_lv_norm
        )
        
        scores = engine_fuz.calculate_scores(bank_narration, ledger_narration)
        final_score = scores["confidence_score"]
        
        # Color based status card
        if final_score >= fuz_threshold:
            st.markdown(f"""
            <div class="glass-card" style="border-left: 5px solid #2ed573;">
                <h3 style="color:#2ed573; margin:0;">🟢 FUZZY MATCH DISCOVERED</h3>
                <p style="font-size:24px; font-weight:bold; margin: 8px 0;">Composite Score: {final_score}%</p>
                <p style="margin:0;">Confidence exceeds the {fuz_threshold}% threshold setting.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="glass-card" style="border-left: 5px solid #ff4757;">
                <h3 style="color:#ff4757; margin:0;">🔴 NO MATCH RESOLVED</h3>
                <p style="font-size:24px; font-weight:bold; margin: 8px 0;">Composite Score: {final_score}%</p>
                <p style="margin:0;">Confidence is below the {fuz_threshold}% threshold setting. Pushed to Exceptions.</p>
            </div>
            """, unsafe_allow_html=True)
            
        st.markdown("#### Component Breakdown")
        
        # Render beautiful metric columns
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("Token Set Ratio", f"{scores['token_set_ratio']}%", f"Weight: {w_ts_norm:.2f}")
        m_col2.metric("Jaro-Winkler Ratio", f"{scores['jaro_winkler']}%", f"Weight: {w_jw_norm:.2f}")
        m_col3.metric("Levenshtein Ratio", f"{scores['levenshtein']}%", f"Weight: {w_lv_norm:.2f}")
        
        # Comparison helper
        st.markdown("""
        **Metric Capabilities Summary:**
        - **Token Set Ratio**: Splits strings into words/tokens, sorts them alphabetically, and matches intersection subsets. Highly resilient against extra tracking words (e.g. `"SEATTLE CA"`).
        - **Jaro-Winkler**: Measures transposition counts. Excellent at resolving slight letter substitutions or trailing reference IDs.
        - **Levenshtein**: Standard char edit count. Captures simple typos, insertions, or deletions.
        """)

# ==============================================================================
# TAB 3: RULE SIMULATOR & SPLIT VISUALIZER
# ==============================================================================
with tab_rules:
    st.markdown("### Advanced Rule-Based Simulator & Split Visualizer")
    st.markdown("""
    Simulate advanced rule-chain matching on currency deviations, splits, and aggregate many-to-many transactions.
    Enable/disable individual rules and inspect the priority reconciliation pipeline.
    """)
    
    col_sim_1, col_sim_2 = st.columns([1, 2])
    
    with col_sim_1:
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.markdown("#### Rule Chain Priorities")
        
        rule_tol_enabled = st.checkbox("Priority 1: Date & Amount Tolerance", value=True)
        rule_fx_enabled = st.checkbox("Priority 2: FX Variance Handling (EUR/USD/GBP)", value=True)
        rule_split_enabled = st.checkbox("Priority 3: Split Transactions (1:N, N:1 Sum)", value=True)
        rule_m2m_enabled = st.checkbox("Priority 4: Many-to-Many Group Settlements", value=True)
        
        st.markdown("---")
        st.markdown("#### Simulation Data Profile")
        data_scenario = st.selectbox(
            "Load Reconciliation Dataset",
            ["Invoice Batch Split (1:N)", "Multi-Currency Cross-Border (FX)", "Aggregate Settlement Bundle (M:N)"]
        )
        
        sim_run_btn = st.button("⚙️ Simulate Reconciliation Chain", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col_sim_2:
        # Load synthetic transactions based on chosen scenario
        sim_bank = []
        sim_ledger = []
        
        if data_scenario == "Invoice Batch Split (1:N)":
            sim_bank = [
                {"id": 1, "reference": "BATCH-001", "bank_account": "ACC_OP", "currency": "USD", "amount": Decimal("5000.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED", "source_system": "bank_statement"}
            ]
            sim_ledger = [
                {"id": 101, "reference": "INV-101", "bank_account": "ACC_OP", "currency": "USD", "amount": Decimal("2000.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED", "source_system": "internal_ledger"},
                {"id": 102, "reference": "INV-102", "bank_account": "ACC_OP", "currency": "USD", "amount": Decimal("3000.00"), "transaction_date": date(2026, 5, 21), "status": "UNMATCHED", "source_system": "internal_ledger"},
                {"id": 103, "reference": "INV-OTHER", "bank_account": "ACC_OP", "currency": "USD", "amount": Decimal("4500.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED", "source_system": "internal_ledger"}
            ]
        elif data_scenario == "Multi-Currency Cross-Border (FX)":
            sim_bank = [
                {"id": 1, "reference": "TX-GLOBAL-99", "bank_account": "ACC_GLOBAL", "currency": "EUR", "amount": Decimal("100.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED", "source_system": "bank_statement"}
            ]
            sim_ledger = [
                # 100 EUR converted at 1.08 = $108.00. Booking records $107.50 due to minor rate delay (0.46% variance)
                {"id": 101, "reference": "TX-GLOBAL-99", "bank_account": "ACC_GLOBAL", "currency": "USD", "amount": Decimal("107.50"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED", "source_system": "internal_ledger"}
            ]
        else:  # Many-to-Many
            sim_bank = [
                {"id": 1, "reference": "REF-BUNDLE", "bank_account": "ACC_SETTLE", "currency": "USD", "amount": Decimal("100.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED", "source_system": "bank_statement"},
                {"id": 2, "reference": "REF-BUNDLE", "bank_account": "ACC_SETTLE", "currency": "USD", "amount": Decimal("200.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED", "source_system": "bank_statement"},
                {"id": 3, "reference": "REF-BUNDLE", "bank_account": "ACC_SETTLE", "currency": "USD", "amount": Decimal("300.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED", "source_system": "bank_statement"}
            ]
            sim_ledger = [
                {"id": 101, "reference": "REF-BUNDLE", "bank_account": "ACC_SETTLE", "currency": "USD", "amount": Decimal("250.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED", "source_system": "internal_ledger"},
                {"id": 102, "reference": "REF-BUNDLE", "bank_account": "ACC_SETTLE", "currency": "USD", "amount": Decimal("350.00"), "transaction_date": date(2026, 5, 22), "status": "UNMATCHED", "source_system": "internal_ledger"}
            ]

        # Display raw unmatched transaction lists
        st.markdown("#### Input Transaction Sheets (Unmatched Pool)")
        
        c_bank, c_ledg = st.columns(2)
        with c_bank:
            st.markdown("**🏦 Bank Statement Pool**")
            st.dataframe(pd.DataFrame(sim_bank)[["id", "reference", "amount", "currency", "transaction_date", "status"]], use_container_width=True, hide_index=True)
            
        with c_ledg:
            st.markdown("**📜 Ledger Entry Pool**")
            st.dataframe(pd.DataFrame(sim_ledger)[["id", "reference", "amount", "currency", "transaction_date", "status"]], use_container_width=True, hide_index=True)

        if sim_run_btn:
            # Build and load engines
            active_rules = []
            if rule_tol_enabled:
                active_rules.append(ToleranceRule(date_tolerance_days=3, amount_tolerance=1.50))
            if rule_fx_enabled:
                active_rules.append(FXVarianceRule(percentage_tolerance=1.5))
            if rule_split_enabled:
                active_rules.append(SplitTransactionRule())
            if rule_m2m_enabled:
                active_rules.append(ManyToManySettlementRule())
                
            engine_rules = RuleEngine(rules=active_rules)
            matches = engine_rules.reconcile(sim_bank, sim_ledger)
            
            st.markdown("#### Simulated Reconciliation Matches")
            if not matches:
                st.info("❌ No rule matches discovered. Transactions will be logged as Exceptions.")
            else:
                for idx, m in enumerate(matches):
                    # Gather identifiers
                    b_ids = [str(ReconciliationRule._get_field(tx, 'id')) for tx in m.bank_transactions]
                    l_ids = [str(ReconciliationRule._get_field(tx, 'id')) for tx in m.ledger_transactions]
                    
                    st.markdown(f"""
                    <div class="glass-card" style="border-left: 5px solid #00C6FF; margin-bottom: 12px;">
                        <h4 style="color:#00C6FF; margin:0 0 4px 0;">⚡ Match #{idx+1}: {m.rule_name}</h4>
                        <p style="margin:4px 0;"><strong>Matched Bank ID(s)</strong>: <code>[{", ".join(b_ids)}]</code> ➔ <strong>Matched Ledger ID(s)</strong>: <code>[{", ".join(l_ids)}]</code></p>
                        <p style="margin:4px 0; font-style:italic; color:rgba(255,255,255,0.7);">{m.match_details}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                st.success(f"Successfully processed {len(matches)} rule group matches! Unmatched queue cleared.")
        else:
            st.info("💡 Review the transaction pools, configure the rule checklist, and click **Simulate Reconciliation Chain** to run matches.")

# ==============================================================================
# TAB 4: CONFIDENCE SCORER PLAYGROUND
# ==============================================================================
with tab_confidence:
    st.markdown("### Weighted Confidence Scorer Playground")
    st.markdown("""
    Evaluate arbitrary transaction pairs, calculate normalized field-level matching scores $[0.0, 1.0]$, 
    and simulate automated routing vs manual review queues.
    """)
    
    col_conf_1, col_conf_2 = st.columns([1, 1])
    
    with col_conf_1:
        st.markdown("#### Configure Engine Weights")
        
        w_ref = st.slider("Reference Score Weight", 0.0, 1.0, 0.35, 0.05, key="w_ref_slider")
        w_amt = st.slider("Amount Score Weight", 0.0, 1.0, 0.25, 0.05, key="w_amt_slider")
        w_date = st.slider("Date Proximity Weight", 0.0, 1.0, 0.15, 0.05, key="w_date_slider")
        w_desc = st.slider("Description Likeness Weight", 0.0, 1.0, 0.15, 0.05, key="w_desc_slider")
        w_acc = st.slider("Account Match Weight", 0.0, 1.0, 0.05, 0.05, key="w_acc_slider")
        w_ccy = st.slider("Currency Match Weight", 0.0, 1.0, 0.05, 0.05, key="w_ccy_slider")
        
        st.markdown("#### Configurable Routing Thresholds")
        thresh_auto = st.slider("Auto-Match Approval Limit (0.0 - 1.0)", 0.50, 1.00, 0.85, 0.05)
        thresh_manual = st.slider("Manual Review Dispatch Limit (0.0 - 1.0)", 0.30, 0.90, 0.60, 0.05)
        
        st.markdown("#### Date Proximity Decay")
        decay_rate = st.slider("Date Proximity Decay Rate (\u03bb)", 0.05, 0.50, 0.15, 0.05, help="Controls date score loss. Higher means date differences penalize score much faster.")
        
    with col_conf_2:
        st.markdown("#### Transaction Comparison Sandbox")
        
        st.markdown("##### 🏦 Bank Statement Record")
        b_col1, b_col2, b_col3 = st.columns(3)
        sim_b_ref = b_col1.text_input("Bank Reference", value="TX-1002-REF", key="sb_ref")
        sim_b_amt = b_col2.number_input("Bank Amount", value=250.00, step=10.0, key="sb_amt")
        sim_b_date = b_col3.date_input("Bank Value Date", date(2026, 5, 22), key="sb_date")
        
        b_col4, b_col5, b_col6 = st.columns(3)
        sim_b_desc = b_col4.text_input("Bank Description", value="Amazon Mktp Purchase CA", key="sb_desc")
        sim_b_acc = b_col5.text_input("Bank Account", value="ACC-OPERATIONAL-1", key="sb_acc")
        sim_b_ccy = b_col6.text_input("Bank Currency", value="USD", key="sb_ccy")
        
        st.markdown("##### 📜 Internal Ledger Record")
        l_col1, l_col2, l_col3 = st.columns(3)
        sim_l_ref = l_col1.text_input("Ledger Reference", value="TX-1002-REF", key="sl_ref")
        sim_l_amt = l_col2.number_input("Ledger Amount", value=250.00, step=10.0, key="sl_amt")
        sim_l_date = l_col3.date_input("Ledger Booking Date", date(2026, 5, 20), key="sl_date")
        
        l_col4, l_col5, l_col6 = st.columns(3)
        sim_l_desc = l_col4.text_input("Ledger Description", value="Amazon Marketplace Seattle", key="sl_desc")
        sim_l_acc = l_col5.text_input("Ledger Account", value="ACC-OPERATIONAL-1", key="sl_acc")
        sim_l_ccy = l_col6.text_input("Ledger Currency", value="USD", key="sl_ccy")
        
        st.markdown("---")
        st.markdown("#### Sandbox Scoring Evaluation")
        
        # Instantiate Confidence Scoring Engine
        scoring_engine = ConfidenceScoringEngine(
            weight_reference=w_ref,
            weight_amount=w_amt,
            weight_date=w_date,
            weight_description=w_desc,
            weight_account=w_acc,
            weight_currency=w_ccy,
            auto_match_threshold=thresh_auto,
            manual_review_threshold=thresh_manual,
            date_decay_rate=decay_rate
        )
        
        # Format structures for evaluation
        tx_bank = {
            "reference": sim_b_ref, "amount": Decimal(str(sim_b_amt)), 
            "transaction_date": sim_b_date, "description": sim_b_desc, 
            "bank_account": sim_b_acc, "currency": sim_b_ccy
        }
        tx_ledger = {
            "reference": sim_l_ref, "amount": Decimal(str(sim_l_amt)), 
            "transaction_date": sim_l_date, "description": sim_l_desc, 
            "bank_account": sim_l_acc, "currency": sim_l_ccy
        }
        
        res = scoring_engine.evaluate(tx_bank, tx_ledger)
        
        # Beautiful progress bar visualizer
        c_score = res.final_score
        st.markdown(f"**Confidence Index Match Level**: `{c_score:.4f}`")
        st.progress(float(c_score))
        
        # Status Card rendering
        if res.classification == "AUTO_MATCH":
            st.markdown(f"""
            <div class="glass-card" style="border-left: 5px solid #2ed573; padding: 12px; margin-bottom: 12px;">
                <h4 style="color:#2ed573; margin:0;">🟢 AUTO MATCH APPROVED</h4>
                <p style="margin: 4px 0;">Final Index <strong>{c_score:.4f}</strong> is equal or above Auto-Match limit (<strong>{thresh_auto:.2f}</strong>).</p>
            </div>
            """, unsafe_allow_html=True)
        elif res.classification == "MANUAL_REVIEW":
            st.markdown(f"""
            <div class="glass-card" style="border-left: 5px solid #ffa502; padding: 12px; margin-bottom: 12px;">
                <h4 style="color:#ffa502; margin:0;">🟡 MANUAL REVIEW FLAG ISSUED</h4>
                <p style="margin: 4px 0;">Final Index <strong>{c_score:.4f}</strong> dispatched to Operator console (Limit: <strong>{thresh_manual:.2f}</strong> - <strong>{thresh_auto:.2f}</strong>).</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="glass-card" style="border-left: 5px solid #ff4757; padding: 12px; margin-bottom: 12px;">
                <h4 style="color:#ff4757; margin:0;">🔴 EXCEPTION EXCLUSION DISPATCHED</h4>
                <p style="margin: 4px 0;">Final Index <strong>{c_score:.4f}</strong> is rejected below manual limit (<strong>{thresh_manual:.2f}</strong>). Logged to exceptions queue.</p>
            </div>
            """, unsafe_allow_html=True)
            
        # Score breakdowns table
        st.markdown("##### Granular Field Contribution Breakdown")
        
        breakdown_df = pd.DataFrame([
            {"Field Evaluated": "Reference ID", "Similarity Score": f"{res.ref_score:.4f}", "Normalized Weight": f"{res.ref_weight:.4f}", "Net Match Contribution": f"{res.ref_score * res.ref_weight:.4f}"},
            {"Field Evaluated": "Amount Value", "Similarity Score": f"{res.amt_score:.4f}", "Normalized Weight": f"{res.amt_weight:.4f}", "Net Match Contribution": f"{res.amt_score * res.amt_weight:.4f}"},
            {"Field Evaluated": "Value Date", "Similarity Score": f"{res.date_score:.4f}", "Normalized Weight": f"{res.date_weight:.4f}", "Net Match Contribution": f"{res.date_score * res.date_weight:.4f}"},
            {"Field Evaluated": "Description", "Similarity Score": f"{res.desc_score:.4f}", "Normalized Weight": f"{res.desc_weight:.4f}", "Net Match Contribution": f"{res.desc_score * res.desc_weight:.4f}"},
            {"Field Evaluated": "Bank Account", "Similarity Score": f"{res.acc_score:.4f}", "Normalized Weight": f"{res.acc_weight:.4f}", "Net Match Contribution": f"{res.acc_score * res.acc_weight:.4f}"},
            {"Field Evaluated": "Currency", "Similarity Score": f"{res.ccy_score:.4f}", "Normalized Weight": f"{res.ccy_weight:.4f}", "Net Match Contribution": f"{res.ccy_score * res.ccy_weight:.4f}"},
        ])
        
        st.dataframe(breakdown_df, use_container_width=True, hide_index=True)
