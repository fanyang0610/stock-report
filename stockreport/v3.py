"""Valuation v3, the Phase 13 redesign (PLAN.md Method 16): what the company's own future earnings are worth,
with the assumptions written out, and what the price expects. Per share, in the quote currency.

- Earnings path: years 1-3 from analysts' EPS (3+ analysts), else the company's own trend (also the backtest
  version). Then profit grows at the same rate g with ROE held for a duration D, then growth and ROE fade to the
  market's long-run levels over a fixed number of years (config fade_years), the same for every company.
- D comes from the base rates (baserates.py): the share of similar companies whose profit kept up g for D
  years. The fair value range is the value at the 25th / 50th / 75th percentile of that distribution, upside the
  50th over the price. The duration the price needs is solved for and placed in the distribution: past the 90th
  percentile 价格隐含过高, under the 10th 价格隐含过低.
- Residual income on book. Book-light companies (negative book without a loss in 5 years, i.e. after buybacks,
  or a 5-year ROE above 40%) are valued on their
  earnings path instead (the value-driver formula: earnings less the reinvestment growth needs, here at a 40%
  return on reinvested capital), written as residual income on the capital that earns 40% (earnings ÷ 40%):
  the value is continuous at the threshold and their excess returns fade like every company's. (Keeping today's
  earnings forever, the formula's usual form, put US book-light stocks at a median +65% against −11% for the
  rest on 2026-10-19, NVIDIA at +331%.)
- Loss-makers get a value only when 3+ analysts expect a profit within 3 years. The discount rate: the market's,
  the median rate at which well-covered stocks' values equal their prices, plus λ × the industry's premium (the
  industry's median implied rate over the market's; config industry_lambda, 0 = one rate per market)."""

import numpy as np
import pandas as pd

from stockreport import baserates as br
from stockreport.config import CONFIG

CFG = CONFIG["v3"]
G_LONG = CFG["long_growth"]
FADE = CFG["fade_years"]
HAIRCUT = CFG["haircut"]
LONG_ROE = CFG["long_roe"]  # per market: "market" (the largest third's median ROE) or "r" (no long-run excess)
LAMBDA = CFG["industry_lambda"]  # per market: share of an industry's implied premium accepted as its risk
COUNTRY_LAMBDA = CFG["country_lambda"]  # US: share of a foreign listing's country premium accepted as its risk
MIN_SPREAD = 0.015  # discount rate at least long-run growth + this
R_RANGE = (0.0, 0.40)
QUANTILES = (0.25, 0.5, 0.75)
LABEL_HIGH, LABEL_LOW = 0.9, 0.1


def per_market(value, market: str):
    return value[market] if isinstance(value, dict) else value  # the backtest sets one value for every market


