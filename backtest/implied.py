"""Stage 3 (docs/PLAN.md, "Stage 3's test"): the implied expected return per stock and month end of the stage-1 frame.
The rate r at which P/B (stage 1's B/P) equals 1 + Σ (earnings_k − r × book_k−1) ÷ (1+r)^k over years 1..T plus year
T's residual income held flat for ever (÷ r). Years 1..H come from the fits in force (the latest 30 June; H = the longest
horizon fit, at most 5), then margin and revenue growth (financials: ROE) fade in a straight line over 10 years to the
sector's long-run level, so T = H + 10. Inputs: the latest fiscal year public on the date, at most 18 months old; the
forecast in units of that year's book applied to the snapshot's latest book. r on a grid 0.5%-50% (0.25-point steps,
linear in between), the first rate at which the value falls to the price. No r when book ≤ 0 or inputs are missing.

  uv run python -m backtest.implied build cn|us|hk   # data/backtest/s3_<market>_ier.pkl (date, code, ier, ...)
"""

import sys
import warnings
from datetime import date, timedelta

import numpy as np
import pandas as pd

from backtest import earn_panel, earnings as en, panel

FADE, STALE = 10, 548
GRID = np.round(np.arange(0.005, 0.50001, 0.0025), 4)


def day_of(d: str) -> str:
    return d if len(d) == 10 else pd.Period(d, "M").end_time.strftime("%Y-%m-%d")


def refit_day(day: str) -> str:
    y = int(day[:4])
    return f"{y}-06-30" if day[5:] >= "06-30" else f"{y - 1}-06-30"


def solve(e: np.ndarray, bprev: np.ndarray, pb: np.ndarray) -> np.ndarray:
    """r per row: value(r) = 1 + Σ (E_k − r B_k−1)/(1+r)^k + (E_T − r B_T−1)/(r (1+r)^T), first grid rate with
    value ≤ P/B, linear between grid points; the grid's ends when no crossing."""
    t = e.shape[1]
    disc = (1 + GRID[None, :]) ** -np.arange(1, t + 1)[:, None]  # T × G
    v = 1 + e @ disc - (bprev @ disc) * GRID[None, :]
    ri_t = e[:, -1:] - GRID[None, :] * bprev[:, -1:]
    v = v + ri_t / GRID[None, :] * disc[-1][None, :]
    below = v <= pb[:, None]
    j = below.argmax(axis=1)
    out = np.where(below.any(axis=1), GRID[j], GRID[-1])
    mid = below.any(axis=1) & (j > 0)
    i = np.flatnonzero(mid)
    v0, v1 = v[i, j[i] - 1], v[i, j[i]]
    out[i] = GRID[j[i] - 1] + (v0 - pb[i]) / (v0 - v1) * (GRID[1] - GRID[0])
    return out


def nonfin_paths(rows: pd.DataFrame, fits: dict, lr: dict) -> tuple[np.ndarray, np.ndarray, int]:
    """Earnings and opening book per year (units of book at t) for non-financials."""
    h = en.horizon(fits, "margin")
    n = len(rows)
    m_lr, g_lr = en.lr_of(rows, lr, "m").to_numpy(float), en.lr_of(rows, lr, "lg").to_numpy(float)
    margins, logg = [], []
    for k in range(1, h + 1):
        margins.append(en.predict(rows, fits, "margin", k))
        logg.append(en.predict(rows, fits, "growth", k))
    if h:
        m_h, gam = margins[-1], logg[-1] - (logg[-2] if h > 1 else 0.0)
    else:
        m_h = rows["m"].to_numpy(float)
        gam = rows["lg"].fillna(rows["med_lg"]).fillna(0.0).to_numpy(float)
    cum = list(logg)
    last = cum[-1] if cum else np.zeros(n)
    for k in range(1, FADE + 1):
        w = k / FADE
        margins.append(m_h + (m_lr - m_h) * w)
        last = last + gam + (g_lr - gam) * w
        cum.append(last)
    e = rows["sb"].to_numpy(float)[:, None] * np.exp(np.column_stack(cum)) * np.column_stack(margins)
    pay = rows["payout"].to_numpy(float)
    b = np.ones((n, e.shape[1] + 1))
    for j in range(e.shape[1]):
        b[:, j + 1] = b[:, j] + e[:, j] - pay * np.maximum(e[:, j], 0)
    return e, b[:, :-1], h


