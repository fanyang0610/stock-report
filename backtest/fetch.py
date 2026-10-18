"""Backtest data (Phase 9): point-in-time CN tables from free sources, under data/backtest/. Raw responses
are parsed in memory and never stored; every task skips what it already has, so a run can be resumed.

  uv run python -m backtest.fetch eastmoney   # valuation history, results, balance sheets, 业绩预告, yields
  uv run python -m backtest.fetch tdx         # 通达信 daily packages (from ~2021-08) and the CSI 300 before
  uv run python -m backtest.fetch reports     # research-report archive for the 2026 consensus window
  uv run python -m backtest.fetch sw          # 申万 industry change history
"""

import logging
import subprocess
import sys
import time
from datetime import date, timedelta

import pandas as pd
from dotenv import dotenv_values

from stockreport.config import DATA, ROOT
from stockreport.fetch import Http, each, tdx
from stockreport.fetch.eastmoney import A_SHARES, CN_RESULTS, FORECAST_FIELDS, datacenter, forecast_table, results_table

log = logging.getLogger("backtest.fetch")
BT = DATA / "backtest"
TODAY = date(2026, 10, 18)
VAL = {"SECURITY_CODE": "code", "SECURITY_NAME_ABBR": "name", "BOARD_NAME": "board", "CLOSE_PRICE": "close",
       "CHANGE_RATE": "chg", "TOTAL_MARKET_CAP": "mcap", "TOTAL_SHARES": "shares", "PE_TTM": "pe", "PB_MRQ": "pb"}
OVERLAP_DAYS = 45  # Eastmoney daily history runs this far into the 通达信 period, to check one against the other


