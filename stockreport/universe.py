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
from stockreport.fetch import eastmoney, frames, hkex, index, nasdaq, sec, swclass, tdx, yahoo
from stockreport.research.sheet import ebit
from stockreport.signals import forward, fy_end

log = logging.getLogger(__name__)
A_SHARE = re.compile(r"^(60[0-5]\d{3}|68[89]\d{3}|00[0-3]\d{3}|30[01]\d{3})$")
NEEDED = ["np_ttm", "revenue_ttm", "bps"]  # a stock without these is dropped (rule 5); growth isn't scored
CN_FINANCIAL = ["银行", "非银金融"]  # 申万 level 1: banks, brokers, insurers and 多元金融 (leasing, trusts)
# The score's financials (PLAN.md, "How each ingredient is built"): banks, insurers, brokers and other lenders, whose
# balance sheet is the product. US: SEC SIC 6000-6199 (credit institutions) and 6300-6399 (insurance carriers) too.
US_SIC = [(6000, 6199), (6300, 6399)]
# The financial sector, whose leverage isn't read (fin_sector): US SIC 6000-6499, finance and insurance.
FIN_SIC = (6000, 6499)
LAG_DAYS = 185  # statement_ebit: at most one half-year report behind the card's figures
CONSENSUS = ["analysts", "e1_year", "eps_e1", "eps_e2", "eps_e3"]  # CN and US: three estimate years


def us_sic(cik: pd.Series) -> pd.Series:
    """Each stock's SEC SIC code by its CIK (frames.SIC; NaN where unknown)."""
    codes = pd.read_csv(frames.SIC, dtype={"code": str}).drop_duplicates("code").set_index("code")["sic"] \
        if frames.SIC.exists() else pd.Series(dtype=float)
    return codes.reindex(cik.dropna().astype("int64").astype(str)).set_axis(cik.dropna().index).reindex(cik.index)


def us_financial(industry: pd.Series, cik: pd.Series) -> pd.Series:
    """Nasdaq's bank, broker and insurer industries, or a lender or insurer by its SEC SIC code (Nasdaq puts AmEx,
    Synchrony and SoFi under "Finance: Consumer Services" with Moody's and Equifax)."""
    sic = us_sic(cik).reindex(industry.index)
    return industry.isin(CONFIG["peers"]["financial_industries_us"]) | sum(sic.between(lo, hi) for lo, hi in US_SIC).astype(bool)


def fin_sector(df: pd.DataFrame, market: str) -> pd.Series:
    """The financial sector (PLAN.md, "Lists", Sell): the score's financials and the fee businesses beside them (asset
    managers, insurance brokers, exchanges), whose consolidated liabilities are largely clients' money, policies or
    their funds' debt, so leverage doesn't mean distress there (Fama and French 1992; Ohlson 1980 fitted his failure
    score without them). The failure logit (signals.distress) and debt ÷ assets aren't read for them. CN 申万 银行 and
    非银金融 (the score's financials already); HK Eastmoney's 金融 sector; US SEC SIC 6000-6499 (finance and insurance:
    real estate and REITs, 6500 and up, borrow against their own assets)."""
    fin = df["financial"].astype(bool)
    if market == "hk":
        return fin | (df["sector"] == "金融")
    if market == "us":
        return fin | us_sic(df["cik"]).between(*FIN_SIC)
    return fin


def load_results(table: str = "results") -> pd.DataFrame:
    """All saved CN report periods of a table (cn_<table>_<period>.csv.gz), with a period column."""
    paths = sorted((DATA / "fundamentals").glob(f"cn_{table}_*.csv.gz"))
    if not paths:
        return pd.DataFrame(columns=["code", "period"])
    return pd.concat([pd.read_csv(p, dtype={"code": str, "notice_date": str}).assign(period=p.name[4 + len(table):-7])
                      for p in paths], ignore_index=True)


