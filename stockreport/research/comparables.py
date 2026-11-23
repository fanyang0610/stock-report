"""Stage 25: growth companies valued over the revenue paths comparable companies actually took (PLAN.md "Valuation and
target price"; docs/reviews/REVIEW-2026-11-23.md, F3). Value is convex in growth, so a DCF on the median path sits below
the average over the paths that can happen (Damodaran, "Valuing Young, Start-up and Growth Companies", 2009: simulate
over the inputs' distributions and weigh failure in; Mauboussin and Callahan, "The Base Rate Book", 2016: sales growth
by starting size).
- The paths: every company-year in the market's history tables with 3 years behind it and 10 ahead (HK's tables start
  in 2015: one cohort, 7 years ahead), its own year-by-year revenue growth; no fitted distribution. US: SEC's frames,
  which keep dead filers; CN and HK: today's listings, so survivors only until stage 27.
- Comparable: the same size fifth and recent-growth band at the start. Each company counts once, however many start
  years it qualifies in.
- Today's nominal terms: each year's growth is restated by today's base rate over its cohort's median that year, so the
  2010s' faster nominal growth isn't carried into a rate set on today's yields (the rule value.paths' base rate follows).
- Failure: a company that stopped reporting after its revenue fell below half its peak in the window. It takes
  Damodaran's distress sale value ("Valuing Distressed and Declining Companies", 2009: firm value = going concern x (1 -
  P) + distress sale x P, proceeds a percent of book assets, cash added). One that stopped with its revenue intact was
  most likely bought: its outcome is unknown and it is left out."""

from functools import lru_cache

import numpy as np
import pandas as pd

from stockreport.config import DATA
from stockreport.research import dcf, fade, value

TYPES = {"fast_grower", "loss_making"}  # the types valued as the mean over the paths
PAST = 3  # the recent-growth window, as the fast-grower test's
BANDS = [-np.inf, 0.0, 0.20, 0.50, np.inf]  # falling; ordinary; Lynch's fast growers from 20%; the review's 50%+
BAND_NAMES = ["营收下降", "年增 0-20%", "年增 20-50%", "年增 50% 以上"]
MIN_FIRMS = 30  # below this a group's mean rests on a handful of outliers: the adjacent size fifths, then every size
FAULT = 20.0  # one year's revenue 20 times the last (or a twentieth): a unit error or a reverse merger, not a growth path
FALLEN = 0.5  # stopped reporting at under half its peak revenue: failed (else most likely acquired)
DISTRESS = 0.25  # the sale's proceeds as a share of book operating assets: Damodaran's worked assumption (2009, p. 35)


def panel(market: str) -> pd.DataFrame:
    """Revenue per company and fiscal year: complete years only. The US from SEC's frames (2009 on, dead filers kept)."""
    if market != "us":
        return fade.complete(fade.revenue_table(market))
    t = pd.read_csv(DATA / "history" / "us_frames.csv.gz", dtype={"cik": str}, usecols=["year", "cik", "revenue"])
    p = t.drop_duplicates(["cik", "year"], keep="last").pivot(index="cik", columns="year", values="revenue").sort_index(axis=1)
    p.columns = [str(c) for c in p.columns]
    return fade.complete(p)


def fifths(s: pd.Series) -> pd.Series:
    return (s.rank(pct=True) * 5).clip(upper=4.999).astype(int)


def today_rates(p: pd.DataFrame) -> dict[int, float]:
    """Each size fifth's median 5-year revenue growth in the latest window: today's nominal terms."""
    a, b = p[p.columns[-6]], p[p.columns[-1]]
    ok = (a > 0) & (b > 0)
    g = (b[ok] / a[ok]) ** (1 / 5) - 1
    return g.groupby(fifths(a[ok])).median().to_dict()


