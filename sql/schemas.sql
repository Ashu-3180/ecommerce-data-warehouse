-- ShopSphere PostgreSQL schemas and landing-zone tables
-- Safe to run more than once (IF NOT EXISTS).
-- Does not drop schemas, tables, or data.
--
-- Run order:
--   1) CREATE DATABASE shopsphere;   -- run separately as a superuser
--   2) sql/schemas.sql               -- this file
--   3) sql/warehouse.sql
--   4) sql/analytics.sql

-- ---------------------------------------------------------------------------
-- 1. Schemas
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS warehouse;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS monitoring;

COMMENT ON SCHEMA raw IS
    'Source landing zone. CSV extracts are stored with little transformation so dirty rows can be loaded.';
COMMENT ON SCHEMA staging IS
    'Cleaned, typed, intermediate tables used after validation and before the dimensional warehouse.';
COMMENT ON SCHEMA warehouse IS
    'Star-schema analytical data warehouse (dimensions and facts).';
COMMENT ON SCHEMA analytics IS
    'BI-facing views built on warehouse tables.';
COMMENT ON SCHEMA monitoring IS
    'ETL run history and data-quality results.';

-- ---------------------------------------------------------------------------
-- 2. Raw tables
-- Source-oriented columns. No foreign keys and no strict CHECKs so
-- intentionally dirty CSV rows can still land here.
-- Types are close to the CSV, but TEXT/VARCHAR is used where the generator
-- (or a real source) may send malformed values.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw.customers (
    _raw_id            BIGSERIAL PRIMARY KEY,
    customer_id        VARCHAR(64),
    first_name         VARCHAR(100),
    last_name          VARCHAR(100),
    email              VARCHAR(255),
    phone              VARCHAR(50),
    city               VARCHAR(100),
    state              VARCHAR(100),
    country            VARCHAR(100),
    customer_segment   VARCHAR(50),
    signup_date        VARCHAR(50),
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw.products (
    _raw_id            BIGSERIAL PRIMARY KEY,
    product_id         VARCHAR(64),
    product_name       VARCHAR(255),
    category           VARCHAR(100),
    subcategory        VARCHAR(100),
    brand              VARCHAR(100),
    supplier           VARCHAR(150),
    unit_cost          VARCHAR(50),
    selling_price      VARCHAR(50),
    product_rating     VARCHAR(50),
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw.stores (
    _raw_id            BIGSERIAL PRIMARY KEY,
    store_id           VARCHAR(64),
    store_name         VARCHAR(255),
    store_type         VARCHAR(50),
    country            VARCHAR(100),
    region             VARCHAR(100),
    city               VARCHAR(100),
    latitude           VARCHAR(50),
    longitude          VARCHAR(50),
    opening_date       VARCHAR(50),
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw.orders (
    _raw_id            BIGSERIAL PRIMARY KEY,
    order_id           VARCHAR(64),
    customer_id        VARCHAR(64),
    store_id           VARCHAR(64),
    order_date         VARCHAR(50),
    sales_channel      VARCHAR(50),
    order_status       VARCHAR(50),
    currency           VARCHAR(20),
    order_total        VARCHAR(50),
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw.order_items (
    _raw_id            BIGSERIAL PRIMARY KEY,
    order_item_id      VARCHAR(64),
    order_id           VARCHAR(64),
    product_id         VARCHAR(64),
    quantity           VARCHAR(50),
    unit_price         VARCHAR(50),
    discount_percent   VARCHAR(50),
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw.payments (
    _raw_id            BIGSERIAL PRIMARY KEY,
    payment_id         VARCHAR(64),
    order_id           VARCHAR(64),
    payment_method     VARCHAR(50),
    payment_status     VARCHAR(50),
    payment_amount     VARCHAR(50),
    payment_date       VARCHAR(50),
    currency           VARCHAR(20),
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw.deliveries (
    _raw_id                    BIGSERIAL PRIMARY KEY,
    delivery_id                VARCHAR(64),
    order_id                   VARCHAR(64),
    store_id                   VARCHAR(64),
    delivery_type              VARCHAR(50),
    delivery_status            VARCHAR(50),
    delivery_distance_km       VARCHAR(50),
    delivery_time_minutes      VARCHAR(50),
    delivery_fee               VARCHAR(50),
    _ingested_at               TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw.exchange_rates (
    _raw_id            BIGSERIAL PRIMARY KEY,
    rate_date          VARCHAR(50),
    currency_code      VARCHAR(20),
    rate_to_inr        VARCHAR(50),
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_raw_customers_customer_id
    ON raw.customers (customer_id);
CREATE INDEX IF NOT EXISTS idx_raw_products_product_id
    ON raw.products (product_id);
CREATE INDEX IF NOT EXISTS idx_raw_stores_store_id
    ON raw.stores (store_id);
CREATE INDEX IF NOT EXISTS idx_raw_orders_order_id
    ON raw.orders (order_id);
CREATE INDEX IF NOT EXISTS idx_raw_order_items_order_id
    ON raw.order_items (order_id);
CREATE INDEX IF NOT EXISTS idx_raw_payments_order_id
    ON raw.payments (order_id);
CREATE INDEX IF NOT EXISTS idx_raw_deliveries_order_id
    ON raw.deliveries (order_id);
CREATE INDEX IF NOT EXISTS idx_raw_exchange_rates_date_ccy
    ON raw.exchange_rates (rate_date, currency_code);

-- ---------------------------------------------------------------------------
-- 3. Staging tables
-- Typed, cleaned representation. Validation flags are placeholders for ETL.
-- No unique business-key constraints yet: duplicates are a data-quality issue
-- that the future validation step must detect.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS staging.customers (
    _staging_id        BIGSERIAL PRIMARY KEY,
    customer_id        VARCHAR(64),
    first_name         VARCHAR(100),
    last_name          VARCHAR(100),
    email              VARCHAR(255),
    phone              VARCHAR(50),
    city               VARCHAR(100),
    state              VARCHAR(100),
    country            VARCHAR(100),
    customer_segment   VARCHAR(50),
    signup_date        DATE,
    _is_valid          BOOLEAN,
    _dq_status         VARCHAR(20),
    _rejection_reason  TEXT,
    _processed_at      TIMESTAMP WITH TIME ZONE,
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.products (
    _staging_id        BIGSERIAL PRIMARY KEY,
    product_id         VARCHAR(64),
    product_name       VARCHAR(255),
    category           VARCHAR(100),
    subcategory        VARCHAR(100),
    brand              VARCHAR(100),
    supplier           VARCHAR(150),
    unit_cost          NUMERIC(12, 2),
    selling_price      NUMERIC(12, 2),
    product_rating     NUMERIC(3, 1),
    _is_valid          BOOLEAN,
    _dq_status         VARCHAR(20),
    _rejection_reason  TEXT,
    _processed_at      TIMESTAMP WITH TIME ZONE,
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.stores (
    _staging_id        BIGSERIAL PRIMARY KEY,
    store_id           VARCHAR(64),
    store_name         VARCHAR(255),
    store_type         VARCHAR(50),
    country            VARCHAR(100),
    region             VARCHAR(100),
    city               VARCHAR(100),
    latitude           NUMERIC(9, 6),
    longitude          NUMERIC(10, 6),
    opening_date       DATE,
    _is_valid          BOOLEAN,
    _dq_status         VARCHAR(20),
    _rejection_reason  TEXT,
    _processed_at      TIMESTAMP WITH TIME ZONE,
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.orders (
    _staging_id        BIGSERIAL PRIMARY KEY,
    order_id           VARCHAR(64),
    customer_id        VARCHAR(64),
    store_id           VARCHAR(64),
    order_date         DATE,
    sales_channel      VARCHAR(50),
    order_status       VARCHAR(50),
    currency           VARCHAR(10),
    order_total        NUMERIC(14, 2),
    _is_valid          BOOLEAN,
    _dq_status         VARCHAR(20),
    _rejection_reason  TEXT,
    _processed_at      TIMESTAMP WITH TIME ZONE,
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.order_items (
    _staging_id        BIGSERIAL PRIMARY KEY,
    order_item_id      VARCHAR(64),
    order_id           VARCHAR(64),
    product_id         VARCHAR(64),
    quantity           INTEGER,
    unit_price         NUMERIC(12, 2),
    discount_percent   NUMERIC(5, 2),
    _is_valid          BOOLEAN,
    _dq_status         VARCHAR(20),
    _rejection_reason  TEXT,
    _processed_at      TIMESTAMP WITH TIME ZONE,
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.payments (
    _staging_id        BIGSERIAL PRIMARY KEY,
    payment_id         VARCHAR(64),
    order_id           VARCHAR(64),
    payment_method     VARCHAR(50),
    payment_status     VARCHAR(50),
    payment_amount     NUMERIC(14, 2),
    payment_date       DATE,
    currency           VARCHAR(10),
    _is_valid          BOOLEAN,
    _dq_status         VARCHAR(20),
    _rejection_reason  TEXT,
    _processed_at      TIMESTAMP WITH TIME ZONE,
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.deliveries (
    _staging_id                BIGSERIAL PRIMARY KEY,
    delivery_id                VARCHAR(64),
    order_id                   VARCHAR(64),
    store_id                   VARCHAR(64),
    delivery_type              VARCHAR(50),
    delivery_status            VARCHAR(50),
    delivery_distance_km       NUMERIC(10, 2),
    delivery_time_minutes      INTEGER,
    delivery_fee               NUMERIC(12, 2),
    _is_valid                  BOOLEAN,
    _dq_status                 VARCHAR(20),
    _rejection_reason          TEXT,
    _processed_at              TIMESTAMP WITH TIME ZONE,
    _ingested_at               TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.exchange_rates (
    _staging_id        BIGSERIAL PRIMARY KEY,
    rate_date          DATE,
    currency_code      VARCHAR(10),
    rate_to_inr        NUMERIC(18, 6),
    _is_valid          BOOLEAN,
    _dq_status         VARCHAR(20),
    _rejection_reason  TEXT,
    _processed_at      TIMESTAMP WITH TIME ZONE,
    _ingested_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stg_customers_customer_id
    ON staging.customers (customer_id);
CREATE INDEX IF NOT EXISTS idx_stg_products_product_id
    ON staging.products (product_id);
CREATE INDEX IF NOT EXISTS idx_stg_stores_store_id
    ON staging.stores (store_id);
CREATE INDEX IF NOT EXISTS idx_stg_orders_order_id
    ON staging.orders (order_id);
CREATE INDEX IF NOT EXISTS idx_stg_order_items_order_id
    ON staging.order_items (order_id);
CREATE INDEX IF NOT EXISTS idx_stg_payments_order_id
    ON staging.payments (order_id);
CREATE INDEX IF NOT EXISTS idx_stg_deliveries_order_id
    ON staging.deliveries (order_id);
CREATE INDEX IF NOT EXISTS idx_stg_exchange_rates_date_ccy
    ON staging.exchange_rates (rate_date, currency_code);

-- ---------------------------------------------------------------------------
-- 4. Monitoring metadata (used by a later ETL layer)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS monitoring.pipeline_runs (
    run_id               BIGSERIAL PRIMARY KEY,
    pipeline_name        VARCHAR(100) NOT NULL,
    started_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at         TIMESTAMP WITH TIME ZONE,
    status               VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    records_extracted    INTEGER,
    records_validated    INTEGER,
    records_rejected     INTEGER,
    records_loaded       INTEGER,
    quality_score        NUMERIC(5, 2),
    error_message        TEXT,
    CONSTRAINT chk_pipeline_runs_status
        CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED', 'PARTIAL')),
    CONSTRAINT chk_pipeline_runs_counts
        CHECK (
            COALESCE(records_extracted, 0) >= 0
            AND COALESCE(records_validated, 0) >= 0
            AND COALESCE(records_rejected, 0) >= 0
            AND COALESCE(records_loaded, 0) >= 0
        ),
    CONSTRAINT chk_pipeline_runs_quality_score
        CHECK (quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100))
);

-- Safe for databases created before quality_score existed.
ALTER TABLE monitoring.pipeline_runs
    ADD COLUMN IF NOT EXISTS quality_score NUMERIC(5, 2);

CREATE TABLE IF NOT EXISTS monitoring.data_quality_results (
    quality_result_id    BIGSERIAL PRIMARY KEY,
    run_id               BIGINT NOT NULL,
    table_name           VARCHAR(100) NOT NULL,
    rule_name            VARCHAR(150) NOT NULL,
    records_checked      INTEGER NOT NULL,
    records_failed       INTEGER NOT NULL,
    failure_rate         NUMERIC(7, 4),
    created_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dq_results_run
        FOREIGN KEY (run_id) REFERENCES monitoring.pipeline_runs (run_id),
    CONSTRAINT chk_dq_records_checked
        CHECK (records_checked >= 0),
    CONSTRAINT chk_dq_records_failed
        CHECK (records_failed >= 0 AND records_failed <= records_checked),
    CONSTRAINT chk_dq_failure_rate
        CHECK (failure_rate IS NULL OR (failure_rate >= 0 AND failure_rate <= 1))
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at
    ON monitoring.pipeline_runs (started_at);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status
    ON monitoring.pipeline_runs (status);
CREATE INDEX IF NOT EXISTS idx_dq_results_run_id
    ON monitoring.data_quality_results (run_id);
CREATE INDEX IF NOT EXISTS idx_dq_results_table_rule
    ON monitoring.data_quality_results (table_name, rule_name);
