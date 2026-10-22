"""Stage 1, the corrected test (docs/PLAN.md "Corrections after the first stage-1 test", registered before this run), on
the same frames, funnel and index-fund benchmark as backtest/stage1.py and the holding-rule portfolio of stage1_hold.py:
1. Return signals enter on the mean 6-month return (top fifth − bottom fifth > 0); risk signals (volatility, a loss, CN
   heat) on 25%+ falls (risky side − safe side > 0); each in at least 3 of 4 sub-periods. Equal weights.
2. Random portfolios use no score: funnel exits are sold, then a binomial number of the rest at the score portfolio's
   average monthly turnover; refills at random from the funnel, at most 2 per industry.
3. A single signal beats the score only with the higher mean 6-month return and no more 25%+ falls per entry.
Items 1, 2, 4 and 5 keep their levels. The avoid list ships in a passing market if its names trailed the 400 largest on
the mean 6-month return and fell 25%+ more often, in at least 3 of 4 sub-periods.

  uv run python -m backtest.stage1_fix bar cn|us|hk
"""

import sys
import warnings

import numpy as np
import pandas as pd

from backtest import panel, stage1, stage1_hold as hold

N, CAP, DRAWS = hold.N, hold.CAP, 1000
RETURN = ["E/P", "B/P", "profitability", "accruals", "12-1 momentum", "6m trend", "issuance"]
RISK = ["volatility", "loss", "CN heat"]


