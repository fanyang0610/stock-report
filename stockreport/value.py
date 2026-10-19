"""Fair value per stock from what its peer group pays, through two lenses, with a residual-income
cross-check (PLAN.md Method sections 2 and 4). Multiples are fitted in logs, so residuals are relative.

- Trailing lens: today's book and earnings power (P/B on ROE and growth; P/S for loss-makers;
  P/B on ROE for banks, insurers and brokers). A stock neither lens can value because an input is
  missing gets a simpler peer multiple (FALLBACKS), marked 低信心 in pick.py.
- Forward lens: what peers pay for expected growth, on analyst consensus EPS (no target prices), for
  financials too: it tempers a one-year ROE spike such as insurers' investment gains. It values a
  stock alone when the trailing lens can't (negative book value)."""

import numpy as np
import pandas as pd

from stockreport.config import CONFIG

POOL = {True: "金融(合并)", False: "全市场(合并)"}


def peer_groups(df: pd.DataFrame, min_size: int) -> pd.Series:
    """Industry; groups smaller than min_size are compared market-wide (financials among financials)."""
    size = df.groupby("industry")["industry"].transform("size")
    return df["industry"].where(size >= min_size, df["financial"].map(POOL))


def fit(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """OLS of y on [1, x]; returns coefficients."""
    a = np.column_stack([np.ones(len(y)), x])
    return np.linalg.lstsq(a, y, rcond=None)[0]


def predict(coef: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), x]) @ coef


def residual_income(bps, roe, r, retention, years: int):
    """Book value plus discounted excess returns, with ROE fading linearly to r over `years`."""
    bps, roe, retention = (np.asarray(v, dtype=float) for v in (bps, roe, retention))
    value, book = bps.copy(), bps.copy()
    for t in range(1, years + 1):
        roe_t = roe + (r - roe) * (t - 1) / years
        value += (roe_t - r) * book / (1 + r) ** t
        book = book * (1 + roe_t * retention)
    return value


def disagree(a: pd.Series, b: pd.Series, price: pd.Series, max_gap: float) -> pd.Series:
    """Two values that point opposite ways versus the price and are more than max_gap apart."""
    return (np.sign(a / price - 1) != np.sign(b / price - 1)) & ((a / b - 1).abs() > max_gap)


def fit_lens(df: pd.DataFrame, multiple: str, xs: list[str], base: str,
             fit_on: pd.Series, applies: pd.Series, min_size: int) -> pd.DataFrame:
    """Fit log(multiple) on xs within each peer group (pooled when too small) and value the `applies`
    stocks: mid = fitted multiple x own per-share base; band = 25th/75th pct of the fit's residuals."""
    out = pd.DataFrame(np.nan, index=df.index, columns=["mid", "band_lo", "band_hi", "fit_n", "peers_lo", "peers_hi"])
    out["fit_group"] = None
    usable = fit_on & (df[multiple] > 0) & df[xs].notna().all(axis=1)
    for group, members in df[applies].groupby("peer_group"):
        fin = bool(members["financial"].iloc[0])
        sample, fit_group = usable & (df["peer_group"] == group), group
        if sample.sum() < min_size or group in POOL.values():
            sample, fit_group = usable & (df["financial"] == fin), POOL[fin]
        if sample.sum() < min_size:
            continue
        y, x = np.log(df.loc[sample, multiple]), df.loc[sample, xs].to_numpy()
        coef = fit(y, x)
        q5, q25, q75, q95 = np.quantile(y - predict(coef, x), [0.05, 0.25, 0.75, 0.95])
        target = members.index[members[xs].notna().all(axis=1)]
        out.loc[target, "mid"] = np.exp(predict(coef, df.loc[target, xs].to_numpy())) * df.loc[target, base]
        out.loc[target, ["band_lo", "band_hi", "fit_n", "peers_lo", "peers_hi"]] = [
            np.exp(q25), np.exp(q75), int(sample.sum()), np.exp(q5), np.exp(q95)]
        out.loc[target, "fit_group"] = fit_group
    return out


# trailing lens: method -> (multiple, regressors, per-share base, stocks the fit is estimated on, stocks it values)
# Profitable non-financials use P/B on ROE and growth, not P/E: in A-shares a P/E fit gets a negative
# ROE coefficient (depressed earnings inflate P/E), which made cheap low-ROE stocks look undervalued.
# Financials have no absolute anchor (the justified P/B was dropped in the Phase 5 review): with one
# market-wide r it turned whole-sector discounts into upside, e.g. Chinese insurers at +200-300%.
METHODS = {
    "P/B on ROE": ("pb", ["roe"], "bps", lambda d: d["financial"] & (d["np_ttm"] > 0),
                   lambda d: d["financial"] & (d["np_ttm"] > 0)),
    "P/B": ("pb", ["roe", "growth"], "bps", lambda d: ~d["financial"] & (d["np_ttm"] > 0),
            lambda d: ~d["financial"] & (d["np_ttm"] > 0)),
    "P/S": ("ps", ["gross_margin", "growth"], "sps_ttm", lambda d: ~d["financial"],
            lambda d: ~d["financial"] & (d["np_ttm"] <= 0)),
}

