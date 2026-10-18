"""Regime breaks (docs/REVIEW.md A2.7). A data test compares today (the current ROE, from the trailing year
and consensus) with the last 5 fiscal years, as the measured base rates do; analysts confirm a break
when their year-3 ROE keeps at least half of the move. A confirmed break is valued twice: the new regime
persists (consensus, slow fade) and the old pattern returns (the old normal ROE, fast fade). Our
probability that the new regime lasts is the market's measured base rate (history.base_rates) moved by
evidence in log-odds; the stock is valued at the probability-weighted value, and the market's implied
probability is where the price sits between the two. The thresholds and evidence weights are first
guesses for Phase 9 to fit."""

import numpy as np
import pandas as pd

from stockreport.config import CONFIG
from stockreport.engine import fade_years, ri, solve, R_RANGE

STEP, NEW_MIN, REV_SHIFT, CONFIRM = 0.12, 0.18, 0.15, 0.5  # the base-rate episodes' move (history.episodes)
PHI_NEW = CONFIG["v2"]["phi_new"]  # per market: persistence floor under the new regime (Phase 9: measured)
PHI_OLD = 0.3  # persistence cap under the old one
OWN_BOOM = CONFIG["v2"]["own_boom_weight"]  # log-odds for the stock's own last boom (Phase 9: no predictive power, 0)
POSITIVE = {"预增", "扭亏", "略增", "续盈"}
NEGATIVE = {"预减", "首亏", "略减", "续亏"}


def test(d: pd.DataFrame, h: pd.DataFrame, margin_now: pd.Series) -> pd.DataFrame:
    """direction (up / down / ""), whether analysts confirm it, the old and the new ROE level. The
    break is the base rates' episode (history.episodes) with today as the latest year: the current ROE
    12+ points above the mean of the last 5 fiscal years and at 18%+ (down: 12+ points below an old level
    of 8%+), and at least 1.5× (down: at most half) of it, backed by a net margin 5+ points away from the
    5-year margin or revenue growth in the last 3 years 15+ points faster (20%+) / slower (no growth)
    than in the years before. A steady grower whose losses all came before the last 3 years is not a
    break (A1: valued on today and consensus); a level that has held for years is the regime, not a break."""
    old, new = h["roe_5y"], d["roe_cur"]
    step, margin, shift = new - old, margin_now - h["margin_5y"], h["rev_g3"] - h["rev_g_before"]
    turning = (h["rev_down_years"] <= 1) & (h["rev_cagr_5y"] >= 0.15) & ~(old > 0.03) & h["early_losses_only"].eq(True)
    up = ~turning & (step >= STEP) & (new >= NEW_MIN) & ((old <= 0) | (new >= 1.5 * old)) & (
        (margin >= 0.05) | ((shift >= REV_SHIFT) & (h["rev_g3"] >= 0.20)))
    down = (old >= 0.08) & (step <= -STEP) & (new <= 0.5 * old) & ((margin <= -0.05) | ((shift <= -REV_SHIFT) & (h["rev_g3"] <= 0)))
    out = pd.DataFrame(index=d.index)
    out["break_dir"] = np.select([up & old.notna(), down & old.notna()], ["up", "down"], "")
    out["break_keep"] = ((d["roe_c3"] - old) / step).where(step.abs() > 0.01)  # share of the move analysts keep in year 3
    out["break_confirmed"] = (out["break_dir"] != "") & d["has_cons"] & (out["break_keep"] >= CONFIRM) & d["valued"]
    out["roe_old"] = h["roe_hist"].fillna(old)  # the old pattern: the 10-year normal ROE
    out["roe_new"] = pd.concat([new, d["roe_c3"]], axis=1).mean(axis=1)  # today and analysts' year 3
    return out


