"""Signal tracking (Phase 9, docs/BACKTEST.md): how well a valuation ranks stocks and how its buckets did
afterwards. The backtest and `track --signal` (the live snapshots, v1 and v2) use the same measures:
rank correlation of the signal with later returns per date, bucket returns against the equal-weight
universe and the index, hit rates by confidence band, and β (the share of the log gap to the value that
closed within the horizon)."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from stockreport.config import DATA

HORIZONS = {"1m": 1, "3m": 3, "12m": 12}  # months; returns run 30 / 91 / 365 days (CN, live) or whole months
MIN_STOCKS = 30


def add_excess(df: pd.DataFrame) -> pd.DataFrame:
    """ex_<h> = return minus the equal-weight average of all stocks with a return that date."""
    ex = {f"ex_{h}": df[f"ret_{h}"] - df.groupby("date")[f"ret_{h}"].transform("mean") for h in HORIZONS if f"ret_{h}" in df}
    return pd.concat([df.drop(columns=list(ex), errors="ignore"), pd.DataFrame(ex, index=df.index)], axis=1)


def rank_ic(df: pd.DataFrame, signal: str, ret: str) -> pd.Series:
    """Spearman correlation of `signal` with `ret` per date (dates with 30+ stocks having both)."""
    ok = df[[signal, ret, "date"]].dropna()
    ok = ok[ok.groupby("date")[ret].transform("size") >= MIN_STOCKS]
    ranks = ok.groupby("date")[[signal, ret]].rank()
    return ranks.groupby(ok["date"]).apply(lambda g: g[signal].corr(g[ret]))


def summarize(series: pd.Series, months: int) -> dict:
    """Mean of a per-date series with a t-statistic for overlapping horizons (n / months independent
    observations)."""
    s = series.dropna()
    if len(s) < 2:
        return {"mean": s.mean() if len(s) else np.nan, "t": np.nan, "n": len(s)}
    eff = max(len(s) / max(months, 1), 1.0)
    return {"mean": s.mean(), "t": s.mean() / (s.std(ddof=1) / np.sqrt(eff)) if s.std() > 0 else np.nan, "n": len(s)}


def bucket_table(df: pd.DataFrame, bucket: str, h: str) -> pd.DataFrame:
    """Per bucket: picks, average return against the equal-weight universe and the index, and the share
    of picks that beat the universe (for a sell, the share that did worse); plus buy minus sell."""
    rows = []
    for b, part in df.dropna(subset=[f"ex_{h}"]).groupby(bucket):
        by_date = part.groupby("date")[f"ex_{h}"].mean()
        vs_idx = (part[f"ret_{h}"] - part[f"idx_{h}"]).mean() if f"idx_{h}" in part else np.nan
        beat = (part[f"ex_{h}"] < 0) if b == "sell" else (part[f"ex_{h}"] > 0)
        rows.append({"bucket": b, "picks": len(part), "dates": part["date"].nunique(), "vs_universe": by_date.mean(),
                     "t": summarize(by_date, HORIZONS[h])["t"], "vs_index": vs_idx, "hit": beat.mean()})
    out = pd.DataFrame(rows).set_index("bucket") if rows else pd.DataFrame()
    if {"buy", "sell"} <= set(out.index):
        ex = df.dropna(subset=[f"ex_{h}"])
        spread = (ex[ex[bucket] == "buy"].groupby("date")[f"ex_{h}"].mean()
                  - ex[ex[bucket] == "sell"].groupby("date")[f"ex_{h}"].mean()).dropna()
        s = summarize(spread, HORIZONS[h])
        out.loc["buy-sell"] = {"picks": np.nan, "dates": s["n"], "vs_universe": s["mean"], "t": s["t"],
                               "vs_index": np.nan, "hit": (spread > 0).mean()}
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


# ---------------------------------------------------------------- live snapshots (`track --signal`)

def live(market: str, prices: pd.DataFrame, index: str) -> pd.DataFrame:
    """Every saved snapshot of a market with its v1 and v2 signals and the returns since (30 / 91 / 365
    days; blank until then), from the daily price table."""
    from stockreport.track import growth
    frames = []
    for path in sorted((DATA / "snapshots").glob(f"*/{market}.csv.gz")):
        s = pd.read_csv(path, dtype={"code": str}).copy()  # consolidated: the snapshot has ~165 columns
        if "v2_upside" not in s:
            continue
        frames.append(s.assign(date=path.parent.name))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).copy()
    picks = pd.read_csv(DATA / "picks.csv", dtype={"ticker": str}) if (DATA / "picks.csv").exists() else pd.DataFrame()
    if len(picks):
        p = picks[picks["market"] == market].drop_duplicates(["date", "ticker"]).set_index(["date", "ticker"])["bucket"]
        df["v1_bucket"] = p.reindex(pd.MultiIndex.from_arrays([df["date"], df["code"]])).to_numpy()
    g = growth(prices, set(df["code"]) | {index})
    days, new = g.index, {}
    for h, months in HORIZONS.items():
        ret, idx = [], []
        for d, code in zip(df["price_date"].astype(str), df["code"]):
            start = days[max(days.searchsorted(d, side="right") - 1, 0)]
            end = (date.fromisoformat(d) + timedelta(days={1: 30, 3: 91, 12: 365}[months])).isoformat()
            if end > days[-1] or code not in g:
                ret.append(np.nan), idx.append(np.nan)
                continue
            end = days[days.searchsorted(end, side="right") - 1]
            ret.append(g.at[end, code] / g.at[start, code] - 1), idx.append(g.at[end, index] / g.at[start, index] - 1)
        new[f"ret_{h}"], new[f"idx_{h}"] = ret, idx
    return add_excess(pd.concat([df, pd.DataFrame(new, index=df.index)], axis=1))


def check_events(df: pd.DataFrame) -> pd.DataFrame:
    """Checks 1-2 on every snapshot (PLAN Method 8): v1's buy and hold picks with the checks against
    without them. excluded = picked only without the checks, replacement = picked only with them; check 1
    exclusions split by whether 3+ analysts expected next year's EPS at or above the last 12 months."""
    from stockreport import pick
    rows = []
    for day, snap in df.groupby("date"):
        s = snap.set_index("code")
        on, off = (pick.pick(s, use) for use in (("c1", "c2"), ()))
        checks = pick.one_off(s[s["fv_mid"].notna()])
        for bucket in ("buy", "hold"):
            a, b = (set(p.loc[(p["role"] == "pick") & (p["bucket"] == bucket), "code"]) for p in (on, off))
            for code, role in [(c, "excluded") for c in b - a] + [(c, "replacement") for c in a - b]:
                if role == "excluded":
                    role = "excluded by check 2" if checks.at[code, "c2"] is True else (
                        "excluded by check 1, analysts ≥ trailing" if s.at[code, "analysts"] >= 3
                        and s.at[code, "eps_e2"] >= s.at[code, "eps_ttm"] else "excluded by check 1, other")
                rows.append({"date": day, "code": code, "role": role} | s.loc[code, [f"ex_{h}" for h in HORIZONS]].to_dict())
    return pd.DataFrame(rows, columns=["date", "code", "role"] + [f"ex_{h}" for h in HORIZONS])


