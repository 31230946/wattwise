"""
Maharashtra (MSEDCL) residential bill calculator.

Billing is TELESCOPIC: each slab's rate applies only to the units that fall
inside that slab. So a home using 320 units pays the 1-100 rate on the first
100, the 101-300 rate on the next 200, and the 301-500 rate on the last 20.
There is no "cliff" where all units jump to a higher rate.

Rates live in tariff_config.json so they can be updated without touching code.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "tariff_config.json")) as f:
    TARIFF = json.load(f)


def energy_charge(units):
    """Telescopic energy charge in Rs for `units` kWh in one billing month."""
    units = max(0.0, float(units))
    total, lower = 0.0, 0.0
    for slab in TARIFF["slabs"]:
        upper = slab["upto_units"] if slab["upto_units"] is not None else float("inf")
        in_slab = max(0.0, min(units, upper) - lower)
        total += in_slab * slab["energy_rs_per_kwh"]
        if units <= upper:
            break
        lower = upper
    return total


def monthly_bill(units, solar_hour_units=0.0, has_smart_meter=False):
    """Bill in Rs (energy + wheeling + fixed). Duty and FAC are left out (see config note)."""
    bill = energy_charge(units) + units * TARIFF["wheeling_charge_rs_per_kwh"] + TARIFF["fixed_charge_rs_per_month"]
    if has_smart_meter:
        bill -= solar_hour_units * TARIFF["tod"]["solar_rebate_rs_per_kwh"]
    return round(bill, 2)


def slab_breakdown(units):
    """Rows for a bill table: how many units fell in each slab and what they cost."""
    units = max(0.0, float(units))
    rows, lower = [], 0.0
    for slab in TARIFF["slabs"]:
        upper = slab["upto_units"] if slab["upto_units"] is not None else float("inf")
        n = max(0.0, min(units, upper) - lower)
        if n > 0:
            rows.append({"slab": f"{int(lower) + 1}-{slab['upto_units'] or 'above'}",
                         "units": round(n, 1), "rate_rs": slab["energy_rs_per_kwh"],
                         "energy_rs": round(n * slab["energy_rs_per_kwh"], 2)})
        if units <= upper:
            break
        lower = upper
    return {"slabs": rows,
            "wheeling_rs": round(units * TARIFF["wheeling_charge_rs_per_kwh"], 2),
            "fixed_rs": TARIFF["fixed_charge_rs_per_month"],
            "total_rs": monthly_bill(units),
            "excludes": "electricity duty, fuel adjustment charge"}


def current_slab(units):
    lower = 0
    for slab in TARIFF["slabs"]:
        upper = slab["upto_units"]
        if upper is None or units <= upper:
            return {"from_units": lower + 1, "to_units": upper,
                    "energy_rs_per_kwh": slab["energy_rs_per_kwh"]}
        lower = upper


def marginal_rate(units):
    """What the NEXT unit costs (energy + wheeling) at this monthly usage."""
    return current_slab(units)["energy_rs_per_kwh"] + TARIFF["wheeling_charge_rs_per_kwh"]


def saving_from_cut(monthly_units, units_cut):
    """Rs saved per month if monthly usage drops by `units_cut`. Exact, across slab lines."""
    units_cut = max(0.0, min(units_cut, monthly_units))
    return round(monthly_bill(monthly_units) - monthly_bill(monthly_units - units_cut), 2)


def saving_from_shift(units_shifted, has_smart_meter):
    """Rs saved per month by moving `units_shifted` into solar hours (09:00-17:00)."""
    if not has_smart_meter:
        return 0.0
    return round(units_shifted * TARIFF["tod"]["solar_rebate_rs_per_kwh"], 2)


def bill_summary(monthly_units, has_smart_meter=False, solar_share=0.0):
    units = float(monthly_units)
    slab = current_slab(units)
    next_line = slab["to_units"]
    lower_line = slab["from_units"] - 1
    return {
        "monthly_units": round(units, 1),
        "estimated_bill_rs": monthly_bill(units, units * solar_share, has_smart_meter),
        "current_slab": f"{slab['from_units']}-{slab['to_units'] or 'above'} units",
        "marginal_rate_rs_per_kwh": round(marginal_rate(units), 2),
        "units_above_lower_slab_line": round(units - lower_line, 1) if lower_line > 0 else None,
        "units_to_next_slab_line": round(next_line - units, 1) if next_line else None,
        "excludes": "electricity duty, fuel adjustment charge",
        "tariff": f"MSEDCL {TARIFF['category']}, {TARIFF['financial_year']}",
    }


if __name__ == "__main__":
    # worked example used in the paper
    for u in (90, 250, 306, 320, 600):
        print(u, "units ->", monthly_bill(u), "Rs, marginal", marginal_rate(u))
    print("cut 33 units from 306 saves", saving_from_cut(306, 33))
