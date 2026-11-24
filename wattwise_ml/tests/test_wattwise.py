"""
Run from the project folder (after train.py):   python -m pytest -q tests
These double as the test cases for the Testing & Validation Report.
"""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import appliance_estimator as ae  # noqa: E402
import carbon  # noqa: E402
import tariff  # noqa: E402

SAMPLES = os.path.join(ROOT, "examples", "sample_requests")
load = lambda name: json.load(open(os.path.join(SAMPLES, name)))  # noqa: E731
HAVE_MODELS = os.path.exists(os.path.join(ROOT, "models", "daily_bundle.joblib"))
needs_models = pytest.mark.skipif(not HAVE_MODELS, reason="run train.py first")


# ---------- tariff ----------
def test_telescopic_bill_306_units():
    assert tariff.monthly_bill(306) == pytest.approx(2884.26, abs=0.01)   # 100*4.32+200*9.40+6*12.51+306*1.2+130


def test_no_cliff_at_slab_line():
    assert tariff.monthly_bill(301) - tariff.monthly_bill(300) == pytest.approx(13.71, abs=0.01)


def test_saving_across_slab_line():
    assert tariff.saving_from_cut(306, 33) == pytest.approx(6 * 13.71 + 27 * 10.60, abs=0.05)


def test_slab_breakdown_adds_up():
    b = tariff.slab_breakdown(306)
    assert sum(r["units"] for r in b["slabs"]) == pytest.approx(306)
    assert sum(r["energy_rs"] for r in b["slabs"]) + b["wheeling_rs"] + b["fixed_rs"] == pytest.approx(b["total_rs"], abs=0.05)


def test_shift_saves_nothing_without_smart_meter():
    assert tariff.saving_from_shift(30, False) == 0
    assert tariff.saving_from_shift(30, True) == pytest.approx(24.0)


# ---------- carbon ----------
def test_carbon_factor():
    assert carbon.kg_co2(100) == pytest.approx(72.7)


def test_expected_savings_range():
    e = carbon.expected_savings(300)
    assert e["low"]["pct"] == 4 and e["high"]["pct"] == 7 and e["is_estimate"]
    assert e["low"]["kg_co2_per_month"] < e["high"]["kg_co2_per_month"]


# ---------- appliance estimator ----------
def test_breakdown_adds_up_to_total():
    est = ae.estimate([{"type": "ac_1_5_ton", "count": 1, "hours_per_day": 4, "when": "evening"},
                       {"type": "fridge", "count": 1, "when": "all_day"}], 8.0)
    assert sum(i["kwh"] for i in est["items"]) == pytest.approx(8.0, abs=0.02)


def test_hours_look_off_flag():
    est = ae.estimate([{"type": "led_lights", "count": 1, "hours_per_day": 1, "when": "evening"}], 10.0)
    assert est["hours_look_off"] is True


# ---------- engine (no server) ----------
@needs_models
def test_bill_screen_no_ml():
    import engine
    out = engine.bill_screen(load("bill.json"))
    assert out["simple_projection"]["is_ml_forecast"] is False
    assert out["last_month"]["carbon"]["kg_co2"] == pytest.approx(306 * 0.727, abs=0.1)


@needs_models
def test_daily_three_horizons_consistent():
    import engine
    f = engine.forecast_daily(load("daily_full.json"))["forecast"]
    for k in ("next_day", "next_7_days", "next_30_days"):
        lo, hi = f[k]["range_80pct"]
        assert lo <= f[k]["kwh"] <= hi
    assert 3 < f["next_30_days"]["kwh"] / f["next_7_days"]["kwh"] < 6   # 30 days ~ 4.3 weeks


@needs_models
def test_daily_needs_seven_days():
    import engine
    with pytest.raises(engine.InputError):
        engine.forecast_daily({"daily_kwh": [5, 5, 5]})


