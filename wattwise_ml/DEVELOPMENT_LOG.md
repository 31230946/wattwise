# WattWise ML: development log (what we tried, what happened, what we changed)

Every entry is something we measured or checked. Read this before the viva: examiners often ask "what didn't work?"
The same list is in the paper (Section VII, Table VIII).

## Version history

| Version | What it was | Main numbers |
|---|---|---|
| v1 | Next-day forecast on **synthetic** data, bandit with a flat reward | MAPE about 4%, but only because synthetic homes are neat. Never quote this number. |
| v2 | Real LCL data (148 homes), leaks fixed, real bandit reward, MSEDCL bill, appliance estimate | Next day WAPE 19.2%; bandit 95% of oracle |
| v3 | Monthly-bill first screen (no ML), daily path (next day / 7 / 30 days), weekly path (next week / 4 weeks), carbon, "predict the change" models, ranges, offline CLI | See `README.md`, "Results" |
| v3.1 | Simulated Pune homes from LCL + Prayas, calibration check, stress test on 146 more unseen London homes, "Homes like yours" | See `pune_sim/PUNE_SIM.md` |
| v3.2 | Weekly forecast removed (daily already covers 7 and 30 days); full React + Node website; bill-units label reworded | Daily results unchanged |
| v3.3 (current) | BEE star ratings in the appliance estimate; appliance list moved into an "Advanced" dropdown on the website. Later clean-up: old `/predict` route, old Node/React example files and superseded docs removed; "Not sure" removed from the AC question on the website | Forecast results unchanged |

## Everything we tried

| # | What we tried | What happened | What we changed |
|---|---|---|---|
| 1 | v1 trained and tested on synthetic data | ~4% MAPE | Switched to real LCL data: 19-22% error. Real homes are noisy. |
| 2 | "Home type" made from each home's full-year average, used as a model input | Leakage: the input partly *was* the answer | Removed as a model input. Peer bands use only each home's first 28 days, which are never targets. |
| 3 | Blend weights chosen on the test fold | Small leakage | Every choice now comes from an inner split of training homes. |
| 4 | App used the "best fold" model | Cherry-picking | App model retrained on all homes. |
| 5 | LCL timestamps used as-is | Each reading covers the half hour *before* its stamp, so days were split wrongly | Shifted back 30 min. Complete days only; gaps break the window. |
| 6 | v1 bandit reward | Same reward for every action, so nothing to learn | Each action targets its own gap against real peer homes. 95% of oracle. |
| 7 | Evening share fixed at 0.3 in the API | Ignored the user's real pattern | From the appliance form, else the peer median. |
| 8 | Tip said "higher than similar homes" without data | Unsupported claim | Wording depends on what was measured. Unknown night load is scaled from usage (rank correlation 0.86). |
| 9 | Assumed "shifting saves no money", then assumed an evening peak charge for homes | Both wrong per the MERC order | Rs 0.80/kWh solar-hours rebate for smart-meter homes; no peak charge for homes. |
| 10 | Idea: pretend to have appliance-meter data | Rejected: data fabrication | Appliance breakdown only from user inputs, labelled as an estimate. Phase 3: a *labelled* simulated set plus real smart-plug readings. |
| 11 | Give LCL homes the appliance mix of REFIT homes with a similar load shape | 4.27 vs 4.63 points error (7.9% better), below our pre-set 10% bar; with 1 neighbour it was worse | Not used. Negative result in the paper (VI-G). |
| 12 | Idea: next-week forecast from monthly bills | No basis (month ÷ 4.3) | Monthly-bill screen does no ML. |
| 13 | v3 first try: XGBoost on raw kWh for 7 days / 30 days / weekly | Lost to simple averages: 13.9 vs 13.5, 15.4 vs 14.8, 14.2 vs 13.6 | Predict the **change** from the recent average, with a trust weight set on training homes. |
| 14 | Change model for next week starting from the 4-week mean | Still lost to "same as last week" (14.1 vs 13.6) | Model picks its starting value on training homes. It picked last week, giving a tie (13.55 vs 13.56). |
| 15 | 80% range for every history length | Rare lengths had 4-66 test cases; one range excluded the forecast | Only lengths with ≥ 300 test cases; others use the nearest. |
| 16 | Claimed ranges widen with less history | Barely true for daily input | Claim removed. |
| 17 | Packaging the zip | The trained models only load on the same library versions | Retrained on Python 3.11 with pinned versions, checked to install on Windows, Mac and Linux. |
| 18 | Idea: photograph meters for 1 week and multiply by random factors to make more data | 1 week = 6 days of use, not enough for even one test; random factors make the test circular; "0 to minus" only lowers bills | Rejected. Built a calibrated simulation instead (row 19). |
| 19 | Simulated Pune homes: real LCL day-to-day behaviour, Pune level/shape/season from Prayas | First version failed calibration check 8 (AC load leaked into late February) | Fixed the simulator (summer starts 8 March), not the pass bar. 12/12 checks pass; only the weekend check was not built in. |
| 20 | Stress test: saved models on 146 more unseen London homes and on their simulated Pune versions | London: same errors as cross-validation. Pune sim: fine most of the year, but worse than the simple average for 30 days / 4 weeks when the AC season ends | Future work: add a season or temperature input. Reported as a limitation. |
| 21 | "Demo mode": pick a simulated home and watch the forecast | Made the website feel unfinished | Replaced by "Homes like yours": the user's own bills are matched to the 5 closest simulated Pune homes (typical day + 12-month outlook with bill and carbon). |
| 22 | Testing "Homes like yours" on the simulated homes (leave one out) | 2.7-4.1% error with the AC answer vs 13% for a flat guess, but flattering by construction (only 2 season templates) | Reported with that warning; never quoted as accuracy. Shows the AC question matters (halves the error). |
| 23 | Keeping a separate weekly forecast (2-12 weeks in, next week / 4 weeks out) | Next week only tied with "same as last week" (13.55 vs 13.56%); 4 weeks 14.0 vs 14.5%. Daily already gives 7 and 30 days ahead (13.2% and 14.3%; weekly 4 weeks was 14.0%, so roughly the same), and one input type is simpler for users and the viva | Removed in v3.2 from the API, models, website and docs. The numbers stay here as a record. |
| 24 | Appliance estimate used one typical wattage per appliance (AC 1.5 kW x 70% duty) | No way to reflect an efficient vs old appliance; AC typical was higher than BEE label figures | Added BEE star ratings (AC, fridge, ceiling fan) and the label kWh/year option. No star given: AC and fridge assume 3-star (AC now 0.63 kWh per hour of use for 1.5 ton, from the BEE label method). Still an estimate, scaled to the meter. |

## Planned, not done

- **Cross-city test:** train on LCL, test on REFIT's 20 whole-house meters (different city and years).
- **REFIT check of the watts × hours appliance estimate** (`refit_validation.py`; fill in the appliance map from the REFIT readme first).
- **Phase 3:** a labelled simulated appliance set (~100 entries, close to real plug-meter readings), plus 2-3 weeks of real smart-plug data from team homes.
- **`/feedback` endpoint**, so the bandit learns from real users.
- **Season/temperature input** for the 30-day and 4-week forecasts (found by the Pune stress test).
- **Ask Prayas for raw Pune smart-meter data** (student access) for a real Indian test.
