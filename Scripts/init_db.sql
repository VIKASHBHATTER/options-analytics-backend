-- ============================================
-- Options Analytics Database - Partitioned Schema
-- ============================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. INSTRUMENT MASTER TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS instrument_master (
    id BIGSERIAL PRIMARY KEY,
    security_id BIGINT UNIQUE NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    underlying VARCHAR(20) NOT NULL,
    strike_price DECIMAL(12,2),
    option_type CHAR(2) CHECK (option_type IN ('CE', 'PE')),
    expiry DATE,
    segment VARCHAR(20) DEFAULT 'NSE_FNO',
    lot_size INTEGER DEFAULT 50,
    tick_size DECIMAL(8,4) DEFAULT 0.05,
    instrument_token VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_instrument_master_security_id ON instrument_master(security_id);
CREATE INDEX idx_instrument_master_symbol ON instrument_master(symbol);
CREATE INDEX idx_instrument_master_underlying ON instrument_master(underlying);
CREATE INDEX idx_instrument_master_expiry ON instrument_master(expiry);
CREATE INDEX idx_instrument_master_strike ON instrument_master(strike_price);
CREATE INDEX idx_instrument_master_option_type ON instrument_master(option_type);
CREATE INDEX idx_instrument_master_composite ON instrument_master(underlying, expiry, strike_price, option_type);

-- ============================================
-- 2. STRIKE DATA - PARTITIONED BY TIME
-- ============================================
CREATE TABLE IF NOT EXISTS strike_data (
    id BIGSERIAL,
    snapshot_id BIGINT,
    underlying VARCHAR(20) NOT NULL,
    strike_price DECIMAL(12,2) NOT NULL,
    expiry DATE,

    -- Call Option Data
    ce_security_id BIGINT,
    ce_oi BIGINT DEFAULT 0,
    ce_oi_change BIGINT DEFAULT 0,
    ce_volume BIGINT DEFAULT 0,
    ce_ltp DECIMAL(12,4),
    ce_iv DECIMAL(8,4),
    ce_bid DECIMAL(12,4),
    ce_ask DECIMAL(12,4),
    ce_bid_qty BIGINT DEFAULT 0,
    ce_ask_qty BIGINT DEFAULT 0,

    -- Put Option Data
    pe_security_id BIGINT,
    pe_oi BIGINT DEFAULT 0,
    pe_oi_change BIGINT DEFAULT 0,
    pe_volume BIGINT DEFAULT 0,
    pe_ltp DECIMAL(12,4),
    pe_iv DECIMAL(8,4),
    pe_bid DECIMAL(12,4),
    pe_ask DECIMAL(12,4),
    pe_bid_qty BIGINT DEFAULT 0,
    pe_ask_qty BIGINT DEFAULT 0,

    -- Computed Metrics
    pcr_oi DECIMAL(10,4),
    pcr_volume DECIMAL(10,4),

    captured_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) PARTITION BY RANGE (captured_at);

-- Create initial partitions (weekly)
CREATE TABLE IF NOT EXISTS strike_data_2026_05_w3 
    PARTITION OF strike_data
    FOR VALUES FROM ('2026-05-18') TO ('2026-05-25');

CREATE TABLE IF NOT EXISTS strike_data_2026_05_w4 
    PARTITION OF strike_data
    FOR VALUES FROM ('2026-05-25') TO ('2026-06-01');

CREATE TABLE IF NOT EXISTS strike_data_2026_06_w1 
    PARTITION OF strike_data
    FOR VALUES FROM ('2026-06-01') TO ('2026-06-08');

-- Indexes on partitioned table
CREATE INDEX idx_strike_data_underlying ON strike_data(underlying);
CREATE INDEX idx_strike_data_expiry ON strike_data(expiry);
CREATE INDEX idx_strike_data_captured ON strike_data(captured_at);
CREATE INDEX idx_strike_data_snapshot ON strike_data(snapshot_id);

-- ============================================
-- 3. REALTIME METRICS CACHE
-- ============================================
CREATE TABLE IF NOT EXISTS realtime_metrics (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    metric_value DECIMAL(20,6),
    metric_data JSONB,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, metric_name)
);

CREATE INDEX idx_realtime_metrics_symbol ON realtime_metrics(symbol);
CREATE INDEX idx_realtime_metrics_name ON realtime_metrics(metric_name);

