"""Eastmoney datacenter (datacenter-web.eastmoney.com): CN daily valuation, quarterly results, balance sheets, dividends
and the ChinaBond 10-year yield; the HK list and main indicators; the company id (ORG_CODE, one per issuer across A/H/ADR
lines) for the issuer dedupe. History: CN annual results (扣非 EPS), CN valuations at half-year ends since 2018-12, HK
main indicators since 2015, and the market-wide 业绩预告 table."""

import logging
from datetime import date, timedelta

import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import HISTORY, Http, merge, needs_refresh, save_raw, save_rates, write

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


def update_quotes() -> None:
    """Latest daily close, market value, PE/PB/PS and industry for every A-share."""
    path = DATA / "quotes" / "cn.csv.gz"
    latest = datacenter("RPT_VALUEANALYSIS_DET", "", "TRADE_DATE", sort="TRADE_DATE",
                        sort_type="-1", page_size=1, max_pages=1)[0]["TRADE_DATE"][:10]
    old = pd.read_csv(path, nrows=1, dtype=str) if path.exists() else None
    if old is not None and old["trade_date"].iloc[0] == latest and "org_code" in old:
        return
    rows = datacenter("RPT_VALUEANALYSIS_DET", f"(TRADE_DATE='{latest}')",
                      "SECURITY_CODE,SECURITY_NAME_ABBR,ORG_CODE,BOARD_NAME,CLOSE_PRICE,TOTAL_MARKET_CAP,"
                      "TOTAL_SHARES,PE_TTM,PB_MRQ,PS_TTM,TRADE_DATE", raw="cn_quotes")
    df = pd.DataFrame(rows).rename(columns={
        "SECURITY_CODE": "code", "SECURITY_NAME_ABBR": "name", "ORG_CODE": "org_code", "BOARD_NAME": "industry",
        "CLOSE_PRICE": "close", "TOTAL_MARKET_CAP": "mcap", "TOTAL_SHARES": "shares",
        "PE_TTM": "pe_ttm_em", "PB_MRQ": "pb_mrq_em", "PS_TTM": "ps_ttm_em", "TRADE_DATE": "trade_date"})
    df["trade_date"] = df["trade_date"].str[:10]
    if len(df) < 4000:
        raise RuntimeError(f"only {len(df)} quotes for {latest}; the source may still be updating")
    write(df, path)
    log.info("cn quotes: %d stocks for %s", len(df), latest)


def cn_largest() -> list[str]:
    """The largest A-shares by today's market value: the ones Tencent's quotes cross-check."""
    quotes = pd.read_csv(DATA / "quotes" / "cn.csv.gz", dtype={"code": str})
    return list(quotes.sort_values("mcap", ascending=False)["code"].head(CONFIG["crosscheck"]["cn_tencent"]))


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


CN_RESULTS = {"SECURITY_CODE": "code", "NOTICE_DATE": "notice_date", "BASIC_EPS": "eps", "DEDUCT_BASIC_EPS": "eps_deduct",
              "TOTAL_OPERATE_INCOME": "revenue", "PARENT_NETPROFIT": "np", "YSTZ": "rev_yoy", "SJLTZ": "np_yoy",
              "BPS": "bps", "MGJYXJJE": "ocfps", "XSMLL": "gross_margin", "WEIGHTAVG_ROE": "roe"}  # eps_deduct: 扣非 EPS


def results_table(rows: list[dict]) -> pd.DataFrame:
    """业绩报表 rows -> code, notice date, EPS and 扣非 EPS, revenue, profit, growth (%), BPS,
    operating cash flow per share, gross margin (%) and weighted ROE (%)."""
    df = pd.DataFrame(rows, columns=list(CN_RESULTS)).rename(columns=CN_RESULTS)
    df["notice_date"] = df["notice_date"].str[:10]
    return df


def update_fundamentals(today: date) -> None:
    """Quarterly results (业绩报表) and balance sheets for the last few report periods."""
    for i, period in enumerate(quarter_ends(today, CONFIG["fetch"]["quarters_kept"])):
        p, opened = period.isoformat(), is_open(period, today)
        path = DATA / "fundamentals" / f"cn_results_{p}.csv.gz"
        if needs_refresh(path, today, opened):
            df = results_table(datacenter("RPT_LICO_FN_CPD", f"(REPORTDATE='{p}'){A_SHARES}", ",".join(CN_RESULTS),
                                          raw=f"cn_results_{p}"))
            write(df, path)
            log.info("cn results %s: %d rows", p, len(df))
        path = DATA / "fundamentals" / f"cn_balance_{p}.csv.gz"
        if i < 3 and needs_refresh(path, today, opened):  # leverage only needs the latest periods
            rows = datacenter("RPT_DMSK_FN_BALANCE", f"(REPORT_DATE='{p}'){A_SHARES}",
                              "SECURITY_CODE,DEBT_ASSET_RATIO", raw=f"cn_balance_{p}")
            df = pd.DataFrame(rows, columns=["SECURITY_CODE", "DEBT_ASSET_RATIO"])
            df.columns = ["code", "debt_ratio"]
            write(df, path)
            log.info("cn balance %s: %d rows", p, len(df))


