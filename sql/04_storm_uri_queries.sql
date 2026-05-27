-- Phase 2 Query: storm_uri_analysis
-- Purpose: Compare February 2021 ERCOT total load during Winter Storm Uri
-- against a normal-February 2019-2020 hourly baseline.

CREATE OR REPLACE VIEW storm_uri_analysis AS
WITH uri_hourly AS (
    SELECT
        datetime,
        year,
        month,
        day,
        hour,
        load_mw AS demand_mw,
        zone
    FROM storm_uri_load
    WHERE datetime >= TIMESTAMP '2021-02-10 00:00:00'
      AND datetime < TIMESTAMP '2021-02-21 00:00:00'
      AND zone = 'TOTAL'
),
baseline_feb AS (
    SELECT
        hour,
        AVG(load_mw) AS baseline_load_mw
    FROM ercot_load
    WHERE month = 2
      AND year IN (2019, 2020)
      AND zone = 'TOTAL'
    GROUP BY hour
),
uri_with_baseline AS (
    SELECT
        u.datetime,
        u.year,
        u.month,
        u.day,
        u.hour,
        u.demand_mw,
        b.baseline_load_mw,
        u.demand_mw - b.baseline_load_mw AS demand_surge_mw,
        CASE
            WHEN u.datetime >= TIMESTAMP '2021-02-11 02:00:00'
             AND u.datetime <= TIMESTAMP '2021-02-19 12:00:00'
            THEN 1
            ELSE 0
        END AS outage_period_flag
    FROM uri_hourly AS u
    LEFT JOIN baseline_feb AS b
        ON u.hour = b.hour
)
SELECT
    *,
    MAX(demand_mw) OVER () AS peak_demand_in_period,
    MIN(demand_mw) OVER () AS min_demand_in_period,
    AVG(baseline_load_mw) OVER () AS avg_baseline
FROM uri_with_baseline
ORDER BY datetime;

SELECT * FROM storm_uri_analysis
ORDER BY datetime;
