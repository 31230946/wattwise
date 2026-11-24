"""
Loads the real Low Carbon London 2013 dataset (refactored by TU Delft) and
turns it into the long format the rest of the pipeline uses:

    household_id, timestamp, kwh

Dataset: https://data.4tu.nl/datasets/fbbe775b-48d8-469f-a39b-b64488bfd6fd
Original source: UK Power Networks, Low Carbon London project (CC-BY).

File facts (from the dataset README):
  * WIDE format: first column DateTime (GMT), then one column per household (MAC######)
  * each value = kWh used in the PRECEDING half hour
      -> a reading stamped 00:30 covers 00:00-00:30, and the reading stamped
         2014-01-01 00:00 actually belongs to 31 Dec 2013, 23:30-24:00.
         We shift every timestamp back by 30 min so the date/hour are right.
  * only 'Std' (flat tariff) households are kept in this release
  * missing readings are NaN

Limitation (put this in the report): this release has NO household metadata
(no dwelling type, no occupant count). So the forecasting model does not use
dwelling type or household size at all. For the "similar homes" peer groups we
split households into 4 usage bands using ONLY their first 28 days of data;
those 28 days are then never used as forecast targets (no leakage).

Usage:
    python3 load_real_lcl.py                 # 150 random households (default)
    python3 load_real_lcl.py --n 300         # more households
Accepts either data/LCL_2013.csv or data/LCL_2013_kWh.csv.zip.
"""
import argparse
import os
import numpy as np
import pandas as pd

CANDIDATES = ["data/LCL_2013.csv", "data/LCL_2013_kWh.csv.zip", "data/LCL_2013_kWh_csv.zip"]
OUT_CSV = "data/household_data.csv"


def find_raw():
    for p in CANDIDATES:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(
        "Put the LCL file in data/ (LCL_2013.csv or LCL_2013_kWh.csv.zip). "
        "Download: https://data.4tu.nl/datasets/fbbe775b-48d8-469f-a39b-b64488bfd6fd")


def pick_households(path, n_households, seed=42):
    header = pd.read_csv(path, nrows=0)
    all_ids = [c for c in header.columns if c.startswith("MAC")]
    rng = np.random.default_rng(seed)
    return sorted(rng.choice(all_ids, size=min(n_households, len(all_ids)), replace=False).tolist())


def load_real(n_households=150, seed=42):
    path = find_raw()
    chosen = pick_households(path, n_households, seed)
    print(f"reading {len(chosen)} of 4443 households from {path} (takes a minute)...")
    wide = pd.read_csv(path, usecols=["DateTime"] + chosen).copy()
    wide["timestamp"] = pd.to_datetime(wide["DateTime"].str.slice(0, 19)) - pd.Timedelta(minutes=30)
    wide = wide.drop(columns="DateTime")

    long = wide.melt(id_vars="timestamp", var_name="household_id", value_name="kwh")
    long = long.dropna(subset=["kwh"])
    long = long[(long["kwh"] >= 0) & (long["kwh"] < 10)]  # a half-hour > 10 kWh (20 kW) is a meter glitch for a home
    long = long[["household_id", "timestamp", "kwh"]].sort_values(["household_id", "timestamp"])
    long.to_csv(OUT_CSV, index=False)
    print(f"wrote {OUT_CSV}: {len(long):,} half-hour readings, {long.household_id.nunique()} households")
    return long


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    load_real(a.n, a.seed)
