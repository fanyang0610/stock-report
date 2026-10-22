"""Stage 3 (docs/PLAN.md, "Stage 3's test"), parts (b)-(d) on the stage-1 frames with the implied return
(backtest/implied.py) joined:
- (b) the signal across all stocks: on each month end's stocks with the implied return, plain E/P, plain B/P and a
  6-month return (percentiles within that set), the top fifth minus bottom fifth on the mean 6-month return and the
  mean monthly rank correlation, both positive in 3 of 4 sub-periods and both higher than E/P's and B/P's in 3 of 4;
  shown: its rank correlation with 12-1 momentum and the 6-month trend.
- (c) stage 1's corrected score with the implied return in place of E/P and B/P (the corrected inclusion rule)
  against that score as it ran: holding-rule portfolios; per sub-period the mean 6-month return over the fund and
  25%+ falls per entry; one better and the other no worse in 3 of 4.
- (d) stage1_fix.py's items 1-5 with the new score.
A harness check first: the old score and its portfolio must reproduce stage1_fix's saved score and printed result.

  uv run python -m backtest.stage3 run cn|us|hk   # parts (b)-(d), run once
"""

import sys
import warnings

import numpy as np
import pandas as pd

from backtest import panel, stage1, stage1_fix as fix, stage1_hold as hold

PERIODS = list(stage1.PERIODS)
VALUE = {"implied return": "ier", "plain E/P": "ep", "plain B/P": "bp"}
TREND = {"12-1 momentum": "mom_12_1", "6m trend": "mom_6"}


def load(market: str) -> pd.DataFrame:
    f = pd.read_pickle(panel.BT / f"s1_{market}_result.pkl").reset_index(drop=True)
    s = pd.read_pickle(panel.BT / f"s3_{market}_ier.pkl")[["date", "code", "ier"]]
    f = f.merge(s, on=["date", "code"], how="left")
    assert len(f) == len(pd.read_pickle(panel.BT / f"s1_{market}_result.pkl"))
    f["bench1"] = stage1.benchmark(f, market, "1m")
    return f


def rank_corr(g: pd.DataFrame, a: str, b: str) -> pd.Series:
    """Per date: Spearman rank correlation of a and b."""
    return g.groupby("date").apply(lambda x: x[a].corr(x[b], method="spearman"))


# ---------------------------------------------------------------- (b)

def part_b(f: pd.DataFrame, market: str) -> bool:
    g = f[f[list(VALUE.values()) + ["ret_6m"]].notna().all(axis=1)].copy()
    per = g["period"]
    spread, ic = {}, {}
    for name, col in VALUE.items():
        g[name] = g.groupby("date")[col].rank(pct=True)
        top, bot = g[name] >= 0.8, g[name] <= 0.2
        ics = rank_corr(g, name, "ret_6m")
        dper = g.drop_duplicates("date").set_index("date")["period"]
        spread[name] = {"all": g.loc[top, "ret_6m"].mean() - g.loc[bot, "ret_6m"].mean()} | {
            q: g.loc[top & (per == q), "ret_6m"].mean() - g.loc[bot & (per == q), "ret_6m"].mean() for q in PERIODS}
        ic[name] = {"all": ics.mean()} | {q: ics[dper.reindex(ics.index) == q].mean() for q in PERIODS}
    sp, rc = pd.DataFrame(spread).T, pd.DataFrame(ic).T
    print(f"\n-- (b) the signal across all stocks: {g['date'].nunique()} dates, {len(g)} stock-months with all three "
          f"signals ({len(g) / f['ret_6m'].notna().sum():.1%} of those with a 6-month return)")
    print("top fifth − bottom fifth, mean 6-month return\n" + sp.round(4).to_string())
    print("mean monthly rank correlation with the 6-month return\n" + rc.round(4).to_string())
    corr = {}
    for name in VALUE:
        h = g.dropna(subset=list(TREND.values()))
        for tname, tcol in TREND.items():
            c = rank_corr(h, name, tcol)
            dper = h.drop_duplicates("date").set_index("date")["period"]
            corr[f"{name} × {tname}"] = {"all": c.mean()} | {q: c[dper.reindex(c.index) == q].mean() for q in PERIODS}
    print("shown, not deciding: mean monthly rank correlation with the trend signals\n" + pd.DataFrame(corr).T.round(3).to_string())
    me = "implied return"
    pos_sp, pos_ic = int((sp.loc[me, PERIODS] > 0).sum()), int((rc.loc[me, PERIODS] > 0).sum())
    beats = {k: (int((sp.loc[me, PERIODS] > sp.loc[k, PERIODS]).sum()), int((rc.loc[me, PERIODS] > rc.loc[k, PERIODS]).sum()))
             for k in ("plain E/P", "plain B/P")}
    items = {"spread positive in 3 of 4": pos_sp >= 3, "rank correlation positive in 3 of 4": pos_ic >= 3}
    items |= {f"beats {k} in 3 of 4 (spread {a}/4, rank correlation {b}/4)": a >= 3 and b >= 3 for k, (a, b) in beats.items()}
    print(f"spread positive {pos_sp}/4, rank correlation positive {pos_ic}/4")
    for k, v in items.items():
        print(f"   {k}: {'pass' if v else 'FAIL'}")
    print(f"   {market.upper()} (b) passes: {all(items.values())}")
    return all(items.values())


