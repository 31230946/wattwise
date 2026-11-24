"""
Calibration check: does the SIMULATED Pune data match the published Prayas Pune numbers?
Pass bars are fixed in pune_targets.json -> "checks" (set before running).

Honest reading: targets 1-8 were used to build the simulator, so passing them shows the
transformation worked as intended (London noise did not wreck the Pune shape). It does NOT
prove the data behaves like real Pune homes day to day. Target 9 (weekend) was NOT imposed,
so it is the one independent check.

Run from the project root:  python pune_sim/check_pune_sim.py
Writes pune_sim/out/calibration_check.csv and figures/pune_sim_*.png
"""
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "pune_sim", "out")
FIG = os.path.join(ROOT, "figures")
T = json.load(open(os.path.join(ROOT, "pune_sim", "pune_targets.json")))
PUB, TOL = T["published"], T["checks"]
DPM = 30.4375


def avg_profile(p, source, months, ac=None, weekend=None):
    """Average household half-hour watts (each home counts once), 48 values."""
    q = p[(p.source == source) & (p.month.isin(months))]
    if ac is not None:
        q = q[q.has_ac == ac]
    if weekend is not None:
        q = q[q.weekend == weekend]
    else:  # weekdays 5/7, weekends 2/7
        q = q.assign(n_homes=q.n_homes * np.where(q.weekend == 1, 2 / 7, 5 / 7))
    g = q.groupby("slot").apply(lambda d: np.average(d.w, weights=d.n_homes), include_groups=False)
    return g.reindex(range(48)).values


def peak(prof, slots):
    slots = np.asarray(slots) % 48
    i = slots[np.argmax(prof[slots])]
    return float(prof[i]), int(i // 2)


def within(x, lo, hi):
    return lo <= x <= hi


def main():
    p = pd.read_csv(os.path.join(OUT, "profiles.csv"))
    sim = pd.read_csv(os.path.join(ROOT, "data", "pune_sim_daily.csv"))
    homes = sim.groupby("household_id")["daily_kwh"].mean() * DPM
    wt, st = TOL["watt_tol"], TOL["spread_tol"]
    rows = []

    def add(n, what, target, got, ok, imposed=True):
        rows.append({"#": n, "check": what, "published (Prayas)": target, "simulated": got,
                     "pass": "PASS" if ok else "FAIL", "used to build sim": "yes" if imposed else "NO"})

    m = homes.mean()
    add(1, "Average monthly use (kWh)", "156", f"{m:.0f}", within(m, 156 * (1 - TOL["monthly_mean_tol"]), 156 * (1 + TOL["monthly_mean_tol"])))
    lo, hi = homes.quantile(0.025), homes.quantile(0.975)
    add(2, "Spread: low / high homes (kWh/month)*", "about 60 / about 348", f"{lo:.0f} / {hi:.0f}",
        within(lo, 60 * (1 - st), 60 * (1 + st)) and within(hi, 348 * (1 - st), 348 * (1 + st)))

    jan = avg_profile(p, "sim", [1])
    w, h = peak(jan, range(12, 24))
    add(3, "January morning peak", "about 350 W, about 9 am", f"{w:.0f} W, {h}:00",
        within(w, 350 * (1 - wt), 350 * (1 + wt)) and 8 <= h <= 10)

    for n, (name, months) in ((4, ("January", [1])), (4, ("August", [8]))):
        pr = avg_profile(p, "sim", months)
        w, h = peak(pr, range(36, 48))
        add(n, f"Evening peak, {name}", "200-250 W, about 9 pm", f"{w:.0f} W, {h}:00",
            within(w, 200 * (1 - wt), 250 * (1 + wt)) and 20 <= h <= 22)

    for name, months in (("Jan", [1]), ("Aug", [8]), ("Nov", [11])):
        night = avg_profile(p, "sim", months)[2:10].mean()
        add(5, f"Night load 1-5 am, {name}", "100-150 W", f"{night:.0f} W", within(night, 100 * (1 - wt), 150 * (1 + wt)))

    may = avg_profile(p, "sim", [5])
    w, h = peak(may, range(44, 54))
    add(6, "May night peak, all homes", "about 350 W, 12-1 am", f"{w:.0f} W, {h}:00",
        within(w, 350 * (1 - wt), 350 * (1 + wt)) and h in (23, 0, 1, 2))
    may_ac = avg_profile(p, "sim", [5], ac=1)
    w, h = peak(may_ac, range(44, 54))
    add(7, "May night peak, AC homes", "about 600 W", f"{w:.0f} W, {h}:00", within(w, 600 * (1 - wt), 600 * (1 + wt)))

    feb_ac = avg_profile(p, "sim", [2], ac=1)[2:10].mean()
    add(8, "No AC in February (AC homes, night 1-5 am)", "not raised: 100-150 W x home size",
        f"{feb_ac:.0f} W vs Jan {avg_profile(p, 'sim', [1], ac=1)[2:10].mean():.0f} W",
        feb_ac <= 1.1 * avg_profile(p, "sim", [1], ac=1)[2:10].mean())

    ns = [1, 2, 8, 9, 11, 12]
    wd = avg_profile(p, "sim", ns, weekend=0)[20:34].mean()
    we = avg_profile(p, "sim", ns, weekend=1)[20:34].mean()
    add(9, "Weekend daytime (10am-5pm) higher than weekdays", "higher on weekends", f"weekend {we:.0f} W vs weekday {wd:.0f} W",
        we > wd, imposed=False)

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "calibration_check.csv"), index=False)
    print(df.to_string(index=False))
    print(f"\n{(df['pass'] == 'PASS').sum()} of {len(df)} checks passed.")
    print("* spread read as the 2.5th / 97.5th percentile of homes (Prayas gives group values, not percentiles)")
    figures(p, sim)


