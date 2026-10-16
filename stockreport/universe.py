"""Universe and metrics: filter the market, keep the top N by market value and compute the
trailing metrics every later step uses (PLAN.md Method sections 1 and 3)."""

import logging
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import tdx

log = logging.getLogger(__name__)
A_SHARE = re.compile(r"^(60[0-5]\d{3}|68[89]\d{3}|00[0-3]\d{3}|30[01]\d{3})$")
WINSORIZED = ["pe", "pb", "ps", "ey", "by", "roe", "rev_growth", "np_growth", "gross_margin",
              "debt_ratio", "cash_conv", "div_yield", "mom_12_1", "vol_1y", "fwd_pe", "fwd_growth"]


def load_results() -> pd.DataFrame:
    frames = []
    for path in sorted((DATA / "fundamentals").glob("cn_results_*.csv.gz")):
        df = pd.read_csv(path, dtype={"code": str, "notice_date": str})
        df["period"] = path.name[len("cn_results_"):-len(".csv.gz")]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def ttm(results: pd.DataFrame) -> pd.DataFrame:
    """Latest report per stock, plus trailing-12-month revenue and profit:
    TTM = year-to-date + last full year - same period of last year."""
    results = results.dropna(subset=["revenue", "np"])
    latest = results.loc[results.groupby("code")["period"].idxmax()].copy()
    year = latest["period"].str[:4].astype(int) - 1
    latest["fy_period"] = year.astype(str) + "-12-31"
    latest["prior_period"] = year.astype(str) + latest["period"].str[4:]
    keyed = results.set_index(["code", "period"])[["revenue", "np"]]
    for tag, col in (("fy", "fy_period"), ("prior", "prior_period")):
        other = keyed.reindex(pd.MultiIndex.from_arrays([latest["code"], latest[col]]))
        latest[f"revenue_{tag}"] = other["revenue"].to_numpy()
        latest[f"np_{tag}"] = other["np"].to_numpy()
    annual = latest["period"].str.endswith("12-31")
    for col in ("revenue", "np"):
        latest[f"{col}_ttm"] = np.where(annual, latest[col], latest[col] + latest[f"{col}_fy"] - latest[f"{col}_prior"])
    return latest.set_index("code")


def price_metrics(prices: pd.DataFrame, codes: list[str]) -> pd.DataFrame:
    """12-1 month momentum and 1-year volatility from returns chained as close / exchange prev-close."""
    dates = np.sort(prices.loc[prices["code"] == "CSI300", "date"].unique())
    px = prices[prices["code"].isin(codes)]
    traded = px["volume"] > 0
    ret = (px["close"] / px["prev_close"] - 1).where(traded)
    wide = pd.DataFrame({"date": px["date"], "code": px["code"], "ret": ret}).pivot(index="date", columns="code", values="ret")
    wide = wide.reindex(index=dates, columns=codes)
    level = (1 + wide.fillna(0)).cumprod()
    first = px.groupby("code")["date"].min().reindex(codes)
    last = date.fromisoformat(dates[-1])
    t0 = dates[dates <= (last - timedelta(days=365)).isoformat()]  # last close a year ago
    t1 = dates[dates <= (last - timedelta(days=30)).isoformat()][-1]  # and a month ago
    out = pd.DataFrame(index=codes)
    if len(t0):
        out["mom_12_1"] = (level.loc[t1] / level.loc[t0[-1]] - 1).where(first <= t0[-1])
    year = wide[wide.index > (last - timedelta(days=365)).isoformat()]
    out["vol_1y"] = year.std() * np.sqrt(252)
    out.loc[year.count() < 120, "vol_1y"] = np.nan
    return out


def winsorize(df: pd.DataFrame, cols: list[str], lo: float, hi: float) -> pd.DataFrame:
    for col in cols:
        low, high = df[col].quantile([lo, hi])
        df[col] = df[col].clip(low, high)
    return df


