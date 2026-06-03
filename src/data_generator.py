"""
AML Transaction Monitoring System
Module 1: Synthetic Data Generator
====================================
Generates realistic customers, accounts, and transactions
including injected suspicious patterns for AML rule testing.
"""

import sqlite3
import random
import uuid
import json
from datetime import datetime, timedelta, date
from faker import Faker

fake = Faker()
random.seed(42)

DB_PATH = "data/aml_transactions.db"

# ── Country lists ──────────────────────────────────────────────────────────────
HIGH_RISK_COUNTRIES = {
    "IR": "Iran", "KP": "North Korea", "MM": "Myanmar",
    "SY": "Syria", "YE": "Yemen", "AF": "Afghanistan",
}
OFFSHORE_COUNTRIES = {
    "KY": "Cayman Islands", "VG": "British Virgin Islands",
    "PA": "Panama", "CH": "Switzerland", "LU": "Luxembourg",
}
NORMAL_COUNTRIES = {
    "US": "United States", "GB": "United Kingdom", "CA": "Canada",
    "AU": "Australia", "DE": "Germany", "FR": "France",
    "SG": "Singapore", "AE": "United Arab Emirates", "IN": "India",
}

OCCUPATIONS = [
    "Software Engineer", "Doctor", "Lawyer", "Accountant", "Business Owner",
    "Import/Export Trader", "Real Estate Agent", "Consultant", "Government Official",
    "Retired", "Student", "Casino Operator", "Money Services Business",
]

# ── Helpers ────────────────────────────────────────────────────────────────────
def new_id(prefix=""):
    return prefix + str(uuid.uuid4())[:8].upper()

def random_date(start_year=2020, end_year=2024):
    start = date(start_year, 1, 1)
    end   = date(end_year, 12, 31)
    return start + timedelta(days=random.randint(0, (end - start).days))

def random_time():
    h = random.randint(0, 23)
    m = random.randint(0, 59)
    return f"{h:02d}:{m:02d}:00"

# ── Generators ────────────────────────────────────────────────────────────────
def generate_customers(n=300):
    customers = []
    for _ in range(n):
        segment  = random.choices(
            ["retail", "business", "high_net_worth", "shell_company"],
            weights=[60, 25, 10, 5]
        )[0]
        risk     = random.choices(
            ["low", "medium", "high", "pep"],
            weights=[55, 30, 12, 3]
        )[0]
        is_pep   = 1 if risk == "pep" else 0
        is_sanc  = 1 if random.random() < 0.01 else 0

        customers.append({
            "customer_id":          new_id("C"),
            "full_name":            fake.name(),
            "date_of_birth":        str(fake.date_of_birth(minimum_age=18, maximum_age=80)),
            "nationality":          random.choice(list(NORMAL_COUNTRIES.keys())),
            "country_of_residence": random.choice(list(NORMAL_COUNTRIES.keys())),
            "occupation":           random.choice(OCCUPATIONS),
            "customer_segment":     segment,
            "risk_rating":          risk,
            "kyc_status":           random.choices(["verified", "pending", "expired"], weights=[75, 15, 10])[0],
            "onboarded_date":       str(random_date(2018, 2022)),
            "is_pep":               is_pep,
            "is_sanctioned":        is_sanc,
        })
    return customers


def generate_accounts(customers):
    accounts = []
    for cust in customers:
        n_accounts = random.choices([1, 2, 3], weights=[60, 30, 10])[0]
        for _ in range(n_accounts):
            acc_type = random.choices(
                ["checking", "savings", "business", "offshore"],
                weights=[45, 30, 20, 5]
            )[0]
            country = random.choice(list(NORMAL_COUNTRIES.keys()))
            if acc_type == "offshore":
                country = random.choice(list(OFFSHORE_COUNTRIES.keys()))

            accounts.append({
                "account_id":   new_id("A"),
                "customer_id":  cust["customer_id"],
                "account_type": acc_type,
                "currency":     "USD",
                "country":      country,
                "opened_date":  str(random_date(2018, 2023)),
                "status":       random.choices(["active", "dormant", "closed"], weights=[80, 15, 5])[0],
                "balance":      round(random.uniform(100, 500_000), 2),
            })
    return accounts


