"""
WattWise core. All app logic lives here, so api.py (web service) and cli.py (offline)
give identical results.

Entry points (each takes a plain dict and returns a JSON-ready dict; bad input raises InputError):
  bill_screen(req)       monthly bill units -> bill + carbon breakdown (no ML)
  forecast_daily(req)    7-28 daily kWh     -> next day / 7 days / 30 days (ML) + bill + carbon + tip
  homes_like_yours(req)  monthly bills      -> closest SIMULATED Pune homes: typical day + 12-month outlook
  meta()                 dropdown values, tariff and carbon factor for the frontend
"""
import datetime as dt
import json
import os

import joblib
import numpy as np
import pandas as pd

import appliance_estimator
import carbon
import tariff
import tips
from bandit_recommender import ACTIONS, build_context
from preprocessing import BAND_LABELS, DAILY_FEATURES, DAILY_MAX_HISTORY, daily_feature_row

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.environ.get("WATTWISE_MODEL_DIR", os.path.join(HERE, "models"))
DAYS_PER_BILL = tariff.TARIFF["days_per_billing_month"]
_cache = {}


class InputError(ValueError):
    """Bad user input. The API turns this into HTTP 422 with the message."""


# ---------------------------------------------------------------- loading (once)
def _load(name):
    if name in _cache:
        return _cache[name]
    p = lambda f: os.path.join(MODEL_DIR, f)  # noqa: E731
    try:
        if name == "daily":
            os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
            import tensorflow as tf   # imported only when a forecast is needed
            b = joblib.load(p("daily_bundle.joblib"))
            b["lstm"] = tf.keras.models.load_model(p("lstm_tomorrow.keras"))
            obj = b
        elif name == "bandit":
            obj = joblib.load(p("bandit.joblib"))
        elif name == "peers":
            with open(p("peer_stats.json")) as f:
                obj = json.load(f)
    except FileNotFoundError as e:
        raise RuntimeError(f"Model file missing: {e.filename}. Run `python train.py` first.") from e
    _cache[name] = obj
    return obj


# ---------------------------------------------------------------- input helpers
def _series(req, values_key, readings_key, min_n, max_n, unit):
    """Accepts either the per-period kWh list, or cumulative meter readings (converted to differences)."""
    if req.get(values_key) is not None:
        vals = [float(v) for v in req[values_key]]
    elif req.get(readings_key) is not None:
        r = [float(v) for v in req[readings_key]]
        if any(b < a for a, b in zip(r, r[1:])):
            raise InputError(f"{readings_key} must not go down (meter readings only increase).")
        vals = list(np.diff(r))
    else:
        raise InputError(f"Send {values_key} (kWh per {unit}) or {readings_key} (meter readings).")
    if any(v < 0 for v in vals):
        raise InputError("kWh values can't be negative.")
    if len(vals) < min_n:
        raise InputError(f"Need at least {min_n} {unit}s of data, got {len(vals)}. "
                         f"Use the monthly bill screen until then.")
    return vals[-max_n:]


def _home(req, defaulted):
    home = req.get("home_type")
    if home is None:
        home = "2bhk"
        defaulted.append("home_type")
    if home not in BAND_LABELS:
        raise InputError(f"home_type must be one of {BAND_LABELS}")
    return home


def _range(ranges_key, bundle, hist_len, point):
    tab = bundle["ranges"][ranges_key]["by_history"]
    keys = sorted(int(k) for k in tab)
    k = min(keys, key=lambda x: abs(x - hist_len))
    lo, hi = tab[k] if k in tab else tab[str(k)]
    return [round(point * lo, 1), round(point * hi, 1)]


