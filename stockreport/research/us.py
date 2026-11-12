"""One US-listed company's data: SEC companyfacts (fetched and parsed in memory, never stored: Storage rule) for every
fiscal year since 2015 in fetch/sec.py's layout plus the concepts the accounting checks need (current assets and
liabilities, receivables, inventory, PP&E, SG&A, depreciation, interest, debt, retained earnings, buybacks, stock-based
pay), the trailing twelve months against a year earlier, and Nasdaq's analyst pages (yearly EPS consensus, the price
target and rating counts), short interest and insider trades."""

from datetime import date, datetime

import pandas as pd

from stockreport.fetch import Http, sec
from stockreport.research import STATEMENT, num

EXTRA = {  # key -> (us-gaap concepts, ifrs-full concepts); a (total, part) pair stands for total - part
    "cogs": (sec.DURATION["cost"], ["CostOfSales"]),
    "sga": (["SellingGeneralAndAdministrativeExpense"], ["SellingGeneralAndAdministrativeExpense"]),
    "rd": (["ResearchAndDevelopmentExpense"], ["ResearchAndDevelopmentExpense"]),
    "interest": (["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestExpenseOperating"],
                 ["FinanceCosts", "InterestExpense"]),
    "pretax": (["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
               ["ProfitLossBeforeTax"]),
    "tax": (["IncomeTaxExpenseBenefit"], ["IncomeTaxExpenseContinuingOperations"]),
    "da": (["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization",
            "Depreciation"], ["DepreciationAndAmortisationExpense", "AdjustmentsForDepreciationAndAmortisationExpense"]),
    "buyback": (["PaymentsForRepurchaseOfCommonStock"], ["PaymentsToAcquireOrRedeemEntitysShares"]),
    "sbc": (["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"], ["AdjustmentsForSharebasedPayments"]),
}
EXTRA_INSTANT = {
    "cur_assets": (["AssetsCurrent"], ["CurrentAssets"]),
    "cur_liab": (["LiabilitiesCurrent"], ["CurrentLiabilities"]),
    "cash": (["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
             ["CashAndCashEquivalents"]),
    "st_invest": (["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
                  ["CurrentInvestments"]),
    "receivables": (["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"], ["TradeAndOtherCurrentReceivables"]),
    "inventory": (["InventoryNet"], ["Inventories"]),
    "ppe": (["PropertyPlantAndEquipmentNet",
             "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization"],
            ["PropertyPlantAndEquipment"]),
    "goodwill": (["Goodwill"], ["Goodwill"]),
    "intangibles": (["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"], ["IntangibleAssetsOtherThanGoodwill"]),
    # debt: a total (long-term with its current part; a REIT's notes payable) plus short-term borrowings, else the parts
    "debt_total": (["DebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
                    "DebtLongtermAndShorttermCombinedAmount", "LongTermDebt", "NotesPayable"], ["Borrowings"]),
    "st_borrow": (["ShortTermBorrowings", "CommercialPaper"], ["ShorttermBorrowings"]),
    "lt_debt": (["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
                ["NoncurrentPortionOfNoncurrentBorrowings", "LongtermBorrowings"]),
    "st_debt": (["LongTermDebtCurrent", "DebtCurrent"], ["CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"]),
    "retained": (["RetainedEarningsAccumulatedDeficit"], ["RetainedEarnings"]),
    "pref2": (["PreferredStockValueOutstanding", "PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount",
               "PreferredStockIncludingAdditionalPaidInCapital", "PreferredStockCarryingAmount"], ["PreferenceShares"]),
    "minority": (["MinorityInterest"], ["NoncontrollingInterests"]),
    "contract_liab": (["ContractWithCustomerLiabilityCurrent", "ContractWithCustomerLiability", "DeferredRevenueCurrent"],
                      ["CurrentContractLiabilities", "ContractLiabilities"]),
}


def parse_statements(code: str, payload: dict) -> pd.DataFrame:
    """Fiscal years in the shared layout (research.KEYS), in the taxonomy and currency fetch/sec.py picks."""
    base = sec.parse_annual(code, payload)
    if not base:
        return pd.DataFrame(columns=STATEMENT)
    taxonomy, unit = base[0]["taxonomy"], base[0]["currency"]
    tax, col = payload["facts"][taxonomy], 0 if taxonomy == "us-gaap" else 1
    series = {k: sec.annual(tax, names[col], unit) for k, names in EXTRA.items()}
    series |= {k: sec.annual(tax, names[col], unit, instant=True) for k, names in EXTRA_INSTANT.items()}
    series["eps"] = sec.annual(tax, ["EarningsPerShareDiluted", "EarningsPerShareBasic"] if col == 0 else
                               ["DilutedEarningsLossPerShare", "BasicEarningsLossPerShare"], f"{unit}/shares")
    rows = []
    for b in base:
        end = b["fy_end"]
        get = lambda k: series[k].get(end, next((v for e, v in series[k].items() if abs(sec.days(e, end)) <= 7), None))
        row = {k: get(k) for k in series} | {
            "period": end, "months": 12, "currency": unit, "notice": b.get("filed"), "revenue": b.get("revenue"),
            "gp": b.get("gp"), "op_income": b.get("op_income"), "ni": b.get("ni_common") or b.get("ni"),
            "ni_core": b.get("ni_cont"), "ocf": b.get("ocf"), "capex": b.get("capex"), "div_paid": b.get("div"),
            "assets": b.get("assets"), "liabilities": b.get("liabilities"), "equity": b.get("equity"), "pref": b.get("pref") if b.get("pref") is not None else get("pref2"),
            "shares": b.get("shares")}
        if row["gp"] is None and None not in (row["revenue"], row["cogs"]):
            row["gp"] = row["revenue"] - row["cogs"]
        if row["cash"] is not None and row["st_invest"] is not None:
            row["cash"] += row["st_invest"]
        parts = ("debt_total", "st_borrow") if row["debt_total"] is not None else ("lt_debt", "st_debt", "st_borrow")
        debts = [row[k] for k in parts if row[k] is not None]
        row["debt"] = sum(debts) if debts else None
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=STATEMENT).sort_values("period").reset_index(drop=True)


def latest(code: str, payload: dict, today: date) -> dict:
    """The trailing twelve months to the latest 10-Q/10-K against the twelve months a year earlier (fetch/sec.py), the
    same trailing months of pretax profit, interest, capex and depreciation, the latest equity and the latest filing's
    cover-page share count (else the quarter's basic weighted average)."""
    f = sec.parse_facts(code, payload, today)
    if f.get("gap"):
        return {}
    gaap = payload["facts"]["us-gaap"]
    extra = {k: sec.ttm(sec.values(gaap, names), f["period"]) for k, names in (
        ("pretax", EXTRA["pretax"][0]), ("interest", EXTRA["interest"][0]), ("da", EXTRA["da"][0]),
        ("capex", sec.TAXONOMIES["us-gaap"][0]["capex"]), ("op_income", sec.TAXONOMIES["us-gaap"][0]["op_income"]))}
    return {"period": f["period"], "months": 12, "basis": "TTM", "notice": f.get("notice_date"), "equity": f.get("equity"),
            "shares": f.get("shares_cover") or f.get("shares_basic")} | extra | {
        f"{k}{s}": f.get(f"{src}_{w}") for k, src in (("revenue", "revenue"), ("ni", "np"), ("gp", "gp"), ("ocf", "ocf"))
        for s, w in (("", "ttm"), ("_prior", "prior"))}


def from_annual(st: pd.DataFrame) -> dict:
    """latest() for a filer without quarterly reports (a 20-F filer: Novo Nordisk, TSMC): the last fiscal year as the
    trailing twelve months, against the year before."""
    a = st[st["months"] == 12].sort_values("period")
    if a.empty:
        return {}
    r, prior = a.iloc[-1], (a.iloc[-2] if len(a) > 1 else None)
    val = lambda row, k: None if row is None or k not in row or pd.isna(row[k]) else float(row[k])
    return {"period": r["period"], "months": 12, "basis": "FY", "notice": None if pd.isna(r.get("notice")) else r["notice"],
            "equity": val(r, "equity"), "shares": val(r, "shares")} | {k: val(r, k) for k in ("pretax", "interest", "da", "capex", "op_income")} | {
        f"{k}{s}": val(row, k) for k in ("revenue", "ni", "gp", "ocf") for s, row in (("", r), ("_prior", prior))}


def companyfacts(code: str) -> dict:
    cik = sec.update_ciks(date.today()).drop_duplicates("code").set_index("code")["cik"].get(code)
    if cik is None:
        raise RuntimeError(f"{code} has no SEC CIK")
    resp = sec.make_http().get(sec.FACTS.format(cik=int(cik)), ok=(200, 404))
    return resp.json() if resp.status_code == 200 else {"cik": int(cik)}


def nasdaq() -> Http:
    return Http(min_interval=0.5, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})


def data(http: Http, path: str) -> dict:
    return http.get("https://api.nasdaq.com/api/" + path, params={"assetclass": "stocks"}).json().get("data") or {}


def parse_consensus(forecast: dict, target: dict, ratings: dict) -> dict:
    """Nasdaq: EPS by fiscal year (the year it ends in) with the estimate count, the consensus target and range, and
    the buy / hold / sell counts behind it."""
    rows = (forecast.get("yearlyForecast") or {}).get("rows") or []
    eps = {str(datetime.strptime(r["fiscalEnd"], "%b %Y").year): num(r.get("consensusEPSForecast")) for r in rows}
    count = {str(datetime.strptime(r["fiscalEnd"], "%b %Y").year): num(r.get("noOfEstimates")) for r in rows}
    ov = target.get("consensusOverview") or {}
    return {"source": "Nasdaq", "eps": eps, "estimates": count, "analysts": max(count.values(), default=None),
            "target_mean": num(ov.get("priceTarget")), "target_low": num(ov.get("lowPriceTarget")),
            "target_high": num(ov.get("highPriceTarget")),
            "ratings": {k: num(ov.get(k)) for k in ("buy", "hold", "sell")}, "rating": ratings.get("meanRatingType")}


def consensus(code: str) -> dict:
    http, sym = nasdaq(), code.replace(".", "-")
    return parse_consensus(data(http, f"analyst/{sym}/earnings-forecast"), data(http, f"analyst/{sym}/targetprice"),
                           data(http, f"analyst/{sym}/ratings"))


def parse_flows(short: dict, insider: dict) -> dict:
    """Short interest (the two latest settlement dates) and insider trades over 3 and 12 months (Nasdaq's Form 4
    summary: open-market buys, sells, shares bought and sold)."""
    rows = (short.get("shortInterestTable") or {}).get("rows") or []
    table = lambda part: {r["insiderTrade"]: (num(r.get("months3")), num(r.get("months12")))
                          for r in (insider.get(part) or {}).get("rows") or []}
    trades, shares = table("numberOfTrades"), table("numberOfSharesTraded")
    return {"short": [{"date": r.get("settlementDate"), "shares": num(r.get("interest")), "days_to_cover": num(r.get("daysToCover"))}
                      for r in rows[:2]],
            "insider": {"buys": trades.get("Number of Open Market Buys"), "sells": trades.get("Number of Sells"),
                        "shares_bought": shares.get("Number of Shares Bought"), "shares_sold": shares.get("Number of Shares Sold"),
                        "periods": ["3m", "12m"]}}


def flows(code: str) -> dict:
    http, sym = nasdaq(), code.replace(".", "-")
    short = http.get(f"https://api.nasdaq.com/api/quote/{sym}/short-interest", params={"assetClass": "stocks"}).json()
    insider = http.get(f"https://api.nasdaq.com/api/company/{sym}/insider-trades",
                       params={"limit": 5, "type": "all", "sortColumn": "lastDate", "sortOrder": "DESC"}).json()
    return parse_flows(short.get("data") or {}, insider.get("data") or {})
