"""Data cross-checks and drift alarms (PLAN.md Method 13): each figure the valuation rests on against a second source
(within 1% agree, 1-5% small, above 5% unusable): CN quotes, shares, TTM profit and book with Tencent; US TTM revenue,
net income and equity with Yahoo's fundamentals, and shares with SEC's and Yahoo's counts (us_shares); HK book, trailing
EPS and shares with Yahoo's statistics. Over `drop_gap` (20%; 5-15% gaps are mostly definitions) and unconfirmed by a
third source (CN: Eastmoney's P/E, P/B; US shares: Yahoo): dropped (rule 5). Known structural gaps (HK A+H and
dual-class counts, Yahoo's HK EPS at old FX, adjusted vs GAAP consensus) are counted only; consensus EPS 20x+ off
trailing EPS on a normal margin is a units error and drops the stock. Drift alarms (against the newest earlier
snapshot) are logged, never dropped. Every run prints the counts; the names go to the log."""

import logging
from datetime import date

import numpy as np
import pandas as pd

from stockreport import history
from stockreport.config import CONFIG, DATA
from stockreport.fetch import sec, tdx, tencent, yahoo

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


def us_shares(df: pd.DataFrame) -> pd.DataFrame:
    """US share counts, before the universe is cut by market value: Nasdaq's market value ÷ its price (df["shares"])
    against SEC's two counts, the latest filing's cover page (as of a few weeks after the quarter) and the quarter's
    basic weighted-average shares (the EPS denominator: the shares the parent's profit and book belong to), each × the
    splits since, and Yahoo's quarter-end count (restated for splits). Nasdaq's stands when an SEC count is within
    `large` of it (it is often the cover's, newer than the quarter end: Gartner's buyback, GameStop's new shares). Else,
    when Yahoo's is within `large` of an SEC count, that count is used (the cover's first): two filings agree and
    Nasdaq doesn't (Monster's 2:1 split counted 3:1; Martin Marietta 18% high; Up-C units and voting-only classes the
    parent's profit leaves to minority interests: Carvana, TKO, Symbotic). More than drop_gap off both SEC counts and
    Yahoo's not within drop_gap of Nasdaq's: dropped (rule 5). Without an SEC count (Berkshire and Ares tag theirs per
    class only; foreign filers) and for ADRs (Nasdaq counts depositary shares), Nasdaq's stands."""
    cols = ["shares_cover", "cover_date", "shares_basic", "notice_date"]
    facts = pd.read_csv(sec.TABLE, dtype={"code": str, "cover_date": str, "notice_date": str})
    facts = facts.drop_duplicates("code", keep="last").set_index("code").reindex(df.index, columns=cols)
    splits, codes = history.read("us_splits"), df.index.to_series()
    adr = df["listing"].str.contains("Depositary", case=False, na=False)
    count = lambda col, day: (facts[col] * history.splits_after(splits, codes, facts[day].fillna("9999"))).where(~adr)
    cover, basic = count("shares_cover", "cover_date"), count("shares_basic", "notice_date")
    y = pd.read_csv(yahoo.GAPS, dtype={"code": str}).drop_duplicates("code", keep="last").set_index("code")["shares"].reindex(df.index)
    nasdaq, large, drop_gap = df["shares"], CFG["large"], CFG["drop_gap"]
    within = lambda a, b, limit: gap(a, b) <= limit  # False when either is missing
    agreed = cover.where(within(cover, y, large)).fillna(basic.where(within(basic, y, large)))
    fixed = ~(within(cover, nasdaq, large) | within(basic, nasdaq, large)) & agreed.notna()
    off = (cover.notna() | basic.notna()) & ~within(cover, nasdaq, drop_gap) & ~within(basic, nasdaq, drop_gap)
    return df.assign(shares=nasdaq.where(~fixed, agreed), shares_nasdaq=nasdaq, shares_fixed=fixed,
                     shares_gap=pd.concat([gap(cover, nasdaq), gap(basic, nasdaq)], axis=1).min(axis=1),
                     shares_drop=off & ~fixed & ~within(nasdaq, y, drop_gap))


