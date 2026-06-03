-- ============================================================
-- AML Rules Engine — Typology Detection Queries
-- ============================================================
-- Each rule generates alert candidates.
-- Run via rules_engine.py which wraps these in Python logic.
-- ============================================================


-- ─────────────────────────────────────────────────────────────
-- RULE 1: STRUCTURING (CTR Avoidance)
-- Multiple cash deposits below $10,000 by same account
-- within a 7-day window, totaling > $10,000
-- Regulatory basis: 31 U.S.C. § 5324 (Bank Secrecy Act)
-- ─────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_structuring_alerts AS
SELECT
    t.sender_account_id                         AS account_id,
    a.customer_id,
    COUNT(*)                                    AS txn_count,
    ROUND(SUM(t.amount), 2)                     AS total_amount,
    MIN(t.transaction_date)                     AS window_start,
    MAX(t.transaction_date)                     AS window_end,
    MIN(t.amount)                               AS min_txn,
    MAX(t.amount)                               AS max_txn,
    'structuring'                               AS alert_type,
    'Multiple cash deposits below $10K CTR threshold within 7 days' AS description
FROM transactions t
JOIN accounts a ON t.sender_account_id = a.account_id
WHERE t.transaction_type IN ('cash_deposit')
  AND t.amount BETWEEN 7000 AND 9999.99
  AND t.status = 'completed'
GROUP BY
    t.sender_account_id,
    (CAST(julianday(t.transaction_date) / 7 AS INTEGER))  -- 7-day buckets
HAVING
    COUNT(*) >= 3
    AND SUM(t.amount) > 10000;


-- ─────────────────────────────────────────────────────────────
-- RULE 2: SMURFING (Aggregation to single account)
-- Multiple DIFFERENT senders sending the same amount
-- to ONE receiver within 48 hours
-- ─────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_smurfing_alerts AS
SELECT
    t.receiver_account_id                       AS account_id,
    a.customer_id,
    COUNT(DISTINCT t.sender_account_id)         AS unique_senders,
    COUNT(*)                                    AS txn_count,
    ROUND(SUM(t.amount), 2)                     AS total_amount,
    ROUND(AVG(t.amount), 2)                     AS avg_amount,
    MIN(t.transaction_date)                     AS window_start,
    MAX(t.transaction_date)                     AS window_end,
    'smurfing'                                  AS alert_type,
    'Multiple senders depositing similar amounts to single account within 48h' AS description
FROM transactions t
JOIN accounts a ON t.receiver_account_id = a.account_id
WHERE t.transaction_type IN ('cash_deposit', 'ach', 'wire')
  AND t.amount BETWEEN 3000 AND 9999.99
  AND t.status = 'completed'
  AND t.receiver_account_id IS NOT NULL
GROUP BY
    t.receiver_account_id,
    t.transaction_date
HAVING
    COUNT(DISTINCT t.sender_account_id) >= 3
    AND COUNT(*) >= 3;


-- ─────────────────────────────────────────────────────────────
-- RULE 3: LAYERING — Rapid Pass-Through
-- Account receives large wire and forwards it out
-- within 72 hours (pass-through / funnel account)
-- ─────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_layering_alerts AS
SELECT
    t_in.receiver_account_id                    AS account_id,
    a.customer_id,
    ROUND(SUM(t_in.amount), 2)                  AS total_received,
    ROUND(SUM(t_out.amount), 2)                 AS total_sent,
    ROUND(
        100.0 * SUM(t_out.amount) / NULLIF(SUM(t_in.amount), 0)
    , 1)                                        AS pass_through_pct,
    COUNT(DISTINCT t_in.transaction_id)         AS in_txn_count,
    COUNT(DISTINCT t_out.transaction_id)        AS out_txn_count,
    MIN(t_in.transaction_date)                  AS first_in,
    MAX(t_out.transaction_date)                 AS last_out,
    'layering'                                  AS alert_type,
    'Account receives and rapidly re-transmits funds within 72 hours (pass-through pattern)' AS description
FROM transactions t_in
JOIN transactions t_out
    ON  t_in.receiver_account_id = t_out.sender_account_id
    AND julianday(t_out.transaction_date) - julianday(t_in.transaction_date) BETWEEN 0 AND 3
