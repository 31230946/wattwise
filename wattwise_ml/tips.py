"""
Turns the bandit's chosen action into a concrete tip with kWh, Rs and kg CO2.

The bandit decides the TYPE of tip; this file fills in the details:
  * which appliance (only if the user filled the optional appliance list)
  * kWh saved -> Rs saved on the real MSEDCL slabs (tariff.py) -> kg CO2 saved (carbon.py)
The wording never claims a comparison we can't back up.
"""
import carbon
import tariff

DAYS = tariff.TARIFF["days_per_billing_month"]
DEFAULT_CUT_SHARE = 0.10   # without appliance data: suggest up to 10% (top of the 4-10% field-study range)


def _slab_note(monthly_units, units_cut):
    lower_line = tariff.current_slab(monthly_units)["from_units"] - 1
    if lower_line > 0 and 0 < monthly_units - lower_line <= units_cut:
        return f" That also brings you back under the {lower_line}-unit slab line."
    return ""


def build_tip(action, daily_kwh, monthly_units, peer_mean_kwh, has_smart_meter,
              breakdown=None, baseload_above_peers=None):
    items = breakdown["items"] if breakdown else []
    tip = {"action": action, "target_appliance": None, "saving_kwh_per_day": 0.0,
           "saving_rs_per_month": 0.0, "saving_kg_co2_per_month": 0.0, "title": "", "message": ""}

    if action == "no_action":
        tip["title"] = "You're doing fine"
        tip["message"] = (f"Your forecast ({daily_kwh:.1f} kWh/day) is close to or below similar homes "
                          f"({peer_mean_kwh:.1f} kWh/day). No change needed right now.")
        return tip

    if action in ("reduce_load_general", "appliance_efficiency_tip"):
        if action == "reduce_load_general":
            cands = [i for i in items if i["cuttable"] and i["hours_per_day"] >= 1]
            if cands:
                t = cands[0]
                kwh = round(t["kwh"] / t["hours_per_day"], 2)     # one hour less per day
                tip["target_appliance"] = t["label"]
                tip["title"] = f"Run the {t['label']} 1 hour less"
                lead = (f"Your {t['label']} is about {t['share_pct']:.0f}% of your use (estimate from your inputs). "
                        f"One hour less a day saves ~{kwh:.1f} kWh")
            else:
                excess = max(daily_kwh - peer_mean_kwh, 0.0)
                kwh = round(min(max(0.3 * excess, 0.05 * daily_kwh), DEFAULT_CUT_SHARE * daily_kwh), 2)
                where = "above" if daily_kwh > peer_mean_kwh else "close to"
                tip["title"] = "Trim your daily use a little"
                lead = (f"You're forecast {where} similar homes ({peer_mean_kwh:.1f} kWh/day). "
                        f"Cutting ~{kwh:.1f} kWh a day")
        else:
            kwh = round(daily_kwh * 0.05, 2)
            tip["target_appliance"] = "Always-on appliances"
            tip["title"] = "Check what stays on all the time"
            first = ("Your night-time (always-on) use is higher than similar homes." if baseload_above_peers
                     else "Always-on load (fridge, standby, router) is an easy place to save.")
            fridge = " Check the fridge door seal and keep it a little off the wall." if any(
                i["type"] == "fridge" for i in items) else ""
            has_ac = any(i["type"].startswith("ac_") for i in items) or not items   # unknown -> mention it
            ac = " Keep ACs at 24-26°C." if has_ac else ""
            lead = (f"{first} Switch off standby devices at the plug.{ac}{fridge} "
                    f"A 5% cut (~{kwh:.1f} kWh/day)")
        units = kwh * DAYS
        rs = tariff.saving_from_cut(monthly_units, units)
        kg = carbon.kg_co2(units)
        tip.update(saving_kwh_per_day=kwh, saving_rs_per_month=rs, saving_kg_co2_per_month=kg)
        tip["message"] = (f"{lead} = about Rs {rs:.0f} and {kg:.0f} kg CO2 a month "
                          f"(each unit costs you Rs {tariff.marginal_rate(monthly_units):.2f} at your slab)."
                          f"{_slab_note(monthly_units, units)}")
        return tip

    if action == "shift_evening_to_midday":
        cands = [i for i in items if i["shiftable"] and i["when"] != "day"]
        kwh = round(cands[0]["kwh"], 2) if cands else round(daily_kwh * 0.05, 2)
        what = cands[0]["label"] if cands else "flexible jobs (washing, ironing, water pump)"
        tip["target_appliance"] = cands[0]["label"] if cands else None
        tip["title"] = f"Move the {what} to daytime"
        rs = tariff.saving_from_shift(kwh * DAYS, has_smart_meter)
        tip.update(saving_rs_per_month=rs)
        if has_smart_meter:
            tip["message"] = (f"Run the {what} between 9am and 5pm. With your smart meter that earns the "
                              f"Rs 0.80/unit solar-hours rebate, about Rs {rs:.0f} a month, and eases the evening peak on the grid.")
        else:
            tip["message"] = (f"Run the {what} between 9am and 5pm. On a normal meter this won't change your bill, "
                              f"but it eases the evening peak on the grid, when there is no solar power available.")
        return tip

    raise ValueError(f"unknown action {action}")
