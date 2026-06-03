"""
AML Transaction Monitoring System
Module 3: Alert Scoring & Case Management Engine

Responsibilities:
  1. Run all SQL rules against the database → populate aml_alerts
  2. Apply a composite risk score (rule score + customer risk multiplier)
  3. Auto-group related alerts into investigation Cases
  4. Export alert summary to CSV for dashboard / reporting
"""

import sqlite3
import uuid
import os
import pandas as pd
from datetime import datetime

DB_PATH     = os.path.join(os.path.dirname(__file__), '..', 'data', 'aml_system.db')
RULES_PATH  = os.path.join(os.path.dirname(__file__), '..', 'sql',  'rules_engine.sql')
OUTPUT_DIR  = os.path.join(os.path.dirname(__file__), '..', 'outputs')

# ── Customer risk multipliers ──────────────────────────────────────────────────
RISK_MULTIPLIER = {
    'low':        1.0,
    'medium':     1.15,
    'high':       1.30,
    'pep':        1.45,
    'sanctioned': 1.60,
}

PRIORITY_THRESHOLDS = {
    'critical': 85,
    'high':     65,
    'medium':   40,
    'low':       0,
}

def get_priority(score: float) -> str:
    for label, threshold in PRIORITY_THRESHOLDS.items():
        if score >= threshold:
            return label
    return 'low'

# ── Step 1: Run SQL Rules ──────────────────────────────────────────────────────

def run_rules(conn: sqlite3.Connection) -> int:
    """Execute all AML detection SQL rules. Returns alert count inserted."""
    with open(RULES_PATH) as f:
        rules_sql = f.read()

    # Split on semicolons, keep only INSERT statements
    raw_stmts  = rules_sql.split(';')
    statements = []
    for s in raw_stmts:
        clean = s.strip()
        # Strip leading comments/dashes to find first real keyword
        lines = [l for l in clean.splitlines() if l.strip() and not l.strip().startswith('--')]
        if lines and lines[0].strip().upper().startswith('INSERT'):
            statements.append(clean)

    before = conn.execute("SELECT COUNT(*) FROM aml_alerts").fetchone()[0]
    for stmt in statements:
        try:
            conn.execute(stmt)
        except sqlite3.Error as e:
            print(f"  ⚠ Rule error: {e}")
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM aml_alerts").fetchone()[0]
    inserted = after - before
    print(f"✓ Rules engine: {inserted} new alerts inserted  (total: {after})")
    return inserted

# ── Step 2: Apply Composite Risk Score ────────────────────────────────────────

def apply_risk_scoring(conn: sqlite3.Connection):
    """
    Recalculate risk_score by multiplying base rule score by customer risk rating.
    Also update priority field accordingly.
    """
    alerts_df = pd.read_sql("""
        SELECT al.alert_id, al.risk_score, al.customer_id, c.risk_rating
        FROM aml_alerts al
        JOIN customers c ON al.customer_id = c.customer_id
    """, conn)

    if alerts_df.empty:
        print("  ⚠ No alerts to score.")
        return

    alerts_df['multiplier']    = alerts_df['risk_rating'].map(RISK_MULTIPLIER).fillna(1.0)
    alerts_df['adjusted_score'] = (alerts_df['risk_score'] * alerts_df['multiplier']).clip(upper=100).round(2)
    alerts_df['new_priority']  = alerts_df['adjusted_score'].apply(get_priority)

    for _, row in alerts_df.iterrows():
        conn.execute("""
            UPDATE aml_alerts
            SET risk_score = ?, priority = ?
            WHERE alert_id = ?
        """, (row['adjusted_score'], row['new_priority'], row['alert_id']))

    conn.commit()
    print(f"✓ Risk scoring applied to {len(alerts_df)} alerts")

    # Summary
    summary = alerts_df.groupby('new_priority').size().reindex(['critical','high','medium','low'], fill_value=0)
    for lvl, cnt in summary.items():
        print(f"    {lvl.upper():10s} → {cnt} alerts")

# ── Step 3: Auto-Case Grouping ────────────────────────────────────────────────