# ---------------------------------------------------------------- scores and portfolios

def scores(f: pd.DataFrame, market: str) -> tuple[pd.Series, pd.Series, list, list, pd.DataFrame]:
    """(old score, new score, old signals, new signals, the inclusion table): stage1_fix's score as it ran, and the
    same with the implied return in place of E/P and B/P."""
    p = stage1.percentiles(f, market)
    p["implied return"] = stage1.pct(f, "ier", 1)
    t = fix.inclusion(f, p)
    old = list(t.index[t["enters"]])
    top, bot = p["implied return"] >= 0.8, p["implied return"] <= 0.2
    row = {q: f.loc[(f["period"] == q) & f["ret_6m"].notna() & top, "ret_6m"].mean()
           - f.loc[(f["period"] == q) & f["ret_6m"].notna() & bot, "ret_6m"].mean() for q in PERIODS}
    row |= {"judged on": "return", "positive": sum(v > 0 for v in row.values())}
    row["enters"] = row["positive"] >= 3
    t.loc["implied return"] = pd.Series(row)
    new = [k for k in old if k not in ("E/P", "B/P")] + ["implied return"] if row["enters"] else old

    def score(sig: list) -> pd.Series:
        return p[sig].fillna(0.5).mean(axis=1).groupby(f["date"]).rank(pct=True) if sig else pd.Series(0.5, f.index)

    return score(old), score(new), old, new, t


def simulate(months: list, bench: np.ndarray, cost: float) -> tuple[np.ndarray, list, list]:
    """stage1_fix.simulate's holding-rule portfolio (no rng), with each entry's month: (returns, falls, entry months)."""
    held, rets, falls, when = [], [], [], []
    for t, mo in enumerate(months):
        held = [c for c in held if c in mo.keep]
        per = {}
        for c in held:
            per[mo.ind[c]] = per.get(mo.ind[c], 0) + 1
        new = []
        for c in mo.order:
            if len(held) + len(new) >= fix.N:
                break
            if c in held or per.get(mo.ind[c], 0) >= fix.CAP:
                continue
            new.append(c)
            per[mo.ind[c]] = per.get(mo.ind[c], 0) + 1
        held = held + new
        for c in new:
            if not np.isnan(mo.fall.get(c, np.nan)):
                falls.append(mo.fall[c])
                when.append(t)
        rets.append(np.mean([mo.ret[c] for c in held]) - cost * len(new) / fix.N if held else 0.0)
    return np.array(rets), falls, when


def setup(f: pd.DataFrame, market: str) -> tuple:
    dates = [d for d, g in f.groupby("date", sort=True) if g["ret_1m"].notna().any() and g["bench1"].notna().any()]
    bench = f.drop_duplicates("date").set_index("date")["bench1"].reindex(dates).to_numpy(float)
    period = f.drop_duplicates("date").set_index("date")["period"].reindex(dates).to_numpy()
    by = {d: g for d, g in f[f["date"].isin(dates)].groupby("date")}
    return dates, bench, period, by


def portfolio(f: pd.DataFrame, market: str, key: pd.Series) -> dict:
    dates, bench, period, by = setup(f, market)
    rets, falls, when = simulate([hold.Month(by[d], key) for d in dates], bench, stage1.COST[market])
    six = hold.six_month(rets, bench)
    start = period[: len(six)]
    fall_per = pd.Series(falls, index=period[when]) if falls else pd.Series(dtype=float)
    return {"six": six, "rets": rets, "falls": np.mean(falls) if falls else np.nan,
            "ret_q": {q: six[start == q].mean() for q in PERIODS},
            "fall_q": {q: fall_per[fall_per.index == q].mean() for q in PERIODS}}


