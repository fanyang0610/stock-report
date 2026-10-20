"""Valuation v3 backtest (Phase 13, PLAN.md item 13): v3 without consensus (the company's own trend) on every month
end of the cached point-in-time snapshots (backtest/run.py), base rates from what was public that day, against
v1 and the plain earnings- and book-yield rankings. Parameters are chosen in-sample (month ends to 2023-12) and
checked out of sample (2024-01..2026-09). The trend-first lists (trend.py, shadow.buckets) re-bucket the saved
frame, so their variants cost seconds.

  uv run python -m backtest.v3 grid|lambda|country|fixes|industry cn|us|hk  # valuation grids -> data/backtest/v3_<grid>_<market>.csv
  uv run python -m backtest.v3 compare            # v1, v3 (config.toml), E/P, B/P -> data/backtest/v3_results.md (+ frames)
  uv run python -m backtest.v3 map cn|us|hk       # trend × valuation map variants on the saved frame -> v3_map_<market>.csv
  uv run python -m backtest.v3 persistence        # base rates by business trend band (panel study) -> v3_persistence.md
  uv run python -m backtest.v3 outliers           # outlier verdicts and the returns after them -> v3_outliers.md
  uv run python -m backtest.v3 cn                 # A-share sentiment signals (limit-up heat, turnover, MAX, 业绩预告) -> v3_cn_signals.md
"""

import sys
import time
import warnings
from contextlib import contextmanager

import numpy as np
import pandas as pd

from backtest import panel, run
from stockreport import baserates as br, history, outliers, shadow, signal, trend, v3

MARKETS = ("cn", "us", "hk")
V1_COLS = ["upside", "z_momentum", "z_quality", "quality_pct", "mom_12_1", "np_growth", "eps_ttm", "mcap_rank",
           "industry", "financial", "price", "ey", "by", "mcap", "country"]
V3_COLS = ["upside", "v_mid", "v_low", "v_high", "bucket", "confidence", "implied_label", "valued", "light", "d50", "level",
           "r", "irr", "screen_ok", "t0", "g", "trend", "trend_score", "verdict", "verdict_why"] + [
           f"vote_{k}" for k in trend.TEXT]
LAMBDA_GRID = {"industry premium": [("v3__LAMBDA", x) for x in (0.0, 0.25, 0.5, 0.75, 1.0)]}
COUNTRY_GRID = {"country premium": [("v3__COUNTRY_LAMBDA", x) for x in (0.0, 0.5, 1.0)]}
FIX_GRID = {"industry checks": [("br__DRIFT", False), ("br__MIN_TAIL", 100), ("br__MIN_TAIL", 300), ("v3__KEEP_ANALYSTS", True)]}
INDUSTRY_GRID = {"industry cells": [("br__INDUSTRY", True)]}  # CN 申万 L2 / HK level-2 base-rate cells
GRID = {
    "fade years": [("v3__FADE", x) for x in (3, 5, 10, 15)],
    "tolerance": [("br__TOL", x) for x in (0.0, 0.1, 0.25)],
    "long-run ROE": [("v3__LONG_ROE", x) for x in ("market", "r")],
}
EVIDENCE = {"all": (list(trend.TEXT), 2), "business": (list(trend.BUSINESS), 2), "price": (["momentum", "revision"], 1)}


@contextmanager
def params(**kw):
    """Temporarily set module constants, e.g. params(v3__FADE=10, br__TOL=0.25)."""
    mods, old = {"v3": v3, "br": br, "shadow": shadow, "trend": trend, "outliers": outliers}, {}
    for key, val in kw.items():
        mod, name = key.split("__")
        old[key] = getattr(mods[mod], name)
        setattr(mods[mod], name, val)
    try:
        yield
    finally:
        for key, val in old.items():
            mod, name = key.split("__")
            setattr(mods[mod], name, val)


