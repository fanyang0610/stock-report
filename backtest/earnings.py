"""Stage 3 (docs/PLAN.md, "Stage 3's test"): the earnings forecast and part (a), its accuracy against "this year's
margin persists, revenue at the sector median growth" (financials: ROE persists). Definitions as registered:
- Non-financials: earnings = revenue × margin. Per horizon h = 1..5 one direct OLS fit of margin(t+h) on margin(t),
  its change, accruals, the gross-margin change, a loss flag and the sector median margin; and one of revenue's log
  growth t→t+h on its log growth t−1→t and the sector median log growth. Financials: ROE(t+h) on ROE(t), its change,
  the loss flag and the sector median ROE; book grows by earnings less the net payout (paid on positive earnings).
- Fits every 30 June on the pairs whose outcome was public by then (300+), winsorized at the sample's 1st/99th
  percentiles; forecasts on raw inputs; a missing change, accrual or gross margin counts as 0.
- (a): forecasts on 30 June of t+1, the 800 largest books per base year, |error| ÷ book(t) capped at 1; 3 years: lower,
  pooled and in at least half of the base years; 1 year: at most 2% above the benchmark's.

  uv run python -m backtest.earnings accuracy cn|us|hk   # part (a), run once
"""

import sys
import warnings

import numpy as np
import pandas as pd

from backtest import earn_panel

H_MAX, MIN_PAIRS, MIN_MED, MIN_LR, TOP, CAP, TIE = 5, 300, 10, 30, 800, 1.0, 1.02
X = {"margin": ["m", "dm", "acc", "dgm", "loss", "med_m"], "growth": ["lg", "med_lg"],
     "roe": ["roe", "droe", "loss", "med_roe"]}
ZERO = ["dm", "acc", "dgm", "lg", "droe"]  # missing counts as 0 (no information)
STATS = {"m": False, "lg": False, "roe": True, "payout": None}  # sector medians: column -> group (None: both groups)


# ---------------------------------------------------------------- the panel's derived columns

def prepare(p: pd.DataFrame, floor: float) -> pd.DataFrame:
    """Per company-year: margin, its change, accruals, gross-margin change, loss, log revenue growth, ROE (on the
    previous book), its change, the 3-year net payout, sales ÷ book, and base-year eligibility (revenue ≥ the floor)."""
    p = p.sort_values(["code", "year"]).drop_duplicates(["code", "year"], keep="last").reset_index(drop=True)
    g = p.groupby("code")

    def prev(s: pd.Series, k: int = 1) -> pd.Series:
        return s.groupby(p["code"]).shift(k).where(g["year"].shift(k) == p["year"] - k)

    rev = p["rev"].where(p["rev"] > 0)
    p["m"] = p["earn"] / rev
    p["dm"] = p["m"] - prev(p["m"])
    gm = p["gp"] / rev
    p["dgm"] = gm - prev(gm)
    p["acc"] = (p["earn"] - p["ocf"]) / rev
    p["loss"] = (p["earn"] < 0).astype(float).where(p["earn"].notna())
    p["lg"] = np.log(rev / prev(rev))
    p["roe"] = p["earn"] / prev(p["book"]).where(prev(p["book"]) > 0)
    p["droe"] = p["roe"] - prev(p["roe"])
    e3 = p["earn"] + prev(p["earn"]) + prev(p["earn"], 2)
    b3 = prev(p["book"], 3)
    p["payout"] = (1 - (p["book"] - b3) / e3).where((e3 > 0) & b3.notna()).clip(0, 1)
    p["sb"] = rev / p["book"].where(p["book"] > 0)
    p["base"] = (p["rev"] >= floor) & (p["rev"] > 0) & p["earn"].notna()
    p["fin"] = p["fin"].astype(bool)
    return p


def outcomes(p: pd.DataFrame, h: int) -> pd.DataFrame:
    """Each row's outcome h years later (same company): revenue, earnings, margin, ROE, public date."""
    o = p[["code", "year", "rev", "earn", "m", "roe", "avail"]].copy()
    o["year"] = o["year"] - h
    o.columns = ["code", "year"] + [f"{c}_h" for c in ["rev", "earn", "m", "roe", "avail"]]
    return p[["code", "year"]].merge(o, on=["code", "year"], how="left").set_index(p.index)


# ---------------------------------------------------------------- sector medians and long-run levels