def inputs(df: pd.DataFrame, h: pd.DataFrame, market: str) -> pd.DataFrame:
    """Per stock: core EPS e0 and book b0 (CN 扣非 EPS updated by a newer 业绩预告; US net of preferred), analysts'
    EPS e1-e3 (HK year 3 = year 2 × (1 + expected growth ≤ 15%)), explicit years t0 (3 with consensus, else 0),
    the growth rate g held during the duration, today's and the 5-year ROE, book-light and its RONIC, and
    whether the stock can be valued at all (a profit today, or analysts expecting one within 3 years)."""
    x = pd.DataFrame(index=df.index)
    col = lambda c, default=np.nan: df[c] if c in df else pd.Series(default, df.index)
    if market == "cn":
        x["e0"] = h["pre_eps_ttm"].fillna(df["eps_deduct_ttm"]).fillna(df["eps_ttm"]) if "pre_eps_ttm" in h else \
            df["eps_deduct_ttm"].fillna(df["eps_ttm"])
    else:
        x["e0"] = df["eps_ttm"] * (1 - h.get("pref_div_share", pd.Series(0.0, df.index)).fillna(0))
    x["b0"] = df["bps"] * (1 - h.get("pref_share", pd.Series(0.0, df.index)).fillna(0))
    e3 = col("eps_e3") if market != "hk" else col("eps_e2") * (1 + col("fwd_growth").clip(0, 0.15))
    x["e1"], x["e2"], x["e3"] = col("eps_e1"), col("eps_e2"), e3
    cons = (col("analysts", 0).fillna(0) >= 3) & x[["e1", "e2", "e3"]].notna().all(axis=1) & (x["e3"] > 0)
    x["t0"] = np.where(cons, 3, 0)
    lo, hi = CFG["growth"]
    g_cons = np.where((x["e1"] > 0) & (x["e3"] > 0), np.sqrt(x["e3"] / x["e1"].where(x["e1"] > 0)) - 1,
                      np.where(x["e2"] > 0, x["e3"] / x["e2"].where(x["e2"] > 0) - 1, hi))
    trend = h["rev_cagr_5y"].where(h["n_years"] >= 5) if "rev_cagr_5y" in h else pd.Series(np.nan, df.index)
    g_own = trend.fillna(0.5 * df["rev_growth"] + 0.5 * per_market(G_LONG, market))
    x["g"] = np.clip(np.where(cons, g_cons, g_own), lo, hi)
    x["roe0"] = (x["e0"] / x["b0"]).where(x["b0"] > 0)
    x["roe5"] = h["roe_5y"] if "roe_5y" in h else np.nan
    # negative book after buybacks counts as book-light; after recent losses (碧桂园) it is distress: no value
    losses = h["loss_5y"] if "loss_5y" in h else h.get("loss_years", pd.Series(0, df.index))
    x["light"] = ((x["b0"] <= 0) & ~(losses.reindex(df.index).fillna(0) > 0)) | (x["roe5"].fillna(x["roe0"]) > CFG["book_light_roe"])
    first = x[["e0", "e1", "e2", "e3"]].where(x[["e0", "e1", "e2", "e3"]] > 0).bfill(axis=1).iloc[:, 0]
    x["book"] = x["b0"].where(~x["light"], np.maximum(x["b0"].fillna(0), first / CFG["book_light_roe"]))
    x["ok"] = ((x["e0"] > 0) | cons) & (x["book"] > 0)
    x["n_years"] = h["n_years"] if "n_years" in h else np.nan
    return x


def paths(x: pd.DataFrame, path: np.ndarray, r, D: np.ndarray, roe_long: float, g_long: float, fade: int) -> np.ndarray:
    """Value per share for growth durations D (stocks × options: years from today the company keeps up its
    growth rate g and its ROE) at discount rate r (scalar or per stock): book + discounted residual income
    (E − r·B). While growing: analysts' EPS for years 1-3 (up to D), then ROE held and book growing at g (at most
    at ROE: no new equity). After D: ROE follows its base-rate cell's path from where it stood (`path`: A and B
    per year, ROE ≈ A + B × ROE at the start) for H years, then fades linearly to roe_long over `fade` years;
    growth fades linearly to g_long over `fade` years; then the long-run residual income (roe_long − r)·B
    grows at g_long forever. Book is the capital that earns 40% for book-light companies (inputs)."""
    n, k = D.shape
    col = lambda c: x[c].to_numpy(float)[:, None]
    r = np.broadcast_to(np.asarray(r, float).reshape(-1, 1) if np.ndim(r) else np.asarray(r, float), (n, k))
    roe_long = r if np.isnan(roe_long) else roe_long  # NaN: no excess return in the long run (long_roe "r")
    t0, g = col("t0"), col("g")
    explicit = np.minimum(D, t0)  # analysts' years within the duration
    last_year = D + br.H + fade
    cons = np.column_stack([x[c].to_numpy(float) for c in ("e1", "e2", "e3")])
    A, Bk = path[:, 0, :], path[:, 1, :]
    B = np.broadcast_to(col("book"), (n, k)).copy()
    roe_star = np.broadcast_to(col("e0") * np.where(t0 == 0, 1 + g, 1) / col("book"), (n, k)).copy()
    roe_end = np.full((n, k), np.nan)
    V, disc = B.copy(), np.ones((n, k))
    for t in range(1, int(last_year.max()) + 1):
        disc = disc / (1 + r)
        after = t - D  # years since growth ended
        j = np.clip(after, 1, br.H).astype(int) - 1
        based = np.take_along_axis(A, j, axis=1) + np.take_along_axis(Bk, j, axis=1) * roe_star
        roe_end = np.where(after == br.H, based, roe_end)
        roe_t = np.where(after <= 0, roe_star, np.where(after <= br.H, based,
                         roe_end + (roe_long - roe_end) * np.clip(after - br.H, 0, fade) / fade))
        g_t = g + (g_long - g) * np.clip(after, 0, fade) / fade
        E = np.where(t <= explicit, cons[:, [t - 1]] if t <= 3 else np.nan, roe_t * B)
        roe_star = np.where(t <= explicit, E / B, roe_star)
        live = t <= last_year
        V = V + np.where(live, (E - r * B) * disc, 0.0)
        B_next = B * (1 + np.maximum(np.minimum(g_t, E / B), -0.5))
        V = V + np.where(t == last_year, (roe_long - r) * B_next / (r - g_long) * disc, 0.0)
        B = np.where(live, B_next, B)
    return V


