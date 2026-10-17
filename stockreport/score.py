"""Sector-neutral z-scores within a market, the composite score and plain-word drivers
(PLAN.md Method sections 5 and 7)."""

import pandas as pd

from stockreport.config import CONFIG

# component -> [(metric, sign)]; financials use their own list where one is given
COMPONENTS = {
    "value": [("upside", 1), ("ey", 1)],
    "quality": [("roe", 1), ("gross_margin", 1), ("cash_conv", 1), ("debt_ratio", -1)],
    "growth": [("rev_growth", 1), ("np_growth", 1)],
    "momentum": [("mom_12_1", 1)],
    "risk": [("vol_1y", -1)],
}
FINANCIAL = {"value": [("upside", 1), ("ey", 1), ("by", 1)], "quality": [("roe", 1)]}
WORDS = {  # component -> (when strong, when weak)
    "value": ("估值低于同行", "估值高于同行"),
    "quality": ("盈利质量高", "盈利质量弱"),
    "growth": ("增长较快", "增长放缓"),
    "momentum": ("股价趋势强", "股价趋势弱"),
    "risk": ("波动较低", "波动较大"),
}


def neutral_z(x: pd.Series, groups: pd.Series) -> pd.Series:
    """Demean within each peer group, scale by the market-wide spread, clip at +-3."""
    demeaned = x - x.groupby(groups).transform("mean")
    return (demeaned / demeaned.std()).clip(-3, 3)


def _component(df: pd.DataFrame, items: list, rows: pd.Series) -> pd.Series:
    sub = df[rows]
    zs = [neutral_z(sign * sub[metric], sub["peer_group"]) for metric, sign in items]
    return pd.concat(zs, axis=1).mean(axis=1)


def score(df: pd.DataFrame) -> pd.DataFrame:
    weights = CONFIG["score"]["weights"]
    df = df.copy()
    fin = df["financial"].astype(bool)
    for comp, items in COMPONENTS.items():
        raw = pd.concat([_component(df, items, ~fin), _component(df, FINANCIAL.get(comp, items), fin)])
        raw = raw.reindex(df.index)
        df[f"z_{comp}"] = ((raw - raw.mean()) / raw.std()).clip(-3, 3)
    df["composite"] = sum(weights[c] * df[f"z_{c}"].fillna(0) for c in COMPONENTS)
    df["quality_pct"] = df["z_quality"].rank(pct=True)
    df["quality_group_median"] = df.groupby("peer_group")["z_quality"].transform("median")
    return df


def explain(row: pd.Series, bucket: str) -> tuple[str, str]:
    """Two drivers (largest weighted contributions behind the call) and the key risk."""
    weights = CONFIG["score"]["weights"]
    z = {c: row[f"z_{c}"] for c in COMPONENTS if pd.notna(row[f"z_{c}"])}
    contrib = sorted(z, key=lambda c: weights[c] * z[c], reverse=bucket != "sell")
    word = lambda c: WORDS[c][0] if z[c] >= 0 else WORDS[c][1]
    drivers = "；".join(word(c) for c in contrib[:2])
    against = min(z, key=z.get) if bucket != "sell" else max(z, key=z.get)
    return drivers, word(against)
