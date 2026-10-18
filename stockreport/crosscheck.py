"""Data cross-checks and drift alarms (PLAN.md Method 13). Each figure the valuation rests on is compared
with a second, independent source (financial-data's rule: within 1% the sources agree, 1-5% is a small
gap, above 5% a figure is not usable): CN quotes, share counts, TTM profit and book with Tencent; US TTM
revenue, net income, equity and share counts with Yahoo's fundamentals; HK book, trailing EPS and share
counts with Yahoo's key statistics. A stock whose figure is more than `drop_gap` (20%: gaps of 5-15% are
mostly definitions, e.g. minority interests and perpetual securities in Yahoo's HK book) off its second
source, and not confirmed by a third where there is one (CN: Eastmoney's P/E and P/B), is dropped as
inconsistent data (rule 5). Gaps with a known structural cause are counted only: share classes and A+H counts at Yahoo,
Yahoo's HK EPS at older FX rates, adjusted vs GAAP consensus. Consensus EPS 20x+ off the trailing EPS on
a normal margin is a units error and drops the stock. Drift alarms compare each stock with the newest
earlier snapshot and are logged, never dropped. Every run prints the counts; the names go to the log."""

import logging
from datetime import date

import numpy as np
import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import tdx, tencent, yahoo

log = logging.getLogger(__name__)
CFG = CONFIG["crosscheck"]


def gap(ours: pd.Series, other: pd.Series) -> pd.Series:
    """Relative gap of a second source's figure from ours: inf when the signs differ, NaN when either is missing."""
    g = (other - ours).abs() / ours.abs()
    return g.where(np.sign(other) == np.sign(ours), np.inf).where(ours.notna() & other.notna())


def worse(g: pd.Series, *confirm: pd.Series) -> pd.Series:
    """The stocks the drop rule takes: more than drop_gap off the second source and no third source within it."""
    out = g > CFG["drop_gap"]
    for c in confirm:
        out &= ~(c <= CFG["drop_gap"])
    return out


def second_sources(df: pd.DataFrame, market: str) -> list[tuple[str, pd.Series, pd.Series | None]]:
    """(label, gap to the second source, the stocks it drops or None) per check."""
    if market == "cn":
        t = tencent.load().reindex(df.index)
        session = t["date"] == df["trade_date"]  # prices compare within one session; the rest any day
        t_profit, t_book = t["mcap"] / t["pe_ttm"].replace(0, np.nan), t["price"] / t["pb"].replace(0, np.nan)
        profit, book = gap(df["np_ttm"], t_profit), gap(df["bps"], t_book)
        shares = gap(df["shares"], t["shares"])
        return [("close vs Tencent", gap(df["price"], t["price"].where(session)), None),
                ("TDX close vs Tencent", gap(df["tdx_close"], t["price"].where(session)), None),
                ("shares vs Tencent", shares, worse(shares)),
                ("TTM profit vs Tencent", profit, worse(profit, gap(df["np_ttm"], df["mcap"] / df["pe_ttm_em"]))),
                ("book per share vs Tencent", book, worse(book, gap(df["bps"], df["price"] / df["pb_mrq_em"])))]
    if market == "us":
        y = pd.read_csv(yahoo.GAPS, dtype={"code": str, "period": str}).set_index("code").reindex(df.index)
        same = (df["source"] == "SEC") & (y["yahoo"] == "ok") & (y["currency"] == "USD") & (
            (pd.to_datetime(y["period"]) - pd.to_datetime(df["period"])).dt.days.abs() <= 20)
        y = y.where(same)
        adr = df["listing"].str.contains("Depositary", case=False, na=False)  # Yahoo counts the ordinary shares
        checks = [("TTM revenue vs Yahoo", gap(df["revenue_ttm"], y["revenue_ttm"])),
                  ("TTM net income vs Yahoo", gap(df["np_ttm"], y["ni_ttm"])),
                  ("equity vs Yahoo", gap(df["equity"], y["equity"]))]
        return [(label, g, worse(g)) for label, g in checks] + [
            ("shares vs Yahoo (not ADRs)", gap(df["shares"], y["shares"].where(~adr)), None)]
    c = pd.read_csv(yahoo.CONSENSUS, dtype={"code": str, "period_y": str}).set_index("code").reindex(df.index)
    c = c.where((pd.to_datetime(c["period_y"]) - pd.to_datetime(df["period"])).dt.days.abs() <= 20)
    book = gap(df["bps"], c["bvps_y"])
    return [("book per share vs Yahoo", book, worse(book)),
            ("trailing EPS vs Yahoo", gap(df["eps_ttm"], c["eps_ttm_y"]), None),
            ("shares vs Yahoo", gap(df["shares"], c["shares_y"]), None)]