def frame(market: str, data: dict, **kw) -> pd.DataFrame:
    """One row per date and stock: v1's and v3's signals, the trend votes and buckets, and the later returns."""
    warnings.simplefilter("ignore")
    p = br.panel(market)
    secs = br.sectors(market)
    country = panel.today_snapshot("us")["country"] if market == "us" else None  # snapshots built before Phase 9's field
    px = panel.CNPrices() if market == "cn" else None  # CN: limit-up days (speculative heat, a cell study)
    rows, started = [], time.monotonic()
    with params(outliers__LIVE=False, **kw):
        for m, d in data.items():
            s, day = d["snap"], run.day_of(market, m)
            if country is not None and "country" not in s:
                s = s.assign(country=country.reindex(s.index))
            st = br.starts(p, day.isoformat(), market)
            st.attrs["roe_long"] = v3.roe_long(p, day.isoformat(), market)
            h = d["loaded"][0] if isinstance(d["loaded"], tuple) else d["loaded"]
            h = shadow.with_trend(h, market, s.index, day.isoformat())
            v = shadow.value(s, market, day, loaded=(h, st, sector_of(s, market, secs)))
            f = s.reindex(columns=V1_COLS).join(v[V3_COLS].add_prefix("v3_")).join(d["fwd"])
            if px is not None:
                f["limit_ups"] = cn_limit_ups(px, s.index, day.isoformat())
            picks = d["picks"]["both"]
            f["v1_bucket"] = picks[picks["role"] == "pick"].set_index("code")["bucket"].reindex(f.index)
            rows.append(f.assign(date=m, market=market))
    out = pd.concat(rows).rename_axis("code").reset_index()
    out = out[out["date"] >= run.START.get(market, "")]
    out["sample"] = np.where(out["date"] <= run.IN_SAMPLE_END[: 7 if market != "cn" else 10], "in", "out")
    print(f"{market} {kw or 'config'}: {out['date'].nunique()} dates in {time.monotonic() - started:.0f}s", flush=True)
    return add_signals(signal.add_excess(out), market)


def cn_limit_ups(px, codes, day: str, days: int = 63) -> pd.Series:
    """CN speculative heat: limit-up days (≥ 9.5%, 19.5% on ChiNext / STAR) in the last 63 trading days. A sell rule
    on it (strict sells need 2+ / 3+) was tested 2026-10-20 (commit 2263b4f): in-sample buy − sell +9.2% / +8.8%
    against v2's +4.1%, out of sample −7.1% / −10.6% against +11.4%; not adopted, then removed from the app."""
    t = int(np.searchsorted(px.days, day, side="right")) - 1
    cols = pd.Index(codes).map(px.col)
    r = px.ret[max(t - days + 1, 0): t + 1][:, np.nan_to_num(cols.to_numpy(float), nan=0).astype(int)] - 1
    limit = np.where(pd.Index(codes).str[:3].isin(["300", "301", "688", "689"]), 0.195, 0.095)
    return pd.Series(np.where(cols.notna(), (r >= limit).sum(axis=0), np.nan), index=codes)


def add_signals(f: pd.DataFrame, market: str) -> pd.DataFrame:
    """The lists with v2's rules on the same values (the before)."""
    f["v3_bucket_v2"] = rebucket(f, market, shadow__MAP=False)
    return f


def rebucket(f: pd.DataFrame, market: str, evidence: str | None = None, **kw) -> pd.Series:
    """The v3 lists on a saved frame with other map settings: the class from the saved votes (`evidence` one of
    EVIDENCE), then shadow.buckets per date."""
    out = pd.Series(None, index=f.index, dtype=object)
    with params(**kw):
        for _, g in f.groupby("date"):
            v = g.set_index("code")
            v = v[[c for c in v if c.startswith("v3_")]].rename(columns=lambda c: c[3:]).join(v[V1_COLS[1:]])
            if evidence:
                use, need = EVIDENCE[evidence]
                score = v[[f"vote_{k}" for k in use]].sum(axis=1)
                v["trend"] = np.select([score >= need, score <= -need], [1, -1], 0)
            v["valued"] = v["valued"].fillna(False).astype(bool)
            v["screen_ok"] = v["screen_ok"].fillna(False).astype(bool)
            b = shadow.buckets(v, v, market)["bucket"]
            out[g.index] = b.reindex(g["code"]).to_numpy()
    return out


