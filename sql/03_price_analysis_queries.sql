-- Phase 2 Query: price_cannibalization_dataset
-- Purpose: Join renewable share with Henry Hub gas prices and season controls
-- to create the regression input used for the price cannibalization analysis.
--
-- Important limitation: this dataset uses a gas-implied wholesale price proxy
-- because nodal/hub wholesale power prices are not part of the Phase 1 raw
-- data package. The proxy converts Henry Hub $/MMBtu to $/MWh using an
-- approximate 17.5 MMBtu/MWh peaker heat rate.

CREATE OR REPLACE VIEW price_cannibalization_dataset AS
WITH seasons AS (
    SELECT
        *,
        CASE
            WHEN month IN (6, 7, 8) THEN 'summer'
            WHEN month IN (12, 1, 2) THEN 'winter'
            ELSE 'shoulder'
        END AS season,
        CASE
            WHEN month IN (6, 7, 8, 12, 1, 2) THEN 1
            ELSE 0
        END AS peak_season_flag
    FROM renewable_share_monthly
),
with_gas AS (
    SELECT
        s.*,
        g.monthly_avg AS henry_hub_price,
        g.monthly_max AS henry_hub_max,
        g.monthly_min AS henry_hub_min,
        g.monthly_avg * 17.5 AS implied_wholesale_price_proxy
    FROM seasons AS s
    LEFT JOIN gas_prices AS g
        ON s.year = g.year
        AND s.month = g.month
    WHERE g.monthly_avg IS NOT NULL
)
SELECT *
FROM with_gas
ORDER BY year, month;

SELECT * FROM price_cannibalization_dataset
ORDER BY year, month;
