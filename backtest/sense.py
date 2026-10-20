"""Common-sense checks for valuation v3 (Phase 13, PLAN.md Method 16, "Common sense first"), in this order and each
period once: (1) fit: do the values explain prices (share within ±30% of the price, median gap), by market and P/B;
(2) guardrails: large stocks valued at under half or over twice their price, and the cases where the business points
the other way (a healthy business valued at under half its price, a business in trouble at over twice), with how
those stocks did, and what each size of gap has meant over the next year; (3) only then returns: rank correlation and
buy − sell, mean and median.

  uv run python -m backtest.sense build us|cn|hk   # the variant frames (minutes): data/backtest/v3_<m>_<variant>.pkl
  uv run python -m backtest.sense us|cn|hk [variant ...]   # the checks on frames v3_<m>.pkl or v3_<m>_<variant>.pkl
"""

import pickle
import sys

import numpy as np
import pandas as pd

from backtest import panel, v3 as bt

HALF, DOUBLE = -0.5, 1.0  # "the price halves" / "the price doubles"
PB_CUTS, PB_NAMES = [0, 1.5, 4, np.inf], ["P/B<1.5", "1.5-4", ">4"]
# variant -> (snapshots, settings); US "annual": the Phase 9 snapshots kept as snap_us_annual.pkl (no quarterly reports)
VARIANTS = {"us": {"annual": ("snap_us_annual", {}), "final": ("snap_us", {})}, "cn": {"final": ("snap_cn", {})},
            "hk": {"final": ("snap_hk", {})}}


def build(market: str) -> None:
    panel.setup_history(market)
    for name, (snaps, kw) in VARIANTS[market].items():
        with open(panel.BT / f"{snaps}.pkl", "rb") as fh:
            f = bt.frame(market, pickle.load(fh), **kw)
        f.to_pickle(panel.BT / f"v3_{market}_{name}.pkl")


def load(market: str, variant: str = "") -> pd.DataFrame:
    f = pd.read_pickle(panel.BT / f"v3_{market}{'_' + variant if variant else ''}.pkl")
    f = f[f["v3_valued"] == True].copy()  # noqa: E712 (object column)
    f["pb"] = pd.cut(1 / f["by"].where(f["by"] > 0), PB_CUTS, labels=PB_NAMES)
    f["large"] = f["mcap"] >= f.groupby("date")["mcap"].transform(lambda s: s.quantile(2 / 3))
    f["healthy"], f["trouble"] = f["v3_health"] >= 1, f["v3_health"] <= -1  # trend.health
    u = f["v3_upside"]
    f["clash"] = ((u <= HALF) & f["healthy"]) | ((u >= DOUBLE) & f["trouble"])
    return f


def fit(f: pd.DataFrame) -> pd.DataFrame:
    """Per sample: share within ±30% of the price, median |gap|, large stocks beyond half / double, clashes."""
    u = f["v3_upside"]
    f = f.assign(near=u.abs() <= 0.3, gap=u.abs(), far=(u <= HALF) | (u >= DOUBLE))
    rows = {}
    for s, g in f.groupby("sample"):
        big = g[g["large"]]
        rows[s] = {"within ±30%": g["near"].mean(), "median |gap|": g["gap"].median(), "large beyond ½/2×": big["far"].mean(),
                   "clashes": g["clash"].mean(), "large clashes": big["clash"].mean()}
        rows[s] |= {f"within ±30% {b}": g.loc[g["pb"] == b, "near"].mean() for b in PB_NAMES}
    return pd.DataFrame(rows)