def write(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_csv(tmp, index=False, compression="gzip")
    tmp.replace(path)


def valuation_day(day: str) -> pd.DataFrame:
    rows = datacenter("RPT_VALUEANALYSIS_DET", f"(TRADE_DATE='{day}')", ",".join(VAL), page_size=5000)
    return pd.DataFrame(rows, columns=list(VAL)).rename(columns=VAL).assign(date=day)


def calendar() -> list[str]:
    """Trading days since 2018-01-02: the days on which any of three large, rarely suspended stocks traded."""
    path = BT / "calendar.csv"
    if path.exists():
        return pd.read_csv(path)["date"].tolist()
    days = set()
    for code in ("000001", "600519", "601318"):
        rows = datacenter("RPT_VALUEANALYSIS_DET", f'(SECURITY_CODE="{code}")', "TRADE_DATE", page_size=5000)
        days |= {r["TRADE_DATE"][:10] for r in rows}
    out = sorted(days)
    pd.DataFrame({"date": out}).to_csv(path, index=False)
    return out


def tdx_start() -> str:
    """First day with a 通达信 daily package (probed once; the archive starts in 2021)."""
    path = BT / "tdx_start.txt"
    if path.exists():
        return path.read_text().strip()
    http = Http(min_interval=0.3, timeout=90)
    for day in [d for d in calendar() if d >= "2021-05-01"]:
        if http.get(tdx.URL.format(ymd=day.replace("-", "")), ok=(200, 404)).status_code == 200:
            path.write_text(day)
            return day
    raise RuntimeError("no 通达信 package found")


def eastmoney() -> None:
    BT.mkdir(parents=True, exist_ok=True)
    days, start = calendar(), tdx_start()
    # 1. daily valuation history until the 通达信 packages start (plus an overlap), one month per file
    end = days[min(days.index(start) + OVERLAP_DAYS, len(days) - 1)]
    for month in sorted({d[:7] for d in days if d <= end}):
        path = BT / "cn_val_daily" / f"{month}.csv.gz"
        if not path.exists():
            write(pd.concat([valuation_day(d) for d in days if d[:7] == month and d <= end]), path)
            log.info("valuation %s", month)
    # 2. the last trading day of every later month (and the latest day)
    path = BT / "cn_val_month.csv.gz"
    have = set(pd.read_csv(path, usecols=["date"])["date"]) if path.exists() else set()
    ends = [d for d in days if d > end and (d == days[-1] or days[days.index(d) + 1][:7] != d[:7])]
    new = [valuation_day(d) for d in ends if d not in have]
    if new:
        old = [pd.read_csv(path, dtype={"code": str})] if path.exists() else []
        write(pd.concat(old + new), path)
        log.info("valuation month ends: +%d", len(new))
    # 3. quarterly results with notice dates since 2009
    path = BT / "cn_results.csv.gz"
    if not path.exists():
        frames = []
        for y in range(2009, TODAY.year + 1):
            for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
                p = date(y, m, d)
                if p < TODAY - timedelta(days=15):
                    rows = datacenter("RPT_LICO_FN_CPD", f"(REPORTDATE='{p}'){A_SHARES}", ",".join(CN_RESULTS),
                                      page_size=5000)
                    frames.append(results_table(rows).assign(period=p.isoformat()))
                    log.info("results %s: %d", p, len(rows))
        write(pd.concat(frames), path)
    # 4. balance sheets: leverage, inventory, advance receipts, assets
    path = BT / "cn_balance.csv.gz"
    if not path.exists():
        cols = "SECURITY_CODE,NOTICE_DATE,DEBT_ASSET_RATIO,INVENTORY,ADVANCE_RECEIVABLES,TOTAL_ASSETS"
        frames = []
        for y in range(2009, TODAY.year + 1):
            for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
                p = date(y, m, d)
                if p < TODAY - timedelta(days=15) and (m == 12 or y >= 2017):
                    rows = datacenter("RPT_DMSK_FN_BALANCE", f"(REPORT_DATE='{p}'){A_SHARES}", cols, page_size=5000)
                    df = pd.DataFrame(rows, columns=cols.split(","))
                    df.columns = ["code", "notice_date", "debt_ratio", "inventory", "advance", "assets"]
                    frames.append(df.assign(period=p.isoformat(), notice_date=df["notice_date"].str[:10]))
                    log.info("balance %s: %d", p, len(rows))
        write(pd.concat(frames), path)
    # 5. 业绩预告 since late 2017
    path = BT / "cn_forecasts.csv.gz"
    if not path.exists():
        rows = datacenter("RPT_PUBLIC_OP_NEWPREDICT", "(NOTICE_DATE>='2017-10-01')", ",".join(FORECAST_FIELDS),
                          sort="NOTICE_DATE,SECURITY_CODE,REPORT_DATE,PREDICT_FINANCE_CODE", sort_type="1,1,1,1",
                          page_size=5000, max_pages=400)
        write(forecast_table(rows), path)
        log.info("forecasts: %d", len(rows))
    rates()


def rates() -> None:
    """10-year yields: ChinaBond (Eastmoney) and US Treasuries (FRED), since 2015."""
    path = BT / "rates.csv"
    if not path.exists():
        rows = datacenter("RPTA_WEB_TREASURYYIELD", "(SOLAR_DATE>='2015-01-01')", "SOLAR_DATE,EMM00166466",
                          sort="SOLAR_DATE", sort_type="1", page_size=5000)
        cn = pd.DataFrame([{"date": r["SOLAR_DATE"][:10], "market": "cn", "y10": r["EMM00166466"]}
                           for r in rows if r["EMM00166466"] is not None])
        key = dotenv_values(ROOT / ".env").get("FRED_API_KEY")
        obs = Http(min_interval=0.5).get("https://api.stlouisfed.org/fred/series/observations", params={
            "series_id": "DGS10", "api_key": key, "file_type": "json", "observation_start": "2015-01-01"}).json()
        us = pd.DataFrame([{"date": o["date"], "market": "us", "y10": float(o["value"])}
                           for o in obs["observations"] if o["value"] not in (".", "")])
        pd.concat([cn, us]).to_csv(path, index=False)
        log.info("rates: cn %d, us %d days", len(cn), len(us))


def tdx_packages() -> None:
    """Every 通达信 daily package from the first one: close, exchange prev-close, volume and turnover per
    A-share and the CSI 300, one month per file; names (with the ST prefix of the day) on month ends."""
    days, start = calendar(), tdx_start()
    todo = [d for d in days if d >= start]

    def one(http, d):
        resp = http.get(tdx.URL.format(ymd=d.replace("-", "")), ok=(200, 404))
        if resp.status_code == 404:
            log.warning("no package for %s", d)
            return None
        return tdx.parse_package(resp.content, d.replace("-", ""), min_rows=3000, names=d == month_end[d[:7]])
    month_end = {d[:7]: d for d in todo}
    for month in sorted({d[:7] for d in todo}):
        path = BT / "tdx" / f"{month}.csv.gz"
        if path.exists() and month < todo[-1][:7]:
            continue
        mdays = [d for d in todo if d[:7] == month]
        frames = [f for f in each(lambda: Http(min_interval=0.5, timeout=120), one, mdays, workers=4) if f is not None]
        if frames:
            write(pd.concat(frames), path)
            log.info("tdx %s: %d days", month, len(frames))
    path = BT / "csi300_early.csv"
    if not path.exists():  # the CSI 300 before the packages: Tencent daily kline (an index: no adjustment)
        resp = Http(min_interval=0.5).get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                                          params={"param": f"sh000300,day,2017-12-01,{start},2000,"})
        bars = resp.json()["data"]["sh000300"]["day"]
        pd.DataFrame([{"date": b[0], "close": float(b[2])} for b in bars]).to_csv(path, index=False)