def at(V: np.ndarray, d: np.ndarray) -> np.ndarray:
    """Values on the integer duration grid (stocks × 0..DMAX) at fractional durations d (stocks × m)."""
    d = np.clip(d, 0, V.shape[1] - 1)
    lo = np.floor(d).astype(int)
    hi = np.minimum(lo + 1, V.shape[1] - 1)
    rows = np.arange(len(V))[:, None]
    return V[rows, lo] + (V[rows, hi] - V[rows, lo]) * (d - lo)


def quantile_durations(S: np.ndarray, qs=QUANTILES) -> np.ndarray:
    """Durations at which the share still going falls to 1 − q (linear within the year; DMAX when it never does)."""
    out = np.full((len(S), len(qs)), float(S.shape[1] - 1))
    for j, q in enumerate(qs):
        level = 1 - q
        below = S <= level
        k = np.where(below.any(axis=1), below.argmax(axis=1), -1)
        for i in np.flatnonzero(k > 0):
            a, b = S[i, k[i] - 1], S[i, k[i]]
            out[i, j] = k[i] - 1 + (a - level) / (a - b) if a > b else k[i]
        out[k == 0, j] = 0.0
    return out


def implied(V: np.ndarray, price: np.ndarray, Sc: np.ndarray, t0: np.ndarray) -> pd.DataFrame:
    """The duration the price needs (first crossing on the grid from t0), the share of similar companies that
    lasted that long and its percentile. Values usually rise with D; they fall with D when ROE is below the
    long-run level (growth then destroys value), so a long implied D is pessimistic there. Label: the price
    needs more than 90% of similar companies achieved (or more than any duration: side "above") 价格隐含过高;
    less than 10% fell short of (or less than none: side "below") 价格隐含过低."""
    n, m = V.shape
    grid = np.arange(m)
    d_imp, side, rising = np.full(n, np.nan), np.full(n, "", dtype=object), np.ones(n, bool)
    for i in range(n):
        v = V[i, int(t0[i]):]
        if not np.isfinite(v).all() or not np.isfinite(price[i]):
            continue
        rising[i] = v[-1] >= v[0]
        f = (v - price[i]) if rising[i] else (price[i] - v)  # crosses from below zero to above
        if f[0] >= 0:
            d_imp[i], side[i] = t0[i], "below" if rising[i] else "above"
        elif f[-1] < 0:
            d_imp[i], side[i] = grid[-1], "above" if rising[i] else "below"
        else:
            j = int(np.argmax(f >= 0))
            d_imp[i], side[i] = t0[i] + j - 1 + (-f[j - 1]) / (f[j] - f[j - 1]), "inside"
    share = np.array([np.interp(d, grid, Sc[i]) if np.isfinite(d) else np.nan for i, d in enumerate(d_imp)])
    optimism = np.where(rising, 1 - share, share)  # percentile of what the price assumes, high = optimistic
    label = np.select([(side == "above") | ((side == "inside") & (optimism >= LABEL_HIGH)),
                       (side == "below") | ((side == "inside") & (optimism <= LABEL_LOW))], ["价格隐含过高", "价格隐含过低"], "")
    return pd.DataFrame({"d_implied": d_imp, "implied_share": share, "implied_pct": 1 - share, "implied_side": side,
                         "rising": rising, "implied_label": np.where(np.isfinite(d_imp), label, "")})


