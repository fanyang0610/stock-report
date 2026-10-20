"""Picking by funnel and score (Phase 13, PLAN.md Method 17) against your 6-month target: a buy beats its market's index
(US S&P 500, CN CSI 300, HK Hang Seng; stock returns include dividends, the indexes don't) over 6 months without a
blow-up (25%+ below its start at any month-end within the 6 months); sells trail the index. In-sample from v3's first
valued month to 2023-12, out of sample 2024-01..2026-03 (the last start with 6 months of prices); each period run once.
Rates come with 5-95% ranges from a block bootstrap over dates (6-month blocks, as the windows overlap).

  uv run python -m backtest.funnel checks cn|us|hk   # the bar, each input alone, confidence, overlaps, blow-up signs, biases
  uv run python -m backtest.funnel score cn|us|hk    # the registered funnel and weightings, chosen in-sample, checked out of sample
"""

import sys
import warnings
import numpy as np
import pandas as pd

from backtest import panel, run

BLOW = -0.25
FIFTH = 0.2
COST = {"us": 0.002, "cn": 0.003, "hk": 0.006}  # assumed round trip incl. spread (CN stamp duty 0.05%, HK 0.1% each side)
PERIODS = {"2019-20": ("2019", "2020-12-31"), "2021-22": ("2021", "2022-12-31"), "2023": ("2023", "2023-12-31"),
           "2024-26": ("2024", "2026-12-31")}
# input -> (column, sign): higher sign × value is better
INPUTS = {"valuation": ("v3_upside", 1), "trend 6m": ("mom_6", 1), "quality": ("z_quality", 1), "health": ("v3_health", 1),
          "business": ("business", 1), "confidence": ("conf", 1), "volatility": ("vol_1y", -1), "debt": ("debt_nf", -1)}
SIGNS = ["lvol", "loss", "mom6", "heat"]  # blow-up model: log volatility, a loss, 6m trend, CN heat (debt preceded no falls)
# registered 2026-10-20 (PLAN.md Method 17): the inputs whose top fifth beat the index without a blow-up more often in-sample
SCORE = {"us": ["valuation", "trend 6m"], "cn": ["valuation", "trend 6m", "business", "volatility"],
         "hk": ["valuation", "trend 6m", "volatility"]}
BUY_N = {"us": 300, "cn": 300, "hk": 200}  # config [shadow] buy_largest_n (US: home listings)
EXTRA = ["vol_1y", "debt_ratio", "np_ttm"]


def load(market: str) -> pd.DataFrame:
    """The saved v3 frame (backtest.sense build) from v3's first valued month, with volatility, debt, losses, the past
    6-month return and the targets: beat (6-month return over the index's), blow (worst month-end ≤ −25%)."""
    warnings.simplefilter("ignore")
    f = pd.read_pickle(panel.BT / f"v3_{market}_final.pkl")
    f = f[f["date"] >= f.loc[f["v3_valued"] == True, "date"].min()].copy()  # noqa: E712
    snaps = run.load(market)
    ex = pd.concat([d["snap"].reindex(columns=EXTRA).assign(date=m) for m, d in snaps.items()]).rename_axis("code").reset_index()
    f = f.merge(ex, on=["date", "code"], how="left").merge(past_6m(market, f), on=["date", "code"], how="left")
    f["conf"] = f["v3_confidence"].map({"高": 2, "中": 1, "低": 0})
    v = f["v3_valued"] == True  # noqa: E712
    # business quality and health as one input: health without its momentum vote (the trend input has the price)
    f["business"] = (pct(f[v], "z_quality", 1) + pct(f[v].assign(h=f["v3_health"] - f["v3_vote_momentum"]), "h", 1)) / 2
    f["debt_nf"] = f["debt_ratio"].where(~f["financial"].astype(bool))
    f["beat"], f["blow"], f["ex6"] = f["ret_6m"] > f["idx_6m"], f["worst_6m"] <= BLOW, f["ret_6m"] - f["idx_6m"]
    f["win"] = f["beat"] & ~f["blow"]  # your target in one: beat the index and no blow-up
    f["period"] = np.select([f["date"].between(*p) for p in PERIODS.values()], list(PERIODS), "")
    return f[f["ret_6m"].notna()].reset_index(drop=True)