def _context_and_tip(req, daily_kwh, monthly_units, hist_mean_daily, home, breakdown, defaulted):
    peers = _load("peers")
    peer = peers[home]
    peer_mean = float(req.get("peer_mean_kwh") or peer["peer_mean_kwh"])
    if req.get("peer_mean_kwh") is None:
        defaulted.append("peer_mean_kwh")
    if req.get("evening_share") is not None:
        ev = float(req["evening_share"])
    elif breakdown:
        ev = breakdown["evening_share"]
    else:
        ev = peer["evening_share"]
        defaulted.append("evening_share")
    base_known = req.get("baseload_kw") is not None
    base = float(req["baseload_kw"]) if base_known else peer["baseload_kw"] * hist_mean_daily / peer["peer_mean_kwh"]
    if not base_known:
        defaulted.append("baseload_kw (scaled from usage)")
    sm = bool(req.get("has_smart_meter", False))
    ctx = build_context(daily_kwh, peer_mean, ev, base, peer["baseload_kw"], 0, sm)
    bandit = _load("bandit")
    a, _ = bandit.select(ctx)
    tip = tips.build_tip(ACTIONS[a], daily_kwh, monthly_units, peer_mean, sm, breakdown,
                         baseload_above_peers=(base > 1.1 * peer["baseload_kw"]) if base_known else None)
    return {
        "peer_group": {"home_type": home, "peer_mean_kwh_per_day": round(peer_mean, 2),
                       "you_vs_peers_pct": round(100 * (daily_kwh - peer_mean) / peer_mean, 1),
                       "note": "Peer groups come from London homes split into 4 usage bands; replaced by real app users later."},
        "recommendation": {**tip, "confidence_scores": {ACTIONS[i]: round(s, 3)
                                                        for i, s in enumerate(bandit.expected(ctx))}},
    }


def _appliances(req, daily_kwh):
    if not req.get("appliances"):
        return None
    for a in req["appliances"]:
        if a.get("type") not in appliance_estimator.CATALOG:
            raise InputError(f"Unknown appliance type '{a.get('type')}'. See /meta for the list.")
        if a.get("star_rating") is not None and a["type"] not in appliance_estimator.STAR_TYPES:
            raise InputError(f"Star ratings are only used for {', '.join(appliance_estimator.CATALOG[t]['label'] for t in appliance_estimator.STAR_TYPES)}.")
        if a.get("label_kwh_per_year") is not None and a["type"] not in appliance_estimator.LABEL_KWH_TYPES:
            raise InputError("Label kWh per year is only used for ACs and fridges.")
    try:
        return appliance_estimator.estimate(req["appliances"], daily_kwh)
    except ValueError as e:
        raise InputError(str(e)) from e


def _money_and_carbon(monthly_units, sm, solar_share, label):
    return {
        "bill": {**tariff.bill_summary(monthly_units, sm, solar_share), "breakdown": tariff.slab_breakdown(monthly_units),
                 "based_on": label},
        "carbon": carbon.summary(monthly_units, label),
        "expected_savings_if_tips_followed": carbon.expected_savings(monthly_units, sm),
    }


NOTES = [
    "Forecast models were trained on 148 London homes (Low Carbon London, 2013); Indian homes may differ.",
    "Bill = energy + wheeling + fixed charge (MSEDCL FY 2026-27). Electricity duty and FAC are not included.",
    "Carbon uses one yearly average for the Indian grid (CEA, 0.727 kg CO2/kWh).",
]


# ---------------------------------------------------------------- 1. bill screen (no ML)
def bill_screen(req):
    units = [float(u) for u in (req.get("monthly_units") or [])]
    if not units:
        raise InputError("Send monthly_units: units from your recent bills, oldest first (1-12 values).")
    if any(u < 0 for u in units) or len(units) > 12:
        raise InputError("monthly_units must be 1-12 non-negative values.")
    sm = bool(req.get("has_smart_meter", False))
    last = units[-1]
    proj = {"same_as_last_month": round(last, 1), "average_of_months_given": round(float(np.mean(units)), 1)}
    if len(units) == 12:
        proj["same_month_last_year"] = round(units[0], 1)   # 12 values, oldest first -> [0] is 12 months before next
    slab = tariff.current_slab(last)
    return {
        "screen": "monthly_bill",
        "last_month": {"units": last, **_money_and_carbon(last, sm, 0.0, "your last bill")},
        "history": [{"units": u, "bill_rs": tariff.monthly_bill(u), "kg_co2": carbon.kg_co2(u)} for u in units],
        "slab_status": {"slab": f"{slab['from_units']}-{slab['to_units'] or 'above'}",
                        "each_unit_cut_saves_rs": round(tariff.marginal_rate(last), 2)},
        "simple_projection": {**proj, "is_ml_forecast": False,
                              "note": "Simple arithmetic, not a forecast. Add daily readings for an ML forecast."},
        "next_step": "Enter daily meter readings (7 or more days) to get a machine-learning forecast and a personal tip.",
        "notes": NOTES[1:],
    }


