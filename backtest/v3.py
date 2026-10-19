"""Valuation v3 backtest (Phase 13, PLAN.md item 13): v3 without consensus (the company's own trend) on every month
end of the cached point-in-time snapshots (backtest/run.py), base rates from what was public that day, against
v1 and the plain earnings- and book-yield rankings. Parameters are chosen in-sample (month ends to 2023-12) and
checked out of sample (2024-01..2026-09).

  uv run python -m backtest.v3 grid cn|us|hk      # one-at-a-time grids -> data/backtest/v3_grid_<market>.csv
  uv run python -m backtest.v3 lambda cn|us|hk    # the industry premium λ -> data/backtest/v3_lambda_<market>.csv
  uv run python -m backtest.v3 compare            # v1, v3 (config.toml), E/P, B/P -> data/backtest/v3_results.md
"""

import sys
import time
import warnings
from contextlib import contextmanager
from datetime import date

import numpy as np
import pandas as pd

from backtest import panel, run
from stockreport import baserates as br, shadow, signal, v3

MARKETS = ("cn", "us", "hk")
V1_COLS = ["upside", "z_momentum", "z_quality", "quality_pct", "mom_12_1", "np_growth", "eps_ttm", "mcap_rank",
           "industry", "financial", "price", "ey", "by", "mcap"]
V3_COLS = ["upside", "v_mid", "bucket", "confidence", "implied_label", "valued", "light", "d50", "level", "r", "irr"]
LAMBDA_GRID = {"industry premium": [("v3__LAMBDA", x) for x in (0.0, 0.25, 0.5, 0.75, 1.0)]}
COUNTRY_GRID = {"country premium": [("v3__COUNTRY_LAMBDA", x) for x in (0.0, 0.5, 1.0)]}
GRID = {
    "fade years": [("v3__FADE", x) for x in (3, 5, 10, 15)],
    "tolerance": [("br__TOL", x) for x in (0.0, 0.1, 0.25)],
    "long-run ROE": [("v3__LONG_ROE", x) for x in ("market", "r")],
}
HK_LAMBDA_GRID = {"industry premium": [("v3__LAMBDA", x) for x in (0.0, 0.25, 0.5, 0.75, 1.0)]}
COUNTRY_GRID = {"country premium": [("v3__COUNTRY_LAMBDA", x) for x in (0.0, 0.5, 1.0)]}
GRID = {"haircut": [("v3__HAIRCUT", x) for x in (0.0, 0.1, 0.2, 0.3)]}  # HK: survivors only (your OK)


@contextmanager
def params(**kw):
    """Temporarily set module constants, e.g. params(v3__FADE=10, br__TOL=0.25)."""
    mods, old = {"v3": v3, "br": br, "shadow": shadow}, {}
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
    """One row per date and stock: v1's and v3's signals and buckets and the later returns."""
    warnings.simplefilter("ignore")
    p = br.panel(market)
    secs = br.sectors(market)
    country = panel.today_snapshot("us")["country"] if market == "us" else None  # snapshots built before Phase 9's field
    rows, started = [], time.monotonic()
    with params(**kw):
        for m, d in data.items():
            s, day = d["snap"], run.day_of(market, m)
            if country is not None and "country" not in s:
                s = s.assign(country=country.reindex(s.index))
            st = br.starts(p, day.isoformat(), market)
            st.attrs["roe_long"] = v3.roe_long(p, day.isoformat(), market)
            h = d["loaded"][0] if isinstance(d["loaded"], tuple) else d["loaded"]
            sector = sector_of(s, market, secs)
            v = shadow.value(s, market, day, loaded=(h, st, sector))
            f = s.reindex(columns=V1_COLS).join(v[V3_COLS].add_prefix("v3_")).join(d["fwd"])
            picks = d["picks"]["both"]
            f["v1_bucket"] = picks[picks["role"] == "pick"].set_index("code")["bucket"].reindex(f.index)
            rows.append(f.assign(date=m, market=market))
    out = pd.concat(rows).rename_axis("code").reset_index()
    out = out[out["date"] >= run.START.get(market, "")]
    out["sample"] = np.where(out["date"] <= run.IN_SAMPLE_END[: 7 if market != "cn" else 10], "in", "out")
    print(f"{market} {kw or 'config'}: {out['date'].nunique()} dates in {time.monotonic() - started:.0f}s", flush=True)
    return signal.add_excess(out)


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


SPEC = {"v1": ("upside", "v1_bucket"), "v3": ("v3_upside", "v3_bucket"), "E/P": ("ey", "ep_bucket"), "B/P": ("by", "bp_bucket")}


def metrics(f: pd.DataFrame, who: str = "v3") -> dict:
    """Per sample: mean rank IC with 1/3/12-month returns, and buy, sell and buy − sell over 12 months against
    the equal-weight universe."""
    up, bucket = SPEC[who]
    out = {}
    for sample in ("in", "out"):
        part = f[f["sample"] == sample]
        for h in ("1m", "3m", "12m"):
            s = signal.summarize(signal.rank_ic(part, up, f"ret_{h}"), signal.HORIZONS[h])
            out[f"{sample} ic {h}"], out[f"{sample} ic {h} t"] = s["mean"], s["t"]
        t = signal.bucket_table(part, bucket, "12m")
        for b in ("buy", "sell", "buy-sell"):
            out[f"{sample} {b} 12m"] = t.at[b, "vs_universe"] if b in t.index else np.nan
        out[f"{sample} buy-sell t"] = t.at["buy-sell", "t"] if "buy-sell" in t.index else np.nan
    return out


def grid(market: str, which: str = "grid") -> pd.DataFrame:
    panel.setup_history(market)
    data, rows = run.load(market), []
    grids = {"lambda": LAMBDA_GRID, "country": COUNTRY_GRID}.get(which) or GRID | (HK_GRID if market == "hk" else {})
    for name, options in grids.items():
        for key, val in options:
            f = frame(market, data, **{key: val})
            rows.append({"param": name, "value": str(val), "market": market} | metrics(f))
            print(name, val, {k: round(v, 3) for k, v in rows[-1].items() if k.endswith(("ic 12m", "buy-sell 12m"))}, flush=True)
    out = pd.DataFrame(rows)
    out.to_csv(panel.BT / f"v3_{which}_{market}.csv", index=False)
    return out


def md(df: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(["", *map(str, df.columns)]) + " |", "|" + "---|" * (len(df.columns) + 1)]
    return "\n".join(lines + ["| " + " | ".join([str(i), *map(str, row)]) + " |" for i, row in df.iterrows()])


def compare() -> None:
    """v1, v3 as configured, E/P and B/P per market and sample -> data/backtest/v3_results.md (and the frames)."""
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


if __name__ == "__main__":
    if sys.argv[1] in ("grid", "lambda", "country"):
        grid(sys.argv[2], sys.argv[1])
    elif sys.argv[1] == "compare":
        compare()
