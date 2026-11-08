"""One A-share's data from Eastmoney's datacenter (serial, at most one request a second, the a-stock-data skill's
rate-limit rules): the three statements for every report since listing (general, bank, insurer or broker layouts by
ORG_TYPE), the main indicators (total shares; banks' bad loans, provisions, capital and margin; insurers' solvency),
主营构成 segments, the 研报一致预期 consensus with the brokers' ratings and target range, six months of broker reports,
the daily valuation table since 2018 (kept at month ends), and the a-stock-data skill's flow and holder endpoints:
融资融券, 股东户数, 解禁, 质押, 增减持, 回购, 龙虎榜, 机构调研 and 分红."""

import logging
from datetime import date, timedelta

import pandas as pd

from stockreport.fetch import Http
from stockreport.fetch.eastmoney import datacenter
from stockreport.research import STATEMENT, num

log = logging.getLogger(__name__)
LAYOUT = {"通用": "G", "银行": "B", "保险": "I", "证券": "S"}  # ORG_TYPE -> statement report prefix
EXTRA = {"npl": "NONPERLOAN", "provision_cover": "BLDKBBL", "car": "NEWCAPITALADER", "cet1": "HXYJBCZL",
         "nim": "NET_INTEREST_MARGIN", "solvency": "SOLVENCY_AR", "loans": "GROSSLOANS", "deposits": "TOTALDEPOSITS"}


def secucode(code: str) -> str:
    return f"{code}.{'SH' if code.startswith(('6', '9')) else 'BJ' if code.startswith(('4', '8', '92')) else 'SZ'}"


def get(report: str, filter_str: str, sort: str, page_size: int = 200, max_pages: int = 10) -> list[dict]:
    return datacenter(report, filter_str, "ALL", sort=sort, sort_type="-1", page_size=page_size, max_pages=max_pages)


def first(row: dict, *names):
    return next((num(row[n]) for n in names if num(row.get(n)) is not None), None)


def total(row: dict, *names):
    vals = [num(row.get(n)) for n in names if num(row.get(n)) is not None]
    return sum(vals) if vals else None


def months(report_type: str) -> int:
    return {"一季报": 3, "中报": 6, "三季报": 9, "年报": 12}.get(report_type, 0)


