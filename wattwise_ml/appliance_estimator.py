"""
OPTIONAL appliance breakdown, built only from what the user types in.

What it does:
  estimate_i = (kWh per hour of use)_i x count_i x hours_i       (kWh per day)
  kWh per hour of use comes from, in this order:
    1. rated_watts the user typed from the label         -> watts x duty / 1000
    2. label_kwh_per_year from the BEE star label (AC, fridge)
         AC: / 1,600 label hours;  fridge: / 365 days (runs all day)
    3. star_rating 1-5 (AC, fridge, ceiling fan)          -> BEE-based per-star value
    4. otherwise the typical value (AC and fridge = 3-star; fan = non-star 70 W)
  (sources and derivation: appliance_catalog.json -> "_star_sources")
  then all estimates are scaled so they add up to the household's real/forecast
  daily total. The scale factor is returned: if it is far from 1 (outside 0.5-2),
  the user's hours are probably off and the app should say so.

What it does NOT do (say this in the app and the report):
  * it is NOT measured appliance data and NOT machine learning
  * it does NOT compare appliances with other homes (we have no real per-appliance
    peer data, so any such comparison would be made up)

Its job is to turn a generic tip ("use less") into a concrete one ("your AC is
about 44% of your use; 1 hour less a day saves ~Rs 369/month").

The REFIT check in refit_validation.py (optional) tests how close this kind of
estimate gets to real sub-metered appliance data.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "appliance_catalog.json")) as f:
    CATALOG = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

PERIOD_HOURS = {  # used to work out evening / solar share from the user's "when used"
    "morning": (6, 9), "day": (9, 17), "evening": (18, 22), "night": (22, 30), "all_day": (0, 24),
}


def _overlap(period, window):
    a, b = PERIOD_HOURS[period]
    lo, hi = window
    return max(0, min(b, hi) - max(a, lo)) + (max(0, min(b - 24, hi) - max(a - 24, lo)) if b > 24 else 0)


STAR_TYPES = {k: v["star"]["kind"] for k, v in CATALOG.items() if "star" in v}
LABEL_KWH_TYPES = [k for k, v in CATALOG.items() if v.get("star", {}).get("kind") in ("kwh_per_hour", "kwh_per_day")]


def per_hour_kwh(spec, a):
    """kWh per hour of use for ONE unit, and a short note on where the number came from."""
    star = spec.get("star")
    if a.get("rated_watts"):
        return float(a["rated_watts"]) * spec["duty"] / 1000.0, "your label watts"
    if star and a.get("label_kwh_per_year") and star["kind"] in ("kwh_per_hour", "kwh_per_day"):
        y = float(a["label_kwh_per_year"])
        if star["kind"] == "kwh_per_hour":
            return y / star["label_hours_per_year"], f"your BEE label ({y:.0f} kWh/year over {star['label_hours_per_year']} h)"
        return y / 365.0 / 24.0, f"your BEE label ({y:.0f} kWh/year)"
    s = a.get("star_rating")
    if star and s:
        s = int(s)
        if not 1 <= s <= 5:
            raise ValueError("star_rating must be 1-5")
        v = float(star["values"][str(s)])
        note = f"BEE {s}-star"
    elif star and star.get("default_star"):
        v = float(star["values"][str(star["default_star"])])
        note = f"typical (assumed {star['default_star']}-star)"
    else:
        return spec["watts"] * spec["duty"] / 1000.0, "typical"
    if star["kind"] == "kwh_per_hour":
        return v, note
    if star["kind"] == "kwh_per_day":
        return v / 24.0, note
    return v / 1000.0, note                     # watts


def estimate(appliances, daily_total_kwh):
    """
    appliances: list of dicts like
        {"type": "ac_1_5_ton", "count": 1, "hours_per_day": 4, "when": "evening", "rated_watts": null}
    Returns dict with per-appliance kWh + share, scale factor, evening/solar share.
    """
    rows = []
    for a in appliances:
        spec = CATALOG.get(a.get("type"), CATALOG["other"])
        count = int(a.get("count", 1))
        hours = 24.0 if a.get("when") == "all_day" and not a.get("hours_per_day") else float(a.get("hours_per_day") or 0)
        per_hour, basis = per_hour_kwh(spec, a)
        if spec.get("star", {}).get("kind") == "kwh_per_day" and not a.get("rated_watts"):
            hours = 24.0                      # a fridge runs all day whatever was typed
        kwh = per_hour * count * hours
        rows.append({"type": a.get("type"), "label": spec["label"], "count": count,
                     "hours_per_day": hours, "when": a.get("when", "day"), "raw_kwh": kwh,
                     "shiftable": spec["shiftable"], "cuttable": spec["cuttable"],
                     "kwh_per_hour": per_hour * count, "basis": basis,
                     "star_rating": a.get("star_rating")})
    raw_total = sum(r["raw_kwh"] for r in rows)
    if raw_total <= 0:
        return None
    scale = daily_total_kwh / raw_total
    evening = solar = 0.0
    for r in rows:
        r["kwh"] = round(r["raw_kwh"] * scale, 2)
        r["share_pct"] = round(100 * r["raw_kwh"] / raw_total, 1)
        span = PERIOD_HOURS[r["when"]][1] - PERIOD_HOURS[r["when"]][0]
        evening += r["raw_kwh"] * _overlap(r["when"], PERIOD_HOURS["evening"]) / span
        solar += r["raw_kwh"] * _overlap(r["when"], PERIOD_HOURS["day"]) / span
    rows.sort(key=lambda r: r["kwh"], reverse=True)
    return {
        "items": [{k: r[k] for k in ("type", "label", "count", "hours_per_day", "when", "kwh", "share_pct",
                                     "shiftable", "cuttable", "kwh_per_hour", "basis", "star_rating")} for r in rows],
        "scale_factor": round(scale, 2),
        "hours_look_off": not (0.5 <= scale <= 2.0),
        "evening_share": round(evening / raw_total, 3),
        "solar_share": round(solar / raw_total, 3),
        "always_on_kwh": round(sum(r["raw_kwh"] for r in rows if r["when"] == "all_day") * scale, 2),
        "note": "Estimate from your inputs (typical or BEE star-label energy use x your hours), scaled to your meter total. Not measured.",
    }


if __name__ == "__main__":
    demo = [
        {"type": "ac_1_5_ton", "count": 1, "hours_per_day": 4, "when": "evening", "star_rating": 5},
        {"type": "ceiling_fan", "count": 3, "hours_per_day": 10, "when": "evening", "star_rating": 3},
        {"type": "fridge", "count": 1, "when": "all_day", "label_kwh_per_year": 250},
        {"type": "geyser", "count": 1, "hours_per_day": 0.5, "when": "morning"},
        {"type": "led_lights", "count": 1, "hours_per_day": 5, "when": "evening"},
        {"type": "washing_machine", "count": 1, "hours_per_day": 1, "when": "morning"},
    ]
    print(json.dumps(estimate(demo, 10.2), indent=1))