def generate_normal_transactions(accounts, n=4000):
    """Everyday legitimate transactions."""
    active = [a for a in accounts if a["status"] == "active"]
    txns   = []
    for _ in range(n):
        sender   = random.choice(active)
        receiver = random.choice(active)
        txn_type = random.choices(
            ["wire", "cash_deposit", "cash_withdrawal", "ach", "check"],
            weights=[20, 20, 20, 30, 10]
        )[0]
        amount   = round(random.lognormvariate(7, 1.5), 2)  # realistic dist
        cp_country = random.choice(list(NORMAL_COUNTRIES.keys()))

        txns.append({
            "transaction_id":      new_id("T"),
            "sender_account_id":   sender["account_id"],
            "receiver_account_id": receiver["account_id"],
            "transaction_type":    txn_type,
            "amount":              amount,
            "currency":            "USD",
            "usd_equivalent":      amount,
            "transaction_date":    str(random_date(2023, 2024)),
            "transaction_time":    random_time(),
            "channel":             random.choice(["branch", "online", "mobile", "atm"]),
            "description":         fake.bs(),
            "counterparty_name":   fake.company(),
            "counterparty_country": cp_country,
            "is_cross_border":     1 if cp_country != sender["country"] else 0,
            "status":              "completed",
            "_pattern":            "normal",
        })
    return txns


# ── Suspicious Pattern Injectors ──────────────────────────────────────────────

def inject_structuring(accounts, n_cases=15):
    """
    Structuring: Breaking up large cash deposits into amounts
    just below the $10,000 CTR reporting threshold.
    Classic typology: 3-9 deposits of $8,000-$9,900 within a few days.
    """
    active = [a for a in accounts if a["status"] == "active"]
    txns   = []
    for _ in range(n_cases):
        account    = random.choice(active)
        base_date  = random_date(2023, 2024)
        n_deposits = random.randint(3, 8)
        for i in range(n_deposits):
            amount = round(random.uniform(8_000, 9_900), 2)
            txn_date = base_date + timedelta(days=random.randint(0, 5))
            txns.append({
                "transaction_id":      new_id("T"),
                "sender_account_id":   account["account_id"],
                "receiver_account_id": None,
                "transaction_type":    "cash_deposit",
                "amount":              amount,
                "currency":            "USD",
                "usd_equivalent":      amount,
                "transaction_date":    str(txn_date),
                "transaction_time":    random_time(),
                "channel":             "branch",
                "description":         "Cash deposit",
                "counterparty_name":   None,
                "counterparty_country": "US",
                "is_cross_border":     0,
                "status":              "completed",
                "_pattern":            "structuring",
            })
    return txns


def inject_smurfing(accounts, customers, n_cases=10):
    """
    Smurfing: A source customer uses multiple accounts/people
    to deposit the same round amount simultaneously —
    then funds consolidate into one account.
    """
    active    = [a for a in accounts if a["status"] == "active"]
    txns      = []
    for _ in range(n_cases):
        target_account = random.choice(active)
        base_date      = random_date(2023, 2024)
        n_smurfs       = random.randint(4, 10)
        smurf_amount   = round(random.choice([5000, 7500, 9000, 4500, 6000]), 2)

        for i in range(n_smurfs):
            sender = random.choice(active)
            txns.append({
                "transaction_id":      new_id("T"),
                "sender_account_id":   sender["account_id"],
                "receiver_account_id": target_account["account_id"],
                "transaction_type":    "cash_deposit",
                "amount":              smurf_amount,
                "currency":            "USD",
                "usd_equivalent":      smurf_amount,
                "transaction_date":    str(base_date + timedelta(days=random.randint(0, 2))),
                "transaction_time":    random_time(),
                "channel":             random.choice(["branch", "atm"]),
                "description":         "Transfer",
                "counterparty_name":   fake.name(),
                "counterparty_country": "US",
                "is_cross_border":     0,
                "status":              "completed",
                "_pattern":            "smurfing",
            })
    return txns


