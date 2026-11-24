# Datasets and official sources

## Used to train the models

**Low Carbon London smart meter data (refactored), 2013**
- Download: https://data.4tu.nl/datasets/fbbe775b-48d8-469f-a39b-b64488bfd6fd (file `LCL_2013_kWh.csv.zip`, ~137 MB zipped, ~590 MB unzipped)
- Original release: UK Power Networks, Low Carbon London project, CC-BY: https://data.london.gov.uk/dataset/smartmeter-energy-use-data-in-london-households
- What it is: half-hourly kWh for 4,443 London homes on a flat tariff, all of 2013. One column per home (`MAC######`), one row per half hour. No dwelling type or household size.
- How we use it: a random 150 homes (seed 42). 149 have complete days and 148 have enough history, giving 52,471 complete days. Put the file in `data/` and run `python train.py --real`.
- Credit line: "Low Carbon London smart meter data, UK Power Networks (CC-BY), refactored by S. Tindemans, TU Delft (4TU.ResearchData)."

## Used for side experiments (optional)

**REFIT: Electrical Load Measurements (Cleaned)**, 20 UK homes with 9 metered appliances each
- Download: https://pureportal.strath.ac.uk/en/datasets/refit-electrical-load-measurements-cleaned/ (DOI 10.15129/9ab14b0e-19ac-4279-938f-27f643078cec), CC BY 4.0
- Files: `CLEAN_REFIT_081116.7z` (~490 MB) and `CLEAN_READ_ME_081116.txt` (appliance list per house)
- Paper: Murray, Stankovic & Stankovic (2017), *Scientific Data* 4:160122
- Used for: (1) the "can load shape stand in for appliance data?" test, which was negative and is reported in the paper; (2) `refit_validation.py`, an optional check of the appliance estimate that has not been run yet.

## Used to build the simulated Pune homes (published numbers only)

**Prayas (Energy Group), Pune: "Insights from smart metering data"**: minute-level smart meters in about 115 homes (Pune city, Pune district, Aurangabad, Kanpur rural, Gonda), Jan 2018 - Jun 2020.
- https://energy.prayaspune.org/electricity-consumption-patterns (monthly kWh: Pune city average 156, about 60 to 348)
- https://energy.prayaspune.org/electricity-load-patterns (watts by hour and season)
- https://energy.prayaspune.org/our-work/article-and-blog/temperature-and-electricity-consumption-patterns (AC only in summer, mostly at night)
- Accessed 27 Oct 2026. Raw data is not published on these pages (eMARC dashboards at emarc.watchyourpower.org).
- Used only as calibration targets in `pune_sim/pune_targets.json`. The simulated homes themselves come from LCL.

## Numbers built into the app (with their sources)

| Number | Value | Source |
|---|---|---|
| MSEDCL residential slabs, FY 2026-27 | Rs 4.32 / 9.40 / 12.51 / 13.97 per kWh, wheeling Rs 1.20, fixed Rs 130 | MERC MYT Order press note, Mar 2025, Annexure 3: https://merc.gov.in/wp-content/uploads/2025/03/Press-Note_MYT-Order_MSEDCL_English-2.pdf |
| ToD solar-hours rebate, homes with a ToD/smart meter | Rs 0.80/kWh, 09:00-17:00 (FY26), rising to Rs 1.00 by FY30; no peak charge for homes | same press note, Section 12 |
| Grid carbon factor | 0.727 kg CO2/kWh (2023-24) | CEA CO2 Baseline Database, User Guide v20.0, Appendix C, Table B |
| Appliance star values (AC, fridge, ceiling fan) | AC 1.5 t: 0.74/0.70/0.63/0.56/0.46 kWh per hour of use (1-5 star); fridge 250 L: 1.10-0.45 kWh/day; fan: 64-52 W | BEE "Know your Star Label" guide, Session 2 (beestarlabel.com/Content/Files/Session_2.pdf); Down To Earth / CSE, 22 Sep 2025 (AC label = 1,600 h/year; 3/4/5-star averages 1,008/903/~740 kWh); Dept. of Consumer Affairs fan test (210 m3/min minimum air delivery). Derivation in `appliance_catalog.json` |
| Expected saving if tips are followed | 4-7% | Nguyen et al. 2024 (Energy Policy 195, RCT, Vietnam, 4.1-6.7%); Malaviya & Chandiwala, WRI 2018 (Delhi, 7%); Allcott 2011 (US, ~2%) |

Check the tariff and carbon numbers before the final demo. MERC review orders (Case 75 of 2025, March 2026 post-remand) may have changed the rates. Both numbers live in `tariff_config.json` and `carbon_config.json`, so updating them needs no code change.