@needs_models
def test_meter_readings_equal_kwh():
    import engine
    kwh = [9.1, 8.7, 10.2, 9.8, 11.0, 10.5, 9.9]
    readings = list(np.cumsum([1000.0] + kwh))
    a = engine.forecast_daily({"daily_kwh": kwh, "last_reading_date": "2026-10-12"})["forecast"]
    b = engine.forecast_daily({"daily_meter_readings": readings, "last_reading_date": "2026-10-12"})["forecast"]
    assert a["next_7_days"]["kwh"] == pytest.approx(b["next_7_days"]["kwh"], abs=0.05)


@needs_models
def test_meter_readings_must_not_drop():
    import engine
    with pytest.raises(engine.InputError):
        engine.forecast_daily({"daily_meter_readings": [100, 105, 90, 110, 115, 120, 125, 130]})


@needs_models
def test_ranges_have_enough_test_cases():
    import json as _j
    r = _j.load(open(os.path.join(ROOT, "models", "results.json")))["ranges_80pct"]
    for key, v in r.items():
        for hist, (lo, hi) in v["by_history"].items():
            assert lo < 1 < hi, (key, hist)        # every range contains the forecast itself


@needs_models
def test_tip_has_rs_and_co2():
    import engine
    t = engine.forecast_daily(load("daily_full.json"))["recommendation"]
    if t["action"] in ("reduce_load_general", "appliance_efficiency_tip"):
        assert t["saving_rs_per_month"] > 0 and t["saving_kg_co2_per_month"] > 0


# ---------- HTTP API ----------
@pytest.fixture(scope="module")
def client():
    if not HAVE_MODELS:
        pytest.skip("run train.py first")
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_meta(client):
    m = client.get("/meta").json()
    assert "ac_1_5_ton" in m["appliance_types"] and m["carbon_factor"]["kg_co2_per_kwh"] == 0.727


@pytest.mark.parametrize("path,file", [("/bill", "bill.json"), ("/forecast/daily", "daily_minimal.json"),
                                       ("/forecast/daily", "daily_full.json"),
                                       ("/homes-like-yours", "homes_like_yours.json")])
def test_all_samples(client, path, file):
    assert client.post(path, json=load(file)).status_code == 200


def test_bad_input_is_422_with_message(client):
    r = client.post("/forecast/daily", json={"daily_kwh": [5, -1, 5, 5, 5, 5, 5]})
    assert r.status_code == 422 and "negative" in r.json()["detail"]


def test_too_few_days_message_is_readable(client):
    r = client.post("/forecast/daily", json={"daily_kwh": [1, 2]})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str) and "daily_kwh" in r.json()["detail"]


def test_unknown_appliance_is_422(client):
    r = client.post("/forecast/daily", json={**load("daily_minimal.json"),
                                             "appliances": [{"type": "spaceship", "hours_per_day": 1}]})
    assert r.status_code == 422


# ---------- offline CLI ----------
@needs_models
def test_cli_offline_daily():
    out = subprocess.run([sys.executable, "cli.py", "daily", "--kwh", "6.1", "5.8", "6.4", "6.0", "5.5", "7.0", "6.6"],
                         capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert out.returncode == 0 and json.loads(out.stdout)["path"] == "daily"


# ---------- REFIT script (fake file in REFIT format: tests the code path ONLY) ----------
def test_refit_script_runs_on_fake_file(tmp_path):
    import refit_validation as rv
    t = pd.date_range("2014-01-01", periods=2 * 24 * 60, freq="1min")
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"Time": t, "Unix": 0, "Aggregate": 500.0,
                       **{f"Appliance{i}": 0.0 for i in range(1, 10)}, "Issues": 0})
    df["Appliance1"] = np.where(rng.random(len(t)) < 0.35, 150.0, 0.0)
    df.loc[df.Time.dt.hour == 19, "Appliance8"] = 2000.0
    p = tmp_path / "CLEAN_House2.csv"
    df.to_csv(p, index=False)
    res, by_app = rv.validate(str(p), house=2, days=2)
    assert set(by_app.index) >= {"fridge", "kettle"}


# ---------- simulated Pune homes (demo data; labelled SIMULATED) ----------
SIM = os.path.join(ROOT, "data", "pune_sim_daily.csv")
needs_sim = pytest.mark.skipif(not os.path.exists(SIM), reason="run pune_sim/make_pune_sim.py first")