# ---------------------------------------------------------------- (c) and (d)

def part_c(f: pd.DataFrame, market: str, old_s: pd.Series, new_s: pd.Series, new: list) -> bool:
    a, b = portfolio(f, market, old_s), portfolio(f, market, new_s)
    tab = pd.DataFrame({"stage 1 score: 6m over the fund": a["ret_q"], "new score: 6m over the fund": b["ret_q"],
                        "stage 1 score: 25%+ falls per entry": a["fall_q"], "new score: 25%+ falls per entry": b["fall_q"]}).T
    tab["all"] = [a["six"].mean(), b["six"].mean(), a["falls"], b["falls"]]
    good = {}
    for q in PERIODS:
        dr, df_ = b["ret_q"][q] - a["ret_q"][q], b["fall_q"][q] - a["fall_q"][q]
        good[q] = bool((dr > 0 and df_ <= 0) or (df_ < 0 and dr >= 0))
    print("\n-- (c) the holding-rule portfolio, new score against stage 1's corrected score\n" + tab.round(4).to_string())
    print("sub-periods with one better and the other no worse: " + ", ".join(f"{q} {'yes' if v else 'no'}" for q, v in good.items()))
    ok = "implied return" in new and sum(good.values()) >= 3
    print(f"   {market.upper()} (c) passes: {ok}" + ("" if "implied return" in new else " (the implied return doesn't enter)"))
    return ok


def part_d(f: pd.DataFrame, market: str, score: pd.Series, label: str) -> bool:
    """stage1_fix.bar's items 1-5 for `score` (same random portfolios, single signals and line)."""
    dates, bench, period, by = setup(f, market)
    period = period[: max(len(dates) - 5, 0)]
    cost = stage1.COST[market]
    keys = {"score": score} | {k: f.groupby("date")[c].rank(pct=True) for k, c in stage1.SINGLE.items()}
    res = {}
    for name, key in keys.items():
        rets, falls, entries = fix.simulate([hold.Month(by[d], key) for d in dates], bench, cost)
        res[name] = {"six": hold.six_month(rets, bench), "falls": np.mean(falls) if falls else np.nan, "rets": rets,
                     "turnover": np.mean(entries[1:]) / fix.N}
    months = [hold.Month(by[d], score) for d in dates]
    rng = np.random.default_rng(0)
    rnd = [fix.simulate(months, bench, cost, rng, res["score"]["turnover"]) for _ in range(fix.DRAWS)]
    rnd6 = np.array([hold.six_month(r, bench) for r, _, _ in rnd])
    rnd_fall = np.nanmean([np.mean(fl) for _, fl, _ in rnd if fl])
    ours = res["score"]["six"]
    sub = {q: ours[period == q].mean() for q in PERIODS}
    sub_rnd = {q: np.median(rnd6[:, period == q].mean(axis=1)) for q in PERIODS}
    beaten = (rnd6.mean(axis=1) < ours.mean()).mean()
    tab = {k: {"all": r["six"].mean()} | {q: r["six"][period == q].mean() for q in PERIODS}
           | {"25%+ falls per entry": r["falls"], "monthly turnover": r["turnover"]} for k, r in res.items()}
    tab["random portfolios (median)"] = {"all": np.median(rnd6.mean(axis=1))} | sub_rnd | {"25%+ falls per entry": rnd_fall}
    print(f"\n-- (d) {label}: 6-month return over the index fund, after costs, from every start month\n"
          + pd.DataFrame(tab).T.round(3).to_string())
    rets = res["score"]["rets"]
    curve, fund = np.cumprod(1 + rets), np.cumprod(1 + bench)
    print(f"a year over the fund {np.mean(rets - bench) * 12:+.3f}; max drawdown {(curve / np.maximum.accumulate(curve) - 1).min():.3f} "
          f"(fund {(fund / np.maximum.accumulate(fund) - 1).min():.3f}); beat {beaten:.1%} of {fix.DRAWS} random portfolios")
    ok = f["ret_6m"].notna() & score.notna()
    x = f["ret_6m"] - stage1.benchmark(f, market)
    slopes = {q: np.polyfit(score[ok & (f["period"] == q)], x[ok & (f["period"] == q)], 1)[0] for q in PERIODS}
    print("expected-return line slope by sub-period: " + ", ".join(f"{q} {v:+.3f}" for q, v in slopes.items()))
    dominated = [k for k in stage1.SINGLE if res[k]["six"].mean() > ours.mean() and res[k]["falls"] <= res["score"]["falls"]]
    items = {"1. mean over the fund > 0, positive in 3 of 4 sub-periods": ours.mean() > 0 and sum(v > 0 for v in sub.values()) >= 3,
             "2. beats 90% of random portfolios (no score), and their median in 3 of 4": beaten >= 0.9 and sum(sub[q] > sub_rnd[q] for q in sub) >= 3,
             "3. no single signal has more return with no more falls": not dominated,
             "4. 25%+ falls per entry no more than random portfolios'": res["score"]["falls"] <= rnd_fall,
             "5. expected-return line slopes up in 3 of 4 sub-periods": sum(v > 0 for v in slopes.values()) >= 3}
    for k, v in items.items():
        print(f"   {k}: {'pass' if v else 'FAIL'}" + (f" (dominated by {dominated})" if k.startswith("3") and dominated else ""))
    print(f"   {market.upper()} {label} passes: {all(items.values())}")
    return all(items.values())