def inject_layering(accounts, n_cases=8):
    """
    Layering: Rapid movement of funds through a chain of accounts
    to obscure the origin. Money hops 3-6 accounts within days.
    """
    active = [a for a in accounts if a["status"] == "active"]
    txns   = []
    for _ in range(n_cases):
        chain_length = random.randint(3, 6)
        chain        = random.sample(active, min(chain_length, len(active)))
        amount       = round(random.uniform(25_000, 200_000), 2)
        base_date    = random_date(2023, 2024)

        for i in range(len(chain) - 1):
            hop_date = base_date + timedelta(days=i)  # one hop per day
            fee_pct  = random.uniform(0.01, 0.03)
            amount   = round(amount * (1 - fee_pct), 2)  # small amount skimmed each hop
            txns.append({
                "transaction_id":      new_id("T"),
                "sender_account_id":   chain[i]["account_id"],
                "receiver_account_id": chain[i+1]["account_id"],
                "transaction_type":    "wire",
                "amount":              amount,
                "currency":            "USD",
                "usd_equivalent":      amount,
                "transaction_date":    str(hop_date),
                "transaction_time":    random_time(),
                "channel":             "online",
                "description":         random.choice(["Consulting fee", "Investment", "Loan repayment", "Service payment"]),
                "counterparty_name":   fake.company(),
                "counterparty_country": random.choice(list(NORMAL_COUNTRIES.keys()) + list(OFFSHORE_COUNTRIES.keys())),
                "is_cross_border":     random.randint(0, 1),
                "status":              "completed",
                "_pattern":            "layering",
            })
    return txns


def inject_round_tripping(accounts, n_cases=8):
    """
    Round-tripping: Funds sent overseas and returned to same
    entity disguised as foreign investment/loan — creating
    false impression of legitimate income.
    """
    active = [a for a in accounts if a["status"] == "active"]
    txns   = []
    for _ in range(n_cases):
        source   = random.choice(active)
        amount   = round(random.uniform(50_000, 300_000), 2)
        offshore = random.choice(list(OFFSHORE_COUNTRIES.keys()))
        out_date = random_date(2023, 2024)
        ret_date = out_date + timedelta(days=random.randint(10, 60))

        # Leg 1: out to offshore
        txns.append({
            "transaction_id":      new_id("T"),
            "sender_account_id":   source["account_id"],
            "receiver_account_id": None,
            "transaction_type":    "wire",
            "amount":              amount,
            "currency":            "USD",
            "usd_equivalent":      amount,
            "transaction_date":    str(out_date),
            "transaction_time":    random_time(),
            "channel":             "online",
            "description":         "Investment abroad",
            "counterparty_name":   fake.company(),
            "counterparty_country": offshore,
            "is_cross_border":     1,
            "status":              "completed",
            "_pattern":            "round_tripping",
        })
        # Leg 2: return from same offshore country
        txns.append({
            "transaction_id":      new_id("T"),
            "sender_account_id":   random.choice(active)["account_id"],
            "receiver_account_id": source["account_id"],
            "transaction_type":    "wire",
            "amount":              round(amount * random.uniform(0.95, 1.05), 2),
            "currency":            "USD",
            "usd_equivalent":      round(amount * random.uniform(0.95, 1.05), 2),
            "transaction_date":    str(ret_date),
            "transaction_time":    random_time(),
            "channel":             "online",
            "description":         random.choice(["Loan repayment", "Dividend income", "Return on investment"]),
            "counterparty_name":   fake.company(),
            "counterparty_country": offshore,
            "is_cross_border":     1,
            "status":              "completed",
            "_pattern":            "round_tripping",
        })
    return txns


def inject_high_risk_geography(accounts, n=50):
    """Transactions to/from high-risk / sanctioned countries."""
    active = [a for a in accounts if a["status"] == "active"]
    txns   = []
    for _ in range(n):
        sender   = random.choice(active)
        country  = random.choice(list(HIGH_RISK_COUNTRIES.keys()))
        amount   = round(random.uniform(1_000, 80_000), 2)
        txns.append({
            "transaction_id":      new_id("T"),
            "sender_account_id":   sender["account_id"],
            "receiver_account_id": None,
            "transaction_type":    "wire",
            "amount":              amount,
            "currency":            "USD",
            "usd_equivalent":      amount,
            "transaction_date":    str(random_date(2023, 2024)),
            "transaction_time":    random_time(),
            "channel":             "online",
            "description":         "International wire",
            "counterparty_name":   fake.company(),
            "counterparty_country": country,
            "is_cross_border":     1,
            "status":              "completed",
            "_pattern":            "high_risk_geography",
        })
    return txns