DIVIDENDS = DATA / "fundamentals" / "cn_dividends.csv.gz"


def update_dividends(today: date) -> None:
    """Cash dividends and bonus shares (送转, which the revisions undo in older estimates) with ex-dates in the last ~13
    months. A table from before the bonus shares were kept is fetched again."""
    if not needs_refresh(DIVIDENDS, today) and "bonus" in pd.read_csv(DIVIDENDS, nrows=0).columns:
        return
    start = (today - timedelta(days=400)).isoformat()
    rows = datacenter("RPT_SHAREBONUS_DET",
                      f"(EX_DIVIDEND_DATE>='{start}')(EX_DIVIDEND_DATE<='{today.isoformat()}')",
                      "SECURITY_CODE,EX_DIVIDEND_DATE,PRETAX_BONUS_RMB,BONUS_IT_RATIO", sort="EX_DIVIDEND_DATE,SECURITY_CODE",
                      sort_type="1,1", raw="cn_dividends")
    df = pd.DataFrame(rows, columns=["SECURITY_CODE", "EX_DIVIDEND_DATE", "PRETAX_BONUS_RMB", "BONUS_IT_RATIO"])
    df.columns = ["code", "ex_date", "dps", "bonus"]
    df["ex_date"] = df["ex_date"].str[:10]
    df[["dps", "bonus"]] = df[["dps", "bonus"]] / 10  # source is per 10 shares
    write(df, DIVIDENDS)
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
    write(df, path)
    log.info("cn consensus: %d stocks with three estimate years", len(df))


CN_REPORTS = HISTORY / "cn_reports.csv.gz"  # broker EPS estimates, one row per report and fiscal year
REPORT_FIELDS = ("predictThisYearEps", "predictNextYearEps", "predictNextTwoYearEps")


def report_rows(payload: dict, year: int) -> list[dict]:
    """One row per company report and estimate year. The archive labels its estimates by the year it is read in
    (predictThisYearEps is that calendar year's; older reports' passed years are blank), so the years are fixed
    when the page is read (`year`)."""
    return [{"code": r["stockCode"], "publish": r["publishDate"][:10], "org": r["orgSName"], "year": year + k,
             "eps": float(r[f])} for r in payload.get("data") or [] for k, f in enumerate(REPORT_FIELDS)
            if r.get(f) not in (None, "")]


def update_reports(today: date, days: int = 300) -> None:
    """Company research reports (Eastmoney's archive, reportapi report/list) since the newest one kept (3 days again,
    as late ones appear), else (or while the table doesn't reach back) the last `days`; kept `days` (the revisions
    need 91 + 180)."""
    old = pd.read_csv(CN_REPORTS, dtype={"code": str, "publish": str}) if CN_REPORTS.exists() else pd.DataFrame()
    start = today - timedelta(days=days)
    if len(old) and old["publish"].min() <= (start + timedelta(days=10)).isoformat():
        start = date.fromisoformat(old["publish"].max()) - timedelta(days=3)
    client, rows, page = Http(min_interval=2.0, headers={"Referer": "https://data.eastmoney.com/"}), [], 1
    while True:
        payload = client.get("https://reportapi.eastmoney.com/report/list", params={
            "industryCode": "*", "pageSize": "100", "industry": "*", "rating": "*", "ratingChange": "*",
            "beginTime": start.isoformat(), "endTime": today.isoformat(), "pageNo": str(page), "fields": "",
            "qType": "0", "orgCode": "", "code": "", "rcode": ""}).json()
        rows += report_rows(payload, today.year)
        if page >= (payload.get("TotalPage") or 1):
            break
        page += 1
    df = pd.concat([old, pd.DataFrame(rows, columns=["code", "publish", "org", "year", "eps"])])
    df = df.drop_duplicates(["code", "publish", "org", "year"], keep="last")
    write(df[df["publish"] >= (today - timedelta(days=days)).isoformat()].sort_values(["publish", "code"]), CN_REPORTS)
    log.info("cn research reports: %d estimates since %s (%d pages)", len(rows), start, page)


