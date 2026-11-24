# WattWise frontend (React website)

This README explains WattWise from the **frontend** side: what the user sees, how the website is built, what it sends to the backend and how it shows the results.

It is written to be read on its own. The backend and the ML models are covered only as far as the frontend needs them. For the full picture: system, backend and every API call in the [root README](../README.md); models and maths in [`../wattwise_ml/README.md`](../wattwise_ml/README.md). How to install and run: [`../LAUNCH.md`](../LAUNCH.md) (Windows and Mac commands).

---

## 1. What the website does

Three tabs, switched with the address bar hash (`#bill`, `#daily`, `#how`):

| Tab | User enters | User sees | ML? |
|---|---|---|---|
| **Your bill** (`#bill`) | Month of the latest bill, units from 1 to 12 bills, AC yes/no, smart meter yes/no | Latest bill in rupees, current slab, "each unit you cut saves Rs X", carbon, slab-by-slab table, bill history chart, the 4-7% savings line, and **Homes like yours** (simulated): a 12-month outlook and a typical day | No |
| **Daily forecast** (`#daily`) | 7-28 days of kWh **or** 8-29 meter readings, date of the last value, home size, smart meter yes/no, and optionally an appliance list (in an "Advanced" dropdown) | Tomorrow, next 7 days and next 30 days, each with a likely range; a chart of the past days plus tomorrow; one tip with Rs and kg CO2 saved; next month's bill and carbon; comparison with similar homes; appliance split (if given) | Yes |
| **How it works** (`#how`) | Nothing | What's real, what's estimated, limits and sources | No |

Both input tabs have a **"Try a sample home"** button that fills in sample values and runs them.

All three tabs stay loaded in the background, so typed inputs and results survive switching tabs.

---

## 2. Tech stack

| Tool | Used for |
|---|---|
| **React 18** | The user interface, built from function components and hooks (`useState`, `useEffect`) |
| **Vite 5** | Builds `src/` into plain HTML/JS/CSS in `dist/`; also runs a live-reload dev server |
| **Recharts 2** | All charts (bar charts, line chart, error bars for the likely range) |
| Plain CSS (`styles.css`) | Dark slate and cyan theme, layout grid, cards, works on phones |
| Google Fonts | Inter (text) and Outfit (headings). Without internet the site falls back to system fonts |

No router library and no state library: the tab comes from `window.location.hash`, and each page keeps its own state.

---

## 3. How it connects to everything else

```
React page ──► src/api.js ──fetch("/api/...")──► Node server :5050 (server.js) ──► ML service :8000
```

- The website only ever calls `/api/...` on the same address it was loaded from. It never calls the ML service directly.
- `src/api.js` has one function per backend route:

  | Function | Route | Called when |
  |---|---|---|
  | `api.health()` | `GET /api/health` | On load, then every 15 s (status badge) |
  | `api.meta()` | `GET /api/meta` | On load (appliance dropdown, which appliances take star ratings) |
  | `api.bill(body)` | `POST /api/bill` | "Calculate" on the bill tab |
  | `api.likeYours(body)` | `POST /api/homes-like-yours` | Same click, sent at the same time as `bill` |
  | `api.daily(body)` | `POST /api/forecast/daily` | "Forecast" on the daily tab |

- If a call fails, `api.js` throws an error carrying the backend's readable `detail` message, and the page shows it in a red box under the form.

**What sits behind `/api` (light version)**
- `wattwise_app/server.js` is the **whole backend in one file**. It serves this website from `dist/` and forwards the 5 `/api/...` calls to the Python ML service on port 8000. It does no calculations. If the ML service is not running, it answers `503` and the site shows the "Model offline" banner.
- The ML service (`wattwise_ml/`) does all the work: `api.py` receives and checks each request, `engine.py` does the maths and runs the models. It double-checks every input and rejects bad ones with HTTP `422` and a plain-English `detail`.
- The first forecast after the ML service starts takes a few seconds (TensorFlow loading). That is why the forecast button shows a spinner.

**What the website sends and which reply fields it uses**

All lists are **oldest first**.

