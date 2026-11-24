"""
"Homes like yours": match a user's monthly bills to the closest SIMULATED Pune homes
(pune_sim/), then show what a home like that typically looks like:
  * a typical day (watts by hour) for the month of the last bill, and for May (peak AC month)
  * a 12-month outlook (units, bill, kg CO2); months the user entered stay as entered

Method: k nearest neighbours (k = 5, fixed before testing). Distance = average gap in log units
between the user's bills and a home's units for the SAME calendar months, so both size and
season shape count. The neighbours are then scaled so they match the user's total exactly.

Everything here comes from SIMULATED homes and must be labelled that way on screen.
How well it works is tested in pune_sim/check_like_yours.py (results in pune_sim/PUNE_SIM.md).
No TensorFlow needed.
"""
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DAILY_FILE = os.path.join(HERE, "data", "pune_sim_daily.csv")
PROFILE_FILE = os.path.join(HERE, "data", "pune_sim_profiles.csv")
K = 5
DAYS_PER_MONTH = 30   # same billing month as tariff_config.json
_cache = {}


def load():
    if "data" not in _cache:
        for f in (DAILY_FILE, PROFILE_FILE):
            if not os.path.exists(f):
                raise FileNotFoundError(f"{os.path.relpath(f, HERE)} is missing. Run: python pune_sim/make_pune_sim.py")
        d = pd.read_csv(DAILY_FILE, parse_dates=["date"])
        d["month"] = d["date"].dt.month
        g = d.groupby(["household_id", "month"])
        ok = g["daily_kwh"].size() >= 15                      # need at least half a month of days
        monthly = (g["daily_kwh"].mean() * DAYS_PER_MONTH)[ok].unstack()   # homes x 12, units per month
        has_ac = d.groupby("household_id")["has_ac"].first().astype(bool)
        prof = pd.read_csv(PROFILE_FILE).set_index(["household_id", "month"])["watts"]
        _cache["data"] = (monthly, has_ac, prof)
    return _cache["data"]


def bill_months(n_bills, last_month):
    """Calendar months of n bills, oldest first, ending at last_month (1-12)."""
    return [((last_month - 1 - i) % 12) + 1 for i in range(n_bills)][::-1]


def match(units, months, has_ac=None, k=K, exclude=None, data=None):
    """units/months: the user's bills. Returns a DataFrame of the k nearest homes with
    their distance and scale factor."""
    monthly, ac, _ = data or load()
    u = np.clip(np.asarray(units, float), 1.0, None)
    cand = monthly[list(months)].dropna()
    if has_ac is not None:
        cand = cand[ac.reindex(cand.index) == bool(has_ac)]
    if exclude is not None:
        cand = cand.drop(index=[h for h in np.atleast_1d(exclude) if h in cand.index])
    gap = np.abs(np.log(u) - np.log(np.clip(cand.values, 1.0, None))).mean(axis=1)
    best = pd.DataFrame({"distance": gap}, index=cand.index).nsmallest(k, "distance")
    best["scale"] = u.sum() / cand.loc[best.index].sum(axis=1)
    return best


def outlook(best, data=None):
    """12-month units for a home like the user's (scaled neighbours, averaged)."""
    monthly, _, _ = data or load()
    m = monthly.loc[best.index]
    scaled = m.mul(best["scale"], axis=0)
    return scaled.mean(skipna=True).reindex(range(1, 13))


def typical_day(best, month, data=None):
    """24 hourly watts for a home like the user's in this calendar month."""
    _, _, prof = data or load()
    rows = []
    for h, sc in best["scale"].items():
        if (h, month) in prof.index:
            rows.append(prof.loc[(h, month)].values * sc)
    return np.mean(rows, axis=0) if rows else None
