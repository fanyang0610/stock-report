"""One US-listed company's data: SEC companyfacts (fetched and parsed in memory, never stored: Storage rule) for every
fiscal year since 2015 in fetch/sec.py's layout plus the concepts the accounting checks need (current assets and
liabilities, receivables, inventory, PP&E, SG&A, depreciation, interest, debt, retained earnings, buybacks, stock-based
pay), the trailing twelve months against a year earlier, and Nasdaq's analyst pages (yearly EPS consensus, the price
target and rating counts), short interest and insider trades."""

import math
import re
import xml.etree.ElementTree as ET
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
    # non-operating stakes and long-term investments at book (their income is outside operating income, which is the
    # DCF's EBIT): the total where tagged, else its parts (Amazon's private stakes, Apple's long-term securities)
    "lt_invest": (["LongTermInvestments"], []),
    "inv_equity": (["EquityMethodInvestments"], ["InvestmentsAccountedForUsingEquityMethod",
                                                 "InvestmentsInAssociatesAccountedForUsingEquityMethod"]),
    "inv_securities": (["MarketableSecuritiesNoncurrent", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent"],
                       ["OtherNoncurrentFinancialAssets"]),
    "inv_private": (["EquitySecuritiesWithoutReadilyDeterminableFairValueAmount"], []),
    "inv_other": (["OtherLongTermInvestments", "EquitySecuritiesFvNiNoncurrent"], []),
}
INVEST_PARTS = ("inv_equity", "inv_securities", "inv_private", "inv_other")


def parse_statements(code: str, payload: dict) -> pd.DataFrame:
    """Fiscal years in the shared layout (research.KEYS), in the taxonomy and currency fetch/sec.py picks."""
    base = sec.parse_annual(code, payload)
    if not base:
        return pd.DataFrame(columns=STATEMENT)
    taxonomy, unit = base[0]["taxonomy"], base[0]["currency"]
    tax, col = payload["facts"][taxonomy], 0 if taxonomy == "us-gaap" else 1
    series = {k: sec.annual(tax, names[col], unit) for k, names in EXTRA.items()}
    series |= {k: sec.annual(tax, names[col], unit, instant=True) for k, names in EXTRA_INSTANT.items()}
    series["avg_shares"] = sec.annual(tax, [sec.BASIC_SHARES] if col == 0 else ["WeightedAverageShares"], "shares")
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
            "shares": b.get("shares") if b.get("shares") is not None else get("avg_shares")}
        if row["gp"] is None and None not in (row["revenue"], row["cogs"]):
            row["gp"] = row["revenue"] - row["cogs"]
        if row["cash"] is not None and row["st_invest"] is not None:
            row["cash"] += row["st_invest"]
        row["securities"] = row["st_invest"]
        parts = ("debt_total", "st_borrow") if row["debt_total"] is not None else ("lt_debt", "st_debt", "st_borrow")
        debts = [row[k] for k in parts if row[k] is not None]
        row["debt"] = sum(debts) if debts else None
        parts = [row[k] for k in INVEST_PARTS if row[k] is not None]
        row["nonop"] = row["lt_invest"] if row["lt_invest"] is not None else sum(parts) if parts else None
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=STATEMENT).sort_values("period").reset_index(drop=True)


def with_securities(st: pd.DataFrame, second: pd.DataFrame | None, large: float) -> tuple[pd.DataFrame, list[str]]:
    """Cash with the short-term investments a filer tags with its own extension, which SEC's companyfacts (the standard
    taxonomies only) leaves out: NVIDIA's FY2026 10-K puts 52bn of securities under nvda:MarketableSecuritiesAndEquity-
    SecuritiesFVNI, so its cash read 10.6bn. A year with no short-term investments in the standard tags whose second
    source's (Yahoo's) cash and short-term investments for the same year end is more than `large` above it (the
    cross-check's large gap: a line missing, not a difference of definition) takes the second source's, said."""
    if second is None or not len(second) or "cash" not in second or "securities" not in st:
        return st, []
    st, years = st.copy(), []
    ends = pd.to_datetime(second["period"])
    for i, row in st[(st["months"] == 12) & st["securities"].isna() & st["cash"].notna()].iterrows():
        near = second[((ends - pd.Timestamp(row["period"])).abs() <= pd.Timedelta(days=10)) & second["cash"].notna()]
        if len(near) and near["cash"].iloc[-1] > row["cash"] * (1 + large):
            st.loc[i, "cash"] = float(near["cash"].iloc[-1])
            years.append(row["period"])
    return st, years


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


