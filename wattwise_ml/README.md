# WattWise ML service

This README explains WattWise from the **machine learning** side: the data, the models, how they were trained and tested, the results, and the bill, carbon and tip logic around them.

It is written to be read on its own. The website and the Node backend are covered only as far as the ML side needs them (section 8). For the full picture: system, backend and every API call in the [root README](../README.md); the website in [`../wattwise_app/README.md`](../wattwise_app/README.md). How to install and run: [`../LAUNCH.md`](../LAUNCH.md) (Windows and Mac commands).

---

## 1. What this part does

| Input | Output | ML? |
|---|---|---|
| 7-28 days of daily kWh (or daily meter readings) | Forecast for **tomorrow**, the **next 7 days** and the **next 30 days**, each with an 80% likely range; next month's bill and carbon; one tip | **Yes** |
| Units from 1-12 monthly bills | Exact MSEDCL bill slab by slab, carbon, value of each unit saved | No (exact maths) |
| Monthly bills + AC yes/no | "Homes like yours": 12-month outlook and typical day from the 5 closest **simulated** Pune homes | No (nearest-neighbour matching) |

Rule followed throughout: **only forecasts tested on homes the model had never seen are shown.** Anything else is labelled as simple arithmetic or an estimate.

---

## 2. Tech stack

| Tool | Used for |
|---|---|
| Python **3.11** (exactly; TensorFlow needs it) | Everything |
| **XGBoost** 3.2 | Main forecasting model (all three horizons) |
| **TensorFlow / Keras** 2.21 / 3.15 | Small LSTM for tomorrow's forecast |
| **scikit-learn** 1.9 | GroupKFold cross-validation, train/validation splits, scaling, error metrics |
| **pandas**, **NumPy** | Data cleaning and features |
| **FastAPI** + **Uvicorn** | The web service on port 8000 |
| **joblib** | Saving and loading trained models |
| **pytest** | 34 automated tests |
| matplotlib | Figures for the simulated Pune data |

Versions are pinned in `requirements.txt`, because the saved models only load on the same library versions.

---

## 3. Data

| Dataset | What it is | Used for |
|---|---|---|
| **Low Carbon London (LCL), 2013** | Real half-hourly smart-meter readings from 4,443 London homes | Training and testing the forecaster. 150 homes picked at random (seed 42); 148 have enough history, giving 52,471 complete days |
| **Simulated Pune homes** | 146 *other* LCL homes, kept as they behave day to day but reshaped to published Pune averages (Prayas Energy Group): usage level, daily shape, AC summer | "Homes like yours" and a stress test. **Labelled simulated everywhere** (`is_simulated = 1`) |
| REFIT | 20 UK homes with appliances metered separately | Only the bridge test (a negative result, see section 7) |

No open Indian dataset of daily household readings at this size was available, which is why London data is used for training.

The raw LCL file (~600 MB) is **not** included. The trained models are, so nothing needs downloading to run the app. Links and sources for every number: `DATASETS.md`.

**Cleaning** (`load_real_lcl.py`, `preprocessing.py`):
- LCL timestamps mark the *end* of each half hour, so every timestamp is moved back 30 minutes. Otherwise the last half hour of each day lands in the next day.
- Only complete days are kept (all 48 readings). Days under 0.2 kWh (empty house or meter off) are dropped. Half-hour values above 10 kWh are treated as meter glitches.
- Each day gets: total kWh, evening kWh (6-10 pm), daytime kWh (9 am-5 pm) and night load (average power 1-5 am, the always-on load).

---

## 4. The forecasting model

### 4.1 Inputs (features)
Built by **one** function, `daily_feature_row()`, used both in training and in the live app, so the model always sees inputs made the same way:

| Feature | Meaning |
|---|---|
| `lag_1` … `lag_7` | kWh 1 to 7 days ago |
| `mean_7`, `std_7`, `min_7`, `max_7` | Average, spread, lowest and highest of the last 7 days |
| `mean_14`, `mean_28` | 2-week and 4-week averages |
| `trend_7_vs_28` | Last week ÷ last 4 weeks (going up or down) |
| `history_days` | How many days were given (7-28), so one model serves new and old users |
| `evening_share` | Share of use between 6 pm and 10 pm |
| `baseload_kw` | Always-on load (night average) |
| `dow`, `is_weekend` | Day of the week of the first forecast day |

Home size is **not** a model input. The London data has no home sizes, so the 1BHK…Villa groups are just usage quartiles used for comparison.

