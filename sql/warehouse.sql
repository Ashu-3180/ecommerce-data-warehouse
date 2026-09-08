-- ShopSphere dimensional warehouse (star schema)
-- Requires sql/schemas.sql to have been applied first.
-- Safe to run more than once (IF NOT EXISTS / ON CONFLICT DO NOTHING).
--
-- Grain
-- -----
-- fact_sales:     ONE ROW = ONE PRODUCT LINE WITHIN ONE CUSTOMER ORDER
--                 (order-line grain; not one row per order header)
-- fact_delivery:  ONE ROW = ONE DELIVERY EVENT FOR ONE ORDER
--                 (not every order has a delivery)

-- ---------------------------------------------------------------------------
-- Dimensions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS warehouse.dim_date (
    date_key         INTEGER PRIMARY KEY,
    full_date        DATE NOT NULL UNIQUE,
    day_of_month     INTEGER NOT NULL,
    day_name         VARCHAR(20) NOT NULL,
    week_number      INTEGER NOT NULL,
    month_number     INTEGER NOT NULL,
    month_name       VARCHAR(20) NOT NULL,
    quarter_number   INTEGER NOT NULL,
    year             INTEGER NOT NULL,
    is_weekend       BOOLEAN NOT NULL,
    CONSTRAINT chk_dim_date_day CHECK (day_of_month BETWEEN 1 AND 31),
    CONSTRAINT chk_dim_date_month CHECK (month_number BETWEEN 1 AND 12),
    CONSTRAINT chk_dim_date_quarter CHECK (quarter_number BETWEEN 1 AND 4)
);

COMMENT ON TABLE warehouse.dim_date IS
    'Date dimension. date_key is YYYYMMDD (for example 20250131).';

CREATE TABLE IF NOT EXISTS warehouse.dim_customer (
    customer_key       BIGSERIAL PRIMARY KEY,
    customer_id        VARCHAR(64) NOT NULL UNIQUE,
    first_name         VARCHAR(100),
    last_name          VARCHAR(100),
    email              VARCHAR(255),
    phone              VARCHAR(50),
    city               VARCHAR(100),
    state              VARCHAR(100),
    country            VARCHAR(100),
    customer_segment   VARCHAR(50),
    signup_date        DATE
);

COMMENT ON COLUMN warehouse.dim_customer.customer_key IS
    'Warehouse surrogate key.';
COMMENT ON COLUMN warehouse.dim_customer.customer_id IS
    'Source-system business key (for example CUST-00001).';

CREATE TABLE IF NOT EXISTS warehouse.dim_product (
    product_key        BIGSERIAL PRIMARY KEY,
    product_id         VARCHAR(64) NOT NULL UNIQUE,
    product_name       VARCHAR(255),
    category           VARCHAR(100),
    subcategory        VARCHAR(100),
    brand              VARCHAR(100),
    supplier           VARCHAR(150),
    unit_cost          NUMERIC(12, 2),
    selling_price      NUMERIC(12, 2),
    product_rating     NUMERIC(3, 1),
    CONSTRAINT chk_dim_product_unit_cost CHECK (unit_cost IS NULL OR unit_cost >= 0),
    CONSTRAINT chk_dim_product_selling_price CHECK (selling_price IS NULL OR selling_price >= 0),
    CONSTRAINT chk_dim_product_rating CHECK (
        product_rating IS NULL OR (product_rating >= 0 AND product_rating <= 5)
    )
);

COMMENT ON COLUMN warehouse.dim_product.product_key IS
    'Warehouse surrogate key.';
COMMENT ON COLUMN warehouse.dim_product.product_id IS
    'Source-system business key (for example PRD-00001).';

CREATE TABLE IF NOT EXISTS warehouse.dim_store (
    store_key          BIGSERIAL PRIMARY KEY,
    store_id           VARCHAR(64) NOT NULL UNIQUE,
    store_name         VARCHAR(255),
    store_type         VARCHAR(50),
    country            VARCHAR(100),
    region             VARCHAR(100),
    city               VARCHAR(100),
    latitude           NUMERIC(9, 6),
    longitude          NUMERIC(10, 6),
    opening_date       DATE,
    CONSTRAINT chk_dim_store_type CHECK (
        store_type IS NULL
        OR store_type IN ('RETAIL_STORE', 'DARK_STORE', 'FULFILLMENT_CENTER')
    )
);