def create_cases(conn: sqlite3.Connection):
    """
    Group alerts by customer. If a customer has ≥2 alerts or ≥1 critical alert,
    open an investigation case.
    """
    eligible = pd.read_sql("""
        SELECT
            customer_id,
            COUNT(*)            AS alert_count,
            SUM(risk_score)     AS total_score,
            MAX(priority)       AS max_priority,
            GROUP_CONCAT(alert_id) AS alert_ids
        FROM aml_alerts
        WHERE status = 'open'
        GROUP BY customer_id
        HAVING alert_count >= 2 OR max_priority = 'critical'
    """, conn)

    analysts = ['analyst_1', 'analyst_2', 'analyst_3', 'analyst_4']
    cases_inserted = 0

    for _, row in eligible.iterrows():
        # Skip if case already exists for this customer
        existing = conn.execute(
            "SELECT COUNT(*) FROM cases WHERE customer_id = ? AND status != 'closed'",
            (row['customer_id'],)
        ).fetchone()[0]
        if existing:
            continue

        case_id   = f"CASE_{uuid.uuid4().hex[:8].upper()}"
        case_type = 'sar_investigation' if row['max_priority'] == 'critical' else 'enhanced_due_diligence'
        analyst   = analysts[cases_inserted % len(analysts)]

        conn.execute("""
            INSERT INTO cases (case_id, customer_id, case_type, opened_date, status,
                               total_suspicious_amount, assigned_analyst)
            VALUES (?, ?, ?, date('now'), 'open', ?, ?)
        """, (case_id, row['customer_id'], case_type,
              round(float(row['total_score']), 2), analyst))

        # Link alerts to case
        for alert_id in row['alert_ids'].split(','):
            conn.execute(
                "INSERT OR IGNORE INTO case_alerts (case_id, alert_id) VALUES (?, ?)",
                (case_id, alert_id.strip())
            )
        cases_inserted += 1

    conn.commit()
    print(f"✓ {cases_inserted} investigation cases created")

# ── Step 4: Export Reports ─────────────────────────────────────────────────────

def export_reports(conn: sqlite3.Connection):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Alert summary
    alerts_df = pd.read_sql("""
        SELECT
            al.alert_id,
            al.typology,
            al.rule_id,
            al.risk_score,
            al.priority,
            al.status,
            al.alert_date,
            c.full_name       AS customer_name,
            c.risk_rating,
            c.is_pep,
            c.nationality,
            t.amount,
            t.transaction_type,
            t.transaction_date,
            t.counterparty_country
        FROM aml_alerts al
        LEFT JOIN customers   c ON al.customer_id   = c.customer_id
        LEFT JOIN transactions t ON al.transaction_id = t.transaction_id
        ORDER BY al.risk_score DESC
    """, conn)
    alerts_df.to_csv(os.path.join(OUTPUT_DIR, 'alert_summary.csv'), index=False)

    # Case summary
    cases_df = pd.read_sql("""
        SELECT
            ca.case_id,
            ca.case_type,
            ca.status,
            ca.opened_date,
            ca.assigned_analyst,
            ca.total_suspicious_amount,
            c.full_name,
            c.risk_rating,
            COUNT(cal.alert_id) AS alert_count
        FROM cases ca
        JOIN customers   c   ON ca.customer_id = c.customer_id
        LEFT JOIN case_alerts cal ON ca.case_id = cal.case_id
        GROUP BY ca.case_id
        ORDER BY ca.total_suspicious_amount DESC
    """, conn)
    cases_df.to_csv(os.path.join(OUTPUT_DIR, 'case_summary.csv'), index=False)

    # Typology breakdown
    typology_df = pd.read_sql("""
        SELECT
            typology,
            rule_id,
            COUNT(*)            AS alert_count,
            AVG(risk_score)     AS avg_risk_score,
            SUM(CASE WHEN priority='critical' THEN 1 ELSE 0 END) AS critical_count
        FROM aml_alerts
        GROUP BY typology, rule_id
        ORDER BY avg_risk_score DESC
    """, conn)
    typology_df.to_csv(os.path.join(OUTPUT_DIR, 'typology_breakdown.csv'), index=False)

    print(f"✓ Reports exported to {OUTPUT_DIR}/")
    print(f"    alert_summary.csv      → {len(alerts_df)} rows")
    print(f"    case_summary.csv       → {len(cases_df)} rows")
    print(f"    typology_breakdown.csv → {len(typology_df)} rows")

# ── Main Orchestrator ──────────────────────────────────────────────────────────

def run_pipeline():
    print("\n" + "="*55)
    print("  AML TRANSACTION MONITORING — RULES PIPELINE")
    print("="*55)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    print("\n[1/4] Running SQL detection rules...")
    run_rules(conn)

    print("\n[2/4] Applying composite risk scoring...")
    apply_risk_scoring(conn)

    print("\n[3/4] Grouping alerts into investigation cases...")
    create_cases(conn)

    print("\n[4/4] Exporting reports...")
    export_reports(conn)

    conn.close()
    print("\n✅ Pipeline complete.\n")

if __name__ == '__main__':
    run_pipeline()