### 4.2 "Predict the change", not the raw number
Homes differ hugely in size but change in similar ways (weekends, cold spells, trends). So instead of predicting kWh directly, XGBoost predicts the **ratio** of the future average to the home's own 7-day average (as a log), and the app multiplies back:

```
forecast = (average of last 7 days) × exp(XGBoost output)
```

Predicting raw kWh lost to the simple 7-day average at 7 and 30 days. Predicting the change won at every horizon. This lives in `ratio_model.py` (`RatioModel`). A trust weight (0 = plain average, 1 = full ML) is picked from 5 fixed values on held-back *training* homes; all three final models picked 1.

XGBoost settings: tree depth 4, learning rate 0.05, up to 600 trees, early stopping after 30 rounds without improvement.

### 4.3 Three horizons
| Horizon | Model |
|---|---|
| Tomorrow | XGBoost **blended with an LSTM** (32 units → dense 16 → 1, reads the last 7 days as a sequence). Blend weights come from each model's error on held-back training homes: about 50/50 (0.497 XGBoost, 0.503 LSTM). Blending mainly reduces the big misses |
| Next 7 days | XGBoost (predicts the average kWh/day, × 7 for the total) |
| Next 30 days | XGBoost (average kWh/day, × 30). Next month's bill is based on this |

### 4.4 Likely range (80%)
Every forecast comes with a low-high range. In testing, the 10th and 90th percentiles of *actual ÷ forecast* were recorded. The app multiplies the forecast by those two numbers. For tomorrow the range is about 0.72 to 1.31 × the forecast; for 30 days about 0.82 to 1.23 ×. A history length gets its own range only if it had at least 300 test cases; others use the nearest one.

---

## 5. How it was tested

**5-fold GroupKFold, grouped by home.** The 148 homes are split into 5 groups of about 30. Each group is tested once by models trained on the other 4. So every error is measured on homes the model **never saw**, which is exactly a new user's situation. All model choices (blend weights, trust weight, early stopping) are made on an inner split of the *training* homes, never the test homes.

**Error measure: WAPE** = total absolute error ÷ total actual use × 100. Lower is better.

**Baselines** scored on exactly the same test rows: "same as yesterday", "average of the last 7 days", "average of all history".

**A further 146 London homes**, never used for any decision, were checked afterwards with the saved models.

---

## 6. Results

| Forecast | WattWise | Best simple method (7-day average) | Extra 146 homes (WattWise vs average) |
|---|---|---|---|
| Tomorrow | **18.6%** | 19.8% | 18.4% vs 19.4% |
| Next 7 days | **13.2%** | 13.5% | 13.1% vs 13.4% |
| Next 30 days | **14.3%** | 14.8% | 13.2% vs 13.5% |

- About 6% better than the baseline for tomorrow (relative), about 3-4% for 7 and 30 days. Real but modest: one home's use is very noisy, and its recent average is already a strong guess.
- The 80% range held the real value 77-78% of the time on the extra 146 homes.
- **Tip picker (LinUCB):** 95% of the best possible reward in simulation, against 73% for always saying "reduce", 70% for a hand-written rule and 36% for random.
- **Stress test on simulated Pune homes:** the forecaster copes for most of the year, but for 30 days around June, when the AC season ends, it does worse than the simple average (17.6% vs 16.8%). The model has no season or weather input.
- **Homes like yours:** 4.1% error vs 13.6% for a flat guess, but this is flattering by construction (only two season templates) and is never quoted as accuracy.

Every number comes from `models/results.json` and `models/cv_summary.csv`. Full detail on the simulated homes: `pune_sim/PUNE_SIM.md`.

---

## 7. The rest of the logic

**Tip picker** (`bandit_recommender.py`, `tips.py`). A contextual bandit (**LinUCB**) chooses the *type* of tip from 4: use less overall, move evening use to daytime, check always-on appliances, or say nothing (for homes already below their peers, because telling them to cut can backfire). It looks at 6 numbers: usage vs similar homes, evening share, night load vs similar homes, weekend, smart meter, and a constant. It was trained offline on a simulated reward built from real LCL peer gaps (bill rupees saved plus evening kWh removed, capped at 10% of the day). `tips.py` then fills in the details: which appliance (if the user listed them), kWh, rupees saved on the real slabs, kg CO2.

**Bill** (`tariff.py` + `tariff_config.json`). MSEDCL residential FY 2026-27 **telescopic** slabs: each rate applies only to the units inside its slab (Rs 4.32 up to 100, 9.40 to 300, 12.51 to 500, 13.97 above), plus wheeling Rs 1.20 per unit and a Rs 130 fixed charge. Smart / ToD-meter homes get Rs 0.80 off per unit used 9 am-5 pm. Electricity duty and the fuel adjustment charge are not included. Rates live in the JSON file, so updating them needs no code change.

