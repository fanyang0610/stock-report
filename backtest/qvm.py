"""The history run (docs/PLAN.md, "The history run"; stage 1, again in stage 3 and its redo): the app's own score and
list (stockreport.score, stockreport.lists) on every month-end snapshot (backtest/run.py), each month's 20-name portfolio
and its 10 and 5 highest scores held 12 months after a round trip of costs against the index fund with dividends (SPY,
2800.HK, 510300.SS), and each family's top fifth against its bottom fifth. It fills the report's 预期 line
(data/history/expect.json) and catches bugs; it decides nothing else.
- Portfolios: the app's buy rule each month (lists.positions: each sector's places by its share of the free-float
  value, its best scores, equal amounts, the screen) on the whole snapshot (the 800 largest; HK all that pass the
  floors). Free float then: CN market value × today's CSI 300 float factor (the median outside it; float_factors), HK
  market value × today's HK-listed share of all shares, US market value. Held 12 months; a cohort's 12 months run month
  end to month end (CN: month-end trading days). The snapshots have no consensus estimates (CN's only from 2026) and
  Yahoo keeps no history of EBIT, debt, cash and accruals, so the score has no forward E/P, revisions or EBIT/EV here
  and the screen doesn't run; the long-run components come from the annual reports public by each date.
- The largest fall: the Jegadeesh-Titman portfolio, 1/12 of the money in each of the last 12 cohorts, each month's
  return the cohorts' average (cost spread as 1/12 of a round trip a month), against the fund over the same months.
- Snapshots built before stage 1 carry inputs winsorized at 2/98% (ROE, debt, 12-1 momentum, growth: ties at the
  extremes) and dropped stocks without growth figures; US gross profit has no Yahoo fill here; all three hold today's
  listings (Eastmoney drops delisted A-shares), and CN 扣非 figures are Eastmoney's latest (restated) ones under the
  first notice date. The score's financials are set by today's definitions (stockreport.universe) on each snapshot.

  uv run python -m backtest.qvm frame cn|us|hk   # the score on every snapshot: data/backtest/qvm_<market>.pkl
  uv run python -m backtest.qvm run cn|us|hk     # portfolios and families; writes data/history/expect.json
"""

import json
import sys
import warnings
from datetime import timedelta

import numpy as np
import pandas as pd

from backtest import panel, run
from backtest.funnel import COST, PERIODS
from backtest.stage1 import ETF
from stockreport import history, lists, signals, universe
from stockreport.config import CONFIG, DATA
from stockreport.fetch import eastmoney, index, sec, swclass, yahoo
from stockreport.score import score

SIZES, HOLD = (20, 10, 5), 12
KEEP = ["name", "sector", "financial", "country", "mcap_rank", "mcap", "float_value", "price", "score", "distress",
        "f_value", "f_quality", "f_growth", "f_momentum"]
EXPECT = history.HISTORY / "expect.json"


def float_factors(market: str) -> pd.Series:
    """Today's free-float factor per stock (CN: the CSI 300 file's, relative, as universe.cn_float reads it; HK: its
    HK-listed shares over all its shares), from the newest snapshot; US none (market value)."""
    snap = pd.read_csv(sorted((DATA / "snapshots").glob(f"*/{market}.csv.gz"))[-1], dtype={"code": str}).set_index("code")
    if market == "hk":
        listed = pd.read_csv(yahoo.HK_SHARES, dtype={"code": str}).drop_duplicates("code").set_index("code")["shares_class"]
        return (listed / snap["shares"]).dropna().clip(upper=1)
    if market == "cn":
        return universe.cn_float(snap["mcap"], index.load()) / snap["mcap"]
    return pd.Series(dtype=float)


# ---------------------------------------------------------------- the score on each snapshot