def inclusion(f: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    """Correction 1: return signals on the 6-month return, risk signals on 25%+ falls, per sub-period."""
    ret = stage1.subperiod_test(f, p)
    rows = {k: {**ret.loc[k, list(stage1.PERIODS)].to_dict(), "judged on": "return"} for k in RETURN if k in ret.index}
    sides = {"volatility": (p.get("volatility") >= 0.8, p.get("volatility") <= 0.2), "loss": (f["loss"] == 0, f["loss"] == 1)}
    if "heat" in f:
        sides["CN heat"] = (f["heat"] == 0, f["heat"] == 1)
    for name, (safe, risky) in sides.items():
        r = {}
        for per in stage1.PERIODS:
            part = (f["period"] == per) & f["blow"].notna()
            r[per] = f.loc[part & risky, "blow"].mean() - f.loc[part & safe, "blow"].mean()
        rows[name] = {**r, "judged on": "falls (risky − safe)"}
    t = pd.DataFrame(rows).T
    t["positive"] = (t[list(stage1.PERIODS)].astype(float) > 0).sum(axis=1)
    t["enters"] = t["positive"] >= 3
    return t


def simulate(months: list, bench: np.ndarray, cost: float, rng=None, turnover: float = 0.0):
    """The holding-rule portfolio (rng None: stage1_hold's rules by the key), or a random one (correction 2)."""
    held, rets, falls, entries = [], [], [], []
    for mo in months:
        if rng is None:
            held = [c for c in held if c in mo.keep]
        else:
            held = [c for c in held if c in mo.ind]
            k = rng.binomial(len(held), turnover) if held else 0
            if k:
                drop = set(rng.choice(len(held), size=k, replace=False))
                held = [c for i, c in enumerate(held) if i not in drop]
        per = {}
        for c in held:
            per[mo.ind[c]] = per.get(mo.ind[c], 0) + 1
        order = mo.order if rng is None else [mo.order[i] for i in rng.permutation(len(mo.order))]
        new = []
        for c in order:
            if len(held) + len(new) >= N:
                break
            if c in held or per.get(mo.ind[c], 0) >= CAP:
                continue
            new.append(c)
            per[mo.ind[c]] = per.get(mo.ind[c], 0) + 1
        held = held + new
        falls += [mo.fall[c] for c in new if not np.isnan(mo.fall.get(c, np.nan))]
        entries.append(len(new))
        rets.append(np.mean([mo.ret[c] for c in held]) - cost * len(new) / N if held else 0.0)
    return np.array(rets), falls, entries


def bar(market: str) -> None:
    warnings.simplefilter("ignore")
    f = pd.read_pickle(panel.BT / f"s1_{market}_result.pkl").reset_index(drop=True)
    f["bench1"] = stage1.benchmark(f, market, "1m")
    p = stage1.percentiles(f, market)
    t = inclusion(f, p)
    entered = list(t.index[t["enters"]])
    score = p[entered].fillna(0.5).mean(axis=1).groupby(f["date"]).rank(pct=True) if entered else pd.Series(0.5, f.index)
    print(f"\n==== {market.upper()} stage 1, the corrected test\n-- which signals enter (per sub-period; positive = as expected)\n"
          + t.round(3).to_string() + f"\nscore = equal-weight mean of: {entered}")

    dates = [d for d, g in f.groupby("date", sort=True) if g["ret_1m"].notna().any() and g["bench1"].notna().any()]
    bench = f.drop_duplicates("date").set_index("date")["bench1"].reindex(dates).to_numpy(float)
    period = f.drop_duplicates("date").set_index("date")["period"].reindex(dates).to_numpy()[: max(len(dates) - 5, 0)]
    cost, by = stage1.COST[market], {d: g for d, g in f[f["date"].isin(dates)].groupby("date")}
    keys = {"score": score} | {k: f.groupby("date")[c].rank(pct=True) for k, c in stage1.SINGLE.items()}
    res = {}
    for name, key in keys.items():
        rets, falls, entries = simulate([hold.Month(by[d], key) for d in dates], bench, cost)
        res[name] = {"six": hold.six_month(rets, bench), "falls": np.mean(falls) if falls else np.nan, "rets": rets,
                     "turnover": np.mean(entries[1:]) / N}
    months = [hold.Month(by[d], score) for d in dates]
    rng = np.random.default_rng(0)
    rnd = [simulate(months, bench, cost, rng, res["score"]["turnover"]) for _ in range(DRAWS)]
    rnd6 = np.array([hold.six_month(r, bench) for r, _, _ in rnd])
    rnd_fall = np.nanmean([np.mean(fl) for _, fl, _ in rnd if fl])
    rnd_turn = np.mean([np.mean(e[1:]) / N for _, _, e in rnd])

    ours = res["score"]["six"]
    sub = {q: ours[period == q].mean() for q in stage1.PERIODS}
    sub_rnd = {q: np.median(rnd6[:, period == q].mean(axis=1)) for q in stage1.PERIODS}
    beaten = (rnd6.mean(axis=1) < ours.mean()).mean()
    tab = {k: {"all": r["six"].mean()} | {q: r["six"][period == q].mean() for q in stage1.PERIODS}
           | {"25%+ falls per entry": r["falls"], "monthly turnover": r["turnover"]} for k, r in res.items()}
    tab["random portfolios (median)"] = ({"all": np.median(rnd6.mean(axis=1))} | sub_rnd
                                         | {"25%+ falls per entry": rnd_fall, "monthly turnover": rnd_turn})
    print("\n-- 6-month return over the index fund, after costs, from every start month (holding-rule portfolios)\n"
          + pd.DataFrame(tab).T.round(3).to_string())
    rets = res["score"]["rets"]
    curve, fund = np.cumprod(1 + rets), np.cumprod(1 + bench)
    print(f"a year over the fund {np.mean(rets - bench) * 12:+.3f}; max drawdown {(curve / np.maximum.accumulate(curve) - 1).min():.3f} "
          f"(fund {(fund / np.maximum.accumulate(fund) - 1).min():.3f}); beat {beaten:.1%} of {DRAWS} random portfolios")

    ok = f["ret_6m"].notna() & score.notna()
    x = f["ret_6m"] - stage1.benchmark(f, market)
    slopes = {q: np.polyfit(score[ok & (f["period"] == q)], x[ok & (f["period"] == q)], 1)[0] for q in stage1.PERIODS}
    b = np.polyfit(score[ok & x.notna()], x[ok & x.notna()], 1)
    print(f"expected-return line: {b[1]:+.3f} + {b[0]:+.3f} × score percentile; by sub-period "
          + ", ".join(f"{q} {v:+.3f}" for q, v in slopes.items()))
    dominated = [k for k in stage1.SINGLE if res[k]["six"].mean() > ours.mean() and res[k]["falls"] <= res["score"]["falls"]]
    items = {"1. mean over the fund > 0, positive in 3 of 4 sub-periods": ours.mean() > 0 and sum(v > 0 for v in sub.values()) >= 3,
             "2. beats 90% of random portfolios (no score), and their median in 3 of 4": beaten >= 0.9 and sum(sub[q] > sub_rnd[q] for q in sub) >= 3,
             "3. no single signal has more return with no more falls": not dominated,
             "4. 25%+ falls per entry no more than random portfolios'": res["score"]["falls"] <= rnd_fall,
             "5. expected-return line slopes up in 3 of 4 sub-periods": sum(v > 0 for v in slopes.values()) >= 3}
    for k, v in items.items():
        print(f"   {k}: {'pass' if v else 'FAIL'}" + (f" (dominated by {dominated})" if k.startswith("3") and dominated else ""))
    passed = all(items.values())
    print(f"   {market.upper()} passes: {passed}")

    known = f[f["blow"].notna()]
    base = known.loc[known["sample"] == "in", "blow"].mean()
    largest = f["mcap_rank"] <= 400
    warn = (f["s1_chance"] > 2 * base) | (f["loss"] == 1) | (stage1.pct(f, "mom_6", 1) <= 0.2) | (f.get("heat", 0) == 1)
    avoid = stage1.lists(f, score, largest & warn, ascending=True)
    six = f["ret_6m"].notna()
    av = {q: (f.loc[avoid & six & (f["period"] == q), "ret_6m"].mean() < f.loc[largest & six & (f["period"] == q), "ret_6m"].mean())
          and (f.loc[avoid & six & (f["period"] == q), "blow"].mean() > f.loc[largest & six & (f["period"] == q), "blow"].mean())
          for q in stage1.PERIODS}
    print(f"avoid list: trailed the 400 largest and fell 25%+ more often in {sum(av.values())}/4 sub-periods "
          f"({', '.join(q for q, v in av.items() if v)}); mean 6-month return {f.loc[avoid & six, 'ret_6m'].mean():+.3f} vs "
          f"{f.loc[largest & six, 'ret_6m'].mean():+.3f}, 25%+ falls {f.loc[avoid & six, 'blow'].mean():.1%} vs "
          f"{f.loc[largest & six, 'blow'].mean():.1%}: {'ships' if passed and sum(av.values()) >= 3 else 'does not ship'}")

    last = f["date"].max()
    show = f[f["date"] == last].assign(score=score)
    buys = stage1.lists(f, score, f["s1_field"].astype(bool))
    print(f"-- lists on {last} (shown, not used): buys " + ", ".join(f"{r['code']} {str(r['name'])[:10]}" for _, r in
          show[buys[show.index]].sort_values("score", ascending=False).iterrows())
          + "; avoid " + ", ".join(f"{r['code']} {str(r['name'])[:10]}" for _, r in show[avoid[show.index]].sort_values("score").iterrows()))
    f.assign(fix_score=score, fix_buy=buys, fix_avoid=avoid).to_pickle(panel.BT / f"s1_{market}_fix.pkl")


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    bar(sys.argv[2]) if sys.argv[1] == "bar" else sys.exit("usage: bar cn|us|hk")