def reports() -> None:
    """Research reports published since 2025-06: their FY2026-28 EPS forecasts (the archive labels its
    EPS fields relative to today, so earlier years are blank), for the 2026 consensus window."""
    path = BT / "cn_reports.csv.gz"
    if path.exists():
        return
    http, rows, page = Http(min_interval=2.0, headers={"Referer": "https://data.eastmoney.com/"}), [], 1
    while True:
        params = {"industryCode": "*", "pageSize": "100", "industry": "*", "rating": "*", "ratingChange": "*",
                  "beginTime": "2025-06-01", "endTime": TODAY.isoformat(), "pageNo": str(page), "fields": "",
                  "qType": "0", "orgCode": "", "code": "", "rcode": ""}
        d = http.get("https://reportapi.eastmoney.com/report/list", params=params).json()
        rows += [{"code": r["stockCode"], "publish": r["publishDate"][:10], "org": r["orgSName"],
                  "eps_2026": r["predictThisYearEps"], "eps_2027": r["predictNextYearEps"],
                  "eps_2028": r["predictNextTwoYearEps"]} for r in d.get("data") or []]
        if page >= (d.get("TotalPage") or 1):
            break
        page += 1
        if page % 20 == 0:
            log.info("reports: page %d of %s", page, d.get("TotalPage"))
    df = pd.DataFrame(rows).replace("", None)
    write(df, path)
    log.info("reports: %d (%d with FY2026 EPS)", len(df), df["eps_2026"].notna().sum())


def sw() -> None:
    """申万 industry change history (codes only). The site refuses Python's TLS client; curl works."""
    path = BT / "sw_history.csv.gz"
    if path.exists():
        return
    xls = BT / "sw.xls"
    BT.mkdir(parents=True, exist_ok=True)
    for attempt in range(5):  # it answers 508 or drops the connection now and then
        done = subprocess.run(["curl", "-sSf", "-o", str(xls), "-A", "Mozilla/5.0",
                               "https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls"])
        if done.returncode == 0:
            break
        time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError("申万 download failed")
    df = pd.read_excel(xls, dtype=str)
    df.columns = ["code", "start", "sw", "updated"]
    write(df.assign(code=df["code"].str.zfill(6), start=df["start"].str[:10])[["code", "start", "sw"]], path)
    xls.unlink()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    for task in sys.argv[1:]:
        {"eastmoney": eastmoney, "tdx": tdx_packages, "reports": reports, "sw": sw, "rates": rates}[task]()