# ---------------------------------------------------------------- 2. daily path (ML)
def forecast_daily(req):
    defaulted = []
    hist = _series(req, "daily_kwh", "daily_meter_readings", 7, DAILY_MAX_HISTORY, "day")
    home = _home(req, defaulted)
    last = req.get("last_reading_date")
    last = dt.date.fromisoformat(str(last)) if last else dt.date.today() - dt.timedelta(days=1)
    if not req.get("last_reading_date"):
        defaulted.append("last_reading_date (assumed yesterday)")
    start = last + dt.timedelta(days=1)

    b = _load("daily")
    peers = _load("peers")
    rough = float(np.mean(hist[-3:]))
    breakdown = _appliances(req, rough)
    ev = (float(req["evening_share"]) if req.get("evening_share") is not None
          else breakdown["evening_share"] if breakdown else peers[home]["evening_share"])
    base = (float(req["baseload_kw"]) if req.get("baseload_kw") is not None
            else peers[home]["baseload_kw"] * float(np.mean(hist)) / peers[home]["peer_mean_kwh"])
    X = pd.DataFrame([daily_feature_row(hist, ev, base, start.weekday())])[DAILY_FEATURES]

    x1 = float(b["xgb_1"].predict(X)[0])
    seq = b["seq_scaler"].transform(np.asarray(hist[-7:], float).reshape(1, -1))[..., None]
    l1 = float(b["lstm"].predict(seq, verbose=0).ravel()[0])
    d1 = max(0.0, b["w_xgb"] * x1 + b["w_lstm"] * l1)
    d7 = max(0.0, float(b["xgb_7"].predict(X)[0]))     # avg kWh/day over next 7 days
    d30 = max(0.0, float(b["xgb_30"].predict(X)[0]))   # avg kWh/day over next 30 days
    n = len(hist)

    def block(total, key, period):
        return {"kwh": round(total, 1), "range_80pct": _range(key, b, n, total),
                "kg_co2": carbon.kg_co2(total), "period": period}

    if breakdown:
        breakdown = appliance_estimator.estimate(req["appliances"], d1)
    month_units = d30 * DAYS_PER_BILL
    ctx = _context_and_tip(req, d1, month_units, float(np.mean(hist)), home, breakdown, defaulted)
    sm = bool(req.get("has_smart_meter", False))
    return {
        "path": "daily",
        "input_summary": {"days_used": n, "low_history": n < 14, "forecast_starts": start.isoformat()},
        "forecast": {
            "next_day": block(d1, "daily_1", start.isoformat()),
            "next_7_days": {**block(7 * d7, "daily_7", f"{start} to {start + dt.timedelta(days=6)}"),
                            "kwh_per_day": round(d7, 2)},
            "next_30_days": {**block(30 * d30, "daily_30", f"{start} to {start + dt.timedelta(days=29)}"),
                             "kwh_per_day": round(d30, 2)},
        },
        "model_details": {"next_day": {"xgboost": round(x1, 2), "lstm": round(l1, 2),
                                       "w_xgb": round(b["w_xgb"], 2), "w_lstm": round(b["w_lstm"], 2)},
                          "range_note": "In testing on homes the model never saw, 8 out of 10 real values fell inside range_80pct."},
        **_money_and_carbon(month_units, sm, breakdown["solar_share"] if breakdown else 0.0,
                            "next 30 days forecast"),
        "peer_group": ctx["peer_group"], "recommendation": ctx["recommendation"],
        "appliance_breakdown": breakdown,
        "inputs_defaulted": defaulted, "notes": NOTES,
    }


def meta():
    return {
        "screens": {"monthly_bill": "POST /bill", "homes_like_yours": "POST /homes-like-yours", "daily": "POST /forecast/daily"},
        "home_types": BAND_LABELS,
        "appliance_types": {k: v["label"] for k, v in appliance_estimator.CATALOG.items()},
        "appliance_when_options": list(appliance_estimator.PERIOD_HOURS.keys()),
        "appliance_star_types": list(appliance_estimator.STAR_TYPES),
        "appliance_label_kwh_types": appliance_estimator.LABEL_KWH_TYPES,
        "tariff": {"name": f"MSEDCL {tariff.TARIFF['category']}", "year": tariff.TARIFF["financial_year"],
                   "slabs": tariff.TARIFF["slabs"], "tod": tariff.TARIFF["tod"]},
        "carbon_factor": {"kg_co2_per_kwh": carbon.FACTOR, "source": carbon.CARBON["_source"]},
        "peer_defaults": _load("peers"),
        "limits": {"daily_kwh": "7-28 values", "monthly_units": "1-12 values"},
    }


