"""How long a company's advantages last, measured in the screening's history tables (today's listings only, so
survivors: persistence above the median and recovery below it are overstated): margins against their own median,
revenue growth above its size fifth's, returns above their cost. backtest/persistence.py prints the full
measurement; value.py uses the rates PLAN.md's rules name (margin_keep, lasting_keep, growth_shares, excess_keep)."""

from functools import lru_cache

import numpy as np
import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.research import damodaran

MIN_GAP = 0.03  # a margin 3 points or more from its median: smaller gaps are noise around it
MARGIN_NAME = {"us": "operating margin", "cn": "扣非 net margin", "hk": "net margin"}
COUNTRY = {"cn": "China", "hk": "Hong Kong", "us": "United States"}


def complete(p: pd.DataFrame) -> pd.DataFrame:
    """Years with at least half the previous year's companies (the newest year is partial until reports are in)."""
    n = p.notna().sum()
    return p.loc[:, [c for i, c in enumerate(p.columns) if i == 0 or n[c] >= n.iloc[i - 1] / 2]]


def wide(t: pd.DataFrame, col: str) -> pd.DataFrame:
    return complete(t.drop_duplicates(["code", "year"], keep="last").pivot(index="code", columns="year", values=col).sort_index(axis=1))


@lru_cache(maxsize=3)
def margin_table(market: str) -> pd.DataFrame:
    """Margin per company and fiscal year: US operating income over revenue; CN 扣非 profit over revenue and HK profit
    over revenue (the CN and HK tables carry no operating profit)."""
    h = DATA / "history"
    if market == "us":
        t = pd.read_csv(h / "us_annual.csv.gz", dtype={"code": str}, usecols=["code", "fy_end", "revenue", "op_income"])
        t = t.assign(year=t["fy_end"].str[:4], m=t["op_income"] / t["revenue"].where(t["revenue"] > 0))
    elif market == "cn":
        a = pd.read_csv(h / "cn_annual.csv.gz", dtype={"code": str}, usecols=["code", "period", "revenue"])
        d = pd.read_csv(h / "cn_deduct.csv.gz", dtype={"code": str}, usecols=["code", "period", "deduct"])
        t = a.merge(d[d["period"].str.endswith("12-31")], on=["code", "period"])
        t = t.assign(year=t["period"].str[:4], m=t["deduct"] / t["revenue"].where(t["revenue"] > 0))
    else:
        t = pd.read_csv(h / "hk_results.csv.gz", dtype={"code": str}, usecols=["code", "period", "date_type", "revenue", "np"])
        t = t[t["date_type"] == 1]
        t = t.assign(year=t["period"].str[:4], m=t["np"] / t["revenue"].where(t["revenue"] > 0))
    return wide(t.assign(m=t["m"].clip(-1, 1)), "m")


def margin_gaps(m: pd.DataFrame, window: int, current: bool, h: int, side: str, net: bool = True,
                among: pd.DataFrame | None = None) -> pd.DataFrame:
    """Each company-year's gap to its own median over `window` years (ending with the year, or the year before), the
    two years before it against the same median (`prev1`, `prev2`: gap_spells) and the margin's distance from that
    median `h` years on; `net`: less the market's drift (the median company's distance from its own median h years on:
    CN margins fell through 2010-2025, US margins rose, a trend of the decade a forecast shouldn't carry); `among`:
    the companies counted in each start year (the drift stays the whole table's)."""
    cols, rows = list(m.columns), []
    for i in range(window - (0 if current else -1) - 1, len(cols) - h):
        hist = m[cols[i - window + 1:i + 1] if current else cols[i - window:i]]
        med = hist.median(axis=1).where(hist.notna().all(axis=1))
        gap, later = m[cols[i]] - med, m[cols[i + h]] - med
        drift = later.where(gap.notna()).median() if net else 0.0
        ok = later.notna() & (gap >= MIN_GAP if side == "above" else gap <= -MIN_GAP)
        if among is not None:
            ok &= among[cols[i]].reindex(m.index, fill_value=False)
        rows.append(pd.DataFrame({"gap": gap[ok], "later": later[ok] - drift, "start": cols[i],
                                  "prev1": (m[cols[i - 1]] - med)[ok], "prev2": (m[cols[i - 2]] - med)[ok]}))
    return pd.concat(rows) if rows else pd.DataFrame(columns=["gap", "later", "start", "prev1", "prev2"])