def market_rate(x: pd.DataFrame, path: np.ndarray, d50: np.ndarray, price: np.ndarray, well: np.ndarray,
                roe_long: float, g_long: float, fade: int) -> tuple[float, np.ndarray, np.ndarray]:
    """Per stock the rate at which its value at the median duration equals its price (bisection; NaN outside
    R_RANGE; for ranking, −inf / +inf beyond its bounds), and the market's rate: the median over well-covered
    stocks."""
    floor = max(R_RANGE[0], g_long + MIN_SPREAD)
    lo_r, hi_r = np.full(len(x), floor), np.full(len(x), R_RANGE[1])
    D = np.column_stack([np.floor(d50), np.ceil(d50)])
    frac = d50 - np.floor(d50)
    value = lambda r: (lambda v: v[:, 0] + (v[:, 1] - v[:, 0]) * frac)(paths(x, path, r, D.astype(int), roe_long, g_long, fade))
    v_lo, v_hi = value(lo_r), value(hi_r)
    inside = (v_lo >= price) & (v_hi <= price)
    for _ in range(40):
        mid = (lo_r + hi_r) / 2
        above = value(mid) > price
        lo_r, hi_r = np.where(above, mid, lo_r), np.where(above, hi_r, mid)
    irr = np.where(inside, (lo_r + hi_r) / 2, np.nan)
    censored = np.where(v_lo < price, -np.inf, np.where(v_hi > price, np.inf, irr))  # beyond the range: still ranked
    pick = well & ~np.isnan(censored)
    # more than half beyond a bound: the bound (the values then sit mostly below or above the prices)
    return float(np.clip(np.median(censored[pick]), floor, R_RANGE[1])), irr, censored


def industry_rates(r_mkt: float, implied: pd.Series, industry: pd.Series, parent: pd.Series, lam: float,
                   floor: float) -> pd.Series:
    """Per stock: the market's rate + λ × its industry's premium, the median implied rate of the industry's
    stocks (5+, else of its parent sector, else none) over the market's, within −3 / +6 points. λ = 0 is one
    rate for every company in the market; λ = 1 takes each industry's pricing as its risk."""
    out = pd.Series(0.0, implied.index)
    for groups in (parent, industry):  # the industry overrides its parent where it has 5+ stocks
        by = implied.dropna().groupby(groups.reindex(implied.dropna().index))
        med = by.median().where(by.count() >= 5).dropna()
        hit = groups.isin(med.index) & (groups != "")
        out[hit] = groups[hit].map(med) - r_mkt
    return (r_mkt + lam * out.clip(-0.03, 0.06)).clip(lower=floor)


def country_premium(implied: pd.Series, country: pd.Series, home: str = "United States") -> pd.Series:
    """US: per foreign listing, its country's median implied rate over home listings' (countries with 5+ listings,
    the rest pooled), within −3 / +6 points; 0 at home. Toyota or Ecopetrol trade at their home market's
    discount, which the US rate would read as upside."""
    c = country.reindex(implied.index).fillna(home)
    ok = implied.notna()
    home_med = implied[ok & (c == home)].median()
    by = implied[ok].groupby(c[ok]).agg(["median", "count"])
    small = by.index[(by["count"] < 5) & (by.index != home)]
    pooled = implied[ok & c.isin(small)].median() - home_med if len(small) else 0.0
    prem = (by["median"] - home_med).where(by["count"] >= 5, pooled)
    return c.map(prem).fillna(pooled).where(c != home, 0.0).clip(-0.03, 0.06)


