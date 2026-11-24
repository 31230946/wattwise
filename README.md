# WattWise: system, backend and API

WattWise is a web app for households in Maharashtra. From the units on recent MSEDCL bills, or a week or more of daily meter readings, it shows:

- the bill, worked out exactly on the MSEDCL telescopic slabs
- the carbon footprint of that electricity
- a machine-learning forecast for tomorrow, the next 7 days and the next 30 days, each with a likely range
- one practical tip, with the rupees and kg of CO2 it would save
- "Homes like yours": a typical year and a typical day for similar homes (based on **simulated** Pune homes, always labelled)

B.Tech Computer Engineering major project (BTECCE23706), Vishwakarma University, Pune, 2026-27.

This README explains the project from the **system and backend** side: the three services, how they talk to each other, and every API call. It is written to be read on its own. The website and the ML models are described here only as far as the backend needs; each has its own full README:

| Part | README | Covers |
|---|---|---|
| System + backend + API | this file | Node server, ML web service, all API calls between them |
| Frontend | [`wattwise_app/README.md`](wattwise_app/README.md) | The React website: pages, components, what it sends and shows |
| ML | [`wattwise_ml/README.md`](wattwise_ml/README.md) | Data, models, training, testing, results, tips, bill and carbon maths |

To install and run everything, see [`LAUNCH.md`](LAUNCH.md) (Windows and Mac commands).

### Who does what: one file per job

| File | Job |
|---|---|
| `wattwise_app/server.js` | **The whole Node backend, in one file.** Serves the website to the browser and forwards the 5 API calls to the ML service. Does no calculations itself |
| `wattwise_ml/api.py` | **The ML service's front door.** Receives each request, checks it, returns the result or a readable error. Does no calculations itself |
| `wattwise_ml/engine.py` | **All the actual app logic**: forecast, bill, carbon, tip, homes like yours. Called by `api.py` (and by the offline tool `cli.py`) |

Browser → `server.js` → `api.py` → `engine.py` → back the same way.

---

## 1. The three services

```
┌────────────────────┐   fetch("/api/...")   ┌──────────────────────────┐   HTTP (JSON)   ┌──────────────────────────┐
│  Browser           │ ────────────────────► │  Node + Express server   │ ──────────────► │  ML service (FastAPI)    │
│  React website     │ ◄──────────────────── │  wattwise_app/server.js  │ ◄────────────── │  wattwise_ml/api.py      │
│  (wattwise_app/src)│        JSON           │  port 5050               │      JSON       │  port 8000               │
└────────────────────┘                       └──────────────────────────┘                 └──────────────────────────┘
                                               serves the built website                     forecasts, bill, carbon,
                                               + forwards 5 API routes                      tips, homes like yours
```

| Service | Folder | Tech | Port | Job |
|---|---|---|---|---|
| Frontend | `wattwise_app/src` | React 18, Vite 5, Recharts | (served by the Node server) | Forms, results, charts |
| Backend | `wattwise_app/server.js` | Node.js 18+, Express 4 | 5050 | Serves the website and forwards API calls |
| ML service | `wattwise_ml` | Python 3.11, FastAPI, Uvicorn, XGBoost, TensorFlow/Keras, scikit-learn, pandas | 8000 | All calculations and models |

You open **http://localhost:5050**. The browser never talks to port 8000 directly. Only the Node server does.

**What the backend needs to know about the other two parts**
- *Frontend:* a React site built by Vite into `wattwise_app/dist/`. The Node server just hands those files to the browser. The site calls only `/api/...` on the same address, checks inputs before sending, and shows the ML service's `detail` message when something is wrong. It checks `/api/health` every 15 s to show a "Model online / offline" badge.
- *ML:* `engine.py` uses saved models in `wattwise_ml/models/` (XGBoost and a small LSTM, trained on real London smart-meter data) plus simulated Pune homes in `wattwise_ml/data/`. Nothing is trained while the app runs. The first forecast after start-up takes a few seconds because TensorFlow loads then, which is why the Node server waits up to 60 s.

