"""Stage 1, the ship bar on the portfolio docs/PLAN.md registers ("buy the 10 buys equal-weight, then hold or sell by the
holding rule"; random lists "held the same way"). backtest/stage1.py's first run scored a fresh list each month held 6
months instead (a deviation the stage review caught); this runs the registered portfolio once, on the same frames,
score, funnel and benchmark (stage1.py `bar` must have run: data/backtest/s1_<market>_result.pkl). Fixed before the run:
- Each month: keep the held names still in the funnel with a score at or above the date's median (the holding rule's
  卖出 line); fill to 10 from the funnel, best score first (random portfolios: in random order), at most 2 per industry;
  equal weight; a round trip of costs on each name that enters.
- Items 1-2: the portfolio's 6-month return over the index fund from every start month (compounded monthly returns),
  its mean over all starts and per sub-period; against 1,000 random portfolios run the same way.
- Item 3: the same portfolio on each single signal's percentile (plain E/P, plain B/P, 12-1 momentum).
- Item 4: 25%+ falls per entry: the share of entered names whose worst month-end within 6 months of entry was 25%+
  below the entry price, against the random portfolios' entries. Item 5 is the score's line, as in stage1.py.

  uv run python -m backtest.stage1_hold etf          # the index funds' daily adjusted closes (data/backtest/index_etf.csv.gz)
  uv run python -m backtest.stage1_hold bar cn|us|hk  # the registered portfolio, run once
"""

import sys
import warnings

import numpy as np
import pandas as pd

from backtest import panel, stage1

N, CAP, DRAWS = 10, 2, 1000


def etf() -> None:
    from stockreport.fetch.yahoo import URL, make_http
    http, rows = make_http(), []
    for sym in stage1.ETF.values():
        res = http.get(URL.format(symbol=sym), params={"period1": 1451606400, "period2": 1792000000, "interval": "1d",
                                                        "events": "div,split"}).json()["chart"]["result"][0]
        day = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(res["meta"]["exchangeTimezoneName"]).strftime("%Y-%m-%d")
        rows.append(pd.DataFrame({"symbol": sym, "date": day, "adjclose": res["indicators"]["adjclose"][0]["adjclose"],
                                  "close": res["indicators"]["quote"][0]["close"]}).dropna())
    pd.concat(rows).to_csv(panel.BT / "index_etf.csv.gz", index=False, compression="gzip")


class Month:
    """One month-end: the funnel's survivors (code → industry), the codes a holder keeps, returns and falls."""

    def __init__(self, g: pd.DataFrame, key: pd.Series):
        field = g[g["s1_field"].astype(bool)]
        self.ind = dict(zip(field["code"], field["industry"].fillna("")))
        self.order = list(field.assign(k=key[field.index]).sort_values("k", ascending=False)["code"])
        self.keep = set(field.loc[key[field.index] >= 0.5, "code"])
        self.ret = dict(zip(g["code"], g["ret_1m"].fillna(0)))
        self.fall = dict(zip(g["code"], g["blow"]))


def simulate(months: list[Month], bench: np.ndarray, cost: float, rng=None) -> tuple[np.ndarray, list[float]]:
    held, rets, falls = [], [], []
    for mo, b in zip(months, bench):
        held = [c for c in held if c in mo.keep]
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
        rets.append(np.mean([mo.ret[c] for c in held]) - cost * len(new) / N if held else 0.0)
    return np.array(rets), falls


def six_month(rets: np.ndarray, bench: np.ndarray) -> np.ndarray:
    """From each start month: the portfolio's compounded 6-month return minus the index fund's."""
    k = len(rets) - 5
    return np.array([np.prod(1 + rets[t: t + 6]) - np.prod(1 + bench[t: t + 6]) for t in range(max(k, 0))])


def bar(market: str) -> None:
    warnings.simplefilter("ignore")
    f = pd.read_pickle(panel.BT / f"s1_{market}_result.pkl").reset_index(drop=True)
    f["bench1"] = stage1.benchmark(f, market, "1m")
    dates = [d for d, g in f.groupby("date", sort=True) if g["ret_1m"].notna().any() and g["bench1"].notna().any()]
    bench = f.drop_duplicates("date").set_index("date")["bench1"].reindex(dates).to_numpy(float)
    period = f.drop_duplicates("date").set_index("date")["period"].reindex(dates).to_numpy()[: max(len(dates) - 5, 0)]
    cost = stage1.COST[market]
    by = {d: g for d, g in f[f["date"].isin(dates)].groupby("date")}
    keys = {"score": f["s1_score"]} | {k: f.groupby("date")[c].rank(pct=True) for k, c in stage1.SINGLE.items()}
    results = {}
    for name, key in keys.items():
        months = [Month(by[d], key) for d in dates]
        rets, falls = simulate(months, bench, cost)
        results[name] = (six_month(rets, bench), np.mean(falls) if falls else np.nan, rets)
    months = [Month(by[d], keys["score"]) for d in dates]
    rng = np.random.default_rng(0)
    rnd = [simulate(months, bench, cost, rng) for _ in range(DRAWS)]
    rnd6 = np.array([six_month(r, bench) for r, _ in rnd])
    rnd_fall = np.nanmean([np.mean(fl) for _, fl in rnd if fl])

    ours, fall, rets = results["score"]
    sub = {p: ours[period == p].mean() for p in stage1.PERIODS}
    sub_rnd = {p: np.median(rnd6[:, period == p].mean(axis=1)) for p in stage1.PERIODS}
    beaten = (rnd6.mean(axis=1) < ours.mean()).mean()
    print(f"\n==== {market.upper()} stage 1, the registered holding-rule portfolio: {len(dates)} months, {len(ours)} 6-month starts")
    tab = {name: {"all": r[0].mean()} | {p: r[0][period == p].mean() for p in stage1.PERIODS} | {"25%+ falls per entry": r[1]}
           for name, r in results.items()}
    tab["random portfolios (median)"] = {"all": np.median(rnd6.mean(axis=1))} | sub_rnd | {"25%+ falls per entry": rnd_fall}
    print("-- 6-month return over the index fund, after costs, from every start month\n" + pd.DataFrame(tab).T.round(3).to_string())
    curve = np.cumprod(1 + rets)
    print(f"annual excess {np.mean(rets - bench) * 12:+.3f}; max drawdown "
          f"{(curve / np.maximum.accumulate(curve) - 1).min():.3f} (index fund {(np.cumprod(1 + bench) / np.maximum.accumulate(np.cumprod(1 + bench)) - 1).min():.3f}); "
          f"the portfolio beat {beaten:.1%} of {DRAWS} random portfolios")
    best_single = max(results[k][0].mean() for k in stage1.SINGLE)
    items = {"1. mean over the index > 0, positive in 3 of 4 sub-periods": ours.mean() > 0 and sum(v > 0 for v in sub.values()) >= 3,
             "2. beats 90% of random portfolios, and their median in 3 of 4 sub-periods": beaten >= 0.9 and sum(sub[p] > sub_rnd[p] for p in sub) >= 3,
             "3. at least as good as the best single signal": ours.mean() >= best_single,
             "4. 25%+ falls no more frequent than random portfolios'": fall <= rnd_fall}
    for k, v in items.items():
        print(f"   {k}: {'pass' if v else 'FAIL'}")
    print("   5. (the score's expected-return line: as stage1.py's run)")


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    {"etf": lambda *_: etf(), "bar": bar}[sys.argv[1]](*(sys.argv[2:3]))
