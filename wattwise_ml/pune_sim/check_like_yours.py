"""
How well does "homes like yours" guess the months a user did NOT enter?
Leave-one-home-out on the SIMULATED Pune homes: hide one home, give the matcher 1, 3 or 6 of its
monthly bills (every possible end month), and compare its guess for the other months with:
  * flat:            every month = the average of the bills given (what a person would assume)
  * average season:  the average Pune-sim season, scaled to the bills given (no matching)
k = 5 was fixed before running. Metric: WAPE over the hidden months (lower is better).

This runs on SIMULATED data, so it shows the matching logic works and is better than the simple
options on data with a Pune-like season. It is NOT evidence about real Pune homes.

Run from the project root:  python pune_sim/check_like_yours.py   (writes pune_sim/out/like_yours_check.csv)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import similar_homes as sh  # noqa: E402


def wape(y, p):
    return float(np.abs(y - p).sum() / y.sum() * 100)


def main():
    data = sh.load()
    monthly, ac, _ = data
    full = monthly.dropna()
    season = (monthly.div(monthly.mean(axis=1), axis=0)).mean()          # average Pune-sim season shape
    out = []
    for n in (1, 3, 6):
        for use_ac in (True, False):
            Y, P, F, S = [], [], [], []
            for h in full.index:
                for last in range(1, 13):
                    months = sh.bill_months(n, last)
                    hidden = [m for m in range(1, 13) if m not in months]
                    u = full.loc[h, months].values
                    best = sh.match(u, months, has_ac=bool(ac[h]) if use_ac else None, exclude=h, data=data)
                    guess = sh.outlook(best, data=data)[hidden].values
                    y = full.loc[h, hidden].values
                    Y.append(y)
                    P.append(guess)
                    F.append(np.full(len(hidden), u.mean()))
                    S.append(season[hidden].values * u.sum() / season[months].sum())
            Y, P, F, S = map(np.concatenate, (Y, P, F, S))
            out.append({"bills_given": n, "ac_answer_used": use_ac, "cases": len(full) * 12,
                        "wape_homes_like_yours": round(wape(Y, P), 1), "wape_flat": round(wape(Y, F), 1),
                        "wape_average_season": round(wape(Y, S), 1)})
    df = pd.DataFrame(out)
    df.to_csv(os.path.join(ROOT, "pune_sim", "out", "like_yours_check.csv"), index=False)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
