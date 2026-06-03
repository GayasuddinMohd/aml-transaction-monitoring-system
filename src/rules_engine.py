"""
AML Transaction Monitoring System
Module 2: Rules Engine + Alert Scoring
=======================================
Executes SQL detection rules, scores alerts,
and writes them to the aml_alerts table.
"""

import sqlite3
import uuid
import re
from datetime import datetime

DB_PATH  = "data/aml_transactions.db"
SQL_PATH = "sql/rules_engine.sql"

# ── Risk scoring matrix ───────────────────────────────────────────────────────
# Each alert type has a base score; modifiers are applied based on customer risk

BASE_SCORES = {
    "structuring":              65,
    "smurfing":                 70,
    "layering":                 75,
    "round_tripping":           80,
    "high_risk_geography":      55,
    "velocity_spike":           50,
    "pep_transaction":          60,
    "sanctioned_customer_transaction": 95,
    "dormant_reactivation":     45,
}

PRIORITY_THRESHOLDS = {
    "critical": 85,
    "high":     65,
    "medium":   40,
    "low":      0,
}

RISK_RATING_BOOST = {
    "pep":    25,
    "high":   15,
    "medium":  5,
    "low":     0,
}


def new_alert_id():
    return "ALT-" + str(uuid.uuid4())[:8].upper()


def get_priority(score):
    for level, threshold in PRIORITY_THRESHOLDS.items():
        if score >= threshold:
            return level
    return "low"


def score_alert(base_score, customer_risk_rating, is_pep, is_sanctioned, cross_border=0):
    score = base_score
    score += RISK_RATING_BOOST.get(customer_risk_rating, 0)
    if is_pep:        score += 10
    if is_sanctioned: score += 30
    if cross_border:  score +=  5
    return min(score, 100)


# ── View runners ─────────────────────────────────────────────────────────────

def run_structuring(conn):
    rows = conn.execute("""
        SELECT vs.*, c.risk_rating, c.is_pep, c.is_sanctioned
        FROM v_structuring_alerts vs
        JOIN accounts a ON vs.account_id = a.account_id
        JOIN customers c ON a.customer_id = c.customer_id
    """).fetchall()

    alerts = []
    for r in rows:
        base    = BASE_SCORES["structuring"]
        # boost for very tight clustering
        if r["txn_count"] >= 6: base += 10
        score   = score_alert(base, r["risk_rating"], r["is_pep"], r["is_sanctioned"])
        alerts.append({
            "alert_id":          new_alert_id(),
            "transaction_id":    None,
            "customer_id":       r["customer_id"],
            "account_id":        r["account_id"],
            "alert_type":        r["alert_type"],
            "alert_description": f"{r['description']} | {r['txn_count']} txns totalling ${r['total_amount']:,.0f} between {r['window_start']} and {r['window_end']}",
            "risk_score":        score,
            "priority":          get_priority(score),
        })
    return alerts


def run_smurfing(conn):
    rows = conn.execute("""
        SELECT vs.*, c.risk_rating, c.is_pep, c.is_sanctioned
        FROM v_smurfing_alerts vs
        JOIN customers c ON vs.customer_id = c.customer_id
    """).fetchall()

    alerts = []
    for r in rows:
        base  = BASE_SCORES["smurfing"]
        if r["unique_senders"] >= 6: base += 10
        score = score_alert(base, r["risk_rating"], r["is_pep"], r["is_sanctioned"])
        alerts.append({
            "alert_id":          new_alert_id(),
            "transaction_id":    None,
            "customer_id":       r["customer_id"],
            "account_id":        r["account_id"],
            "alert_type":        r["alert_type"],
            "alert_description": f"{r['description']} | {r['unique_senders']} unique senders, avg ${r['avg_amount']:,.0f} each, total ${r['total_amount']:,.0f}",
            "risk_score":        score,
            "priority":          get_priority(score),
        })
    return alerts