def avoid(f: pd.DataFrame, score: pd.Series) -> None:
    """Reported, as stage1_fix: the avoid list against the 400 largest, per sub-period."""
    base = f.loc[f["blow"].notna() & (f["sample"] == "in"), "blow"].mean()
    largest = f["mcap_rank"] <= 400
    warn = (f["s1_chance"] > 2 * base) | (f["loss"] == 1) | (stage1.pct(f, "mom_6", 1) <= 0.2) | (f.get("heat", 0) == 1)
    av_ = stage1.lists(f, score, largest & warn, ascending=True)
    six = f["ret_6m"].notna()
    n = sum((f.loc[av_ & six & (f["period"] == q), "ret_6m"].mean() < f.loc[largest & six & (f["period"] == q), "ret_6m"].mean())
            and (f.loc[av_ & six & (f["period"] == q), "blow"].mean() > f.loc[largest & six & (f["period"] == q), "blow"].mean())
            for q in PERIODS)
    print(f"avoid list (reported): trailed the 400 largest and fell 25%+ more often in {n}/4 sub-periods; mean 6-month "
          f"return {f.loc[av_ & six, 'ret_6m'].mean():+.3f} vs {f.loc[largest & six, 'ret_6m'].mean():+.3f}, falls "
          f"{f.loc[av_ & six, 'blow'].mean():.1%} vs {f.loc[largest & six, 'blow'].mean():.1%}")


def run(market: str) -> None:
    warnings.simplefilter("ignore")
    f = load(market)
    old_s, new_s, old, new, t = scores(f, market)
    saved = pd.read_pickle(panel.BT / f"s1_{market}_fix.pkl").reset_index(drop=True)["fix_score"]
    print(f"\n==== {market.upper()} stage 3, parts (b)-(d): {f['date'].nunique()} month ends; implied return on "
          f"{f['ier'].notna().mean():.1%} of stock-months\nharness check: stage 1's corrected score reproduced "
          f"{'exactly' if np.allclose(old_s.to_numpy(), saved.to_numpy(), equal_nan=True) else 'NOT (stop)'}")
    part_b(f, market)
    print("\n-- the inclusion rule (as corrected), with the implied return as a return signal\n" + t.round(4).to_string()
          + f"\nstage 1 score: {old}\nnew score: {new}")
    part_c(f, market, old_s, new_s, new)
    part_d(f, market, old_s, "harness check, stage 1's corrected score (must match backtest.stage1_fix)")
    part_d(f, market, new_s, "(d) the ship bar with the new score")
    avoid(f, new_s)
    last = f["date"].max()
    show = f[f["date"] == last].assign(score=new_s)
    buys = stage1.lists(f, new_s, f["s1_field"].astype(bool))
    print(f"-- buys on {last} with the new score (shown, not used): " + ", ".join(
        f"{r['code']} {str(r['name'])[:10]} ({r['ier']:.1%})" for _, r in show[buys[show.index]].sort_values("score", ascending=False).iterrows()))
    f.assign(s3_old=old_s, s3_new=new_s, s3_buy=buys).to_pickle(panel.BT / f"s3_{market}_result.pkl")


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    {"run": run}[sys.argv[1]](sys.argv[2])