def clash_record(f: pd.DataFrame) -> pd.DataFrame:
    """How the clashes did over the next 12 months: share that beat the market, median excess return, and how often
    the price actually halved / doubled (all stocks with the same business reading, for comparison)."""
    f = f[f["ex_12m"].notna()]
    u, rows = f["v3_upside"], {}
    for name, rule, base in (("healthy, valued under ½ price", (u <= HALF) & f["healthy"], f["healthy"]),
                             ("in trouble, valued over 2× price", (u >= DOUBLE) & f["trouble"], f["trouble"])):
        for s in ("in", "out"):
            g, b = f[rule & (f["sample"] == s)], f[base & (f["sample"] == s)]
            rows[(name, s)] = {"n": len(g), "beat the market": (g["ex_12m"] > 0).mean(), "median excess": g["ex_12m"].median(),
                               "halved": (g["ret_12m"] <= -0.5).mean(), "doubled": (g["ret_12m"] >= 1).mean(),
                               "all such: halved": (b["ret_12m"] <= -0.5).mean(), "all such: doubled": (b["ret_12m"] >= 1).mean()}
    return pd.DataFrame(rows).T


def meaning(f: pd.DataFrame) -> pd.DataFrame:
    """What a gap has meant over the next 12 months, per sample and gap band: median excess return, share that beat
    the market, and how often the price halved or doubled."""
    f = f[f["ex_12m"].notna()].assign(band=pd.cut(f["v3_upside"], [-1, HALF, -0.2, 0.2, DOUBLE, np.inf],
                                                  labels=["under ½", "−50 to −20%", "±20%", "+20 to +100%", "over 2×"]))
    g = f.groupby(["sample", "band"], observed=True)
    return pd.DataFrame({"share of stocks": g.size() / f.groupby("sample").size(), "median excess": g["ex_12m"].median(),
                         "beat the market": g["ex_12m"].apply(lambda x: (x > 0).mean()),
                         "halved": g["ret_12m"].apply(lambda x: (x <= -0.5).mean()),
                         "doubled": g["ret_12m"].apply(lambda x: (x >= 1).mean())})


def returns(f: pd.DataFrame) -> pd.DataFrame:
    """Per sample: 12-month rank correlation of upside with excess return, buy − sell mean and median, share of sells
    that trailed the market."""
    f, rows = f[f["ex_12m"].notna()], {}
    for s, g in f.groupby("sample"):
        ic = g.groupby("date").apply(lambda d: d["v3_upside"].rank().corr(d["ex_12m"].rank()))
        by = g.groupby("date")
        b, sl = (by.apply(lambda d, k=k: d.loc[d["v3_bucket"] == k, "ex_12m"].agg(["mean", "median"])) for k in ("buy", "sell"))
        rows[s] = {"rank corr": ic.mean(), "buy − sell mean": (b["mean"] - sl["mean"]).mean(),
                   "buy − sell median": (b["median"] - sl["median"]).mean(),
                   "sells trailing": (g.loc[g["v3_bucket"] == "sell", "ex_12m"] < 0).mean()}
    return pd.DataFrame(rows)


def versus(market: str, variant: str = "") -> pd.DataFrame:
    """The done-when comparison (PLAN item 13 (1), backtest.v3.metrics) on the same snapshots: 12-month rank IC and
    buy − sell against the equal-weight universe, v3 against v1, E/P and B/P."""
    f = pd.read_pickle(panel.BT / f"v3_{market}{'_' + variant if variant else ''}.pkl")
    f["ep_bucket"], f["bp_bucket"] = bt.factor_buckets(f, "ey"), bt.factor_buckets(f, "by")
    keys = ["in ic 12m", "out ic 12m", "in buy-sell 12m", "out buy-sell 12m"]
    return pd.DataFrame({w: {k: bt.metrics(f, w)[k] for k in keys} for w in ("v3 trend-first", "v1", "E/P", "B/P")}).T


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    if sys.argv[1] == "build":
        build(sys.argv[2])
        sys.exit()
    market, variants = sys.argv[1], sys.argv[2:] or [""]
    for v in variants:
        f = load(market, v)
        print(f"\n=== {market.upper()} {v or 'current'}: {f['date'].nunique()} dates")
        print(fit(f).round(3).to_string())
        print(clash_record(f).round(3).to_string())
        print(meaning(f).round(3).to_string())
        print(returns(f).round(3).to_string())
        print(versus(market, v).round(3).to_string())
