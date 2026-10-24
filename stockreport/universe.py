"""Universe and metrics: filter the market, keep the top N by market value and compute the trailing figures the
score (signals.py) and the cards use (PLAN.md, the method). Figures are kept as reported, not winsorized: the score
uses percentiles, and the cards show them."""

import logging
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from stockreport import crosscheck
from stockreport.config import CONFIG, DATA
from stockreport.fetch import eastmoney, hkex, nasdaq, sec, swclass, tdx, yahoo

log = logging.getLogger(__name__)
A_SHARE = re.compile(r"^(60[0-5]\d{3}|68[89]\d{3}|00[0-3]\d{3}|30[01]\d{3})$")
NEEDED = ["np_ttm", "revenue_ttm", "bps"]  # a stock without these is dropped (rule 5); growth isn't scored


def load_results(table: str = "results") -> pd.DataFrame:
    """All saved CN report periods of a table (cn_<table>_<period>.csv.gz), with a period column."""
    paths = sorted((DATA / "fundamentals").glob(f"cn_{table}_*.csv.gz"))
    return pd.concat([pd.read_csv(p, dtype={"code": str, "notice_date": str}).assign(period=p.name[4 + len(table):-7])
                      for p in paths], ignore_index=True)


def ttm(results: pd.DataFrame) -> pd.DataFrame:
    """Latest report per stock, plus trailing-12-month revenue and profit (and 扣非 EPS where the table has it): TTM =
    year-to-date + last full year - same period of last year; the fiscal year starts on the row's `start` (HK) or Jan 1."""
    results = results.dropna(subset=["revenue", "np"])
    cols = ["revenue", "np"] + (["eps_deduct"] if "eps_deduct" in results else [])
    latest = results.loc[results.groupby("code")["period"].idxmax()].copy()
    start = pd.to_datetime(latest["start"] if "start" in latest else latest["period"].str[:4] + "-01-01")
    latest["fy_period"] = (start - pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d")
    latest["prior_period"] = (latest["period"].str[:4].astype(int) - 1).astype(str) + latest["period"].str[4:]
    keyed = results.set_index(["code", "period"])[cols]
    for tag, col in (("fy", "fy_period"), ("prior", "prior_period")):
        other = keyed.reindex(pd.MultiIndex.from_arrays([latest["code"], latest[col]]))
        for c in cols:
            latest[f"{c}_{tag}"] = other[c].to_numpy()
    annual = (pd.to_datetime(latest["period"]) - start).dt.days > 350
    for c in cols:
        latest[f"{c}_ttm"] = np.where(annual, latest[c], latest[c] + latest[f"{c}_fy"] - latest[f"{c}_prior"])
    return latest.set_index("code")


def trading_days(prices: pd.DataFrame) -> np.ndarray:
    """The market's trading days: days with prices for at least half as many stocks as its busiest day, so one
    stock's stray newer row doesn't make a day, and an index that skipped a day (Yahoo's ^HSI, 2026-10-20) doesn't
    remove one."""
    n = prices.groupby("date")["code"].nunique()
    return np.sort(n.index[n >= n.max() / 2].to_numpy())


def price_metrics(prices: pd.DataFrame, codes: list[str]) -> pd.DataFrame:
    """12-1 month momentum, the 6-month return (a card's key risk) and 1-year volatility from returns chained as
    close / prev-close (ex-rights adjusted), on the market's trading days."""
    dates = trading_days(prices)
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
    t6 = dates[dates <= (last - timedelta(days=182)).isoformat()]
    out = pd.DataFrame(index=codes)
    if len(t0):
        out["mom_12_1"] = (level.loc[t1] / level.loc[t0[-1]] - 1).where(first <= t0[-1])
    if len(t6):
        out["ret_6m"] = (level.iloc[-1] / level.loc[t6[-1]] - 1).where(first <= t6[-1])
    year = wide[wide.index > (last - timedelta(days=365)).isoformat()]
    out["vol_1y"] = year.std() * np.sqrt(252)
    out.loc[year.count() < 120, "vol_1y"] = np.nan
    return out


def dividends(path: Path, today: date) -> pd.Series:
    """Cash dividends per share (quote currency) with ex-dates in the last 365 days."""
    if not path.exists():
        return pd.Series(dtype=float)
    div = pd.read_csv(path, dtype={"code": str, "ex_date": str})
    return div[div["ex_date"] > (today - timedelta(days=365)).isoformat()].groupby("code")["dps"].sum()


def screen(df: pd.DataFrame, prices: pd.DataFrame, today: date, market: str, info: dict) -> pd.DataFrame:
    """Traded on the last day, listed at least a year, 20-day average turnover above the minimum."""
    cfg = CONFIG["universe"]
    last = str(trading_days(prices)[-1])
    today_px = prices[prices["date"] == last].set_index("code")
    df = df[df.index.isin(today_px.index[today_px["volume"] > 0])]
    info["stages"]["traded on last day"] = len(df)
    first_seen = prices.groupby("code")["date"].min()
    listed_before = (today - timedelta(days=cfg["min_listing_days"])).isoformat()
    df = df[first_seen.reindex(df.index) <= listed_before]
    info["stages"]["listed >= 1 year"] = len(df)
    recent = np.sort(prices["date"].unique())[-20:]
    turnover = prices[prices["date"].isin(recent)].groupby("code")["amount"].sum() / len(recent)
    df = df.assign(turnover_20d=turnover.reindex(df.index).fillna(0))
    df = df[df["turnover_20d"] >= cfg["min_turnover"][market]]
    info["stages"]["20-day turnover >= min"] = len(df)
    return df


def top_by_value(df: pd.DataFrame, info: dict) -> pd.DataFrame:
    df = df.sort_values("mcap", ascending=False).head(CONFIG["universe"]["top_n"]).copy()
    df["mcap_rank"] = np.arange(1, len(df) + 1)
    info["stages"]["top by market value"] = len(df)
    return df


def ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Per-share numbers and multiples, from price, mcap, shares, np_ttm, revenue_ttm, bps, dps_ttm
    and consensus EPS (all in the quote currency)."""
    df["eps_ttm"] = df["np_ttm"] / df["shares"]
    df["sps_ttm"] = df["revenue_ttm"] / df["shares"]
    df["pe"] = (df["mcap"] / df["np_ttm"]).where(df["np_ttm"] > 0)
    df["pb"] = (df["price"] / df["bps"]).where(df["bps"] > 0)
    df["ps"] = (df["mcap"] / df["revenue_ttm"]).where(df["revenue_ttm"] > 0)
    df["ey"] = df["np_ttm"] / df["mcap"]
    df["by"] = df["bps"] / df["price"]
    df["roe"] = (df["np_ttm"] / (df["bps"] * df["shares"])).where(df["bps"] > 0)  # none on a negative book
    df["div_yield"] = df["dps_ttm"] / df["price"]
    payout = (df["dps_ttm"] / df["eps_ttm"]).where(df["eps_ttm"] > 0, 0).clip(0, 1)
    df["retention"] = 1 - payout
    df["fwd_pe"] = (df["price"] / df["eps_e2"]).where(df["eps_e2"] > 0)  # on next year's consensus EPS
    df["fwd_growth"] = (df["eps_e3"] / df["eps_e1"]).where((df["eps_e1"] > 0) & (df["eps_e3"] > 0)) ** 0.5 - 1
    return df


def finish(df: pd.DataFrame, info: dict, checks: dict) -> tuple[pd.DataFrame, dict]:
    """Drop stocks failing a check (first failing reason is recorded) and clip cash conversion (the DeepSeek notes'
    figure). It explodes when profit is tiny (兖煤澳大利亚 31.6) and mixes consolidated cash flow with attributable
    profit, so it is clipped and left out below a minimum net margin."""
    cfg = CONFIG["universe"]
    bad = pd.Series(False, index=df.index)
    for reason, mask in checks.items():
        mask = mask.fillna(False) & ~bad
        info["dropped"][reason] = sorted(df.index[mask])
        bad |= mask
    df = df[~bad].copy()
    info["stages"]["complete, consistent data"] = len(df)
    margin = df["np_ttm"] / df["revenue_ttm"].where(df["revenue_ttm"] > 0)
    df["cash_conv"] = df["cash_conv"].clip(*cfg["cash_conv_range"]).where(margin >= cfg["cash_conv_min_margin"])
    return df, info


def build_cn(today: date) -> tuple[pd.DataFrame, dict]:
    cfg = CONFIG["universe"]
    quotes = pd.read_csv(DATA / "quotes" / "cn.csv.gz", dtype={"code": str, "trade_date": str})
    prices = tdx.load_prices()
    last = str(trading_days(prices)[-1])
    info = {"quote_date": quotes["trade_date"].iloc[0], "price_date": last, "stages": {}, "dropped": {}}
    if info["quote_date"] != last:
        log.warning("quotes are for %s but the latest daily package is %s", info["quote_date"], last)

    df = quotes[quotes["code"].str.match(A_SHARE)].set_index("code")
    info["stages"]["A-shares (SH/SZ)"] = len(df)
    df = df[~df["name"].str.contains("|".join(cfg["exclude_name_patterns"]), regex=True)]
    info["stages"]["not ST / delisting"] = len(df)
    df = top_by_value(screen(df, prices, today, "cn", info), info)

    df["price"] = df["close"]
    df["tdx_close"] = prices[prices["date"] == last].set_index("code")["close"].reindex(df.index)
    df = df.join(price_metrics(prices, list(df.index)))
    fund = ttm(load_results())
    df = df.join(fund.reindex(columns=["period", "notice_date", "revenue_ttm", "np_ttm", "bps", "eps", "ocfps",
                                       "gross_margin", "rev_yoy", "np_yoy", "revenue", "np"]))
    # cash backing on the latest report's year to date (operating cash flow per share × today's shares)
    df = df.rename(columns={"revenue": "revenue_ytd", "np": "np_ytd"}).assign(ocf_ytd=df["ocfps"] * df["shares"])
    balance = load_results("balance").dropna(subset=["debt_ratio"]).sort_values("period")
    df["debt_ratio"] = balance.groupby("code")["debt_ratio"].last().reindex(df.index) / 100
    df["dps_ttm"] = dividends(DATA / "fundamentals" / "cn_dividends.csv.gz", today).reindex(df.index).fillna(0)
    df = ratios(join_consensus(df, DATA / "fundamentals" / "cn_consensus.csv.gz",
                               ["analysts", "e1_year", "eps_e1", "eps_e2", "eps_e3"]))
    df["rev_growth"] = df["rev_yoy"] / 100
    df["np_growth"] = df["np_yoy"] / 100
    df["gross_margin"] = df["gross_margin"] / 100
    df["cash_conv"] = (df["ocfps"] / df["eps"]).where(df["eps"] > 0)
    fin = CONFIG["peers"]["financial_industries"]
    df["financial"] = df["industry"].fillna("").str.contains("|".join(fin))
    df["sector"] = swclass.level1().reindex(df.index).fillna("未分类")

    checks = {
        "missing fundamentals": df[NEEDED].isna().any(axis=1),
        "missing price history": df[["mom_12_1", "vol_1y"]].isna().any(axis=1),
        "quote vs daily close differ >1%": (df["tdx_close"] / df["price"] - 1).abs() > 0.01,
        "P/E disagrees with source": df["pe_ttm_em"].notna() & (((df["pe_ttm_em"] > 0) != (df["np_ttm"] > 0))
                                                              | ((df["pe"] / df["pe_ttm_em"]).sub(1).abs() > 0.5)),
        "P/B disagrees with source": (df["pb"] / df["pb_mrq_em"]).sub(1).abs() > 0.5,
    }
    return finish(df, info, checks | crosscheck.checks(df, "cn", info))


def us_fundamentals() -> pd.DataFrame:
    """SEC companyfacts rows, and Yahoo rows for the companies SEC has no recent quarterly numbers for
    (mostly foreign filers), converted to US dollars."""
    money = ["revenue_ttm", "np_ttm", "gp_ttm", "ocf_ttm", "equity", "liabilities", "assets"]
    cols = ["period", "notice_date", "rev_yoy", "np_yoy", "source", "currency"] + money
    read = lambda p: pd.read_csv(p, dtype={"code": str, "period": str, "notice_date": str})
    facts = read(sec.TABLE)
    facts = facts[sec.covered(facts)].assign(source="SEC", currency="USD")
    gaps = read(yahoo.GAPS) if yahoo.GAPS.exists() else pd.DataFrame(columns=["code", "yahoo"])
    gaps = gaps[gaps["yahoo"] == "ok"].assign(source="Yahoo").reindex(columns=["code"] + cols)
    gaps[money] = gaps[money].div(gaps["currency"].map(yahoo.load_fx()), axis=0)
    both = pd.concat([facts, gaps[~gaps["code"].isin(facts["code"])]]).set_index("code")[cols]
    # a quarter of SEC filers tag neither gross profit nor a cost of revenue (Mastercard, Oracle, GE): Yahoo's
    # standardized gross profit (the cross-checks' second source) fills it, in USD
    yahoo_gp = gaps.set_index("code")["gp_ttm"]
    both["gp_ttm"] = both["gp_ttm"].fillna(yahoo_gp[~yahoo_gp.index.duplicated()].reindex(both.index))
    return both


def join_consensus(df: pd.DataFrame, path: Path, cols: list[str]) -> pd.DataFrame:
    cons = pd.read_csv(path, dtype={"code": str}).set_index("code") if path.exists() else pd.DataFrame()
    df = df.join(cons.reindex(columns=cols))
    df["analysts"] = df["analysts"].fillna(0)
    return df


def build_us(today: date) -> tuple[pd.DataFrame, dict]:
    prices = yahoo.load_prices()
    last = str(trading_days(prices)[-1])
    info = {"quote_date": last, "price_date": last, "stages": {}, "dropped": {}}
    codes = nasdaq.candidates()
    df = nasdaq.load_list().drop_duplicates("code").set_index("code").loc[codes]
    info["stages"][f"ordinary shares (largest {len(codes)})"] = len(df)
    df = screen(df, prices, today, "us", info)
    df["cik"] = sec.load_ciks().reindex(df.index)
    by_turnover = df.sort_values("turnover_20d", ascending=False)
    df = df.loc[by_turnover.index[~(by_turnover["cik"].notna() & by_turnover["cik"].duplicated())]]
    info["stages"]["one share class per issuer"] = len(df)

    recent = prices[prices["date"].isin(np.sort(prices["date"].unique())[-3:])]
    closes = recent.pivot(index="code", columns="date", values="close").reindex(df.index)
    df["price"] = closes[last]
    df["shares"] = df["mcap"] / df["last"]  # the screener's market value is company-wide; its price can lag a day
    df["mcap"] = df["shares"] * df["price"]
    df = top_by_value(df, info)
    df = df.join(price_metrics(prices, list(df.index)))
    df = df.join(us_fundamentals())
    df["bps"] = df["equity"] / df["shares"]
    df["debt_ratio"] = df["liabilities"] / df["assets"]
    df["gross_margin"] = df["gp_ttm"] / df["revenue_ttm"]
    df["cash_conv"] = (df["ocf_ttm"] / df["np_ttm"]).where(df["np_ttm"] > 0)
    df["rev_growth"], df["np_growth"] = df["rev_yoy"], df["np_yoy"]
    df["dps_ttm"] = dividends(Path(str(yahoo.DIVIDENDS).format("us")), today).reindex(df.index).fillna(0)
    df = ratios(join_consensus(df, nasdaq.CONSENSUS, ["analysts", "e1_year", "eps_e1", "eps_e2", "eps_e3"]))

    listed_px = (closes.loc[df.index].div(df["last"], axis=0) - 1).abs().min(axis=1)
    checks = {
        "no recent fundamentals (SEC or Yahoo)": df["source"].isna(),
        "missing fundamentals": df[NEEDED].isna().any(axis=1),
        "missing price history": df[["mom_12_1", "vol_1y"]].isna().any(axis=1),
        "listing price vs Yahoo closes differ >1%": listed_px > 0.01,
    }
    df["financial"] = df["industry"].isin(CONFIG["peers"]["financial_industries_us"])
    df["sector"] = df["sector"].replace("", np.nan).fillna("Miscellaneous")
    return finish(df, info, checks | crosscheck.checks(df, "us", info))


def hk_fundamentals(currency: pd.Series) -> pd.DataFrame:
    """The latest Eastmoney report per company with TTM revenue and profit, in HKD. Eastmoney converts
    every company's amounts to CNY at each period-end rate: they go back to the reporting currency at
    that rate (Yahoo's close, ~0.5% from Eastmoney's) before the TTM sum, then to HKD at today's rate. Year-to-date
    revenue, profit and operating cash flow stay in the reporting currency (their ratios are what's used)."""
    rows = pd.read_csv(eastmoney.HK_RESULTS, dtype={"code": str, "period": str, "start": str, "date_type": str})
    rows["currency"] = rows["code"].map(currency)
    rows = rows[rows["currency"].notna()]
    money = ["revenue", "np", "bps", "ocf"]
    rows[money] = rows[money].div(yahoo.cny_per(rows["currency"], rows["period"]), axis=0)
    df, fx = ttm(rows), yahoo.load_fx()
    df[["revenue_ttm", "np_ttm", "bps"]] = df[["revenue_ttm", "np_ttm", "bps"]].mul(df["currency"].map(fx["HKD"] / fx), axis=0)
    return df


def build_hk(today: date) -> tuple[pd.DataFrame, dict]:
    prices = yahoo.load_prices("hk")
    last = str(trading_days(prices)[-1])
    info = {"quote_date": last, "price_date": last, "stages": {}, "dropped": {}}
    codes = eastmoney.hk_candidates()
    df = eastmoney.load_hk_list().drop_duplicates("code").set_index("code").loc[codes]
    info["stages"][f"ordinary shares (largest {len(codes)})"] = len(df)
    df = screen(df, prices, today, "hk", info)
    cons = join_consensus(df[[]], yahoo.CONSENSUS, ["analysts", "e1_year", "currency", "report_currency",
                                                    "eps_e0", "eps_e1", "eps_e2"])
    df = df.join(hk_fundamentals(cons["report_currency"].dropna()).drop(columns="currency"))
    df["price"] = prices[prices["date"] == last].set_index("code")["close"].reindex(df.index)
    df["mcap"] = df["price"] * df["shares"]  # all issued shares (H + A + unlisted) at the HK price
    df = top_by_value(df, info)
    df = df.join(price_metrics(prices, list(df.index)))
    df["gross_margin"], df["debt_ratio"] = df["gross_margin"] / 100, df["debt_ratio"] / 100
    df["cash_conv"] = (df["ocf"] / df["np"]).where(df["np"] > 0)
    df["revenue_ytd"], df["np_ytd"], df["ocf_ytd"] = df["revenue"], df["np"], df["ocf"]  # reporting currency
    df["rev_growth"], df["np_growth"] = df["rev_yoy"] / 100, df["np_yoy"] / 100  # year to date, reporting currency
    df["dps_ttm"] = dividends(Path(str(yahoo.DIVIDENDS).format("hk")), today).reindex(df.index).fillna(0)
    est, fx = ["eps_e0", "eps_e1", "eps_e2"], yahoo.load_fx()
    cons[est] = cons[est].mul(cons["currency"].map(fx["HKD"] / fx), axis=0)
    df = ratios(df.join(cons[["analysts", "e1_year"] + est]).assign(eps_e3=np.nan, notice_date=None))  # no filing dates
    # Yahoo has two estimate years, so the 2-year expected EPS growth runs from last year's actual to next year
    df["fwd_growth"] = (df["eps_e2"] / df["eps_e0"]).where((df["eps_e0"] > 0) & (df["eps_e2"] > 0)) ** 0.5 - 1
    df["financial"] = df["industry_type"].fillna("").str.split("-").str[-1].isin(CONFIG["peers"]["financial_industries_hk"])
    df["sector"] = df["industry_type"].fillna("").str.split("-").str[0].replace("", "未分类")
    df["lot"] = hkex.load_lots().reindex(df.index)

    checks = {
        "no reporting currency (Yahoo)": cons["report_currency"].reindex(df.index).isna(),
        "missing fundamentals": df[NEEDED].isna().any(axis=1),
        "no report in the last 300 days": pd.to_datetime(df["period"]) < pd.Timestamp(today - timedelta(days=300)),
        "missing price history": df[["mom_12_1", "vol_1y"]].isna().any(axis=1),
        "P/E disagrees with source": df["pe_ttm_em"].notna() & (((df["pe_ttm_em"] > 0) != (df["np_ttm"] > 0))
                                                              | ((df["pe"] / df["pe_ttm_em"]).sub(1).abs() > 0.5)),
        "P/B disagrees with source": (df["pb"] / df["pb_ttm_em"]).sub(1).abs() > 0.5,
    }
    return finish(df, info, checks | crosscheck.checks(df, "hk", info))