def prepare(s: pd.DataFrame, market: str, m: str, ytd: pd.DataFrame | None) -> pd.DataFrame:
    """The live universe's extra columns for one snapshot: sector, year-to-date figures for the cash backing, and the
    US preferred-equity shares."""
    s = s.copy()
    day = run.day_of(market, m)
    if market == "cn":
        s["sector"] = s["industry"].str[2:4].map(swclass.L1).fillna("未分类")
        s["financial"] = s["sector"].isin(universe.CN_FINANCIAL)
        key = pd.MultiIndex.from_arrays([s.index, s["period"]])
        s["revenue_ytd"], s["np_ytd"] = (ytd[c].reindex(key).to_numpy() for c in ("revenue", "np"))
        s["ocf_ytd"] = s["ocfps"] * s["shares"]
    elif market == "hk":
        s["sector"] = s["industry_type"].fillna("").str.split("-").str[0].replace("", "未分类")
        s["financial"] = s["industry_type"].fillna("").str.split("-").str[-1].isin(CONFIG["peers"]["financial_industries_hk"])
        s["revenue_ytd"] = ytd["revenue"].reindex(pd.MultiIndex.from_arrays([s.index, s["period"]])).to_numpy()
        s["np_ytd"], s["ocf_ytd"] = s["np"], s["ocf"]  # CNY, as the revenue
    else:
        s["sector"] = s["sector"].replace("", np.nan).fillna("Miscellaneous")
        s["financial"] = universe.us_financial(s["industry_raw"], sec.load_ciks().reindex(s.index))
        pref = history.us_preferred(s, day)[["pref_share", "pref_div_share"]]
        s = s.join(pref).fillna({"pref_share": 0.0, "pref_div_share": 0.0})
    return s


def frame(market: str) -> pd.DataFrame:
    warnings.simplefilter("ignore")
    panel.setup_history(market)
    snaps, rows, ytd, deduct, factor = run.load(market), [], None, None, float_factors(market)
    if market == "cn":
        ytd = panel.cn_results().drop_duplicates(["code", "period"]).set_index(["code", "period"])
        deduct = pd.read_csv(eastmoney.CN_DEDUCT, dtype={"code": str, "period": str, "notice_date": str})
    if market == "hk":
        ytd = history.hk_results().sort_values("date_type").drop_duplicates(["code", "period"]).set_index(["code", "period"])
    years = history.YEARS[market]()
    for m, d in snaps.items():
        if m < run.START.get(market, ""):
            continue
        s = prepare(d["snap"], market, m, ytd)
        s["float_value"] = s["mcap"] * (factor.reindex(s.index).fillna(factor.median()) if len(factor) else 1.0)
        day = run.day_of(market, m)
        s = s.join(signals.long_run(years, day.isoformat()))
        cn = signals.cn_deduct(deduct, (day - timedelta(days=1)).isoformat()) if market == "cn" else None  # public before
        sc = score(s, market, cn, lines=False)
        rows.append(sc.reindex(columns=KEEP + [c for c in sc if c.startswith("p_")]).join(d["fwd"]).assign(date=m))
    f = pd.concat(rows).rename_axis("code").reset_index()
    f.to_pickle(panel.BT / f"qvm_{market}.pkl")
    print(f"{market}: {f['date'].nunique()} dates, {len(f)} rows, components present "
          + str({c[2:]: round(f[c].notna().mean(), 2) for c in f if c.startswith("p_")}))
    return f


# ---------------------------------------------------------------- portfolios

