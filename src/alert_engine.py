"""
AML Transaction Monitoring System
Module 3: Alert Engine

Runs all SQL rules, scores alerts, deduplicates,
assigns priorities, and writes to aml_alerts table.
"""

import sqlite3
import uuid
import json
import os
from datetime import datetime

DB_PATH     = os.path.join(os.path.dirname(__file__), '..', 'data', 'aml_system.db')
RULES_PATH  = os.path.join(os.path.dirname(__file__), '..', 'sql', 'rules_engine.sql')

ANALYSTS = ['sarah.chen', 'marcus.obi', 'priya.nair', 'james.ford', 'aisha.malik']

PRIORITY_MAP = {
    (85, 100): 'CRITICAL',
    (70,  84): 'HIGH',
    (50,  69): 'MEDIUM',
    ( 0,  49): 'LOW',
}

def get_priority(score):
    for (lo, hi), priority in PRIORITY_MAP.items():
        if lo <= score <= hi:
            return priority
    return 'LOW'


def parse_rules(sql_text):
    """Split the rules file into individual SELECT statements."""
    import re
    # Split on the rule header comments
    blocks = re.split(r'--\s*═+\s*\n--\s*RULE\s+(R\d+)', sql_text)
    rules = {}
    # blocks[0] is preamble, then alternating rule_id / sql
    for i in range(1, len(blocks), 2):
        rule_id = blocks[i].strip()
        sql_block = blocks[i+1]
        # Extract the SELECT ... ; portion
        match = re.search(r'((?:WITH|SELECT)[\s\S]+?);', sql_block, re.IGNORECASE)
        if match:
            rules[rule_id] = match.group(1).strip()
    return rules


def run_rules(conn):
    """Execute each rule and collect raw alert rows."""
    with open(RULES_PATH, 'r') as f:
        sql_text = f.read()

    rules = parse_rules(sql_text)
    print(f"  Loaded {len(rules)} rules: {', '.join(rules.keys())}")

    all_alerts = []
    for rule_id, sql in rules.items():
        try:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            for row in rows:
                rec = dict(zip(cols, row))
                rec['rule_id'] = rule_id
                all_alerts.append(rec)
            print(f"  {rule_id}: {len(rows)} hits")
        except Exception as e:
            print(f"  {rule_id}: ERROR — {e}")

    return all_alerts


def deduplicate(alerts):
    """
    Deduplicate: one alert per (customer_id, typology, evidence_date).
    When the same account triggers the same rule on the same day,
    keep only the highest-scoring instance.
    """
    seen = {}
    for a in alerts:
        ev = {}
        try:
            ev = json.loads(a.get('evidence_json') or '{}')
        except Exception:
            pass
        day_key = (ev.get('txn_day') or ev.get('txn_date','')[:10] or 'N/A')
        key = (a['customer_id'], a['typology'], day_key)
        if key not in seen or a['risk_score'] > seen[key]['risk_score']:
            seen[key] = a
    return list(seen.values())


def build_alert_records(alerts):
    """Convert raw rule hits into aml_alerts rows."""
    records = []
    for a in alerts:
        score    = int(a.get('risk_score', 50))
        priority = get_priority(score)
        records.append({
            'alert_id'    : f'ALT{uuid.uuid4().hex[:10].upper()}',
            'alert_date'  : datetime.utcnow().isoformat(),
            'customer_id' : a.get('customer_id'),
            'account_id'  : a.get('account_id'),
            'txn_id'      : a.get('txn_id'),
            'typology'    : a.get('typology'),
            'rule_id'     : a.get('rule_id'),
            'risk_score'  : score,
            'priority'    : priority,
            'status'      : 'OPEN',
            'analyst_notes': None,
            'assigned_to' : None,    # will assign below
        })

    # Auto-assign critical/high to analysts round-robin
    idx = 0
    for r in records:
        if r['priority'] in ('CRITICAL','HIGH'):
            r['assigned_to'] = ANALYSTS[idx % len(ANALYSTS)]
            idx += 1

    return records


def save_alerts(conn, records):
    """Truncate old alerts and insert fresh batch."""
    conn.execute("DELETE FROM aml_alerts")
    conn.execute("DELETE FROM alert_evidence")
    conn.executemany("""
        INSERT INTO aml_alerts
        (alert_id,alert_date,customer_id,account_id,txn_id,typology,
         rule_id,risk_score,priority,status,analyst_notes,assigned_to)
        VALUES
        (:alert_id,:alert_date,:customer_id,:account_id,:txn_id,:typology,
         :rule_id,:risk_score,:priority,:status,:analyst_notes,:assigned_to)
    """, records)
    conn.commit()


def print_summary(records):
    from collections import Counter
    print("\n  ── Alert Summary ───────────────────────────────")
    print(f"  Total alerts generated : {len(records)}")

    by_priority  = Counter(r['priority']  for r in records)
    by_typology  = Counter(r['typology']  for r in records)

    print("\n  By Priority:")
    for p in ['CRITICAL','HIGH','MEDIUM','LOW']:
        print(f"    {p:<12} : {by_priority.get(p,0)}")

    print("\n  By Typology:")
    for typ, cnt in by_typology.most_common():
        print(f"    {typ:<30} : {cnt}")
    print("  " + "─"*48)


def main():
    print("=" * 55)
    print("  AML System — Alert Engine")
    print("=" * 55)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    print("\n► Running detection rules...")
    raw_alerts = run_rules(conn)
    print(f"\n  Raw hits before dedup : {len(raw_alerts)}")

    deduped = deduplicate(raw_alerts)
    print(f"  After deduplication   : {len(deduped)}")

    records = build_alert_records(deduped)
    save_alerts(conn, records)
    print_summary(records)

    conn.close()
    print("\n✓ Alert engine complete.")
    print("=" * 55)


if __name__ == '__main__':
    main()
