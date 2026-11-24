"""
Carbon footprint: kWh x the Indian grid emission factor (CEA, 0.727 kg CO2/kWh for 2023-24).
Settings and sources are in carbon_config.json.
"""
import json
import os

import tariff

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "carbon_config.json")) as f:
    CARBON = json.load(f)
FACTOR = CARBON["kg_co2_per_kwh"]


def kg_co2(kwh):
    return round(max(0.0, float(kwh)) * FACTOR, 1)


def expected_savings(monthly_units, has_smart_meter=False):
    """What a home could save over the following months IF it responds like households in
    published feedback studies (4-7%). Clearly an estimate from other studies."""
    e = CARBON["expected_saving_from_feedback"]
    out = {}
    for key, pct in (("low", e["low_pct"]), ("high", e["high_pct"])):
        units = monthly_units * pct / 100
        out[key] = {"pct": pct, "units_per_month": round(units, 1), "kg_co2_per_month": kg_co2(units),
                    "rs_per_month": tariff.saving_from_cut(monthly_units, units)}
    return {
        **out,
        "message": (f"Homes that follow energy tips typically use {e['low_pct']}-{e['high_pct']}% less. "
                    f"For you that is about {out['low']['kg_co2_per_month']:.0f}-{out['high']['kg_co2_per_month']:.0f} kg CO2 "
                    f"and Rs {out['low']['rs_per_month']:.0f}-{out['high']['rs_per_month']:.0f} a month."),
        "basis": e["_basis"],
        "is_estimate": True,
    }


def summary(kwh, period_label):
    return {"kwh": round(kwh, 1), "kg_co2": kg_co2(kwh), "period": period_label,
            "factor_kg_per_kwh": FACTOR, "source": f"CEA CO2 Baseline Database v20, {CARBON['year']}"}