| Call | Body the website sends | Reply fields it shows |
|---|---|---|
| `bill` | `monthly_units` (1-12 numbers), `has_smart_meter` | `last_month.bill` (rupees, `breakdown` for the slab table), `last_month.carbon.kg_co2`, `slab_status`, `history[]`, `last_month.expected_savings_if_tips_followed` |
| `likeYours` | same as `bill` + `last_bill_month` (1-12) + `has_ac` (`true`/`false`) | `data_label`, `matched`, `year_outlook[]` (each row's `source` decides solid or dashed bar), `year_summary`, `typical_day`, `typical_day_peak_month`, `inputs_defaulted` (warnings), `how_good_is_this` |
| `daily` | `daily_kwh` (7-28) **or** `daily_meter_readings` (8-29), `last_reading_date`, `home_type`, `has_smart_meter`, optional `appliances[]` | `forecast.next_day / next_7_days / next_30_days` (`kwh`, `range_80pct`, `kg_co2`), `recommendation` (the tip), `bill`, `carbon`, `peer_group`, `appliance_breakdown`, `model_details`, `input_summary.low_history`, `inputs_defaulted`, `notes` |
| `meta` | nothing | `appliance_types` (dropdown), `appliance_star_types` (which appliances get a star-rating box) |

**What the numbers mean, so the UI can explain them**
- **Forecasts** come from machine learning (XGBoost, plus a small LSTM for tomorrow) trained on real smart-meter data from London homes. They were tested only on homes the model had never seen.
- **Likely range** (`range_80pct`): in testing, the real value fell inside it 8 times out of 10.
- **Bill** is exact maths on the MSEDCL slab tariff (no ML). Electricity duty and the fuel adjustment charge are not included.
- **Carbon** = units × 0.727 kg CO2 (Indian grid average).
- **Tip** is chosen by a small learning algorithm (a contextual bandit) from 4 types, then filled in with rupees and kg CO2.
- **Homes like yours** comes from **simulated** Pune homes, not real Indian readings, which is why it is always labelled.
- **4-7% savings** and the **appliance split** are estimates, not measurements.

---

## 4. How it was implemented

**Inputs are checked twice.** Each page checks the obvious things first (numbers only, enough values, bills above 0, AC answered), so most mistakes are caught instantly. The ML service then checks everything again and its message is shown if anything is still wrong.

**Bill tab.** The bill and "Homes like yours" requests go out together with `Promise.allSettled`. The bill must succeed; if only "Homes like yours" fails, the bill still shows with a small notice. The month label above each bill box is worked out from the month of the latest bill.

**Daily tab.** Typed values are split on spaces, commas or new lines (`parseNumbers`). Meter readings are sent as they are, and the ML service turns them into daily kWh; the page does the same subtraction only to draw the chart. The appliance list is converted to the API format by `appliancesForApi` (fridges are sent as "all day", star ratings only for AC, fridge and fan).

**Honesty rules the UI always keeps:**
- "Homes like yours" always shows its `data_label` and a **simulated** badge, and simulated months are drawn as dashed violet bars, unlike the user's own bills.
- Every forecast shows its likely range, explained as "in testing, 8 out of 10 real values fell inside it".
- The 4-7% savings line is always marked as an estimate from other studies.
- The appliance split is always marked as an estimate.

**Status badge.** `App.jsx` checks `/api/health` every 15 s. If the ML service stops, a banner appears, and it disappears by itself when the service comes back.

---

## 5. Most important files and functions

| File | What's in it |
|---|---|
| `index.html` | The page shell: title, fonts and the `<div id="root">` React draws into |
| `src/main.jsx` | Starts React and loads `styles.css` |
| `src/App.jsx` | **`App`**: header, "Model online/offline" badge, tabs, footer. Reads the tab from the URL hash, polls `/api/health`, loads `/api/meta` once and passes it to the forecast page |
| `src/api.js` | **`call(method, path, body)`**: one `fetch` wrapper that turns failures into readable errors. **`api`**: the five route functions |
| `src/format.js` | Formatting helpers: `rs` / `rs2` (₹ with Indian digit grouping), `num`, `hourLabel` (0 → "12am"), `MONTHS`, `lastMonthIndex`, `isoDate`, and **`parseNumbers`** (text → list of numbers + anything that isn't a number) |
| `src/pages/BillPage.jsx` | **`BillPage`**: the bill form and its `submit`. **`BillResults`**: stat tiles, slab table, bill chart, savings line. **`LikeYours`**: the simulated-homes card (year chart, typical day) |
| `src/pages/ForecastPage.jsx` | **`CFG`**: labels, limits and the sample home. **`ForecastPage`**: the readings form and its `submit`. **`DailyResults`**: forecast tiles, chart, tip, bill, peers, appliance split. **`Range`**: the "likely a-b" text |
| `src/pages/AboutPage.jsx` | Static "How it works" text, limits and sources |
| `src/components/ui.jsx` | Small building blocks: `Card`, `Stat` (number tile), `Seg` (Yes/No style buttons), `Notice`, `ErrorBox`, `Empty`, `Spin`, **`SlabTable`**, `SavingsLine`, **`Tip`** (tip card), `Defaults` ("About these numbers") |
| `src/components/forecastBits.jsx` | Daily-tab pieces: **`ApplianceEditor`** (the Advanced appliance list), **`appliancesForApi`**, `HomeAndMeter`, `PeerCard`, `ApplianceCard`, `BillCard` |
| `src/components/charts.jsx` | Recharts charts: `BillHistoryChart`, **`YearChart`** (own bills solid, simulated months dashed), `DayChart` (typical day), **`ForecastChart`** (past days + tomorrow with its range), `ShareBars` (appliance split) |
| `src/styles.css` | All styling. Colours are CSS variables at the top |
| `vite.config.js` | Vite settings. In `npm run dev`, `/api` calls go to the Node server on :5050 |
| `server.js` | The Node backend, in one file: serves `dist/` and forwards the 5 `/api` routes to the ML service (`PORT` default 5050, `ML_URL` default http://localhost:8000). Full detail in the root README |

---

## 6. Working on the frontend

```bash
cd wattwise_app
npm install          # first time only
npm start            # terminal A: Node server on :5050 (the ML service must also be running)
npm run dev          # terminal B: live-reloading site on http://localhost:5173
```

Edit files in `src/`. The page at :5173 updates on save. When done, run `npm run build` so `npm start` serves the new version from `dist/`.