def statement_rows(income: list[dict], balance: list[dict], cash: list[dict], main: list[dict]) -> pd.DataFrame:
    """Every report period's statements in the shared layout (research.KEYS); banks', insurers' and brokers' layouts
    fill what they have (revenue is their total operating income). Dividends paid aren't read from the cash flow (CN
    lumps interest paid in): the fact sheet takes them from the dividend table."""
    by = lambda rows: {r["REPORT_DATE"][:10]: r for r in rows}
    inc, bal, cf, mf = by(income), by(balance), by(cash), by(main)
    out = []
    for period, i in inc.items():
        b, c, m = bal.get(period, {}), cf.get(period, {}), mf.get(period, {})
        revenue, cogs = first(i, "TOTAL_OPERATE_INCOME", "OPERATE_INCOME"), first(i, "OPERATE_COST")
        row = {"period": period, "months": months(i.get("REPORT_TYPE", "")), "currency": i.get("CURRENCY") or "CNY",
               "notice": (i.get("NOTICE_DATE") or "")[:10], "opinion": i.get("OPINION_TYPE"),
               "updated": (b.get("UPDATE_DATE") or "")[:10],  # the year-end balance: later when a later report restated it
               "revenue": revenue, "cogs": cogs, "gp": revenue - cogs if None not in (revenue, cogs) else None,
               "sga": total(i, "SALE_EXPENSE", "MANAGE_EXPENSE") or first(i, "BUSINESS_MANAGE_EXPENSE"),
               "rd": first(i, "RESEARCH_EXPENSE"), "op_income": first(i, "OPERATE_PROFIT"),
               "interest": first(i, "FE_INTEREST_EXPENSE"), "pretax": first(i, "TOTAL_PROFIT"), "tax": first(i, "INCOME_TAX"),
               "ni": first(i, "PARENT_NETPROFIT"), "ni_core": first(i, "DEDUCT_PARENT_NETPROFIT"), "eps": first(i, "BASIC_EPS"),
               "da": total(c, "FA_IR_DEPR", "IA_AMORTIZE", "LPE_AMORTIZE", "USERIGHT_ASSET_AMORTIZE"),
               "ocf": first(c, "NETCASH_OPERATE"), "capex": first(c, "CONSTRUCT_LONG_ASSET"),
               "assets": first(b, "TOTAL_ASSETS"), "cur_assets": first(b, "TOTAL_CURRENT_ASSETS"),
               "cur_liab": first(b, "TOTAL_CURRENT_LIAB"),
               "cash": total(b, "MONETARYFUNDS", "TRADE_FINASSET", "TRADE_FINASSET_NOTFVTPL", "LEND_FUND"),  # 拆出资金:
               # a finance subsidiary's interbank lending (Moutai's CNY 99bn)
               "receivables": first(b, "NOTE_ACCOUNTS_RECE") or total(b, "ACCOUNTS_RECE", "NOTE_RECE"),
               "inventory": first(b, "INVENTORY"), "ppe": first(b, "FIXED_ASSET"), "goodwill": first(b, "GOODWILL"),
               "intangibles": first(b, "INTANGIBLE_ASSET"), "liabilities": first(b, "TOTAL_LIABILITIES"),
               "debt": total(b, "SHORT_LOAN", "NONCURRENT_LIAB_1YEAR", "LONG_LOAN", "BOND_PAYABLE", "LEASE_LIAB"),
               "lt_debt": total(b, "LONG_LOAN", "BOND_PAYABLE"), "equity": first(b, "TOTAL_PARENT_EQUITY"),
               "pref": first(b, "OTHER_EQUITY_TOOL"),  # preferred shares and perpetual bonds
               "minority": first(b, "MINORITY_EQUITY"), "retained": total(b, "UNASSIGN_RPOFIT", "SURPLUS_RESERVE"),
               "shares": first(m, "TOTAL_SHARE") or first(b, "SHARE_CAPITAL"), "share_capital": first(b, "SHARE_CAPITAL"),
               "contract_liab": total(b, "CONTRACT_LIAB", "ADVANCE_RECEIVABLES"), "cip": first(b, "CIP")}
        out.append(row | {k: first(m, f) for k, f in EXTRA.items()})
    df = pd.DataFrame(out)
    return df.reindex(columns=STATEMENT + ["opinion", "updated", "share_capital"] + list(EXTRA)).sort_values("period").reset_index(drop=True)


def statements(code: str) -> pd.DataFrame:
    sec = f'(SECUCODE="{secucode(code)}")'
    main = get("RPT_F10_FINANCE_MAINFINADATA", sec, "REPORT_DATE")
    if not main:
        raise RuntimeError(f"no Eastmoney statements for {code}")
    kind = main[0].get("ORG_TYPE") or "通用"
    p = LAYOUT.get(kind, "G")
    parts = [get(f"RPT_F10_FINANCE_{p}{s}", sec, "REPORT_DATE") for s in ("INCOME", "BALANCE", "CASHFLOW")]
    return statement_rows(*parts, main).assign(org_type=kind)


def segments(code: str) -> pd.DataFrame:
    """主营构成 for the last three fiscal years and the latest period: by industry (1), product (2) and region (3)."""
    rows = get("RPT_F10_FN_MAINOP", f'(SECUCODE="{secucode(code)}")', "REPORT_DATE", page_size=500, max_pages=2)
    df = pd.DataFrame([{"period": r["REPORT_DATE"][:10], "by": {"1": "industry", "2": "product", "3": "region"}.get(str(r["MAINOP_TYPE"])),
                        "item": r["ITEM_NAME"], "revenue": num(r.get("MAIN_BUSINESS_INCOME")), "share": num(r.get("MBI_RATIO")),
                        "gross_margin": num(r.get("GROSS_RPOFIT_RATIO"))} for r in rows])
    if df.empty:
        return df
    keep = sorted(p for p in df["period"].unique() if p.endswith("12-31"))[-3:] + [df["period"].max()]
    return df[df["period"].isin(keep)].drop_duplicates(["period", "by", "item"])