def sector_of(s: pd.DataFrame, market: str, secs: pd.Series) -> pd.Series:
    if market == "us":
        from stockreport.fetch import sec
        cik = sec.load_ciks().reindex(s.index)
        return cik.map(lambda c: secs.get(str(int(c)), "") if pd.notna(c) else "")
    if market == "hk":
        return shadow.parents(s, "hk")
    return secs.reindex(s.index).fillna("")


def factor_buckets(f: pd.DataFrame, col: str) -> pd.Series:
    """A plain benchmark: per date, buy = the 5 highest `col` (at most 2 per industry), sell = the 5 lowest among
    the 400 largest (as Phase 9)."""
    out = pd.Series(None, index=f.index, dtype=object)
    for _, g in f.groupby("date"):
        for bucket, part, asc in (("buy", g, False), ("sell", g[g["mcap_rank"] <= 400], True)):
            taken, per = [], {}
            for i in part[col].dropna().sort_values(ascending=asc).index:
                ind = f.at[i, "industry"]
                if per.get(ind, 0) < 2:
                    taken.append(i)
                    per[ind] = per.get(ind, 0) + 1
                if len(taken) == 5:
                    break
            out[taken] = bucket
    return out


SPEC = {"v1": ("upside", "v1_bucket"), "v3 before (v2 rules)": ("v3_upside", "v3_bucket_v2"),
        "v3 trend-first": ("v3_upside", "v3_bucket"), "E/P": ("ey", "ep_bucket"), "B/P": ("by", "bp_bucket")}


def metrics(f: pd.DataFrame, who: str = "v3 trend-first", bucket: str | None = None) -> dict:
    """Per sample: mean rank IC with 1/3/12-month returns, and buy, sell and buy − sell over 12 months against
    the equal-weight universe."""
    up, b = SPEC[who]
    bucket = bucket or b
    out = {}
    for sample in ("in", "out"):
        part = f[f["sample"] == sample]
        for h in ("1m", "3m", "12m"):
            s = signal.summarize(signal.rank_ic(part, up, f"ret_{h}"), signal.HORIZONS[h])
            out[f"{sample} ic {h}"], out[f"{sample} ic {h} t"] = s["mean"], s["t"]
        t = signal.bucket_table(part, bucket, "12m")
        for k in ("buy", "sell", "buy-sell"):
            out[f"{sample} {k} 12m"] = t.at[k, "vs_universe"] if k in t.index else np.nan
        out[f"{sample} buy-sell t"] = t.at["buy-sell", "t"] if "buy-sell" in t.index else np.nan
    return out


def beta(df: pd.DataFrame, gap: str, h: str, by: list[str] | None = None) -> pd.DataFrame:
    """β per group: the slope of the log return over the universe on the log gap log(value / price),
    pooled over dates (A2.5: E[price] = price × (V / price)^β)."""
    d = df.dropna(subset=[gap, f"ret_{h}"]).copy()
    d = d[np.isfinite(d[gap])]
    d["y"] = np.log1p(d[f"ret_{h}"]) - d.groupby("date")[f"ret_{h}"].transform(lambda r: np.log1p(r).mean())
    d["x"] = d[gap] - d.groupby("date")[gap].transform("mean")
    groups = d.groupby(by) if by else [("all", d)]
    rows = []
    for key, g in groups:
        if len(g) < 50:
            continue
        b = (g["x"] * g["y"]).sum() / (g["x"] ** 2).sum()
        rows.append({"group": key, "n": len(g), "beta": b})
    return pd.DataFrame(rows)


