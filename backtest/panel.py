"""Point-in-time snapshots for the backtest: for every month end, the v1 snapshot columns built only from
what was public that day, and the stocks' forward returns. CN from data/backtest (Eastmoney valuation
history until the 通达信 packages start in 2021-08, then the packages; 业绩报表 by notice date; 申万 industry
of the day). US and HK from data/history: today's candidates only (survivors), today's industries, annual
SEC reports by filing date (US) and Eastmoney results 90 days after the period (HK)."""

import os
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

from stockreport import history, universe
from stockreport.config import CONFIG, DATA
from stockreport.fetch import nasdaq, sec

BT = DATA / "backtest"
HIST = BT / "history"  # history tables as the v2 code reads them (CN rebuilt point-in-time, US/HK linked)
A_SHARE = re.compile(r"^(60[0-5]\d{3}|68[89]\d{3}|00[0-3]\d{3}|30[01]\d{3})$")
HORIZONS = {"1m": 30, "3m": 91, "12m": 365}  # calendar days (CN); 1, 3, 12 months (US, HK)
PREMIUM = CONFIG["value"]["equity_premium"]
HK_TOP = 410  # HK: the turnover screen needs volumes the monthly table lacks; ~410 names pass it today (Method 1)
FIN_SW = ("48", "4901", "4902")  # 申万 banks (L1), brokers and insurers (L2)


def setup_history(market: str) -> None:
    """data/backtest/history: CN annual results since 2009, half-year P/B since 2018-06 and 业绩预告 since
    2017-10, rebuilt from the backtest tables; US/HK tables linked from data/history."""
    HIST.mkdir(parents=True, exist_ok=True)
    history.HISTORY = HIST
    for name in ("us_annual", "us_monthly", "us_splits", "hk_results", "hk_monthly", "hk_splits"):
        link = HIST / f"{name}.csv.gz"
        if not link.exists():
            os.symlink(os.path.relpath(DATA / "history" / f"{name}.csv.gz", HIST), link)
    if market != "cn":
        return
    res = cn_results()
    res[res["period"].str.endswith("12-31")].to_csv(HIST / "cn_annual.csv.gz", index=False, compression="gzip")
    val = cn_valuations()
    half = val[val["date"].isin(half_year_ends(val["date"].unique()))]
    half = half.rename(columns={"date": "trade_date", "pb": "pb_mrq", "pe": "pe_ttm"})
    half["period"] = half["trade_date"].str[:4] + np.where(half["trade_date"].str[5:7] == "06", "-06-30", "-12-31")
    half[["code", "trade_date", "close", "mcap", "shares", "pe_ttm", "pb_mrq", "period"]].to_csv(
        HIST / "cn_valuation.csv.gz", index=False, compression="gzip")
    pd.read_csv(BT / "cn_forecasts.csv.gz", dtype=str).to_csv(HIST / "cn_forecasts.csv.gz", index=False, compression="gzip")


def half_year_ends(days) -> list[str]:
    days = sorted(days)
    return [d for d, n in zip(days, days[1:] + ["9999"]) if d[5:7] in ("06", "12") and n[:7] != d[:7]]


def calendar() -> list[str]:
    return pd.read_csv(BT / "calendar.csv")["date"].tolist()


def month_ends(days: list[str], start: str, end: str) -> list[str]:
    return [d for d, n in zip(days, days[1:] + ["9999"]) if start <= d <= end and n[:7] != d[:7]]


# ---------------------------------------------------------------- CN

def cn_results() -> pd.DataFrame:
    """业绩报表 for every quarter since 2009; a missing notice date is filled with the statutory deadline."""
    r = pd.read_csv(BT / "cn_results.csv.gz", dtype={"code": str, "notice_date": str, "period": str})
    deadline = pd.to_datetime(r["period"]) + pd.to_timedelta(np.where(r["period"].str[5:7] == "12", 120, 62), unit="D")
    r["notice_date"] = r["notice_date"].fillna(deadline.dt.strftime("%Y-%m-%d"))
    return r[r["code"].str.match(A_SHARE)]


def cn_valuations() -> pd.DataFrame:
    """Eastmoney's daily valuation rows on month ends (and every day before the packages): close, market
    value, shares, PE, PB and industry name, survivors only."""
    days = calendar()
    ends = set(month_ends(days, "2018-01-01", "9999"))
    frames = [pd.read_csv(p, dtype={"code": str}) for p in sorted((BT / "cn_val_daily").glob("*.csv.gz"))]
    daily = pd.concat(frames)
    out = pd.concat([daily[daily["date"].isin(ends)], pd.read_csv(BT / "cn_val_month.csv.gz", dtype={"code": str})])
    return out.drop_duplicates(["date", "code"])