def update_yield() -> None:
    """ChinaBond 10-year government bond yield (%), as republished by Eastmoney."""
    rows = datacenter("RPTA_WEB_TREASURYYIELD", "", "SOLAR_DATE,EMM00166466", sort="SOLAR_DATE",
                      sort_type="-1", page_size=20, max_pages=1)
    save_rates(pd.DataFrame([{"date": r["SOLAR_DATE"][:10], "market": "cn", "y10": r["EMM00166466"]}
                             for r in rows if r["EMM00166466"] is not None]), "cn")


CN_ANNUAL, CN_VALUATION = HISTORY / "cn_annual.csv.gz", HISTORY / "cn_valuation.csv.gz"
CN_FORECASTS, CN_DEDUCT = HISTORY / "cn_forecasts.csv.gz", HISTORY / "cn_deduct.csv.gz"
DEDUCT_FIELDS = {"SECURITY_CODE": "code", "NOTICE_DATE": "notice_date", "KCFJCXSYJLR": "deduct"}
ANNUAL_FIELDS = DEDUCT_FIELDS | {"TOTAL_ASSETS_PK": "assets"}  # fiscal years: total assets, for the long-run ROA


def deduct_table(rows: list[dict], period: str) -> pd.DataFrame:
    fields = ANNUAL_FIELDS if period.endswith("12-31") else DEDUCT_FIELDS
    df = pd.DataFrame(rows, columns=list(fields)).rename(columns=fields)
    return df.assign(notice_date=df["notice_date"].str[:10], period=period)


def update_cn_deduct(today: date) -> None:
    """Year-to-date 扣非 net profit (CNY) of every A-share for every quarter since 2015 and every fiscal year since
    2009, from 主要财务指标 (RPT_F10_FINANCE_MAINFINADATA, with the first notice date): E/P and the SUE (PLAN.md, the
    score), and with each fiscal year's total assets the long-run figures (history.cn_years; 8 years back from the
    history run's first years). 业绩报表 has 扣非 EPS only in half-year and annual reports. Each period once; one still
    reporting daily; the fiscal years once more for a table saved before they carried total assets."""
    have, fresh = periods_in(CN_DEDUCT), not needs_refresh(CN_DEDUCT, today, True)
    if have and "assets" not in pd.read_csv(CN_DEDUCT, nrows=0).columns:
        have = {p for p in have if not p.endswith("12-31")}
    for period in reversed(quarter_ends(today, 4 * (today.year - 2009) + 4)):
        p = period.isoformat()
        wanted = p >= "2015" or (p >= "2009" and p.endswith("12-31"))
        if wanted and (p not in have or (is_open(period, today) and not fresh)):
            fields = ANNUAL_FIELDS if p.endswith("12-31") else DEDUCT_FIELDS
            rows = datacenter("RPT_F10_FINANCE_MAINFINADATA", f"(REPORT_DATE='{p}'){A_SHARES}", ",".join(fields))
            merge(CN_DEDUCT, deduct_table(rows, p), ["code", "period"])  # each quarter as it comes: the first run is ~17 min
            log.info("cn 扣非 %s: %d rows", p, len(rows))
VALUATION_FIELDS = {"SECURITY_CODE": "code", "TRADE_DATE": "trade_date", "CLOSE_PRICE": "close",
                    "TOTAL_MARKET_CAP": "mcap", "TOTAL_SHARES": "shares", "PE_TTM": "pe_ttm", "PB_MRQ": "pb_mrq", "PS_TTM": "ps_ttm"}
FORECAST_FIELDS = {"SECURITY_CODE": "code", "SECURITY_NAME_ABBR": "name", "NOTICE_DATE": "notice_date",
                   "REPORT_DATE": "period", "PREDICT_FINANCE_CODE": "item_code", "PREDICT_FINANCE": "item",
                   "PREDICT_TYPE": "type", "PREDICT_AMT_LOWER": "amount_low", "PREDICT_AMT_UPPER": "amount_high",
                   "ADD_AMP_LOWER": "yoy_low", "ADD_AMP_UPPER": "yoy_high", "PREYEAR_SAME_PERIOD": "prior_year"}


def periods_in(path, column: str = "period") -> set[str]:
    return set(pd.read_csv(path, usecols=[column], dtype=str)[column]) if path.exists() else set()