def consensus(code: str, today: date) -> dict:
    """研报一致预期 (EPS by year, A = actual, E = estimate; the brokers' rating counts and the range of their targets) and
    the last six months of broker reports (title, broker, rating, EPS this and next two years as labelled when read)."""
    rows = get("RPT_WEB_RESPREDICT", f'(SECURITY_CODE="{code}")', "SECURITY_CODE", page_size=5, max_pages=1)
    r = rows[0] if rows else {}
    eps = {str(r[f"YEAR{i}"]): num(r.get(f"EPS{i}")) for i in range(1, 5) if r.get(f"YEAR_MARK{i}") == "E"}
    http = Http(min_interval=2.0, headers={"Referer": "https://data.eastmoney.com/"})
    payload = http.get("https://reportapi.eastmoney.com/report/list", params={
        "industryCode": "*", "pageSize": "100", "industry": "*", "rating": "*", "ratingChange": "*", "fields": "",
        "beginTime": (today - timedelta(days=183)).isoformat(), "endTime": today.isoformat(), "pageNo": "1",
        "qType": "0", "orgCode": "", "code": code, "rcode": ""}).json()
    reports = [{"date": x["publishDate"][:10], "broker": x.get("orgSName"), "title": x.get("title"),
                "rating": x.get("emRatingName") or x.get("sRatingName"),
                "eps": {str(today.year + k): num(x.get(f)) for k, f in enumerate(("predictThisYearEps", "predictNextYearEps",
                                                                                  "predictNextTwoYearEps"))}}
               for x in payload.get("data") or []]
    return {"source": "Eastmoney 研报一致预期", "eps": eps, "analysts": num(r.get("RATING_ORG_NUM")),
            "ratings": {"buy": num(r.get("RATING_BUY_NUM")), "add": num(r.get("RATING_ADD_NUM")),
                        "neutral": num(r.get("RATING_NEUTRAL_NUM")), "reduce": num(r.get("RATING_REDUCE_NUM")),
                        "sell": num(r.get("RATING_SALE_NUM"))},
            "target_high": num(r.get("DEC_AIMPRICEMAX")), "target_low": num(r.get("DEC_AIMPRICEMIN")),
            "industry": r.get("INDUSTRY_BOARD"), "reports": reports}


def valuation(code: str) -> pd.DataFrame:
    """The daily valuation table since 2018 at month ends (the latest day kept too): close, market value, shares,
    PE-TTM, PB-MRQ, PS-TTM, price to operating cash flow (TTM)."""
    rows = get("RPT_VALUEANALYSIS_DET", f'(SECURITY_CODE="{code}")', "TRADE_DATE", page_size=500, max_pages=10)
    df = pd.DataFrame([{"date": r["TRADE_DATE"][:10], "close": num(r.get("CLOSE_PRICE")), "mcap": num(r.get("TOTAL_MARKET_CAP")),
                        "shares": num(r.get("TOTAL_SHARES")), "pe": num(r.get("PE_TTM")), "pb": num(r.get("PB_MRQ")),
                        "ps": num(r.get("PS_TTM")), "pcf": num(r.get("PCF_OCF_TTM")), "industry": r.get("BOARD_NAME")}
                       for r in rows]).sort_values("date")
    month_end = df.groupby(df["date"].str[:7]).tail(1)
    return pd.concat([month_end, df.tail(1)]).drop_duplicates("date")


def since(rows: list[dict] | None, field: str, start: str) -> list[dict] | None:
    return None if rows is None else [r for r in rows if (r.get(field) or "")[:10] >= start]


def optional(report: str, filter_str: str, sort: str, page_size: int) -> list[dict] | None:
    """One flow table; None when the call fails (the fact sheet then says the item is unavailable)."""
    try:
        return get(report, filter_str, sort, page_size=page_size, max_pages=1)
    except Exception as e:
        log.warning("%s %s: %s", report, filter_str, e)
        return None


