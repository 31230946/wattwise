"""
Run WattWise with NO server and NO internet. Prints JSON (same output as the API).

Examples
  python cli.py bill   --units 280 295 306
  python cli.py daily  --kwh 9.1 8.7 10.2 9.8 11.0 10.5 9.9 --home 2bhk
  python cli.py daily  --json examples/sample_requests/daily_full.json
  python cli.py demo                     # runs all three screens on sample homes
  python cli.py like --units 140 150 210 --last-month 4 --ac yes   # homes like yours (SIMULATED Pune homes)
"""
import argparse
import json
import os
import sys

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engine  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="WattWise offline")
    ap.add_argument("mode", choices=["bill", "daily", "demo", "meta", "like"])
    ap.add_argument("--kwh", type=float, nargs="*", help="daily kWh, oldest first")
    ap.add_argument("--units", type=float, nargs="*", help="monthly bill units, oldest first")
    ap.add_argument("--home", default=None, choices=["1bhk", "2bhk", "3bhk", "villa"])
    ap.add_argument("--smart-meter", action="store_true")
    ap.add_argument("--last-month", type=int, help="like: calendar month (1-12) of the last bill")
    ap.add_argument("--ac", choices=["yes", "no"], help="like: does the home have an AC?")
    ap.add_argument("--json", help="path to a JSON request file (overrides the flags)")
    a = ap.parse_args()

    if a.mode == "meta":
        out = engine.meta()
    elif a.mode == "like":
        req = {"monthly_units": a.units, "last_bill_month": a.last_month,
               "has_ac": {"yes": True, "no": False}.get(a.ac), "has_smart_meter": a.smart_meter}
        try:
            out = engine.homes_like_yours(req)
        except engine.InputError as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            sys.exit(2)
    elif a.mode == "demo":
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "examples", "sample_requests", "demo_all.json")) as f:
            demo = json.load(f)
        out = {"bill": engine.bill_screen(demo["bill"]), "daily": engine.forecast_daily(demo["daily"]),
               "homes_like_yours": engine.homes_like_yours(demo["homes_like_yours"])}
    else:
        if a.json:
            with open(a.json) as f:
                req = json.load(f)
        else:
            req = {"home_type": a.home, "has_smart_meter": a.smart_meter}
            if a.mode == "bill":
                req["monthly_units"] = a.units
            else:
                req["daily_kwh"] = a.kwh
        fn = {"bill": engine.bill_screen, "daily": engine.forecast_daily}[a.mode]
        try:
            out = fn(req)
        except engine.InputError as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            sys.exit(2)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