@lru_cache(maxsize=3)
def windows(market: str) -> dict:
    """Every usable window: its growth by year (today's nominal terms; NaN past its data), whether it failed, the
    company, its size fifth and its growth band at the start."""
    p = panel(market)
    cols, base = list(p.columns), today_rates(p)
    h = min(dcf.YEARS, len(cols) - 1 - PAST)
    out = {"growth": [], "failed": [], "code": [], "fifth": [], "band": []}
    for i in range(PAST, len(cols) - h):
        s0, s = p[cols[i - PAST]], p[cols[i]]
        ok = (s0 > 0) & (s > 0)
        fifth = fifths(s[ok])
        band = np.digitize(((s[ok] / s0[ok]) ** (1 / PAST) - 1).to_numpy(), BANDS) - 1
        span = p.loc[fifth.index, cols[i - PAST:i + h + 1]].where(lambda d: d > 0).to_numpy()  # with the years its band reads
        r = span[:, PAST:]
        ratio, every = r[:, 1:] / r[:, :-1], span[:, 1:] / span[:, :-1]
        seen = ~np.isnan(r[:, 1:])
        ended = ~seen.all(axis=1)
        gap = (np.diff(seen.astype(int), axis=1) > 0).any(axis=1)  # a hole, then figures again
        fault = np.nanmax(np.maximum(every, 1 / every), axis=1, initial=1.0) >= FAULT
        last = np.array([x[~np.isnan(x)][-1] for x in r])
        failed = ended & (last < FALLEN * np.nanmax(r, axis=1))
        keep = ~gap & ~fault & (~ended | failed)  # stopped with its revenue intact: most likely bought, outcome unknown
        cohort = np.array([[np.nanmedian(ratio[(fifth.to_numpy() == f), t]) for t in range(h)] for f in range(5)])
        today = np.array([1 + base.get(f, 0.0) for f in range(5)])
        scaled = ratio * (today[fifth.to_numpy()][:, None] / cohort[fifth.to_numpy()]) - 1
        pad = np.full((len(scaled), dcf.YEARS - h), np.nan)
        out["growth"].append(np.hstack([scaled, pad])[keep])
        out["failed"].append(failed[keep])
        out["code"].append(fifth.index.to_numpy()[keep])
        out["fifth"].append(fifth.to_numpy()[keep])
        out["band"].append(band[keep])
    return {k: np.concatenate(v) for k, v in out.items()} | {"years": h, "latest": p[cols[-1]].dropna().to_numpy(),
                                                              "cohorts": len(cols) - h - PAST}


def group(market: str, revenue_now: float | None, growth_3y: float | None) -> dict | None:
    """The comparable windows: same size fifth and growth band, widened to the adjacent fifths, then every size, until
    MIN_FIRMS companies; None when even that is too few or the revenue isn't known. Each company's windows share one
    weight."""
    if not revenue_now or revenue_now <= 0:
        return None
    w = windows(market)
    fifth = min(int((w["latest"] < revenue_now).mean() * 5), 4)
    band = None if growth_3y is None else int(np.digitize(growth_3y, BANDS) - 1)
    in_band = np.ones(len(w["band"]), bool) if band is None else w["band"] == band
    for near in (0, 1, 4):
        sel = in_band & (np.abs(w["fifth"] - fifth) <= near)
        codes, counts = np.unique(w["code"][sel], return_counts=True)
        if len(codes) >= MIN_FIRMS:
            n = dict(zip(codes, counts))
            weight = np.array([1 / n[c] for c in w["code"][sel]])
            failed = w["failed"][sel]
            return {"growth": w["growth"][sel], "failed": failed, "weight": weight / weight.sum(), "firms": len(codes),
                    "windows": int(sel.sum()), "fifth": fifth + 1, "band": BAND_NAMES[band] if band is not None else "不分增长",
                    "near": near, "years": w["years"], "cohorts": w["cohorts"],
                    "failed_share": float((weight * failed).sum() / weight.sum())}
    return None


def filled(row: np.ndarray, base: list[float], fixed: int) -> list[float]:
    """A window's growth on the company's path: its own first `fixed` years (the consensus's), then the window's, then
    the company's own fade past the window's data."""
    return [base[t] if t < fixed or np.isnan(row[t]) else float(row[t]) for t in range(dcf.YEARS)]