@needs_sim
def test_pune_sim_is_labelled_and_calibrated():
    d = pd.read_csv(SIM)
    assert (d["is_simulated"] == 1).all() and d.isna().sum().sum() == 0
    monthly = d.groupby("household_id")["daily_kwh"].mean().mean() * 30.4375
    assert 156 * 0.9 <= monthly <= 156 * 1.1          # Prayas Pune city average, +/-10%
    assert 0.25 <= d.groupby("household_id")["has_ac"].first().mean() <= 0.35


@needs_sim
def test_pune_sim_homes_not_training_homes():
    from load_real_lcl import pick_households
    homes = pd.read_csv(os.path.join(ROOT, "pune_sim", "out", "homes.csv"))
    train = set(pick_households("data/LCL_2013.csv", 150, 42)) if os.path.exists("data/LCL_2013.csv") else set()
    assert not (set(homes["source_lcl_id"]) & train)


@needs_sim
def test_homes_like_yours_keeps_bills_and_labels():
    import engine
    out = engine.homes_like_yours(load("homes_like_yours.json"))
    assert out["data_label"].startswith("Based on SIMULATED")
    year = {r["month"]: r for r in out["year_outlook"]}
    assert len(year) == 12 and year["Apr"]["units"] == 210 and year["Apr"]["source"] == "your bill"
    assert year["May"]["source"].startswith("homes like yours")
    assert year["May"]["units"] > year["Aug"]["units"]          # AC home: May above monsoon months
    assert len(out["typical_day"]["hourly_watts"]) == 24


@needs_models
@needs_sim
def test_homes_like_yours_endpoint(client):
    r = client.post("/homes-like-yours", json=load("homes_like_yours.json"))
    assert r.status_code == 200 and r.json()["matched"]["homes"] == 5
    bad = client.post("/homes-like-yours", json={"monthly_units": [150], "last_bill_month": 13})
    assert bad.status_code == 422 and isinstance(bad.json()["detail"], str)


# ---------- appliance star ratings (BEE-based; still an estimate scaled to the meter total) ----------
def test_star_rating_lowers_ac_estimate():
    ph = lambda s: ae.per_hour_kwh(ae.CATALOG["ac_1_5_ton"], {"star_rating": s})[0]  # noqa: E731
    assert ph(1) > ph(3) > ph(5) > 0
    assert ae.per_hour_kwh(ae.CATALOG["ac_1_5_ton"], {})[0] == ph(3)          # no star = assumed 3-star


def test_fridge_label_and_fan_default():
    per_hour, basis = ae.per_hour_kwh(ae.CATALOG["fridge"], {"label_kwh_per_year": 365})
    assert per_hour * 24 == pytest.approx(1.0) and "label" in basis
    assert ae.per_hour_kwh(ae.CATALOG["ceiling_fan"], {})[0] == pytest.approx(0.070)   # non-star fan
    out = ae.estimate([{"type": "fridge", "count": 1, "hours_per_day": 3, "when": "all_day", "star_rating": 5},
                       {"type": "tv", "count": 1, "hours_per_day": 3, "when": "evening"}], 5.0)
    assert out["items"][0]["hours_per_day"] == 24 or out["items"][1]["hours_per_day"] == 24


@needs_models
def test_api_star_rating(client):
    body = {**load("daily_minimal.json"), "appliances": [
        {"type": "ac_1_5_ton", "count": 1, "hours_per_day": 4, "when": "night", "star_rating": 5},
        {"type": "fridge", "count": 1, "when": "all_day", "star_rating": 3}]}
    r = client.post("/forecast/daily", json=body)
    assert r.status_code == 200
    assert {i["basis"] for i in r.json()["appliance_breakdown"]["items"]} == {"BEE 5-star", "BEE 3-star"}
    bad = {**body, "appliances": [{"type": "tv", "count": 1, "hours_per_day": 3, "star_rating": 4}]}
    assert client.post("/forecast/daily", json=bad).status_code == 422
