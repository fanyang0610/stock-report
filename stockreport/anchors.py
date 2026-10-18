"""Valuation v2 anchors, combination, quality screen and confidence (docs/REVIEW.md A2.2 items 6-8):
the intrinsic value is combined in logs with a repaired peer value and the stock's own-history P/B,
with weights by archetype; how far apart they are, with data depth, coverage and the quality screen,
sets the confidence (高 / 中 / 低). First-guess weights and points, for Phase 9 to calibrate."""

import numpy as np
import pandas as pd

MIN_GROUP, SHRINK = 15, 10  # peer fits need 15 members; a smaller group keeps n/(n+10) of its own level
WEIGHTS = {"steady": [0.6, 0.3, 0.1], "cyclical": [0.5, 0.1, 0.4], "financial": [0.55, 0.3, 0.15]}  # intrinsic/peer/own


def fit(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """OLS of y on [1, x], dropping a regressor whose slope comes out negative (higher ROE or growth never
    earns a lower multiple: B1 found wrong-signed fits in HK 建筑 and US telecom equipment)."""
    keep = list(range(x.shape[1]))
    while True:
        coef = np.linalg.lstsq(np.column_stack([np.ones(len(y)), x[:, keep]]), y, rcond=None)[0]
        bad = [k for k, c in zip(keep, coef[1:]) if c < 0]
        if not bad:
            full = np.zeros(x.shape[1] + 1)
            full[0], full[[k + 1 for k in keep]] = coef[0], coef[1:]
            return full
        keep.remove(bad[0])


def peer(df: pd.DataFrame, d: pd.DataFrame, parent: pd.Series) -> pd.Series:
    """Repaired peer value: log P/B (on book net of preferred) fitted on normal ROE and expected growth
    (bounded) within the industry when it has 15+ valued members; a smaller industry uses its parent
    sector's fit (the market's when the parent is small too, financials apart) plus n/(n+10) of its
    own mean residual. Financials on normal ROE alone."""
    pb = np.log((df["price"] / d["bps_c"]).where(d["bps_c"] > 0))
    x = pd.DataFrame({"roe": d["roe_norm"].clip(-0.1, 0.5), "g": d["g_exp"].clip(-0.1, 0.3).fillna(0.03)})
    fin = df["financial"].astype(bool)
    usable = d["valued"] & pb.notna() & x["roe"].notna()
    out = pd.Series(np.nan, df.index)
    pool = parent.where(~fin, "金融").fillna("其他")
    for (_, is_fin), members in df.groupby([df["industry"], fin]):
        rows = members.index[usable[members.index]]
        cols = ["roe"] if is_fin else ["roe", "g"]
        if len(rows) >= MIN_GROUP:
            sample, shift = rows, 0.0
        else:
            sample = usable.index[usable & (pool == pool[members.index[0]])]
            if len(sample) < MIN_GROUP:
                sample = usable.index[usable & (fin == fin[members.index[0]])]
            shift = None
        coef = fit(pb[sample].to_numpy(), x.loc[sample, cols].to_numpy())
        pred = lambda idx: coef[0] + x.loc[idx, cols].to_numpy() @ coef[1:]
        if shift is None:
            resid = pb[rows] - pred(rows) if len(rows) else pd.Series(dtype=float)
            shift = len(rows) / (len(rows) + SHRINK) * resid.mean() if len(rows) else 0.0
        target = members.index[d.loc[members.index, "valued"]]
        out[target] = np.exp(pred(target) + shift) * d.loc[target, "bps_c"]
    return out


def combine(v: pd.DataFrame, price: pd.Series, archetype: pd.Series, w_hist: pd.Series) -> pd.DataFrame:
    """Combined value in logs: steady and growth (1 − w) × [0.6, 0.3, 0.1] + w × [0.5, 0.1, 0.4] (w = the
    history weight); financials [0.55, 0.3, 0.15]; missing anchors drop out; no intrinsic value, no
    combined value. dispersion = weighted standard deviation of the anchors in logs."""
    w = w_hist.to_numpy()[:, None]
    weights = (1 - w) * np.array(WEIGHTS["steady"]) + w * np.array(WEIGHTS["cyclical"])
    weights[(archetype == "financial").to_numpy()] = WEIGHTS["financial"]
    a = np.log(v[["v_intrinsic", "v_peer", "v_own"]].where(v[["v_intrinsic", "v_peer", "v_own"]] > 0)
               .to_numpy(float) / price.to_numpy()[:, None])
    weights = np.where(np.isnan(a), 0.0, weights)
    weights[np.isnan(a[:, 0])] = 0.0
    total = weights.sum(axis=1)
    safe = np.where(total > 0, total, 1.0)
    mean = (np.nan_to_num(a) * weights).sum(axis=1) / safe
    disp = np.sqrt((weights * (np.nan_to_num(a) - mean[:, None]) ** 2).sum(axis=1) / safe)
    ok = total > 0
    return pd.DataFrame({"v_comb": np.where(ok, price * np.exp(mean), np.nan), "dispersion": np.where(ok, disp, np.nan),
                         "n_anchors": (weights > 0).sum(axis=1)}, index=v.index)


def screen(df: pd.DataFrame, h: pd.DataFrame) -> pd.DataFrame:
    """Quality screen (quality-screen rules, market-wide; buy and hold only): 10-year ROE < 8% (exemption
    A: under 10 years of history, gross margin > 30%, operating cash flow positive in the last 2 years);
    5-year OCF/NI < 0.7; 5-year free cash flow < 0 (US: CN/HK tables have no capex); long-run net margin
    < 5% (exemption B: gross margin > 30% and the last 2 years at 5%+ or rising; C: 10-year ROE > 20%
    and OCF/NI > 1). Banks, insurers and brokers on ROE alone. Dilution > 20% in 5 years is a flag (US)."""
    fin, gm = df["financial"].astype(bool), df["gross_margin"]
    young = (h["n_years"] < 10) & (gm > 0.3) & h["ocf_2y_pos"].eq(True)
    exempt_b = (gm > 0.3) & ((h["margin_2y"] >= 0.05) | (h["margin_2y"] > h["margin_hist"]))
    exempt_c = (h["roe_hist"] > 0.2) & (h["ocf_ni_5y"] > 1)
    fails = pd.DataFrame({
        "ROE<8%": (h["roe_hist"] < 0.08) & ~young,
        "OCF/NI<0.7": ~fin & (h["ocf_ni_5y"] < 0.7),
        "FCF<0": ~fin & (h["fcf_5y"] < 0),
        "净利率<5%": ~fin & (h["margin_hist"] < 0.05) & ~exempt_b & ~exempt_c,
    }, index=df.index).fillna(False)
    text = fails.apply(lambda r: ",".join(c for c in fails.columns if r[c]), axis=1)
    return pd.DataFrame({"screen_fails": text, "screen_ok": text == ""}, index=df.index)


def confidence(v: pd.DataFrame, h: pd.DataFrame, analysts: pd.Series, price: pd.Series) -> pd.DataFrame:
    """Points: anchor agreement (dispersion ≤ 0.15 +2, ≤ 0.3 +1, > 0.5 −1), three anchors +1 / one −1,
    7+ years of history +1 / under 5 −1, 5+ analysts +1 / under 3 for growth or cyclical −1, steady or
    financial +1, quality screen +1 / −1, normal ROE within 3 points of analysts' year 3 +1 / 5+ points
    above it −2, the market disagreeing by more than 2× −2, trailing core EPS and next year's consensus
    more than 2× apart −1, revisions with / against the call ±1, a cut history −1. 5+ = 高, 3-4 = 中,
    else 低; dispersion above 0.5 or any value above 3× price caps at 低."""
    disp, arch, up = v["dispersion"], v["archetype"], v["v_final"] / price - 1
    s = pd.Series(np.select([disp <= 0.15, disp <= 0.30, disp > 0.5], [2, 1, -1], 0), v.index)
    s += np.select([v["n_anchors"] == 3, v["n_anchors"] <= 1], [1, -1], 0)
    s += np.select([h["n_years"] >= 7, ~(h["n_years"] >= 5)], [1, -1], 0)
    s += np.select([analysts >= 5, (analysts < 3) & arch.isin(["growth", "cyclical"])], [1, -1], 0)
    s += np.where(arch.isin(["steady", "financial"]), 1, 0) + np.where(v["screen_ok"], 1, -1)
    gap = v["roe_norm"] - v["roe_c3"]
    s += np.select([gap.abs() <= 0.03, gap > 0.05], [1, -2], 0)
    s -= 2 * ((up > 1.0) | (up < -0.5)).astype(int)  # the market disagrees by more than 2×
    eps, e2 = v["eps_core"], v["e2"]
    s -= ((eps > 0) & (e2 > 0) & ((e2 / eps > 2) | (e2 / eps < 0.5)) | ((eps > 0) != (e2 > 0))).astype(int)
    rev = h["revision"].fillna(0)
    agree = (rev >= 0.03) & (up > 0) | (rev <= -0.03) & (up < 0)
    s += np.select([agree, (rev.abs() >= 0.03) & ~agree & (up != 0)], [1, -1], 0)
    if "history_from" in h:
        s -= h["history_from"].notna().astype(int)
    label = np.select([s >= 5, s >= 3], ["高", "中"], "低")
    shown = v[["v_intrinsic", "v_comb", "v_final", "v_regime", "v_new"]].max(axis=1)
    capped = (disp > 0.5) | (shown > 3 * price)
    label = np.where(capped, "低", label)
    return pd.DataFrame({"conf_points": s, "confidence": np.where(v["v_final"].notna(), label, "")}, index=v.index)