def fin_paths(rows: pd.DataFrame, fits: dict, lr: dict) -> tuple[np.ndarray, np.ndarray, int]:
    """Earnings and opening book per year (units of book at t) for financials, from ROE."""
    h = en.horizon(fits, "roe")
    roe = [en.predict(rows, fits, "roe", k) for k in range(1, h + 1)]
    r_h = roe[-1] if h else rows["roe"].to_numpy(float)
    r_lr = en.lr_of(rows, lr, "roe").to_numpy(float)
    roe += [r_h + (r_lr - r_h) * k / FADE for k in range(1, FADE + 1)]
    e, b = en.book_path(np.column_stack(roe), rows["payout"].to_numpy(float))
    return e, b[:, :-1], h


def build(market: str) -> pd.DataFrame:
    warnings.simplefilter("ignore")
    fitp, own, floor = earn_panel.panels(market)
    p = en.prepare(fitp, floor)
    o = p if market != "us" else en.prepare(own, 0.0)
    outs = {h: en.outcomes(p, h) for h in range(1, en.H_MAX + 1)}
    f = pd.read_pickle(panel.BT / f"s1_{market}_result.pkl")
    fits_at, out = {}, []
    for d, g in f.groupby("date", sort=True):
        day = day_of(d)
        r_day = refit_day(day)
        if r_day not in fits_at:
            fits_at[r_day] = en.fit_at(p, outs, r_day)
        fits = fits_at[r_day]
        oldest = (date.fromisoformat(day) - timedelta(days=STALE)).isoformat()
        latest = o[(o["avail"] <= day) & (o["fy_end"] >= oldest)].groupby("code").tail(1).set_index("code")
        rows = latest.reindex(g["code"]).dropna(subset=["year"])
        rows = rows[rows["base"].astype(bool) & (rows["book"] > 0)].reset_index()
        rows["fin"], rows["year"] = rows["fin"].astype(bool), rows["year"].astype(int)
        rows = en.with_medians(rows, en.medians(p, day))
        rows["payout"] = rows["payout"].fillna(0.0)
        lr = en.long_run(p, day)
        pb = 1 / g.set_index("code")["bp"].reindex(rows["code"]).to_numpy(float)
        res = pd.DataFrame({"code": rows["code"], "ier": np.nan, "h": np.nan, "roe1": np.nan, "fin": rows["fin"]})
        for is_fin, paths in ((False, nonfin_paths), (True, fin_paths)):
            sel = (rows["fin"] == is_fin) & (rows["roe" if is_fin else "m"].notna()) & np.isfinite(pb) & (pb > 0)
            if not sel.any():
                continue
            e, bprev, h = paths(rows[sel], fits, lr)
            ok = np.isfinite(e).all(axis=1) & np.isfinite(bprev).all(axis=1)
            idx = np.flatnonzero(sel.to_numpy())[ok]
            res.loc[idx, "ier"] = solve(e[ok], bprev[ok], pb[sel.to_numpy()][ok])
            res.loc[idx, "h"], res.loc[idx, "roe1"] = h, e[ok, 0]
        out.append(res.assign(date=d))
        print(f"{market} {d}: {res['ier'].notna().sum()}/{len(g)} valued, H = {en.horizon(fits, 'margin')} / "
              f"{en.horizon(fits, 'roe')} (fits of {r_day}), median {res['ier'].median():.3f}", flush=True)
    s = pd.concat(out, ignore_index=True)
    s.to_pickle(panel.BT / f"s3_{market}_ier.pkl")
    return s


if __name__ == "__main__":
    {"build": build}[sys.argv[1]](sys.argv[2])
