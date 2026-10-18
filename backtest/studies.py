"""Panel studies for the Phase 9 calibration, on the yearly history panels (CN 2009+, US and HK 2015+):
- regime persistence: how well base-rate groupings and evidence predict whether an ROE jump lasts (A2.7);
- normal ROE: whether the history weight and cycle rules forecast the next 3 years' ROE better than
  today's ROE or the 10-year mean, and which rule parameters do best in-sample;
- φ: how much of an excess ROE is still there 5-10 years later.
In-sample = outcomes known by the end of 2023; out-of-sample = the rest (A4)."""

import numpy as np
import pandas as pd

from stockreport import engine, history

EPS = 1e-6


def years(market: str) -> pd.DataFrame:
    y = history.YEARS[market]().sort_values(["code", "year"]).drop_duplicates(["code", "year"], keep="last")
    return y.reset_index(drop=True)


# ---------------------------------------------------------------- regime persistence

def episode_table(y: pd.DataFrame) -> pd.DataFrame:
    """history.episodes with the evidence known in the episode's year: the history groupings (loss, revenue
    down years, ROE volatility), the size and level of the jump, the net margin against its 5-year mean,
    revenue growth against the 3 years before, the stock's own earlier episode and its outcome."""
    y = y.copy()
    y["roe"] = y["roe"].clip(-0.5, 1.0)
    g = y.groupby("code")
    roll = lambda s, n=5, f="mean": getattr(s.groupby(y["code"]).shift(1).groupby(y["code"]).rolling(n, min_periods=3), f)().reset_index(level=0, drop=True)
    y["prior"] = roll(y["roe"])
    y["prior_sd"] = roll(y["roe"], f="std")
    down = (g["rev"].pct_change() < -0.02).astype(float)
    loss = (y["roe"] < 0).astype(float)
    y["downs"], y["losses"] = roll(down, f="sum"), roll(loss, f="sum")
    y["cyclical"] = roll(((down > 0) | (loss > 0)).astype(float), f="sum") >= 2  # history.episodes' definition
    margin = y["core"] / y["rev"].where(y["rev"] > 0)
    y["margin_step"] = margin - roll(margin)
    y["rev_g1"] = g["rev"].pct_change()
    y["rev_g_prior"] = roll(y["rev_g1"], 3)
    y["move"] = y["roe"] - y["prior"]
    y["dir"] = np.select([(y["move"] >= 0.12) & (y["roe"] >= 0.18), y["move"] <= -0.12], ["up", "down"], "")
    first = (y["dir"] != "") & (y["dir"] != g["dir"].shift(1).fillna(""))
    later = g["roe"].shift(-3).where(g["year"].shift(-3) == y["year"] + 3)
    y["kept"] = ((later - y["prior"]) / y["move"] >= 0.5).where(later.notna())
    y["outcome_avail"] = g["avail"].shift(-3)
    e = y[first].copy()
    e["rel_vol"] = e["prior_sd"] / e["prior"].abs().clip(lower=0.05)
    # the stock's own earlier episode in the same direction whose outcome was public by this year's report
    e["own_prev"] = np.nan
    for code, part in e.groupby("code"):
        for i, row in part.iterrows():
            prev = part[(part["dir"] == row["dir"]) & (part["year"] < row["year"]) & (part["outcome_avail"] <= row["avail"])]
            if len(prev):
                e.at[i, "own_prev"] = float(prev["kept"].iloc[-1])
    return e[e["kept"].notna()].assign(kept=lambda d: d["kept"].astype(float))


GROUPINGS = {
    "all": lambda e: pd.Series("all", e.index),
    "steady/cyclical (v2 today)": lambda e: np.where(e["cyclical"], "cyclical", "steady"),
    "any loss in 5 years": lambda e: np.where(e["losses"] >= 1, "loss", "no loss"),
    "2+ revenue down years": lambda e: np.where(e["downs"] >= 2, "down", "no"),
    "ROE volatility > 0.5": lambda e: np.where(e["rel_vol"] > 0.5, "volatile", "stable"),
    "jump ≥ 25 points": lambda e: np.where(e["move"] >= 0.25, "big", "small"),
    "new ROE ≥ 35%": lambda e: np.where(e["roe"] >= 0.35, "high", "normal"),
    "margin up ≥ 5 points": lambda e: np.where(e["margin_step"] >= 0.05, "margin", "no margin"),
}