def past_6m(market: str, f: pd.DataFrame) -> pd.DataFrame:
    """The 6-month price trend: the total return over the 6 months up to each date."""
    rows = []
    if market == "cn":
        px = panel.CNPrices()
        for d, g in f.groupby("date"):
            cols = g["code"].map(px.col)
            t, t0 = px.at(d), px.at(d, 182)
            ok = cols.notna().to_numpy()
            idx = np.nan_to_num(cols.to_numpy(float), nan=0).astype(int)
            rows.append(pd.DataFrame({"date": d, "code": g["code"].to_numpy(),
                                      "mom_6": np.where(ok, px.level[t, idx] / px.level[t0, idx] - 1, np.nan)}))
    else:
        mon = panel.Monthly(market)
        for d, g in f.groupby("date"):
            i = mon.ret.index.get_loc(d)
            r = (1 + mon.ret.iloc[i - 5: i + 1].reindex(columns=list(g["code"]))).prod(min_count=6) - 1
            rows.append(pd.DataFrame({"date": d, "code": g["code"].to_numpy(), "mom_6": r.to_numpy()}))
    return pd.concat(rows)


# ---------------------------------------------------------------- rates with ranges

def rate(g: pd.DataFrame, col: str, seed: int = 0, reps: int = 1000, block: int = 6) -> tuple[float, float, float]:
    """Share of rows with `col` true, and its 5-95% range from a moving-block bootstrap over dates."""
    by = g.groupby("date")[col].agg(["sum", "count"])
    if by["count"].sum() == 0:
        return np.nan, np.nan, np.nan
    s, n, k = by["sum"].to_numpy(float), by["count"].to_numpy(float), len(by)
    rng, b = np.random.default_rng(seed), min(block, k)
    starts = rng.integers(0, k - b + 1, size=(reps, -(-k // b)))
    pick = (starts[:, :, None] + np.arange(b)).reshape(reps, -1)[:, :k]
    boot = s[pick].sum(axis=1) / np.maximum(n[pick].sum(axis=1), 1)
    return s.sum() / n.sum(), *np.percentile(boot, [5, 95])


def fmt(x: tuple) -> str:
    return "n/a" if np.isnan(x[0]) else f"{x[0]:.1%} ({x[1]:.0%}-{x[2]:.0%})"


def summary(groups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per group and sample: beat the index, blow-ups, both (your target), mean 6-month return over the index, n."""
    rows = {}
    for name, g in groups.items():
        for s in ("in", "out"):
            x = g[g["sample"] == s]
            rows[(name, s)] = {"beat index": fmt(rate(x, "beat")), "blow-ups": fmt(rate(x, "blow")),
                               "beat, no blow-up": fmt(rate(x, "win")), "mean vs index": f"{x['ex6'].mean():+.1%}", "n": len(x)}
    return pd.DataFrame(rows).T


def bar(f: pd.DataFrame) -> pd.DataFrame:
    return summary({"all stocks": f, "today's v3 buys": f[f["v3_bucket"] == "buy"], "v1 buys": f[f["v1_bucket"] == "buy"],
                    "today's v3 sells": f[f["v3_bucket"] == "sell"]})


# ---------------------------------------------------------------- checks before the score

def pct(f: pd.DataFrame, col: str, sign: int) -> pd.Series:
    """Percentile within the date (valued stocks), better = higher."""
    return f.groupby("date")[col].rank(pct=True, ascending=sign > 0)


def alone(f: pd.DataFrame) -> pd.DataFrame:
    """Each input on its own (valued stocks): its top fifth against its bottom fifth, per sample: beat the index, blow-ups,
    mean vs index, and the per-date rank correlation with the 6-month return over the index."""
    v, rows = f[f["v3_valued"] == True], {}  # noqa: E712
    for name, (col, sign) in INPUTS.items():
        p = pct(v, col, sign)
        for s in ("in", "out"):
            x, ps = v[v["sample"] == s], p[v["sample"] == s]
            top, bot = x[ps >= 1 - FIFTH], x[ps <= FIFTH]
            ic = x.dropna(subset=[col]).groupby("date").apply(lambda d: d[col].rank().corr(d["ex6"].rank()) * sign).mean()
            rows[(name, s)] = {"top win": top["win"].mean(), "bottom win": bot["win"].mean(),
                               "top beat": top["beat"].mean(), "bottom beat": bot["beat"].mean(), "top blow": top["blow"].mean(),
                               "bottom blow": bot["blow"].mean(), "top − bottom vs index": top["ex6"].mean() - bot["ex6"].mean(),
                               "rank IC": ic, "has data": x[col].notna().mean()}
    return pd.DataFrame(rows).T


def calibration(f: pd.DataFrame) -> pd.DataFrame:
    """Confidence: within each level, does v3's gap rank the 6-month return over the index (rank IC), and do its cheapest
    fifth beat the index more often than its dearest fifth? 高 should beat 低 for confidence to scale the valuation."""
    v, rows = f[f["v3_valued"] == True], {}  # noqa: E712
    for s in ("in", "out"):
        for lvl in ("高", "中", "低"):
            x = v[(v["sample"] == s) & (v["v3_confidence"] == lvl)]
            p = x.groupby("date")["v3_upside"].rank(pct=True)
            ic = x.groupby("date").apply(lambda d: d["v3_upside"].rank().corr(d["ex6"].rank()) if len(d) >= 10 else np.nan)
            rows[(s, lvl)] = {"stocks per date": len(x) / max(x["date"].nunique(), 1), "rank IC": ic.mean(),
                              "cheap fifth beat": x.loc[p >= 1 - FIFTH, "beat"].mean(), "dear fifth beat": x.loc[p <= FIFTH, "beat"].mean(),
                              "cheap fifth blow": x.loc[p >= 1 - FIFTH, "blow"].mean(), "all beat": x["beat"].mean()}
    return pd.DataFrame(rows).T


def overlaps(f: pd.DataFrame) -> pd.DataFrame:
    """Mean per-date rank correlation between the inputs (signed so higher is better), valued stocks, in-sample."""
    v = f[(f["v3_valued"] == True) & (f["sample"] == "in")]  # noqa: E712
    cols = {k: c for k, (c, _) in INPUTS.items()}
    sign = {k: s for k, (_, s) in INPUTS.items()}
    mats = [d[list(cols.values())].rank().corr().to_numpy() for _, d in v.groupby("date")]
    m = pd.DataFrame(np.nanmean(mats, axis=0), index=list(cols), columns=list(cols))
    return m * np.outer([sign[k] for k in cols], [sign[k] for k in cols])


def features(f: pd.DataFrame, market: str) -> pd.DataFrame:
    """The blow-up signs as model inputs (financials' debt at the non-financial median; CN heat = limit-up days)."""
    x = pd.DataFrame({"lvol": np.log(f["vol_1y"].clip(0.05, 3)), "debt": f["debt_nf"].fillna(f["debt_nf"].median()),
                      "loss": (f["np_ttm"] <= 0).astype(float), "mom6": f["mom_6"].clip(-0.9, 3)}, index=f.index)
    x["heat"] = f["limit_ups"].fillna(0).clip(0, 5) if market == "cn" and "limit_ups" in f else 0.0
    return x


def logit(x: np.ndarray, y: np.ndarray, iters: int = 50) -> np.ndarray:
    """Logistic regression by Newton steps (intercept first)."""
    X, b = np.column_stack([np.ones(len(x)), x]), np.zeros(x.shape[1] + 1)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ b))
        step = np.linalg.solve(X.T @ (X * (p * (1 - p))[:, None]) + 1e-6 * np.eye(len(b)), X.T @ (y - p))
        b += step
        if np.abs(step).max() < 1e-8:
            break
    return b


def blowup_model(f: pd.DataFrame, market: str) -> tuple[pd.Series, pd.Series, float]:
    """In-sample fit of the blow-up chance on the signs (all stocks with the signs), the chance for every row, and the
    in-sample market rate (all stocks)."""
    x = features(f, market)
    use = [c for c in SIGNS if x[c].std() > 0]
    fit = (f["sample"] == "in") & x[use].notna().all(axis=1)
    b = logit(x.loc[fit, use].to_numpy(float), f.loc[fit, "blow"].to_numpy(float))
    p = 1 / (1 + np.exp(-(b[0] + x[use].to_numpy(float) @ b[1:])))
    return pd.Series(b, ["const"] + use), pd.Series(p, f.index), f.loc[f["sample"] == "in", "blow"].mean()


def signs(f: pd.DataFrame, market: str) -> pd.DataFrame:
    """Which observable signs preceded blow-ups: the blow-up rate with each sign against the market's (all stocks)."""
    x = features(f, market)
    v = f["v3_valued"] == True  # noqa: E712
    marks = {"volatility top fifth": pct(f, "vol_1y", 1) >= 1 - FIFTH, "debt top fifth (non-fin.)": pct(f, "debt_nf", 1) >= 1 - FIFTH,
             "a loss (12 months)": x["loss"] == 1, "6m trend bottom fifth": pct(f, "mom_6", 1) <= FIFTH,
             "health ≤ −1": f["v3_health"] <= -1, "trend 恶化": f["v3_trend"] == -1, "smallest fifth": pct(f, "mcap", 1) <= FIFTH,
             "v3 gap beyond ±100%": v & (f["v3_upside"].abs() > 1), "P/B over 4": f["by"].between(0, 0.25, inclusive="neither"),
             "not valued by v3": ~v}
    if market == "cn":
        marks["2+ limit-ups in 3 months"] = f["limit_ups"] >= 2
    rows = {}
    for name, mk in marks.items():
        for s in ("in", "out"):
            part = f["sample"] == s
            rows[(name, s)] = {"share of stocks": mk[part].mean(), "blow-up rate": f.loc[part & mk, "blow"].mean(),
                               "market's": f.loc[part, "blow"].mean(), "× market": f.loc[part & mk, "blow"].mean() / f.loc[part, "blow"].mean(),
                               "beat index": f.loc[part & mk, "beat"].mean()}
    return pd.DataFrame(rows).T


def biases(f: pd.DataFrame, market: str) -> list[str]:
    """Trading costs and turnover of today's v3 buys; how many stocks left the price table within their 6 months."""
    out, buys = [], f[f["v3_bucket"] == "buy"]
    for s in ("in", "out"):
        b = buys[buys["sample"] == s]
        after = (b["ret_6m"] - COST[market] > b["idx_6m"]).mean()
        out.append(f"{s}: today's v3 buys beat the index {b['beat'].mean():.1%}, after a {COST[market]:.1%} round trip {after:.1%}; "
                   f"monthly turnover {turnover(b):.0%} of the list")
    return out


def turnover(picks: pd.DataFrame) -> float:
    sets = picks.groupby("date")["code"].apply(set).sort_index()
    return np.mean([len(b - a) / max(len(b), 1) for a, b in zip(sets.iloc[:-1], sets.iloc[1:])]) if len(sets) > 1 else np.nan


def checks(market: str) -> None:
    f = load(market)
    print(f"\n==== {market.upper()} Method 17 checks: {f.groupby('sample')['date'].nunique().to_dict()} dates")
    print("\n-- the bar (6 months)\n" + bar(f).to_string())
    print("\n-- each input alone (valued stocks; top vs bottom fifth)\n" + alone(f).round(3).to_string())
    print("\n-- confidence calibrated\n" + calibration(f).round(3).to_string())
    print("\n-- overlaps (in-sample mean rank correlation)\n" + overlaps(f).round(2).to_string())
    print("\n-- blow-up signs\n" + signs(f, market).round(3).to_string())
    b, p, base = blowup_model(f, market)
    cut = p > 2 * base
    print(f"\n-- blow-up model (in-sample fit): {b.round(3).to_dict()}; market rate in-sample {base:.1%}")
    for s in ("in", "out"):
        part = f["sample"] == s
        print(f"  {s}: chance over 2× the market's: {cut[part].mean():.1%} of stocks, their blow-ups {f.loc[part & cut, 'blow'].mean():.1%} "
              f"against {f.loc[part & ~cut, 'blow'].mean():.1%} for the rest; beat index {f.loc[part & cut, 'beat'].mean():.1%} vs "
              f"{f.loc[part & ~cut, 'beat'].mean():.1%}")
    print("\n-- costs and turnover\n" + "\n".join(biases(f, market)))


# ---------------------------------------------------------------- the score (run once)

def weightings(market: str) -> dict[str, dict[str, float]]:
    ins = SCORE[market]
    out = {"equal": dict.fromkeys(ins, 1.0), "valuation-led": {k: 2.0 if k == "valuation" else 1.0 for k in ins}}
    if "volatility" in ins:
        out["risk-led"] = {k: 2.0 if k == "volatility" else 1.0 for k in ins}
    return out


def score(f: pd.DataFrame, w: dict[str, float]) -> pd.Series:
    """The weighted mean of the inputs' percentiles within the date (valued stocks; a missing input counts as the middle)."""
    v = f["v3_valued"] == True  # noqa: E712
    parts = [pct(f[v], INPUTS[k][0], INPUTS[k][1]).fillna(0.5) * x for k, x in w.items()]
    return (sum(parts) / sum(w.values())).reindex(f.index)


def funnel(f: pd.DataFrame, market: str, cut: pd.Series) -> pd.Series:
    """Stocks a buy may come from: valued, investable (the buy universe), blow-up chance under twice the market's, the
    quality screen."""
    home = f["country"].fillna("United States") == "United States" if market == "us" else True
    return (f["v3_valued"] == True) & (f["mcap_rank"] <= BUY_N[market]) & home & ~cut & (f["v3_screen_ok"] == True)  # noqa: E712


def lists(f: pd.DataFrame, s: pd.Series, field: pd.Series, n: int = 5, cap: int = 2) -> pd.Series:
    """Per date: buys = the n highest scores in the field, sells = the n lowest among the 400 largest valued; at most cap
    per industry."""
    out = pd.Series(None, f.index, dtype=object)
    sellable = (f["v3_valued"] == True) & (f["mcap_rank"] <= 400)  # noqa: E712
    for _, g in f.groupby("date"):
        for bucket, mask, asc in (("buy", field, False), ("sell", sellable, True)):
            taken, per = [], {}
            for i in s[g.index][mask[g.index]].dropna().sort_values(ascending=asc).index:
                if per.get(f.at[i, "industry"], 0) < cap:
                    taken.append(i)
                    per[f.at[i, "industry"]] = per.get(f.at[i, "industry"], 0) + 1
                if len(taken) == n:
                    break
            out[taken] = bucket
    return out


def fifths(f: pd.DataFrame, s: pd.Series, mask: pd.Series) -> tuple[pd.Series, pd.Series]:
    p = s[mask].groupby(f.loc[mask, "date"]).rank(pct=True).reindex(f.index)
    return p >= 1 - FIFTH, p <= FIFTH


def run_score(market: str) -> None:
    f = load(market)
    _, chance, base = blowup_model(f, market)
    cut = chance > 2 * base
    field = funnel(f, market, cut)
    valued = f["v3_valued"] == True  # noqa: E712
    print(f"\n==== {market.upper()} Method 17 score (run once): inputs {SCORE[market]}; blow-up cut {cut[valued].mean():.1%} of "
          f"valued stocks; the funnel leaves {field.groupby(f['date']).sum().mean():.0f} a date")
    rows, scores = {}, {}
    for name, w in weightings(market).items():
        s = scores[name] = score(f, w)
        top, _ = fifths(f, s, field)
        b = lists(f, s, field)
        for smp in ("in", "out"):
            part = f["sample"] == smp
            rows[(name, smp)] = {"top fifth of the field: beat, no blow-up": f.loc[part & top, "win"].mean(),
                                 "5-name buys: beat": f.loc[part & (b == "buy"), "beat"].mean(),
                                 "5-name buys: blow-ups": f.loc[part & (b == "buy"), "blow"].mean()}
    t = pd.DataFrame(rows).T
    print("\n-- weightings (chosen by the in-sample top fifth; the 5-name lists are shown, not used)\n" + t.round(3).to_string())
    ins = t.xs("in", level=1)["top fifth of the field: beat, no blow-up"]
    best = ins.idxmax()
    chosen = "equal" if ins[best] - ins["equal"] <= 0.005 else best
    print(f"chosen in-sample: {chosen}")
    s = scores[chosen]
    b = lists(f, s, field)
    groups = {"all stocks": f, "today's v3 buys": f[f["v3_bucket"] == "buy"], f"buys ({chosen})": f[b == "buy"],
              "today's v3 sells": f[f["v3_bucket"] == "sell"], f"sells ({chosen})": f[b == "sell"]}
    print("\n-- the lists, 6 months\n" + summary(groups).to_string())
    top, bot = fifths(f, s, valued)
    print("\n-- all valued stocks, top vs bottom fifth by score: mean 6-month return over the index; blow-ups")
    sub = {}
    for key, part in [(("sample", x), f["sample"] == x) for x in ("in", "out")] + [(("period", p), f["period"] == p) for p in PERIODS]:
        sub[key] = {"top vs index": f.loc[part & top, "ex6"].mean(), "bottom vs index": f.loc[part & bot, "ex6"].mean(),
                    "top blow": f.loc[part & top, "blow"].mean(), "bottom blow": f.loc[part & bot, "blow"].mean(),
                    "top beat": f.loc[part & top, "beat"].mean(), "bottom beat": f.loc[part & bot, "beat"].mean()}
    sub = pd.DataFrame(sub).T
    sub["holds"] = (sub["top vs index"] > sub["bottom vs index"]) & (sub["top blow"] < sub["bottom blow"])
    print(sub.round(3).to_string())
    side = {}
    for h in ("3m", "12m"):
        for smp in ("in", "out"):
            x = f[(b == "buy") & (f["sample"] == smp)].dropna(subset=[f"ret_{h}"])
            y = f[(f["v3_bucket"] == "buy") & (f["sample"] == smp)].dropna(subset=[f"ret_{h}"])
            side[(h, smp)] = {"buys beat index": (x[f"ret_{h}"] > x[f"idx_{h}"]).mean(),
                              "today's v3 buys": (y[f"ret_{h}"] > y[f"idx_{h}"]).mean()}
    print("\n-- side checks (never used to choose)\n" + pd.DataFrame(side).T.round(3).to_string())
    buys = f[b == "buy"]
    for smp in ("in", "out"):
        x = buys[buys["sample"] == smp]
        print(f"{smp}: after a {COST[market]:.1%} round trip the buys beat the index {(x['ret_6m'] - COST[market] > x['idx_6m']).mean():.1%}; "
              f"monthly turnover {turnover(x):.0%}; gaps beyond +100% {(x['v3_upside'] > 1).mean():.0%} of buys")
    verdict(f, b, sub, market)
    f.assign(m17_score=s, m17_bucket=b, m17_cut=cut, m17_chance=chance).to_pickle(panel.BT / f"m17_{market}.pkl")


def verdict(f: pd.DataFrame, b: pd.Series, sub: pd.DataFrame, market: str) -> None:
    """The registered pass bar, item by item."""
    r = {}
    for smp in ("in", "out"):
        part = f["sample"] == smp
        r[smp] = {"beat": f.loc[part & (b == "buy"), "beat"].mean(), "blow": f.loc[part & (b == "buy"), "blow"].mean(),
                  "v3 beat": f.loc[part & (f["v3_bucket"] == "buy"), "beat"].mean(),
                  "v3 blow": f.loc[part & (f["v3_bucket"] == "buy"), "blow"].mean(), "market blow": f.loc[part, "blow"].mean()}
    o, i = r["out"], r["in"]
    items = {"out: buys beat the index ≥ 55%": o["beat"] >= 0.55,
             "out: blow-ups ≤ half the market's": o["blow"] <= o["market blow"] / 2,
             "out: ≥ today's v3 buys on both": (o["beat"] >= o["v3 beat"]) & (o["blow"] <= o["v3 blow"]),
             "in: same direction": (i["beat"] > 0.5) & (i["blow"] < i["market blow"]) & (i["beat"] >= i["v3 beat"]) & (i["blow"] <= i["v3 blow"]),
             "top fifth beats bottom fifth, both samples": bool(sub.loc[("sample", "in"), "holds"] and sub.loc[("sample", "out"), "holds"]),
             "holds in 3 of 4 sub-periods": int(sub.xs("period", level=0)["holds"].sum()) >= 3}
    print(f"\n-- pass bar ({market.upper()}): " + "; ".join(f"{k}: {'pass' if v else 'FAIL'}" for k, v in items.items()))
    print(f"   numbers: out {o['beat']:.1%} / {o['blow']:.1%} (today's v3 {o['v3 beat']:.1%} / {o['v3 blow']:.1%}, market blow-ups "
          f"{o['market blow']:.1%}); in {i['beat']:.1%} / {i['blow']:.1%} (today's v3 {i['v3 beat']:.1%} / {i['v3 blow']:.1%}, market "
          f"{i['market blow']:.1%}); market passes: {all(items.values())}")


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    {"checks": checks, "score": run_score}[sys.argv[1]](sys.argv[2])