def ttm(results: pd.DataFrame, need: list[str] | None = None) -> pd.DataFrame:
    """Latest report per stock, plus trailing-12-month revenue and profit (and 扣非 EPS where the table has it), or the
    `need` columns: TTM = year-to-date + last full year - same period of last year; the fiscal year starts on the row's
    `start` (HK) or Jan 1."""
    cols = need or ["revenue", "np"] + (["eps_deduct"] if "eps_deduct" in results else [])
    results = results.dropna(subset=need or ["revenue", "np"])
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


def moved(prices: pd.DataFrame, day: str | None) -> pd.Series:
    """Each stock's price change after `day` (chained close ÷ previous close, so bonus shares and splits don't count)."""
    after = prices[prices["date"] > day] if day else prices.iloc[:0]
    return (after["close"] / after["prev_close"]).groupby(after["code"]).prod()


def cn_float(mcap: pd.Series, weights: pd.Series, since: pd.Series | None = None) -> pd.Series:
    """CN free-float value: market value × the CSI 300's float factor (a member's index weight over its share of the
    members' market value; the median factor outside the index), as total value counts state holdings that never
    trade (PLAN.md, "Lists"). The weights are CSI's month-end file's, so each member's value is taken at that date
    (today's ÷ its price change `since`): with today's, a member that fell after the month end got a factor larger in
    proportion. Market value where the file is missing."""
    w = weights.reindex(mcap.index).dropna()
    if w.empty:
        return mcap
    then = mcap[w.index] / (since.reindex(w.index).fillna(1.0) if since is not None else 1.0)
    factor = (w / w.sum()) / (then / then.sum())
    return mcap * factor.reindex(mcap.index).fillna(factor.median())


def statement_ebit(rows: pd.DataFrame, market: str, period: pd.Series) -> pd.Series:
    """Trailing-12-month EBIT from Eastmoney's income lines (eastmoney.CN_EBIT, eastmoney.HK_EBIT), each report's on
    research/sheet.ebit's definitions (the research report's operating profit: without investment income, fair-value
    changes and interest income, plus interest expense), summed like revenue (ttm). Kept where its latest report is
    at most LAG_DAYS older than the one the rest of the stock's figures come from (`period`): Eastmoney updates its HK
    statements and main indicators on different days (on 2026-11-28 中国石油's Q3 had indicators and no statement,
    小米's the reverse), and a newer statement is kept; an older one, or none, leaves Yahoo's (yahoo_balance)."""
    if rows.empty:
        return pd.Series(np.nan, index=period.index)
    if "start" in rows:  # a fiscal-year change gives two reports for one period end (00653's 2024-12-31): the new year's
        rows = rows.sort_values("start").drop_duplicates(["code", "period"], keep="last")
    rows = rows.assign(ebit=ebit(market, rows))
    t = ttm(rows, ["ebit"]).reindex(period.index)
    lag = (pd.to_datetime(period) - pd.to_datetime(t["period"])).dt.days
    return t["ebit_ttm"].where(lag <= LAG_DAYS)