def score(p: np.ndarray, y: np.ndarray) -> dict:
    p = np.clip(p, 0.02, 0.98)
    return {"n": len(y), "realized": y.mean(), "predicted": p.mean(), "brier": np.mean((p - y) ** 2),
            "logloss": -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))}


def grouping_test(e: pd.DataFrame, split_avail: str = "2024-01-01") -> pd.DataFrame:
    """Base rates per group from in-sample episodes (outcome public before split_avail), applied to the
    out-of-sample ones: Brier score and log loss (lower is better), and each group's rates."""
    ins, oos = e[e["outcome_avail"] < split_avail], e[e["outcome_avail"] >= split_avail]
    rows = []
    for name, fn in GROUPINGS.items():
        gi, go = pd.Series(fn(ins), ins.index), pd.Series(fn(oos), oos.index)
        rates = ins["kept"].groupby(gi).agg(["mean", "count"])
        p = go.map(rates["mean"]).fillna(ins["kept"].mean()).to_numpy()
        s = score(p, oos["kept"].to_numpy())
        rates_oos = oos["kept"].groupby(go).agg(["mean", "count"])
        s["groups"] = "; ".join(f"{k} {rates.at[k, 'mean']:.0%} of {rates.at[k, 'count']:.0f} → "
                                f"{rates_oos['mean'].get(k, np.nan):.0%} of {rates_oos['count'].get(k, 0):.0f}"
                                for k in rates.index)
        rows.append({"grouping": name} | s)
    return pd.DataFrame(rows).set_index("grouping")


def logit_fit(x: np.ndarray, y: np.ndarray, l2: float = 1.0) -> np.ndarray:
    """Logistic regression with an intercept and a ridge penalty (not on the intercept), by Newton steps."""
    x = np.column_stack([np.ones(len(x)), x])
    b = np.zeros(x.shape[1])
    pen = np.full(x.shape[1], l2)
    pen[0] = 0
    for _ in range(50):
        p = 1 / (1 + np.exp(-x @ b))
        grad = x.T @ (p - y) + pen * b
        hess = (x * (p * (1 - p))[:, None]).T @ x + np.diag(pen)
        step = np.linalg.solve(hess, grad)
        b -= step
        if np.abs(step).max() < 1e-8:
            break
    return b


def logit_predict(b: np.ndarray, x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-(b[0] + x @ b[1:])))


EVIDENCE = {"cyclical": lambda e: e["cyclical"].astype(float), "log jump": lambda e: np.log(e["move"].clip(lower=0.01)),
            "new ROE": lambda e: e["roe"], "margin step": lambda e: e["margin_step"].clip(-0.3, 0.3).fillna(0),
            "revenue acceleration": lambda e: (e["rev_g1"] - e["rev_g_prior"]).clip(-1, 2).fillna(0),
            "own earlier episode kept": lambda e: e["own_prev"].fillna(0.5) - 0.5,
            "ROE volatility": lambda e: e["rel_vol"].clip(0, 3).fillna(1)}