**Carbon** (`carbon.py` + `carbon_config.json`). kWh × 0.727 kg CO2 (CEA grid average, 2023-24). Also the "homes that follow tips use 4-7% less" estimate, which comes from published studies, not WattWise users.

**Appliance split** (`appliance_estimator.py` + `appliance_catalog.json`). Optional. Typical energy use (or the BEE star-label figure for AC, fridge and ceiling fan) × the user's hours, then scaled so the total matches the meter. It is an estimate, not ML and not measured. A REFIT check found a plain watts × hours estimate can be far off (fridge 320-760% too high), which is why it is always labelled.

**Homes like yours** (`similar_homes.py`). k-nearest neighbours (k = 5, fixed before testing). Distance = average gap in log units between the user's bills and each simulated home's units for the same calendar months, so both size and season shape count. With the AC answer, AC homes are matched only with AC homes and non-AC with non-AC. The 5 homes are scaled to the user's level and averaged.

**What was tried and dropped** (full list in `DEVELOPMENT_LOG.md`): an appliance "bridge" that borrowed REFIT appliance splits for London homes by matching load shapes (7.9% better than a simple baseline, below the 10% bar set in advance, so not used); a weekly forecast (only tied with "same as last week"); training on synthetic data (looked great, meant nothing).

---

## 8. How the ML connects to the website and backend

The models never talk to the browser directly. The chain is:

```
React website  ──►  Node server, port 5050 (wattwise_app/server.js)  ──►  this service, port 8000
(wattwise_app/src)   one file: serves the website,                       api.py  → checks the request
                     forwards 5 /api routes, no maths                     engine.py → does all the work
```

- **`api.py` is the front door.** It is a thin FastAPI layer: it checks each request body (types, limits, list lengths) with Pydantic models, passes it to `engine.py`, and turns any input problem into HTTP 422 with a plain-English `detail`. The website shows that message under the form as-is.
- **`engine.py` is where everything happens.** Each route calls one function:

  | Route | Engine function | Website screen |
  |---|---|---|
  | `GET /health` | (none, returns `{"status": "ok"}`) | "Model online" badge, checked every 15 s |
  | `GET /meta` | `meta()` | Appliance dropdown and star-rating boxes |
  | `POST /bill` | `bill_screen()` | Bill tab |
  | `POST /homes-like-yours` | `homes_like_yours()` | Bill tab, sent together with `/bill` |
  | `POST /forecast/daily` | `forecast_daily()` | Daily forecast tab |

- **What the website sends to the forecast:** `daily_kwh` (7-28 values, oldest first) or `daily_meter_readings` (8-29), `last_reading_date`, `home_type`, `has_smart_meter`, and optionally `appliances`. `home_type` only picks the comparison group; it is not a model input.
- **What the website relies on in the reply:** the three forecasts with `range_80pct`, the tip in `recommendation`, `bill`, `carbon`, `peer_group`, `appliance_breakdown`, and the labels the UI must always show (`data_label` for simulated homes, the estimate notes). Renaming or removing a reply field breaks the website, so change the frontend at the same time.
- **Loading:** models in `models/` are loaded once, on first use, and kept in memory. TensorFlow loads only when the first forecast arrives, so that one takes a few seconds; the Node server waits up to 60 s.
- **Ports and settings:** this service runs on 8000 (`python -m uvicorn api:app --port 8000`). The Node server finds it through its `ML_URL` setting (default `http://localhost:8000`). If this service is down, the website shows "Model offline" and reconnects by itself.

---

## 9. Most important files and functions

**Used by the running app**