def grid(market: str, which: str = "grid") -> pd.DataFrame:
    panel.setup_history(market)
    data, rows = run.load(market), []
    grids = {"lambda": LAMBDA_GRID, "country": COUNTRY_GRID, "fixes": FIX_GRID, "industry": INDUSTRY_GRID}.get(which) or GRID
    for name, options in grids.items():
        for key, val in options:
            f = frame(market, data, **{key: val})
            f.to_pickle(panel.BT / f"v3_{market}_{key}_{val}.pkl") if which in ("fixes", "industry") else None
            rows.append({"param": name, "value": f"{key}={val}", "market": market} | metrics(f, "v3 before (v2 rules)")
                        | {f"map {k}": x for k, x in metrics(f).items() if "buy" in k})
            print(name, val, {k: round(x, 3) for k, x in rows[-1].items() if k.endswith(("ic 12m", "buy-sell 12m"))}, flush=True)
    out = pd.DataFrame(rows)
    out.to_csv(panel.BT / f"v3_{which}_{market}.csv", index=False)
    return out


def map_grid(market: str) -> pd.DataFrame:
    """The trend × valuation map's variants (votes counted, buys from improving only or stable too) and v2's rules,
    re-bucketed on the saved frame; the in-sample buy − sell decides (Phase 9's bar: +1 point)."""
    f = pd.read_pickle(panel.BT / f"v3_{market}.pkl")
    rows = [{"variant": "v2 rules (before)"} | metrics(f, "v3 before (v2 rules)")]
    for ev in EVIDENCE:
        for buy in ("improving", "stable"):
            f["b"] = rebucket(f, market, evidence=ev, shadow__MAP=True, shadow__BUY=buy)
            rows.append({"variant": f"map, votes {ev}, buys {buy}"} | metrics(f, bucket="b"))
            print(market, rows[-1]["variant"], {k: round(x, 3) for k, x in rows[-1].items() if "buy" in k and "t" not in k[-2:]}, flush=True)
    cells = []
    for ev, (use, need) in EVIDENCE.items():  # the ranking: upside percentile + w × the class (w = 1: class first)
        score = f[[f"v3_vote_{k}" for k in use]].sum(axis=1)
        cls = np.select([score >= need, score <= -need], [1, -1], 0)
        cells.append(cell_table(f, cls).assign(votes=ev))
        for w in (0.05, 0.1, 0.25, 0.5, 1.0):
            f["s"] = f.groupby("date")["v3_upside"].rank(pct=True) + w * cls
            ic = {s: signal.summarize(signal.rank_ic(f[f["sample"] == s], "s", "ret_12m"), 12)["mean"] for s in ("in", "out")}
            rows.append({"variant": f"ranking, votes {ev}, class weight {w}", "in ic 12m": ic["in"], "out ic 12m": ic["out"]})
    out = pd.DataFrame(rows)
    out.to_csv(panel.BT / f"v3_map_{market}.csv", index=False)
    if "limit_ups" in f:  # CN: valuation × speculative heat (2+ limit-up days in 3 months)
        cells.append(cell_table(f, np.where(f["limit_ups"] >= 2, 1, 0)).assign(votes="heat 2+"))
    pd.concat(cells).to_csv(panel.BT / f"v3_map_cells_{market}.csv")  # valuation × trend class: 12-month excess return
    return out


def cell_table(f: pd.DataFrame, cls) -> pd.DataFrame:
    """Mean 12-month excess return (per date, then over dates) and stocks per date by sample × valuation × class."""
    val = np.select([f["v3_upside"] >= 0.2, f["v3_upside"] <= -0.25], ["cheap", "expensive"], "middle")
    by = f.assign(cls=cls, val=val).dropna(subset=["ex_12m"]).groupby(["sample", "val", "cls", "date"])["ex_12m"]
    return pd.DataFrame({"ex_12m": by.mean().groupby(level=[0, 1, 2]).mean(), "per_date": by.size().groupby(level=[0, 1, 2]).mean()})