def run_layering(conn):
    rows = conn.execute("""
        SELECT vl.*, c.risk_rating, c.is_pep, c.is_sanctioned
        FROM v_layering_alerts vl
        JOIN customers c ON vl.customer_id = c.customer_id
    """).fetchall()

    alerts = []
    for r in rows:
        base  = BASE_SCORES["layering"]
        if r["pass_through_pct"] and r["pass_through_pct"] >= 90: base += 10
        score = score_alert(base, r["risk_rating"], r["is_pep"], r["is_sanctioned"])
        alerts.append({
            "alert_id":          new_alert_id(),
            "transaction_id":    None,
            "customer_id":       r["customer_id"],
            "account_id":        r["account_id"],
            "alert_type":        r["alert_type"],
            "alert_description": f"{r['description']} | Received ${r['total_received']:,.0f}, forwarded {r['pass_through_pct']}% within 72h",
            "risk_score":        score,
            "priority":          get_priority(score),
        })
    return alerts


def run_round_tripping(conn):
    rows = conn.execute("""
        SELECT vr.*, c.risk_rating, c.is_pep, c.is_sanctioned
        FROM v_round_tripping_alerts vr
        JOIN accounts a ON vr.account_id = a.account_id
        JOIN customers c ON a.customer_id = c.customer_id
    """).fetchall()

    alerts = []
    for r in rows:
        base  = BASE_SCORES["round_tripping"]
        if r["days_gap"] and r["days_gap"] < 14: base += 10  # tighter loop = riskier
        score = score_alert(base, r["risk_rating"], r["is_pep"], r["is_sanctioned"], cross_border=1)
        alerts.append({
            "alert_id":          new_alert_id(),
            "transaction_id":    None,
            "customer_id":       r["customer_id"],
            "account_id":        r["account_id"],
            "alert_type":        r["alert_type"],
            "alert_description": f"{r['description']} | Sent ${r['amount_sent']:,.0f} to {r['offshore_country']}, returned ${r['amount_returned']:,.0f} after {r['days_gap']:.0f} days",
            "risk_score":        score,
            "priority":          get_priority(score),
        })
    return alerts


def run_high_risk_geo(conn):
    rows = conn.execute("""
        SELECT vg.*, c.risk_rating, c.is_pep, c.is_sanctioned
        FROM v_high_risk_geo_alerts vg
        JOIN customers c ON vg.customer_id = c.customer_id
    """).fetchall()

    alerts = []
    for r in rows:
        base  = BASE_SCORES["high_risk_geography"]
        if r["fatf_listed"]: base += 15
        if r["risk_level"] == "sanctioned": base += 30
        score = score_alert(base, r["risk_rating"], r["is_pep"], r["is_sanctioned"], cross_border=1)
        alerts.append({
            "alert_id":          new_alert_id(),
            "transaction_id":    r["transaction_id"],
            "customer_id":       r["customer_id"],
            "account_id":        r["account_id"],
            "alert_type":        r["alert_type"],
            "alert_description": f"{r['description']} | ${r['amount']:,.0f} to {r['risk_country_name']} ({r['risk_level']})",
            "risk_score":        score,
            "priority":          get_priority(score),
        })
    return alerts


def run_velocity(conn):
    rows = conn.execute("""
        SELECT vv.*, c.risk_rating, c.is_pep, c.is_sanctioned
        FROM v_velocity_alerts vv
        JOIN customers c ON vv.customer_id = c.customer_id
    """).fetchall()

    alerts = []
    for r in rows:
        base  = BASE_SCORES["velocity_spike"]
        if r["count_multiplier"] and r["count_multiplier"] >= 10: base += 15
        score = score_alert(base, r["risk_rating"], r["is_pep"], r["is_sanctioned"])
        alerts.append({
            "alert_id":          new_alert_id(),
            "transaction_id":    None,
            "customer_id":       r["customer_id"],
            "account_id":        r["account_id"],
            "alert_type":        r["alert_type"],
            "alert_description": f"{r['description']} | {r['daily_count']} txns on {r['transaction_date']} vs avg {r['avg_daily_count']}/day ({r['count_multiplier']}x spike)",
            "risk_score":        score,
            "priority":          get_priority(score),
        })
    return alerts