class Paths:
    """Growth of each stock from a formation date to each of the next 12 month ends, and the fund's."""

    def __init__(self, market: str, dates: list[str]):
        self.market = market
        e = pd.read_csv(panel.BT / "index_etf.csv.gz")
        self.fund = e[e["symbol"] == ETF[market]].set_index("date")["adjclose"].sort_index()
        if market == "cn":
            self.px = panel.CNPrices()
            ends = self.px.days[self.px.eom]
            self.ends = {d: [str(x) for x in ends[ends > d][:HOLD]] for d in dates}
        else:
            self.mon = panel.Monthly(market)
            months = list(self.mon.ret.index)
            self.ends = {d: months[months.index(d) + 1: months.index(d) + 1 + HOLD] for d in dates}

    def fund_level(self, day: str) -> float:
        if self.market != "cn":
            day = pd.Period(day, "M").end_time.strftime("%Y-%m-%d")
        i = self.fund.index.searchsorted(day, side="right") - 1
        return self.fund.iloc[i] if i >= 0 and day <= self.fund.index[-1] else np.nan

    def growth(self, d: str, weights: pd.Series) -> tuple[list[str], np.ndarray, np.ndarray]:
        """(month keys, the portfolio's growth since d at its weights, the fund's) at each month end after d."""
        ends = self.ends[d]
        if self.market == "cn":
            held = [c for c in weights.index if c in self.px.col]
            cols, w = [self.px.col[c] for c in held], weights[held].to_numpy()
            t = self.px.at(d)
            lv = self.px.level[[self.px.at(e) for e in ends]][:, cols] / self.px.level[t, cols]
            port = lv @ (w / w.sum())
        else:
            r = self.mon.ret.loc[ends].reindex(columns=weights.index).fillna(0)
            port = (1 + r).cumprod().to_numpy() @ (weights / weights.sum()).to_numpy()
        fund = np.array([self.fund_level(e) for e in ends]) / self.fund_level(d)
        return [e[:7] for e in ends], np.asarray(port, float), fund


def portfolios(f: pd.DataFrame, market: str) -> dict[str, pd.Series]:
    """Each month's 20-name list: code -> weight (lists.positions, in score order)."""
    out = {}
    for d, g in f.groupby("date"):
        buys, _ = lists.positions(g.set_index("code").sort_values("score", ascending=False), CONFIG["lists"]["buys"], market)
        out[d] = buys["weight"]
    return out


def largest(picks: dict[str, pd.Series], n: int) -> dict[str, pd.Series]:
    """The n highest scores of each list (the lists are in score order; equal amounts, scaled in Paths.growth)."""
    return {d: w.iloc[:n] for d, w in picks.items()}


def drawdown(monthly: pd.Series) -> float:
    curve = (1 + monthly).cumprod()
    return float((curve / curve.cummax() - 1).min())


def evaluate(paths: Paths, picks: dict[str, pd.Series], cost: float) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Per cohort with 12 months: its return and the fund's; the overlapping portfolio's monthly returns and the fund's."""
    windows, cohort_ret, fund_ret = [], {}, {}
    for d, weights in picks.items():
        keys, port, fund = paths.growth(d, weights)
        if not keys:
            continue
        port = port * (1 - cost)
        if len(keys) == HOLD and np.isfinite(fund[-1]):
            windows.append({"date": d, "ret": port[-1] - 1, "fund": fund[-1] - 1})
        prev_p, prev_f = np.r_[1 - cost, port[:-1]], np.r_[1.0, fund[:-1]]
        cohort_ret[d] = pd.Series(port / prev_p - 1, keys)
        fund_ret[d] = pd.Series(fund / prev_f - 1, keys)
    by_month = pd.DataFrame(cohort_ret)  # month key × cohort
    first = sorted(picks)[HOLD - 1][:7]  # from the month all 12 cohorts are held
    active = by_month.notna().sum(axis=1) >= HOLD
    monthly = by_month[active & (by_month.index > first)].mean(axis=1) - cost / HOLD
    fund = pd.DataFrame(fund_ret).loc[monthly.index].mean(axis=1)  # every cohort's fund month is the same month
    return pd.DataFrame(windows).set_index("date"), monthly, fund


def families(f: pd.DataFrame) -> pd.DataFrame:
    """Each family's (and the score's) top fifth minus bottom fifth on the mean 12-month return, per sub-period."""
    f = f[f["ret_12m"].notna()]
    per = np.select([f["date"].between(*p) for p in PERIODS.values()], list(PERIODS), "")
    rows = {}
    for col in ("f_value", "f_quality", "f_growth", "f_momentum", "score"):
        pct = f.groupby("date")[col].rank(pct=True)
        spread = (f[pct > 0.8].groupby("date")["ret_12m"].mean() - f[pct <= 0.2].groupby("date")["ret_12m"].mean())
        p = pd.Series(per, f.index).groupby(f["date"]).first().reindex(spread.index)
        rows[col] = {"all": spread.mean()} | {k: spread[p == k].mean() for k in PERIODS}
    t = pd.DataFrame(rows).T
    t["sub-periods positive"] = (t[list(PERIODS)] > 0).sum(axis=1)
    return t