| File | Key functions / contents |
|---|---|
| `api.py` | The web front door: Pydantic request models (`BillRequest`, `DailyRequest`, `LikeYoursRequest`, `Appliance`), `readable_422` (one readable error message), `_run` (turns `InputError` into HTTP 422), and the 5 one-line route functions |
| `engine.py` | All app logic, used by both `api.py` and `cli.py`. **`forecast_daily(req)`**: checks input, builds features, runs XGBoost + LSTM, adds ranges, bill, carbon, tip. **`bill_screen(req)`**: bill and carbon for monthly bills. **`homes_like_yours(req)`**: simulated-homes outlook. **`meta()`**: dropdown values. Helpers: `_load` (loads models once and caches them; TensorFlow only loads when a forecast is needed), `_series` (kWh list or meter readings → daily kWh), `_range`, `_context_and_tip`, `_appliances`. `InputError` = bad user input → HTTP 422 |
| `preprocessing.py` | **`daily_feature_row()`**: the 19 model inputs, shared by training and the app. `daily_aggregate()`, `assign_peer_bands()`, `peer_stats()`, `make_daily_rows()` (training rows with random 7/14/21/28-day histories) |
| `ratio_model.py` | **`RatioModel`**: the "predict the change" XGBoost wrapper (`fit`, `predict`). The saved models are instances of this class |
| `bandit_recommender.py` | **`LinUCB`** (`select`, `update`, `expected`), `build_context()`, `ACTIONS`; plus the offline training and evaluation used by `train.py` |
| `tips.py` | **`build_tip()`**: turns the chosen tip type into a title, message, kWh, Rs and kg CO2 |
| `tariff.py` | `monthly_bill()`, `slab_breakdown()`, `current_slab()`, `marginal_rate()`, `saving_from_cut()`, `saving_from_shift()`, `bill_summary()` |
| `carbon.py` | `kg_co2()`, `expected_savings()`, `summary()` |
| `appliance_estimator.py` | **`estimate()`**: appliance split scaled to the daily total. `per_hour_kwh()`: label watts → BEE label kWh → star rating → typical value |
| `similar_homes.py` | `match()` (5 nearest simulated homes), `outlook()` (12 months), `typical_day()`, `bill_months()` |
| `models/` | `daily_bundle.joblib` (XGBoost models, scaler, blend weights, ranges), `lstm_tomorrow.keras`, `bandit.joblib`, `peer_stats.json`, `results.json` and the test result CSVs |
| `data/pune_sim_daily.csv`, `data/pune_sim_profiles.csv` | The simulated Pune homes and their typical days |
| `*_config.json`, `appliance_catalog.json` | Tariff, carbon factor, appliance values, each with its source |

**Training, testing and research** (not needed to run the app)

| File | What it does |
|---|---|
| `train.py` | Retrains everything: `python train.py --real` (needs the LCL file in `data/`), or `--synthetic` for a quick check that the pipeline runs |
| `forecasting_model.py` | `run_cv()` (5-fold test on unseen homes), `fit_tomorrow()` (XGBoost + LSTM blend), `build_lstm()`, `range_table()` (80% ranges), `daily_baselines()`, `train_all()` |
| `load_real_lcl.py` | Reads the LCL file, picks the homes, fixes timestamps |
| `synthetic_data_generator.py` | Fake data for `train.py --synthetic` only |
| `pune_sim/` | `make_pune_sim.py` (builds the simulated homes), `check_pune_sim.py` (12 calibration checks), `stress_test_pune.py`, `check_like_yours.py`, `PUNE_SIM.md` |
| `refit_validation.py` | The REFIT check of the appliance estimate |
| `cli.py` | Run without a server: `python cli.py demo`, `python cli.py bill --units 280 295 306`, `python cli.py daily --kwh 9.1 8.7 10.2 9.8 11.0 10.5 9.9` |
| `tests/test_wattwise.py` | 34 tests: tariff, carbon, appliance estimate, engine, API, CLI, REFIT script, simulated Pune data, homes like yours, star ratings |
| `examples/` | Sample requests (used by the tests and `cli.py demo`) and matching sample responses |

---

## 10. Commands

Run from this folder with the virtual environment active (setup in `../LAUNCH.md`):

```bash
python -m pytest -q tests                  # 34 tests
python -m uvicorn api:app --port 8000      # web service -> http://localhost:8000/docs
python cli.py demo                         # all three screens on sample homes, no server
python train.py --real                     # retrain (needs data/LCL_2013_kWh.csv.zip, ~10-15 min)
```

## 11. Limits to state honestly
- The forecaster has **never seen an Indian home**. It learned from London, 2013.
- No season or weather input, hence the June weakness.
- The tip picker's 95% is on a **simulated** reward. It shows the method can learn, not that people save money.
- Simulated Pune homes are **simulated**. They never appear in the main results.
- The 4-7% saving and the appliance split are estimates.

## Other docs in this folder
- `DEVELOPMENT_LOG.md`: everything tried, what failed and what changed (useful before the viva)
- `DATASETS.md`: dataset links and the source of every number in the app
- `pune_sim/PUNE_SIM.md`: how the simulated Pune homes were built and checked
- `openapi.json`: machine-readable API schema
