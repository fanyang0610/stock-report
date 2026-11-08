"""One HK-listed company's statements from Eastmoney's HK F10 tables (RPT_HKF10_FN_INCOME_PC / BALANCE_PC /
CASHFLOW_PC: one row per item, annual, interim and quarterly reports), mapped to the shared layout by item name; the share count
from the main indicators. Eastmoney gives every amount in CNY at the period end's rate (SHKP's FY2026 profit: CNY
18.61bn = HKD 21.43bn x 0.8686, HSBC's FY2025: CNY 148.32bn = USD 21.10bn x 7.0288), so each period goes back to the
reporting currency at that rate (yahoo.cny_per), as history.hk_years does. Companies Eastmoney has no statements for
(REITs such as Link) take Yahoo's annual series as their only source, which the fact sheet says."""

import pandas as pd

from stockreport.fetch import yahoo
from stockreport.fetch.eastmoney import datacenter
from stockreport.research import KEYS, STATEMENT, num

# key -> item names, the first present wins; a list of lists is summed (each inner list: the first present)
ITEMS = {
    "revenue": ["营运收入", "营业额", "经营收入总额"], "cogs": ["销售成本", "营业成本"], "gp": ["毛利"],
    "sga": [["销售及分销费用"], ["行政开支", "行政及一般费用"]], "rd": ["研究及开发费用", "研发费用"],
    "op_income": ["经营溢利"], "interest": ["融资成本"], "pretax": ["除税前溢利"], "tax": ["税项"],
    "ni": ["股东应占溢利"], "da": ["加:折旧及摊销"], "ocf": ["经营业务现金净额"],
    "capex": [["购建固定资产"], ["购建无形资产及其他资产"]], "div_paid": ["已付股息(融资)"], "buyback": ["回购股份"],
    "assets": ["总资产"], "cur_assets": ["流动资产合计"], "cur_liab": ["流动负债合计"],
    "cash": [["现金及等价物", "现金及现金等价物"], ["短期存款"]], "receivables": ["应收帐款"], "inventory": ["存货"],
    "ppe": ["物业厂房及设备"], "goodwill": ["商誉"], "intangibles": ["无形资产"], "liabilities": ["总负债"],
    "debt": [["短期贷款"], ["长期贷款"], ["应付票据(非流动)"], ["融资租赁负债(流动)"], ["融资租赁负债(非流动)"]],
    "lt_debt": [["长期贷款"], ["应付票据(非流动)"]], "equity": ["股东权益", "归属于母公司股东权益"],
    "pref": [["优先股"], ["永久资本证券", "永续资本证券", "其他权益工具"]],
    "minority": ["少数股东权益", "非控股股东权益"], "retained": ["保留溢利(累计亏损)"],
    "contract_liab": [["合约负债"], ["递延收入(流动)"]], "cip": ["在建工程"]}
DATE_TYPES = {"001": 12, "002": 6, "003": 3, "004": 9}  # annual, interim, and quarterly reporters' Q1 and Q3 (year to date)


def pick(items: dict, names: list):
    if names and isinstance(names[0], list):
        vals = [pick(items, inner) for inner in names]
        return sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None
    return next((items[n] for n in names if items.get(n) is not None), None)


def statement_rows(rows: list[dict], shares: dict[str, tuple]) -> pd.DataFrame:
    """Long rows (REPORT_DATE, DATE_TYPE_CODE, STD_ITEM_NAME, AMOUNT) of the three statements -> one row per period
    in the shared layout (research.KEYS). Capex, dividends and buybacks are positive outflows."""
    by = {}
    for r in rows:
        key = (r["REPORT_DATE"][:10], r["DATE_TYPE_CODE"])
        by.setdefault(key, {})[r["STD_ITEM_NAME"]] = num(r.get("AMOUNT"))
    out = []
    for (period, kind), items in sorted(by.items()):
        row = {"period": period, "months": DATE_TYPES.get(kind, 0)} | {k: pick(items, names) for k, names in ITEMS.items()}
        for k in ("capex", "div_paid", "buyback"):
            row[k] = abs(row[k]) if row[k] is not None else None
        if row["gp"] is None and None not in (row["revenue"], row["cogs"]):
            row["gp"] = row["revenue"] - row["cogs"]
        if row["cogs"] is None and None not in (row["revenue"], row["gp"]):
            row["cogs"] = row["revenue"] - row["gp"]
        row["shares"], row["issued"] = shares.get(period, (None, None))
        out.append(row)
    return pd.DataFrame(out).reindex(columns=STATEMENT + ["issued"])


def to_currency(df: pd.DataFrame, currency: str) -> pd.DataFrame:
    """Eastmoney's CNY amounts back in the reporting currency at each period end's rate; periods before the rate
    history (data/fx_cny.csv.gz, ~12 years) are left out."""
    rate = yahoo.cny_per(pd.Series(currency, index=df.index), df["period"])
    if rate.isna().all():
        raise RuntimeError(f"no CNY rate for {currency}")
    df, rate = df[rate.notna()], rate[rate.notna()]
    money = [k for k in KEYS if k not in ("shares", "eps")]
    return df.assign(**{k: pd.to_numeric(df[k], errors="coerce") / rate for k in money}, currency=currency)


def statements(code: str, currency: str) -> pd.DataFrame:
    sec = f'(SECUCODE="{code}.HK")(DATE_TYPE_CODE in ("001","002","003","004"))(REPORT_DATE>=\'2013-01-01\')'
    rows = []
    for part in ("INCOME", "BALANCE", "CASHFLOW"):
        rows += datacenter(f"RPT_HKF10_FN_{part}_PC", sec, "REPORT_DATE,DATE_TYPE_CODE,STD_ITEM_NAME,AMOUNT",
                           sort="REPORT_DATE", sort_type="-1", page_size=500, max_pages=20)
    if not rows:
        return pd.DataFrame(columns=STATEMENT)
    main = datacenter("RPT_HKF10_FN_MAININDICATOR", f'(SECUCODE="{code}.HK")', "REPORT_DATE,ISSUED_COMMON_SHARES,"
                      "HOLDER_PROFIT,BASIC_EPS", sort="REPORT_DATE", sort_type="-1", page_size=200, max_pages=2)
    return to_currency(statement_rows(rows, {m["REPORT_DATE"][:10]: shares_of(m) for m in main}), currency)


def shares_of(m: dict) -> tuple:
    """A period's shares as profit over basic EPS (the weighted average; both CNY in this table) and the issued count:
    ISSUED_COMMON_SHARES repeats today's count on every period (Tencent: 9.09bn back to 2013, 9.53bn by EPS in 2021),
    so buybacks and placements show only through EPS. A loss or a tiny EPS leaves the issued count."""
    profit, eps, issued = num(m.get("HOLDER_PROFIT")), num(m.get("BASIC_EPS")), num(m.get("ISSUED_COMMON_SHARES"))
    by_eps = profit / eps if profit and eps and profit > 0 and eps > 0.01 else None
    return by_eps or issued, issued