**Why a Node server in the middle?**
- The website and the API come from the same address, so the browser needs no CORS setup.
- Only 5 approved routes are passed through. Anything else on the ML service (for example its `/docs` page) is not exposed to the website.
- If the ML service is down, the server sends back one clear message instead of a browser network error.
- It is the natural place to add user accounts and a database later.

---

## 2. Backend: the Node server (`wattwise_app/server.js`)

A single file of about 60 lines.

**What it does, in order:**
1. Reads two settings from environment variables: `PORT` (default `5050`) and `ML_URL` (default `http://localhost:8000`).
2. Accepts JSON request bodies up to 100 kB.
3. For each of the 5 allowed routes, registers a handler that forwards the request to the ML service and sends back the ML service's status code and JSON unchanged:

   | Website calls | Forwarded to |
   |---|---|
   | `GET /api/health` | `GET /health` |
   | `GET /api/meta` | `GET /meta` |
   | `POST /api/bill` | `POST /bill` |
   | `POST /api/forecast/daily` | `POST /forecast/daily` |
   | `POST /api/homes-like-yours` | `POST /homes-like-yours` |

4. If the ML service can't be reached, or takes longer than 60 seconds, it replies `503` with `{"detail": "The WattWise ML service is not reachable at ..."}`.
5. Any other `/api/...` path gets `404 {"detail": "Unknown API route"}`.
6. Serves the built website from `dist/`. Every other path returns `dist/index.html`, so page links keep working on refresh. If `dist/` doesn't exist yet, it replies with a message to run `npm run build`.

**Key parts of `server.js`:**

| Part | What it is |
|---|---|
| `ROUTES` | The list of 5 allowed routes and where each one goes on the ML service |
| the `for` loop over `ROUTES` | Creates one Express handler per route. It uses the built-in `fetch` to call the ML service with a 60 s timeout (`AbortSignal.timeout`) |
| `app.all("/api/*")` | The 404 for unknown API routes |
| `express.static(DIST)` + `app.get("*")` | Serves the website and the `index.html` fallback |

**npm scripts** (`wattwise_app/package.json`): `npm run build` builds the website into `dist/`, `npm start` runs `server.js`, and `npm run dev` runs a live-reloading copy of the website on port 5173 that sends `/api` calls to port 5050 (set in `vite.config.js`).

---

## 3. The ML web service (`wattwise_ml/api.py`)

A thin FastAPI layer over `engine.py`, which holds all the actual logic.

**How a request is handled:**
1. FastAPI checks the JSON body against a **Pydantic** model (`BillRequest`, `DailyRequest`, `LikeYoursRequest`). Wrong types, out-of-range values or a list that is too short are rejected before any code runs.
2. The body is turned into a plain dict and passed to the matching function in `engine.py`.
3. `engine.py` raises `InputError` for problems the schema can't catch (for example meter readings that go down). `_run()` turns that into HTTP 422.
4. `readable_422()` makes sure **every** 422 has a plain-English `detail` string, so the website can show it as-is. The raw error list is kept in `errors` for debugging.

**Key parts of `api.py`:**

| Part | What it is |
|---|---|
| `Appliance`, `Common`, `BillRequest`, `LikeYoursRequest`, `DailyRequest` | Pydantic models: the allowed fields, their types and limits |
| `readable_422` | Exception handler that turns validation errors into one readable message |
| `_run(fn, payload)` | Calls an engine function and converts `InputError` to HTTP 422 |
| `health`, `meta`, `bill`, `forecast_daily`, `homes_like_yours` | The 5 route functions, one line each |
| `CORSMiddleware` | Only matters if a browser ever calls port 8000 directly (`ALLOWED_ORIGINS`). Normally unused because of the Node server. |

Interactive docs, with a "Try it out" button for every route: **http://localhost:8000/docs**. The same schema is saved in `wattwise_ml/openapi.json`.