def figures(p, sim):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(FIG, exist_ok=True)
    x = np.arange(48) / 2
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for a, (mon, name) in zip(ax, ((1, "January"), (5, "May"))):
        a.plot(x, avg_profile(p, "london", [mon]), color="#888", label="London source homes (real)")
        a.plot(x, avg_profile(p, "sim", [mon]), color="#c0392b", label="Pune homes (SIMULATED)")
        if mon == 5:
            a.plot(x, avg_profile(p, "sim", [5], ac=1), color="#c0392b", ls="--", label="  of which AC homes")
        a.set_title(name)
        a.set_xlabel("hour of day")
        a.set_xticks(range(0, 25, 3))
    ax[0].set_ylabel("average watts per home")
    ax[1].legend(fontsize=8)
    fig.suptitle("Average day: London source vs simulated Pune (SIMULATED data)", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "pune_sim_daily_shape.png"), dpi=150)

    lon = pd.read_csv(os.path.join(OUT, "london_source_daily.csv"), parse_dates=["date"])
    s = sim.assign(date=pd.to_datetime(sim.date))
    fig, a = plt.subplots(figsize=(6, 3.4))
    for d, c, lab in ((lon, "#888", "London source homes (real)"), (s, "#c0392b", "Pune homes (SIMULATED)")):
        mm = d.groupby([d.date.dt.month, "household_id"]).daily_kwh.mean().groupby(level=0).mean() * DPM
        a.plot(mm.index, mm.values, marker="o", color=c, label=lab)
    a.axhline(156, color="#c0392b", ls=":", lw=1, label="Prayas Pune city average (156)")
    a.set_xticks(range(1, 13))
    a.set_xticklabels(list("JFMAMJJASOND"))
    a.set_ylabel("kWh per home per month")
    a.legend(fontsize=8)
    a.set_title("Season: London winter peak vs simulated Pune summer peak", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "pune_sim_monthly.png"), dpi=150)
    print("figures: figures/pune_sim_daily_shape.png, figures/pune_sim_monthly.png")


if __name__ == "__main__":
    main()