def second_sources(df: pd.DataFrame, market: str) -> list[tuple]:
    """(label, gap to the second source, the stocks it drops or None[, the stocks it keeps as 低信心]) per check."""
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
        y = pd.read_csv(yahoo.GAPS, dtype={"code": str, "period": str, "balance_period": str}).set_index("code").reindex(df.index)
        near = lambda day: (pd.to_datetime(y[day]) - pd.to_datetime(df["period"])).dt.days.abs() <= 20
        y = y.where((df["source"] == "SEC") & (y["yahoo"] == "ok") & (y["currency"] == "USD") & near("period"))
        checks = [("TTM net income vs Yahoo", gap(df["np_ttm"], y["ni_ttm"])),
                  # Yahoo's latest equity can be a quarter older than its TTM (Amazon, Gartner on 2026-10-19)
                  ("equity vs Yahoo", gap(df["equity"], y["equity"].where(near("balance_period"))))]
        # Revenue sets the fair value only for loss-makers (P/S); for the rest a gap is mostly a definition
        # (brokers' net vs gross revenue, asset managers' carried interest, card issuers' partner payments)
        # and touches only the growth input: kept as 低信心.
        revenue, on_sales = gap(df["revenue_ttm"], y["revenue_ttm"]), ~df["financial"] & (df["np_ttm"] <= 0)
        return [("TTM revenue vs Yahoo", revenue, worse(revenue) & on_sales, worse(revenue) & ~on_sales)] + [
            (label, g, worse(g)) for label, g in checks] + [
            ("Nasdaq shares vs SEC", df["shares_gap"], df["shares_drop"])]
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
    large gaps to the log; returns {reason: stocks to drop} for universe.finish. Stocks kept despite a gap
    on a figure their fair value doesn't rest on are marked df["source_gap"] (低信心 in pick.py)."""
    agree, large, drop_gap = (f"{CFG[k]:.0%}" for k in ("agree", "large", "drop_gap"))
    lines, drops = [f"Cross-checks ({market.upper()}; compared: agree within {agree} / {agree}-{large} / "
                    f"over {large}, drops over {drop_gap}):"], {}
    try:
        sources = second_sources(df, market)
    except (OSError, KeyError) as e:  # no second-source table yet (fetch failed): the checks can't run
        sources = []
        lines.append(f"  second source unavailable ({type(e).__name__}: {e})")
    df["source_gap"] = False
    for label, g, drop, *keep in sources:
        n, large = int(g.notna().sum()), g > CFG["large"]
        line = f"  {label:<28} {n:4d}: {int((g <= CFG['agree']).sum()):4d} / " \
               f"{int(((g > CFG['agree']) & ~large).sum()):3d} / {int(large.sum()):3d}"
        if drop is not None:
            drops[f"{label} >{CFG['drop_gap']:.0%}"] = drop
            line += f", drops {int(drop.sum())}"
        if keep:
            df["source_gap"] |= keep[0].fillna(False)
            line += f", kept as 低信心 {int(keep[0].sum())}"
            if keep[0].any():
                log.info("%s %s over %.0f%%, kept as 低信心: %s", market.upper(), label, 100 * CFG["drop_gap"], names(keep[0], 40))
        lines.append(line)
        if large.any():
            log.info("%s %s over %.0f%%: %s", market.upper(), label, 100 * CFG["large"], names(large, 40))
    if "shares_fixed" in df:
        fixed = df["shares_fixed"].fillna(False).astype(bool)
        lines.append(f"  shares set to SEC's count (Yahoo's agrees, Nasdaq's doesn't): {int(fixed.sum())}")
        if fixed.any():
            log.info("%s shares set to SEC's count: %s", market.upper(), names(fixed, 40))
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
    book changing without a new report, and next year's consensus jumping. Logged, never dropped."""
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
    alarms = {"price vs the stock's return (a split?)": gap(prev["price"] * ret, df["price"]) > lim["value"],
              "market value vs the stock's return": gap(prev["mcap"] * ret, df["mcap"]) > lim["value"],
              "TTM profit without a new report": same & (gap(prev["np_ttm"], df["np_ttm"]) > lim["profit"]),
              "book without a new report": same & (book > lim["book"]),
              "next year's consensus EPS": year & (gap(prev["eps_e2"], df["eps_e2"]) > lim["consensus"])}
    for label, mask in alarms.items():
        if mask.any():
            log.info("%s drift since %s, %s: %s", market.upper(), days[-1], label, names(mask, 40))
    return [f"Drift alarms since {days[-1]} ({int(prev['price'].notna().sum())} stocks in both, logged only): "
            + ", ".join(f"{label} {int(mask.sum())}" for label, mask in alarms.items())]