---

## 4. Every API call

All requests and responses are JSON. Lists of values are always **oldest first**. Bad input returns **422** with a readable `detail`.

### 4.1 `GET /api/health`
Returns `{"status": "ok"}`. The website calls it on load and then every 15 seconds to show the "Model online / offline" badge.

### 4.2 `GET /api/meta`
Called once when the website loads. Returns the values the forms need:
- `appliance_types`: appliance keys and labels for the dropdown (for example `"ac_1_5_ton": "AC (1.5 ton)"`)
- `appliance_star_types`: which appliances accept a BEE star rating (AC, fridge, ceiling fan)
- `appliance_when_options`, `home_types`, `tariff` (slabs and the ToD rebate), `carbon_factor`, `peer_defaults`, `limits`

### 4.3 `POST /api/bill` (no ML)

```json
{"monthly_units": [126, 132, 129], "has_smart_meter": false}
```
| Field | Required | Meaning |
|---|---|---|
| `monthly_units` | yes | Units from 1 to 12 recent bills |
| `has_smart_meter` | no | `true` if billed on a smart / time-of-day meter |

Main parts of the reply:
| Field | Meaning |
|---|---|
| `last_month.units`, `last_month.bill.estimated_bill_rs` | Latest bill in rupees (energy + wheeling + fixed charge) |
| `last_month.bill.breakdown.slabs[]` | Slab table: slab, units in it, rate, amount |
| `last_month.carbon.kg_co2` | Carbon for that bill |
| `last_month.expected_savings_if_tips_followed` | The "homes that follow tips use 4-7% less" line (an estimate from other studies) |
| `slab_status` | Current slab and `each_unit_cut_saves_rs` |
| `history[]` | Units, bill and kg CO2 for every bill entered |
| `simple_projection` | Simple arithmetic only, marked `is_ml_forecast: false` |

### 4.4 `POST /api/homes-like-yours` (no ML, simulated data)

```json
{"monthly_units": [126, 132, 129], "last_bill_month": 9, "has_ac": true, "has_smart_meter": false}
```
| Field | Required | Meaning |
|---|---|---|
| `monthly_units` | yes | Same bills as `/bill` |
| `last_bill_month` | no | Calendar month (1-12) of the latest bill. Default: last month |
| `has_ac` | no | `true` / `false`. The website always sends it. If an API caller leaves it out, all simulated homes are searched |
| `has_smart_meter` | no | As above |

Main parts of the reply:
| Field | Meaning |
|---|---|
| `data_label` | "Based on SIMULATED Pune homes..." **Must be shown on screen** |
| `matched` | `homes` (5), `with_ac`, `how_close_pct` |
| `year_outlook[]` | 12 rows: month, units, bill, slab, kg CO2, and `source` (`"your bill"` or `"homes like yours (simulated)"`) |
| `year_summary` | Yearly units, bill and carbon, and the highest month |
| `typical_day`, `typical_day_peak_month` | 24 hourly watts, peak hour, night load, evening share |
| `inputs_defaulted` | What was assumed; can include a warning if the bills are outside the simulated range |

### 4.5 `POST /api/forecast/daily` (ML)

```json
{
  "daily_kwh": [5.2, 5.6, 6.1, 5.4, 5.0, 6.8, 6.5],
  "last_reading_date": "2026-11-23",
  "home_type": "2bhk",
  "has_smart_meter": false,
  "appliances": [{"type": "ceiling_fan", "count": 3, "hours_per_day": 9, "when": "evening", "star_rating": 3}]
}
```
| Field | Required | Meaning |
|---|---|---|
| `daily_kwh` | one of these two | 7 to 28 values: kWh used each day |
| `daily_meter_readings` | one of these two | 8 to 29 meter readings, one per day. The differences give each day's kWh |
| `last_reading_date` | no | Date of the last value (`YYYY-MM-DD`). Default: yesterday |
| `home_type` | no | `1bhk`, `2bhk`, `3bhk` or `villa`. Only picks the comparison group; it does not change the forecast |
| `has_smart_meter` | no | Changes whether shifting use to daytime saves money |
| `appliances` | no | Optional list. Each item: `type`, `count`, `hours_per_day` (empty for `all_day`), `when`, and optionally `star_rating` (1-5), `rated_watts` or `label_kwh_per_year` |
| `peer_mean_kwh`, `evening_share`, `baseload_kw` | no | Only if better numbers are known. Otherwise defaults are used |