class CNPrices:
    """Daily matrices (trading day × A-share): gross return, close, turnover (¥, packages only) and
    whether the stock traded; Eastmoney's daily change before the 通达信 packages, close / exchange
    prev-close after. Cached in data/backtest/cn_daily.npz."""

    def __init__(self):
        path = BT / "cn_daily.npz"
        if not path.exists():
            self.build(path)
        z = np.load(path, allow_pickle=False)
        self.days, self.codes = z["days"].astype(str), z["codes"].astype(str)
        self.ret, self.close, self.amount, self.traded = z["ret"], z["close"], z["amount"], z["traded"]
        self.col = {c: i for i, c in enumerate(self.codes)}
        self.level = np.cumprod(np.nan_to_num(self.ret, nan=1.0), axis=0)
        self.index = self.csi300()

    @staticmethod
    def build(path) -> None:
        start = (BT / "tdx_start.txt").read_text().strip()
        days = np.array(calendar())
        em = pd.concat([pd.read_csv(p, dtype={"code": str}, usecols=["code", "date", "close", "chg"])
                        for p in sorted((BT / "cn_val_daily").glob("*.csv.gz"))])
        em = em[(em["date"] < start) & em["code"].str.match(A_SHARE)]
        em = em.assign(ret=1 + em["chg"] / 100, amount=np.nan, traded=em["chg"].notna())
        tdx = pd.concat([pd.read_csv(p, dtype={"code": str}, usecols=["date", "code", "close", "prev_close", "volume", "amount"])
                         for p in sorted((BT / "tdx").glob("*.csv.gz"))])
        tdx = tdx[tdx["code"].str.match(A_SHARE) & (tdx["date"] >= start)]
        tdx = tdx.assign(ret=np.where(tdx["volume"] > 0, tdx["close"] / tdx["prev_close"], 1.0), traded=tdx["volume"] > 0)
        both = pd.concat([em[["date", "code", "close", "ret", "amount", "traded"]],
                          tdx[["date", "code", "close", "ret", "amount", "traded"]]])
        codes = np.array(sorted(both["code"].unique()))
        r, c = np.searchsorted(days, both["date"].to_numpy()), np.searchsorted(codes, both["code"].to_numpy())
        mats = {}
        for name, fill, dtype in (("ret", np.nan, np.float32), ("close", np.nan, np.float32),
                                  ("amount", np.nan, np.float32), ("traded", False, bool)):
            m = np.full((len(days), len(codes)), fill, dtype=dtype)
            m[r, c] = both[name].to_numpy()
            mats[name] = m
        np.savez_compressed(path, days=days, codes=codes, **mats)

    @staticmethod
    def csi300() -> pd.Series:
        early = pd.read_csv(BT / "csi300_early.csv").set_index("date")["close"]
        late = pd.concat([pd.read_csv(p, dtype={"code": str}) for p in sorted((BT / "tdx").glob("*.csv.gz"))])
        late = late[late["code"] == "CSI300"].set_index("date")["close"]
        out = pd.concat([early[early.index < late.index.min()], late])
        return out.set_axis(pd.to_datetime(out.index)).sort_index()

    def at(self, day: str, back_days: int = 0) -> int:
        """Row of the last trading day on or before `day` minus `back_days` calendar days."""
        target = (date.fromisoformat(day) - timedelta(days=back_days)).isoformat()
        return int(np.searchsorted(self.days, target, side="right")) - 1

    def metrics(self, day: str, codes: list[str]) -> pd.DataFrame:
        """12-1 month momentum, 1-year volatility, 20-day turnover, first trading day (as universe.py)."""
        cols = [self.col[c] for c in codes]
        t, t0, t1 = self.at(day), self.at(day, 365), self.at(day, 30)
        lv = self.level[:, cols]
        first = self.traded[:, cols].argmax(axis=0)
        year = slice(t0 + 1, t + 1)
        r = np.where(self.traded[year][:, cols], self.ret[year][:, cols] - 1, np.nan)
        n = np.isfinite(r).sum(axis=0)
        amount = self.amount[t - 19: t + 1, cols]
        return pd.DataFrame({
            "mom_12_1": np.where((first <= t0) & (t0 >= 0), lv[t1] / lv[t0] - 1, np.nan),
            "vol_1y": np.where(n >= 120, np.nanstd(r, axis=0, ddof=1) * np.sqrt(252), np.nan),
            "turnover_20d": np.nanmean(amount, axis=0) if np.isfinite(amount).any() else np.nan,
            "traded_today": self.traded[t, cols], "first_day": self.days[first]}, index=codes)

    def forward(self, day: str, codes: list[str]) -> pd.DataFrame:
        """Total return from the close of `day` to the last close on or before 30 / 91 / 365 days later
        (NaN when that is beyond the data); a stock that stopped trading stays flat after its last day."""
        cols, t, last = [self.col[c] for c in codes], self.at(day), self.days[-1]
        out = pd.DataFrame(index=codes)
        for h, n in HORIZONS.items():
            end = (date.fromisoformat(day) + timedelta(days=n)).isoformat()
            if end > last:
                out[f"ret_{h}"] = np.nan
                continue
            e = self.at(end)
            out[f"ret_{h}"] = self.level[e, cols] / self.level[t, cols] - 1
            out[f"idx_{h}"] = self.index.asof(pd.Timestamp(str(self.days[e]))) / self.index.asof(pd.Timestamp(str(self.days[t]))) - 1
        return out