def run_pep_sanctions(conn):
    rows = conn.execute("""
        SELECT vp.*, c.risk_rating
        FROM v_pep_sanctions_alerts vp
        JOIN customers c ON vp.customer_id = c.customer_id
    """).fetchall()

    alerts = []
    for r in rows:
        base  = BASE_SCORES.get(r["alert_type"], 60)
        score = score_alert(base, r["risk_rating"], r["is_pep"], r["is_sanctioned"])
        alerts.append({
            "alert_id":          new_alert_id(),
            "transaction_id":    r["transaction_id"],
            "customer_id":       r["customer_id"],
            "account_id":        r["account_id"],
            "alert_type":        r["alert_type"],
            "alert_description": f"{r['description']} | {r['full_name']}, ${r['amount']:,.0f} on {r['transaction_date']}",
            "risk_score":        score,
            "priority":          get_priority(score),
        })
    return alerts


def run_dormant(conn):
    rows = conn.execute("""
        SELECT vd.*, c.risk_rating, c.is_pep, c.is_sanctioned
        FROM v_dormant_reactivation_alerts vd
        JOIN customers c ON vd.customer_id = c.customer_id
    """).fetchall()

    alerts = []
    for r in rows:
        base  = BASE_SCORES["dormant_reactivation"]
        if r["days_dormant"] and r["days_dormant"] >= 365: base += 15
        score = score_alert(base, r["risk_rating"], r["is_pep"], r["is_sanctioned"])
        alerts.append({
            "alert_id":          new_alert_id(),
            "transaction_id":    r["transaction_id"],
            "customer_id":       r["customer_id"],
            "account_id":        r["account_id"],
            "alert_type":        r["alert_type"],
            "alert_description": f"{r['description']} | Inactive {r['days_dormant']:.0f} days, then ${r['amount']:,.0f} on {r['reactivation_date']}",
            "risk_score":        score,
            "priority":          get_priority(score),
        })
    return alerts


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Load views
    with open(SQL_PATH) as f:
        conn.executescript(f.read())

    print("🔍 Running AML detection rules...")

    all_alerts = []
    runners = [
        ("Structuring",          run_structuring),
        ("Smurfing",             run_smurfing),
        ("Layering",             run_layering),
        ("Round-Tripping",       run_round_tripping),
        ("High-Risk Geography",  run_high_risk_geo),
        ("Velocity Spike",       run_velocity),
        ("PEP / Sanctions",      run_pep_sanctions),
        ("Dormant Reactivation", run_dormant),
    ]

    for name, fn in runners:
        alerts = fn(conn)
        all_alerts.extend(alerts)
        print(f"   ✓ {name:<25} → {len(alerts):>4} alerts")

    # Deduplicate: if same customer+type already alerted, keep highest score
    deduped = {}
    for al in all_alerts:
        key = (al["customer_id"], al["alert_type"], al.get("account_id"))
        if key not in deduped or al["risk_score"] > deduped[key]["risk_score"]:
            deduped[key] = al

    final_alerts = list(deduped.values())

    # Insert into DB
    conn.executemany("""
        INSERT OR IGNORE INTO aml_alerts
        (alert_id, transaction_id, customer_id, account_id,
         alert_type, alert_description, risk_score, priority, status)
        VALUES
        (:alert_id, :transaction_id, :customer_id, :account_id,
         :alert_type, :alert_description, :risk_score, :priority, 'open')
    """, final_alerts)
    conn.commit()

    # Summary stats
    total = conn.execute("SELECT COUNT(*) FROM aml_alerts").fetchone()[0]
    print(f"\n✅ {total} alerts written to aml_alerts table")
    print("\n   Priority breakdown:")
    for row in conn.execute("""
        SELECT priority, COUNT(*) as cnt
        FROM aml_alerts GROUP BY priority
        ORDER BY CASE priority
            WHEN 'critical' THEN 1 WHEN 'high' THEN 2
            WHEN 'medium'   THEN 3 ELSE 4 END
    """):
        bar = "█" * (row["cnt"] // 2)
        print(f"   {row['priority']:<10} {row['cnt']:>4}  {bar}")

    conn.close()


if __name__ == "__main__":
    main()
