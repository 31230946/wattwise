"""
Tip picker: a contextual bandit (LinUCB, Li et al. 2010) that chooses which
KIND of tip to show a household.

Actions
  reduce_load_general      "use less overall"           -> targets kWh above peers
  shift_evening_to_midday  "move evening use to daytime" -> targets evening share above peers
  appliance_efficiency_tip "check always-on appliances"  -> targets night baseload above peers
  no_action                say nothing this time         -> right call for homes already below
                                                            their peers (avoids the "boomerang"
                                                            effect, Schultz et al. 2007)

Context (6 numbers):
  [bias, usage_vs_peers, evening_share, baseload_vs_peers, is_weekend, has_smart_meter]

Each action's simulated outcome depends on the gap it targets, measured against
real peer households from the LCL data on the same day.

Reward (all simulated offline, there are no live users):
  bill_rs     = rupees saved per day (kWh cut x marginal slab rate, + Rs 0.80/kWh shifted
                into solar hours if the home has a smart meter)
  evening_cut = kWh removed from the 18:00-22:00 window
  reward      = 0.8 * min(1, bill_rs / RS_NORM) + 0.2 * min(1, evening_cut / EV_NORM)

How big a saving is "achievable" is capped at 10% of the day's use, in line
with the 4-10% savings reported by feedback field studies (Nguyen et al. 2024;
Ruokamo et al. 2022; WRI 2018). These caps are assumptions and are listed in
the paper's limitations.
"""
import numpy as np
import pandas as pd

import tariff

ACTIONS = ["reduce_load_general", "shift_evening_to_midday", "appliance_efficiency_tip", "no_action"]
N_FEATURES = 6

# --- simulation assumptions (one place, so they're easy to report and change) ---
SIM = {
    "take_up_of_gap": 0.30,     # share of the "excess over peers" a household actually removes
    "max_saving_share": 0.10,   # never more than 10% of the day's kWh (field-study range 4-10%)
    "noise_low": 0.5, "noise_high": 1.5,  # households differ in how well they follow a tip
    "no_action_reward_if_below_peers": 0.05,
    "RS_NORM": 15.0,            # Rs/day that counts as a "full" bill reward
    "EV_NORM": 1.0,             # kWh/day removed from the evening window that counts as "full"
    "w_bill": 0.8, "w_evening": 0.2,
}


class LinUCB:
    """One ridge-regression model per action + an optimism bonus for uncertain actions."""

    def __init__(self, n_actions=len(ACTIONS), n_features=N_FEATURES, alpha=0.5):
        self.alpha = alpha
        self.A = [np.eye(n_features) for _ in range(n_actions)]
        self.b = [np.zeros(n_features) for _ in range(n_actions)]

    def scores(self, x):
        x = np.asarray(x, float)
        out = []
        for A, b in zip(self.A, self.b):
            A_inv = np.linalg.inv(A)
            out.append(float((A_inv @ b) @ x + self.alpha * np.sqrt(x @ A_inv @ x)))
        return out

    def expected(self, x):
        """Mean predicted reward per action, WITHOUT the exploration bonus (used for display)."""
        x = np.asarray(x, float)
        return [float((np.linalg.inv(A) @ b) @ x) for A, b in zip(self.A, self.b)]

    def select(self, x):
        s = self.scores(x)
        return int(np.argmax(s)), s

    def update(self, a, x, r):
        x = np.asarray(x, float)
        self.A[a] += np.outer(x, x)
        self.b[a] += r * x


def build_context(predicted_kwh, peer_mean_kwh, evening_share, baseload_kw, peer_baseload_kw,
                  is_weekend, has_smart_meter):
    usage_vs_peers = np.clip((predicted_kwh - peer_mean_kwh) / max(peer_mean_kwh, 1e-6), -1, 2)
    base_vs_peers = np.clip((baseload_kw - peer_baseload_kw) / max(peer_baseload_kw, 1e-6), -1, 2)
    return np.array([1.0, usage_vs_peers, evening_share, base_vs_peers,
                     float(is_weekend), float(has_smart_meter)])


def simulate_outcome(row, action, has_smart_meter, rng):
    """What would following `action` achieve on this household-day? Uses the
    gap between this household and its real peer group (same band, same date)."""
    kwh = row["daily_kwh"]
    cap = SIM["max_saving_share"] * kwh
    noise = rng.uniform(SIM["noise_low"], SIM["noise_high"])
    excess_kwh = max(0.0, kwh - row["peer_median_kwh"])
    excess_ev = max(0.0, row["evening_share"] - row["peer_evening_share"]) * kwh
    excess_base = max(0.0, row["baseload_kw"] - row["peer_baseload_kw"]) * 24

    cut, shifted = 0.0, 0.0
    if action == "reduce_load_general":
        cut = min(SIM["take_up_of_gap"] * excess_kwh * noise, cap)
    elif action == "appliance_efficiency_tip":
        cut = min(SIM["take_up_of_gap"] * excess_base * noise, cap)
    elif action == "shift_evening_to_midday":
        shifted = min(SIM["take_up_of_gap"] * excess_ev * noise, cap)
    return cut, shifted