def md(df: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(["", *map(str, df.columns)]) + " |", "|" + "---|" * (len(df.columns) + 1)]
    return "\n".join(lines + ["| " + " | ".join([str(i), *map(str, row)]) + " |" for i, row in df.iterrows()])


def compare() -> None:
    """v1, v3 before (v2 rules) and trend-first, E/P and B/P per market and sample -> data/backtest/v3_results.md."""
    rows = []
    for m in MARKETS:
        panel.setup_history(m)
        f = frame(m, run.load(m))
        f["ep_bucket"], f["bp_bucket"] = factor_buckets(f, "ey"), factor_buckets(f, "by")
        f.to_pickle(panel.BT / f"v3_{m}.pkl")
        rows += [{"market": m, "method": who} | metrics(f, who) for who in SPEC]
    t = pd.DataFrame(rows)
    t.to_csv(panel.BT / "v3_metrics.csv", index=False)
    lines = ["# v3 backtest (backtest/v3.py)\n"]
    for sample in ("in", "out"):
        cols = [f"{sample} ic 1m", f"{sample} ic 3m", f"{sample} ic 12m", f"{sample} ic 12m t", f"{sample} buy 12m",
                f"{sample} sell 12m", f"{sample} buy-sell 12m", f"{sample} buy-sell t"]
        lines += [f"\n## {sample}-of-sample\n", md(t.set_index(["market", "method"])[cols].round(3))]
    (panel.BT / "v3_results.md").write_text("\n".join(lines))
    print("\n".join(lines))


def band(rev: np.ndarray, earn: np.ndarray, roe: np.ndarray) -> np.ndarray:
    """Business trend band per row (columns latest first): 2 improving (trend.py's business votes sum ≥ 2), 0
    deteriorating (≤ −2), else 1. (Splitting the base-rate cells by it was tested in-sample, 2026-10-20: CN
    0.131 / US 0.060 / HK 0.119 rank IC against 0.135 / 0.060 / 0.123 by size; not adopted, then removed.)"""
    acc = trend.accelerations(rev, earn, roe)
    s = sum(trend.vote(acc[k], trend.DEAD[k]) for k in trend.BUSINESS)
    return np.select([s >= 2, s <= -2], [2, 0], 1)


def start_bands(p: pd.DataFrame, market: str) -> np.ndarray:
    """The band of every br.starts(p, <after the panel>) row, in its order: the start year and the 3 before."""
    years = list(range(int(p["year"].min()), int(p["year"].max()) + 1))
    w = {c: p.pivot(index="code", columns="year", values=c).reindex(columns=years).to_numpy(float) for c in ("earn", "rev", "roe")}
    e, rev, roe, out = w["earn"], w["rev"], w["roe"].clip(*history.ROE_CLIP), []
    for j in range(1, len(years)):
        ok = (e[:, j] > 0) & (rev[:, j] > (br.US_MIN_REVENUE if market == "us" else 0))
        if ok.sum() >= 3:
            back = lambda m: np.column_stack([m[ok, j - i] if j >= i else np.full(ok.sum(), np.nan) for i in range(4)])
            out.append(band(back(rev), back(e), back(roe)))
    return np.concatenate(out)


