"""The score's ingredients (PLAN.md, "The score: three families"): each component per stock, and its percentile within
the market on the date. Inputs are point-in-time: the universe's latest public reports and prices, and for CN the
quarterly 扣非 profit by notice date (fetch.eastmoney.CN_DEDUCT)."""

import numpy as np
import pandas as pd

FAMILIES = {  # family -> market -> components
    "value": {"cn": ["ep", "bp", "sp"], "hk": ["ep", "bp", "sp"], "us": ["ep", "bp", "sp"]},
    "quality": {"cn": ["roe", "cash", "debt"], "hk": ["roe", "cash", "debt"], "us": ["gpa", "cash", "debt"]},
    "momentum": {"cn": ["sue"], "hk": ["mom"], "us": ["mom"]},
}
LOWER_IS_BETTER = {"debt"}
SUE_QUARTERS, SUE_MIN = 8, 6  # the change's spread over the last 8 quarters, at least 6 of them known


def quarters(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Code × quarter from year-to-date 扣非 profit (code, period, deduct): the trailing-12-month sum and the SUE, the
    quarter's profit minus the same quarter a year earlier over the standard deviation of that change in the last 8
    quarters. Amounts, not per-share figures, so bonus shares (送转) don't read as a fall."""
    ytd = table.pivot_table(index="code", columns="period", values="deduct", aggfunc="last")
    span = pd.period_range(ytd.columns.min(), ytd.columns.max(), freq="Q")
    ytd = ytd.reindex(columns=[p.end_time.strftime("%Y-%m-%d") for p in span])
    single = ytd - ytd.shift(1, axis=1)
    first = [c.endswith("-03-31") for c in ytd.columns]  # the fiscal year's first quarter is its year to date
    single.loc[:, first] = ytd.loc[:, first]
    change = single - single.shift(4, axis=1)
    sd = change.T.rolling(SUE_QUARTERS, min_periods=SUE_MIN).std().T
    return single.T.rolling(4, min_periods=4).sum().T, change / sd.where(sd > 0)


def cn_deduct(table: pd.DataFrame, day: str) -> pd.DataFrame:
    """Per stock, from the reports noticed on or before `day`: the latest quarter, its 扣非 TTM profit and SUE."""
    public = table[(table["notice_date"] <= day) & table["deduct"].notna()]
    ttm, sue = quarters(public)
    latest = public.groupby("code")["period"].max()
    rows, cols = ttm.index.get_indexer(latest.index), ttm.columns.get_indexer(latest.to_numpy())
    return pd.DataFrame({"deduct_period": latest, "deduct_ttm": ttm.to_numpy()[rows, cols],
                         "sue": sue.to_numpy()[rows, cols]}, index=latest.index)


def components(df: pd.DataFrame, market: str, cn: pd.DataFrame | None = None) -> pd.DataFrame:
    """Each component's raw value (NaN where it doesn't apply). E/P on 扣非 TTM in CN (reported profit where 扣非 is
    missing), and on profit to common shareholders in the US (B/P on common book, history.us_preferred); B/P only on
    a positive book; S/P, cash backing and debt not for banks, insurers and brokers."""
    fin = df["financial"].astype(bool)
    pref = df.get("pref_share", 0.0)
    earnings = df["np_ttm"] * (1 - df.get("pref_div_share", 0.0))
    if market == "cn" and cn is not None:
        earnings = cn["deduct_ttm"].reindex(df.index).fillna(df["np_ttm"])
    ocf, npf, rev = (["ocf_ttm", "np_ttm", "revenue_ttm"] if market == "us" else ["ocf_ytd", "np_ytd", "revenue_ytd"])
    book = df["bps"] * (1 - pref)
    out = pd.DataFrame({
        "ep": earnings / df["mcap"],
        "bp": (book / df["price"]).where(book > 0),
        "sp": (df["revenue_ttm"] / df["mcap"]).where(~fin & (df["revenue_ttm"] > 0)),
        "roe": df["roe"],
        "cash": ((df[ocf] - df[npf]) / df[rev]).where(~fin & (df[rev] > 0)),
        "debt": df["debt_ratio"].where(~fin),
        "mom": df["mom_12_1"],
    }, index=df.index)
    if market == "us":
        out["gpa"] = (df["gp_ttm"] / df["assets"]).where(~fin & (df["assets"] > 0))
    if market == "cn":
        out["sue"] = cn["sue"].reindex(df.index) if cn is not None else np.nan
    return out


def percentiles(comp: pd.DataFrame, df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Each component as a percentile within the market (1 = best). US financials have no gross profit: their
    profitability is ROE, ranked among financials (Novy-Marx's gross profitability excludes them)."""
    used = sorted({c for fam in FAMILIES.values() for c in fam[market]})
    pct = pd.DataFrame({c: (-comp[c] if c in LOWER_IS_BETTER else comp[c]).rank(pct=True) for c in used}, index=comp.index)
    if market == "us":
        fin = df["financial"].astype(bool)
        pct.loc[fin, "gpa"] = comp.loc[fin, "roe"].rank(pct=True)
    return pct
