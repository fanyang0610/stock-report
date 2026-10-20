"""Point-in-time month-end snapshots for the backtest (Phase 9): v1 (value, score, picks with and without
checks 1-2) and the history inputs per date, built once per market and cached (data/backtest/snap_<market>.pkl);
backtest/v3.py runs valuation v3 on them (Phase 13).

  uv run python -m backtest.run build cn|us|hk   # snapshots, v1, history inputs (cached)
"""

import logging
import pickle
import sys
import time
import warnings
from datetime import date

import numpy as np
import pandas as pd

from backtest import panel
from stockreport import history, pick, score, value

log = logging.getLogger("backtest.run")
IN_SAMPLE_END = "2023-12-31"  # calibrate on month ends up to here, check on the rest (A4)
QUARTERLY = True  # US: trailing numbers from 10-Qs (Phase 13); False rebuilds the annual-only snapshots
START = {"us": "2018-01"}  # the SEC table starts with FY2015 and growth needs two years: ~400 US names from 2018
V1_COLS = ["upside", "composite", "z_value", "z_quality", "z_growth", "z_momentum", "z_risk", "quality_pct", "mom_12_1",
           "np_growth", "cash_conv", "eps_ttm", "eps_e2", "analysts", "mcap_rank", "industry", "financial", "price",
           "ey", "by", "mcap"]


def months(market: str) -> list[str]:
    if market == "cn":
        return panel.month_ends(panel.calendar(), "2019-01-01", "2026-09-30")
    return [m.strftime("%Y-%m") for m in pd.period_range("2016-10", "2026-09", freq="M")]


def day_of(market: str, m: str) -> date:
    """The valuation day of a rebalance: the CN month-end trading day, else the calendar month end."""
    return date.fromisoformat(m) if market == "cn" else (pd.Period(m, "M").end_time.date())


def v1_picks(s: pd.DataFrame, checks: str = "both") -> pd.DataFrame:
    """v1's picks with checks 1-2 as in production ("both"), or with only one of them, or none."""
    return pick.pick(s, {"both": ("c1", "c2"), "none": (), "c1": ("c1",), "c2": ("c2",)}[checks])


def build(market: str) -> None:
    """Snapshots → v1 (value, score, picks with and without checks 1-2) → the history inputs, per date."""
    warnings.simplefilter("ignore")
    panel.setup_history(market)
    out, started = {}, time.monotonic()
    if market == "cn":
        cons = consensus_window()  # also the weekly-snapshot table, monthly here, for the revisions
        pd.concat([e.assign(snapshot=m) for m, e in cons.items()]).rename_axis("code").reset_index().to_csv(
            panel.HIST / "cn_consensus.csv.gz", index=False, compression="gzip")
        px, res, bal, val = panel.CNPrices(), panel.cn_results(), panel.cn_balance(), panel.cn_valuations()
        tdx_names = pd.concat([pd.read_csv(p, dtype={"code": str}, usecols=["date", "code", "name"])
                               for p in sorted((panel.BT / "tdx").glob("*.csv.gz"))]).dropna(subset=["name"])
        rates = panel.rates_series("cn")
    else:
        mon, today_snap, rates = panel.Monthly(market), panel.today_snapshot(market), panel.rates_series(market)
        res = history.hk_results() if market == "hk" else panel.us_books(today_snap)
        quarters = pd.read_csv(panel.BT / "us_quarterly.csv.gz", dtype={"code": str, "end": str, "filed": str}).dropna(
            subset=["end", "filed"]).sort_values(["code", "end"]) if market == "us" and QUARTERLY else None  # backtest.fetch sec
    for m in months(market):
        day = day_of(market, m)
        if market == "cn":
            snap, info = panel.cn_snapshot(m, px, res, bal, val, tdx_names, rates, cons.get(m))
            fwd = px.forward(m, list(snap.index))
        elif market == "us":
            snap, info = panel.us_snapshot(m, mon, today_snap, res, rates, quarters)
            fwd = mon.forward(m, snap.index)
        else:
            snap, info = panel.hk_snapshot(m, mon, today_snap, res, rates)
            fwd = mon.forward(m, snap.index)
        s = score.score(value.value(snap, float(snap["r"].iloc[0])))
        picks = {c: v1_picks(s, c) for c in ("both", "none", "c1", "c2")}
        loaded = history.load(market, s, day)
        out[m] = {"snap": s, "picks": picks, "loaded": loaded, "fwd": fwd, "info": info}
        log.info("%s %s: %d stocks, %d v1 picks (%.0fs)", market, m, len(s),
                 (picks["both"]["role"] == "pick").sum(), time.monotonic() - started)
    with open(panel.BT / f"snap_{market}.pkl", "wb") as f:
        pickle.dump(out, f)


def consensus_window() -> dict[str, pd.DataFrame]:
    """Point-in-time consensus for the CN month ends of 2026-01..09 from the research-report archive:
    per stock, the median FY EPS of the reports in the trailing 120 days, one report per broker (its
    newest), with the number of brokers as the analyst count. Years 1-3 are the first three fiscal
    years not yet reported (only FY2026-28 survive in the archive, so before a stock's FY2025 report e1
    is blank)."""
    path = panel.BT / "cn_reports.csv.gz"
    if not path.exists():
        return {}
    rep = pd.read_csv(path, dtype={"code": str})
    res = panel.cn_results()
    annual = res[res["period"].str.endswith("12-31")]
    out = {}
    for m in months("cn"):
        if m < "2026-01-01":
            continue
        win = rep[(rep["publish"] <= m) & (rep["publish"] > (pd.Timestamp(m) - pd.Timedelta(days=120)).strftime("%Y-%m-%d"))]
        win = win.sort_values("publish").drop_duplicates(["code", "org"], keep="last")
        med = win.groupby("code")[["eps_2026", "eps_2027", "eps_2028"]].median()
        n = win.groupby("code")["eps_2026"].count()
        reported_2025 = set(annual.loc[(annual["period"] == "2025-12-31") & (annual["notice_date"] < m), "code"])
        has25 = med.index.isin(reported_2025)
        e = pd.DataFrame(index=med.index)
        e["eps_e1"] = np.where(has25, med["eps_2026"], np.nan)  # FY2025 forecasts are gone from the archive
        e["eps_e2"] = np.where(has25, med["eps_2027"], med["eps_2026"])
        e["eps_e3"] = np.where(has25, med["eps_2028"], med["eps_2027"])
        e["analysts"] = n.reindex(med.index).fillna(0)
        e["e1_year"] = np.where(has25, "2026", "2025")
        out[m] = e
    return out


def load(market: str) -> dict:
    with open(panel.BT / f"snap_{market}.pkl", "rb") as f:
        return pickle.load(f)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if sys.argv[1] == "build":
        build(sys.argv[2])
