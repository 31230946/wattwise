"""
Trains EVERYTHING. Run this (not the individual files):

    python train.py --real        # rebuild data from the LCL file (150 homes), then train  (~10-15 min)
    python train.py               # train on data/household_data.csv as it already is
    python train.py --synthetic   # quick test on fake data (~2 min)

Writes to models/:
  daily_bundle.joblib + lstm_tomorrow.keras   daily path (tomorrow, 7 days, 30 days)
  bandit.joblib                               tip picker (LinUCB)
  peer_stats.json                             "similar homes" defaults
  results.json                                every number reported in the paper/docs
  cv_summary.csv, cv_metrics_by_fold.csv      full test results
"""
import argparse
import json
import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import joblib  # noqa: E402

import bandit_recommender as br  # noqa: E402
import forecasting_model as fm  # noqa: E402
from preprocessing import (assign_peer_bands, daily_aggregate, load_raw, make_daily_rows,  # noqa: E402
                           peer_stats)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--n", type=int, default=150)
    a = ap.parse_args()
    os.makedirs("models", exist_ok=True)
    if a.real:
        from load_real_lcl import load_real
        load_real(a.n)
    elif a.synthetic:
        from synthetic_data_generator import generate
        generate(n_days=200).to_csv("data/household_data.csv", index=False)

    print("== 1/4 preprocessing ==", flush=True)
    daily = assign_peer_bands(daily_aggregate(load_raw()))
    drows = make_daily_rows(daily)
    stats = peer_stats(daily)
    with open("models/peer_stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    print(f"{daily.household_id.nunique()} homes, {len(daily):,} complete days -> "
          f"{len(drows):,} daily rows", flush=True)

    print("\n== 2/4 forecast models (5-fold, unseen homes) ==", flush=True)
    res, summary, ranges, imp = fm.train_all(drows)

    print("\n== 3/4 bandit ==", flush=True)
    bsum, mix = br.evaluate(daily)
    print(bsum.to_string())
    joblib.dump(br.train_offline(daily, daily["household_id"].unique(), n_interactions=6000), "models/bandit.joblib")

    print("\n== 4/4 results.json ==")
    m = res.groupby(["path", "horizon", "model"])[["rmse", "mae", "wape"]].mean().round(3)
    s = res.groupby(["path", "horizon", "model"])[["rmse", "mae", "wape"]].std().round(3)
    forecast = {}
    for (path, H, model), row in m.iterrows():
        forecast.setdefault(f"{path}_{H}", {})[model] = {**row.to_dict(),
                                                         **{f"{k}_std": v for k, v in s.loc[(path, H, model)].items()}}
    results = {
        "data": {"homes": int(daily.household_id.nunique()), "complete_days": int(len(daily)),
                 "daily_rows": int(len(drows))},
        "peer_stats": stats, "forecast_cv": forecast, "ranges_80pct": ranges,
        "feature_importance_gain_pct": imp,
        "bandit_eval": bsum.to_dict(orient="index"), "bandit_action_mix": mix, "bandit_sim": br.SIM,
    }
    with open("models/results.json", "w") as f:
        json.dump(results, f, indent=2, default=float)
    print("saved models/results.json\nNext: python -m pytest -q tests   then   python -m uvicorn api:app --port 8000")


if __name__ == "__main__":
    main()