def consensus(df: pd.DataFrame) -> list[tuple[str, pd.Series, bool]]:
    """(label, flagged stocks, drops?): units errors drop, basis gaps are only counted."""
    eps, margin = df["eps_ttm"], df["np_ttm"] / df["revenue_ttm"].where(df["revenue_ttm"] > 0)
    ratio = (df["eps_e2"] / eps).where((eps > 0) & (df["eps_e2"] > 0))
    units = ((ratio > CFG["units_ratio"]) | (ratio < 1 / CFG["units_ratio"])) & (margin >= 0.05)
    basis = (df["eps_e1"] / eps).where((eps > 0) & (df["eps_e1"] > 0) & (df["analysts"] >= 3))
    apart = (basis > CFG["basis_ratio"]) | (basis < 1 / CFG["basis_ratio"])
    return [(f"consensus EPS units ({CFG['units_ratio']}x+ off trailing EPS, 5%+ margin)", units, True),
            (f"consensus {CFG['basis_ratio']}x+ off trailing EPS (adjusted vs GAAP or a low base)", apart, False)]


def names(mask: pd.Series, n: int = 12) -> str:
    codes = list(mask.index[mask.fillna(False)])
    return " ".join(codes[:n]) + (" ..." if len(codes) > n else "")


def checks(df: pd.DataFrame, market: str, info: dict) -> dict[str, pd.Series]:
    """All cross-checks: the count lines go to info["checks"] (the run prints them), the names behind
    large gaps to the log; returns {reason: stocks to drop} for universe.finish."""
    agree, large, drop_gap = (f"{CFG[k]:.0%}" for k in ("agree", "large", "drop_gap"))
    lines, drops = [f"Cross-checks ({market.upper()}; compared: agree within {agree} / {agree}-{large} / "
                    f"over {large}, drops over {drop_gap}):"], {}
    try:
        sources = second_sources(df, market)
    except (OSError, KeyError) as e:  # no second-source table yet (fetch failed): the checks can't run
        sources = []
        lines.append(f"  second source unavailable ({type(e).__name__}: {e})")
    for label, g, drop in sources:
        n, large = int(g.notna().sum()), g > CFG["large"]
        line = f"  {label:<28} {n:4d}: {int((g <= CFG['agree']).sum()):4d} / " \
               f"{int(((g > CFG['agree']) & ~large).sum()):3d} / {int(large.sum()):3d}"
        if drop is not None:
            drops[f"{label} >{CFG['drop_gap']:.0%}"] = drop
            line += f", drops {int(drop.sum())}"
        lines.append(line)
        if large.any():
            log.info("%s %s over %.0f%%: %s", market.upper(), label, 100 * CFG["large"], names(large, 40))
    for label, flagged, drop in consensus(df):
        lines.append(f"  {label}: {int(flagged.sum())}" + (" dropped" if drop else " (counted only)"))
        if drop:
            drops[label] = flagged
        if flagged.any():
            log.info("%s %s: %s", market.upper(), label, names(flagged, 40))
    info["checks"] = lines
    return drops


def returns(market: str, start: str, end: str) -> pd.Series:
    """Each stock's chained return (close / prev_close, ex-rights adjusted) after `start` up to `end`."""
    px = tdx.load_prices() if market == "cn" else yahoo.load_prices(market)
    px = px[(px["date"] > start) & (px["date"] <= end)]
    return (px["close"] / px["prev_close"]).groupby(px["code"]).prod()


def drift(df: pd.DataFrame, market: str, today: date) -> list[str]:
    """Day-over-day alarms against the newest earlier snapshot: price and market value moving apart from the
    stock's chained return (a split, a bad price or a share count the quote doesn't reflect), TTM profit or
    book changing without a new report, next year's consensus jumping, and fair value moving while the price
    stayed flat. Logged, never dropped."""
    days = sorted(p.parent.name for p in (DATA / "snapshots").glob(f"*/{market}.csv.gz")
                  if p.parent.name < today.isoformat())
    if not days:
        return ["Drift: no earlier snapshot"]
    prev = pd.read_csv(DATA / "snapshots" / days[-1] / f"{market}.csv.gz",
                       dtype={"code": str, "period": str, "price_date": str}).set_index("code").reindex(df.index)
    lim = CFG["drift"]
    ret = returns(market, str(prev["price_date"].dropna().max()), str(df["price_date"].iloc[0]))
    ret = ret.reindex(df.index).fillna(1.0)  # no trade since: no return
    same = df["period"].astype(str) == prev["period"]
    year = (df["e1_year"].astype(str) == prev["e1_year"].astype(str)) if "e1_year" in prev else True
    book = gap(prev["bps"] * prev["shares"], df["bps"] * df["shares"])
    flat = (ret - 1).abs() < lim["value"]
    alarms = {"price vs the stock's return (a split?)": gap(prev["price"] * ret, df["price"]) > lim["value"],
              "market value vs the stock's return": gap(prev["mcap"] * ret, df["mcap"]) > lim["value"],
              "TTM profit without a new report": same & (gap(prev["np_ttm"], df["np_ttm"]) > lim["profit"]),
              "book without a new report": same & (book > lim["book"]),
              "next year's consensus EPS": year & (gap(prev["eps_e2"], df["eps_e2"]) > lim["consensus"]),
              "fair value with a flat price": flat & (gap(prev["fv_mid"], df["fv_mid"]) > lim["fair_value"])}
    for label, mask in alarms.items():
        if mask.any():
            log.info("%s drift since %s, %s: %s", market.upper(), days[-1], label, names(mask, 40))
    return [f"Drift alarms since {days[-1]} ({int(prev['price'].notna().sum())} stocks in both, logged only): "
            + ", ".join(f"{label} {int(mask.sum())}" for label, mask in alarms.items())]