COMMENT ON COLUMN warehouse.dim_store.store_key IS
    'Warehouse surrogate key.';
COMMENT ON COLUMN warehouse.dim_store.store_id IS
    'Source-system business key (for example STR-0001).';

CREATE TABLE IF NOT EXISTS warehouse.dim_channel (
    channel_key        INTEGER PRIMARY KEY,
    channel_code       VARCHAR(40) NOT NULL UNIQUE,
    channel_name       VARCHAR(80) NOT NULL,
    channel_group      VARCHAR(40) NOT NULL
);

COMMENT ON TABLE warehouse.dim_channel IS
    'Sales channel dimension. channel_group supports DIGITAL, PHYSICAL, QUICK_COMMERCE.';

CREATE TABLE IF NOT EXISTS warehouse.dim_currency (
    currency_key       INTEGER PRIMARY KEY,
    currency_code      VARCHAR(10) NOT NULL UNIQUE,
    currency_name      VARCHAR(80) NOT NULL,
    currency_symbol    VARCHAR(10),
    rate_to_inr        NUMERIC(18, 6) NOT NULL,
    CONSTRAINT chk_dim_currency_rate CHECK (rate_to_inr > 0)
);

COMMENT ON TABLE warehouse.dim_currency IS
    'Currency dimension. rate_to_inr is a reference rate for reporting; daily historical rates live in staging.exchange_rates and will be applied by ETL later.';

CREATE TABLE IF NOT EXISTS warehouse.dim_payment_method (
    payment_method_key     INTEGER PRIMARY KEY,
    payment_method_code    VARCHAR(40) NOT NULL UNIQUE,
    payment_method_name    VARCHAR(80) NOT NULL,
    payment_type           VARCHAR(40) NOT NULL
);

-- ---------------------------------------------------------------------------
-- Facts
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS warehouse.fact_sales (
    sales_key              BIGSERIAL PRIMARY KEY,
    date_key               INTEGER NOT NULL,
    customer_key           BIGINT NOT NULL,
    product_key            BIGINT NOT NULL,
    store_key              BIGINT NOT NULL,
    channel_key            INTEGER NOT NULL,
    currency_key           INTEGER NOT NULL,
    payment_method_key     INTEGER,
    source_order_id        VARCHAR(64) NOT NULL,
    source_order_item_id   VARCHAR(64) NOT NULL,
    quantity               INTEGER NOT NULL,
    unit_price             NUMERIC(12, 2) NOT NULL,
    gross_amount           NUMERIC(14, 2) NOT NULL,
    discount_amount        NUMERIC(14, 2) NOT NULL,
    net_amount             NUMERIC(14, 2) NOT NULL,
    cost_amount            NUMERIC(14, 2) NOT NULL,
    profit_amount          NUMERIC(14, 2) NOT NULL,
    order_status           VARCHAR(50),
    CONSTRAINT uq_fact_sales_order_item UNIQUE (source_order_item_id),
    CONSTRAINT fk_fact_sales_date
        FOREIGN KEY (date_key) REFERENCES warehouse.dim_date (date_key),
    CONSTRAINT fk_fact_sales_customer
        FOREIGN KEY (customer_key) REFERENCES warehouse.dim_customer (customer_key),
    CONSTRAINT fk_fact_sales_product
        FOREIGN KEY (product_key) REFERENCES warehouse.dim_product (product_key),
    CONSTRAINT fk_fact_sales_store
        FOREIGN KEY (store_key) REFERENCES warehouse.dim_store (store_key),
    CONSTRAINT fk_fact_sales_channel
        FOREIGN KEY (channel_key) REFERENCES warehouse.dim_channel (channel_key),
    CONSTRAINT fk_fact_sales_currency
        FOREIGN KEY (currency_key) REFERENCES warehouse.dim_currency (currency_key),
    CONSTRAINT fk_fact_sales_payment_method
        FOREIGN KEY (payment_method_key) REFERENCES warehouse.dim_payment_method (payment_method_key),
    CONSTRAINT chk_fact_sales_quantity CHECK (quantity > 0),
    CONSTRAINT chk_fact_sales_unit_price CHECK (unit_price >= 0),
    CONSTRAINT chk_fact_sales_gross CHECK (gross_amount >= 0),
    CONSTRAINT chk_fact_sales_discount CHECK (discount_amount >= 0),
    CONSTRAINT chk_fact_sales_net CHECK (net_amount >= 0),
    CONSTRAINT chk_fact_sales_cost CHECK (cost_amount >= 0)
);