CLASS_AXIS, EPS = "StatementClassOfStockAxis", ("EarningsPerShareBasic", "EarningsPerShareBasicAndDiluted")
NI_COMMON = ["NetIncomeLossAvailableToCommonStockholdersBasic", "NetIncomeLoss"]


def denominators(root: ET.Element) -> dict[tuple, dict[str, float]]:
    """(start, end) -> {share class: net income to common / the class's basic EPS}: each class's EPS denominator in
    its own units, from a filing's XBRL instance. Under the two-class method every class's EPS is its conversion rate
    times the one income per as-converted share (Visa's B-1 earns 1.55 times its class A, its C 4.0 times; Berkshire's
    A 1,500 times its B), so each figure is the whole company counted in that class's units."""
    local = lambda tag: tag.rsplit("}", 1)[-1]
    ctx = {}
    for c in root.iter():
        if local(c.tag) == "context":
            dims = {m.get("dimension", "").rsplit(":", 1)[-1]: m.text for m in c.iter() if local(m.tag) == "explicitMember"}
            per = {local(p.tag): p.text for p in c.iter() if local(p.tag) in ("startDate", "endDate")}
            if "startDate" in per:
                ctx[c.get("id")] = ((per["startDate"], per["endDate"]), dims)
    ni, eps = {}, {}
    for e in root:
        name, (period, dims) = local(e.tag), ctx.get(e.get("contextRef"), (None, None))
        if period is None or not (e.text or "").strip():
            continue
        if name in NI_COMMON and not dims:
            ni.setdefault(period, {})[name] = float(e.text)
        elif name in EPS and set(dims) == {CLASS_AXIS} and float(e.text):
            eps.setdefault(period, {}).setdefault(dims[CLASS_AXIS], float(e.text))
    out = {}
    for period, by in eps.items():
        n = next((ni[period][k] for k in NI_COMMON if k in ni.get(period, {})), None)
        counts = {m: n / v for m, v in by.items() if n is not None and n / v > 0}
        if counts:
            out[period] = counts
    return out


def instance(http, cik: int, accn: str) -> ET.Element:
    """A filing's XBRL instance, parsed in memory and not kept: the inline filing's extracted _htm.xml, else the
    filing's own instance (before 2019)."""
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/"
    names = [i["name"] for i in http.get(base + "index.json").json()["directory"]["item"]]
    xml = [n for n in names if n.endswith("_htm.xml")] or [
        n for n in names if n.endswith(".xml") and not re.search(r"(_cal|_def|_lab|_pre|FilingSummary)\.xml$", n)]
    if not xml:
        raise RuntimeError(f"no XBRL instance in {base}")
    return ET.fromstring(http.get(base + xml[0]).content)


def member(counts: dict[str, dict[str, float]], ref: float) -> str:
    """The class whose count is closest to `ref`, judged on the newest period that has one."""
    c = counts[max(counts)]
    return min(c, key=lambda m: abs(math.log(c[m] / ref)))