def reward_from_outcome(row, action, cut, shifted, has_smart_meter):
    if action == "no_action":
        return SIM["no_action_reward_if_below_peers"] if row["daily_kwh"] <= row["peer_median_kwh"] else 0.0
    monthly_units = row["daily_kwh"] * tariff.TARIFF["days_per_billing_month"]
    bill_rs = cut * tariff.marginal_rate(monthly_units)
    if has_smart_meter:
        bill_rs += shifted * tariff.TARIFF["tod"]["solar_rebate_rs_per_kwh"]
    evening_cut = shifted + cut * row["evening_share"]
    return (SIM["w_bill"] * min(1.0, bill_rs / SIM["RS_NORM"])
            + SIM["w_evening"] * min(1.0, evening_cut / SIM["EV_NORM"]))


def add_peer_columns(daily):
    """Peer = same usage band, same date. Uses the median of the peers (excluding self is
    not needed at ~37 homes per band; one home barely moves a median)."""
    d = daily.copy()
    grp = d.groupby(["date", "peer_band"])
    d["peer_median_kwh"] = grp["daily_kwh"].transform("median")
    d["peer_evening_share"] = grp["evening_share"].transform("median")
    d["peer_baseload_kw"] = grp["baseload_kw"].transform("median")
    return d


def context_of(row, has_smart_meter):
    return build_context(row["daily_kwh"], row["peer_median_kwh"], row["evening_share"],
                         row["baseload_kw"], row["peer_baseload_kw"], row["is_weekend"], has_smart_meter)


def run_policy(policy, rows, rng, bandit=None, learn=True, policy_rng=None):
    """Plays `policy` over rows, returns list of rewards. Smart-meter status is a
    tariff scenario, not something in the London data, so it is drawn 50/50."""
    # rng drives the simulated world (smart meter, noise); policy_rng drives the random
    # policy only, so every policy sees exactly the same world.
    policy_rng = policy_rng or np.random.default_rng(12345)
    rewards, chosen = [], []
    for _, row in rows.iterrows():
        sm = int(rng.random() < 0.5)
        x = context_of(row, sm)
        if policy == "linucb":
            a, _ = bandit.select(x)
        elif policy == "random":
            a = int(policy_rng.integers(len(ACTIONS)))
        elif policy == "always_reduce":
            a = 0
        elif policy == "rule_based":
            # a sensible hand-written rule, the kind a fixed nudge programme would use
            if x[1] <= 0:
                a = 3
            elif x[2] > row["peer_evening_share"] + 0.05:
                a = 1
            elif x[3] > 0.3:
                a = 2
            else:
                a = 0
        outcomes = []
        for k, act in enumerate(ACTIONS):
            sub_rng = np.random.default_rng(rng.integers(1 << 31))
            c, s = simulate_outcome(row, act, sm, sub_rng)
            outcomes.append(reward_from_outcome(row, act, c, s, sm))
        if policy == "oracle":
            a = int(np.argmax(outcomes))
        r = outcomes[a]
        if policy == "linucb" and learn:
            bandit.update(a, x, r)
        rewards.append(r)
        chosen.append(ACTIONS[a])
    return rewards, chosen


def train_offline(daily, train_households, n_interactions=4000, alpha=0.5, seed=1):
    d = add_peer_columns(daily)
    d = d[d["household_id"].isin(train_households)]
    rng = np.random.default_rng(seed)
    bandit = LinUCB(alpha=alpha)
    run_policy("linucb", d.sample(min(n_interactions, len(d)), random_state=seed), rng, bandit=bandit)
    return bandit


def evaluate(daily, n_train=4000, n_test=3000, seeds=(1, 2, 3, 4, 5)):
    """Bandit trained on 80% of households, then all policies compared on the
    other 20% (unseen households). LinUCB keeps learning online during the test
    replay, like it would in the app."""
    d = add_peer_columns(daily)
    hh = np.array(sorted(d["household_id"].unique()))
    results, picks = [], []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        test_hh = rng.choice(hh, size=len(hh) // 5, replace=False)
        train_hh = np.setdiff1d(hh, test_hh)
        bandit = train_offline(daily, train_hh, n_train, seed=seed)
        pool = d[d["household_id"].isin(test_hh)]
        test_rows = pool.sample(min(n_test, len(pool)), random_state=seed)
        for pol in ["random", "always_reduce", "rule_based", "linucb", "oracle"]:
            r, ch = run_policy(pol, test_rows, np.random.default_rng(seed + 100), bandit=bandit)
            results.append({"seed": seed, "policy": pol, "mean_reward": float(np.mean(r))})
            if pol == "linucb":
                picks += ch
    res = pd.DataFrame(results)
    summary = res.groupby("policy")["mean_reward"].agg(["mean", "std"])
    summary["pct_of_oracle"] = 100 * summary["mean"] / summary.loc["oracle", "mean"]
    share = pd.Series(picks).value_counts(normalize=True).round(3).to_dict()
    return summary.round(4), share


if __name__ == "__main__":
    from preprocessing import load_raw, daily_aggregate, assign_peer_bands
    daily = assign_peer_bands(daily_aggregate(load_raw()))
    s, share = evaluate(daily)
    print(s.to_string())
    print("LinUCB action mix on test households:", share)
