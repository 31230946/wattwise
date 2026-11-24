"""
Stress test: run the SAVED WattWise models (trained on 148 London homes) on
  (a) 146 London homes they never saw (real data), and
  (b) the same 146 homes turned into SIMULATED Pune homes.

(a) is a real extra check on unseen homes. (b) only shows how the forecast copes with a
Pune-like level and season (AC summer); it is NOT evidence of accuracy on real Indian homes.

Run from the project root (after make_pune_sim.py):  python pune_sim/stress_test_pune.py
Writes pune_sim/out/stress_test.csv
"""
import os
import sys

import joblib
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
from preprocessing import DAILY_FEATURES, assign_peer_bands, make_daily_rows  # noqa: E402

OUT = os.path.join(ROOT, "pune_sim", "out")


def wape(y, p):
    return float(np.abs(y - p).sum() / y.sum() * 100)


def period(d):
    """Season of the forecast start day (simulated Pune calendar)."""
    md = d.month * 100 + d.day
    if 308 <= md <= 531:
        return "AC season starts (8 Mar - 31 May)"
    if 601 <= md <= 630:
        return "AC season ends (June)"
    return "rest of year"


def coverage(y, p, ranges, hist):
    lo = np.array([ranges["by_history"].get(int(h), ranges["overall"])[0] for h in hist])
    hi = np.array([ranges["by_history"].get(int(h), ranges["overall"])[1] for h in hist])
    r = y / np.clip(p, 1e-6, None)
    return float(((r >= lo) & (r <= hi)).mean() * 100)


def main():
    from tensorflow import keras
    db = joblib.load(os.path.join(ROOT, "models", "daily_bundle.joblib"))
    lstm = keras.models.load_model(os.path.join(ROOT, "models", "lstm_tomorrow.keras"))
    sources = {
        "London, unseen homes (real)": pd.read_csv(os.path.join(OUT, "london_source_daily.csv"), parse_dates=["date"]),
        "Pune (SIMULATED)": pd.read_csv(os.path.join(ROOT, "data", "pune_sim_daily.csv"), parse_dates=["date"]),
    }
    out = []
    for name, daily in sources.items():
        daily = assign_peer_bands(daily)
        rows = make_daily_rows(daily)
        X = rows[DAILY_FEATURES]
        x1 = db["xgb_1"].predict(X)
        seq = db["seq_scaler"].transform(rows[[f"lag_{k}" for k in range(7, 0, -1)]].values)[..., None]
        l1 = lstm.predict(seq, verbose=0, batch_size=2048).ravel()
        preds = {1: np.clip(db["w_xgb"] * x1 + db["w_lstm"] * l1, 0, None),
                 7: np.clip(db["xgb_7"].predict(X), 0, None), 30: np.clip(db["xgb_30"].predict(X), 0, None)}
        rows["period"] = pd.to_datetime(rows["date"]).map(period)
        for H, label in ((1, "next day"), (7, "next 7 days"), (30, "next 30 days")):
            ok = rows[f"y_{H}"].notna().values
            for per in ["all"] + sorted(rows["period"].unique()):
                sel = ok & ((rows["period"] == per).values if per != "all" else True)
                y, p, b = rows[f"y_{H}"].values[sel], preds[H][sel], rows["mean_7"].values[sel]
                out.append({"data": name, "path": "daily", "forecast": label, "period": per, "n": int(sel.sum()),
                            "wape_model": round(wape(y, p), 1), "wape_avg_last_7_days": round(wape(y, b), 1),
                            "range_80_coverage_pct": round(coverage(y, p, db["ranges"][f"daily_{H}"],
                                                                   rows["history_days"].values[sel]), 1)})
    df = pd.DataFrame(out)
    df.to_csv(os.path.join(OUT, "stress_test.csv"), index=False)
    pd.set_option("display.width", 200)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