def distress(f: dict, k: dict) -> float:
    """The value per share if the company fails: DISTRESS of its book operating assets, its cash and stakes added and
    the claims ahead of common holders taken off, at least 0."""
    proceeds = DISTRESS * max(value.capital_now(f, k), 0.0)
    return max(dcf.equity_value(proceeds, k["debt"], k["minority"], k["cash"], k["nonop"], pref=k["pref"]), 0.0) / k["shares"] / k["fx"]


def spread(f: dict, k: dict, path: dict, s2c: float, ronic: list[float], g: float, c: dict, margin_step: float = 0.0,
           cost_shift: float = 0.0) -> dict:
    """The DCF over the comparable paths: the weighted mean (the fair value today) and quartiles (the bear and bull:
    Morningstar's are the outcomes with a 25% chance of worse and of better). Each path is valued at the company's own
    margins and capital (value.paths), its long-run margin at its source's 25th, 50th and 75th percentile, a third each
    (`margin_step`, the half-range: Damodaran's simulation draws growth and margin, and revenue paths alone would call a
    biotech's value certain). A failed window takes the distress value."""
    fixed, floor = path.get("fixed_years", 0), distress(f, k)
    shifts = (-margin_step, 0.0, margin_step) if margin_step else (0.0,)
    def worth(row, shift):
        margin = [x + shift * min(i + 1, value.CONVERGENCE) / value.CONVERGENCE for i, x in enumerate(path["margin"])]
        return max(value.dcf_value(f, k, path | {"growth": filled(row, path["growth"], fixed), "margin": margin}, s2c, ronic, cost_shift, g)[0], 0.0)
    x = np.array([[floor if bad else worth(row, m) for row, bad in zip(c["growth"], c["failed"])] for m in shifts]).ravel()
    w = np.tile(c["weight"] / len(shifts), len(shifts))
    q = lambda p: float(np.quantile(x, p, weights=w, method="inverted_cdf"))
    return {"mean": float(x @ w), "p25": q(0.25), "median": q(0.5), "p75": q(0.75), "distress": floor, "margin_step": margin_step,
            **{key: c[key] for key in ("firms", "windows", "fifth", "band", "near", "years", "cohorts", "failed_share")}}


def multiples(c: dict, base: list[float]) -> np.ndarray:
    """Each window's revenue in year 10 over its start (a failed one's counts as 0; past the window's data, the
    company's own fade)."""
    grown = np.prod([1 + np.array([filled(r, base, 0)[t] for r in c["growth"]]) for t in range(dcf.YEARS)], axis=0)
    return np.where(c["failed"], 0.0, grown)


def needs(f: dict, k: dict, d: dict, price: float, c: dict | None) -> list[dict]:
    """What today's price needs, in business terms: for a long-run margin (the forecast's, 1.5 times and twice it) the
    revenue in year 10 as a multiple of today's, and the share of comparable companies that got there. It solves when
    new capital earns more than it costs; otherwise more revenue adds no value and the row has no multiple."""
    path, base = d["path"], d["path"]["growth"]
    r0 = path.get("revenue0") or f["valuation"]["ttm"]["revenue"]
    fixed = path.get("fixed_years", 0)
    m10, out = path["margin"][-1], []
    if m10 <= 0:
        return out
    grown = multiples(c, base) if c else None
    for m in (m10, m10 * 1.5, m10 * 2):
        if m > 0.8:
            break
        margin = [x + (m - m10) * min(i + 1, value.CONVERGENCE) / value.CONVERGENCE for i, x in enumerate(path["margin"])]
        start = float(np.prod([1 + x for x in base[:fixed]]))
        def at(mult: float) -> float:
            g = (mult / start) ** (1 / (dcf.YEARS - fixed)) - 1
            return value.dcf_value(f, k, path | {"growth": base[:fixed] + [g] * (dcf.YEARS - fixed), "margin": margin},
                                   d["sales_to_capital"], d["moat"]["ronic"], g_term=d["g"])[0]
        need = dcf.solve(at, price, 0.05, 3000.0, tol=1e-4)
        share = None if need is None or grown is None else float(c["weight"] @ (grown >= need))
        out.append({"margin": float(m), "multiple": need, "revenue": None if need is None else need * r0, "share": share})
    return out