def evidence_test(e: pd.DataFrame, split_avail: str = "2024-01-01", extra: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Logistic model of 'kept' on the evidence, fitted in-sample; out-of-sample scores against the plain
    base rate, the coefficients (in sd units), and a calibration table (predicted vs realized by fifth)."""
    ev = EVIDENCE | (extra or {})
    x = pd.DataFrame({k: f(e) for k, f in ev.items()}, index=e.index).astype(float)
    ins = (e["outcome_avail"] < split_avail).to_numpy()
    mu, sd = x[ins].mean(), x[ins].std().replace(0, 1)
    z = ((x - mu) / sd).fillna(0).to_numpy()
    b = logit_fit(z[ins], e["kept"].to_numpy()[ins])
    p = logit_predict(b, z)
    y = e["kept"].to_numpy()
    base = np.full(len(y), y[ins].mean())
    scores = pd.DataFrame([{"model": "base rate (all)"} | score(base[~ins], y[~ins]),
                           {"model": "logistic on evidence"} | score(p[~ins], y[~ins]),
                           {"model": "logistic, in-sample fit"} | score(p[ins], y[ins])]).set_index("model")
    coef = pd.Series(b[1:], index=x.columns, name="coef per sd")
    cal = pd.DataFrame({"p": p[~ins], "y": y[~ins]})
    cal["bin"] = pd.qcut(cal["p"], 5, duplicates="drop") if len(cal) >= 25 else "all"
    table = cal.groupby("bin", observed=True).agg(predicted=("p", "mean"), realized=("y", "mean"), n=("y", "size"))
    return scores, pd.concat([coef, pd.Series({"intercept": b[0]})]).to_frame("coef per sd"), table


# ---------------------------------------------------------------- normal ROE and φ

def asof_panel(y: pd.DataFrame, first: int, last: int, cycle=None, vol_band=None) -> pd.DataFrame:
    """For every fiscal year Y in [first, last]: the v2 normal ROE from the history up to Y (no consensus:
    today = ROE of Y, expected growth = 5-year revenue growth), next to the realized ROE of Y+1..Y+10."""
    out = []
    old = engine.CYCLE, engine.VOL_BAND
    engine.CYCLE, engine.VOL_BAND = cycle or engine.CYCLE, vol_band or engine.VOL_BAND
    try:
        for year in range(first, last + 1):
            past = y[y["year"] <= year]
            codes = past.loc[past["year"] == year, "code"].unique()
            h = history.features(past, codes)
            h = h[h["n_years"] >= 5]
            now = past[past["year"] == year].set_index("code")["roe"].clip(*history.ROE_CLIP).reindex(h.index)
            d = pd.DataFrame({"roe_cur": now, "roe_c3": np.nan, "g_exp": h["rev_cagr_5y"], "g_cons": np.nan,
                              "has_cons": False, "e2": np.nan}, index=h.index)
            d = engine.normal(d, h, pd.Series(False, h.index), now)
            out.append(pd.DataFrame({"code": h.index, "year": year, "roe_now": now.to_numpy(), "roe_hist": h["roe_hist"].to_numpy(),
                                     "roe_norm": d["roe_norm"].to_numpy(), "w_hist": d["w_hist"].to_numpy(),
                                     "phi": d["phi"].to_numpy(), "archetype": d["archetype"].to_numpy()}))
    finally:
        engine.CYCLE, engine.VOL_BAND = old
    p = pd.concat(out, ignore_index=True)
    fut = y.set_index(["code", "year"])["roe"].clip(*history.ROE_CLIP)
    for k in range(1, 11):
        p[f"roe_{k}"] = fut.reindex(pd.MultiIndex.from_arrays([p["code"], p["year"] + k])).to_numpy()
    p["next3"] = p[["roe_1", "roe_2", "roe_3"]].mean(axis=1, skipna=False)
    return p


def forecast_errors(p: pd.DataFrame) -> pd.Series:
    """Mean absolute error of each predictor of the next 3 years' average ROE (rows with all three)."""
    ok = p.dropna(subset=["next3", "roe_norm", "roe_now", "roe_hist"])
    return pd.Series({c: (ok[c] - ok["next3"]).abs().mean() for c in ("roe_now", "roe_hist", "roe_norm")} | {"n": len(ok)})


def persistence(p: pd.DataFrame, ks=range(1, 11)) -> pd.DataFrame:
    """Slope of (ROE in k years − that year's market median) on (normal ROE − the market median now):
    the share of an excess ROE still there k years later."""
    rows = []
    med = p.groupby("year")["roe_now"].median()
    for k in ks:
        d = p.dropna(subset=[f"roe_{k}", "roe_norm"])
        if len(d) < 100:
            continue
        x = wins(d["roe_norm"] - d["year"].map(med))
        fut_med = d.groupby("year")[f"roe_{k}"].transform("median")
        yv = wins(d[f"roe_{k}"] - fut_med)
        rows.append({"k": k, "n": len(d), "slope": (x * yv).sum() / (x * x).sum()})
    return pd.DataFrame(rows, columns=["k", "n", "slope"]).set_index("k")


def wins(x: pd.Series, q: float = 0.02) -> pd.Series:
    """Clipped at the 2nd and 98th percentile: a few ROEs on tiny books would set the slope."""
    lo, hi = x.quantile([q, 1 - q])
    return x.clip(lo, hi)


def current_p(e: pd.DataFrame, split_avail: str = "2024-01-01") -> pd.DataFrame:
    """v2's probability as it is today (regime.probability without consensus evidence): the in-sample base
    rate by steady / cyclical history, ±0.5 in log-odds for the stock's own earlier episode; scored
    out-of-sample, with its calibration by fifth."""
    ins, oos = e[e["outcome_avail"] < split_avail], e[e["outcome_avail"] >= split_avail]
    rates = ins.groupby("cyclical")["kept"].mean()
    z = np.log(oos["cyclical"].map(rates) / (1 - oos["cyclical"].map(rates)))
    z = z + np.where(oos["own_prev"].eq(1), 0.5, np.where(oos["own_prev"].eq(0), -0.5, 0))
    p = (1 / (1 + np.exp(-z))).clip(0.05, 0.95).to_numpy()
    cal = pd.DataFrame({"p": p, "y": oos["kept"].to_numpy()})
    cal["bin"] = pd.qcut(cal["p"], 4, duplicates="drop") if len(cal) >= 20 else "all"
    table = cal.groupby("bin", observed=True).agg(predicted=("p", "mean"), realized=("y", "mean"), n=("y", "size"))
    return pd.DataFrame([{"model": "v2 today (history group ± own boom)"} | score(p, oos["kept"].to_numpy())]).set_index("model"), table


def episode_persistence(y: pd.DataFrame, e: pd.DataFrame) -> pd.DataFrame:
    """For upward breaks: the share of the new excess ROE (over the market median ROE of the year) still
    there k years later, for all breaks, those that kept half after 3 years, and new ROE ≥ 40% (MU-type)."""
    med = y.groupby("year")["roe"].median()
    roe = y.set_index(["code", "year"])["roe"].clip(-0.5, 1.0)
    up = e[e["dir"] == "up"].copy()
    rows = []
    for k in range(1, 8):
        fut = roe.reindex(pd.MultiIndex.from_arrays([up["code"], up["year"] + k])).to_numpy()
        x = up["roe"] - up["year"].map(med)
        yk = wins(pd.Series(fut, up.index) - (up["year"] + k).map(med))
        for label, sel in (("all up-breaks", x.notna()), ("kept after 3 years", up["kept"] == 1),
                           ("new ROE ≥ 40%", up["roe"] >= 0.4)):
            ok = sel & yk.notna() & x.notna() & (x > 0)
            if ok.sum() >= 20:
                rows.append({"k": k, "group": label, "n": int(ok.sum()), "share": (yk[ok] * x[ok]).sum() / (x[ok] ** 2).sum()})
    return pd.DataFrame(rows).pivot(index="group", columns="k", values="share")


VOL_BANDS = [(0.3, 0.7), (0.1, 0.5), (0.2, 0.6), (0.5, 0.7), (0.3, 1.0), (0.0, 0.3)]
CYCLES = [(1.0, 0.0, 0.3, 0.6), (1.0, 0.0, 0.5, 0.8), (0.7, 0.0, 0.2, 0.4), (1.0, 0.3, 0.6, 0.8), (0.5, 0.0, 0.2, 0.3),
          (1.0, 1.0, 1.0, 1.0)]


def normal_grid(y: pd.DataFrame, first: int, split: int, last: int) -> pd.DataFrame:
    """Mean absolute error of v2's normal ROE as a forecast of the next 3 years' average ROE, for each
    volatility band and cycle-factor set: in-sample fiscal years first..split (outcomes known by 2023),
    out-of-sample split+1..last; today's ROE and the 10-year mean as the benchmarks."""
    rows = []
    for vb in VOL_BANDS:
        for cy in CYCLES:
            p = asof_panel(y, first, last, cycle=cy, vol_band=vb)
            ins, oos = forecast_errors(p[p["year"] <= split]), forecast_errors(p[p["year"] > split])
            rows.append({"vol_band": vb, "cycle": cy, "in": ins["roe_norm"], "out": oos["roe_norm"],
                         "in today": ins["roe_now"], "out today": oos["roe_now"], "in hist": ins["roe_hist"],
                         "out hist": oos["roe_hist"], "n in": ins["n"], "n out": oos["n"]})
    return pd.DataFrame(rows)


def evidence_one_by_one(e: pd.DataFrame, split_avail: str = "2024-01-01") -> pd.DataFrame:
    """Each piece of evidence alone (logistic with an intercept), fitted in-sample: its coefficient per sd
    and the out-of-sample log loss against the plain base rate (only evidence that beats it keeps a weight)."""
    ins = (e["outcome_avail"] < split_avail).to_numpy()
    y = e["kept"].to_numpy()
    base = score(np.full((~ins).sum(), y[ins].mean()), y[~ins])["logloss"]
    rows = []
    for name, f in EVIDENCE.items():
        x = f(e).astype(float)
        mu, sd = x[ins].mean(), x[ins].std() or 1.0
        z = ((x - mu) / sd).fillna(0).to_numpy()[:, None]
        b = logit_fit(z[ins], y[ins])
        ll = score(logit_predict(b, z[~ins]), y[~ins])["logloss"]
        rows.append({"evidence": name, "coef per sd": b[1], "out logloss": ll, "base logloss": base, "helps": ll < base})
    return pd.DataFrame(rows).set_index("evidence")