COMMENT ON TABLE warehouse.fact_sales IS
    'Sales fact at order-line grain. ONE ROW = ONE PRODUCT LINE WITHIN ONE CUSTOMER ORDER. Amounts are in the transaction currency (see currency_key). Expected measures: gross_amount = quantity * unit_price; discount_amount = gross_amount * discount_percent / 100; net_amount = gross_amount - discount_amount; cost_amount = quantity * product unit_cost; profit_amount = net_amount - cost_amount.';

CREATE TABLE IF NOT EXISTS warehouse.fact_delivery (
    delivery_key               BIGSERIAL PRIMARY KEY,
    date_key                   INTEGER NOT NULL,
    customer_key               BIGINT NOT NULL,
    store_key                  BIGINT NOT NULL,
    channel_key                INTEGER NOT NULL,
    source_order_id            VARCHAR(64) NOT NULL,
    delivery_id                VARCHAR(64) NOT NULL,
    delivery_type              VARCHAR(50) NOT NULL,
    delivery_status            VARCHAR(50) NOT NULL,
    delivery_distance_km       NUMERIC(10, 2) NOT NULL,
    delivery_time_minutes      INTEGER NOT NULL,
    delivery_fee               NUMERIC(12, 2) NOT NULL,
    CONSTRAINT uq_fact_delivery_id UNIQUE (delivery_id),
    CONSTRAINT fk_fact_delivery_date
        FOREIGN KEY (date_key) REFERENCES warehouse.dim_date (date_key),
    CONSTRAINT fk_fact_delivery_customer
        FOREIGN KEY (customer_key) REFERENCES warehouse.dim_customer (customer_key),
    CONSTRAINT fk_fact_delivery_store
        FOREIGN KEY (store_key) REFERENCES warehouse.dim_store (store_key),
    CONSTRAINT fk_fact_delivery_channel
        FOREIGN KEY (channel_key) REFERENCES warehouse.dim_channel (channel_key),
    CONSTRAINT chk_fact_delivery_distance CHECK (delivery_distance_km >= 0),
    CONSTRAINT chk_fact_delivery_time CHECK (delivery_time_minutes >= 0),
    CONSTRAINT chk_fact_delivery_fee CHECK (delivery_fee >= 0)
);

COMMENT ON TABLE warehouse.fact_delivery IS
    'Delivery fact grain: ONE ROW = ONE DELIVERY EVENT FOR ONE ORDER. Physical-store walk-out orders often have no row here. date_key is the order date until a true delivery timestamp is added by ETL.';