def inject_velocity_spike(accounts, n_cases=10):
    """
    Unusual velocity: account with normally quiet history
    suddenly fires 20-40 transactions in 24 hours.
    """
    active = [a for a in accounts if a["status"] == "active"]
    txns   = []
    for _ in range(n_cases):
        account   = random.choice(active)
        spike_day = random_date(2023, 2024)
        n_txns    = random.randint(20, 40)
        for _ in range(n_txns):
            amount = round(random.uniform(500, 5_000), 2)
            txns.append({
                "transaction_id":      new_id("T"),
                "sender_account_id":   account["account_id"],
                "receiver_account_id": random.choice(active)["account_id"],
                "transaction_type":    random.choice(["ach", "wire", "internal_transfer"]),
                "amount":              amount,
                "currency":            "USD",
                "usd_equivalent":      amount,
                "transaction_date":    str(spike_day),
                "transaction_time":    random_time(),
                "channel":             "online",
                "description":         "Transfer",
                "counterparty_name":   fake.name(),
                "counterparty_country": "US",
                "is_cross_border":     0,
                "status":              "completed",
                "_pattern":            "velocity_spike",
            })
    return txns


# ── DB loader ─────────────────────────────────────────────────────────────────
def load_high_risk_countries(conn):
    rows = []
    for code, name in HIGH_RISK_COUNTRIES.items():
        rows.append((code, name, "high", 1))
    for code, name in OFFSHORE_COUNTRIES.items():
        rows.append((code, name, "offshore", 0))
    conn.executemany(
        "INSERT OR IGNORE INTO high_risk_countries VALUES (?,?,?,?)", rows
    )


def insert_all(conn, customers, accounts, transactions):
    conn.executemany("""
        INSERT OR IGNORE INTO customers
        (customer_id,full_name,date_of_birth,nationality,country_of_residence,
         occupation,customer_segment,risk_rating,kyc_status,onboarded_date,is_pep,is_sanctioned)
        VALUES (:customer_id,:full_name,:date_of_birth,:nationality,:country_of_residence,
                :occupation,:customer_segment,:risk_rating,:kyc_status,:onboarded_date,:is_pep,:is_sanctioned)
    """, customers)

    conn.executemany("""
        INSERT OR IGNORE INTO accounts
        (account_id,customer_id,account_type,currency,country,opened_date,status,balance)
        VALUES (:account_id,:customer_id,:account_type,:currency,:country,:opened_date,:status,:balance)
    """, accounts)

    conn.executemany("""
        INSERT OR IGNORE INTO transactions
        (transaction_id,sender_account_id,receiver_account_id,transaction_type,
         amount,currency,usd_equivalent,transaction_date,transaction_time,
         channel,description,counterparty_name,counterparty_country,is_cross_border,status)
        VALUES (:transaction_id,:sender_account_id,:receiver_account_id,:transaction_type,
                :amount,:currency,:usd_equivalent,:transaction_date,:transaction_time,
                :channel,:description,:counterparty_name,:counterparty_country,:is_cross_border,:status)
    """, transactions)

    conn.commit()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    import os
    os.makedirs("data", exist_ok=True)

    print("📦 Connecting to database...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    with open("sql/schema.sql") as f:
        conn.executescript(f.read())

    print("👤 Generating customers...")
    customers = generate_customers(300)

    print("🏦 Generating accounts...")
    accounts  = generate_accounts(customers)

    print("💸 Generating normal transactions...")
    txns = generate_normal_transactions(accounts, n=4000)

    print("🚨 Injecting suspicious patterns...")
    txns += inject_structuring(accounts,              n_cases=15)
    txns += inject_smurfing(accounts, customers,      n_cases=10)
    txns += inject_layering(accounts,                 n_cases=8)
    txns += inject_round_tripping(accounts,           n_cases=8)
    txns += inject_high_risk_geography(accounts,      n=50)
    txns += inject_velocity_spike(accounts,           n_cases=10)

    random.shuffle(txns)

    # Save pattern labels separately for validation (not in DB — simulates real world)
    pattern_map = {t["transaction_id"]: t.pop("_pattern") for t in txns}
    with open("data/ground_truth_patterns.json", "w") as f:
        json.dump(pattern_map, f, indent=2)

    print(f"💾 Loading {len(customers)} customers, {len(accounts)} accounts, {len(txns)} transactions...")
    load_high_risk_countries(conn)
    insert_all(conn, customers, accounts, txns)

    # Summary
    c = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    a = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    t = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    print(f"\n✅ Database ready at {DB_PATH}")
    print(f"   Customers : {c}")
    print(f"   Accounts  : {a}")
    print(f"   Transactions: {t}")
    pattern_counts = {}
    for p in pattern_map.values():
        pattern_counts[p] = pattern_counts.get(p, 0) + 1
    print("\n   Injected patterns:")
    for k, v in sorted(pattern_counts.items()):
        print(f"   {'  '+k:<30} {v:>5} txns")

    conn.close()


if __name__ == "__main__":
    main()
