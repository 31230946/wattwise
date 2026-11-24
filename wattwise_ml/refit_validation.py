"""
OPTIONAL: checks how good the appliance estimator (watts x hours) is, using
REFIT, a real UK dataset where individual appliances were metered.

DISCLAIMER (keep this wording in the report):
  This check has NOT been run on the full REFIT data yet. Until it is, the
  appliance breakdown in the app is an unvalidated estimate. Also, REFIT
  homes are British: no ACs, no geysers, but kettles and tumble dryers. So
  even after this check, the numbers only say how well "watts x hours" works
  in general, not how well it works for Indian appliances.

Dataset: Murray, Stankovic & Stankovic (2017), "An electrical load measurements
dataset of United Kingdom households from a two-year longitudinal study",
Scientific Data 4:160122. Files look like CLEAN_House2.csv with columns
  Time, Unix, Aggregate, Appliance1 ... Appliance9, Issues   (watts, ~8 s apart)

The idea:
  1. From the real readings, work out how many hours each appliance was ON per day.
     That is the number a user would type into our form.
  2. Feed those hours into the same watts x hours estimator the app uses.
  3. Compare the estimated share of each appliance with its real measured share.
  4. Report the average error in percentage points.

Usage:
  python3 refit_validation.py data/refit/CLEAN_House2.csv --house 2 --days 30
"""
import argparse
import json

import numpy as np
import pandas as pd

import appliance_estimator as ae

# Fill this in from the REFIT README for each house you download.
# It maps each ApplianceN column to a catalog type; columns mapped to None are skipped.
# The entry below is a PLACEHOLDER showing the shape. It is NOT the real house 2 list,
# so check the README before running.
HOUSE_APPLIANCES = {
    2: {"Appliance1": "fridge", "Appliance2": "washing_machine", "Appliance3": None,
        "Appliance4": None, "Appliance5": None, "Appliance6": None,
        "Appliance7": None, "Appliance8": "kettle", "Appliance9": None},
}

# UK appliances that are not in the Indian catalog (typical watts; assumptions)
REFIT_EXTRA = {
    "kettle": {"label": "Kettle", "watts": 2000, "duty": 1.0, "shiftable": False, "cuttable": False},
    "dishwasher": {"label": "Dishwasher", "watts": 1800, "duty": 0.6, "shiftable": True, "cuttable": False},
    "tumble_dryer": {"label": "Tumble dryer", "watts": 2500, "duty": 0.8, "shiftable": True, "cuttable": False},
    "toaster": {"label": "Toaster", "watts": 900, "duty": 1.0, "shiftable": False, "cuttable": False},
    "freezer": {"label": "Freezer", "watts": 100, "duty": 0.35, "shiftable": False, "cuttable": False},
    "electric_heater": {"label": "Electric heater", "watts": 2000, "duty": 0.8, "shiftable": False, "cuttable": True},
}
ALWAYS_ON = {"fridge", "freezer"}
ON_THRESHOLD_W = 15


def load_house(path):
    df = pd.read_csv(path)
    df["Time"] = pd.to_datetime(df["Time"])
    df = df.set_index("Time").drop(columns=[c for c in ("Unix", "Issues") if c in df.columns])
    return df.resample("1min").mean()   # minute-average watts


def validate(path, house, days=30):
    ae.CATALOG.update(REFIT_EXTRA)
    mapping = {k: v for k, v in HOUSE_APPLIANCES[house].items() if v}
    m = load_house(path)
    rows = []
    for day, g in list(m.groupby(m.index.date))[:days]:
        if len(g) < 1380:   # need ~23 h of minutes
            continue
        measured, form = {}, []
        for col, typ in mapping.items():
            w = g[col].fillna(0)
            measured[typ] = w.mean() * 24 / 1000               # kWh that day
            on_hours = (w > ON_THRESHOLD_W).sum() / 60
            if typ in ALWAYS_ON:
                form.append({"type": typ, "count": 1, "when": "all_day"})
            elif on_hours > 0:
                form.append({"type": typ, "count": 1, "hours_per_day": round(on_hours * 2) / 2 or 0.5,
                             "when": "evening"})   # people round to the half hour
        total = sum(measured.values())
        if total <= 0 or not form:
            continue
        est = ae.estimate(form, total)
        est_share = {i["type"]: i["share_pct"] for i in est["items"]}
        for typ, kwh in measured.items():
            rows.append({"date": str(day), "appliance": typ,
                         "measured_pct": 100 * kwh / total, "estimated_pct": est_share.get(typ, 0.0)})
    res = pd.DataFrame(rows)
    res["abs_err_pts"] = (res["measured_pct"] - res["estimated_pct"]).abs()
    by_app = res.groupby("appliance")[["measured_pct", "estimated_pct", "abs_err_pts"]].mean().round(1)
    return res, by_app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--house", type=int, default=2)
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    res, by_app = validate(a.csv, a.house, a.days)
    print(by_app.to_string())
    print(f"\nmean absolute error: {res.abs_err_pts.mean():.1f} percentage points "
          f"over {res.date.nunique()} days")
    by_app.to_csv(f"models/refit_house{a.house}_check.csv")
    with open(f"models/refit_house{a.house}_check.json", "w") as f:
        json.dump({"mae_pts": round(float(res.abs_err_pts.mean()), 2), "days": int(res.date.nunique())}, f)
