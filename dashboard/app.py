"""
AML Transaction Monitoring System
Module 3: Streamlit Investigation Dashboard
============================================
Run with: streamlit run dashboard/app.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime, date
import plotly.express as px
import plotly.graph_objects as go

DB_PATH = "data/aml_transactions.db"

# ── Auto-setup: generate data if DB doesn't exist ────────────────────────────
def setup_database():
    os.makedirs("data", exist_ok=True)
    needs_setup = False
    if not os.path.exists(DB_PATH):
        needs_setup = True
    else:
        try:
            conn = sqlite3.connect(DB_PATH)
            count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            conn.close()
            if count == 0:
                needs_setup = True
        except Exception:
            needs_setup = True
    if needs_setup:
        with st.spinner("🔧 First run: generating data... (~15 seconds)"):
            try:
                from src.data_generator import main as gen_main
                from src.rules_engine import main as rules_main
                gen_main()
                rules_main()
            except Exception as e:
                st.error(f"Setup failed: {e}")
                st.stop()
        st.success("✅ Database ready!")
        st.rerun()

setup_database()

# ── Theming ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AML Transaction Monitoring System",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

PRIORITY_COLORS = {
    "critical": "#FF3B30",
    "high":     "#FF9500",
    "medium":   "#FFCC00",
    "low":      "#34C759",
}

STATUS_COLORS = {
    "open":            "#FF3B30",
    "under_review":    "#FF9500",
    "escalated":       "#AF52DE",
    "closed_sar":      "#007AFF",
    "closed_no_action":"#8E8E93",
}

# ── DB helpers ────────────────────────────────────────────────────────────────
@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql, params=()):
    conn = get_conn()
    return pd.read_sql_query(sql, conn, params=params)


def execute(sql, params=()):
    conn = get_conn()
    conn.execute(sql, params)
    conn.commit()


# ── Sidebar navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛡️ AML Monitor")
    st.markdown("---")
    page = st.radio("Navigate", [
        "📊 Executive Dashboard",
        "🚨 Alert Queue",
        "🔍 Customer 360",
        "💸 Transaction Explorer",
        "📋 SAR Case Manager",
    ])
    st.markdown("---")
    st.caption(f"DB: `{DB_PATH}`")
    st.caption(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — EXECUTIVE DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
if page == "📊 Executive Dashboard":
    st.title("📊 AML Executive Dashboard")
    st.caption("Real-time overview of transaction monitoring and alert pipeline")

    # KPI row
    kpis = query("""
        SELECT
            (SELECT COUNT(*) FROM transactions)                       AS total_txns,
            (SELECT ROUND(SUM(amount)/1e6, 2) FROM transactions)     AS total_volume_m,
            (SELECT COUNT(*) FROM aml_alerts)                        AS total_alerts,
            (SELECT COUNT(*) FROM aml_alerts WHERE status='open')    AS open_alerts,
            (SELECT COUNT(*) FROM aml_alerts WHERE priority='critical') AS critical_alerts,
            (SELECT COUNT(*) FROM customers WHERE is_sanctioned=1)   AS sanctioned_customers
    """).iloc[0]

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Transactions", f"{int(kpis['total_txns']):,}")
    c2.metric("Total Volume",       f"${kpis['total_volume_m']}M")
    c3.metric("Total Alerts",       f"{int(kpis['total_alerts']):,}")
    c4.metric("Open Alerts",        f"{int(kpis['open_alerts']):,}",  delta_color="inverse")
    c5.metric("⚠️ Critical",        f"{int(kpis['critical_alerts']):,}", delta_color="inverse")
    c6.metric("Sanctioned Customers", f"{int(kpis['sanctioned_customers']):,}", delta_color="inverse")

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        # Alert type distribution
        df_types = query("""
            SELECT alert_type, COUNT(*) as cnt
            FROM aml_alerts GROUP BY alert_type ORDER BY cnt DESC
        """)
        fig = px.bar(
            df_types, x="cnt", y="alert_type", orientation="h",
            title="Alerts by Typology",
            color="cnt", color_continuous_scale="Reds",
            labels={"cnt": "Alert Count", "alert_type": "Typology"}
        )
        fig.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Priority donut
        df_pri = query("""
            SELECT priority, COUNT(*) as cnt
            FROM aml_alerts GROUP BY priority
        """)
        colors = [PRIORITY_COLORS.get(p, "#999") for p in df_pri["priority"]]
        fig2 = go.Figure(go.Pie(
            labels=df_pri["priority"], values=df_pri["cnt"],
            hole=0.55, marker_colors=colors,
            textinfo="label+percent"
        ))
        fig2.update_layout(title="Alert Priority Distribution", height=350)
        st.plotly_chart(fig2, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        # Transaction volume over time
        df_vol = query("""
            SELECT transaction_date,
                   COUNT(*) as txn_count,
                   ROUND(SUM(amount)/1000, 1) as volume_k
            FROM transactions
            GROUP BY transaction_date
            ORDER BY transaction_date
        """)
        fig3 = px.area(
            df_vol, x="transaction_date", y="volume_k",
            title="Daily Transaction Volume ($K)",
            labels={"transaction_date": "Date", "volume_k": "Volume ($K)"}
        )
        fig3.update_layout(height=300)
        st.plotly_chart(fig3, use_container_width=True)

    with col4:
        # Top 10 highest risk customers
        df_risk = query("""
            SELECT c.full_name, c.risk_rating, c.customer_segment,
                   COUNT(al.alert_id) as alert_count,
                   MAX(al.risk_score) as max_score
            FROM customers c
            JOIN aml_alerts al ON c.customer_id = al.customer_id
            GROUP BY c.customer_id
            ORDER BY max_score DESC, alert_count DESC
            LIMIT 10
        """)
        st.markdown("##### 🔴 Top 10 Riskiest Customers")
        st.dataframe(
            df_risk.style.background_gradient(subset=["max_score"], cmap="Reds"),
            use_container_width=True, height=270
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — ALERT QUEUE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🚨 Alert Queue":
    st.title("🚨 Alert Queue")
    st.caption("Review, triage, and action open AML alerts")

    # Filters
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        priority_filter = st.multiselect("Priority", ["critical","high","medium","low"],
                                          default=["critical","high"])
    with f2:
        status_filter = st.multiselect("Status",
                                        ["open","under_review","escalated","closed_sar","closed_no_action"],
                                        default=["open","under_review"])
    with f3:
        type_filter = st.multiselect("Alert Type", [
            "structuring","smurfing","layering","round_tripping",
            "high_risk_geography","velocity_spike","pep_transaction",
            "sanctioned_customer_transaction","dormant_reactivation"
        ])
    with f4:
        score_min = st.slider("Min Risk Score", 0, 100, 40)

    # Build query
    where_clauses = [f"al.risk_score >= {score_min}"]
    if priority_filter:
        plist = ",".join(f"'{p}'" for p in priority_filter)
        where_clauses.append(f"al.priority IN ({plist})")
    if status_filter:
        slist = ",".join(f"'{s}'" for s in status_filter)
        where_clauses.append(f"al.status IN ({slist})")
    if type_filter:
        tlist = ",".join(f"'{t}'" for t in type_filter)
        where_clauses.append(f"al.alert_type IN ({tlist})")

    where_sql = " AND ".join(where_clauses)

    df_alerts = query(f"""
        SELECT
            al.alert_id, al.alert_type, al.priority, al.risk_score,
            al.status, al.detected_at,
            c.full_name as customer_name, c.risk_rating, c.is_pep, c.is_sanctioned,
            al.alert_description, al.customer_id
        FROM aml_alerts al
        JOIN customers c ON al.customer_id = c.customer_id
        WHERE {where_sql}
        ORDER BY al.risk_score DESC, al.detected_at DESC
    """)

    st.markdown(f"**{len(df_alerts)} alerts** match current filters")
    st.markdown("---")

    if df_alerts.empty:
        st.info("No alerts match the selected filters.")
    else:
        # Render each alert as a card
        for _, row in df_alerts.head(50).iterrows():
            pri_color = PRIORITY_COLORS.get(row["priority"], "#999")
            pep_badge = " 🏛️ PEP" if row["is_pep"] else ""
            sanc_badge = " ⛔ SANCTIONED" if row["is_sanctioned"] else ""

            with st.expander(
                f"{'🔴' if row['priority']=='critical' else '🟠' if row['priority']=='high' else '🟡' if row['priority']=='medium' else '🟢'} "
                f"[{row['priority'].upper()}] {row['alert_type'].replace('_',' ').title()}  —  "
                f"{row['customer_name']}{pep_badge}{sanc_badge}  |  Score: {row['risk_score']}/100"
            ):
                c1, c2, c3, c4 = st.columns(4)
                c1.markdown(f"**Alert ID**\n\n`{row['alert_id']}`")
                c2.markdown(f"**Status**\n\n`{row['status']}`")
                c3.markdown(f"**Risk Rating**\n\n`{row['risk_rating']}`")
                c4.markdown(f"**Detected**\n\n`{str(row['detected_at'])[:16]}`")
                st.markdown(f"**Description:** {row['alert_description']}")

                # Action buttons
                a1, a2, a3, a4, a5 = st.columns(5)
                with a1:
                    if st.button("▶️ Start Review", key=f"rev_{row['alert_id']}"):
                        execute("UPDATE aml_alerts SET status='under_review' WHERE alert_id=?",
                                (row["alert_id"],))
                        st.success("Status → Under Review")
                with a2:
                    if st.button("⬆️ Escalate", key=f"esc_{row['alert_id']}"):
                        execute("UPDATE aml_alerts SET status='escalated' WHERE alert_id=?",
                                (row["alert_id"],))
                        st.warning("Status → Escalated")
                with a3:
                    if st.button("📝 File SAR", key=f"sar_{row['alert_id']}"):
                        execute("UPDATE aml_alerts SET status='closed_sar' WHERE alert_id=?",
                                (row["alert_id"],))
                        st.info("Status → Closed (SAR Filed)")
                with a4:
                    if st.button("✅ No Action", key=f"na_{row['alert_id']}"):
                        execute("UPDATE aml_alerts SET status='closed_no_action' WHERE alert_id=?",
                                (row["alert_id"],))
                        st.success("Status → Closed (No Action)")
                with a5:
                    st.markdown(f"[🔍 Customer 360](?customer={row['customer_id']})")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — CUSTOMER 360
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Customer 360":
    st.title("🔍 Customer 360 View")

    # Customer search
    customers_df = query("SELECT customer_id, full_name, risk_rating FROM customers ORDER BY full_name")
    options = {f"{r['full_name']} ({r['customer_id']})": r['customer_id']
               for _, r in customers_df.iterrows()}
    selected_label = st.selectbox("Search Customer", list(options.keys()))
    cust_id = options[selected_label]

    # Customer profile
    cust = query("SELECT * FROM customers WHERE customer_id = ?", (cust_id,)).iloc[0]
    accs = query("SELECT * FROM accounts WHERE customer_id = ?", (cust_id,))
    alerts = query("""
        SELECT * FROM aml_alerts
        WHERE customer_id = ? ORDER BY risk_score DESC
    """, (cust_id,))
    txns = query("""
        SELECT t.* FROM transactions t
        JOIN accounts a ON t.sender_account_id = a.account_id
        WHERE a.customer_id = ?
        ORDER BY t.transaction_date DESC LIMIT 100
    """, (cust_id,))

    # Header
    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴", "pep": "🏛️"}.get(cust["risk_rating"], "⚪")
    st.markdown(f"## {risk_emoji} {cust['full_name']}")
    if cust["is_sanctioned"]: st.error("⛔ SANCTIONED CUSTOMER — Immediate escalation required")
    if cust["is_pep"]:        st.warning("🏛️ Politically Exposed Person (PEP)")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Risk Rating",    cust["risk_rating"].upper())
    col2.metric("KYC Status",     cust["kyc_status"])
    col3.metric("Segment",        cust["customer_segment"])
    col4.metric("Open Alerts",    len(alerts[alerts["status"] == "open"]) if not alerts.empty else 0)

    tab1, tab2, tab3, tab4 = st.tabs(["👤 Profile", "🏦 Accounts", "🚨 Alerts", "💸 Transactions"])

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Personal Details**")
            st.write(f"- **ID:** `{cust['customer_id']}`")
            st.write(f"- **DOB:** {cust['date_of_birth']}")
            st.write(f"- **Nationality:** {cust['nationality']}")
            st.write(f"- **Country:** {cust['country_of_residence']}")
            st.write(f"- **Occupation:** {cust['occupation']}")
        with c2:
            st.markdown("**Compliance Details**")
            st.write(f"- **Onboarded:** {cust['onboarded_date']}")
            st.write(f"- **KYC:** {cust['kyc_status']}")
            st.write(f"- **PEP:** {'Yes ⚠️' if cust['is_pep'] else 'No'}")
            st.write(f"- **Sanctioned:** {'YES ⛔' if cust['is_sanctioned'] else 'No'}")

    with tab2:
        if accs.empty:
            st.info("No accounts found.")
        else:
            st.dataframe(accs, use_container_width=True)

    with tab3:
        if alerts.empty:
            st.success("No alerts for this customer.")
        else:
            for _, al in alerts.iterrows():
                color = PRIORITY_COLORS.get(al["priority"], "#999")
                st.markdown(
                    f"**[{al['priority'].upper()}]** `{al['alert_type']}` — "
                    f"Score: **{al['risk_score']}/100** | Status: `{al['status']}`"
                )
                st.caption(al["alert_description"])
                st.markdown("---")

    with tab4:
        if txns.empty:
            st.info("No transactions found.")
        else:
            # Volume chart
            daily = txns.groupby("transaction_date")["amount"].sum().reset_index()
            fig = px.bar(daily, x="transaction_date", y="amount",
                         title="Transaction Volume Over Time",
                         labels={"amount": "Amount ($)", "transaction_date": "Date"})
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(txns[["transaction_id","transaction_date","transaction_type",
                                "amount","counterparty_country","channel","status"]],
                         use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — TRANSACTION EXPLORER
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "💸 Transaction Explorer":
    st.title("💸 Transaction Explorer")

    c1, c2, c3 = st.columns(3)
    with c1:
        txn_types = st.multiselect("Transaction Type",
            ["wire","cash_deposit","cash_withdrawal","ach","internal_transfer","check"],
            default=["wire","cash_deposit"])
    with c2:
        amount_range = st.slider("Amount Range ($)", 0, 300000, (0, 300000), step=1000)
    with c3:
        cross_border = st.selectbox("Cross-Border", ["All", "Yes", "No"])

    where = []
    if txn_types:
        tl = ",".join(f"'{t}'" for t in txn_types)
        where.append(f"t.transaction_type IN ({tl})")
    where.append(f"t.amount BETWEEN {amount_range[0]} AND {amount_range[1]}")
    if cross_border == "Yes": where.append("t.is_cross_border = 1")
    if cross_border == "No":  where.append("t.is_cross_border = 0")

    df_txns = query(f"""
        SELECT t.transaction_id, t.transaction_date, t.transaction_type,
               t.amount, t.currency, t.channel, t.counterparty_country,
               t.is_cross_border, t.description,
               c.full_name as customer_name, c.risk_rating
        FROM transactions t
        JOIN accounts a ON t.sender_account_id = a.account_id
        JOIN customers c ON a.customer_id = c.customer_id
        WHERE {' AND '.join(where)}
        ORDER BY t.amount DESC LIMIT 500
    """)

    st.markdown(f"**{len(df_txns)} transactions** (showing up to 500)")

    col1, col2 = st.columns(2)
    with col1:
        country_dist = df_txns.groupby("counterparty_country")["amount"].sum().nlargest(15).reset_index()
        fig = px.bar(country_dist, x="counterparty_country", y="amount",
                     title="Volume by Counterparty Country",
                     labels={"amount": "Total Amount ($)", "counterparty_country": "Country"})
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        type_dist = df_txns.groupby("transaction_type")["amount"].sum().reset_index()
        fig2 = px.pie(type_dist, names="transaction_type", values="amount",
                      title="Volume by Transaction Type")
        st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(df_txns, use_container_width=True, height=400)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — SAR CASE MANAGER
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📋 SAR Case Manager":
    st.title("📋 SAR Case Manager")
    st.caption("Draft and manage Suspicious Activity Reports")

    tab1, tab2 = st.tabs(["📝 Create New SAR", "📂 Existing Cases"])

    with tab1:
        st.markdown("### Create SAR from Escalated Alert")

        escalated = query("""
            SELECT al.alert_id, al.alert_type, al.risk_score,
                   c.full_name, c.customer_id, al.alert_description
            FROM aml_alerts al
            JOIN customers c ON al.customer_id = c.customer_id
            WHERE al.status IN ('escalated', 'under_review')
            ORDER BY al.risk_score DESC
        """)

        if escalated.empty:
            st.info("No escalated alerts available. Escalate an alert from the Alert Queue first.")
        else:
            alert_options = {
                f"{r['full_name']} | {r['alert_type']} | Score:{r['risk_score']}": r['alert_id']
                for _, r in escalated.iterrows()
            }
            chosen_label  = st.selectbox("Select Alert", list(alert_options.keys()))
            chosen_alert  = escalated[escalated["alert_id"] == alert_options[chosen_label]].iloc[0]

            st.markdown(f"**Alert:** {chosen_alert['alert_description']}")
            analyst_name  = st.text_input("Analyst Name", placeholder="Your name")
            susp_amount   = st.number_input("Total Suspicious Amount ($)", min_value=0.0, step=1000.0)
            narrative     = st.text_area("SAR Narrative", height=200, placeholder=
                "Describe the suspicious activity, why it is suspicious, and any relevant context...\n\n"
                "Example: The subject customer conducted 6 cash deposits ranging from $8,200-$9,800 "
                "over a 5-day period totaling $53,400. The transactions appear structured to avoid "
                "the $10,000 CTR reporting threshold under 31 U.S.C. § 5324...")
            filing_status = st.selectbox("Initial Status", ["draft", "pending_review"])

            if st.button("📝 Create SAR Case", type="primary"):
                if not analyst_name or not narrative:
                    st.error("Please fill in analyst name and narrative.")
                else:
                    case_id = "SAR-" + str(__import__("uuid").uuid4())[:8].upper()
                    get_conn().execute("""
                        INSERT INTO sar_cases
                        (case_id, alert_id, customer_id, analyst_name,
                         narrative, total_suspicious_amount, filing_status)
                        VALUES (?,?,?,?,?,?,?)
                    """, (case_id, chosen_alert["alert_id"], chosen_alert["customer_id"],
                          analyst_name, narrative, susp_amount, filing_status))
                    get_conn().commit()
                    st.success(f"✅ SAR Case `{case_id}` created successfully!")

    with tab2:
        cases = query("""
            SELECT sc.case_id, sc.filing_status, sc.analyst_name,
                   sc.total_suspicious_amount, sc.created_at,
                   c.full_name as customer_name,
                   al.alert_type, al.risk_score
            FROM sar_cases sc
            JOIN customers c  ON sc.customer_id = c.customer_id
            JOIN aml_alerts al ON sc.alert_id = al.alert_id
            ORDER BY sc.created_at DESC
        """)

        if cases.empty:
            st.info("No SAR cases yet. Create one from an escalated alert.")
        else:
            st.dataframe(cases, use_container_width=True)
