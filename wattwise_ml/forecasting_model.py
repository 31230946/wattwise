"""
Training and testing of the daily forecast models. Every model is tested the same way:
5-fold GroupKFold grouped by household, so each test fold is ~30 homes the model
has NEVER seen (the cold-start case of a brand new app user).

  h=1  tomorrow         XGBoost + LSTM blend (weights from an inner validation split)
  h=7  next 7 days      XGBoost (predicts the average kWh/day, x7 for the total)
  h=30 next 30 days     XGBoost (average kWh/day, x30)

For every model we also store:
  * simple baselines on the same test homes (so the error has something to be compared to)
  * an 80% range: the 10th and 90th percentile of actual/predicted from the out-of-fold
    test predictions, per history length. So a user with 7 days of data gets a wider,
    honest range than one with 28 days.
  * XGBoost feature importance (gain), reported in the docs.
"""
import os
import random

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from tensorflow.keras import callbacks, layers, models

from preprocessing import DAILY_FEATURES, LAG_COLS
from ratio_model import RatioModel, inner_split

SEED = 42
RANGE_Q = (0.10, 0.90)


def set_seeds(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def metrics(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return {"rmse": float(mean_squared_error(y, p) ** 0.5), "mae": float(mean_absolute_error(y, p)),
            "wape": float(np.abs(y - p).sum() / y.sum() * 100)}


def fit_xgb(train_df, features, target):
    return RatioModel(features, "mean_7").fit(train_df, target)


# ---------------------------------------------------------------- LSTM for tomorrow
def build_lstm():
    m = models.Sequential([layers.Input(shape=(7, 1)), layers.LSTM(32),
                           layers.Dense(16, activation="relu"), layers.Dense(1)])
    m.compile(optimizer="adam", loss="mse")
    return m


def seq_view(df):
    return df[LAG_COLS].values[:, ::-1].astype(float)   # lag_7..lag_1 = oldest -> newest


def fit_tomorrow(train_df):
    """XGB + LSTM, blended by 1/RMSE on an inner validation split of TRAINING homes."""
    set_seeds()
    fit, val = inner_split(train_df)
    xm = RatioModel(DAILY_FEATURES, "mean_7").fit(fit, "y_1")
    sc = StandardScaler().fit(seq_view(fit))
    lm = build_lstm()
    lm.fit(sc.transform(seq_view(fit))[..., None], fit["y_1"].values,
           validation_data=(sc.transform(seq_view(val))[..., None], val["y_1"].values),
           epochs=40, batch_size=128, verbose=0,
           callbacks=[callbacks.EarlyStopping(patience=4, restore_best_weights=True)])
    rx = metrics(val["y_1"], xm.predict(val))["rmse"]
    rl = metrics(val["y_1"], lm.predict(sc.transform(seq_view(val))[..., None], verbose=0).ravel())["rmse"]
    w = (1 / rx) / (1 / rx + 1 / rl)
    return {"xgb": xm, "lstm": lm, "seq_scaler": sc, "w_xgb": float(w), "w_lstm": float(1 - w)}


def predict_tomorrow(b, df):
    x = b["xgb"].predict(df)
    l = b["lstm"].predict(b["seq_scaler"].transform(seq_view(df))[..., None], verbose=0).ravel()
    return b["w_xgb"] * x + b["w_lstm"] * l, x, l


# ---------------------------------------------------------------- baselines
def daily_baselines(df, H):
    if H == 1:
        return {"persistence (yesterday)": df["lag_1"].values, "mean of last 7 days": df["mean_7"].values}
    return {"mean of last 7 days": df["mean_7"].values, "mean of all history": df["mean_28"].values}


# ---------------------------------------------------------------- generic CV
MIN_RANGE_ROWS = 300   # a history length needs at least this many test cases to get its own range


def range_table(oof, hist_col):
    """80% range of actual/predicted, per history length (only lengths with enough test cases;
    the app maps any other length to the nearest one that has a range)."""
    oof = oof[oof["pred"] > 0].copy()
    oof["ratio"] = oof["actual"] / oof["pred"]
    tab = {}
    for h, g in oof.groupby(hist_col):
        if len(g) >= MIN_RANGE_ROWS:
            tab[int(h)] = [float(g["ratio"].quantile(RANGE_Q[0])), float(g["ratio"].quantile(RANGE_Q[1]))]
    allq = [float(oof["ratio"].quantile(RANGE_Q[0])), float(oof["ratio"].quantile(RANGE_Q[1]))]
    inside = ((oof["ratio"] >= allq[0]) & (oof["ratio"] <= allq[1])).mean()
    return {"by_history": tab, "overall": allq, "coverage_check": float(inside)}


def run_cv(rows, features, target, H, baseline_fn, hist_col, path, tomorrow=False, n_splits=5):
    df = rows.dropna(subset=[target]).reset_index(drop=True)
    res, oof = [], []
    for fold, (tr, te) in enumerate(GroupKFold(n_splits).split(df, groups=df["household_id"])):
        train_df, test_df = df.iloc[tr], df.iloc[te]
        y = test_df[target].values * H                      # back to TOTAL kWh for the horizon
        if tomorrow:
            b = fit_tomorrow(train_df)
            e, x, l = predict_tomorrow(b, test_df)
            preds = {"WattWise (XGBoost + LSTM)": e, "XGBoost alone": x, "LSTM alone": l}
        else:
            m = fit_xgb(train_df, features, target)
            e = m.predict(test_df)
            preds = {"WattWise (XGBoost)": e}
            print(f"    fold {fold}: trust in ML w={m.w}, start={m.base_col}", flush=True)
        preds.update(baseline_fn(test_df, H))
        for name, p in preds.items():
            res.append({"path": path, "horizon": H, "fold": fold, "model": name, **metrics(y, np.asarray(p) * H)})
        first_base = list(baseline_fn(test_df, H).values())[0]
        oof.append(pd.DataFrame({"household_id": test_df["household_id"].values, "fold": fold,
                                 "date": test_df["date"].values,
                                 "peer_band": test_df["peer_band"].values, "actual": y,
                                 "pred": np.asarray(e) * H, "baseline": np.asarray(first_base) * H,
                                 hist_col: test_df[hist_col].values}))
        print(f"  [{path} h={H}] fold {fold}: WAPE {metrics(y, np.asarray(e) * H)['wape']:.1f}%", flush=True)
    res = pd.DataFrame(res)
    oof = pd.concat(oof)
    oof.to_csv(f"models/cv_predictions_{path}_{H}.csv", index=False)
    return res, range_table(oof, hist_col)


def importance(model, features):
    g = model.m.get_booster().get_score(importance_type="gain")
    tot = sum(g.values()) or 1
    return {f: round(100 * g.get(f"f{i}", 0.0) / tot, 1) for i, f in enumerate(features)}


# ---------------------------------------------------------------- full training
def train_all(daily_rows, out_dir="models"):
    os.makedirs(out_dir, exist_ok=True)
    all_res, ranges, imp = [], {}, {}

    print("DAILY path")
    for H in (1, 7, 30):
        r, rng = run_cv(daily_rows, DAILY_FEATURES, f"y_{H}", H, daily_baselines, "history_days",
                        "daily", tomorrow=(H == 1))
        all_res.append(r)
        ranges[f"daily_{H}"] = rng
    res = pd.concat(all_res)
    res.to_csv(f"{out_dir}/cv_metrics_by_fold.csv", index=False)
    summary = res.groupby(["path", "horizon", "model"])[["rmse", "mae", "wape"]].agg(["mean", "std"]).round(3)
    summary.to_csv(f"{out_dir}/cv_summary.csv")
    print(summary.to_string())

    # final models on ALL homes (these are what the app uses)
    d = daily_rows
    tomorrow = fit_tomorrow(d.dropna(subset=["y_1"]))
    daily_bundle = {"features": DAILY_FEATURES, "w_xgb": tomorrow["w_xgb"], "w_lstm": tomorrow["w_lstm"],
                    "xgb_1": tomorrow["xgb"], "seq_scaler": tomorrow["seq_scaler"]}
    tomorrow["lstm"].save(f"{out_dir}/lstm_tomorrow.keras")
    imp["daily_1"] = importance(tomorrow["xgb"], DAILY_FEATURES)
    print(f"  final daily h=1: trust in ML w={tomorrow['xgb'].w}, blend w_xgb={tomorrow['w_xgb']:.2f}")
    for H in (7, 30):
        m = fit_xgb(d.dropna(subset=[f"y_{H}"]), DAILY_FEATURES, f"y_{H}")
        daily_bundle[f"xgb_{H}"] = m
        imp[f"daily_{H}"] = importance(m, DAILY_FEATURES)
        print(f"  final daily h={H}: trust in ML w={m.w}, start={m.base_col}")
    daily_bundle["ranges"] = ranges
    joblib.dump(daily_bundle, f"{out_dir}/daily_bundle.joblib")
    return res, summary, ranges, imp
