"""
SIMULATED Pune homes made from real London (LCL) homes.

What is kept from London (real):  each home's day-to-day ups and downs (weekly habits,
streaks, odd days) and its half-hour spikiness.
What is replaced with Pune numbers (Prayas smart-meter studies, see pune_targets.json):
  1. usage level      -> Pune spread (mean 156 kWh/month)
  2. daily shape      -> Pune morning / evening / night watts
  3. season           -> Pune summer (AC nights in Apr-May) instead of London winter
  4. AC homes         -> 30% of homes get the summer AC night load (our assumption)

Homes used: 150 LCL homes that were NOT used to train the models (seed 7, excluding the
seed-42 training homes), so the stress test runs on homes the model has never seen.

Every output row is labelled is_simulated = 1. Never report these as real Indian results.

Run from the project root:   python pune_sim/make_pune_sim.py
Outputs:
  data/pune_sim_daily.csv             simulated Pune homes, one row per home per day
  data/pune_sim_profiles.csv          each simulated home's typical day (hourly watts) per month
  pune_sim/out/london_source_daily.csv  the same homes before the change (for comparison)
  pune_sim/out/profiles.csv           average half-hour watts by month (sim and London)
  pune_sim/out/homes.csv              one row per home: level, AC yes/no, source LCL id
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from statistics import NormalDist

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from load_real_lcl import find_raw, pick_households  # noqa: E402
from preprocessing import EVENING_HOURS, NIGHT_HOURS, SOLAR_HOURS  # noqa: E402

N_HOMES, SEED = 150, 7
DAYS_PER_MONTH = 30.4375
OUT = os.path.join(ROOT, "pune_sim", "out")
T = json.load(open(os.path.join(ROOT, "pune_sim", "pune_targets.json")))


def half_hour_profile(hourly):
    """24 hourly watts -> 48 half-hour watts (linear, wraps round midnight)."""
    h = np.asarray(hourly, float)
    centres = np.arange(24) + 0.5
    slots = np.arange(48) / 2 + 0.25
    return np.interp(slots, centres, h, period=24)


def month_weights(by_month, doy, year=2013):
    """Monthly anchor (on the 15th) -> smooth daily weight."""
    mids = np.array([pd.Timestamp(year, m, 15).dayofyear for m in range(1, 13)], float)
    vals = np.array([by_month[str(m)] for m in range(1, 13)], float)
    return np.interp(doy, mids, vals, period=365)


def date_weights(anchors, doy, year=2013):
    """[["MM-DD", weight], ...] -> daily weight, straight lines between anchors."""
    d = np.array([pd.Timestamp(f"{year}-{a}").dayofyear for a, _ in anchors], float)
    v = np.array([w for _, w in anchors], float)
    return np.interp(doy, d, v, period=365)


def day_profiles(dates, has_ac):
    """Half-hour watts for an average home of this class, for each date (days x 48)."""
    A = T["assumptions"]
    P = {k: half_hour_profile(v) for k, v in T["profiles_w"].items() if not k.startswith("_")}
    doy = dates.dayofyear.values.astype(float)
    s = date_weights(A["summer_weight_anchors"], doy)[:, None]
    wm = month_weights(A["winter_morning_weight_by_month"], doy)[:, None]
    nonsummer = wm * P["nonsummer_winter"] + (1 - wm) * P["nonsummer_other"]
    summer = P["summer_ac"] if has_ac else P["summer_no_ac"]
    return s * summer + (1 - s) * nonsummer


def pick_new_homes(path):
    train_ids = set(pick_households(path, 150, 42))
    all_ids = [c for c in pd.read_csv(path, nrows=0).columns if c.startswith("MAC")]
    rest = sorted(set(all_ids) - train_ids)
    rng = np.random.default_rng(SEED)
    return sorted(rng.choice(rest, size=N_HOMES, replace=False).tolist())


def to_day_matrix(s):
    """Half-hour series -> (dates, days x 48 kWh), complete clean days only."""
    df = pd.DataFrame({"kwh": s.values}, index=s.index)
    df.loc[(df["kwh"] < 0) | (df["kwh"] >= 10), "kwh"] = np.nan
    df["date"] = df.index.normalize()
    df["slot"] = df.index.hour * 2 + df.index.minute // 30
    m = df.pivot_table(index="date", columns="slot", values="kwh", aggfunc="first")
    m = m.reindex(columns=range(48)).dropna()
    m = m[m.sum(axis=1) > 0.2]
    return m.index, m.values


def day_metrics(dates, X):
    hrs = np.arange(48) // 2
    ev = (hrs >= EVENING_HOURS[0]) & (hrs < EVENING_HOURS[1])
    so = (hrs >= SOLAR_HOURS[0]) & (hrs < SOLAR_HOURS[1])
    ni = (hrs >= NIGHT_HOURS[0]) & (hrs < NIGHT_HOURS[1])
    tot = X.sum(1)
    d = pd.DataFrame({"date": dates, "daily_kwh": tot, "evening_kwh": X[:, ev].sum(1),
                      "solar_kwh": X[:, so].sum(1),
                      "baseload_kw": X[:, ni].sum(1) / (NIGHT_HOURS[1] - NIGHT_HOURS[0])})
    d["evening_share"] = d["evening_kwh"] / d["daily_kwh"].clip(lower=1e-6)
    d["dow"] = d["date"].dt.dayofweek
    d["is_weekend"] = (d["dow"] >= 5).astype(int)
    return d


def main():
    os.makedirs(OUT, exist_ok=True)
    path = find_raw()
    ids = pick_new_homes(path)
    print(f"reading {len(ids)} unseen LCL homes from {path} ...")
    wide = pd.read_csv(path, usecols=["DateTime"] + ids)
    ts = pd.to_datetime(wide.pop("DateTime").str.slice(0, 19)) - pd.Timedelta(minutes=30)
    wide.index = ts
    wide = wide[wide.index.year == 2013]

    # ---- pass 1: London day matrices, keep homes with >= 200 clean days
    homes = {}
    for hid in ids:
        dates, X = to_day_matrix(wide[hid])
        if len(dates) >= 200:
            homes[hid] = (dates, X)
    print(f"{len(homes)} homes with at least 200 complete days")

    # ---- usage level: rank London homes, map onto the Pune lognormal (quantile mapping)
    lon_mean = pd.Series({h: X.sum(1).mean() for h, (_, X) in homes.items()})
    rank = lon_mean.rank(method="first")
    n = len(lon_mean)
    sigma = 0.448
    mu = np.log(T["published"]["monthly_kwh_mean_pune_city"]) - sigma ** 2 / 2
    level_month = np.exp(mu + sigma * np.array([NormalDist().inv_cdf(q) for q in ((rank - 0.5) / n)]))
    level_day = pd.Series(level_month / DAYS_PER_MONTH, index=lon_mean.index)

    # ---- AC homes: 30% of all homes, drawn at random from the top 60% by usage
    rng = np.random.default_rng(SEED)
    top = rank[rank > 0.4 * n].index.tolist()
    ac = set(rng.choice(top, size=int(round(T["assumptions"]["ac_share"] * n)), replace=False))

    # yearly mean kWh/day of each class profile, so the season factor averages to 1
    year = pd.date_range("2013-01-01", "2013-12-31", freq="D")
    ebar = {c: (day_profiles(year, c).sum(1) * 0.5 / 1000).mean() for c in (False, True)}

    sim_rows, lon_rows, home_rows, prof, home_prof = [], [], [], [], []
    for i, (hid, (dates, X)) in enumerate(sorted(homes.items())):
        sid = f"PUNESIM_{i + 1:03d}"
        has_ac = hid in ac
        dtot = X.sum(1)
        # day-to-day wiggle: today vs this home's 31-day centred average (London season removed)
        s = pd.Series(dtot, index=dates).reindex(pd.date_range(dates.min(), dates.max()))
        roll = s.rolling(31, center=True, min_periods=10).mean().reindex(dates).values
        wiggle = dtot / roll
        keep = np.isfinite(wiggle)            # isolated days with too few neighbours are dropped
        dates, X, dtot, wiggle = dates[keep], X[keep], dtot[keep], wiggle[keep]
        # half-hour spikiness: each slot vs this home's average for that month and slot
        mo = dates.month.values
        mprof = np.vstack([X[mo == m].mean(0) if (mo == m).any() else np.ones(48) for m in range(1, 13)])
        r = np.clip(X / np.clip(mprof[mo - 1], 1e-4, None), 0.2, 5.0)

        P = day_profiles(dates, has_ac)                       # Pune average-home watts
        season = (P.sum(1) * 0.5 / 1000) / ebar[has_ac]       # Pune season factor, mean 1
        d_new = level_day[hid] * season * wiggle              # kWh per day
        shape = P * r
        Y = d_new[:, None] * shape / shape.sum(1, keepdims=True)

        ds = day_metrics(dates, Y)
        ds.insert(0, "household_id", sid)
        ds["has_ac"] = int(has_ac)
        ds["is_simulated"] = 1
        sim_rows.append(ds)
        dl = day_metrics(dates, X)
        dl.insert(0, "household_id", sid)
        lon_rows.append(dl)
        home_rows.append({"household_id": sid, "source_lcl_id": hid, "has_ac": int(has_ac),
                          "london_kwh_per_day": round(float(dtot.mean()), 3),
                          "sim_kwh_per_month": round(float(d_new.mean() * DAYS_PER_MONTH), 1),
                          "days": len(dates)})
        for m in range(1, 13):                 # per-home typical day by month (for "homes like yours")
            sel = mo == m
            if sel.any():
                hw = Y[sel].mean(0).reshape(24, 2).mean(1) * 2000
                home_prof.append(pd.DataFrame({"household_id": sid, "month": m, "hour": range(24),
                                               "watts": hw.round(1)}))
        wk = dates.dayofweek.values >= 5
        for m in range(1, 13):
            for src, M in (("sim", Y), ("london", X)):
                for w in (0, 1):
                    sel = (mo == m) & (wk == w)
                    if sel.any():
                        prof.append(pd.DataFrame({"source": src, "household_id": sid, "has_ac": int(has_ac),
                                                  "month": m, "weekend": w, "slot": range(48),
                                                  "w": M[sel].mean(0) * 2000, "n_days": int(sel.sum())}))

    sim = pd.concat(sim_rows, ignore_index=True)
    lon = pd.concat(lon_rows, ignore_index=True)
    rnd = {c: 4 for c in ["daily_kwh", "evening_kwh", "solar_kwh", "baseload_kw", "evening_share"]}
    sim.round(rnd).to_csv(os.path.join(ROOT, "data", "pune_sim_daily.csv"), index=False)
    lon.round(rnd).to_csv(os.path.join(OUT, "london_source_daily.csv"), index=False)
    pd.DataFrame(home_rows).to_csv(os.path.join(OUT, "homes.csv"), index=False)
    p = pd.concat(prof, ignore_index=True)
    p = p.groupby(["source", "has_ac", "month", "weekend", "slot"]).agg(
        w=("w", "mean"), n_homes=("household_id", "nunique")).reset_index()
    p.round(2).to_csv(os.path.join(OUT, "profiles.csv"), index=False)
    pd.concat(home_prof, ignore_index=True).to_csv(os.path.join(ROOT, "data", "pune_sim_profiles.csv"), index=False)
    print(f"wrote data/pune_sim_daily.csv: {len(sim):,} rows, {sim.household_id.nunique()} SIMULATED homes, "
          f"{len(ac)} with AC")


if __name__ == "__main__":
    main()