def value(df: pd.DataFrame, h: pd.DataFrame, st: pd.DataFrame, market: str, sector: pd.Series) -> pd.DataFrame:
    """The v3 columns for one market's snapshot `df`: inputs, base-rate cell and survival, the market's rate,
    the value range, upside and the implied duration with its label."""
    x = inputs(df, h, market)
    g_long, fade, cut = per_market(G_LONG, market), per_market(FADE, market), per_market(HAIRCUT, market)
    roe_long = np.nan if per_market(LONG_ROE, market) == "r" else float(st.attrs["roe_long"])
    want = br.bands(df["rev_growth"], x["roe0"].where(x["b0"] > 0, 1.0),
                    np.searchsorted(st.attrs["size_cuts"], df["revenue_ttm"].fillna(0)))
    want.index = df.index
    want["sector"] = sector.reindex(df.index).fillna("")
    S, path, cells = br.survival(st, want, x["g"], per_market(br.TOL, market))
    x = x.join(cells)
    t0 = x["t0"].to_numpy(int)
    q = quantile_durations(S) * (1 - cut)  # HK: survivors only
    ok, price = x["ok"].to_numpy(bool), df["price"].to_numpy(float)
    well = ok & (x["t0"].to_numpy() == 3) & (x["n_years"].to_numpy() >= 5)
    if well.sum() < 30:  # no consensus (the backtest): stocks with 5+ years of history
        well = ok & (x["n_years"].to_numpy() >= 5)
    sub = x[ok]
    r_mkt, irr, censored = market_rate(sub, path[ok], q[ok, 1], price[ok], well[ok], roe_long, g_long, fade)
    implied_rates = pd.Series(censored, sub.index)
    r = industry_rates(r_mkt, implied_rates, df["industry"].fillna("").reindex(sub.index),
                       want["sector"].reindex(sub.index), per_market(LAMBDA, market), g_long + MIN_SPREAD)
    if market == "us" and COUNTRY_LAMBDA and "country" in df:  # foreign listings: their home market's premium
        r = (r + COUNTRY_LAMBDA * country_premium(implied_rates, df["country"])).clip(lower=g_long + MIN_SPREAD)
    grid = np.full((len(x), br.DMAX + 1), np.nan)
    grid[ok] = paths(sub, path[ok], r.to_numpy(), np.tile(np.arange(br.DMAX + 1), (ok.sum(), 1)), roe_long, g_long, fade)
    vals = at(np.nan_to_num(grid, nan=-1e18), q)
    vals[~ok] = np.nan
    good = ok & (vals[:, 1] > 0)
    out = x.assign(r=r.reindex(df.index), r_mkt=r_mkt, roe_long=r_mkt if np.isnan(roe_long) else roe_long, irr=np.nan,
                   d25=q[:, 0], d50=q[:, 1], d75=q[:, 2], s1=S[:, 1], s3=S[:, 3], s5=S[:, 5], s10=S[:, 10])
    out.loc[ok, "irr"] = irr
    rng = np.sort(np.where(good[:, None], vals, np.nan), axis=1)
    out["v_low"], out["v_mid"], out["v_high"] = rng[:, 0], np.where(good, vals[:, 1], np.nan), rng[:, 2]
    out["upside"] = out["v_mid"] / df["price"] - 1
    out["v_t0"] = np.where(good, grid[:, 0], np.nan)
    imp = implied(np.where(good[:, None], grid, np.nan), price, S, np.zeros(len(x), int))
    imp.index = df.index
    out = out.join(imp)
    out["valued"] = good
    # where no duration explains the price (below a stop to growth, above 30 years, or growth at a low ROE): the
    # constant ROE on book forever that the price implies, and the share of similar companies whose ROE got there
    # (the average of years 3-5); 价格隐含过高/过低 only when under 10% did
    other = good & ((out["implied_side"] != "inside") | ~out["rising"])
    on_book = out["r"] + (df["price"] / x["book"] - 1) * (out["r"] - g_long)  # on the capital earning 40% for book-light
    now = x["roe0"].where(~x["light"], x["roe5"].fillna(x["roe0"]))
    implied_roe = on_book.where(~x["light"], on_book * now / (x["e0"] / x["book"]))  # book-light: on its own book
    out["roe_now"] = now
    out["roe_implied"] = implied_roe.where(other)
    out["roe_reached"] = br.roe_reached(st, x[["level", "key"]], implied_roe.where(other & (x["e0"] > 0) & now.notna()), now)
    rare = other & (out["roe_reached"] < LABEL_LOW)
    out.loc[other & ~rare, "implied_label"] = ""
    out.loc[rare, "implied_label"] = np.where(implied_roe[rare] > now[rare], "价格隐含过高", "价格隐含过低")
    return out


def roe_long(p: pd.DataFrame, today: str, market: str, years: int = 10) -> float:
    """The market's long-run ROE: the median over the last `years` years (public by `today`) of the panel's
    largest third by revenue each year, the companies the universe holds (the whole panel's median is pulled
    down by small filers: US 7.5% against 13.1% for the largest third on 2026-10-19)."""
    q = p[(p["avail"] <= today) & p["roe"].notna() & (p["rev"] > 0)]
    q = q[q["year"] > q["year"].max() - years]
    big = q["rev"] >= q.groupby("year")["rev"].transform(lambda s: s.quantile(2 / 3))
    return float(q.loc[big, "roe"].clip(-1, 1).median())