def forecast_pieces(df: pd.DataFrame, market: str, h: str) -> list[str]:
    """The parts of v2 the backtest couldn't test (no consensus history; docs/BACKTEST.md): its value on
    consensus years 1-3 with and without the haircut (history weight ≥ 0.5 pulls consensus toward the normal
    path), analyst-confirmed regime breaks (did the ones we call cheap beat the ones we call dear?), and
    whether 4-week consensus revisions rank stocks (a candidate for the buy ranking)."""
    from stockreport import history
    out, ret, ex = [], f"ret_{h}", f"ex_{h}"
    cons = df[df["analysts"] >= 3]
    for label, part in (("haircut (history weight ≥ 0.5)", cons[cons["v2_w_hist"] >= 0.5]),
                        ("no haircut", cons[cons["v2_w_hist"] < 0.5])):
        s = summarize(rank_ic(part, "v2_upside", ret), HORIZONS[h])
        out.append(f"{h} rank IC v2 upside, 3+ analysts, {label}: {s['mean']:+.3f} ({s['n']} dates)")
    brk = df[df["v2_break_confirmed"].eq(True)].dropna(subset=[ex])
    if len(brk):
        side = np.where(brk["v2_upside"] > 0, "cheap", "dear")
        out.append(f"{h} confirmed regime breaks vs the universe: " + ", ".join(
            f"{k} {v['mean']:+.1%} ({v['count']:.0f})" for k, v in brk.groupby(side)[ex].agg(["mean", "count"]).iterrows()))
    rev = pd.concat([history.revisions(market, date.fromisoformat(d)).rename("revision").to_frame().assign(date=d)
                     for d in df["date"].unique()]).rename_axis("code").reset_index()
    if len(rev):
        s = summarize(rank_ic(df.merge(rev, on=["date", "code"]), "revision", ret), HORIZONS[h])
        out.append(f"{h} rank IC of the 4-week consensus revision: {s['mean']:+.3f} ({s['n']} dates)")
    return out


def report(market: str, df: pd.DataFrame) -> None:
    """The same tables the backtest reports, for v1 and v2, at every horizon that has returns yet, plus
    the forecast-dependent pieces the backtest couldn't test."""
    print(f"\n== {market.upper()}: {df['date'].nunique()} snapshots with v2 columns, {df['date'].min()} to {df['date'].max()}")
    ev = check_events(df) if df["ret_1m"].notna().any() else pd.DataFrame()
    for h in HORIZONS:
        if df[f"ret_{h}"].notna().sum() == 0:
            print(f"{h}: no returns yet (the first snapshot reaches {h} later)")
            continue
        for name, sig in (("v1 upside", "upside"), ("v2 upside", "v2_upside")):
            s = summarize(rank_ic(df, sig, f"ret_{h}"), HORIZONS[h])
            print(f"{h} rank IC {name}: {s['mean']:+.3f} (t {s['t']:+.1f}, {s['n']} dates)")
        for name, col in (("v1", "v1_bucket"), ("v2", "v2_bucket")):
            if col in df and df[col].notna().any():
                print(f"{h} {name} buckets:\n{bucket_table(df, col, h).round(3).to_string()}")
        if len(ev):
            t = ev.groupby("role")[f"ex_{h}"].agg(["count", "mean"]).rename(columns={"mean": "vs universe"})
            print(f"{h} checks 1-2, names they excluded vs the names that took their places:\n{t.round(3).to_string()}")
        if "v2_confidence" in df:
            buys = df[df["v2_bucket"] == "buy"]
            print(f"{h} v2 buys beating the universe by confidence: "
                  + ", ".join(f"{k} {v:.0%}" for k, v in (buys[f"ex_{h}"] > 0).groupby(buys["v2_confidence"]).mean().items()))
        print("\n".join(forecast_pieces(df, market, h)))