def update_cn_history(today: date) -> None:
    """Annual results for every fiscal year since 2009 (each fetched once; the latest again every week
    while its reports are still coming in), and the valuation table on the last trading day of every
    half-year since 2018-12 (Eastmoney has nothing earlier)."""
    have, frames = periods_in(CN_ANNUAL), []
    for year in range(2009, today.year):  # 2009-2014 for the Phase 13 base rates
        period = date(year, 12, 31)
        if period.isoformat() not in have or (is_open(period, today) and needs_refresh(CN_ANNUAL, today)):
            rows = datacenter("RPT_LICO_FN_CPD", f"(REPORTDATE='{period}'){A_SHARES}", ",".join(CN_RESULTS))
            frames.append(results_table(rows).assign(period=period.isoformat()))
            log.info("cn annual %s: %d rows", period, len(rows))
    if frames:
        merge(CN_ANNUAL, pd.concat(frames), ["code", "period"])
    have, frames = periods_in(CN_VALUATION), []
    ends = [date(y, m, d) for y in range(2018, today.year + 1) for m, d in ((6, 30), (12, 31))]
    for end in [e for e in ends if date(2018, 12, 1) < e < today and e.isoformat() not in have]:
        for back in range(8):  # holidays: step back to the last trading day
            day = (end - timedelta(days=back)).isoformat()
            if rows := datacenter("RPT_VALUEANALYSIS_DET", f"(TRADE_DATE='{day}')", ",".join(VALUATION_FIELDS)):
                df = pd.DataFrame(rows, columns=list(VALUATION_FIELDS)).rename(columns=VALUATION_FIELDS)
                frames.append(df.assign(trade_date=day, period=end.isoformat()))
                log.info("cn valuation %s: %d rows", day, len(rows))
                break
    if frames:
        merge(CN_VALUATION, pd.concat(frames), ["code", "period"])


def forecast_table(rows: list[dict]) -> pd.DataFrame:
    """业绩预告 rows -> one row per stock, period, indicator and notice: the range of the amount and of
    the change on a year earlier (%), the type (预增, 扭亏, ...) and last year's figure."""
    df = pd.DataFrame(rows, columns=list(FORECAST_FIELDS)).rename(columns=FORECAST_FIELDS)
    df["notice_date"], df["period"] = df["notice_date"].str[:10], df["period"].str[:10]
    return df


def update_forecasts(today: date, backfill_days: int = 400) -> None:
    """The market-wide 业绩预告 table, daily from a week before the newest stored notice (the first
    time, the last `backfill_days` days)."""
    have = periods_in(CN_FORECASTS, "notice_date")
    since = (date.fromisoformat(max(have)) - timedelta(days=7) if have else today - timedelta(days=backfill_days)).isoformat()
    rows = datacenter("RPT_PUBLIC_OP_NEWPREDICT", f"(NOTICE_DATE>='{since}')", ",".join(FORECAST_FIELDS),
                      sort="NOTICE_DATE,SECURITY_CODE,REPORT_DATE,PREDICT_FINANCE_CODE", sort_type="1,1,1,1")
    merge(CN_FORECASTS, forecast_table(rows), ["code", "period", "item_code", "notice_date"])
    log.info("cn forecasts: %d rows since %s", len(rows), since)


HK_LIST, HK_RESULTS = DATA / "quotes" / "hk_list.csv.gz", DATA / "fundamentals" / "hk_results.csv.gz"
US_ORGS, HK_HISTORY = DATA / "fundamentals" / "us_org.csv.gz", HISTORY / "hk_results.csv.gz"
HK_FIELDS = {"SECURITY_CODE": "code", "REPORT_DATE": "period", "START_DATE": "start", "DATE_TYPE_CODE": "date_type",
             "OPERATE_INCOME": "revenue", "HOLDER_PROFIT": "np", "OPERATE_INCOME_YOY": "rev_yoy",
             "HOLDER_PROFIT_YOY": "np_yoy", "GROSS_PROFIT_RATIO": "gross_margin", "BPS": "bps",
             "NETCASH_OPERATE": "ocf", "DEBT_ASSET_RATIO": "debt_ratio", "ISSUED_COMMON_SHARES": "shares",
             "BASIC_EPS": "eps", "ROE_AVG": "roe", "TOTAL_ASSETS": "assets",
             "TOTAL_MARKET_CAP": "mcap_em", "PE_TTM": "pe_ttm_em", "PB_TTM": "pb_ttm_em"}
HK_CURRENT = ["mcap_em", "pe_ttm_em", "pb_ttm_em"]  # today's values on every row: not history