def flows(code: str, today: date) -> dict:
    """The money and holder signals of the report's sections 5, 10 and 11, from a-stock-data's endpoints."""
    year_ago, f = (today - timedelta(days=365)).isoformat(), f'(SECURITY_CODE="{code}")'
    half = (today - timedelta(days=183)).isoformat()
    margin = optional("RPTA_WEB_RZRQ_GGMX", f'(SCODE="{code}")', "DATE", 250) or []
    m = lambda i: num(margin[i]["RZYE"]) if len(margin) > i else None
    holders = optional("RPT_HOLDERNUM_DET", f, "END_DATE", 8)
    lifts = optional("RPT_LIFT_STAGE", f + f"(FREE_DATE>='{year_ago}')(FREE_DATE<='{(today + timedelta(days=365)).isoformat()}')",
                     "FREE_DATE", 50)
    pledge = optional("RPT_CSDC_LIST", f, "TRADE_DATE", 1)
    trades = since(optional("RPT_SHARE_HOLDER_INCREASE", f + f"(NOTICE_DATE>='{year_ago}')", "NOTICE_DATE", 100), "NOTICE_DATE", year_ago)
    buybacks = optional("RPTA_WEB_GETHGLIST_NEW", f'(DIM_SCODE="{code}")', "UPD", 5)
    board = since(optional("RPT_DAILYBILLBOARD_DETAILSNEW", f + f"(TRADE_DATE>='{year_ago}')", "TRADE_DATE", 100), "TRADE_DATE", year_ago)
    survey = since(optional("RPT_ORG_SURVEYNEW", f, "NOTICE_DATE", 50), "NOTICE_DATE", half)  # one row per meeting
    divs = optional("RPT_SHAREBONUS_DET", f, "EX_DIVIDEND_DATE", 100)
    dividend_rows = lambda rows: None if rows is None else dividend_list(rows)
    each = lambda rows, fn: None if rows is None else [fn(r) for r in rows]
    return {
        "margin": {"balance": m(0), "date": margin[0]["DATE"][:10] if margin else None, "balance_60d": m(59),
                   "balance_250d": m(249), "share_of_float": num(margin[0].get("RZYEZB")) if margin else None,
                   "short_balance": num(margin[0].get("RQYE")) if margin else None},
        "holders": each(holders, lambda h: {"date": h["END_DATE"][:10], "count": num(h.get("HOLDER_NUM")),
                                            "change": num(h.get("HOLDER_NUM_RATIO"))}),
        "lockups": each(lifts, lambda x: {"date": x["FREE_DATE"][:10], "type": x.get("FREE_SHARES_TYPE"),
                                          "shares": num(x.get("FREE_SHARES")), "able_shares": num(x.get("ABLE_FREE_SHARES")),
                                          "of_total": num(x.get("TOTAL_RATIO"))}),
        "pledge": None if pledge is None else {"date": pledge[0]["TRADE_DATE"][:10] if pledge else None,
                                               "ratio": num(pledge[0].get("PLEDGE_RATIO")) if pledge else 0.0},
        "holder_trades": each(trades, lambda t: {"date": t["NOTICE_DATE"][:10], "holder": t.get("HOLDER_NAME"),
                                                 "direction": t.get("DIRECTION"), "shares": num(t.get("CHANGE_NUM_SYMBOL")),
                                                 "of_total": num(t.get("AFTER_CHANGE_RATE")), "channel": t.get("MARKET")}),
        "buybacks": each(buybacks, lambda b: {"notice": (b.get("UPDATEDATE") or "")[:10], "progress": b.get("REPURPROGRESS"),
                                              "amount_done": num(b.get("REPURAMOUNT")), "amount_cap": num(b.get("REPURAMOUNTLIMIT")),
                                              "start": (b.get("REPURSTARTDATE") or "")[:10], "end": (b.get("REPURENDDATE") or "")[:10]}),
        "dragon_tiger_1y": None if board is None else {"days": len({b["TRADE_DATE"][:10] for b in board}),
                                                       "net": sum(num(b.get("BILLBOARD_NET_AMT")) or 0 for b in board)},
        "surveys_6m": None if survey is None else {"events": len(survey), "institutions": sum(num(s.get("SUM")) or 0 for s in survey)},
        "dividends": dividend_rows(divs)}


def dividend_list(rows: list[dict]) -> list[dict]:
    """分红: per share and per fiscal period (the source's amounts are per 10 shares)."""
    return [{"period": (d.get("REPORT_DATE") or "")[:10], "ex_date": (d.get("EX_DIVIDEND_DATE") or "")[:10],
             "dps": (num(d.get("PRETAX_BONUS_RMB")) or 0) / 10, "bonus": (num(d.get("BONUS_IT_RATIO")) or 0) / 10,
             "progress": d.get("ASSIGN_PROGRESS")} for d in rows]


def dividends(code: str) -> list[dict]:
    return dividend_list(get("RPT_SHAREBONUS_DET", f'(SECURITY_CODE="{code}")', "EX_DIVIDEND_DATE", page_size=100, max_pages=1))