def build_cn(today: date) -> tuple[pd.DataFrame, dict]:
    cfg = CONFIG["universe"]
    quotes = pd.read_csv(DATA / "quotes" / "cn.csv.gz", dtype={"code": str, "trade_date": str})
    prices = tdx.load_prices()
    last = prices["date"].max()
    info = {"quote_date": quotes["trade_date"].iloc[0], "price_date": last, "stages": {}, "dropped": {}}
    if info["quote_date"] != last:
        log.warning("quotes are for %s but the latest daily package is %s", info["quote_date"], last)

    df = quotes[quotes["code"].str.match(A_SHARE)].set_index("code")
    info["stages"]["A-shares (SH/SZ)"] = len(df)
    df = df[~df["name"].str.contains("|".join(cfg["exclude_name_patterns"]), regex=True)]
    info["stages"]["not ST / delisting"] = len(df)

    today_px = prices[prices["date"] == last].set_index("code")
    df = df[df.index.isin(today_px.index[today_px["volume"] > 0])]
    info["stages"]["traded on last day"] = len(df)
    first_seen = prices.groupby("code")["date"].min()
    listed_before = (today - timedelta(days=cfg["min_listing_days"])).isoformat()
    df = df[first_seen.reindex(df.index) <= listed_before]
    info["stages"]["listed >= 1 year"] = len(df)
    recent = np.sort(prices["date"].unique())[-20:]
    turnover = prices[prices["date"].isin(recent)].groupby("code")["amount"].sum() / len(recent)
    df["turnover_20d"] = turnover.reindex(df.index).fillna(0)
    df = df[df["turnover_20d"] >= cfg["min_turnover"]["cn"]]
    info["stages"]["20-day turnover >= min"] = len(df)
    df = df.sort_values("mcap", ascending=False).head(cfg["top_n"]).copy()
    df["mcap_rank"] = np.arange(1, len(df) + 1)
    info["stages"]["top by market value"] = len(df)

    df["price"] = df["close"]
    df["tdx_close"] = today_px["close"].reindex(df.index)
    df = df.join(price_metrics(prices, list(df.index)))
    fund = ttm(load_results())
    df = df.join(fund[["period", "notice_date", "revenue_ttm", "np_ttm", "bps", "eps", "ocfps",
                       "gross_margin", "rev_yoy", "np_yoy"]])
    balance = []
    for path in sorted((DATA / "fundamentals").glob("cn_balance_*.csv.gz")):
        b = pd.read_csv(path, dtype={"code": str})
        b["bperiod"] = path.name[len("cn_balance_"):-len(".csv.gz")]
        balance.append(b)
    balance = pd.concat(balance).dropna(subset=["debt_ratio"]).sort_values("bperiod")
    df["debt_ratio"] = balance.groupby("code")["debt_ratio"].last().reindex(df.index) / 100
    div = pd.read_csv(DATA / "fundamentals" / "cn_dividends.csv.gz", dtype={"code": str, "ex_date": str})
    div = div[div["ex_date"] > (today - timedelta(days=365)).isoformat()]
    df["dps_ttm"] = div.groupby("code")["dps"].sum().reindex(df.index).fillna(0)
    cons_path = DATA / "fundamentals" / "cn_consensus.csv.gz"
    cons = pd.read_csv(cons_path, dtype={"code": str}).set_index("code") if cons_path.exists() else pd.DataFrame()
    df = df.join(cons.reindex(columns=["analysts", "eps_e1", "eps_e2", "eps_e3"]))
    df["analysts"] = df["analysts"].fillna(0)

    df["eps_ttm"] = df["np_ttm"] / df["shares"]
    df["sps_ttm"] = df["revenue_ttm"] / df["shares"]
    df["pe"] = (df["mcap"] / df["np_ttm"]).where(df["np_ttm"] > 0)
    df["pb"] = (df["price"] / df["bps"]).where(df["bps"] > 0)
    df["ps"] = (df["mcap"] / df["revenue_ttm"]).where(df["revenue_ttm"] > 0)
    df["ey"] = df["np_ttm"] / df["mcap"]
    df["by"] = df["bps"] / df["price"]
    df["roe"] = df["np_ttm"] / (df["bps"] * df["shares"])
    df["rev_growth"] = df["rev_yoy"] / 100
    df["np_growth"] = df["np_yoy"] / 100
    df["gross_margin"] = df["gross_margin"] / 100
    df["cash_conv"] = (df["ocfps"] / df["eps"]).where(df["eps"] > 0)
    df["div_yield"] = df["dps_ttm"] / df["price"]
    payout = (df["dps_ttm"] / df["eps_ttm"]).where(df["eps_ttm"] > 0, 0).clip(0, 1)
    df["retention"] = 1 - payout
    df["fwd_pe"] = (df["price"] / df["eps_e2"]).where(df["eps_e2"] > 0)  # on next year's consensus EPS
    df["fwd_growth"] = (df["eps_e3"] / df["eps_e1"]).where((df["eps_e1"] > 0) & (df["eps_e3"] > 0)) ** 0.5 - 1
    fin = CONFIG["peers"]["financial_industries"]
    df["financial"] = df["industry"].fillna("").str.contains("|".join(fin))

    checks = {
        "missing fundamentals": df[["np_ttm", "revenue_ttm", "bps", "rev_growth", "np_growth"]].isna().any(axis=1),
        "negative book value": df["bps"] <= 0,
        "missing price history": df[["mom_12_1", "vol_1y"]].isna().any(axis=1),
        "quote vs daily close differ >1%": (df["tdx_close"] / df["price"] - 1).abs() > 0.01,
        "P/E disagrees with source": df["pe_ttm_em"].notna() & (((df["pe_ttm_em"] > 0) != (df["np_ttm"] > 0))
                                                              | ((df["pe"] / df["pe_ttm_em"]).sub(1).abs() > 0.5)),
        "P/B disagrees with source": (df["pb"] / df["pb_mrq_em"]).sub(1).abs() > 0.5,
    }
    bad = pd.Series(False, index=df.index)
    for reason, mask in checks.items():
        mask = mask.fillna(False) & ~bad
        info["dropped"][reason] = sorted(df.index[mask])
        bad |= mask
    df = df[~bad].copy()
    info["stages"]["complete, consistent data"] = len(df)
    lo, hi = CONFIG["value"]["winsor"]
    return winsorize(df, WINSORIZED, lo, hi), info
