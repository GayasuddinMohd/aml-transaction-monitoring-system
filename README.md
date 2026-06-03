🌐 **Live Demo:** [AML Transaction Monitoring System](https://aml-transaction-monitoring-system-cewdjuxzhzrorweexrvwno.streamlit.app/)

# 🛡️ End-to-End AML Transaction Monitoring System

A production-grade **Anti-Money Laundering (AML) Transaction Monitoring System** built with Python and SQL — simulating real-world fraud analytics pipelines used at banks and financial institutions.

> Built as a portfolio project targeting Fraud Analytics roles requiring SQL, Python, and domain knowledge.

---

## 📐 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AML TMS Pipeline                        │
├─────────────┬──────────────┬──────────────┬─────────────────┤
│  Data Layer │ Rules Engine │ Alert Scoring│  Investigation  │
│             │              │              │   Dashboard     │
│  SQLite DB  │  SQL Views   │  Python +    │   Streamlit     │
│  300 custs  │  8 typology  │  Risk Matrix │   5 pages       │
│  ~700 accs  │  detection   │  0-100 score │   Alert Queue   │
│  ~4500 txns │  queries     │  Priorities  │   Customer 360  │
└─────────────┴──────────────┴──────────────┴─────────────────┘
```

---

## 🚨 AML Typologies Detected

| Rule | Typology | Regulatory Basis |
|------|----------|-----------------|
| 1 | **Structuring** — Multiple cash deposits just below $10K | 31 U.S.C. § 5324 (BSA) |
| 2 | **Smurfing** — Multiple senders depositing same amount to one account | FATF Recommendation 29 |
| 3 | **Layering** — Rapid pass-through / funnel account (72h hop) | FATF 40 Recommendations |
| 4 | **Round-Tripping** — Funds sent offshore and returned within 90 days | FinCEN SAR guidance |
| 5 | **High-Risk Geography** — Wires to/from FATF-listed / sanctioned countries | OFAC / FinCEN |
| 6 | **Velocity Spike** — 3× daily transaction count vs. account average | Behavioral analytics |
| 7 | **PEP / Sanctions** — Transactions by Politically Exposed Persons | BSA / OFAC |
| 8 | **Dormant Reactivation** — 180+ day dormant account sudden large txn | Internal control |

---

## 📁 Project Structure

```
aml_system/
├── data/
│   ├── aml_transactions.db          # SQLite database (generated)
│   └── ground_truth_patterns.json   # Injected pattern labels (for validation)
│
├── sql/
│   ├── schema.sql                   # Full DB schema (7 tables + indexes)
│   └── rules_engine.sql             # 8 AML detection views
│
├── src/
│   ├── data_generator.py            # Synthetic data + suspicious pattern injection
│   ├── rules_engine.py              # Rules runner + risk scoring + alert writer
│   └── run_pipeline.py              # Master pipeline (run this first)
│
├── dashboard/
│   └── app.py                       # Streamlit 5-page investigation dashboard
│
├── requirements.txt
└── README.md
```

---

## ⚡ Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the full pipeline
```bash
python src/run_pipeline.py
```

This generates ~300 customers, ~700 accounts, ~4,500 transactions (including injected suspicious patterns), then runs all 8 AML rules and writes alerts to the database.

### 3. Launch the dashboard
```bash
streamlit run dashboard/app.py
```

---

## 📊 Dashboard Pages

| Page | Description |
|------|-------------|
| **Executive Dashboard** | KPIs, alert volume, typology breakdown, risk heatmap |
| **Alert Queue** | Filter by priority/type/score, action alerts (Review → Escalate → SAR / No Action) |
| **Customer 360** | Full customer profile, accounts, alert history, transaction chart |
| **Transaction Explorer** | Filter/search all transactions by type, amount, geography |
| **SAR Case Manager** | Draft Suspicious Activity Reports from escalated alerts |

---

## 🔬 Risk Scoring Logic

Alerts are scored 0–100 using a weighted matrix:

```
Base Score (by typology)
    + Customer Risk Rating Boost  (PEP: +25, High: +15, Medium: +5)
    + PEP Flag Boost              (+10)
    + Sanctioned Customer Boost   (+30)
    + Cross-Border Boost          (+5)
    + Typology-Specific Modifiers (e.g. tight structuring window, pass-through %)
    = Final Risk Score (capped at 100)
```

Priority mapping:
- **Critical**: 85–100
- **High**: 65–84
- **Medium**: 40–64
- **Low**: 0–39

---

## 🗄️ Database Schema

```
customers       → KYC data, risk rating, PEP/sanctions flags
accounts        → Account type, country, status, balance
transactions    → All transaction records with counterparty info
high_risk_countries → FATF grey/black list + offshore jurisdictions
aml_alerts      → Generated alerts with risk scores and investigation status
sar_cases       → SAR drafts linked to escalated alerts
```

---

## 💼 Skills Demonstrated

This project directly maps to what fraud analytics hiring managers evaluate:

| Skill | Where |
|-------|-------|
| **SQL** | 8 complex detection views with window functions, CTEs, self-joins |
| **Python** | Data generation, rule orchestration, scoring logic |
| **Fraud Domain Knowledge** | Real AML typologies with regulatory citations |
| **Analytical Thinking** | Risk scoring matrix, priority triage logic |
| **Data Modeling** | Normalized schema with appropriate indexes |
| **Business Communication** | Alert descriptions written for analyst consumption |

---

## 📚 References

- [FinCEN SAR Activity Review](https://www.fincen.gov/resources/advisoriesfatf/publications)
- [FATF 40 Recommendations](https://www.fatf-gafi.org/en/topics/fatf-recommendations.html)
- [Bank Secrecy Act — 31 U.S.C. § 5324](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title31-section5324)
- [OFAC Sanctions List](https://ofac.treasury.gov/sanctions-list-service)

---

*Built with Python · SQLite · Streamlit · Plotly*