-- ============================================
-- 4. GREEKS DATA
-- ============================================
CREATE TABLE IF NOT EXISTS greeks_data (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR(20) NOT NULL,
    spot_price DECIMAL(12,4),
    strike_price DECIMAL(12,2),
    expiry DATE,
    days_to_expiry DECIMAL(8,2),

    -- Call Greeks
    ce_delta DECIMAL(10,6),
    ce_gamma DECIMAL(10,6),
    ce_theta DECIMAL(10,6),
    ce_vega DECIMAL(10,6),
    ce_rho DECIMAL(10,6),

    -- Put Greeks
    pe_delta DECIMAL(10,6),
    pe_gamma DECIMAL(10,6),
    pe_theta DECIMAL(10,6),
    pe_vega DECIMAL(10,6),
    pe_rho DECIMAL(10,6),

    -- Exposure Metrics
    gamma_exposure DECIMAL(20,2),
    delta_exposure DECIMAL(20,2),
    vega_exposure DECIMAL(20,2),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_greeks_data_symbol ON greeks_data(symbol);
CREATE INDEX idx_greeks_data_timestamp ON greeks_data(timestamp);
CREATE INDEX idx_greeks_data_expiry ON greeks_data(expiry);

-- ============================================
-- 5. ALERTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    alert_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    symbol VARCHAR(20),
    strike_price DECIMAL(12,2),
    message TEXT NOT NULL,
    metric_data JSONB,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alerts_type ON alerts(alert_type);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_alerts_symbol ON alerts(symbol);
CREATE INDEX idx_alerts_timestamp ON alerts(alert_timestamp);
CREATE INDEX idx_alerts_resolved ON alerts(is_resolved);

-- ============================================
-- 6. TRADE LOGS (For Risk Engine)
-- ============================================
CREATE TABLE IF NOT EXISTS trade_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    trade_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR(20) NOT NULL,
    option_type CHAR(2),
    strike_price DECIMAL(12,2),
    expiry DATE,
    action VARCHAR(20) CHECK (action IN ('BUY', 'SELL')),
    quantity INTEGER,
    price DECIMAL(12,4),
    premium DECIMAL(15,2),
    pnl DECIMAL(15,2),
    status VARCHAR(20) DEFAULT 'PENDING',
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trade_logs_user ON trade_logs(user_id);
CREATE INDEX idx_trade_logs_timestamp ON trade_logs(trade_timestamp);
CREATE INDEX idx_trade_logs_symbol ON trade_logs(symbol);

-- ============================================
-- 7. FEATURE STORE (For AI/ML)
-- ============================================
CREATE TABLE IF NOT EXISTS feature_store (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR(20) NOT NULL,
    feature_name VARCHAR(50) NOT NULL,
    feature_value DECIMAL(20,6),
    feature_vector JSONB,
    model_version VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_feature_store_symbol ON feature_store(symbol);
CREATE INDEX idx_feature_store_name ON feature_store(feature_name);
CREATE INDEX idx_feature_store_timestamp ON feature_store(timestamp);

-- ============================================
-- 8. AUTO PARTITION FUNCTION
-- ============================================
CREATE OR REPLACE FUNCTION create_weekly_partition()
RETURNS void AS $$
DECLARE
    start_date DATE;
    end_date DATE;
    partition_name TEXT;
BEGIN
    start_date := date_trunc('week', CURRENT_DATE + INTERVAL '7 days');
    end_date := start_date + INTERVAL '7 days';
    partition_name := 'strike_data_' || to_char(start_date, 'YYYY_MM_DD');

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF strike_data FOR VALUES FROM (%L) TO (%L)',
        partition_name, start_date, end_date
    );

    RAISE NOTICE 'Created partition: %', partition_name;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 9. SNAPSHOT SEQUENCE
-- ============================================
CREATE SEQUENCE IF NOT EXISTS snapshot_seq START 1;

-- ============================================
-- 10. UPDATE TRIGGER FOR INSTRUMENT MASTER
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_instrument_master_updated_at
    BEFORE UPDATE ON instrument_master
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- INITIAL DATA (Sample)
-- ============================================
INSERT INTO realtime_metrics (symbol, metric_name, metric_value, metric_data)
VALUES 
    ('NIFTY', 'spot_price', 0, '{"source": "init"}'),
    ('BANKNIFTY', 'spot_price', 0, '{"source": "init"}')
ON CONFLICT (symbol, metric_name) DO NOTHING;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO options_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO options_user;

