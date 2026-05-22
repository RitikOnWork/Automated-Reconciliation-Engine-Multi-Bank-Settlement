-- ==============================================================================
-- Automated Reconciliation Engine - PostgreSQL Schema Blueprint DDL
-- Highly optimized for indexing, scalability, partitioning, and audit compliance.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Table Definitions
-- ------------------------------------------------------------------------------

-- Users Table (Security & Authentication)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'analyst' CHECK (role IN ('analyst', 'admin')),
    is_active BOOLEAN DEFAULT TRUE NOT NULL
);

-- Bank Configurations Table (Multi-bank details)
CREATE TABLE IF NOT EXISTS bank_configurations (
    id SERIAL PRIMARY KEY,
    bank_name VARCHAR(100) NOT NULL,
    account_number VARCHAR(50) UNIQUE NOT NULL,
    statement_format VARCHAR(10) NOT NULL CHECK (statement_format IN ('mt940', 'camt053', 'csv')),
    parser_rules JSONB, -- Nested JSON configurations mapping CSV columns/aliases
    is_active BOOLEAN DEFAULT TRUE NOT NULL
);

-- Raw Transactions Staging Table
CREATE TABLE IF NOT EXISTS raw_transactions (
    id SERIAL PRIMARY KEY,
    bank_config_id INTEGER REFERENCES bank_configurations(id) ON DELETE RESTRICT,
    filename VARCHAR(255) NOT NULL,
    raw_payload JSONB NOT NULL, -- Full row or line parsing snapshot
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'STAGED' CHECK (status IN ('STAGED', 'NORMALIZED', 'ERROR'))
);

-- Match Results Table (Tracks pairs created)
CREATE TABLE IF NOT EXISTS match_results (
    id SERIAL PRIMARY KEY,
    match_type VARCHAR(20) NOT NULL CHECK (match_type IN ('exact', 'fuzzy', 'rule_based', 'manual')),
    matched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    matching_rules_applied TEXT,
    similarity_score DOUBLE PRECISION DEFAULT 100.0,
    resolved_by VARCHAR(50) -- Username of analyst if manual, or 'system'
);

-- Normalized Transactions Table (Core Ledger/Statements entries)
-- Designed with optional partitioning below.
CREATE TABLE IF NOT EXISTS normalized_transactions (
    id SERIAL PRIMARY KEY,
    raw_tx_id INTEGER REFERENCES raw_transactions(id) ON DELETE SET NULL,
    bank_config_id INTEGER REFERENCES bank_configurations(id) ON DELETE RESTRICT,
    source_system VARCHAR(20) NOT NULL CHECK (source_system IN ('bank_statement', 'internal_ledger')),
    transaction_date DATE NOT NULL,
    value_date DATE,
    amount NUMERIC(15, 2) NOT NULL, -- NUMERIC prevents floating point rounding errors
    currency VARCHAR(3) DEFAULT 'USD' NOT NULL,
    reference VARCHAR(255),
    description TEXT,
    bank_account VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'UNMATCHED' CHECK (status IN ('UNMATCHED', 'MATCHED', 'EXCEPTION')),
    match_id INTEGER REFERENCES match_results(id) ON DELETE SET NULL
);

-- Exceptions Table (Varances tracking queue)
CREATE TABLE IF NOT EXISTS exceptions (
    id SERIAL PRIMARY KEY,
    transaction_id INTEGER REFERENCES normalized_transactions(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED', 'WAIVED')),
    error_type VARCHAR(50) NOT NULL CHECK (error_type IN ('unmatched_bank_entry', 'unmatched_ledger_entry', 'amount_mismatch', 'date_out_of_bounds')),
    resolution_action VARCHAR(20) CHECK (resolution_action IN ('force_matched', 'written_off', 'adjusted')),
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(50),
    comments TEXT
);

-- Audit Logs Table (Compliance Trails)
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    action VARCHAR(50) NOT NULL,
    table_name VARCHAR(50),
    record_id INTEGER,
    old_value TEXT, -- JSON snapshots
    new_value TEXT, -- JSON snapshots
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    performed_by VARCHAR(50) NOT NULL,
    ip_address VARCHAR(45),
    comments TEXT
);

-- ------------------------------------------------------------------------------
-- 2. Performance Indexing Strategies
-- ------------------------------------------------------------------------------

-- Index for authentication logins lookup
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Index foreign keys to avoid lock contention on cascading deletes
CREATE INDEX IF NOT EXISTS idx_raw_tx_config ON raw_transactions(bank_config_id);
CREATE INDEX IF NOT EXISTS idx_norm_tx_raw ON normalized_transactions(raw_tx_id);
CREATE INDEX IF NOT EXISTS idx_norm_tx_config ON normalized_transactions(bank_config_id);
CREATE INDEX IF NOT EXISTS idx_norm_tx_match ON normalized_transactions(match_id);
CREATE INDEX IF NOT EXISTS idx_exceptions_tx ON exceptions(transaction_id);