def yahoo_balance(df: pd.DataFrame, market: str, quote: str) -> pd.DataFrame:
    """Trailing EBIT and Yahoo's latest debt, cash (with short-term investments), minorities, preferred stock and
    liabilities in the quote currency (fetch/yahoo.py), EV = market value + debt + minorities + preferred stock − cash
    (the claims ahead of common holders, at carrying value: preferred stock, and in CN the perpetual bonds booked as
    equity; the book value and earnings per share already leave them out, history.py), and the latest fiscal year's
    scaled total accruals (sta, the buys' screen). EBIT is the operating profit of the company's own statements (op_ttm,
    quote currency): what US filers report to the SEC as operating income where they tag it, CN and HK operating profit
    from Eastmoney's statements (statement_ebit); else Yahoo's, which is pretax profit plus interest and so carries
    investment gains, fair-value changes and one-off items below operating income (PLAN.md, EBIT/EV). A debt, minorities or preferred line Yahoo doesn't list is none; without a cash line the
    balance sheet wasn't read: no EBIT or no cash leaves EBIT/EV out (rule 5)."""
    path = yahoo.gaps_path(market)
    y = pd.read_csv(path, dtype={"code": str}).drop_duplicates("code", keep="last").set_index("code") \
        if path.exists() else pd.DataFrame(columns=["yahoo", "currency"])
    y = y[y["yahoo"] == "ok"].reindex(df.index).reindex(columns=["currency", "ebit_ttm", "debt", "cash", "minority",
                                                                  "pref", "other_equity", "liabilities", "sta"])
    fx = yahoo.load_fx()
    rate = (fx.get(quote, np.nan) / y["currency"].map(fx)).where(y["currency"] != quote, 1.0)
    if market == "cn":  # China's 其他权益工具 (preferred shares and perpetual bonds) is Yahoo's OtherEquityInterest, equal to
        # Eastmoney's line (招商银行 199.989bn, 比亚迪 17.08bn) and holding the preferred shares: the larger line. In the
        # US and HK that line is other reserves (携程's equals its whole equity), so they take the preferred stock only
        y["pref"] = y[["pref", "other_equity"]].clip(lower=0).max(axis=1)
    items = y[["debt", "cash", "minority", "pref", "liabilities"]].mul(rate, axis=0)
    ebit = y["ebit_ttm"] * rate
    if "op_ttm" in df:
        ebit = df["op_ttm"].where(df["op_ttm"].notna(), ebit)
    have = ebit.notna()
    ev = df["mcap"] + (items[["debt", "minority", "pref"]].fillna(0).sum(axis=1) - items["cash"]).where(have)
    return df.assign(ebit=ebit, ev=ev, cash=items["cash"].where(have), liab_y=items["liabilities"],
                     sta=y["sta"])


def estimates(df: pd.DataFrame, table: pd.DataFrame, per_unit: pd.Series) -> pd.DataFrame:
    """Next year's consensus EPS now and 90 days ago (est_now, est_90; Yahoo's +1y) in the quote currency
    (`per_unit`: quote-currency units per estimate-currency unit, per stock), its analyst count (est_n) and fiscal year
    (rev_year). Yahoo shows 0 where it has no 90-day-old figure (yahoo.parse_trend): missing."""
    t = table.reindex(df.index)
    return df.assign(est_now=t["eps_e2"] * per_unit, est_90=t["eps_e2_90"].replace(0, np.nan) * per_unit,
                     est_n=t["analysts"].fillna(0), rev_year=fy_end(t["e1_year"]).dt.year + 1)


def trading_days(prices: pd.DataFrame) -> np.ndarray:
    """The market's trading days: days with prices for at least half as many stocks as its busiest day, so one
    stock's stray newer row doesn't make a day, and an index that skipped a day (Yahoo's ^HSI, 2026-10-20) doesn't
    remove one."""
    n = prices.groupby("date")["code"].nunique()
    return np.sort(n.index[n >= n.max() / 2].to_numpy())


