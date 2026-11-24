"""
Raw meter readings -> clean daily table -> model-ready rows for the DAILY forecast.

Daily table (one row per household per complete day):
  daily_kwh     total kWh that day
  evening_kwh   kWh 18:00-22:00 (evening peak window)
  solar_kwh     kWh 09:00-17:00 (MSEDCL solar hours)
  baseload_kw   average power 01:00-05:00 = always-on load (fridge, standby...)

DAILY rows: a "forecast start day" t, with up to 28 days of history before it.
  Each row gets a random history length L in {7, 14, 21, 28}, so the model
  learns to work for new users with only a week of data AND for users with a month.
  Targets: y_1 (day t), y_7 (days t..t+6, as average kWh/day), y_30 (days t..t+29, avg/day).

Dwelling type / household size are never model inputs (the LCL data has no such
metadata). Peer bands for "similar homes" use only each home's first 28 days, and
those days are never forecast targets (no leakage).
"""
import numpy as np
import pandas as pd

EVENING_HOURS = (18, 22)
SOLAR_HOURS = (9, 17)
NIGHT_HOURS = (1, 5)
BAND_LABELS = ["1bhk", "2bhk", "3bhk", "villa"]
PEER_BAND_DAYS = 28

DAILY_MAX_HISTORY = 28
DAILY_HISTORY_CHOICES = (7, 14, 21, 28)
DAILY_HORIZONS = (1, 7, 30)


DAILY_FEATURES = [f"lag_{k}" for k in range(1, 8)] + [
    "mean_7", "std_7", "min_7", "max_7", "mean_14", "mean_28", "trend_7_vs_28",
    "history_days", "evening_share", "baseload_kw", "dow", "is_weekend",
]
LAG_COLS = [f"lag_{k}" for k in range(1, 8)]


def load_raw(path="data/household_data.csv"):
    return pd.read_csv(path, parse_dates=["timestamp"])


def daily_aggregate(df):
    df = df.copy()
    df["date"] = df["timestamp"].dt.normalize()
    h = df["timestamp"].dt.hour
    df["ev"] = np.where((h >= EVENING_HOURS[0]) & (h < EVENING_HOURS[1]), df["kwh"], 0.0)
    df["so"] = np.where((h >= SOLAR_HOURS[0]) & (h < SOLAR_HOURS[1]), df["kwh"], 0.0)
    df["ni"] = np.where((h >= NIGHT_HOURS[0]) & (h < NIGHT_HOURS[1]), df["kwh"], 0.0)
    daily = df.groupby(["household_id", "date"]).agg(
        daily_kwh=("kwh", "sum"), evening_kwh=("ev", "sum"), solar_kwh=("so", "sum"),
        night_kwh=("ni", "sum"), n_readings=("kwh", "size")).reset_index()
    per_day = int(daily["n_readings"].mode().iloc[0])          # 48 for LCL half-hours
    daily = daily[daily["n_readings"] == per_day].copy()        # complete days only
    daily["baseload_kw"] = daily["night_kwh"] / (NIGHT_HOURS[1] - NIGHT_HOURS[0])
    daily["evening_share"] = daily["evening_kwh"] / daily["daily_kwh"].clip(lower=1e-6)
    daily["dow"] = daily["date"].dt.dayofweek
    daily["is_weekend"] = (daily["dow"] >= 5).astype(int)
    daily = daily[daily["daily_kwh"] > 0.2]                     # empty house / meter off
    return daily.drop(columns=["night_kwh", "n_readings"]).sort_values(
        ["household_id", "date"]).reset_index(drop=True)


def assign_peer_bands(daily):
    first = daily.groupby("household_id").head(PEER_BAND_DAYS)
    hh_mean = first.groupby("household_id")["daily_kwh"].mean()
    bands = pd.qcut(hh_mean, 4, labels=BAND_LABELS)
    daily = daily.copy()
    daily["peer_band"] = daily["household_id"].map(bands).astype(str)
    daily["in_band_window"] = daily.index.isin(first.index)
    return daily


def peer_stats(daily):
    s = daily.groupby("peer_band").agg(
        peer_mean_kwh=("daily_kwh", "mean"), peer_median_kwh=("daily_kwh", "median"),
        evening_share=("evening_share", "median"), baseload_kw=("baseload_kw", "median"),
        n_households=("household_id", "nunique"))
    return s.round(3).to_dict(orient="index")


# ---------------------------------------------------------------- daily features
def daily_feature_row(hist_kwh, evening_share, baseload_kw, dow):
    """hist_kwh: oldest -> newest, 7 to 28 values. Used by BOTH training and the app,
    so the model always sees features built exactly the same way."""
    h = np.asarray(hist_kwh, float)[-DAILY_MAX_HISTORY:]
    last7 = h[-7:]
    m7 = last7.mean()
    m14 = h[-14:].mean()
    m28 = h.mean()
    row = {f"lag_{k}": h[-k] for k in range(1, 8)}
    row.update(mean_7=m7, std_7=last7.std(), min_7=last7.min(), max_7=last7.max(),
               mean_14=m14, mean_28=m28, trend_7_vs_28=m7 / max(m28, 1e-6),
               history_days=len(h), evening_share=evening_share, baseload_kw=baseload_kw,
               dow=dow, is_weekend=int(dow >= 5))
    return row


def make_daily_rows(daily, seed=42):
    rng = np.random.default_rng(seed)
    out = []
    for hid, g in daily.groupby("household_id"):
        g = g.reset_index(drop=True)
        d = g["date"].values
        kwh = g["daily_kwh"].values
        ev, base = g["evening_kwh"].values, g["baseload_kw"].values
        band_win = g["in_band_window"].values if "in_band_window" in g else np.zeros(len(g), bool)
        band = g["peer_band"].iloc[0] if "peer_band" in g else ""
        day = lambda i: d[i].astype("datetime64[D]")  # noqa: E731
        for i in range(DAILY_MAX_HISTORY, len(g)):
            L = int(rng.choice(DAILY_HISTORY_CHOICES))
            # history i-L..i-1 must be consecutive calendar days
            if (day(i) - day(i - L)).astype(int) != L or band_win[i]:
                continue
            hist = kwh[i - L:i]
            row = daily_feature_row(hist, ev[i - L:i].sum() / max(hist.sum(), 1e-6),
                                    base[i - L:i].mean(), int(g["dow"].values[i]))
            for H in DAILY_HORIZONS:
                ok = i + H <= len(g) and (day(i + H - 1) - day(i)).astype(int) == H - 1
                row[f"y_{H}"] = kwh[i:i + H].mean() if ok else np.nan   # avg kWh/day
            row.update(household_id=hid, date=d[i], peer_band=band)
            out.append(row)
    return pd.DataFrame(out)
