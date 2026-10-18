"""Valuation v2 engine (docs/REVIEW.md A2.2): core earnings, the weight on history, normal ROE and
archetype, a three-stage residual-income value, the expected return at today's price (the implied cost
of capital) and the ROE the price implies. Per share, in the quote currency, vectorized over stocks.
The parameters are first guesses that Phase 9 calibrates by backtest."""

import numpy as np
import pandas as pd

from stockreport.config import CONFIG

G_LONG = CONFIG["v2"]["long_growth"]  # long-run nominal growth
FADE_YEARS = 10
HAIRCUT = np.array([0.1, 0.25, 0.5])  # consensus years 1-3 pulled toward the normal path at full history weight
MIN_SPREAD = 0.03  # terminal r − g
LAMBDA = CONFIG["v2"]["lambda"]  # share of an industry's implied premium accepted as its risk
R_RANGE = (-0.05, 0.40)  # expected-return search range; a result on the edge means "beyond"


def earnings(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Earnings base: CN on 扣非 EPS (updated by a newer 业绩预告), US less preferred dividends over book
    net of preferred equity. Current ROE = median of the trailing ROE and consensus years 2 and 3 on
    today's book, robust to one-offs: year 1 mostly overlaps the trailing 12 months, so a one-off in the
    current year would count twice (Gilead's 2026 in-process R&D charge is in both)."""
    d = pd.DataFrame(index=df.index)
    if market == "cn":
        d["eps_core"] = df["pre_eps_ttm"].fillna(df["eps_deduct_ttm"]).fillna(df["eps_ttm"])
    else:
        d["eps_core"] = df["eps_ttm"] * (1 - df.get("pref_div_share", pd.Series(0.0, df.index)).fillna(0))
    d["bps_c"] = df["bps"] * (1 - df.get("pref_share", pd.Series(0.0, df.index)).fillna(0))
    e3 = df["eps_e3"] if market != "hk" else df["eps_e2"] * (1 + df["fwd_growth"].clip(0, 0.15))
    d["e1"], d["e2"], d["e3"] = df["eps_e1"], df["eps_e2"], e3
    d["has_cons"] = (df["analysts"] >= 3) & d[["e1", "e2", "e3"]].notna().all(axis=1)
    book = d["bps_c"].where(d["bps_c"] > 0)
    d["roe_ttm"] = d["eps_core"] / book
    cons_roe = pd.concat([d["roe_ttm"], d["e2"] / book, d["e3"] / book], axis=1).median(axis=1)
    d["roe_cur"] = cons_roe.where(d["has_cons"], d["roe_ttm"]).clip(-0.5, 1.5)
    d["g_cons"] = df["fwd_growth"].where(d["has_cons"])
    d["roe_c3"] = (d["e3"] / (book * (1 + d["g_cons"].clip(0, 0.15)) ** 2)).where(d["has_cons"])
    d["g_exp"] = d["g_cons"].fillna(df["rev_cagr_5y"])
    return d


def normal(d: pd.DataFrame, h: pd.DataFrame, financial: pd.Series, np_ttm: pd.Series) -> pd.DataFrame:
    """History weight w, normal ROE, archetype, persistence φ and starting book growth.
    w = f(ROE volatility relative to its level) × cycle factor (1.0 with 2+ revenue down years or no
    growth expected; 0.3 for a grower with at most one down year and 15%+ expected growth; else 0.6).
    normal = w × history + (1 − w) × today; below its history, ROE reverts up only after past dips, with
    no steady 5-year decline and analysts' year-3 ROE at least halfway back; else today (or consensus)."""
    rh, rc, c3 = h["roe_hist"], d["roe_cur"], d["roe_c3"]
    rel_vol = h["roe_vol"] / rh.abs().clip(lower=0.05)
    w_vol = ((rel_vol - 0.3) / 0.7).clip(0, 1).where(h["loss_years"] < 3, 1.0).where(rh.notna(), 0.0)
    down, g = h["rev_down_years"], d["g_exp"]
    grower = (down <= 1) & (g >= 0.15)
    # A1: fast growers whose early years lost money are valued on today and consensus
    cycle = np.select([(down >= 2) | (g < 0.05), grower & h["early_losses_only"].eq(True), grower], [1.0, 0.0, 0.3], 0.6)
    d["w_hist"] = (w_vol * cycle).fillna(0.0)
    w = d["w_hist"]
    decline = (h["roe_slope"] < -0.015) & (h["roe_r2"] > 0.5)
    dips = (down >= 2) | (h["loss_years"] >= 1)
    up_ok = dips & ~decline & (c3.isna() | (c3 >= rc + 0.5 * (rh - rc)))
    blend = w * rh + (1 - w) * rc
    held = np.where(c3.notna(), np.maximum(rc, np.minimum(c3, rh)), rc)
    below = rc < rh
    d["structural_decline"] = below & ~up_ok
    d["roe_norm"] = pd.Series(np.where(below & ~up_ok, held, blend), d.index).fillna(rc)
    # pre-profit: no profitable history (10-year ROE ≤ 3% or none) and a loss today that analysts don't
    # expect to turn, or losses in half its years and no positive normal ROE (a biotech's licence
    # windfall); value() adds the stocks whose value comes out at zero or below
    loss_now = (np_ttm <= 0) & ~(d["has_cons"] & (d["e2"] > 0))
    mostly_losses = ~(d["roe_norm"] > 0) & (h["loss_years"] >= h["n_years"] / 2)
    preprofit = ~(rh > 0.03) & (loss_now | mostly_losses)
    grower = (g >= 0.15) & (h["rev_cagr_5y"] >= 0.15)
    d["archetype"] = np.select([preprofit, financial, w >= 0.6, grower], ["pre-profit", "financial", "cyclical", "growth"], "steady")
    stability = 1 - rel_vol.clip(0, 1).fillna(0.6)
    margin = (h["gm_hist"].clip(0, 0.6) / 0.6).fillna(0.5)
    d["phi"] = (0.15 + 0.45 * stability + 0.2 * margin).clip(0.1, 0.8)
    g0 = d["g_cons"].fillna(h["rev_cagr_5y"] * 0.5).clip(0, 0.15)
    return d.assign(g0=g0)


def ri(r, d: pd.DataFrame, g_long: float, w=None, nn=None, phi=None) -> np.ndarray:
    """Three-stage residual-income value per share at discount rate r (scalar or per stock).
    Years 1-3: consensus EPS (pulled toward the ROE path from today to normal by w × HAIRCUT), else that
    path. Years 4-13: ROE fades linearly from w × normal + (1 − w) × year 3's to r + φ × (normal − r),
    so a cyclical's peak ends after year 3 (the prototype's rule). Book grows at most at the
    sustainable rate g (consensus growth fading to g_long; the rest is paid out). Terminal: the last
    excess return as a perpetuity growing at g_long, with r − g at least MIN_SPREAD."""
    b0 = d["bps_c"].to_numpy(float)
    r = np.broadcast_to(np.asarray(r, float), b0.shape)
    w = d["w_hist"].to_numpy(float) if w is None else np.broadcast_to(np.asarray(w, float), b0.shape)
    nn = d["roe_norm"].to_numpy(float) if nn is None else np.asarray(nn, float)
    phi = d["phi"].to_numpy(float) if phi is None else np.broadcast_to(np.asarray(phi, float), b0.shape)
    rc, g0, has = d["roe_cur"].to_numpy(float), d["g0"].to_numpy(float), d["has_cons"].to_numpy(bool)
    cons = d[["e1", "e2", "e3"]].to_numpy(float)
    v, b, disc, roe = b0.copy(), b0.copy(), np.ones_like(b0), np.zeros_like(b0)
    for t in range(3):
        path = (rc + (nn - rc) * (t + 1) / 3) * b
        e = np.where(has, (1 - w * HAIRCUT[t]) * cons[:, t] + w * HAIRCUT[t] * path, path)
        disc = disc / (1 + r)
        v = v + (e - r * b) * disc
        roe = e / b
        b = b * (1 + np.minimum(g0, np.maximum(roe, -0.5)))
    long_ = r + phi * (nn - r)
    start = w * nn + (1 - w) * np.clip(roe, -0.5, 1.5)  # a cyclical restarts from its normal ROE in year 4
    for k in range(1, FADE_YEARS + 1):
        roe = start + (long_ - start) * k / FADE_YEARS
        disc = disc / (1 + r)
        v = v + (roe - r) * b * disc
        b = b * (1 + np.minimum(g0 + (g_long - g0) * k / FADE_YEARS, np.maximum(roe, -0.5)))
    return v + (long_ - r) * b / np.maximum(r - g_long, MIN_SPREAD) * disc


def solve(fn, target: np.ndarray, lo: float, hi: float, iters: int = 50) -> np.ndarray:
    """x with fn(x) = target for a decreasing fn, by bisection; the nearer bound when out of range."""
    a, b = np.full(target.shape, lo), np.full(target.shape, hi)
    for _ in range(iters):
        mid = (a + b) / 2
        above = fn(mid) > target
        a, b = np.where(above, mid, a), np.where(above, b, mid)
    return (a + b) / 2


def implied_roe(d: pd.DataFrame, price: np.ndarray, r: np.ndarray) -> np.ndarray:
    """The constant ROE over 10 years (book growing at the sustainable rate, no excess return after)
    that makes the residual-income value equal today's price."""
    b0, g0 = d["bps_c"].to_numpy(float), d["g0"].to_numpy(float)

    def value(x):
        v, b, disc = b0.copy(), b0.copy(), np.ones_like(b0)
        for _ in range(10):
            disc = disc / (1 + r)
            v = v + (x - r) * b * disc
            b = b * (1 + np.minimum(g0, np.maximum(x, -0.5)))
        return v
    return -solve(lambda x: value(-x), price, -3.0, 0.5)  # value rises with x: solve on −x


def required(icc: pd.Series, well: pd.Series, industry: pd.Series, g_long: float) -> tuple[pd.Series, float]:
    """r = the market's implied return (median expected return of well-covered stocks) plus LAMBDA × the
    industry's implied premium (industries with 5+ valued stocks), within −3 / +6 points of the market."""
    inside = icc.between(R_RANGE[0] + 1e-3, R_RANGE[1] - 1e-3)
    r_mkt = float(icc[well & inside].median())
    by = icc[inside].groupby(industry[inside])
    premium = (by.median() - r_mkt).where(by.count() >= 5)
    r = r_mkt + LAMBDA * industry.map(premium).fillna(0.0)
    return r.clip(r_mkt - 0.03, r_mkt + 0.06).clip(lower=g_long + MIN_SPREAD), r_mkt


def value(df: pd.DataFrame, h: pd.DataFrame, market: str) -> pd.DataFrame:
    """The engine for one market: inputs, intrinsic value at the required return, expected return,
    implied ROE. `df` is the v1 snapshot, `h` the history features (history.load)."""
    d = normal(earnings(df.join(h), market), h, df["financial"].astype(bool), df["np_ttm"])
    g_long, price = G_LONG[market], df["price"].to_numpy(float)
    d["valued"] = (d["bps_c"] > 0) & d["roe_norm"].notna() & d["roe_cur"].notna() & (d["archetype"] != "pre-profit")
    ok = d["valued"].to_numpy()
    icc = solve(lambda r: ri(r, d, g_long), price, *R_RANGE)
    d["icc"] = np.where(ok, icc, np.nan)
    well = d["has_cons"] & (h["n_years"] >= 5)
    d["r_req"], r_mkt = required(d["icc"], well, df["industry"], g_long)
    d["r_mkt"] = r_mkt
    d["v_intrinsic"] = np.where(ok, ri(d["r_req"].to_numpy(), d, g_long), np.nan)
    # no positive value: without a positive normal ROE there is no sustainable profit (pre-profit); with
    # one, a return far below r on a growing book (a weak bank) simply has no value the model can state
    worthless = d["valued"] & ~(d["v_intrinsic"] > 0)
    d.loc[worthless & ~(d["roe_norm"] > 0), "archetype"] = "pre-profit"
    d.loc[worthless, "valued"] = False
    d.loc[worthless, ["v_intrinsic", "icc"]] = np.nan
    d["roe_implied"] = np.where(ok, implied_roe(d, price, d["r_req"].to_numpy()), np.nan)
    return d