def update_hk_list(today: date) -> None:
    """Every HK company profile: name, org code, industry and listing date (weekly). REITs, ETFs and
    other funds have no organisation type."""
    if not needs_refresh(HK_LIST, today):
        return
    rows = datacenter("RPT_HKF10_INFO_ORGPROFILE", "", "SECURITY_CODE,SECURITY_NAME_ABBR,ORG_CODE,BELONG_INDUSTRY,"
                      "INDUSTRY_TYPE,ORG_TYPE,LISTING_DATE")
    df = pd.DataFrame(rows)
    df.columns = ["code", "name", "org_code", "industry", "industry_type", "org_type", "listing_date"]
    write(df.assign(listing_date=df["listing_date"].str[:10]), HK_LIST)
    log.info("hk list: %d company profiles", len(df))


def hk_results(rows: list[dict]) -> pd.DataFrame:
    """Main-indicator rows -> a table keyed by code and period end. Money is in CNY: Eastmoney converts
    every company's figures at each period's rate; its growth rates are in the reporting currency."""
    df = pd.DataFrame(rows, columns=list(HK_FIELDS)).rename(columns=HK_FIELDS)
    df["period"], df["start"] = df["period"].str[:10], df["start"].str[:10]
    return df


def update_hk_fundamentals(today: date) -> None:
    """Main indicators of every HK company for periods ending in the last ~2.2 years: one market-wide
    table, weekly, and daily in the results seasons (March, April, August)."""
    if not needs_refresh(HK_RESULTS, today, open_period=today.month in (3, 4, 8)):
        return
    since = (today - timedelta(days=800)).isoformat()
    df = hk_results(datacenter("RPT_HKF10_FN_MAININDICATOR", f"(REPORT_DATE>='{since}')", ",".join(HK_FIELDS),
                               sort="SECURITY_CODE,REPORT_DATE", sort_type="1,1"))
    write(df, HK_RESULTS)
    log.info("hk results: %d rows for %d companies since %s", len(df), df["code"].nunique(), since)


def update_hk_history(today: date) -> None:
    """Main indicators of every HK company since 2015 (amounts in CNY, as in the weekly table): fetched
    once (again for a table saved before it carried total assets, merged in: companies Eastmoney no longer lists
    keep their rows), then topped up from the weekly table whenever it is newer, with no extra calls."""
    if not HK_HISTORY.exists() or "assets" not in pd.read_csv(HK_HISTORY, nrows=0).columns:
        df = hk_results(datacenter("RPT_HKF10_FN_MAININDICATOR", "(REPORT_DATE>='2015-01-01')", ",".join(HK_FIELDS),
                                   sort="SECURITY_CODE,REPORT_DATE", sort_type="1,1", max_pages=400))
        merge(HK_HISTORY, df.drop(columns=HK_CURRENT), ["code", "period", "date_type"])
        log.info("hk history: %d rows for %d companies", len(df), df["code"].nunique())
        return
    if HK_RESULTS.stat().st_mtime <= HK_HISTORY.stat().st_mtime:
        return
    weekly = pd.read_csv(HK_RESULTS, dtype={"code": str, "period": str, "start": str, "date_type": str})
    if "roe" in weekly:  # a weekly table fetched before Phase 7 has no eps/roe: wait for the next one
        merge(HK_HISTORY, weekly.drop(columns=HK_CURRENT), ["code", "period", "date_type"])


def load_hk_list() -> pd.DataFrame:
    return pd.read_csv(HK_LIST, dtype={"code": str, "org_code": str})


def hk_candidates() -> list[str]:
    """Ordinary shares (an organisation type, and not an RMB counter 8xxxx), largest first by
    Eastmoney's latest market value: the stocks whose prices are kept up to date."""
    lst = load_hk_list()
    lst = lst[lst["org_type"].notna() & (lst["code"] < "10000")]
    fund = pd.read_csv(HK_RESULTS, dtype={"code": str, "period": str}).sort_values("period")
    mcap = fund.groupby("code")["mcap_em"].last().reindex(lst["code"])
    return list(mcap.sort_values(ascending=False).dropna().index[:CONFIG["universe"]["hk_candidates"]])


def update_us_orgs(today: date) -> None:
    """US ticker -> Eastmoney org code (weekly), to find the HK line of a US-listed issuer."""
    if not needs_refresh(US_ORGS, today):
        return
    df = pd.DataFrame(datacenter("RPT_USF10_INFO_ORGPROFILE", "", "SECURITY_CODE,ORG_CODE"))
    write(df.set_axis(["code", "org_code"], axis=1), US_ORGS)
