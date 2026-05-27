# ERCOT Power Market Intelligence
## Texas Grid Transformation and Market Signal Adequacy, 2015-2024

*Saatvika Chokkapu — MS Business Analytics & AI, UT Dallas — May 2026*  
*Data: U.S. Energy Information Administration; ERCOT Grid Operations*

## Executive Summary

ERCOT's generation mix changed materially between 2015 and 2024: renewable share rose from 10.3% to 30.2%, while coal fell from 26.6% to 11.3% of monthly generation share. Solar was the sharpest growth story, increasing 748% from 2019 to 2024 and reaching 7.9% of generation share in 2024. The market adequacy analysis is more nuanced: scarcity proxy hours increased from 176 in 2015 to 279 in 2024, and the 2024 Revenue Adequacy Index remained positive at 0.349, meaning this proxy does not show ERCOT's energy-only market has already broken.

## Background

ERCOT is the most important U.S. test case for high-renewable power market design. It serves most Texas load, operates with limited interconnection to neighboring systems, and relies on an energy-only market rather than a centralized capacity market. That structure makes price formation, scarcity conditions, and flexible-resource economics especially important for investors.

This study combines EIA Texas generation data, ERCOT hourly load data, Henry Hub gas prices, and public post-Uri outage figures. The objective is to quantify how the generation mix changed, where grid vulnerability appeared during Winter Storm Uri, and whether early market signals indicate stress in ERCOT's investment model.

## Generation Mix Transformation

Renewables nearly tripled their share of generation, rising 19.9 percentage points from 10.3% in 2015 to 30.2% in 2024. Wind increased from 10.2% to 22.3%, while solar grew from negligible levels to 7.9% by 2024. Coal's share declined 15.3 percentage points, from 26.6% to 11.3%, while natural gas remained the largest source at 50.7% in 2024.

## Price Dynamics and Cannibalization

The price dataset uses a gas-implied wholesale price proxy equal to Henry Hub multiplied by a fixed heat-rate assumption. That proxy is useful for framing gas-price exposure, but it is not a valid direct test of ERCOT price cannibalization. The full OLS model produced a renewable coefficient of -0.000 $/MWh per percentage point with p=0.885; because the dependent variable is mechanically derived from Henry Hub, actual ERCOT hub or LMP settlement prices would be required before making an investment-grade cannibalization claim.

## Grid Vulnerability: Winter Storm Uri

During February 10-20, 2021, ERCOT load peaked at 69.7 GW on 2021-02-14 20:00, with the maximum demand surge reaching 30.0 GW above a normal February hourly baseline. Public post-storm figures indicate about 34 GW of generation was forced offline at peak. Gas plant freeze-offs accounted for roughly 30 GW, or 88% of documented forced outages, while wind accounted for about 6%. The investment lesson is fuel-supply resilience, not just installed capacity.

## The Revenue Adequacy Problem

Notebook 07 tests whether ERCOT's energy-only market is showing early stress using load-based scarcity and curtailment-pressure proxies. Scarcity hours, defined as hours above 90% of each year's annual peak load, increased from 176 in 2015 to 279 in 2024. Curtailment-pressure hours, defined as spring low-demand hours, increased from 393 to 433. The composite Revenue Adequacy Index ranged from -0.182 to 1.032; it was negative in 2015-2016 but positive from 2017 onward, including 0.349 in 2024. This does not prove ERCOT has reached a breaking point today. It shows investors should monitor whether future renewable growth reduces scarcity revenues while increasing curtailment risk.

## Implications

For investors evaluating Texas gas plants, batteries, or renewable projects, the key result is not a single failure threshold but a tightening set of trade-offs: renewables are forecast to reach 45.1% by December 2030, while flexibility and congestion management become more valuable. Aurora-style analysis should therefore pair generation-mix forecasts with actual ERCOT price, curtailment, and ancillary-service revenue data before recommending capital allocation.