JOIN accounts a ON t_in.receiver_account_id = a.account_id
WHERE t_in.transaction_type IN ('wire', 'ach')
  AND t_out.transaction_type IN ('wire', 'ach')
  AND t_in.amount > 10000
  AND t_out.amount > 5000
  AND t_in.status = 'completed'
  AND t_out.status = 'completed'
GROUP BY t_in.receiver_account_id
HAVING
    pass_through_pct >= 70
    AND in_txn_count >= 2;


-- ─────────────────────────────────────────────────────────────
-- RULE 4: ROUND-TRIPPING
-- Account sends large wire to high-risk / offshore country
-- AND receives a similar amount from same country within 90 days
-- ─────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_round_tripping_alerts AS
SELECT
    t_out.sender_account_id                     AS account_id,
    a.customer_id,
    t_out.counterparty_country                  AS offshore_country,
    ROUND(t_out.amount, 2)                      AS amount_sent,
    ROUND(t_in.amount, 2)                       AS amount_returned,
    t_out.transaction_date                      AS sent_date,
    t_in.transaction_date                       AS returned_date,
    julianday(t_in.transaction_date) - julianday(t_out.transaction_date) AS days_gap,
    'round_tripping'                            AS alert_type,
    'Funds sent to offshore/high-risk jurisdiction and returned within 90 days' AS description
FROM transactions t_out
JOIN transactions t_in
    ON  t_out.sender_account_id = t_in.receiver_account_id
    AND t_out.counterparty_country = t_in.counterparty_country
    AND julianday(t_in.transaction_date) > julianday(t_out.transaction_date)
    AND julianday(t_in.transaction_date) - julianday(t_out.transaction_date) <= 90
JOIN accounts a ON t_out.sender_account_id = a.account_id
JOIN high_risk_countries hrc ON t_out.counterparty_country = hrc.country_code
WHERE t_out.transaction_type = 'wire'
  AND t_in.transaction_type  = 'wire'
  AND t_out.amount > 20000
  AND t_in.amount  > 10000
  AND t_out.status = 'completed'
  AND t_in.status  = 'completed';


-- ─────────────────────────────────────────────────────────────
-- RULE 5: HIGH-RISK GEOGRAPHY
-- Any wire transfer to/from FATF-listed or sanctioned country
-- above $5,000
-- ─────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_high_risk_geo_alerts AS
SELECT
    t.transaction_id,
    t.sender_account_id                         AS account_id,
    a.customer_id,
    t.amount,
    t.transaction_date,
    t.counterparty_country,
    hrc.country_name                            AS risk_country_name,
    hrc.risk_level,
    hrc.fatf_listed,
    'high_risk_geography'                       AS alert_type,
    'Wire transfer to/from high-risk or sanctioned jurisdiction' AS description
FROM transactions t
JOIN accounts a ON t.sender_account_id = a.account_id
JOIN high_risk_countries hrc ON t.counterparty_country = hrc.country_code
WHERE t.transaction_type = 'wire'
  AND t.amount > 5000
  AND t.status = 'completed';


-- ─────────────────────────────────────────────────────────────
-- RULE 6: VELOCITY SPIKE
-- Account with > 15 transactions in a single day,
-- where that day's volume exceeds 3× their 30-day daily average
-- ─────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_velocity_alerts AS
WITH daily_totals AS (
    SELECT
        sender_account_id,
        transaction_date,
        COUNT(*)            AS daily_count,
        SUM(amount)         AS daily_amount
    FROM transactions
    WHERE status = 'completed'
    GROUP BY sender_account_id, transaction_date
),
account_avg AS (
    SELECT
        sender_account_id,
        AVG(daily_count)    AS avg_daily_count,
        AVG(daily_amount)   AS avg_daily_amount
    FROM daily_totals
    GROUP BY sender_account_id
)
SELECT
    dt.sender_account_id                        AS account_id,
    a.customer_id,
    dt.transaction_date,
    dt.daily_count,
    ROUND(dt.daily_amount, 2)                   AS daily_amount,
    ROUND(aa.avg_daily_count, 1)                AS avg_daily_count,
    ROUND(aa.avg_daily_amount, 2)               AS avg_daily_amount,
    ROUND(dt.daily_count / NULLIF(aa.avg_daily_count, 0), 1) AS count_multiplier,
    'velocity_spike'                            AS alert_type,
    'Unusual transaction velocity: single-day count exceeds 3x account average' AS description