-- ---------------------------------------------------------------------------
-- Fact indexes (high-use FKs and ETL lookup keys)
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_fact_sales_date_key
    ON warehouse.fact_sales (date_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_customer_key
    ON warehouse.fact_sales (customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_product_key
    ON warehouse.fact_sales (product_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_store_key
    ON warehouse.fact_sales (store_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_channel_key
    ON warehouse.fact_sales (channel_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_currency_key
    ON warehouse.fact_sales (currency_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_source_order_id
    ON warehouse.fact_sales (source_order_id);

CREATE INDEX IF NOT EXISTS idx_fact_delivery_date_key
    ON warehouse.fact_delivery (date_key);
CREATE INDEX IF NOT EXISTS idx_fact_delivery_store_key
    ON warehouse.fact_delivery (store_key);
CREATE INDEX IF NOT EXISTS idx_fact_delivery_channel_key
    ON warehouse.fact_delivery (channel_key);
CREATE INDEX IF NOT EXISTS idx_fact_delivery_customer_key
    ON warehouse.fact_delivery (customer_key);
CREATE INDEX IF NOT EXISTS idx_fact_delivery_source_order_id
    ON warehouse.fact_delivery (source_order_id);

-- ---------------------------------------------------------------------------
-- Reference data that is safe to seed now (static / calendar)
-- ---------------------------------------------------------------------------

-- Calendar covers store opening dates (from 2016) through a buffer past the
-- current historical extract window.
INSERT INTO warehouse.dim_date (
    date_key,
    full_date,
    day_of_month,
    day_name,
    week_number,
    month_number,
    month_name,
    quarter_number,
    year,
    is_weekend
)
SELECT
    TO_CHAR(d::date, 'YYYYMMDD')::INTEGER,
    d::date,
    EXTRACT(DAY FROM d)::INTEGER,
    TRIM(TO_CHAR(d, 'FMDay')),
    EXTRACT(WEEK FROM d)::INTEGER,
    EXTRACT(MONTH FROM d)::INTEGER,
    TRIM(TO_CHAR(d, 'FMMonth')),
    EXTRACT(QUARTER FROM d)::INTEGER,
    EXTRACT(YEAR FROM d)::INTEGER,
    EXTRACT(ISODOW FROM d) IN (6, 7)
FROM generate_series(DATE '2015-01-01', DATE '2030-12-31', INTERVAL '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;

INSERT INTO warehouse.dim_channel (channel_key, channel_code, channel_name, channel_group)
VALUES
    (1, 'WEBSITE', 'Website', 'DIGITAL'),
    (2, 'MOBILE_APP', 'Mobile App', 'DIGITAL'),
    (3, 'PHYSICAL_STORE', 'Physical Store', 'PHYSICAL'),
    (4, 'QUICK_COMMERCE', 'Quick Commerce', 'QUICK_COMMERCE')
ON CONFLICT (channel_key) DO NOTHING;

-- Reference INR rates (approximate). Historical daily rates remain in
-- staging.exchange_rates for a later ETL step.
INSERT INTO warehouse.dim_currency (
    currency_key, currency_code, currency_name, currency_symbol, rate_to_inr
)
VALUES
    (1,  'INR', 'Indian Rupee',           'Rs',  1.000000),
    (2,  'USD', 'United States Dollar',   '$',   83.500000),
    (3,  'GBP', 'British Pound Sterling', 'GBP', 106.200000),
    (4,  'EUR', 'Euro',                   'EUR', 90.400000),
    (5,  'AED', 'UAE Dirham',             'AED', 22.730000),
    (6,  'SGD', 'Singapore Dollar',       'S$',  62.100000),
    (7,  'AUD', 'Australian Dollar',      'A$',  54.800000),
    (8,  'CAD', 'Canadian Dollar',        'C$',  61.200000),
    (9,  'JPY', 'Japanese Yen',           'JPY', 0.560000),
    (10, 'SAR', 'Saudi Riyal',            'SAR', 22.260000),
    (11, 'MYR', 'Malaysian Ringgit',      'RM',  18.700000),
    (12, 'NZD', 'New Zealand Dollar',     'NZ$', 50.400000)
ON CONFLICT (currency_key) DO NOTHING;

INSERT INTO warehouse.dim_payment_method (
    payment_method_key, payment_method_code, payment_method_name, payment_type
)
VALUES
    (1, 'CREDIT_CARD', 'Credit Card', 'CARD'),
    (2, 'DEBIT_CARD',  'Debit Card',  'CARD'),
    (3, 'UPI',         'UPI',         'BANK'),
    (4, 'NET_BANKING', 'Net Banking', 'BANK'),
    (5, 'WALLET',      'Wallet',      'WALLET'),
    (6, 'CASH',        'Cash',        'CASH'),
    (7, 'PAYPAL',      'PayPal',      'ONLINE')
ON CONFLICT (payment_method_key) DO NOTHING;
