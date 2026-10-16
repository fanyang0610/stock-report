"""Eastmoney datacenter (datacenter-web.eastmoney.com): CN daily valuation, quarterly results,
balance sheets, dividends and the ChinaBond 10-year yield it republishes."""

import logging
from datetime import date, timedelta

import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import Http, needs_refresh, save_raw

log = logging.getLogger(__name__)
URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
A_SHARES = '(SECURITY_TYPE_CODE in ("058001001","058001008"))'
http = Http(min_interval=1.0)


def datacenter(report: str, filter_str: str, columns: str, sort: str = "SECURITY_CODE",
               sort_type: str = "1", page_size: int = 500, max_pages: int = 100, raw: str | None = None) -> list[dict]:
    rows, page = [], 1
    while True:
        payload = http.get(URL, params={
            "reportName": report, "columns": columns, "filter": filter_str, "pageNumber": page,
            "pageSize": page_size, "sortColumns": sort, "sortTypes": sort_type,
            "source": "WEB", "client": "WEB"}).json()
        if payload.get("code") == 9201 and page == 1:  # "no data" for this filter
            return []
        result = payload.get("result")
        if payload.get("code") != 0 or not result:
            raise RuntimeError(f"{report}: code={payload.get('code')} {payload.get('message')}")
        if raw:
            save_raw(f"{raw}_p{page}", payload)
        rows += result["data"] or []
        if page >= min(result["pages"], max_pages):
            break
        page += 1
    if max_pages >= result["pages"] and len(rows) != result["count"]:
        raise RuntimeError(f"{report}: got {len(rows)} rows, expected {result['count']}")
    return rows