FROM daily_totals dt
JOIN account_avg aa   ON dt.sender_account_id = aa.sender_account_id
JOIN accounts a       ON dt.sender_account_id = a.account_id
WHERE dt.daily_count >= 15
  AND dt.daily_count > (3 * aa.avg_daily_count);


-- ─────────────────────────────────────────────────────────────
-- RULE 7: PEP / SANCTIONED CUSTOMER TRANSACTION
-- Any transaction above $1,000 from a PEP or sanctioned customer
-- ─────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_pep_sanctions_alerts AS
SELECT
    t.transaction_id,
    t.sender_account_id                         AS account_id,
    c.customer_id,
    c.full_name,
    c.is_pep,
    c.is_sanctioned,
    c.risk_rating,
    t.amount,
    t.transaction_date,
    t.transaction_type,
    CASE
        WHEN c.is_sanctioned = 1 THEN 'sanctioned_customer_transaction'
        ELSE 'pep_transaction'
    END                                         AS alert_type,
    CASE
        WHEN c.is_sanctioned = 1 THEN 'Transaction by sanctioned customer — immediate review required'
        ELSE 'Transaction by Politically Exposed Person above threshold'
    END                                         AS description
FROM transactions t
JOIN accounts a  ON t.sender_account_id = a.account_id
JOIN customers c ON a.customer_id = c.customer_id
WHERE (c.is_pep = 1 OR c.is_sanctioned = 1)
  AND t.amount > 1000
  AND t.status = 'completed';


-- ─────────────────────────────────────────────────────────────
-- RULE 8: DORMANT ACCOUNT REACTIVATION
-- Account inactive for 180+ days suddenly processes
-- a transaction above $10,000
-- ─────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_dormant_reactivation_alerts AS
WITH last_activity AS (
    SELECT
        sender_account_id,
        MAX(transaction_date) AS last_txn_date
    FROM transactions
    GROUP BY sender_account_id
),
account_history AS (
    SELECT
        t.transaction_id,
        t.sender_account_id,
        t.amount,
        t.transaction_date,
        t.transaction_type,
        la.last_txn_date,
        LAG(t.transaction_date) OVER (
            PARTITION BY t.sender_account_id
            ORDER BY t.transaction_date
        ) AS prev_txn_date
    FROM transactions t
    JOIN last_activity la ON t.sender_account_id = la.sender_account_id
)
SELECT
    ah.transaction_id,
    ah.sender_account_id                        AS account_id,
    a.customer_id,
    ah.prev_txn_date,
    ah.transaction_date                         AS reactivation_date,
    julianday(ah.transaction_date) - julianday(ah.prev_txn_date) AS days_dormant,
    ROUND(ah.amount, 2)                         AS amount,
    'dormant_reactivation'                      AS alert_type,
    'Dormant account reactivated with high-value transaction after 180+ days of inactivity' AS description
FROM account_history ah
JOIN accounts a ON ah.sender_account_id = a.account_id
WHERE julianday(ah.transaction_date) - julianday(ah.prev_txn_date) >= 180
  AND ah.amount > 10000;


-- ─────────────────────────────────────────────────────────────
-- SUMMARY VIEW: Customer-level risk aggregation
-- ─────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_customer_risk_summary AS
SELECT
    c.customer_id,
    c.full_name,
    c.risk_rating,
    c.customer_segment,
    c.is_pep,
    c.is_sanctioned,
    c.kyc_status,
    COUNT(DISTINCT a.account_id)                AS total_accounts,
    COUNT(DISTINCT t.transaction_id)            AS total_transactions,
    ROUND(SUM(t.amount), 2)                     AS total_volume_usd,
    ROUND(AVG(t.amount), 2)                     AS avg_txn_amount,
    MAX(t.transaction_date)                     AS last_transaction_date,
    SUM(t.is_cross_border)                      AS cross_border_count,
    COUNT(DISTINCT al.alert_id)                 AS total_alerts,
    SUM(CASE WHEN al.status = 'open' THEN 1 ELSE 0 END) AS open_alerts,
    MAX(al.risk_score)                          AS max_risk_score
FROM customers c
LEFT JOIN accounts a    ON c.customer_id = a.customer_id
LEFT JOIN transactions t ON a.account_id = t.sender_account_id
LEFT JOIN aml_alerts al  ON c.customer_id = al.customer_id
GROUP BY c.customer_id;