def margin_kept(m: pd.DataFrame, window: int, current: bool, h: int, side: str, net: bool = True) -> dict:
    d = margin_gaps(m, window, current, h, side, net)
    if d.empty:
        return {"median": float("nan"), "n": 0, "cohorts": 0}
    return {"median": float((d["later"] / d["gap"]).median()), "n": len(d), "cohorts": d["start"].nunique()}


def slope(x: pd.Series, y: pd.Series) -> float:
    """y's slope on x across the deciles of x (their medians, robust to the tails), between 0 and 1."""
    t = pd.DataFrame({"x": x, "y": y}).groupby(pd.qcut(x, 10, labels=False, duplicates="drop")).median()
    return float(min(max(np.polyfit(t["x"], t["y"], 1)[0], 0.0), 1.0)) if len(t) > 2 else 0.0


@lru_cache(maxsize=3)
def revenue_table(market: str) -> pd.DataFrame:
    """Annual revenue per company and fiscal year (USD filers in the US, so growth isn't a currency move)."""
    h = DATA / "history"
    if market == "cn":
        t = pd.read_csv(h / "cn_annual.csv.gz", dtype={"code": str}, usecols=["code", "period", "revenue"])
        t = t.assign(year=t["period"].astype(str).str[:4])
    elif market == "us":
        t = pd.read_csv(h / "us_annual.csv.gz", dtype={"code": str}, usecols=["code", "fy_end", "revenue", "currency"])
        t = t[t["currency"] == "USD"].assign(year=lambda d: d["fy_end"].str[:4])
    else:
        t = pd.read_csv(h / "hk_results.csv.gz", dtype={"code": str}, usecols=["code", "period", "date_type", "revenue"])
        t = t[t["date_type"] == 1].assign(year=lambda d: d["period"].str[:4])
    return t.drop_duplicates(["code", "year"], keep="last").pivot(index="code", columns="year", values="revenue").sort_index(axis=1)


def excess_growth(p: pd.DataFrame, past: int, h: int) -> pd.DataFrame:
    """Each company-year's revenue growth over the past `past` years and in year t+h, both above the median of the
    company's size fifth (its revenue rank in year t), complete years only."""
    cols, rows = list(complete(p).columns), []
    for i in range(past, len(cols) - h):
        s0, s, a, b = p[cols[i - past]], p[cols[i]], p[cols[i + h - 1]], p[cols[i + h]]
        ok = (s0 > 0) & (s > 0) & (a > 0) & (b > 0)
        d = pd.DataFrame({"past": (s[ok] / s0[ok]) ** (1 / past) - 1, "next": b[ok] / a[ok] - 1,
                          "fifth": (s.rank(pct=True)[ok] * 5).clip(upper=4.999).astype(int)})
        d = d[d["past"].between(-0.5, 1.0) & d["next"].between(-0.5, 1.0)]
        rows.append(d[["past", "next"]] - d.groupby("fifth")[["past", "next"]].transform("median"))
    return pd.concat(rows) if rows else pd.DataFrame(columns=["past", "next"])


def growth_profile(market: str, past: int, years: int = 5) -> dict[int, tuple[float, int]]:
    """The share of the past years' excess growth kept in each of the next `years` years: {h: (slope, observations)}."""
    p, out = revenue_table(market), {}
    for h in range(1, years + 1):
        d = excess_growth(p, past, h)
        out[h] = (slope(d["past"], d["next"]), len(d))
    return out


@lru_cache(maxsize=3)
def return_table(market: str) -> pd.DataFrame:
    """Return on equity per company and fiscal year (CN and HK: the tables' ROE; US: profit over year-end equity)."""
    h = DATA / "history"
    if market == "us":
        t = pd.read_csv(h / "us_annual.csv.gz", dtype={"code": str}, usecols=["code", "fy_end", "ni", "equity"])
        t = t.assign(year=t["fy_end"].str[:4], r=t["ni"] / t["equity"].where(t["equity"] > 0))
    elif market == "cn":
        t = pd.read_csv(h / "cn_annual.csv.gz", dtype={"code": str}, usecols=["code", "period", "roe"])
        t = t.assign(year=t["period"].str[:4], r=t["roe"] / 100)
    else:
        t = pd.read_csv(h / "hk_results.csv.gz", dtype={"code": str}, usecols=["code", "period", "date_type", "roe"])
        t = t[t["date_type"] == 1].assign(year=lambda d: d["period"].str[:4], r=lambda d: d["roe"] / 100)
    return wide(t.assign(r=t["r"].clip(-2, 2)), "r")


