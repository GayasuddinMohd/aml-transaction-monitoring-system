-- ============================================================
-- AML Transaction Monitoring System - Database Schema
-- ============================================================

-- CUSTOMERS
CREATE TABLE IF NOT EXISTS customers (
    customer_id         TEXT PRIMARY KEY,
    full_name           TEXT NOT NULL,
    date_of_birth       DATE,
    nationality         TEXT,
    country_of_residence TEXT,
    occupation          TEXT,
    customer_segment    TEXT CHECK(customer_segment IN ('retail', 'business', 'high_net_worth', 'shell_company')),
    risk_rating         TEXT CHECK(risk_rating IN ('low', 'medium', 'high', 'pep')),
    kyc_status          TEXT CHECK(kyc_status IN ('verified', 'pending', 'expired')),
    onboarded_date      DATE,
    is_pep              INTEGER DEFAULT 0,
    is_sanctioned       INTEGER DEFAULT 0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ACCOUNTS
CREATE TABLE IF NOT EXISTS accounts (
    account_id          TEXT PRIMARY KEY,
    customer_id         TEXT NOT NULL,
    account_type        TEXT CHECK(account_type IN ('checking', 'savings', 'business', 'offshore')),
    currency            TEXT DEFAULT 'USD',
    country             TEXT,
    opened_date         DATE,
    status              TEXT CHECK(status IN ('active', 'dormant', 'closed', 'frozen')),
    balance             REAL DEFAULT 0.0,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- TRANSACTIONS
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id      TEXT PRIMARY KEY,
    sender_account_id   TEXT NOT NULL,
    receiver_account_id TEXT,
    transaction_type    TEXT CHECK(transaction_type IN ('wire', 'cash_deposit', 'cash_withdrawal', 'ach', 'internal_transfer', 'crypto', 'check')),
    amount              REAL NOT NULL,
    currency            TEXT DEFAULT 'USD',
    usd_equivalent      REAL,
    transaction_date    DATE NOT NULL,
    transaction_time    TEXT,
    channel             TEXT CHECK(channel IN ('branch', 'online', 'mobile', 'atm', 'third_party')),
    description         TEXT,
    counterparty_name   TEXT,
    counterparty_country TEXT,
    is_cross_border     INTEGER DEFAULT 0,
    status              TEXT DEFAULT 'completed',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_account_id) REFERENCES accounts(account_id)
);

-- HIGH RISK COUNTRIES
CREATE TABLE IF NOT EXISTS high_risk_countries (
    country_code        TEXT PRIMARY KEY,
    country_name        TEXT,
    risk_level          TEXT CHECK(risk_level IN ('high', 'sanctioned', 'offshore')),
    fatf_listed         INTEGER DEFAULT 0
);

-- AML ALERTS
CREATE TABLE IF NOT EXISTS aml_alerts (
    alert_id            TEXT PRIMARY KEY,
    transaction_id      TEXT,
    customer_id         TEXT NOT NULL,
    account_id          TEXT,
    alert_type          TEXT NOT NULL,
    alert_description   TEXT,
    risk_score          INTEGER DEFAULT 0,
    priority            TEXT CHECK(priority IN ('low', 'medium', 'high', 'critical')),
    status              TEXT CHECK(status IN ('open', 'under_review', 'escalated', 'closed_sar', 'closed_no_action')) DEFAULT 'open',
    detected_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_by         TEXT,
    reviewed_at         TIMESTAMP,
    notes               TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- SAR CASES
CREATE TABLE IF NOT EXISTS sar_cases (
    case_id             TEXT PRIMARY KEY,
    alert_id            TEXT NOT NULL,
    customer_id         TEXT NOT NULL,
    analyst_name        TEXT,
    narrative           TEXT,
    total_suspicious_amount REAL,
    filing_status       TEXT CHECK(filing_status IN ('draft', 'pending_review', 'filed', 'withdrawn')) DEFAULT 'draft',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    filed_at            TIMESTAMP,
    FOREIGN KEY (alert_id) REFERENCES aml_alerts(alert_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE INDEX IF NOT EXISTS idx_txn_sender      ON transactions(sender_account_id);
CREATE INDEX IF NOT EXISTS idx_txn_date        ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_txn_amount      ON transactions(amount);
CREATE INDEX IF NOT EXISTS idx_alerts_customer ON aml_alerts(customer_id);
CREATE INDEX IF NOT EXISTS idx_alerts_status   ON aml_alerts(status);
CREATE INDEX IF NOT EXISTS idx_accounts_cust   ON accounts(customer_id);
