-- Phase 2 Query: monthly_generation_mix and renewable_share_monthly
-- Purpose: Calculate ERCOT/Texas monthly generation share by fuel type and
-- combined wind+solar renewable penetration for downstream analysis.

CREATE OR REPLACE VIEW monthly_generation_mix AS
WITH monthly_totals AS (
    SELECT
        year,
        month,
        MAKE_DATE(year, month, 1) AS month_date,
        SUM(generation_mwh) AS total_generation_mwh
    FROM ercot_generation
    GROUP BY year, month
),
monthly_by_fuel AS (
    SELECT
        g.year,
        g.month,
        mt.month_date,
        g.fuel_type,
        SUM(g.generation_mwh) AS generation_mwh,
        mt.total_generation_mwh,
        ROUND(SUM(g.generation_mwh) / mt.total_generation_mwh * 100, 3) AS pct_share
    FROM ercot_generation AS g
    INNER JOIN monthly_totals AS mt
        ON g.year = mt.year
        AND g.month = mt.month
    GROUP BY
        g.year,
        g.month,
        mt.month_date,
        g.fuel_type,
        mt.total_generation_mwh
)
SELECT
    *,
    LAG(pct_share, 12) OVER (
        PARTITION BY fuel_type
        ORDER BY year, month
    ) AS pct_share_prior_year,
    pct_share - LAG(pct_share, 12) OVER (
        PARTITION BY fuel_type
        ORDER BY year, month
    ) AS yoy_change_ppts,
    AVG(pct_share) OVER (
        PARTITION BY fuel_type
        ORDER BY year, month
        ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
    ) AS rolling_12m_avg_pct
FROM monthly_by_fuel;

CREATE OR REPLACE VIEW renewable_share_monthly AS
WITH base AS (
    SELECT * FROM monthly_generation_mix
)
SELECT
    year,
    month,
    month_date,
    MAX(total_generation_mwh) AS total_generation_mwh,
    SUM(CASE WHEN fuel_type IN ('wind', 'solar') THEN generation_mwh ELSE 0 END) AS renewable_mwh,
    SUM(CASE WHEN fuel_type = 'wind' THEN generation_mwh ELSE 0 END) AS wind_mwh,
    SUM(CASE WHEN fuel_type = 'solar' THEN generation_mwh ELSE 0 END) AS solar_mwh,
    SUM(CASE WHEN fuel_type = 'natural_gas' THEN generation_mwh ELSE 0 END) AS gas_mwh,
    SUM(CASE WHEN fuel_type = 'coal' THEN generation_mwh ELSE 0 END) AS coal_mwh,
    ROUND(SUM(CASE WHEN fuel_type IN ('wind', 'solar') THEN generation_mwh ELSE 0 END)
        / MAX(total_generation_mwh) * 100, 3) AS renewable_pct,
    ROUND(SUM(CASE WHEN fuel_type = 'solar' THEN generation_mwh ELSE 0 END)
        / MAX(total_generation_mwh) * 100, 3) AS solar_pct,
    ROUND(SUM(CASE WHEN fuel_type = 'wind' THEN generation_mwh ELSE 0 END)
        / MAX(total_generation_mwh) * 100, 3) AS wind_pct,
    LAG(ROUND(SUM(CASE WHEN fuel_type IN ('wind', 'solar') THEN generation_mwh ELSE 0 END)
        / MAX(total_generation_mwh) * 100, 3), 12) OVER (ORDER BY year, month) AS renewable_pct_prior_year,
    ROUND(SUM(CASE WHEN fuel_type IN ('wind', 'solar') THEN generation_mwh ELSE 0 END)
        / MAX(total_generation_mwh) * 100, 3)
        - LAG(ROUND(SUM(CASE WHEN fuel_type IN ('wind', 'solar') THEN generation_mwh ELSE 0 END)
        / MAX(total_generation_mwh) * 100, 3), 12) OVER (ORDER BY year, month) AS renewable_yoy_change
FROM base
GROUP BY year, month, month_date
ORDER BY year, month;

SELECT * FROM monthly_generation_mix
ORDER BY year, month, fuel_type;