def with_classes(st: pd.DataFrame, last: dict, payload: dict, line: float | None, fetch=instance):
    """A filer with several share classes tags its counts per class (Visa's A, B-1, B-2, B-3 and C; Berkshire's A and B),
    which SEC's companyfacts leaves out: the latest filing and the 10-Ks give each class's EPS denominator
    (denominators()), and the class in the listed line's units is the one whose count is closest to the line's market
    value over its price (`line`: facts.units' test). An older 10-K takes the class closest to the count of the year it
    shares with the newer one (each 10-K reports three years), so a conversion rate changing over a decade can't
    switch the class. The latest count is the latest quarter's (else the latest period's), as latest() takes the
    quarter's weighted average. Only when the latest year or the latest filing has no count, for the years without one."""
    a = st["months"] == 12
    if not line or not a.any() or (pd.notna(st.loc[a, "shares"].iloc[-1]) and last.get("shares")):
        return st, last
    gaap, cik, http = payload.get("facts", {}).get("us-gaap", {}), int(payload["cik"]), sec.make_http()
    filings = {}  # accession -> (the latest period end it reports, form)
    for n in NI_COMMON:
        for f in gaap.get(n, {}).get("units", {}).get("USD", []):
            if f.get("form") in ("10-K", "10-Q"):
                filings[f["accn"]] = max(filings.get(f["accn"], ("", "")), (f["end"], f["form"]))
    if not filings:
        return st, last
    newest = max(filings, key=lambda k: filings[k])
    got = {newest: denominators(fetch(http, cik, newest))}
    end, last = filings[newest][0], dict(last)
    ending = sorted((sec.days(s, e), (s, e)) for s, e in got[newest] if e == end)
    if ending and not last.get("shares"):
        c = got[newest][ending[0][1]]
        last["shares"] = c[member({end: c}, line)]
    on = lambda day, table: next((v for y, v in table.items() if abs(sec.days(day, y)) <= 7), None)
    years, want = {}, set(st.loc[a & st["shares"].isna(), "period"])
    tenk = sorted(((e, k) for k, (e, form) in filings.items() if form == "10-K"), reverse=True)
    while want and tenk:
        oldest = min(years) if years else None
        pick = next((k for e, k in tenk if oldest is None or abs(sec.days(e, oldest)) <= 7), None)
        if pick is None:
            break
        tenk = [x for x in tenk if x[0] < filings[pick][0]]
        d = got.get(pick) or denominators(fetch(http, cik, pick))
        annual = {e: c for (s, e), c in d.items() if 350 <= sec.days(s, e) <= 380}
        if not annual:
            break
        shared = {e: c for e, c in annual.items() if on(e, years)}
        cls = member(shared, on(max(shared), years)) if shared else member(annual, line)
        for e, c in annual.items():
            if cls in c and on(e, years) is None:
                years[e] = c[cls]
        want = {p for p in want if on(p, years) is None}
        if len(annual) < 2:  # nothing to chain the next one on
            break
    st = st.assign(shares=st["shares"].where(st["shares"].notna() | ~a, st["period"].map(lambda p: on(p, years))))
    return st, last


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
    http = sec.make_http()
    resp = http.get(sec.FACTS.format(cik=int(cik)), ok=(200, 404))
    if resp.status_code != 200:
        return {"cik": int(cik)}
    return sec.complete(http, int(cik), resp.json(), date.today())  # the newest annual report companyfacts lacks


def nasdaq() -> Http:
    return Http(min_interval=0.5, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})


def data(http: Http, path: str) -> dict:
    return http.get("https://api.nasdaq.com/api/" + path, params={"assetclass": "stocks"}).json().get("data") or {}


def parse_consensus(forecast: dict, target: dict, ratings: dict, surprise: dict | None = None) -> dict:
    """Nasdaq: EPS by fiscal year (the year it ends in) with the estimate count, the consensus target and range, the
    buy / hold / sell counts behind it, and the last four quarters' reported EPS on the consensus's own basis (Zacks's:
    before items it deems non-recurring, mostly the companies' adjusted figures; Snowflake's are GAAP), which
    value.consensus_years measures the consensus's growth from."""
    actual = [{"quarter": datetime.strptime(r["fiscalQtrEnd"], "%b %Y").strftime("%Y-%m"), "eps": num(r.get("eps"))}
              for r in ((surprise or {}).get("earningsSurpriseTable") or {}).get("rows") or []]
    rows = (forecast.get("yearlyForecast") or {}).get("rows") or []
    eps = {str(datetime.strptime(r["fiscalEnd"], "%b %Y").year): num(r.get("consensusEPSForecast")) for r in rows}
    count = {str(datetime.strptime(r["fiscalEnd"], "%b %Y").year): num(r.get("noOfEstimates")) for r in rows}
    ov = target.get("consensusOverview") or {}
    return {"source": "Nasdaq", "eps": eps, "estimates": count, "analysts": max(count.values(), default=None),
            "target_mean": num(ov.get("priceTarget")), "target_low": num(ov.get("lowPriceTarget")),
            "target_high": num(ov.get("highPriceTarget")),
            "ratings": {k: num(ov.get(k)) for k in ("buy", "hold", "sell")}, "rating": ratings.get("meanRatingType"),
            "actuals": actual}


def consensus(code: str) -> dict:
    http, sym = nasdaq(), code.replace(".", "-")
    try:
        surprise = data(http, f"company/{sym}/earnings-surprise")
    except RuntimeError:  # without it the consensus stands, its basis unmeasured (value.consensus_years says so)
        surprise = {}
    return parse_consensus(data(http, f"analyst/{sym}/earnings-forecast"), data(http, f"analyst/{sym}/targetprice"),
                           data(http, f"analyst/{sym}/ratings"), surprise)


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