# ---------------------------------------------------------------- 3. homes like yours (SIMULATED Pune homes)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LIKE_LABEL = ("Based on SIMULATED Pune homes (real London homes reshaped to published Pune smart-meter "
              "averages). A typical picture for homes like yours, not a forecast from your own data.")


def homes_like_yours(req):
    """Monthly bills (+ AC yes/no) -> closest simulated Pune homes -> typical day and 12-month outlook."""
    import similar_homes as sh
    units = [float(u) for u in (req.get("monthly_units") or [])]
    if not units:
        raise InputError("Send monthly_units: units from 1 to 12 recent bills, oldest first.")
    if len(units) > 12:
        raise InputError("At most 12 monthly bills.")
    if any(u <= 0 for u in units):
        raise InputError("Bill units must be more than 0.")
    defaulted = []
    last = req.get("last_bill_month")
    if last is None:
        last = (dt.date.today().replace(day=1) - dt.timedelta(days=1)).month
        defaulted.append("last_bill_month (assumed last month)")
    last = int(last)
    if not 1 <= last <= 12:
        raise InputError("last_bill_month must be 1-12.")
    has_ac = req.get("has_ac")
    if has_ac is None:
        defaulted.append("has_ac (unknown: matched against all homes)")
    sm = bool(req.get("has_smart_meter", False))
    months = sh.bill_months(len(units), last)
    try:
        best = sh.match(units, months, has_ac)
    except FileNotFoundError as e:
        raise RuntimeError(str(e)) from e
    guess = sh.outlook(best)
    given = dict(zip(months, units))

    year = []
    for m in range(1, 13):
        u = given.get(m, float(guess[m]))
        b = tariff.bill_summary(u, sm, 0.0)
        year.append({"month": MONTHS[m - 1], "units": round(u, 0), "bill_rs": b["estimated_bill_rs"],
                     "slab": b["current_slab"], "kg_co2": carbon.kg_co2(u),
                     "source": "your bill" if m in given else "homes like yours (simulated)"})
    peak = max(year, key=lambda r: r["units"])
    total_units = sum(r["units"] for r in year)

    def day(month):
        w = sh.typical_day(best, month)
        if w is None:
            return None
        hrs = np.arange(24)
        return {"month": MONTHS[month - 1], "hourly_watts": [round(float(x)) for x in w],
                "peak_hour": int(hrs[np.argmax(w)]), "peak_watts": round(float(w.max())),
                "night_watts_1_to_5am": round(float(w[1:5].mean())),
                "evening_share_6_to_10pm": round(float(w[18:22].sum() / w.sum()), 3)}

    close = float(np.expm1(best["distance"].mean()) * 100)
    if close > 30:
        defaulted.append("warning: your use is outside the range of the simulated homes, so this picture is less reliable")
    return {
        "data_label": LIKE_LABEL,
        "matched": {"homes": int(len(best)), "with_ac": has_ac,
                    "how_close_pct": round(close, 1),
                    "note": "Average gap between your bills and the matched homes' units for the same months."},
        "your_bills": [{"month": MONTHS[m - 1], "units": u} for m, u in zip(months, units)],
        "typical_day": day(last),
        "typical_day_peak_month": day(MONTHS.index(peak["month"]) + 1),
        "year_outlook": year,
        "year_summary": {"units": round(total_units), "bill_rs": round(sum(r["bill_rs"] for r in year)),
                         "kg_co2": round(sum(r["kg_co2"] for r in year)),
                         "highest_month": peak["month"], "highest_month_units": peak["units"],
                         "highest_month_slab": peak["slab"]},
        "how_good_is_this": ("Tested on the simulated homes only (pune_sim/PUNE_SIM.md). Real homes vary more, "
                             "so treat months you didn't enter as a rough guide."),
        "inputs_defaulted": defaulted,
    }