def persistence() -> None:
    """Base rates by business trend band (band), per market, on every start public today: the share whose
    profit kept up 5% / 10% a year for 3 and 5 years, the median duration, and the ROE change 3 and 5 years on;
    and within growth × ROE cells (60+ starts in both bands) improving minus deteriorating."""
    lines = ["# Base rates by business trend (backtest/v3.py persistence)\n"]
    for m in MARKETS:
        p = br.panel(m)
        st, tol = br.starts(p, "9999-12-31", m), v3.per_market(br.TOL, m)
        st["tb"] = start_bands(p, m)
        rows = []
        for b, name in ((2, "improving"), (1, "stable"), (0, "deteriorating")):
            part, row = st[st["tb"] == b], {"band": name}
            row["starts"] = len(part)
            for g in (0.05, 0.10):
                S = br.extend(*br.km(np.cumsum(part[br.ECOLS].to_numpy(float), axis=1), br.track(g, tol)))
                row[f"kept {g:.0%} 3y"], row[f"kept {g:.0%} 5y"] = round(S[3], 2), round(S[5], 2)
                row[f"median years at {g:.0%}"] = round(float(np.interp(0.5, S[::-1], np.arange(len(S))[::-1])), 1)
            row["ROE start"] = round(part["q0"].median(), 3)
            row["ROE change 3y"], row["ROE change 5y"] = (round((part[f"q{k}"] - part["q0"]).median(), 3) for k in (3, 5))
            rows.append(row)
        diffs = []
        for _, cell in st.groupby(["gb", "qb"]):
            S = {}
            for b in (0, 2):
                part = cell[cell["tb"] == b]
                if len(part) >= 60:
                    S[b] = br.extend(*br.km(np.cumsum(part[br.ECOLS].to_numpy(float), axis=1), br.track(0.05, tol)))
            if len(S) == 2:
                diffs.append((len(cell), S[2][3] - S[0][3], S[2][5] - S[0][5]))
        d = np.array(diffs) if diffs else np.zeros((0, 3))
        within = (f"within {len(d)} growth × ROE cells, improving − deteriorating share kept at 5%: 3 years "
                  f"{np.average(d[:, 1], weights=d[:, 0]):+.2f}, 5 years {np.average(d[:, 2], weights=d[:, 0]):+.2f}") if len(d) else ""
        lines += [f"\n## {m.upper()} ({len(st)} starts)\n", md(pd.DataFrame(rows).set_index("band")), "", within]
    (panel.BT / "v3_persistence.md").write_text("\n".join(lines))
    print("\n".join(lines))


def outlier_study() -> None:
    """The backtest's outliers (beyond ±100% or labelled; data-error and event evidence is live only, so the
    verdicts here are 行业 / 证据支持 by the trend / 需复核), and how they did over 12 months against the universe:
    a cheap outlier that trailed the universe, or an expensive one that beat it, is one the market was right about."""
    lines = ["# Outlier verdicts in the backtest (backtest/v3.py outliers)\n"]
    for m in MARKETS:
        f = pd.read_pickle(panel.BT / f"v3_{m}.pkl")
        o = f[f["v3_verdict"].fillna("") != ""].copy()
        o["side"] = np.where((o["v3_upside"] > 1) | (o["v3_implied_label"] == "价格隐含过低"), "cheap", "expensive")
        t = o.groupby(["sample", "side", "v3_verdict"]).agg(n=("ex_12m", "count"), ex_12m=("ex_12m", "mean"))
        t["market right"] = o.assign(right=np.where(o["side"] == "cheap", o["ex_12m"] < 0, o["ex_12m"] > 0)).dropna(
            subset=["ex_12m"]).groupby(["sample", "side", "v3_verdict"])["right"].mean()
        share = len(o) / f["v3_valued"].sum()
        lines += [f"\n## {m.upper()}: {len(o)} outlier stock-dates ({share:.0%} of valued)\n", md(t.round(3))]
    (panel.BT / "v3_outliers.md").write_text("\n".join(lines))
    print("\n".join(lines))


