# Simulated Pune homes (LCL-derived): what, how, results, limits

> **Everything in this folder is SIMULATED data.** It is made from real London homes reshaped
> to match published Pune averages. Use it for the demo and as a stress test. Never present it
> as real Indian readings, and never put its numbers in the main results table.

## 1. Why

Our forecast is trained on London homes, but the app is for Maharashtra. No open Indian daily
dataset was available in time, and we have no IoT hardware. So we built a **calibrated simulation**:
it keeps the real behaviour of London homes and changes only the things we have published Pune numbers for.

## 2. What is kept and what is changed

| | Where it comes from |
|---|---|
| Day-to-day ups and downs, weekly habits, odd days, half-hour spikiness | **Kept** from 146 real LCL homes |
| Usage level (kWh per month) | **Changed** to the Pune spread (Prayas: average 156 kWh/month, about 60 for basic homes, about 348 with AC or water heater) |
| Shape of the day | **Changed** to Pune: morning peak ~350 W at 9 am (January), evening peak 200-250 W at 9 pm, night 100-150 W |
| Season | **Changed**: London's winter peak is removed; Pune summer added (May night peak ~350 W, ~600 W in AC homes; no AC in February and early March) |
| AC homes | **Our assumption**: 30% of homes, picked at random from the top 60% by usage |

Every Pune number and every assumption is in `pune_targets.json`, with the source pages.

**The 146 homes are NOT the 148 homes the models were trained on** (different random draw,
training homes excluded). So the stress test runs on homes the model never saw.

### How one home is changed (in plain words)
1. Take the real London home's daily totals and divide each day by that home's own 31-day average.
   This removes London's winter-heating season but keeps the day-to-day wiggle.
2. Give the home a Pune usage level: rank all 146 homes by London usage and give each home the
   matching position in the Pune spread (lowest London home gets a low Pune level, and so on).