Main parts of the reply:
| Field | Meaning |
|---|---|
| `forecast.next_day`, `.next_7_days`, `.next_30_days` | `kwh`, `range_80pct` (likely low and high), `kg_co2`, `period` |
| `bill`, `carbon` | Next month's bill (slab by slab) and carbon, based on the 30-day forecast |
| `recommendation` | The tip: `title`, `message`, `saving_rs_per_month`, `saving_kg_co2_per_month`, `action`, and the tip picker's score for each tip type |
| `peer_group` | How the home compares with similar homes (`you_vs_peers_pct`) |
| `appliance_breakdown` | Only if appliances were sent: estimated kWh and share for each one. Always labelled as an estimate |
| `model_details.next_day` | The XGBoost and LSTM parts of tomorrow's forecast and their blend weights |
| `input_summary` | Days used, forecast start date, `low_history` (fewer than 14 days) |
| `inputs_defaulted`, `notes` | What was assumed, and footnotes |

Full example requests and replies: `wattwise_ml/examples/sample_requests/` and `wattwise_ml/examples/sample_responses/`.

---

## 5. What happens when you press a button

**"Calculate" on the bill screen**
1. The browser checks the inputs (at least one bill, numbers above 0, AC answered).
2. It sends `POST /api/bill` and `POST /api/homes-like-yours` **at the same time**.
3. The Node server forwards both to the ML service.
4. `engine.bill_screen()` does the slab and carbon maths. `engine.homes_like_yours()` finds the 5 closest simulated Pune homes.
5. The website shows the bill first. If "Homes like yours" fails on its own, the bill still shows with a small notice.

**"Forecast" on the daily screen**
1. The browser checks there are at least 7 days of kWh (or 8 meter readings).
2. It sends `POST /api/forecast/daily`.
3. `engine.forecast_daily()` builds the input features, runs the XGBoost models and the LSTM, adds the likely ranges, works out the bill and carbon, and asks the tip picker for a tip.
4. The first forecast after the ML service starts takes a few seconds while TensorFlow loads. Later ones are quick.

---

## 6. Running it

Full copy-paste commands for **Windows** and **Mac**, plus troubleshooting, are in [`LAUNCH.md`](LAUNCH.md). In short:

- Needs **Python 3.11** exactly (TensorFlow needs it) and **Node.js 18+**.
- Once: in `wattwise_ml`, create a venv and `pip install -r requirements.txt`. In `wattwise_app`, `npm install` and `npm run build`.
- Every time, two terminals: `python -m uvicorn api:app --port 8000` in `wattwise_ml` (venv active), and `npm start` in `wattwise_app`.
- Open **http://localhost:5050**.

---

## 7. Folder map

| Path | What |
|---|---|
| `wattwise_app/` | Website: React source (`src/`), Node server (`server.js`), built site (`dist/`) |
| `wattwise_ml/` | ML service: API, models, training, tests, simulated Pune homes, docs |
| `LAUNCH.md` | Step-by-step commands for Windows and Mac, handy commands, troubleshooting |

## 8. Possible next steps on the backend
- User accounts and a SQL database in `server.js`, so readings and tips can be saved.
- A `POST /feedback` route, so the tip picker can learn from real outcomes: store each tip shown with its context, then use `bandit_recommender.reward_from_outcome()` and `LinUCB.update()` when the next week's readings arrive.