-- Composite Index optimized for reconciliation execution scans
-- Pairs on Account, Currency, Amount, and status checks
CREATE INDEX IF NOT EXISTS idx_norm_tx_recon_matching
ON normalized_transactions(bank_account, currency, ABS(amount), status, transaction_date);

-- Case-insensitive index on reference code to speed up alphanumeric string Joins
CREATE INDEX IF NOT EXISTS idx_norm_tx_upper_reference
ON normalized_transactions (UPPER(reference))
WHERE reference IS NOT NULL;

-- GIN Index on raw transactions JSONB payload to query custom statement tags instantly
CREATE INDEX IF NOT EXISTS idx_raw_tx_payload_gin
ON raw_transactions USING GIN(raw_payload);

-- Index status on exception queues for dashboard listing speed
CREATE INDEX IF NOT EXISTS idx_exceptions_status_open
ON exceptions(status)
WHERE status = 'OPEN';

-- Compliance index on audit log timestamps
CREATE INDEX IF NOT EXISTS idx_audit_logs_time ON audit_logs(timestamp DESC);


-- ------------------------------------------------------------------------------
-- 3. PostgreSQL Table Partitioning Recommendations
-- ------------------------------------------------------------------------------
/*
For high-volume transaction ledger engines, the 'normalized_transactions' table 
should be range-partitioned on 'transaction_date'. This keeps indexes fitting in RAM 
and allows dropping entire month blocks for historical data pruning.

Partition Blueprint DDL Syntax:

CREATE TABLE normalized_transactions_partitioned (
    id SERIAL,
    raw_tx_id INTEGER,
    bank_config_id INTEGER,
    source_system VARCHAR(20) NOT NULL,
    transaction_date DATE NOT NULL,
    amount NUMERIC(15, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    reference VARCHAR(255),
    description TEXT,
    bank_account VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'UNMATCHED',
    match_id INTEGER,
    PRIMARY KEY (id, transaction_date) -- Date must be part of primary key for partitioning
) PARTITION BY RANGE (transaction_date);

-- Create concrete monthly partitions
CREATE TABLE normalized_tx_2026_m05 PARTITION OF normalized_transactions_partitioned
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE normalized_tx_2026_m06 PARTITION OF normalized_transactions_partitioned
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
*/


-- ------------------------------------------------------------------------------
-- 4. Highly Optimized Reconciliation CTE Match Query
-- ------------------------------------------------------------------------------
/*
This query performs an exact matching sweep across active unmatched bank statement entries 
and ledger entries.
It uses dynamic row-number sorting to guarantee that:
- It does NOT double-match (1:N or N:1) entries when multiple rows share duplicate amounts & references.
- Selects matching records precisely with O(N log N) database-level index joins.
*/
-- EXPLAIN ANALYZE -- Prefix to run audit analysis on PostgreSQL
WITH bank_unmatched AS (
    SELECT 
        id, 
        bank_account, 
        currency, 
        amount, 
        UPPER(TRIM(reference)) as clean_ref, 
        transaction_date,
        ROW_NUMBER() OVER(PARTITION BY bank_account, currency, amount, UPPER(TRIM(reference)) ORDER BY transaction_date, id) as row_seq
    FROM normalized_transactions
    WHERE source_system = 'bank_statement' 
      AND status = 'UNMATCHED'
      AND reference IS NOT NULL
),
ledger_unmatched AS (
    SELECT 
        id, 
        bank_account, 
        currency, 
        amount, 
        UPPER(TRIM(reference)) as clean_ref, 
        transaction_date,
        -- Flip sign for direct debit/credit pairing comparison if ledger matches abs value
        ROW_NUMBER() OVER(PARTITION BY bank_account, currency, ABS(amount), UPPER(TRIM(reference)) ORDER BY transaction_date, id) as row_seq
    FROM normalized_transactions
    WHERE source_system = 'internal_ledger' 
      AND status = 'UNMATCHED'
      AND reference IS NOT NULL
)
SELECT 
    b.id AS bank_transaction_id,
    l.id AS ledger_transaction_id,
    b.bank_account,
    b.amount AS bank_amount,
    l.amount AS ledger_amount,
    b.clean_ref AS reference,
    'EXACT_REFERENCE_AND_AMOUNT_CTE_SQL' AS rule_applied
FROM bank_unmatched b
INNER JOIN ledger_unmatched l 
    ON b.bank_account = l.bank_account
   AND b.currency = l.currency
   -- Matches equal absolute values (bank credit vs ledger debit)
   AND ABS(b.amount) = ABS(l.amount)
   AND b.clean_ref = l.clean_ref
   -- Row sequence matches prevents duplicate N:1 overmatching
   AND b.row_seq = l.row_seq;