def medians(p: pd.DataFrame, day: str) -> dict:
    """Per stat: medians by (fin, sector, year) and by (fin, year), over the base rows public by `day`."""
    rows = p[p["base"] & (p["avail"] <= day)]
    out = {}
    for col, grp in STATS.items():
        r = rows if grp is None else rows[rows["fin"] == grp]
        by = r.groupby(["fin", "sector", "year"])[col].agg(["median", "count"])
        mk = r.groupby(["fin", "year"])[col].agg(["median", "count"])
        out[col] = (by[by["count"] >= MIN_MED]["median"], mk[mk["count"] >= MIN_MED]["median"])
    return out


def attach(rows: pd.DataFrame, med: dict, col: str) -> pd.Series:
    """The sector median of `col` for each row's base year: (sector, t), else (sector, t−1), else the market's."""
    by, mk = med[col]
    out = pd.Series(np.nan, rows.index)
    for key, table in (([rows["fin"], rows["sector"], rows["year"]], by), ([rows["fin"], rows["sector"], rows["year"] - 1], by),
                       ([rows["fin"], rows["year"]], mk), ([rows["fin"], rows["year"] - 1], mk)):
        idx = pd.MultiIndex.from_arrays(key)
        out = out.fillna(pd.Series(table.reindex(idx).to_numpy(), rows.index))
    return out


def with_medians(rows: pd.DataFrame, med: dict) -> pd.DataFrame:
    rows = rows.copy()
    rows["med_m"], rows["med_lg"], rows["med_roe"] = (attach(rows, med, c) for c in ("m", "lg", "roe"))
    rows["payout"] = rows["payout"].fillna(attach(rows, med, "payout"))
    return rows


def long_run(p: pd.DataFrame, day: str) -> dict:
    """Per stat (m, lg non-financial; roe financial): the median company-year of the last 10 fiscal years public by
    `day`, per (fin, sector) with 30+ company-years, and per fin group (the market's)."""
    rows = p[p["base"] & (p["avail"] <= day)]
    rows = rows[rows["year"] >= rows["year"].max() - 9]
    out = {}
    for col, grp in (("m", False), ("lg", False), ("roe", True)):
        r = rows[rows["fin"] == grp]
        by = r.groupby("sector")[col].agg(["median", "count"])
        out[col] = (by[by["count"] >= MIN_LR]["median"], r[col].median())
    return out


def lr_of(rows: pd.DataFrame, lr: dict, col: str) -> pd.Series:
    by, market = lr[col]
    return rows["sector"].map(by).fillna(market)


# ---------------------------------------------------------------- fits and forecasts

def design(rows: pd.DataFrame, kind: str) -> np.ndarray:
    x = rows[X[kind]].copy()
    for c in ZERO:
        if c in x:
            x[c] = x[c].fillna(0.0)
    return x.fillna(0.0).to_numpy(float)


def fit_at(p: pd.DataFrame, outs: dict, day: str) -> dict:
    """(kind, h) -> coefficients (intercept first), fit on the pairs whose outcome was public by `day`."""
    med = medians(p, day)
    fits = {}
    for h, o in outs.items():
        known = p["base"] & (o["avail_h"] <= day)
        rows = with_medians(p[known], med)
        oh = o[known]
        targets = {"margin": (~rows["fin"] & rows["m"].notna() & oh["m_h"].notna(), oh["m_h"]),
                   "growth": (~rows["fin"] & (oh["rev_h"] > 0), np.log(oh["rev_h"] / rows["rev"])),
                   "roe": (rows["fin"] & rows["roe"].notna() & oh["roe_h"].notna(), oh["roe_h"])}
        for kind, (ok, y) in targets.items():
            if ok.sum() < MIN_PAIRS:
                continue
            xs, ys = design(rows[ok], kind), y[ok].to_numpy(float)
            lo, hi = np.nanpercentile(xs, 1, axis=0), np.nanpercentile(xs, 99, axis=0)
            binary = [c == "loss" for c in X[kind]]
            xs = np.where(binary, xs, np.clip(xs, lo, hi))
            ys = np.clip(ys, *np.percentile(ys, [1, 99]))
            fits[(kind, h)] = np.linalg.lstsq(np.column_stack([np.ones(len(xs)), xs]), ys, rcond=None)[0]
    return fits


def horizon(fits: dict, kind: str) -> int:
    """The longest horizon H with fits for 1..H (growth too, for non-financials)."""
    need = ["roe"] if kind == "roe" else ["margin", "growth"]
    h = 0
    while h < H_MAX and all((k, h + 1) in fits for k in need):
        h += 1
    return h


def predict(rows: pd.DataFrame, fits: dict, kind: str, h: int) -> np.ndarray:
    b = fits[(kind, h)]
    return b[0] + design(rows, kind) @ b[1:]


