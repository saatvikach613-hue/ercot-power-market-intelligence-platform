-- Phase 1 schema and validation queries
-- ERCOT Power Market Intelligence Platform
--
-- These queries document the DuckDB tables created by
-- notebooks/01_ingestion_and_validation.ipynb / phase1_ingestion.py and the
-- validation checks used before approving Phase 1.

-- Expected tables
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'main'
ORDER BY table_name;

-- Date ranges and row counts
SELECT
    'ercot_generation' AS table_name,
    MIN(date) AS earliest,
    MAX(date) AS latest,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT year) AS years_covered
FROM ercot_generation
UNION ALL
SELECT
    'ercot_load' AS table_name,
    MIN(datetime) AS earliest,
    MAX(datetime) AS latest,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT year) AS years_covered
FROM ercot_load
UNION ALL
SELECT
    'gas_prices' AS table_name,
    MIN(date) AS earliest,
    MAX(date) AS latest,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT year) AS years_covered
FROM gas_prices;

-- Generation null check
SELECT
    SUM(CASE WHEN generation_mwh IS NULL THEN 1 ELSE 0 END) AS null_generation,
    SUM(CASE WHEN fuel_type IS NULL THEN 1 ELSE 0 END) AS null_fuel_type,
    SUM(CASE WHEN year IS NULL THEN 1 ELSE 0 END) AS null_year,
    SUM(CASE WHEN pct_of_total_monthly IS NULL THEN 1 ELSE 0 END) AS null_pct
FROM ercot_generation;

-- Fuel type distribution
SELECT
    fuel_type,
    COUNT(*) AS months,
    ROUND(SUM(generation_mwh) / 1e6, 2) AS total_twh,
    ROUND(AVG(pct_of_total_monthly), 2) AS avg_monthly_share_pct
FROM ercot_generation
GROUP BY fuel_type
ORDER BY total_twh DESC;

-- Monthly generation shares should sum to approximately 100%.
SELECT
    year,
    month,
    ROUND(SUM(pct_of_total_monthly), 1) AS total_pct
FROM ercot_generation
GROUP BY year, month
HAVING ABS(SUM(pct_of_total_monthly) - 100) > 2
ORDER BY year, month;

-- Total ERCOT load sanity check.
SELECT
    MIN(load_mw) AS min_load,
    MAX(load_mw) AS max_load,
    AVG(load_mw) AS avg_load,
    SUM(CASE WHEN load_mw < 0 THEN 1 ELSE 0 END) AS negative_values,
    SUM(CASE WHEN load_mw > 90000 THEN 1 ELSE 0 END) AS extreme_values
FROM ercot_load
WHERE zone = 'TOTAL';