def price_metrics(prices: pd.DataFrame, codes: list[str]) -> pd.DataFrame:
    """12-1 month momentum, the 12- and 6-month returns (the distress probability; a card's key risk) and 1-year and
    3-month volatility from returns chained as close / prev-close (ex-rights adjusted), on the market's trading days."""
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
    if len(t0):
        out["ret_12m"] = (level.iloc[-1] / level.loc[t0[-1]] - 1).where(first <= t0[-1])
    if len(t6):
        out["ret_6m"] = (level.iloc[-1] / level.loc[t6[-1]] - 1).where(first <= t6[-1])
    year, quarter = wide[wide.index > (last - timedelta(days=365)).isoformat()], wide.iloc[-63:]
    out["vol_1y"] = year.std() * np.sqrt(252)
    out.loc[year.count() < 120, "vol_1y"] = np.nan
    out["vol_3m"] = (quarter.std() * np.sqrt(252)).where(quarter.count() >= 40)  # the distress model's SIGMA
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
    df["fwd_pe"] = (df["price"] / df["eps_ntm"]).where(df["eps_ntm"] > 0) if "eps_ntm" in df else np.nan  # signals.forward
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
    df = ratios(forward(join_consensus(df, DATA / "fundamentals" / "cn_consensus.csv.gz", CONSENSUS), today))
    df["rev_growth"] = df["rev_yoy"] / 100
    df["np_growth"] = df["np_yoy"] / 100
    df["gross_margin"] = df["gross_margin"] / 100
    df["cash_conv"] = (df["ocfps"] / df["eps"]).where(df["eps"] > 0)
    df["sector"] = swclass.level1().reindex(df.index).fillna("未分类")
    df["financial"] = df["sector"].isin(CN_FINANCIAL)
    df["fin_sector"] = fin_sector(df, "cn")
    df["float_value"] = cn_float(df["mcap"], index.load(), moved(prices, index.as_of()))
    df["op_ttm"] = statement_ebit(load_results("ebit"), "cn", df["period"])
    df = yahoo_balance(df, "cn", "CNY")

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
    money = ["revenue_ttm", "np_ttm", "gp_ttm", "ocf_ttm", "op_ttm", "equity", "liabilities", "assets"]
    cols = ["period", "notice_date", "rev_yoy", "np_yoy", "source", "currency"] + money
    read = lambda p: pd.read_csv(p, dtype={"code": str, "period": str, "notice_date": str})
    facts = read(sec.TABLE)
    facts = facts[sec.covered(facts)].assign(source="SEC", currency="USD")
    gaps = read(yahoo.GAPS) if yahoo.GAPS.exists() else pd.DataFrame(columns=["code", "yahoo"])
    gaps = gaps[gaps["yahoo"] == "ok"].assign(source="Yahoo").reindex(columns=["code"] + cols)
    gaps[money] = gaps[money].div(gaps["currency"].map(yahoo.load_fx()), axis=0)
    both = pd.concat([facts, gaps[~gaps["code"].isin(facts["code"])]]).set_index("code").reindex(columns=cols)
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
    df = nasdaq.named(nasdaq.load_list().drop_duplicates("code").set_index("code").loc[codes])  # Yahoo's names
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
    df = crosscheck.us_shares(df)  # against SEC's and Yahoo's counts: kept, set to SEC's, or dropped below
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
    df = ratios(forward(join_consensus(df, nasdaq.CONSENSUS, CONSENSUS), today))
    trend = pd.read_csv(yahoo.US_TREND, dtype={"code": str}).set_index("code") if yahoo.US_TREND.exists() else \
        pd.DataFrame(columns=["e1_year", "eps_e2", "eps_e2_90", "analysts", "currency"])
    df = estimates(df, trend, 1 / trend["currency"].map(yahoo.load_fx()).reindex(df.index))
    df = yahoo_balance(df, "us", "USD").assign(float_value=df["mcap"])  # US float ≈ total value by sector (PLAN.md, "Lists")

    # the screener's price against the closes up to its own day: a failed fetch keeps an older list (2026-11-12: the
    # 11-10 list against 11-11's closes dropped 456 names that had simply moved), and its shares are still good
    fetched = nasdaq.load_list()["fetched"].astype(str).str[:10]
    days = np.sort(prices["date"].unique())
    near = days[days <= fetched.max()][-3:] if len(fetched) and (days <= fetched.max()).any() else days[-3:]
    near_closes = prices[prices["date"].isin(near)].pivot(index="code", columns="date", values="close").reindex(df.index)
    listed_px = (near_closes.div(df["last"], axis=0) - 1).abs().min(axis=1)
    checks = {
        "no recent fundamentals (SEC or Yahoo)": df["source"].isna(),
        "missing fundamentals": df[NEEDED].isna().any(axis=1),
        "missing price history": df[["mom_12_1", "vol_1y"]].isna().any(axis=1),
        "listing price vs Yahoo closes differ >1%": listed_px > 0.01,
    }
    df["financial"] = us_financial(df["industry"], df["cik"])
    df["sector"] = df["sector"].replace("", np.nan).fillna("Miscellaneous")
    df["fin_sector"] = fin_sector(df, "us")
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
    if eastmoney.HK_EBIT.exists():  # the same way: CNY at each period end's rate, back to the reporting currency, HKD
        lines = pd.read_csv(eastmoney.HK_EBIT, dtype={"code": str, "period": str, "start": str, "date_type": str})
        lines = lines.assign(currency=lines["code"].map(currency)).dropna(subset=["currency"])
        money = ["pretax", "interest", "interest_income", "invest_income"]
        lines[money] = lines[money].div(yahoo.cny_per(lines["currency"], lines["period"]), axis=0)
        df["op_ttm"] = statement_ebit(lines, "hk", df["period"]) * df["currency"].map(fx["HKD"] / fx)
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
                                                    "eps_e0", "eps_e1", "eps_e2", "eps_e2_90"])
    df = df.join(hk_fundamentals(cons["report_currency"].dropna()).drop(columns="currency"))
    df["price"] = prices[prices["date"] == last].set_index("code")["close"].reindex(df.index)
    df["mcap"] = df["price"] * df["shares"]  # all issued shares (H + A + unlisted) at the HK price
    df = top_by_value(df, info)
    df = df.join(price_metrics(prices, list(df.index)))
    df["gross_margin"], df["debt_ratio"] = df["gross_margin"] / 100, df["debt_ratio"] / 100
    df["cash_conv"] = (df["ocf"] / df["np"]).where(df["np"] > 0)
    df["revenue_ytd"], df["np_ytd"], df["ocf_ytd"] = df["revenue"], df["np"], df["ocf"]  # reporting currency
    df["report_currency"] = cons["report_currency"].reindex(df.index)  # the deep dive's data check compares np_ytd
    df["rev_growth"], df["np_growth"] = df["rev_yoy"] / 100, df["np_yoy"] / 100  # year to date, reporting currency
    df["dps_ttm"] = dividends(Path(str(yahoo.DIVIDENDS).format("hk")), today).reindex(df.index).fillna(0)
    est, fx = ["eps_e0", "eps_e1", "eps_e2", "eps_e2_90"], yahoo.load_fx()
    cons[est] = cons[est].mul(cons["currency"].map(fx["HKD"] / fx), axis=0)
    df = ratios(forward(df.join(cons[["analysts", "e1_year"] + est]).assign(eps_e3=np.nan, notice_date=None), today))
    df = estimates(df, cons, 1.0)  # already in HKD
    listed = pd.read_csv(yahoo.HK_SHARES, dtype={"code": str}).drop_duplicates("code").set_index("code")["shares_class"] \
        if yahoo.HK_SHARES.exists() else pd.Series(dtype=float)
    listed = listed.reindex(df.index)  # HK-listed shares only (an A+H issuer's H shares); never more than all shares
    df["listed_value"] = listed.where(listed <= df["shares"], df["shares"]) * df["price"]
    df["float_value"] = df["listed_value"].fillna(df["mcap"])  # what can be bought in HK (PLAN.md, "Lists")
    df = yahoo_balance(df, "hk", "HKD")
    # Yahoo has two estimate years, so the 2-year expected EPS growth runs from last year's actual to next year
    df["fwd_growth"] = (df["eps_e2"] / df["eps_e0"]).where((df["eps_e0"] > 0) & (df["eps_e2"] > 0)) ** 0.5 - 1
    df["financial"] = df["industry_type"].fillna("").str.split("-").str[-1].isin(CONFIG["peers"]["financial_industries_hk"])
    df["sector"] = df["industry_type"].fillna("").str.split("-").str[0].replace("", "未分类")
    df["fin_sector"] = fin_sector(df, "hk")
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
