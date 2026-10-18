"""Calibration and the v1/v2 comparison (Phase 9): v2 variants re-run on the cached point-in-time
snapshots; each is scored by its rank correlation with later returns and its buckets, in-sample (month
ends to 2023-12) and out-of-sample (2024-01 on). Parameters are chosen on in-sample numbers only.

  uv run python -m backtest.calibrate grid cn   # one-at-a-time grids → data/backtest/grid_cn.csv
  uv run python -m backtest.calibrate compare   # v1 vs v2 (defaults and calibrated) → data/backtest/compare/
"""

import json
import sys

import numpy as np
import pandas as pd

from backtest import run
from stockreport import anchors, signal

MARKETS = ("cn", "us", "hk")
W_TODAY = dict(anchors.WEIGHTS)
WEIGHT_SETS = {  # intrinsic / peer / own for steady, cyclical, financial
    "v2 today": W_TODAY,
    "intrinsic only": {"steady": [1, 0, 0], "cyclical": [1, 0, 0], "financial": [1, 0, 0]},
    "more peer": {"steady": [0.4, 0.5, 0.1], "cyclical": [0.4, 0.3, 0.3], "financial": [0.4, 0.5, 0.1]},
    "more own": {"steady": [0.4, 0.2, 0.4], "cyclical": [0.3, 0.1, 0.6], "financial": [0.4, 0.2, 0.4]},
    "equal": {k: [1 / 3] * 3 for k in W_TODAY},
    "peer + own only": {"steady": [0.2, 0.5, 0.3], "cyclical": [0.2, 0.3, 0.5], "financial": [0.2, 0.5, 0.3]},
}
GRID = {
    "lambda": [("engine__LAMBDA", x) for x in (0.0, 0.25, 0.5, 0.75, 1.0)],
    "discount": [("engine__DISCOUNT", x) for x in ("implied", "configured")],
    "anchor weights": [("anchors__WEIGHTS", k) for k in WEIGHT_SETS],
    "phi scale": [("engine__PHI", x) for x in ((0.15, 0.45, 0.2), (0.075, 0.225, 0.1), (0.3, 0.45, 0.2), (0.05, 0.2, 0.1))],
    "momentum floor": [("shadow__MOM_FLOOR", x) for x in ("industry", "market", "none")],
    "momentum weight": [("shadow__MOM_WEIGHT", x) for x in (0.0, 0.25, 0.5, 1.0)],
    "momentum weight, market floor": [("shadow__MOM_WEIGHT", x) for x in (0.0, 0.25, 0.5, 1.0)],
}

GRID2 = {  # after the panel studies: φ levels and fade length, the panel's history weights, floor and weight together
    "phi level": [("engine__PHI", x) for x in ((0.15, 0.45, 0.2), (0.05, 0.15, 0.067), (0.4, 0, 0), (0.2, 0, 0), (0.1, 0, 0))],
    "fade years": [("engine__FADE_YEARS", x) for x in (10, 7, 5, 3)],
    "cycle factors": [("engine__CYCLE", x) for x in ((1.0, 0.0, 0.3, 0.6), (0.5, 0.0, 0.2, 0.3), (0.7, 0.0, 0.2, 0.4))],
    "momentum weight, no floor": [("shadow__MOM_WEIGHT", x) for x in (0.0, 0.25, 0.5, 1.0)],
}


PHI_MARKET = {"cn": (0.2, 0.0, 0.0), "hk": (0.2, 0.0, 0.0), "us": (0.15, 0.45, 0.2)}  # the panel and grid choice
BASE = {"engine__LAMBDA": 0.0, "shadow__MOM_WEIGHT": 0.5}  # the first grids' best values (λ 0 then failed the 0.005 bar)
GRID3 = {  # joint check of the chosen values (φ per market, see BACKTEST.md) with fade length, λ and cycle factors
    "joint: fade years": [("engine__FADE_YEARS", x) for x in (10, 5, 3)],
    "joint: lambda": [("engine__LAMBDA", x) for x in (0.0, 0.5)],
    "joint: cycle factors": [("engine__CYCLE", x) for x in ((1.0, 0.0, 0.3, 0.6), (0.5, 0.0, 0.2, 0.3))],
    "joint: anchor weights": [("anchors__WEIGHTS", k) for k in ("v2 today", "intrinsic only")],
}


def kwargs(name: str, key: str, val, market: str = "") -> dict:
    if name.startswith("review"):
        return EXCESS_ON if val == "on" else {} if key == "excess" else {key: val}
    if name.startswith("joint"):
        base = BASE | {"engine__PHI": PHI_MARKET[market]}
        return base | {key: WEIGHT_SETS[val] if key == "anchors__WEIGHTS" else val}
    kw = {key: WEIGHT_SETS[val] if key == "anchors__WEIGHTS" else val}
    if name == "momentum weight, market floor":
        kw["shadow__MOM_FLOOR"] = "market"
    if name == "momentum weight, no floor":
        kw["shadow__MOM_FLOOR"] = "none"
    return kw