# A missing input drops the regressor, not the stock: loss-makers with no gross profit line (biotech, telecom
# equipment, media, exchanges) on P/S and growth; profitable companies with negative book value (buybacks, REITs)
# and too few analysts for the forward lens on P/E and growth. Only stocks neither lens values; 低信心 (simple_lens).
# A stock priced outside its peers' spread around the fit (5th-95th percentile) is priced on something else, e.g.
# pre-revenue Roivant at ~1,000x sales or 碧桂园's restructuring gain: no value rather than a meaningless one.
FALLBACKS = {
    "P/S on growth": ("ps", ["growth"], "sps_ttm", lambda d: ~d["financial"], lambda d: ~d["financial"] & (d["np_ttm"] <= 0)),
    "P/E on growth": ("pe", ["growth"], "eps_ttm", lambda d: ~d["financial"] & (d["np_ttm"] > 0),
                      lambda d: ~d["financial"] & (d["np_ttm"] > 0)),
}


def value(df: pd.DataFrame, r: float) -> pd.DataFrame:
    """Adds peer_group, method, fv_trailing, fv_forward, fv_low/mid/high, upside, ri_value and
    the two 低信心 checks (lenses_agree, cross_check_ok)."""
    cfg, min_size = CONFIG["value"], CONFIG["peers"]["min_group_size"]
    df = df.copy()
    df["growth"] = df[cfg["growth_metric"]]
    df["peer_group"] = peer_groups(df, min_size)
    df["method"], df["fit_group"], df["fit_n"] = None, None, np.nan

    trail = pd.DataFrame(np.nan, index=df.index, columns=["mid", "band_lo", "band_hi"])
    for method, (multiple, xs, base, fit_on, applies) in METHODS.items():
        lens = fit_lens(df, multiple, xs, base, fit_on(df), applies(df), min_size)
        rows = lens["mid"].notna()
        trail.loc[rows] = lens.loc[rows, ["mid", "band_lo", "band_hi"]].to_numpy()
        df.loc[rows, "method"] = method
        df.loc[rows, ["fit_group", "fit_n"]] = lens.loc[rows, ["fit_group", "fit_n"]].to_numpy()

    has_forecast = (df["analysts"] >= cfg["forward_min_analysts"]) & (df["eps_e2"] > 0) & df["fwd_growth"].notna()
    fwd = fit_lens(df, "fwd_pe", ["fwd_growth"], "eps_e2", has_forecast, has_forecast, min_size)
    for method, (multiple, xs, base, fit_on, applies) in FALLBACKS.items():
        lens = fit_lens(df, multiple, xs, base, fit_on(df), applies(df) & trail["mid"].isna() & fwd["mid"].isna(), min_size)
        rows = lens["mid"].notna() & (df["price"] / lens["mid"]).between(lens["peers_lo"], lens["peers_hi"])
        trail.loc[rows] = lens.loc[rows, ["mid", "band_lo", "band_hi"]].to_numpy()
        df.loc[rows, "method"] = method
        df.loc[rows, ["fit_group", "fit_n"]] = lens.loc[rows, ["fit_group", "fit_n"]].to_numpy()
    df["simple_lens"] = df["method"].isin(list(FALLBACKS))

    w, gap = cfg["forward_weight"], cfg["cross_check_max_gap"]
    t, f = trail["mid"].astype(float), fwd["mid"].astype(float)
    both = t.notna() & f.notna()
    t_lo, t_hi = t * trail["band_lo"], t * trail["band_hi"]
    blend_lo = (1 - w) * t_lo + w * f * fwd["band_lo"]
    blend_hi = (1 - w) * t_hi + w * f * fwd["band_hi"]
    df["fv_trailing"], df["fv_forward"] = t, f
    df["fv_mid"] = t.where(~both, (1 - w) * t + w * f)
    df["fv_low"] = t_lo.where(~both, np.minimum(blend_lo, np.minimum(t, f)))  # range covers both lenses
    df["fv_high"] = t_hi.where(~both, np.maximum(blend_hi, np.maximum(t, f)))
    alone = t.isna() & f.notna()  # no trailing lens, e.g. negative book value: the forward lens alone
    df.loc[alone, ["fv_mid", "fv_low", "fv_high"]] = np.column_stack(
        [f[alone], f[alone] * fwd.loc[alone, "band_lo"], f[alone] * fwd.loc[alone, "band_hi"]])
    df.loc[alone, ["method", "fit_group", "fit_n"]] = np.column_stack(
        [np.full(alone.sum(), "fwd P/E"), fwd.loc[alone, "fit_group"], fwd.loc[alone, "fit_n"]])
    df["upside"] = df["fv_mid"] / df["price"] - 1
    df["lenses_agree"] = ~(both & disagree(t, f, df["price"], gap))

    df["ri_value"] = residual_income(df["bps"], df["roe"], r, df["retention"], cfg["ri_fade_years"])
    df["ri_gap"] = df["fv_mid"] / df["ri_value"] - 1
    df["cross_check_ok"] = ~disagree(df["fv_mid"], df["ri_value"], df["price"], gap)
    return df
