-- ShopSphere analytics views for BI consumption
-- Requires sql/warehouse.sql to have been applied first.
-- Views return no rows until ETL loads the warehouse; they do not hard-code figures.
--
-- Monetary measures are converted to INR using warehouse.dim_currency.rate_to_inr
-- (a reference rate). Dated historical FX conversion is a later ETL improvement.

CREATE OR REPLACE VIEW analytics.monthly_sales AS
SELECT
    d.year,
    d.month_number AS month,
    d.month_name,
    ROUND(SUM(f.net_amount * ccy.rate_to_inr), 2) AS sales,
    COUNT(DISTINCT f.source_order_id) AS orders,
    SUM(f.quantity) AS units,
    ROUND(SUM(f.profit_amount * ccy.rate_to_inr), 2) AS profit
FROM warehouse.fact_sales AS f
INNER JOIN warehouse.dim_date AS d
    ON d.date_key = f.date_key
INNER JOIN warehouse.dim_currency AS ccy
    ON ccy.currency_key = f.currency_key
GROUP BY
    d.year,
    d.month_number,
    d.month_name;

COMMENT ON VIEW analytics.monthly_sales IS
    'Monthly sales, distinct orders, units, and profit in INR.';

CREATE OR REPLACE VIEW analytics.category_performance AS
SELECT
    p.category,
    ROUND(SUM(f.net_amount * ccy.rate_to_inr), 2) AS sales,
    SUM(f.quantity) AS units,
    COUNT(DISTINCT f.source_order_id) AS orders,
    ROUND(SUM(f.profit_amount * ccy.rate_to_inr), 2) AS profit
FROM warehouse.fact_sales AS f
INNER JOIN warehouse.dim_product AS p
    ON p.product_key = f.product_key
INNER JOIN warehouse.dim_currency AS ccy
    ON ccy.currency_key = f.currency_key
GROUP BY
    p.category;

COMMENT ON VIEW analytics.category_performance IS
    'Sales, units, distinct orders, and profit by product category (INR).';

CREATE OR REPLACE VIEW analytics.product_performance AS
SELECT
    p.product_id,
    p.product_name,
    p.category,
    p.brand,
    ROUND(SUM(f.net_amount * ccy.rate_to_inr), 2) AS sales,
    SUM(f.quantity) AS units,
    COUNT(DISTINCT f.source_order_id) AS orders,
    ROUND(SUM(f.profit_amount * ccy.rate_to_inr), 2) AS profit
FROM warehouse.fact_sales AS f
INNER JOIN warehouse.dim_product AS p
    ON p.product_key = f.product_key
INNER JOIN warehouse.dim_currency AS ccy
    ON ccy.currency_key = f.currency_key
GROUP BY
    p.product_id,
    p.product_name,
    p.category,
    p.brand;

COMMENT ON VIEW analytics.product_performance IS
    'Sales, units, distinct orders, and profit by product (INR).';

CREATE OR REPLACE VIEW analytics.store_performance AS
SELECT
    s.store_id,
    s.store_name,
    s.store_type,
    s.country,
    s.city,
    ROUND(SUM(f.net_amount * ccy.rate_to_inr), 2) AS sales,
    COUNT(DISTINCT f.source_order_id) AS orders,
    SUM(f.quantity) AS units,
    ROUND(SUM(f.profit_amount * ccy.rate_to_inr), 2) AS profit
FROM warehouse.fact_sales AS f
INNER JOIN warehouse.dim_store AS s
    ON s.store_key = f.store_key
INNER JOIN warehouse.dim_currency AS ccy
    ON ccy.currency_key = f.currency_key
GROUP BY
    s.store_id,
    s.store_name,
    s.store_type,
    s.country,
    s.city;

COMMENT ON VIEW analytics.store_performance IS
    'Sales, distinct orders, units, and profit by store / fulfillment location (INR).';

CREATE OR REPLACE VIEW analytics.channel_performance AS
SELECT
    ch.channel_code,
    ch.channel_name,
    ch.channel_group,
    ROUND(SUM(f.net_amount * ccy.rate_to_inr), 2) AS sales,
    COUNT(DISTINCT f.source_order_id) AS orders,
    SUM(f.quantity) AS units,
    ROUND(SUM(f.profit_amount * ccy.rate_to_inr), 2) AS profit
FROM warehouse.fact_sales AS f
INNER JOIN warehouse.dim_channel AS ch
    ON ch.channel_key = f.channel_key
INNER JOIN warehouse.dim_currency AS ccy
    ON ccy.currency_key = f.currency_key
GROUP BY
    ch.channel_code,
    ch.channel_name,
    ch.channel_group;

COMMENT ON VIEW analytics.channel_performance IS
    'Sales, distinct orders, units, and profit by sales channel (INR).';

CREATE OR REPLACE VIEW analytics.customer_performance AS
SELECT
    c.customer_id,
    c.first_name,
    c.last_name,
    c.country,
    c.customer_segment,
    ROUND(SUM(f.net_amount * ccy.rate_to_inr), 2) AS sales,
    COUNT(DISTINCT f.source_order_id) AS orders,
    SUM(f.quantity) AS units,
    ROUND(SUM(f.profit_amount * ccy.rate_to_inr), 2) AS profit
FROM warehouse.fact_sales AS f
INNER JOIN warehouse.dim_customer AS c
    ON c.customer_key = f.customer_key
INNER JOIN warehouse.dim_currency AS ccy
    ON ccy.currency_key = f.currency_key
GROUP BY
    c.customer_id,
    c.first_name,
    c.last_name,
    c.country,
    c.customer_segment;

COMMENT ON VIEW analytics.customer_performance IS
    'Sales, distinct orders, units, and profit by customer (INR).';

CREATE OR REPLACE VIEW analytics.delivery_performance AS
SELECT
    del.delivery_type,
    del.delivery_status,
    ch.channel_group,
    COUNT(*) AS deliveries,
    ROUND(AVG(del.delivery_distance_km), 2) AS avg_distance_km,
    ROUND(AVG(del.delivery_time_minutes), 2) AS avg_time_minutes,
    ROUND(SUM(del.delivery_fee), 2) AS total_delivery_fee
FROM warehouse.fact_delivery AS del
INNER JOIN warehouse.dim_channel AS ch
    ON ch.channel_key = del.channel_key
GROUP BY
    del.delivery_type,
    del.delivery_status,
    ch.channel_group;

COMMENT ON VIEW analytics.delivery_performance IS
    'Delivery counts and averages by type, status, and channel group.';