def cn_study() -> None:
    """A-share signals on the saved CN frame (your question, 2026-10-20: CN is emotional; a-stock-data lists the
    A-share data): rank IC at 1 and 12 months of limit-up days (3 months), abnormal turnover (1-month over 12-month
    traded value; the 通达信 packages start 2021-08), the largest daily return and the daily volatility of the last
    month, the 1-month return, and the latest 业绩预告 in 90 days (+1 预增/扭亏/略增/续盈, −1 预减/首亏/续亏/略减/增亏);
    and 12-month excess returns by valuation × heat (2+ and 3+ limit-up days)."""
    warnings.simplefilter("ignore")  # empty turnover windows before the packages start
    f, px = pd.read_pickle(panel.BT / "v3_cn.pkl"), panel.CNPrices()
    fc = pd.read_csv(panel.BT / "cn_forecasts.csv.gz", dtype={"code": str}).assign(code=lambda d: d["code"].str.zfill(6))
    tone = {**dict.fromkeys(["预增", "扭亏", "略增", "续盈"], 1), **dict.fromkeys(["预减", "首亏", "续亏", "略减", "增亏"], -1)}
    rows = []
    for d, g in f.groupby("date"):
        t, cols = int(np.searchsorted(px.days, d, side="right")) - 1, g["code"].map(px.col)
        idx, ok = np.nan_to_num(cols.to_numpy(float), nan=0).astype(int), cols.notna().to_numpy()
        r, a = px.ret[t - 20: t + 1][:, idx], px.amount
        since = (pd.Timestamp(d) - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
        pre = fc[(fc["notice_date"] <= d) & (fc["notice_date"] > since)].sort_values("notice_date").groupby("code").tail(1)
        sig = {"rev1m": np.nanprod(r, axis=0) - 1, "max1m": np.nanmax(r, axis=0) - 1, "vol1m": np.nanstd(r, axis=0),
               "abturn": np.nanmean(a[t - 20: t + 1][:, idx], axis=0) / np.nanmean(a[max(t - 250, 0): t + 1][:, idx], axis=0)}
        rows.append(pd.DataFrame({k: np.where(ok, v, np.nan) for k, v in sig.items()}).assign(
            date=d, code=g["code"].to_numpy(), preann=g["code"].map(pre.set_index("code")["type"].map(tone)).fillna(0).to_numpy()))
    x = f.merge(pd.concat(rows), on=["date", "code"], how="left")
    lines = ["# A-share signals on the CN backtest frame (backtest/v3.py cn)\n", "| signal | in IC 1m (t) | in IC 12m (t) | out IC 1m (t) | out IC 12m (t) |", "|---|---|---|---|---|"]
    for c in ("limit_ups", "abturn", "max1m", "vol1m", "rev1m", "preann", "mom_12_1", "v3_upside"):
        cell = []
        for sample in ("in", "out"):
            for h in ("1m", "12m"):
                s = signal.summarize(signal.rank_ic(x[x["sample"] == sample], c, f"ret_{h}"), signal.HORIZONS[h])
                cell.append(f"{s['mean']:+.3f} ({s['t']:+.1f}, {s['n']} dates)")
        lines.append(f"| {c} | " + " | ".join(cell) + " |")
    for k in (2, 3):
        t = cell_table(x[x["v3_valued"] == True], np.where(x.loc[x["v3_valued"] == True, "limit_ups"] >= k, "hot", "calm"))
        lines += [f"\n12-month excess return, valuation × {k}+ limit-up days in 3 months (stocks per date)\n",
                  md((t["ex_12m"] * 100).round(1).astype(str).str.cat(t["per_date"].round(0).astype(int).astype(str), sep=" (").add(")").unstack("cls"))]
    (panel.BT / "v3_cn_signals.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    if sys.argv[1] in ("grid", "lambda", "country", "fixes", "industry"):
        grid(sys.argv[2], sys.argv[1])
    elif sys.argv[1] == "map":
        map_grid(sys.argv[2])
    elif sys.argv[1] == "compare":
        compare()
    elif sys.argv[1] == "persistence":
        persistence()
    elif sys.argv[1] == "outliers":
        outlier_study()
    elif sys.argv[1] == "cn":
        cn_study()
