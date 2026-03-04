-- ============================================
-- init_db.sql - Demo Healthcare Database Schema & Seed Data
-- ============================================
-- WHY: This creates a realistic mock database that mirrors real healthcare
-- ops data. The agent's query_database tool runs SQL against this DB.
-- Seeded with ~1000 rows so queries return meaningful results.

-- Claims table: Core healthcare claims data
CREATE TABLE IF NOT EXISTS claims (
    claim_id SERIAL PRIMARY KEY,
    member_id VARCHAR(20) NOT NULL,
    provider_id VARCHAR(20) NOT NULL,
    claim_status VARCHAR(30) NOT NULL, -- 'pending', 'approved', 'denied', 'recycled', 'in_review'
    claim_type VARCHAR(20) NOT NULL,   -- 'professional', 'institutional', 'dental', 'pharmacy'
    amount DECIMAL(10, 2) NOT NULL,
    date_of_service DATE NOT NULL,
    date_received DATE NOT NULL,
    diagnosis_code VARCHAR(10),
    procedure_code VARCHAR(10),
    state_code VARCHAR(2),
    market VARCHAR(30),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Members table: Plan members
CREATE TABLE IF NOT EXISTS members (
    member_id VARCHAR(20) PRIMARY KEY,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    plan_type VARCHAR(30),       -- 'medicaid', 'medicare', 'commercial'
    state VARCHAR(2),
    enrollment_date DATE,
    status VARCHAR(20) DEFAULT 'active'
);

-- Providers table: Healthcare providers
CREATE TABLE IF NOT EXISTS providers (
    provider_id VARCHAR(20) PRIMARY KEY,
    provider_name VARCHAR(100),
    npi VARCHAR(10),
    specialty VARCHAR(50),
    network_status VARCHAR(20),   -- 'in_network', 'out_of_network'
    state VARCHAR(2)
);

-- Job runs table: Mirrors Tidal job execution history
CREATE TABLE IF NOT EXISTS job_runs (
    run_id SERIAL PRIMARY KEY,
    job_id VARCHAR(50) NOT NULL,       -- e.g., 'CFT303A', 'ATL101Y'
    job_name VARCHAR(200),
    run_date TIMESTAMP NOT NULL,
    status VARCHAR(30) NOT NULL,        -- 'completed', 'failed', 'running', 'timed_out'
    duration_seconds INTEGER,
    error_message TEXT,
    agent_name VARCHAR(100),
    server VARCHAR(50)
);

-- ============================================
-- Seed Data
-- ============================================

-- Seed members (100 records)
INSERT INTO members (member_id, first_name, last_name, plan_type, state, enrollment_date, status)
SELECT
    'MBR' || LPAD(i::TEXT, 6, '0'),
    (ARRAY['John','Jane','Michael','Sarah','David','Emily','Robert','Lisa','James','Maria'])[1 + (i % 10)],
    (ARRAY['Smith','Johnson','Williams','Brown','Jones','Garcia','Miller','Davis','Rodriguez','Martinez'])[1 + (i % 10)],
    (ARRAY['medicaid','medicare','commercial'])[1 + (i % 3)],
    (ARRAY['TX','CA','FL','NY','OH','IN','WI','NJ','GA','LA'])[1 + (i % 10)],
    DATE '2020-01-01' + (i * 3),
    CASE WHEN i % 20 = 0 THEN 'inactive' ELSE 'active' END
FROM generate_series(1, 100) AS i;

-- Seed providers (50 records)
INSERT INTO providers (provider_id, provider_name, npi, specialty, network_status, state)
SELECT
    'PRV' || LPAD(i::TEXT, 5, '0'),
    'Provider ' || i || ' Medical Group',
    LPAD((1000000000 + i)::TEXT, 10, '0'),
    (ARRAY['Family Medicine','Cardiology','Orthopedics','Pediatrics','Internal Medicine','Radiology','Emergency Medicine','Psychiatry','Dermatology','Oncology'])[1 + (i % 10)],
    CASE WHEN i % 5 = 0 THEN 'out_of_network' ELSE 'in_network' END,
    (ARRAY['TX','CA','FL','NY','OH','IN','WI','NJ','GA','LA'])[1 + (i % 10)]
FROM generate_series(1, 50) AS i;

-- Seed claims (500 records)
INSERT INTO claims (member_id, provider_id, claim_status, claim_type, amount, date_of_service, date_received, diagnosis_code, procedure_code, state_code, market)
SELECT
    'MBR' || LPAD((1 + (i % 100))::TEXT, 6, '0'),
    'PRV' || LPAD((1 + (i % 50))::TEXT, 5, '0'),
    (ARRAY['pending','approved','denied','recycled','in_review'])[1 + (i % 5)],
    (ARRAY['professional','institutional','dental','pharmacy'])[1 + (i % 4)],
    ROUND((RANDOM() * 5000 + 50)::NUMERIC, 2),
    DATE '2024-01-01' + (i % 365),
    DATE '2024-01-01' + (i % 365) + INTERVAL '2 days',
    'Z' || LPAD((i % 99)::TEXT, 2, '0') || '.' || (i % 9),
    LPAD((10000 + i % 9999)::TEXT, 5, '0'),
    (ARRAY['TX','CA','FL','NY','OH','IN','WI','NJ','GA','LA'])[1 + (i % 10)],
    (ARRAY['Texas','California','Florida','New York','Ohio','Indiana','Wisconsin','New Jersey','Georgia','Louisiana'])[1 + (i % 10)]
FROM generate_series(1, 500) AS i;

-- Seed job runs (300 records) - realistic Tidal job execution data
INSERT INTO job_runs (job_id, job_name, run_date, status, duration_seconds, error_message, agent_name, server)
SELECT
    (ARRAY['CFT303A','CFT303B','CFT303D','CFT303E','CFT301B','CFT302B','ATL101Y','ATL101A','ATL303Z','CFT005','CFT008','CFT029','CFT201','CFT456','CFT460'])[1 + (i % 15)],
    (ARRAY[
        'START_INBOUND_FILE_PROCESS','INBOUND_FILE_PROCESSING','PEGA_LOAD_EDI','PEGA_LOAD_GENERIC',
        'CLAIMS_RECYCLE_CONTROLLER','EDINETCLAIM_PROCESS_DATA_MOVE','CLAIMS_LOAD_NOT_STARTED_ALERT',
        'COPS_KPI_SANITY_CHECKS','CHECKLIST_AUTOMATION','FACETS_CLMU','EDOCS',
        'CIFT_SRC_TO_STG_FAC','COPS_SLA_FLEXCLONE_CHECK','CORRECTED_CLAIMS_AUTO_ADJUSTMENTS',
        'BATCH_RECYCLE_VALIDATION'
    ])[1 + (i % 15)],
    TIMESTAMP '2024-10-01 00:00:00' + (i * INTERVAL '4 hours'),
    CASE
        WHEN i % 20 = 0 THEN 'failed'
        WHEN i % 30 = 0 THEN 'timed_out'
        WHEN i % 50 = 0 THEN 'running'
        ELSE 'completed'
    END,
    CASE WHEN i % 20 = 0 THEN NULL ELSE 60 + (i % 3600) END,
    CASE WHEN i % 20 = 0 THEN 'Error: ' || (ARRAY['Connection timeout','File not found','Permission denied','Disk full','Agent not responding'])[1 + (i % 5)] ELSE NULL END,
    'VA01PMSQSIS001_ProdUS',
    (ARRAY['EDINET1P','EDINET2P','DWA1P','DWA2P'])[1 + (i % 4)]
FROM generate_series(1, 300) AS i;

-- Create indexes for common queries
CREATE INDEX idx_claims_status ON claims(claim_status);
CREATE INDEX idx_claims_date ON claims(date_of_service);
CREATE INDEX idx_claims_member ON claims(member_id);
CREATE INDEX idx_job_runs_job_id ON job_runs(job_id);
CREATE INDEX idx_job_runs_status ON job_runs(status);
CREATE INDEX idx_job_runs_date ON job_runs(run_date);