def book_path(roe: np.ndarray, payout: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Earnings and book (units of book at t) from ROE per year (columns): book grows by earnings less the payout
    on positive earnings."""
    n, k = roe.shape
    e, b = np.zeros((n, k)), np.ones((n, k + 1))
    for j in range(k):
        e[:, j] = roe[:, j] * b[:, j]
        b[:, j + 1] = b[:, j] + e[:, j] - payout * np.maximum(e[:, j], 0)
    return e, b


# ---------------------------------------------------------------- part (a)

def accuracy(market: str) -> dict:
    warnings.simplefilter("ignore")
    fitp, _, floor = earn_panel.panels(market)
    p = prepare(fitp, floor)
    outs = {h: outcomes(p, h) for h in range(1, H_MAX + 1)}
    years = sorted(p["year"].unique())
    res = {1: [], 3: []}
    for t in years:
        day = f"{t + 1}-06-30"
        fits = fit_at(p, outs, day)
        rows = p[(p["year"] == t) & p["base"] & (p["avail"] <= day) & (p["book"] > 0)]
        rows = with_medians(rows[~rows["fin"] | rows["roe"].notna()], medians(p, day))
        rows["payout"] = rows["payout"].fillna(0.0)
        for h in res:
            o = outs[h].loc[rows.index]
            have = {False: horizon(fits, "margin") >= h, True: horizon(fits, "roe") >= h}
            ev = rows[o["earn_h"].notna() & rows["fin"].map(have)]
            ev = ev.sort_values("book", ascending=False).head(TOP)
            if ev.empty:
                continue
            actual = outs[h].loc[ev.index, "earn_h"].to_numpy(float)
            model, bench = np.full(len(ev), np.nan), np.full(len(ev), np.nan)
            nf = ~ev["fin"].to_numpy()
            if nf.any():
                r = ev[nf]
                model[nf] = r["rev"] * np.exp(predict(r, fits, "growth", h)) * predict(r, fits, "margin", h)
                bench[nf] = r["rev"] * np.exp(h * r["med_lg"].fillna(0)) * r["m"]
            if (~nf).any():
                r = ev[~nf]
                pay = r["payout"].to_numpy(float)
                roe_m = np.column_stack([predict(r, fits, "roe", k) for k in range(1, h + 1)])
                roe_b = np.repeat(r["roe"].to_numpy(float)[:, None], h, axis=1)
                model[~nf] = book_path(roe_m, pay)[0][:, -1] * r["book"]
                bench[~nf] = book_path(roe_b, pay)[0][:, -1] * r["book"]
            book = ev["book"].to_numpy(float)
            res[h].append(pd.DataFrame({"year": t, "fin": ev["fin"].to_numpy(),
                                        "model": np.minimum(np.abs(model - actual) / book, CAP),
                                        "bench": np.minimum(np.abs(bench - actual) / book, CAP)}))
    return summarize(market, {h: pd.concat(v) for h, v in res.items() if v})


def summarize(market: str, res: dict) -> dict:
    out = {}
    print(f"\n==== {market.upper()} stage 3 (a): forecast accuracy, |error| ÷ book(t) capped at {CAP:g}, the {TOP} largest books a year")
    for h, d in res.items():
        by = d.groupby("year")[["model", "bench"]].mean()
        by["n"] = d.groupby("year").size()
        by["model lower"] = by["model"] < by["bench"]
        print(f"-- {h} year{'s' if h > 1 else ''} ahead, per base year (mean error)\n" + by.round(4).to_string())
        grp = d.groupby("fin")[["model", "bench"]].mean().rename(index={False: "non-financials", True: "financials"})
        print("by group (mean): " + "; ".join(f"{i} model {r['model']:.4f} vs {r['bench']:.4f}" for i, r in grp.iterrows()))
        mm, mb = d["model"].mean(), d["bench"].mean()
        lower_years = int(by["model lower"].sum())
        ok = (mm < mb and lower_years >= len(by) / 2) if h == 3 else mm <= TIE * mb
        print(f"pooled mean {mm:.4f} vs benchmark {mb:.4f} ({mm / mb - 1:+.1%}); median {d['model'].median():.4f} vs "
              f"{d['bench'].median():.4f}; model lower in {lower_years}/{len(by)} base years; "
              f"{'lower (pooled and in half the years)' if h == 3 else 'not worse (≤ +2%)'}: {'pass' if ok else 'FAIL'}")
        out[h] = {"model": mm, "bench": mb, "years": len(by), "lower_years": lower_years, "n": len(d), "pass": ok}
    passed = all(out.get(h, {}).get("pass", False) for h in (1, 3))
    print(f"   {market.upper()} (a) passes: {passed}")
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    {"accuracy": accuracy}[sys.argv[1]](sys.argv[2])