def probability(b: pd.DataFrame, d: pd.DataFrame, h: pd.DataFrame, rates: pd.DataFrame,
                pre_type: pd.Series, ai: pd.Series, gauge: float) -> tuple[pd.Series, pd.Series]:
    """Our probability that the new regime lasts, with its evidence in words: the base rate for the
    break's direction and the stock's history (cyclical: a loss or 2+ revenue down years), moved by the
    stock's own last boom, how durable consensus is, the newest 业绩预告, revisions and (AI-tagged
    stocks) the capex of the largest US spenders."""
    p, why = pd.Series(np.nan, b.index), pd.Series("", b.index)
    for code in b.index[b["break_confirmed"]]:
        up = b.at[code, "break_dir"] == "up"
        hist = "cyclical" if (h.at[code, "rev_down_years"] >= 2 or h.at[code, "loss_years"] >= 1) else "steady"
        key = (b.at[code, "break_dir"], hist)
        if key not in rates.index or rates.loc[key, "count"] < 20:
            key = (key[0], "all")
        base, n = float(np.clip(rates.loc[key, "mean"], 0.02, 0.98)), int(rates.loc[key, "count"])
        notes = [f"基础比率 {base:.0%}（{n} 例{'，周期史' if key[1] == 'cyclical' else ''}）"]
        z = np.log(base / (1 - base))
        kept, year = h.at[code, "past_boom_kept"], h.at[code, "past_boom_year"]
        if OWN_BOOM and up and pd.notna(kept) and year <= h.at[code, "first_year"] + h.at[code, "n_years"] - 4:
            z += OWN_BOOM if kept else -OWN_BOOM
            notes.append(f"{year:.0f} 年那轮高 ROE {'延续了' if kept else '三年内回落'}{'+' if kept else '−'}")
        if not up and d.at[code, "structural_decline"]:
            z += 0.8
            notes.append("五年 ROE 持续下行且分析师不预期回升+")
        durable = d.at[code, "e3"] / d.at[code, "e1"] if d.at[code, "e1"] > 0 else np.nan
        if pd.notna(durable):
            sign = 1 if up else -1
            if durable >= 1.15:
                z += 0.4 * sign
            elif durable < 0.9:
                z -= 0.4 * sign
            notes.append(f"分析师第3年/第1年 EPS {durable:.2f}")
            if up and d.at[code, "e3"] < 0.95 * d.at[code, "e2"]:
                z -= 0.3
                notes.append("分析师预计第 2 年见顶−")
        t = pre_type.get(code)
        if isinstance(t, str) and t in POSITIVE | NEGATIVE:
            z += (0.2 if t in POSITIVE else -0.3) * (1 if up else -1)
            notes.append(f"业绩预告 {t}")
        rev = h.at[code, "revision"]
        if pd.notna(rev) and abs(rev) >= 0.03:
            z += 0.3 * np.sign(rev) * (1 if up else -1)
            notes.append(f"一致预期 4 周 {rev:+.0%}")
        if up and ai.get(code, False) and pd.notna(gauge):
            z += 0.3 if gauge >= 0.2 else -0.5 if gauge <= 0 else 0
            notes.append(f"美股前 10 大资本开支 {gauge:+.0%}")
        p[code], why[code] = float(np.clip(1 / (1 + np.exp(-z)), 0.05, 0.95)), "；".join(notes)
    return p, why


def scenarios(b: pd.DataFrame, d: pd.DataFrame, h: pd.DataFrame, price: pd.Series, r: pd.Series,
              g_long: float, market: str = "us") -> pd.DataFrame:
    """V_new: consensus without a haircut and the post-break normal ROE (today and analysts' year 3), slow
    fade; for a downward break book follows the shrinking revenue. V_old:
    consensus fully pulled toward the old path, the old normal ROE, fast fade. Then the value at our
    probability, the expected return at that value and the market's implied probability."""
    rows = b["break_confirmed"].to_numpy()
    out = pd.DataFrame(index=b.index, columns=["v_new", "v_old", "v_regime", "icc_regime", "p_market"], dtype=float)
    if not rows.any():
        return out
    dd = d[rows].copy()
    bb, pp = b[rows], b.loc[rows, "p"].to_numpy()
    new = dd.assign(g0=np.where(bb["break_dir"] == "down", np.minimum(dd["g0"], h.loc[rows, "rev_g3"].clip(-0.1)), dd["g0"]))
    phi = dd["phi"].to_numpy()
    floor, years = (PHI_NEW[market] if isinstance(PHI_NEW, dict) else PHI_NEW), fade_years(market)
    v_new = lambda rr: ri(rr, new, g_long, w=0.0, nn=bb["roe_new"].to_numpy(), phi=np.maximum(phi, floor), years=years)
    v_old = lambda rr: ri(rr, dd, g_long, w=1.0, nn=bb["roe_old"].to_numpy(), phi=np.minimum(phi, PHI_OLD), years=years)
    rr, px = r[rows].to_numpy(), price[rows].to_numpy()
    vn, vo = np.maximum(v_new(rr), 0), np.maximum(v_old(rr), 0)
    out.loc[rows, "v_new"], out.loc[rows, "v_old"] = vn, vo
    out.loc[rows, "v_regime"] = pp * vn + (1 - pp) * vo
    out.loc[rows, "icc_regime"] = solve(lambda x: pp * v_new(x) + (1 - pp) * v_old(x), px, *R_RANGE)
    out.loc[rows, "p_market"] = (px - vo) / np.where(np.abs(vn - vo) > 1e-9, vn - vo, np.nan)
    return out


def capex_gauge(us_annual: pd.DataFrame) -> float:
    """Combined capex growth of the 10 largest spenders among the US candidates (latest fiscal year vs
    the one before; USD reporters): the AI evidence the review asks for, with no hand-picked names."""
    a = us_annual[us_annual["currency"] == "USD"].sort_values(["code", "year"])
    last2 = a.groupby("code").tail(2)
    pairs = last2.groupby("code")["capex"].agg(["first", "last", "count"])
    top = pairs[pairs["count"] == 2].nlargest(10, "last")
    return float(top["last"].sum() / top["first"].sum() - 1) if len(top) else np.nan