def hurdle(market: str) -> float:
    """Today's stable cost of equity in the market: its 10-year yield plus Damodaran's mature-market premium."""
    from stockreport.research import value
    c = damodaran.country(COUNTRY[market])
    return value.rate(market)[0] + c["erp"] - c["crp"]


def pav(x: list[float]) -> list[float]:
    """The closest non-increasing sequence (least squares; pool-adjacent-violators): a share kept can't rise with
    time, and the US's thinner years otherwise give growth that falls and rises again."""
    blocks = []
    for v in x:
        blocks.append([v, 1])
        while len(blocks) > 1 and blocks[-2][0] < blocks[-1][0]:
            (a, n), (b, k) = blocks[-2], blocks.pop()
            blocks[-1] = [(a * n + b * k) / (n + k), n + k]
    return [v for v, n in blocks for _ in range(n)]


KEPT_YEARS = 3  # the margin horizon every market measures with 3+ start years (US and HK: 11 complete years)


@lru_cache(maxsize=3)
def margin_keep(market: str) -> dict:
    """The share of a margin's gap to its own median kept each year, above and below apart: the median share kept
    3 years on (median of the 5 years before, net of the market's drift, gaps of 3+ points), as an annual rate (Fama
    and French 2000's partial-adjustment model: the gap shrinks by the same share each year)."""
    m, out = margin_table(market), {}
    for side in ("above", "below"):
        kept = margin_kept(m, 5, False, KEPT_YEARS, side)["median"]
        out[side] = float(min(max(kept, 0.0), 1.0) ** (1 / KEPT_YEARS))
    return out


LASTING_YEARS = 3  # a lasting gap: on its side in each of the last 3 years
LASTING_SIDES = {"cn": ("below",), "us": ("above", "below"), "hk": ("below",)}  # where a gap that has lasted 3 years
# keeps more than one that just opened, the 90% interval above zero against both the 5 years' median before and the
# 8-year median the forecast anchors on (backtest/persistence.py; PLAN.md "Forecast")
LASTING_HORIZON = 8  # the longest horizon read, where the history has 3 start years for it (a 10-year forecast's rate)