def sw_industry(day: str, codes) -> pd.Series:
    """申万 code of the day per stock (the last change on or before it)."""
    sw = pd.read_csv(BT / "sw_history.csv.gz", dtype=str)
    sw = sw[(sw["start"] <= day) & sw["code"].isin(set(codes))].sort_values("start").groupby("code").last()
    return sw["sw"].reindex(codes)


def cn_snapshot(day: str, px: CNPrices, res: pd.DataFrame, bal: pd.DataFrame, val: pd.DataFrame,
                names: pd.DataFrame, rates: pd.Series, consensus: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """The CN v1 snapshot of `day` (a month end), as universe.build_cn builds it, from what was public."""
    info = {"stages": {}, "dropped": {}}
    q = val[val["date"] == day].set_index("code")
    q = q[q.index.str.match(A_SHARE) & q.index.isin(px.col)]
    info["stages"]["A-shares in Eastmoney's table (survivors)"] = len(q)
    st = names[(names["date"] == day) & names["name"].str.contains("ST|退", regex=True)]["code"]
    q = q[~q.index.isin(set(st))]
    info["stages"]["not ST / delisting (通达信 names, 2021-08+)"] = len(q)
    m = px.metrics(day, list(q.index))
    q = q.join(m)
    q = q[q["traded_today"]]
    sw_first = pd.read_csv(BT / "sw_history.csv.gz", dtype=str).groupby("code")["start"].min()
    listed = q["first_day"].where(q["first_day"] > "2018-01-02", sw_first.reindex(q.index).fillna("2018-01-02"))
    q = q[listed <= (date.fromisoformat(day) - timedelta(days=365)).isoformat()]
    info["stages"]["traded, listed >= 1 year"] = len(q)
    if q["turnover_20d"].notna().any():  # turnover only in the 通达信 period
        q = q[q["turnover_20d"].fillna(0) >= CONFIG["universe"]["min_turnover"]["cn"]]
    info["stages"]["20-day turnover >= min (2021-08+)"] = len(q)
    df = q.sort_values("mcap", ascending=False).head(CONFIG["universe"]["top_n"]).copy()
    df["mcap_rank"] = np.arange(1, len(df) + 1)
    df["price"] = df["close"]
    df["pe_ttm_em"], df["pb_mrq_em"] = df["pe"], df["pb"]
    df = df.drop(columns=["pe", "pb"])
    fund = universe.ttm(res[res["notice_date"] < day])
    df = df.join(fund.reindex(columns=["period", "notice_date", "revenue_ttm", "np_ttm", "bps", "eps", "ocfps",
                                       "gross_margin", "rev_yoy", "np_yoy", "eps_deduct_ttm"]))
    b = bal[bal["avail"] < day].sort_values("period").groupby("code")["debt_ratio"].last()
    df["debt_ratio"] = b.reindex(df.index) / 100
    df["dps_ttm"] = 0.0  # dividends only move v1's reference RI value; returns include them
    cons = ["analysts", "eps_e1", "eps_e2", "eps_e3"]
    df = df.join(consensus[cons] if consensus is not None else pd.DataFrame(index=df.index, columns=cons, dtype=float))
    df["analysts"] = df["analysts"].fillna(0)
    df = universe.ratios(df)
    df["rev_growth"], df["np_growth"] = df["rev_yoy"] / 100, df["np_yoy"] / 100
    df["gross_margin"] = df["gross_margin"] / 100
    df["cash_conv"] = (df["ocfps"] / df["eps"]).where(df["eps"] > 0)
    sw = sw_industry(day, df.index)
    df["industry"] = "SW" + sw.str[:4].fillna("0000")
    df["financial"] = sw.fillna("").str.startswith(FIN_SW)
    df["r"], df["price_date"] = rates.asof(pd.Timestamp(day)) / 100 + PREMIUM["cn"], day
    checks = {
        "missing fundamentals": df[["np_ttm", "revenue_ttm", "bps", "rev_growth", "np_growth"]].isna().any(axis=1),
        "missing price history": df[["mom_12_1", "vol_1y"]].isna().any(axis=1),
        "P/E disagrees with source": df["pe_ttm_em"].notna() & (((df["pe_ttm_em"] > 0) != (df["np_ttm"] > 0))
                                                              | ((df["pe"] / df["pe_ttm_em"]).sub(1).abs() > 0.5)),
        "P/B disagrees with source": (df["pb"] / df["pb_mrq_em"]).sub(1).abs() > 0.5,
    }
    return universe.finish(df, info, checks)


def cn_balance() -> pd.DataFrame:
    """Balance sheets, public when that period's results were (the balance table's own notice date is
    the latest restatement's)."""
    bal = pd.read_csv(BT / "cn_balance.csv.gz", dtype={"code": str, "period": str, "notice_date": str})
    notice = cn_results().set_index(["code", "period"])["notice_date"]
    bal["avail"] = notice.reindex(pd.MultiIndex.from_arrays([bal["code"], bal["period"]])).to_numpy()
    return bal.dropna(subset=["avail"])


# ---------------------------------------------------------------- US and HK (monthly)

class Monthly:
    """Month-end closes (as traded), monthly total returns and split factors for US or HK."""

    def __init__(self, market: str):
        m = history.read(f"{market}_monthly")
        self.close = m.pivot(index="month", columns="code", values="close")
        self.ret = m.pivot(index="month", columns="code", values="ret")
        self.splits = history.read(f"{market}_splits")
        self.index_code = {"us": "SPX", "hk": "HSI"}[market]

    def today_units(self, month: str, codes) -> pd.Series:
        """Close at the month end in today's units (divided by the later splits)."""
        codes = list(codes)
        f = history.splits_after(self.splits, pd.Series(codes), pd.Series([f"{month}-28"] * len(codes)))
        return self.close.loc[month, codes] / f

    def metrics(self, month: str, codes) -> pd.DataFrame:
        """12-1 month momentum and volatility from monthly total returns (12 months up to the month end)."""
        i = self.ret.index.get_loc(month)
        r = self.ret.iloc[max(i - 11, 0): i + 1].reindex(columns=list(codes))
        mom = (1 + self.ret.iloc[i - 11: i].reindex(columns=list(codes))).prod(min_count=11) - 1 if i >= 11 else np.nan
        return pd.DataFrame({"mom_12_1": mom, "vol_1y": r.std().where(r.count() >= 10) * np.sqrt(12)}, index=list(codes))

    def forward(self, month: str, codes) -> pd.DataFrame:
        i, n, out = self.ret.index.get_loc(month), len(self.ret.index), pd.DataFrame(index=list(codes))
        for h, k in (("1m", 1), ("3m", 3), ("12m", 12)):
            if i + k >= n:
                out[f"ret_{h}"] = np.nan
                continue
            window = 1 + self.ret.iloc[i + 1: i + k + 1]
            out[f"ret_{h}"] = window.reindex(columns=list(codes)).prod(min_count=k) - 1
            out[f"idx_{h}"] = self.close[self.index_code].iloc[i + k] / self.close[self.index_code].iloc[i] - 1
        return out


def us_books(today_snap: pd.DataFrame) -> pd.DataFrame:
    """Every annual report with its share count in today's listed units (history.us_books on the whole
    history, so the units follow today's count; a history cut by a merger or spin-off drops the years
    before it, even on dates before the event), one share class per issuer."""
    a, _, _ = history.us_books(today_snap, date(2026, 10, 18))
    return a[a["code"].isin(set(today_snap.drop_duplicates("issuer").index))]


def us_snapshot(month: str, mon: Monthly, today_snap: pd.DataFrame, books: pd.DataFrame,
                rates: pd.Series) -> tuple[pd.DataFrame, dict]:
    """The US v1 snapshot at a month end: the last annual report filed by then (no quarterly history, so
    trailing numbers are the last fiscal year), in today's listed units; USD at that month's FX."""
    day = pd.Timestamp(f"{month}-01") + pd.offsets.MonthEnd(0)
    info = {"stages": {}, "dropped": {}}
    codes = [c for c in today_snap.index if c in mon.close.columns and pd.notna(mon.close.at[month, c])]
    a = books[books["code"].isin(set(codes)) & (books["avail"] <= day.strftime("%Y-%m-%d"))]
    a = a.sort_values(["code", "fy_end"])
    last, prev = a.groupby("code").last(), a.groupby("code").nth(-2).set_index("code")
    fx = {c[:3]: mon.close.at[month, c] for c in mon.close.columns if c.endswith("=X")}
    rate = last["currency"].map(lambda c: 1.0 if c == "USD" else fx.get(c, np.nan))
    df = today_snap.loc[last.index.intersection(codes), ["name", "sector", "industry_raw", "financial", "country"]].copy()
    df["price"] = mon.today_units(month, df.index)
    df["shares"] = last["units"]
    df["mcap"] = df["price"] * df["shares"]
    for col, src in (("revenue_ttm", "revenue"), ("np_ttm", "ni"), ("gp_ttm", "gp"), ("ocf_ttm", "ocf"),
                     ("equity", "equity"), ("liabilities", "liabilities"), ("assets", "assets")):
        df[col] = last[src] / rate
    df["bps"] = df["equity"] / df["shares"]
    df["debt_ratio"] = df["liabilities"] / df["assets"]
    df["gross_margin"] = df["gp_ttm"] / df["revenue_ttm"]
    df["cash_conv"] = (df["ocf_ttm"] / df["np_ttm"]).where(df["np_ttm"] > 0)
    df["rev_growth"] = last["revenue"] / prev["revenue"].reindex(last.index) - 1
    df["np_growth"] = (last["ni"] - prev["ni"].reindex(last.index)) / prev["ni"].reindex(last.index).abs()
    df["period"], df["notice_date"] = last["fy_end"], last["avail"]
    info["stages"]["today's candidates with an annual report"] = len(df)
    df = df.join(mon.metrics(month, df.index))
    df = df.sort_values("mcap", ascending=False).head(CONFIG["universe"]["top_n"]).copy()
    df["mcap_rank"] = np.arange(1, len(df) + 1)
    df["dps_ttm"], df["analysts"] = 0.0, 0.0
    df[["eps_e1", "eps_e2", "eps_e3"]] = np.nan
    df = universe.ratios(df)
    df["industry"] = df["industry_raw"]
    df["r"], df["price_date"] = rates.asof(day) / 100 + PREMIUM["us"], month
    checks = {"missing fundamentals": df[["np_ttm", "revenue_ttm", "bps", "rev_growth", "np_growth"]].isna().any(axis=1),
              "missing price history": df[["mom_12_1", "vol_1y"]].isna().any(axis=1)}
    df, info = universe.finish(df, info, checks)
    small = (df.groupby("industry")["industry"].transform("size") < CONFIG["peers"]["min_group_size"]) & ~df["financial"]
    df.loc[small, "industry"] = np.where(df.loc[small, "sector"].fillna("") != "", df.loc[small, "sector"] + " (other)",
                                         "Miscellaneous")
    df.loc[df["industry"].fillna("") == "", "industry"] = "Miscellaneous"
    return df, info


def hk_snapshot(month: str, mon: Monthly, today_snap: pd.DataFrame, res: pd.DataFrame,
                rates: pd.Series) -> tuple[pd.DataFrame, dict]:
    """The HK v1 snapshot at a month end: Eastmoney results public 90 days after the period (A4), CNY
    amounts in HKD at that month's HKDCNY, prices in today's units."""
    day = (pd.Timestamp(f"{month}-01") + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    info = {"stages": {}, "dropped": {}}
    codes = [c for c in today_snap.index if c in mon.close.columns and pd.notna(mon.close.at[month, c])]
    rows = res[(res["avail"] <= day) & res["code"].isin(set(codes))]
    rows = rows.sort_values("date_type").drop_duplicates(["code", "period"])  # a changed fiscal year: the annual row
    fund = universe.ttm(rows)
    fx = mon.close.at[month, "HKDCNY=X"]
    df = today_snap.loc[fund.index, ["name", "industry", "industry_type", "financial"]].copy()
    df = df.join(fund[["period", "start", "revenue_ttm", "np_ttm", "bps", "shares", "gross_margin", "rev_yoy", "np_yoy",
                       "debt_ratio", "ocf", "np"]])
    df[["revenue_ttm", "np_ttm", "bps"]] = df[["revenue_ttm", "np_ttm", "bps"]] / fx
    split = history.splits_after(mon.splits, pd.Series(df.index), df["period"].reset_index(drop=True))
    df["shares"] = df["shares"].to_numpy() * split
    df["price"] = mon.today_units(month, df.index)
    df["mcap"] = df["price"] * df["shares"]
    info["stages"]["today's candidates with results public by then"] = len(df)
    df = df.join(mon.metrics(month, df.index))
    df = df.sort_values("mcap", ascending=False).head(HK_TOP).copy()
    df["mcap_rank"] = np.arange(1, len(df) + 1)
    df["gross_margin"], df["debt_ratio"] = df["gross_margin"] / 100, df["debt_ratio"] / 100
    df["cash_conv"] = (df["ocf"] / df["np"]).where(df["np"] > 0)
    df["rev_growth"], df["np_growth"] = df["rev_yoy"] / 100, df["np_yoy"] / 100
    df["dps_ttm"], df["analysts"] = 0.0, 0.0
    df[["eps_e0", "eps_e1", "eps_e2", "eps_e3"]] = np.nan
    df = universe.ratios(df.assign(notice_date=None))
    df["r"], df["price_date"] = rates.asof(pd.Timestamp(day)) / 100 + PREMIUM["hk"], month
    checks = {"missing fundamentals": df[["np_ttm", "revenue_ttm", "bps", "rev_growth", "np_growth"]].isna().any(axis=1),
              "no report in the last 300 days": pd.to_datetime(df["period"]) < pd.Timestamp(day) - pd.Timedelta(days=300),
              "missing price history": df[["mom_12_1", "vol_1y"]].isna().any(axis=1)}
    return universe.finish(df, info, checks)


def today_snapshot(market: str) -> pd.DataFrame:
    """Names, industries (today's) and listed share counts of today's candidates (US: every listed name
    in the screener with monthly prices; HK: the snapshot's names plus the HK list)."""
    snap = pd.read_csv(DATA / "snapshots" / "2026-10-18" / f"{market}.csv.gz", dtype={"code": str}).set_index("code")
    if market == "us":
        lst = nasdaq.load_list().drop_duplicates("code").set_index("code")
        lst = lst[lst["last"] > 0]
        out = pd.DataFrame({"name": lst["name"], "sector": lst["sector"].fillna(""), "industry_raw": lst["industry"].fillna(""),
                            "shares": lst["mcap"] / lst["last"], "country": lst["country"]})
        out["financial"] = out["industry_raw"].isin(CONFIG["peers"]["financial_industries_us"])
        out = out[out["shares"] > 0]
        # one share class per issuer (SEC CIK): today's universe's choice first, else the larger
        cik = sec.load_ciks().reindex(out.index)
        out["issuer"] = np.where(cik.notna(), "cik" + cik.astype(str), out.index)
        out["in_snap"] = out.index.isin(snap.index)
        return out.sort_values(["in_snap", "shares"], ascending=False)
    from stockreport.fetch import eastmoney
    lst = eastmoney.load_hk_list().drop_duplicates("code").set_index("code")
    lst = lst[lst["org_type"].notna() & (lst.index < "10000")]
    out = lst[["name", "industry", "industry_type"]].copy()
    out["financial"] = out["industry_type"].fillna("").str.split("-").str[-1].isin(CONFIG["peers"]["financial_industries_hk"])
    return out.combine_first(snap[["name"]])


def rates_series(market: str) -> pd.Series:
    """10-year yield (%) by day; HK has no free history: the US 10-year less today's HK-US gap (HKD peg)."""
    r = pd.read_csv(BT / "rates.csv")
    r = r.set_axis(pd.to_datetime(r["date"]))
    if market == "hk":
        now = pd.read_csv(DATA / "rates.csv").groupby("market")["y10"].last()
        return r.loc[r["market"] == "us", "y10"].sort_index() + (now["hk"] - now["us"])
    return r.loc[r["market"] == market, "y10"].sort_index()
