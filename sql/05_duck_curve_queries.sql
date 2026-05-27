-- Phase 2 Query: duck_curve_analysis
-- Purpose: Estimate average hourly net load by year and season.
--
-- Net load = ERCOT total load - average hourly wind generation - average
-- hourly solar generation. Because the Phase 1 EIA generation source is
-- monthly rather than hourly, wind and solar are converted to average hourly
-- output within each month before aggregation. This is suitable for a first
-- pass trend indicator, not a unit-commitment operational model.

CREATE OR REPLACE VIEW duck_curve_analysis AS
WITH hourly_load AS (
    SELECT
        year,
        month,
        hour,
        CASE
            WHEN month IN (6, 7, 8) THEN 'summer'
            WHEN month IN (12, 1, 2) THEN 'winter'
            ELSE 'shoulder'
        END AS season,
        AVG(load_mw) AS avg_load_mw
    FROM ercot_load
    WHERE zone = 'TOTAL'
    GROUP BY year, month, hour, season
),
monthly_renewable AS (
    SELECT
        year,
        month,
        SUM(CASE WHEN fuel_type = 'wind' THEN generation_mwh ELSE 0 END)
            / (DAY(LAST_DAY(MAKE_DATE(year, month, 1))) * 24) AS avg_wind_mw,
        SUM(CASE WHEN fuel_type = 'solar' THEN generation_mwh ELSE 0 END)
            / (DAY(LAST_DAY(MAKE_DATE(year, month, 1))) * 24) AS avg_solar_mw
    FROM ercot_generation
    GROUP BY year, month
),
monthly_net_load AS (
    SELECT
        l.year,
        l.month,
        l.hour,
        l.season,
        l.avg_load_mw,
        COALESCE(r.avg_wind_mw, 0) AS avg_wind_mw,
        COALESCE(r.avg_solar_mw, 0) AS avg_solar_mw,
        l.avg_load_mw - COALESCE(r.avg_wind_mw, 0) - COALESCE(r.avg_solar_mw, 0) AS net_load_mw
    FROM hourly_load AS l
    LEFT JOIN monthly_renewable AS r
        ON l.year = r.year
        AND l.month = r.month
),
seasonal_hourly_profiles AS (
    SELECT
        year,
        hour,
        season,
        AVG(avg_load_mw) AS avg_load_mw,
        AVG(avg_wind_mw) AS avg_wind_mw,
        AVG(avg_solar_mw) AS avg_solar_mw,
        AVG(net_load_mw) AS net_load_mw
    FROM monthly_net_load
    GROUP BY year, hour, season
)
SELECT
    *,
    MIN(net_load_mw) OVER (PARTITION BY year, season) AS season_min_net_load,
    MAX(CASE WHEN hour BETWEEN 17 AND 21 THEN net_load_mw ELSE NULL END)
        OVER (PARTITION BY year, season) AS evening_peak_net_load,
    MAX(CASE WHEN hour BETWEEN 17 AND 21 THEN net_load_mw ELSE NULL END)
        OVER (PARTITION BY year, season)
        - MIN(net_load_mw) OVER (PARTITION BY year, season) AS duck_curve_depth_mw
FROM seasonal_hourly_profiles
ORDER BY year, season, hour;

SELECT * FROM duck_curve_analysis
ORDER BY year, season, hour;