def gap_spells(d: pd.DataFrame, side: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """margin_gaps' rows split: the gap has lasted (3 points or more on its side in each of the last 3 years), or it
    opened in the last year (the year before wasn't on its side). A 2-year gap is in neither."""
    s = 1 if side == "above" else -1
    return d[(s * d["prev1"] >= MIN_GAP) & (s * d["prev2"] >= MIN_GAP)], d[s * d["prev1"] < MIN_GAP]


@lru_cache(maxsize=1)
def frames_margins() -> tuple[pd.DataFrame, pd.DataFrame]:
    """US net margin per filer and year from SEC's frames (2009 on, dead filers kept), and which filers are among the
    largest by revenue that year, as many as the screening's US candidates. The US's lasting gaps are read here: the
    operating-margin table has 3 start years, all 2020-22, and today's listings only."""
    t = pd.read_csv(DATA / "history" / "us_frames.csv.gz", dtype={"cik": str}, usecols=["year", "cik", "revenue", "ni"])
    t = t.assign(code=t["cik"], year=t["year"].astype(str), m=(t["ni"] / t["revenue"].where(t["revenue"] > 0)).clip(-1, 1))
    m = wide(t, "m")
    return m, wide(t, "revenue").reindex(columns=m.columns).rank(ascending=False) <= CONFIG["universe"]["us_candidates"]


def lasting_panel(market: str) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    return frames_margins() if market == "us" else (margin_table(market), None)


@lru_cache(maxsize=3)
def lasting_keep(market: str) -> dict:
    """The share kept each year of a margin gap that has lasted 3 years, above and below apart: the annual rate that
    fits the median share kept at each horizon with 3 start years and 30 gaps (through the origin in logs, so the long
    horizons a 10-year forecast depends on weigh most). The gap is to the 8-year median ending with the year, the
    forecast's own anchor; where that leaves under 3 horizons (HK's tables start in 2015), to the 5 years' median
    before. Stage 14's rate where a lasting gap keeps no more (LASTING_SIDES)."""
    out, (m, among) = dict(margin_keep(market)), lasting_panel(market)
    for side in LASTING_SIDES[market]:
        for window, current in ((8, True), (5, False)):
            fit = []
            for h in range(1, LASTING_HORIZON + 1):
                d = gap_spells(margin_gaps(m, window, current, h, side, among=among), side)[0]
                if len(d) >= 30 and d["start"].nunique() >= 3:
                    fit.append((h, float(np.log(np.clip((d["later"] / d["gap"]).median(), 0.01, 1.0)))))
            if len(fit) >= 3:
                out[side] = float(np.exp(sum(h * x for h, x in fit) / sum(h * h for h, _ in fit)))
                break
    return out


@lru_cache(maxsize=6)
def growth_shares(market: str, past: int = 1) -> list[float]:
    """The share of the past `past` years' excess revenue growth (over the size fifth's median) kept in each of the
    next 5 years, non-increasing."""
    return pav([b for b, _ in growth_profile(market, past).values()])


def excess_kept(t: pd.DataFrame, hurdle: float, h: int, edge_min: float = 0.02) -> tuple[float, int]:
    """Of company-years whose return beat `hurdle` in each of the last 5 years by a median of `edge_min` or more, the
    median share of that excess kept `h` years on, net of the market's drift (the median company's return h years on
    against its own 5-year median: CN returns fell through the period)."""
    cols, kept = list(t.columns), []
    for i in range(4, len(cols) - h):
        last = t[cols[i - 4:i + 1]]
        ok = last.notna().all(axis=1) & t[cols[i + h]].notna()
        med, later = last[ok].median(axis=1), t.loc[ok, cols[i + h]]
        drift = (later - med).median()
        sel = (last[ok] > hurdle).all(axis=1) & (med - hurdle >= edge_min)
        kept.append((later[sel] - hurdle - drift) / (med[sel] - hurdle))
    k = pd.concat(kept) if kept else pd.Series(dtype=float)
    return (float(k.median()) if len(k) else float("nan")), len(k)


EXCESS_YEARS = 5


@lru_cache(maxsize=3)
def excess_keep(market: str) -> float:
    """The share of a sustained excess return kept each year: the median share kept 5 years on (excess_kept), as an
    annual rate (the fade of CFROI towards the market's in Credit Suisse HOLT's model, measured here)."""
    kept, _ = excess_kept(return_table(market), hurdle(market), EXCESS_YEARS)
    return float(min(max(kept, 0.0), 1.0) ** (1 / EXCESS_YEARS))


def base_rates(market: str, revenue_now: float, rates: dict[str, float | None], years: int = 5) -> dict:
    """Mauboussin and Callahan's base rates: of the companies in the same fifth by revenue (its rank in each start
    year), how many grew revenue at least as fast over `years`; the median company's growth (the market's norm); and
    the same fifth's median in the latest complete window (today's conditions: the DCF's growth beyond the consensus)."""
    p = revenue_table(market)
    cols, rows = sorted(p.columns), []
    for a, b in zip(cols, cols[years:]):
        start, end = p[a], p[b]
        ok = (start > 0) & (end > 0)
        rows.append(pd.DataFrame({"g": (end[ok] / start[ok]) ** (1 / years) - 1, "end": b,
                                  "fifth": (start.rank(pct=True)[ok] * 5).clip(upper=4.999).astype(int)}))
    if not rows:
        return {}
    d, latest = pd.concat(rows), p[cols[-2]].dropna()  # the last full year's cross-section (the newest may be partial)
    fifth = min(int((latest < revenue_now).mean() * 5), 4)
    same, now = d[d["fifth"] == fifth]["g"], d[(d["fifth"] == fifth) & (d["end"] == cols[-2])]["g"]  # cols[-1] may be partial
    return {"years": f"{cols[0]}-{cols[-1]}", "fifth": fifth + 1, "count": len(same), "median": float(same.median()),
            "fifth_recent": float(now.median()) if len(now) else None, "recent_window": f"{int(cols[-2]) - years}-{cols[-2]}",
            "fifth_recent_quartiles": [float(now.quantile(0.25)), float(now.quantile(0.75))] if len(now) else None,  # the
            # scenarios' growth (stage 18: Morningstar's bear and bull are the 25th and 75th percentile outcomes)
            "market_median": float(d["g"].median()), "recent_median": float(rows[-1]["g"].median()),
            "share_at_least": {name: float((same >= x).mean()) if x is not None else None for name, x in rates.items()}}
