"""
Fake hourly readings in the same shape as the real data, used only by
`python train.py --synthetic` to check the training pipeline runs end to end
without the LCL download. Never used for any reported result.
"""
import numpy as np
import pandas as pd

def generate(n_households=40, n_days=120, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    for hid in range(n_households):
        dwelling = rng.choice(["1bhk", "2bhk", "3bhk", "villa"], p=[0.3, 0.35, 0.25, 0.1])
        size_map = {"1bhk": 1.5, "2bhk": 2.5, "3bhk": 3.5, "villa": 5.0}
        household_size = int(max(1, rng.normal(size_map[dwelling], 0.7)))
        base_load = 0.15 + 0.05 * household_size + rng.normal(0, 0.03)   # kWh baseline per hour
        evening_peak = 0.4 + 0.08 * household_size + rng.normal(0, 0.05)  # extra kWh at peak

        start = pd.Timestamp("2025-01-01")
        for day in range(n_days):
            date = start + pd.Timedelta(days=day)
            is_weekend = date.dayofweek >= 5
            for hour in range(24):
                # load curve shape: low at night, small morning bump, big evening peak
                if 0 <= hour < 6:
                    shape = 0.4
                elif 6 <= hour < 9:
                    shape = 1.1
                elif 9 <= hour < 17:
                    shape = 0.8 if not is_weekend else 1.0
                elif 17 <= hour < 22:
                    shape = 2.2
                else:
                    shape = 0.9
                noise = rng.normal(0, 0.06)
                kwh = max(0.02, base_load * shape + (evening_peak if 18 <= hour <= 21 else 0) * 0.5 + noise)
                rows.append((hid, dwelling, household_size, date + pd.Timedelta(hours=hour), kwh))

    df = pd.DataFrame(rows, columns=["household_id", "dwelling_type", "household_size", "timestamp", "kwh"])
    return df

if __name__ == "__main__":
    df = generate()
    df.to_csv("data/household_data.csv", index=False)
    print(f"wrote data/household_data.csv -- {df.shape[0]} rows, {df.household_id.nunique()} households")