def _write(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_csv(tmp, index=False, compression="gzip")
    tmp.replace(path)


def update_quotes() -> None:
    """Latest daily close, market value, PE/PB/PS and industry for every A-share."""
    path = DATA / "quotes" / "cn.csv.gz"
    latest = datacenter("RPT_VALUEANALYSIS_DET", "", "TRADE_DATE", sort="TRADE_DATE",
                        sort_type="-1", page_size=1, max_pages=1)[0]["TRADE_DATE"][:10]
    if path.exists() and pd.read_csv(path, nrows=1, dtype=str)["trade_date"].iloc[0] == latest:
        return
    rows = datacenter("RPT_VALUEANALYSIS_DET", f"(TRADE_DATE='{latest}')",
                      "SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,CLOSE_PRICE,TOTAL_MARKET_CAP,"
                      "TOTAL_SHARES,PE_TTM,PB_MRQ,PS_TTM,TRADE_DATE", raw="cn_quotes")
    df = pd.DataFrame(rows).rename(columns={
        "SECURITY_CODE": "code", "SECURITY_NAME_ABBR": "name", "BOARD_NAME": "industry",
        "CLOSE_PRICE": "close", "TOTAL_MARKET_CAP": "mcap", "TOTAL_SHARES": "shares",
        "PE_TTM": "pe_ttm_em", "PB_MRQ": "pb_mrq_em", "PS_TTM": "ps_ttm_em", "TRADE_DATE": "trade_date"})
    df["trade_date"] = df["trade_date"].str[:10]
    if len(df) < 4000:
        raise RuntimeError(f"only {len(df)} quotes for {latest}; the source may still be updating")
    _write(df, path)
    log.info("cn quotes: %d stocks for %s", len(df), latest)


def quarter_ends(today: date, n: int) -> list[date]:
    ends, y, q = [], today.year, (today.month - 1) // 3  # q = quarters completed this year
    while len(ends) < n:
        if q == 0:
            y, q = y - 1, 4
        ends.append(date(y, 3 * q, 31 if q in (1, 4) else 30))
        q -= 1
    return ends


def is_open(period: date, today: date) -> bool:
    """Reports for this period may still be coming in (statutory deadline + a week)."""
    deadline = {3: date(period.year, 4, 30), 6: date(period.year, 8, 31),
                9: date(period.year, 10, 31), 12: date(period.year + 1, 4, 30)}[period.month]
    return period < today <= deadline + timedelta(days=7)


def update_fundamentals(today: date) -> None:
    """Quarterly results (业绩报表) and balance sheets for the last few report periods."""
    for i, period in enumerate(quarter_ends(today, CONFIG["fetch"]["quarters_kept"])):
        p, opened = period.isoformat(), is_open(period, today)
        path = DATA / "fundamentals" / f"cn_results_{p}.csv.gz"
        if needs_refresh(path, today, opened):
            rows = datacenter("RPT_LICO_FN_CPD", f"(REPORTDATE='{p}'){A_SHARES}",
                              "SECURITY_CODE,NOTICE_DATE,BASIC_EPS,TOTAL_OPERATE_INCOME,PARENT_NETPROFIT,"
                              "YSTZ,SJLTZ,BPS,MGJYXJJE,XSMLL", raw=f"cn_results_{p}")
            df = pd.DataFrame(rows, columns=["SECURITY_CODE", "NOTICE_DATE", "BASIC_EPS", "TOTAL_OPERATE_INCOME",
                                             "PARENT_NETPROFIT", "YSTZ", "SJLTZ", "BPS", "MGJYXJJE", "XSMLL"])
            df.columns = ["code", "notice_date", "eps", "revenue", "np", "rev_yoy", "np_yoy", "bps", "ocfps", "gross_margin"]
            df["notice_date"] = df["notice_date"].str[:10]
            _write(df, path)
            log.info("cn results %s: %d rows", p, len(df))
        path = DATA / "fundamentals" / f"cn_balance_{p}.csv.gz"
        if i < 3 and needs_refresh(path, today, opened):  # leverage only needs the latest periods
            rows = datacenter("RPT_DMSK_FN_BALANCE", f"(REPORT_DATE='{p}'){A_SHARES}",
                              "SECURITY_CODE,DEBT_ASSET_RATIO", raw=f"cn_balance_{p}")
            df = pd.DataFrame(rows, columns=["SECURITY_CODE", "DEBT_ASSET_RATIO"])
            df.columns = ["code", "debt_ratio"]
            _write(df, path)
            log.info("cn balance %s: %d rows", p, len(df))


def update_dividends(today: date) -> None:
    """Cash dividends with ex-dates in the last ~13 months."""
    path = DATA / "fundamentals" / "cn_dividends.csv.gz"
    if not needs_refresh(path, today):
        return
    start = (today - timedelta(days=400)).isoformat()
    rows = datacenter("RPT_SHAREBONUS_DET",
                      f"(EX_DIVIDEND_DATE>='{start}')(EX_DIVIDEND_DATE<='{today.isoformat()}')",
                      "SECURITY_CODE,EX_DIVIDEND_DATE,PRETAX_BONUS_RMB", sort="EX_DIVIDEND_DATE,SECURITY_CODE", sort_type="1,1",
                      raw="cn_dividends")
    df = pd.DataFrame(rows, columns=["SECURITY_CODE", "EX_DIVIDEND_DATE", "PRETAX_BONUS_RMB"])
    df.columns = ["code", "ex_date", "dps"]
    df["ex_date"] = df["ex_date"].str[:10]
    df["dps"] = df["dps"] / 10  # source is per 10 shares
    _write(df, path)
    log.info("cn dividends: %d rows since %s", len(df), start)


CONSENSUS_FIELDS = ["SECURITY_CODE", "RATING_ORG_NUM"] + [f"{k}{i}" for i in range(1, 5) for k in ("YEAR", "YEAR_MARK", "EPS")]


def consensus_table(rows: list[dict]) -> pd.DataFrame:
    """Analyst consensus EPS for the first three estimate years (marked "E") per stock.
    Target prices and ratings in the same table are deliberately not kept."""
    out = []
    for row in rows:
        est = [(row[f"YEAR{i}"], row[f"EPS{i}"]) for i in range(1, 5) if row.get(f"YEAR_MARK{i}") == "E"]
        if len(est) < 3:
            continue
        est = sorted(est)[:3]
        out.append({"code": row["SECURITY_CODE"], "analysts": row["RATING_ORG_NUM"] or 0, "e1_year": est[0][0],
                    "eps_e1": est[0][1], "eps_e2": est[1][1], "eps_e3": est[2][1]})
    return pd.DataFrame(out, columns=["code", "analysts", "e1_year", "eps_e1", "eps_e2", "eps_e3"])


def update_consensus(today: date) -> None:
    """Consensus EPS forecasts (研报一致预期) for every covered A-share, refreshed weekly."""
    path = DATA / "fundamentals" / "cn_consensus.csv.gz"
    if not needs_refresh(path, today):
        return
    rows = datacenter("RPT_WEB_RESPREDICT", "", ",".join(CONSENSUS_FIELDS), raw="cn_consensus")
    df = consensus_table(rows)
    _write(df, path)
    log.info("cn consensus: %d stocks with three estimate years", len(df))


def update_yield() -> None:
    """ChinaBond 10-year government bond yield (%), as republished by Eastmoney."""
    rows = datacenter("RPTA_WEB_TREASURYYIELD", "", "SOLAR_DATE,EMM00166466", sort="SOLAR_DATE",
                      sort_type="-1", page_size=20, max_pages=1)
    new = pd.DataFrame([{"date": r["SOLAR_DATE"][:10], "market": "cn", "y10": r["EMM00166466"]}
                        for r in rows if r["EMM00166466"] is not None])
    if new.empty:
        raise RuntimeError("no CN 10-year yield in the last 20 days")
    path = DATA / "rates.csv"
    old = pd.read_csv(path, dtype={"date": str}) if path.exists() else new.iloc[:0]
    df = pd.concat([old, new]).drop_duplicates(["date", "market"], keep="last").sort_values(["market", "date"])
    df.to_csv(path, index=False)