3. Multiply by the Pune season for that date (higher in April-May, more in AC homes).
4. Spread each day over the half hours using the Pune daily shape, times the London home's
   own half-hour spikiness (so it isn't a smooth textbook curve).

## 3. Calibration check (pass bars set before running, in `pune_targets.json`)

| # | Check | Published (Prayas, Pune city) | Simulated | Result |
|---|---|---|---|---|
| 1 | Average monthly use | 156 kWh | 155 kWh | PASS |
| 2 | Spread, low / high homes* | about 60 / about 348 kWh | 60 / 329 kWh | PASS |
| 3 | January morning peak | about 350 W, about 9 am | 333 W, 9 am | PASS |
| 4 | Evening peak (Jan and Aug) | 200-250 W, about 9 pm | 230 W, 9 pm | PASS |
| 5 | Night load 1-5 am (Jan, Aug, Nov) | 100-150 W | 120-121 W | PASS |
| 6 | May night peak, all homes | about 350 W, 12-1 am | 332 W, midnight | PASS |
| 7 | May night peak, AC homes | about 600 W | 632 W | PASS |
| 8 | No AC in February | not raised | 149 W vs 148 W in Jan | PASS (failed in the first version, see below) |
| 9 | Weekend daytime higher than weekdays | higher | 235 W vs 197 W | PASS (**not** built in, see below) |

\* Read as the 2.5th and 97.5th percentile of homes. Prayas gives group values, not percentiles.

**How to read this honestly:**
- Checks 1-8 were used to *build* the simulation. Passing them only shows the build worked,
  i.e. the London wiggle didn't wreck the Pune shape. It is not proof the data behaves like
  real Pune homes.
- Check 9 was **not** built in. It comes from the London homes' own habits, and it happens
  to match what Prayas reports for Pune. That is the only independent check.
- **Check 8 failed the first time.** The smoothing between months let some AC load leak into
  late February (160 W vs 145 W in January). We fixed the simulator, not the pass bar: summer now
  starts on 8 March. We report this because it is the kind of thing an examiner asks about.

## 4. Stress test: the saved models (trained on London) on these homes

WAPE = total error / total use (lower is better). Coverage = how often the real value fell
inside the 80% range (should be about 80%).

### (a) 146 unseen London homes, real data (a genuine extra test)

| Forecast | WattWise | Simple method | Range coverage |
|---|---|---|---|
| Next day | **18.4%** | 19.4% (avg of last 7 days) | 78% |
| Next 7 days | **13.1%** | 13.4% | 77% |
| Next 30 days | **13.2%** | 13.5% | 78% |

These match the cross-validation results (`models/results.json`), so the models hold up on a
fresh set of real homes. Ranges cover slightly under 80%, which is close enough to call honest.

### (b) The same homes as SIMULATED Pune homes

| Forecast | All year | AC season starts (8 Mar - 31 May) | **AC season ends (June)** | Rest of year |
|---|---|---|---|---|
| Next day | 19.3% (vs 20.2%) | 18.7% (vs 19.8%) | 20.2% (vs 20.7%) | 19.4% (vs 20.4%) |
| Next 7 days | 13.3% (vs 14.4%) | 13.5% (vs 14.3%) | 14.6% (vs 14.6%) | 13.0% (vs 14.3%) |
| Next 30 days | 12.3% (vs 12.6%) | 14.4% (vs 14.8%) | **17.6% (vs 16.8%)** | 10.4% (vs 10.7%) |

(First number = WattWise, in brackets = simple method. Range coverage drops to 69% for the
30-day forecast in June.)

**What this shows:**
- Over most of the year the model copes with Pune-like levels and seasons about as well as with London.
  This is expected: it predicts the change from the home's own recent average, so the usage level
  doesn't matter much.
- **Weak spot: when the AC season ends (June).** The 30-day forecast gets *worse than the
  simple average*, and the ranges miss more often. The model has no idea what time of year it is or
  what the weather will do. It sees usage rising through May and carries that on, but in June the
  monsoon arrives and AC use stops.
- So for India the model needs a **season or temperature input** (month, or cooling degree days from
  a weather feed). This is future work, and it is a finding we didn't expect.

## 5. In the app: "Homes like yours" (on the monthly bill screen)

The user enters their bill units (1-12 bills), the month of the last bill and whether they have an AC.
The app finds the **5 closest simulated Pune homes** (same months, similar units, same AC answer),
scales them to the user's total, and shows:
- a **typical day** (watts by hour) for a home like theirs, for the month of their last bill and for their peak month
- a **12-month outlook**: units, MSEDCL bill, slab and kg CO2 for every month. Months they entered stay exactly as entered; the rest are marked "homes like yours (simulated)".

It is labelled on screen as based on simulated homes, a typical picture rather than a forecast from their own data.
(This replaced an earlier "demo mode" that let you pick a simulated home, which made the site feel unfinished.)

### How well does it guess the months you didn't enter? (simulated homes only)

Leave one simulated home out, give the matcher 1, 3 or 6 of its bills, guess the other months.
k = 5 fixed before running. WAPE, lower is better.

| Bills given | Homes like yours (AC answer used) | Homes like yours (AC unknown) | Flat (same as your bills) | Average Pune season |
|---|---|---|---|---|
| 1 | 4.1% | 8.5% | 13.6% | 9.1% |
| 3 | 2.9% | 6.1% | 13.5% | 8.8% |
| 6 | 2.7% | 5.6% | 12.9% | 8.7% |

**Be careful with these numbers. They are flattering by construction.** Every simulated home's season
comes from one of only two Pune templates (AC or no AC), so once the matcher knows the AC answer it
mostly just recovers the template. Real Pune homes vary far more (water heaters, family size, work-from-home,
the monsoon). What the test does show:
- the code works, and the months you didn't enter follow a Pune-like season instead of being a flat guess
- the AC question matters: it halves the error
- **it says nothing about the error on real homes.** Do not quote 4% anywhere as an accuracy figure.

## 6. What we can and cannot claim

Can say:
- "We tested on 146 further unseen London homes; errors matched cross-validation."
- "'Homes like yours' shows a typical Pune-like day and year for homes with similar bills, based on simulated homes."
- "On LCL-derived simulated Pune homes, calibrated to published Prayas averages (12/12 checks),
  the forecast held up except at the end of the AC season, which shows it needs a season input."

Cannot say:
- that the model is accurate on Indian homes (no real Indian daily data yet)
- that the simulated homes *are* Pune homes. The day-to-day randomness is still London's.
  Power cuts, inverters, water pumps, festivals and monsoon behaviour are not in it.

## 7. Files and how to run

```bash
python pune_sim/make_pune_sim.py     # builds data/pune_sim_daily.csv (needs data/LCL_2013.csv), ~15 s
python pune_sim/check_pune_sim.py    # calibration table + figures/pune_sim_*.png
python pune_sim/stress_test_pune.py  # stress test table, ~1 min
python pune_sim/check_like_yours.py  # matching check above, ~1 min
python cli.py like --units 140 150 210 --last-month 4 --ac yes
```
API: `POST /homes-like-yours` (see the root `README.md`, "API calls"). **The frontend must show `data_label` on screen.**

| File | What |
|---|---|
| `pune_targets.json` | Every Pune number (with source) and every assumption |
| `make_pune_sim.py` | Builds the simulated homes |
| `check_pune_sim.py` | Calibration check + figures |
| `stress_test_pune.py` | Runs the saved models on both versions |
| `check_like_yours.py` | Matching check for "homes like yours" |
| `out/calibration_check.csv`, `out/stress_test.csv`, `out/like_yours_check.csv` | Results above |
| `out/homes.csv` | One row per simulated home: source LCL id, AC yes/no, level |
| `out/london_source_daily.csv` | The same homes before the change |
| `out/profiles.csv` | Average half-hour watts by month (simulated and London) |
| `../data/pune_sim_daily.csv` | The simulated homes, one row per home per day, `is_simulated = 1` |
| `../data/pune_sim_profiles.csv` | Each simulated home's typical day (watts by hour) per month |
| `../similar_homes.py` | The matching code used by the app |

## 8. Source

Prayas (Energy Group), Pune, "Insights from smart metering data" articles: minute-level smart meters
in about 115 homes (Pune city, Pune district, Aurangabad, Kanpur rural, Gonda), Jan 2018 - Jun 2020.
- https://energy.prayaspune.org/electricity-consumption-patterns
- https://energy.prayaspune.org/electricity-load-patterns
- https://energy.prayaspune.org/our-work/article-and-blog/temperature-and-electricity-consumption-patterns

(accessed 27 Oct 2026). Raw data is not public on these pages. Their eMARC dashboards are at
emarc.watchyourpower.org. Asking Prayas for student access to the raw data is the best next step
for a real Indian test.