def run_market(market: str) -> None:
    warnings.simplefilter("ignore")
    f = pd.read_pickle(panel.BT / f"qvm_{market}.pkl")
    dates = sorted(f["date"].unique())
    paths, cost, result = Paths(market, dates), COST[market], {}
    print(f"\n==== {market.upper()}: {len(dates)} month ends {dates[0]}..{dates[-1]}, fund {ETF[market]}, round trip {cost:.1%}")
    t = families(f)
    print("-- top fifth − bottom fifth, mean 12-month return\n" + t.round(3).to_string())
    lists20 = portfolios(f, market)
    for n in SIZES:
        w, monthly, fund = evaluate(paths, largest(lists20, n), cost)
        ex = w["ret"] - w["fund"]
        worst = w["ret"].idxmin()
        r = {"excess": ex.mean(), "beat": (ex > 0).mean(), "worst": w.at[worst, "ret"], "worst_fund": w.at[worst, "fund"],
             "worst_excess": ex.min(), "best_excess": ex.max(), "p10": ex.quantile(0.1), "p90": ex.quantile(0.9),
             "drawdown": drawdown(monthly), "mean": w["ret"].mean(), "fund_mean": w["fund"].mean()}
        per = pd.Series(np.select([pd.Series(w.index).between(*p) for p in PERIODS.values()], list(PERIODS), ""), w.index)
        r["periods"] = {k: ex[per == k].mean() for k in PERIODS if (per == k).any()}
        result[str(n)] = r
        print(f"-- {n} names: {len(w)} windows ({w.index[0]}..{w.index[-1]}); 12-month return {r['mean']:+.1%} vs fund "
              f"{r['fund_mean']:+.1%}: excess {r['excess']:+.1%}, beat {r['beat']:.0%}, 10th/90th pct {r['p10']:+.1%}/"
              f"{r['p90']:+.1%}, worst excess {r['worst_excess']:+.1%}; worst 12 months {r['worst']:+.1%} (fund {r['worst_fund']:+.1%}, "
              f"{worst}); largest fall {r['drawdown']:.1%} (fund {drawdown(fund):.1%}, {monthly.index[0]}..{monthly.index[-1]}); "
              "by sub-period " + ", ".join(f"{k} {v:+.1%}" for k, v in r["periods"].items()))
        if n == 20:
            first, last_month, fund_dd, n_windows = w.index[0][:7], w.index[-1][:7], drawdown(fund), len(w)
    last = lists20[dates[-1]]
    names = f[f["date"] == dates[-1]].set_index("code")["name"]
    print(f"-- {dates[-1]} portfolio: " + ", ".join(f"{c} {names[c]} {x:.1%}" for c, x in last.items()))
    held = {d: x.index for d, x in lists20.items()}
    top = {d: f.loc[f["date"] == d].nsmallest(10, "mcap_rank")["code"] for d in dates}
    print(f"-- the 10 largest companies held, average per list: {np.mean([len(set(held[d]) & set(top[d])) for d in dates]):.1f}; "
          f"weight in them {np.mean([lists20[d][lists20[d].index.isin(top[d])].sum() for d in dates]):.0%}")
    runs = json.loads(EXPECT.read_text(encoding="utf-8")) if EXPECT.exists() else {}
    runs[market] = {"first": first, "last": last_month, "windows": n_windows, "fund_drawdown": fund_dd, "portfolios": result,
                    "families": {k: v["all"] for k, v in t.T.to_dict().items()}}
    EXPECT.write_text(json.dumps(runs, ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    {"frame": frame, "run": run_market}[sys.argv[1]](sys.argv[2])