def metrics(f: pd.DataFrame, who: str = "v2") -> dict:
    """Per sample: mean rank IC of the upside with 1/3/12-month returns, buy, sell and buy − sell against
    the universe (12 and 3 months), and the buys' hit rate."""
    out = {}
    up, bucket = ("v2_upside", "v2_bucket") if who == "v2" else ("upside", "v1_bucket")
    for sample in ("in", "out"):
        part = f[f["sample"] == sample]
        for h in ("1m", "3m", "12m"):
            s = signal.summarize(signal.rank_ic(part, up, f"ret_{h}"), signal.HORIZONS[h])
            out[f"{sample} ic {h}"], out[f"{sample} ic {h} t"] = s["mean"], s["t"]
        for h in ("3m", "12m"):
            t = signal.bucket_table(part, bucket, h)
            for b in ("buy", "hold", "sell", "buy-sell"):
                out[f"{sample} {b} {h}"] = t.at[b, "vs_universe"] if b in t.index else np.nan
            out[f"{sample} buy hit {h}"] = t.at["buy", "hit"] if "buy" in t.index else np.nan
            out[f"{sample} buy-sell t {h}"] = t.at["buy-sell", "t"] if "buy-sell" in t.index else np.nan
    return out


def grid(market: str, which: str = "grid") -> pd.DataFrame:
    """Every grid value for one market → data/backtest/<which>_<market>.csv."""
    run.panel.setup_history(market)
    data, rows = run.load(market), []
    for name, options in {"grid": GRID, "grid2": GRID2, "grid3": GRID3, "grid4": GRID4}[which].items():
        if name == "review: country premium" and market != "us":
            continue
        for key, val in options:
            f = run.frame(market, data, **kwargs(name, key, val, market))
            rows.append({"param": name, "value": str(val), "market": market} | metrics(f))
            print(name, val, market, {k: round(v, 3) for k, v in rows[-1].items() if k.endswith("ic 12m")}, flush=True)
    out = pd.DataFrame(rows)
    out.to_csv(run.panel.BT / f"{which}_{market}.csv", index=False)
    return out


def best(g: pd.DataFrame, param: str, key: str = "in ic 12m") -> str:
    """The value with the best in-sample score averaged over the three markets."""
    return g[g["param"] == param].groupby("value", sort=False)[key].mean().idxmax()


PHASE8 = {"engine__PHI": (0.15, 0.45, 0.2), "engine__FADE_YEARS": 10, "shadow__MOM_WEIGHT": 0.0,
          "regime__PHI_NEW": 0.5, "regime__OWN_BOOM": 0.5, "engine__COUNTRY_LAMBDA": 0.0,
          "shadow__BUY_MIN_EXCESS": 0.02, "shadow__SELL_MAX_EXCESS": -0.02,
          "shadow__BUY_LARGEST": None, "shadow__BUY_HOME_ONLY": False}  # v2 as Phase 8 left it
NO_FLOOR = {"shadow__BUY_LARGEST": None, "shadow__BUY_HOME_ONLY": False}
FIRST_CALIBRATION = {"engine__FADE_YEARS": 3, "engine__COUNTRY_LAMBDA": 0.0, "shadow__BUY_MIN_EXCESS": 0.02,
                     "shadow__SELL_MAX_EXCESS": -0.02} | NO_FLOOR  # Phase 9 before the US review (2026-10-18)
REVIEW = NO_FLOOR  # after the US review, before the size floor
EXCESS_ON = {"shadow__BUY_MIN_EXCESS": 0.02, "shadow__SELL_MAX_EXCESS": -0.02}
GRID4 = {  # the US review: per-market fade, the country premium, the duration-dependent excess rule (config = today)
    "review: fade years": [("engine__FADE_YEARS", x) for x in (10, 5, 3)],
    "review: country premium": [("engine__COUNTRY_LAMBDA", x) for x in (0.0, 0.5, 1.0)],
    "review: excess rule": [("excess", x) for x in ("off", "on")],
}


def compare(chosen: dict) -> None:
    """v1 and v2 (Phase 8's first guesses as "default", config.toml's calibrated values) per market."""
    out = run.panel.BT / "compare"
    out.mkdir(exist_ok=True)
    rows = []
    for m in MARKETS:
        run.panel.setup_history(m)
        data = run.load(m)
        for label, kw in (("default", PHASE8), ("first", FIRST_CALIBRATION), ("review", REVIEW), ("calibrated", chosen)):
            f = run.frame(m, data, **kw)
            f.to_pickle(out / f"{m}_{label}.pkl")
            rows.append({"market": m, "method": f"v2 {label}"} | metrics(f, "v2"))
        rows.append({"market": m, "method": "v1"} | metrics(f, "v1"))
    pd.DataFrame(rows).to_csv(out / "metrics.csv", index=False)


if __name__ == "__main__":
    if sys.argv[1] in ("grid", "grid2", "grid3", "grid4"):
        grid(sys.argv[2], sys.argv[1])
    elif sys.argv[1] == "compare":
        compare(json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})
