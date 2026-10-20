"""SEC EDGAR (data.sec.gov): trailing-12-month US fundamentals from companyfacts (XBRL, us-gaap, USD),
annual history from the same files (10-K, 20-F and 40-F, us-gaap or ifrs-full, in the reporting
currency), and recent filing titles from the submissions list for the AI notes. At most 10 requests/s,
with the User-Agent SEC_USER_AGENT from .env. companyfacts files are several MB each: they are parsed
in memory and never written to disk; only the extracted rows per company are kept (refreshed weekly)."""

from datetime import date, timedelta

import pandas as pd
from dotenv import dotenv_values

from stockreport.config import DATA, ROOT
from stockreport.fetch import HISTORY, Http, stale, upsert_each, write

TICKERS = "https://www.sec.gov/files/company_tickers_exchange.json"
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
CIKS, TABLE = DATA / "fundamentals" / "us_cik.csv.gz", DATA / "fundamentals" / "us_facts.csv.gz"
ANNUAL = HISTORY / "us_annual.csv.gz"  # one row per company and fiscal year (SEC, else Yahoo)
# Concepts in order of preference. Companies switch concepts between filings, so the values of all
# of them are merged per period, the first concept winning; a (total, part) pair stands for total - part.
# Revenue is chosen per period instead (revenue()): companies also tag parts of it with its concepts (fee revenue
# in ASC 606 scope at banks and card issuers, a non-interest revenue subtotal, a REIT's non-rent income) and
# totals before intersegment eliminations (Williams' ASC 606 total, Hasbro's "Revenues").
PARENT_NI = ("ProfitLoss", "NetIncomeLossAttributableToNoncontrollingInterest")  # no NetIncomeLoss tag (IVZ)
DURATION = {
    "np": ["NetIncomeLoss", PARENT_NI, "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"],
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                "RevenuesNetOfInterestExpense", "RegulatedAndUnregulatedOperatingRevenue", "OperatingLeaseLeaseIncome"],
    "nii": ["InterestIncomeExpenseNet"],  # banks: net interest + noninterest income when larger than revenue
    "nonint": ["NoninterestIncome"],
    "gp": ["GrossProfit"],
    "cost": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
}
# Equity is the parent's: the total including minorities less the minorities' share when only the total is tagged.
WITH_NCI = "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
INSTANT = {
    "equity": ["StockholdersEquity", (WITH_NCI, "MinorityInterest"), WITH_NCI],
    "liabilities": ["Liabilities"],
    "assets": ["Assets"],
}
MAX_AGE_DAYS = 200  # no 10-Q/10-K period this recent (e.g. 20-F/40-F filers): a gap, filled from Yahoo
# Annual history: fiscal-year concepts per taxonomy (durations, instants), merged per year like DURATION.
# 20-F filers report in us-gaap (ASML, BABA) or ifrs-full (TSM, NVO), often in their own currency.
ANNUAL_FORMS, HISTORY_FROM = ("10-K", "20-F", "40-F"), "2015-01-01"
TAXONOMIES = {
    "us-gaap": ({"revenue": DURATION["revenue"], "nii": DURATION["nii"], "nonint": DURATION["nonint"],
                 "gp": DURATION["gp"], "cost": DURATION["cost"], "op_income": ["OperatingIncomeLoss"],
                 "ni": DURATION["np"], "ni_common": ["NetIncomeLossAvailableToCommonStockholdersBasic"],
                 "ni_cont": ["IncomeLossFromContinuingOperations",
                             "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest"],
                 "ocf": DURATION["ocf"], "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
                 "div": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
                 "dil_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"]},
                {"equity": INSTANT["equity"] + ["PartnersCapital", ("PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest",
                                                  "MinorityInterest"), "PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest"],
                 "pref": ["PreferredStockValue"], "assets": ["Assets"],  # partners' capital: MLPs (EPD, MPLX)
                 "liabilities": ["Liabilities"], "shares": ["CommonStockSharesOutstanding"]}),
    "ifrs-full": ({"revenue": ["Revenue", "RevenueFromContractsWithCustomers"], "gp": ["GrossProfit"], "cost": ["CostOfSales"],
                   "op_income": ["ProfitLossFromOperatingActivities"],
                   "ni": ["ProfitLossAttributableToOwnersOfParent", ("ProfitLoss", "ProfitLossAttributableToNoncontrollingInterests"),
                          "ProfitLoss"],
                   "ni_cont": ["ProfitLossFromContinuingOperationsAttributableToOwnersOfParent",
                               "ProfitLossFromContinuingOperations"],
                   "ocf": ["CashFlowsFromUsedInOperatingActivities"],
                   "capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                             "PurchaseOfPropertyPlantAndEquipment"],
                   "div": ["DividendsPaidClassifiedAsFinancingActivities", "DividendsPaid"],
                   "dil_shares": ["AdjustedWeightedAverageShares"]},
                  {"equity": ["EquityAttributableToOwnersOfParent", ("Equity", "NoncontrollingInterests"), "Equity"], "assets": ["Assets"],
                   "liabilities": ["Liabilities"], "shares": ["NumberOfSharesOutstanding"]}),
}
CHECKS = {"us-gaap": [(["GrossProfit"], DURATION["cost"]), (["OperatingIncomeLoss"], ["CostsAndExpenses"])],
          "ifrs-full": [(["GrossProfit"], ["CostOfSales"])]}  # revenue = the sum of each pair (revenue())
SHARE_UNITS = ("dil_shares", "shares")
# Filing titles for the AI notes: the forms that say something about the business, and 8-K items
# (the filing list only has item numbers, not headlines).
FORMS = {"10-Q": "Quarterly report", "10-K": "Annual report", "20-F": "Annual report", "40-F": "Annual report",
         "6-K": "Report of foreign issuer", "SC 13D": "5%+ stake with intent to influence (13D)",
         "SC 13D/A": "13D stake amended", "SCHEDULE 13D": "5%+ stake with intent to influence (13D)",
         "SCHEDULE 13D/A": "13D stake amended", "SC TO-T": "Tender offer by a third party", "SC TO-I": "Issuer tender offer",
         "SC 14D9": "Board response to a tender offer", "PREM14A": "Merger proxy (preliminary)",
         "DEFM14A": "Merger proxy (definitive)", "S-4": "Registration for a merger or exchange offer",
         "425": "Merger communication", "NT 10-Q": "Late quarterly report notice", "NT 10-K": "Late annual report notice",
         "15-12B": "Deregistration", "25-NSE": "Delisting notice"}
ITEMS = {"1.01": "Material definitive agreement", "1.02": "Termination of a material agreement",
         "1.03": "Bankruptcy or receivership", "1.05": "Material cybersecurity incident",
         "2.01": "Completed acquisition or disposition of assets", "2.02": "Results of operations",
         "2.03": "New direct financial obligation", "2.04": "Event accelerating an obligation",
         "2.05": "Exit or disposal costs", "2.06": "Material impairment",
         "3.01": "Delisting or listing-rule failure notice", "3.02": "Unregistered sale of equity",
         "3.03": "Change to shareholder rights", "4.01": "Auditor change",
         "4.02": "Non-reliance on previous financial statements", "5.01": "Change in control",
         "5.02": "Director or officer change", "5.03": "Charter or bylaw amendment",
         "5.07": "Shareholder vote results"}  # 7.01 Reg FD and 8.01 "Other events" are bare labels: left out


def make_http() -> Http:
    agent = dotenv_values(ROOT / ".env").get("SEC_USER_AGENT")
    if not agent:
        raise RuntimeError("SEC_USER_AGENT is missing from .env (SEC needs a name and contact email)")
    return Http(min_interval=0.5, timeout=60, headers={"User-Agent": agent})


def days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def shift(day: str, n: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=n)).isoformat()


def latest(tax: dict, name: str | tuple, unit: str, keep) -> dict:
    """(start, end) -> one concept's most recently filed value (restatements win) among the facts that pass
    `keep`; a (total, part) pair gives total - part for the periods that have both. Instants have start None."""
    if isinstance(name, tuple):
        total, part = (latest(tax, n, unit, keep) for n in name)
        return {k: v - part[k] for k, v in total.items() if k in part}
    best = {}
    for f in tax.get(name, {}).get("units", {}).get(unit, []):
        key = (f.get("start"), f["end"])
        if keep(f) and (key not in best or f["filed"] > best[key][0]):
            best[key] = (f["filed"], f["val"])
    return {k: v for k, (_, v) in best.items()}


larger = lambda a, b: b if a is None else max(a, b)


def merge(per_concept) -> dict:
    """Per period, the value of the first concept that has it."""
    out = {}
    for vals in per_concept:
        for k, v in vals.items():
            out.setdefault(k, v)
    return out


def revenue(get, names: list, checks: list) -> dict:
    """Per period, the revenue concept within 5% of the revenue the income statement implies (the first of
    `checks` with both parts tagged and a concept that close: gross profit + cost of revenue, operating income +
    total costs and expenses; Centene's gross profit is its services' only), else the largest concept."""
    per, implied = [get([n]) for n in names], [(get(a), get(b)) for a, b in checks]
    out = {}
    for k in set().union(*per):
        vals, sums = [v[k] for v in per if k in v], [a[k] + b[k] for a, b in implied if k in a and k in b]
        pick = lambda x: min(vals, key=lambda v: abs(v - x))
        out[k] = next((pick(x) for x in sums if abs(pick(x) - x) <= 0.05 * abs(x)), max(vals))
    return out


def quarterly(f: dict) -> bool:
    """10-Q and 10-K figures; a 12-month figure only from the 10-K (a 10-Q once tagged Q1 as the fiscal year)."""
    form = f.get("form", "")
    return form.startswith("10-K") or form.startswith("10-Q") and not ("start" in f and days(f["start"], f["end"]) >= 340)


def values(gaap: dict, names: list) -> dict:
    """(start, end) -> value from 10-Q/10-K filings in USD, merged over the concepts in `names`."""
    return merge(latest(gaap, n, "USD", quarterly) for n in names)


def near(vals: dict, end: str, length: int | None, tol: int):
    """The value whose period ends within `tol` days of `end` and lasts ~`length` days (any if None)."""
    for (s, e), v in vals.items():
        if abs(days(e, end)) <= tol and (length is None or (s and abs(days(s, e) - length) <= tol)):
            return v
    return None


def ttm(vals: dict, end: str, short_year: bool = False) -> float | None:
    """Trailing 12 months to the period ending near `end` (52/53-week years move period ends): the
    fiscal year itself, or year-to-date + the last fiscal year - the same year-to-date a year earlier;
    after an annual report for less than a year (short_year), chained periods (chain())."""
    fy = near(vals, end, 365, tol=15)
    if fy is not None:
        return fy
    ytd = [(days(s, e), s, e) for s, e in vals if s and abs(days(e, end)) <= 12 and 80 <= days(s, e) < 340]
    if not ytd:
        return None
    length, s, e = max(ytd)
    last_fy, prior = near(vals, shift(s, -1), 365, tol=15), near(vals, shift(e, -364), length, tol=12)
    if last_fy is None or prior is None:
        return chain(vals, e) if short_year else None
    return vals[(s, e)] + last_fy - prior


def chain(vals: dict, end: str) -> float | None:
    """The 12 months to `end` from the fewest reported periods added and subtracted end to end, back to a date
    a year earlier (within 15 days): a fiscal-year change's transition period (Ferguson), a merger's predecessor
    and successor periods (Paramount Skydance; boundaries up to 3 days apart join, the closing day is in
    neither). Only after a short annual report: L3Harris tags its fiscal-year revenue with Q4's dates."""
    edges, level, seen, start = [(shift(s, -1), e, v) for (s, e), v in vals.items() if s], {end: 0.0}, {end}, shift(end, -365)
    for _ in range(6):
        step = {}
        for node, total in level.items():
            for a, b, v in edges:
                for here, there, sign in ((b, a, 1), (a, b, -1)):  # back over a period adds it, forward subtracts it
                    if abs(days(here, node)) <= 3 and there not in seen:
                        step.setdefault(there, total + sign * v)
        hit = sorted((abs(days(n, start)), t) for n, t in step.items() if abs(days(n, start)) <= 15)
        if hit:
            return hit[0][1]
        seen, level = seen | set(step), step
    return None


def parse_facts(code: str, payload: dict, today: date) -> dict:
    """One row per company: latest period, TTM revenue / profit / gross profit / operating cash flow,
    growth against the TTM a year earlier (same concept), and the latest equity, liabilities and
    assets. gap = True when there is no recent us-gaap 10-Q/10-K period in USD or no TTM profit/revenue."""
    gaap = payload.get("facts", {}).get("us-gaap", {})
    filed, year = {}, {}  # period end -> first filing date; 10-K period end -> its longest period
    for n in DURATION["np"]:
        for f in gaap.get(n, {}).get("units", {}).get("USD", []):
            if f.get("form", "").startswith(("10-Q", "10-K")) and "start" in f:
                filed[f["end"]] = min(filed.get(f["end"], f["filed"]), f["filed"])
                if f["form"].startswith("10-K"):
                    year[f["end"]] = max(year.get(f["end"], 0), days(f["start"], f["end"]))
    row = {"code": code, "cik": payload.get("cik")}
    if not filed or days(max(filed), today.isoformat()) > MAX_AGE_DAYS:
        return row | {"gap": True}
    end = max(filed)
    get, short = lambda names: values(gaap, names), bool(year) and year[max(year)] < 340  # last 10-K under a year
    for key, names in DURATION.items():
        vals = revenue(get, names, CHECKS["us-gaap"]) if key == "revenue" else get(names)
        row[f"{key}_ttm"], row[f"{key}_prior"] = ttm(vals, end, short), ttm(vals, shift(end, -364), short)
    instant = lambda names: near(values(gaap, names), end, None, 5)
    for key, names in INSTANT.items():
        row[key] = instant(names)
    for when in ("ttm", "prior"):
        if None not in (row[f"nii_{when}"], row[f"nonint_{when}"]):
            row[f"revenue_{when}"] = larger(row[f"revenue_{when}"], row[f"nii_{when}"] + row[f"nonint_{when}"])
    if row["gp_ttm"] is None and None not in (row["cost_ttm"], row["revenue_ttm"]):
        row["gp_ttm"] = row["revenue_ttm"] - row["cost_ttm"]
    if row["liabilities"] is None:  # total liabilities and equity - equity including minorities
        total, equity = instant(["LiabilitiesAndStockholdersEquity"]), instant([WITH_NCI, "StockholdersEquity"])
        row["liabilities"] = None if None in (total, equity) else total - equity
    growth = lambda now, before: None if now is None or not before else (now - before) / abs(before)
    # no TTM profit or revenue (e.g. a new holding-company CIK without a year of history) is a gap too
    return row | {"gap": row["np_ttm"] is None or row["revenue_ttm"] is None, "period": end, "notice_date": filed[end],
                  "rev_yoy": growth(row["revenue_ttm"], row["revenue_prior"]),
                  "np_yoy": growth(row["np_ttm"], row["np_prior"])}


def annual(tax: dict, names: list, unit: str, instant: bool = False) -> dict[str, float]:
    """Fiscal-year end -> value from annual reports (10-K, 20-F, 40-F): durations of 350-380 days or
    instants, merged over the concepts in `names` like values()."""
    keep = lambda f: (f.get("form", "").startswith(ANNUAL_FORMS) and ("start" not in f) == instant
                      and (instant or 350 <= days(f["start"], f["end"]) <= 380))
    return {e: v for (_, e), v in merge(latest(tax, n, unit, keep) for n in names).items()}


def parse_annual(code: str, payload: dict) -> list[dict]:
    """One row per fiscal year since 2015, in the taxonomy and currency with the most annual profit
    years, then facts (TSM: ifrs-full in TWD, which every 20-F repeats as comparatives, not its USD
    convenience figures); filed = when the year was first reported. Capex and dividends paid are
    positive, as SEC reports them."""
    facts, best = payload.get("facts", {}), (0, 0, "", "")
    for name, (dur, _) in TAXONOMIES.items():
        tax = facts.get(name, {})
        for unit in sorted({u for c in dur["ni"] for u in tax.get(c, {}).get("units", {})}):
            n = sum(f.get("form", "").startswith(ANNUAL_FORMS) for c in dur["ni"] for f in tax.get(c, {}).get("units", {}).get(unit, []))
            best = max(best, (len(annual(tax, dur["ni"], unit)), n, name, unit))
    if not best[0]:
        return []
    _, _, name, unit = best
    tax, (dur, inst) = facts[name], TAXONOMIES[name]
    get = lambda names, unit=unit: annual(tax, names, unit)
    series = {k: revenue(get, c, CHECKS[name]) if k == "revenue" else get(c, "shares" if k in SHARE_UNITS else unit)
              for k, c in dur.items()}
    series |= {k: annual(tax, c, "shares" if k in SHARE_UNITS else unit, instant=True) for k, c in inst.items()}
    filed = {}
    for c in dur["ni"]:
        for f in tax.get(c, {}).get("units", {}).get(unit, []):
            if f.get("form", "").startswith(ANNUAL_FORMS) and "start" in f:
                filed[f["end"]] = min(filed.get(f["end"], f["filed"]), f["filed"])
    cover = [(f["end"], f["val"]) for f in facts.get("dei", {}).get("EntityCommonStockSharesOutstanding", {})
             .get("units", {}).get("shares", []) if f.get("form", "").startswith(ANNUAL_FORMS)]
    rows = []
    for end in sorted(e for e in series["ni"] if e >= HISTORY_FROM):
        get = lambda k: series[k].get(end, next((v for e, v in series[k].items() if abs(days(e, end)) <= 7), None))
        row = {"code": code, "fy_end": end, "filed": filed.get(end), "source": "SEC", "taxonomy": name,
               "currency": unit} | {k: get(k) for k in series}
        if None not in (row.get("nii"), row.get("nonint")):
            row["revenue"] = larger(row["revenue"], row["nii"] + row["nonint"])
        if row["gp"] is None and None not in (row["revenue"], row["cost"]):
            row["gp"] = row["revenue"] - row["cost"]
        if row["shares"] is None:  # the cover page count, a few weeks after the year end
            row["shares"] = next((v for e, v in cover if 0 <= days(end, e) <= 120), None)
        rows.append({k: v for k, v in row.items() if k not in ("nii", "nonint", "cost")})
    return rows


def update_ciks(today: date) -> pd.DataFrame:
    if not CIKS.exists() or (today - date.fromtimestamp(CIKS.stat().st_mtime)).days >= 7:
        payload = make_http().get(TICKERS).json()
        df = pd.DataFrame(payload["data"], columns=payload["fields"])
        df["code"] = df["ticker"].str.replace("-", ".")
        write(df[["code", "cik", "name", "exchange"]], CIKS)
    return pd.read_csv(CIKS, dtype={"code": str})


def load_ciks() -> pd.Series:
    return pd.read_csv(CIKS, dtype={"code": str}).drop_duplicates("code").set_index("code")["cik"]


def covered(table: pd.DataFrame) -> pd.Series:
    """Rows with everything the valuation needs; the rest (no recent 10-Q/10-K, no CIK, or a missing
    field, e.g. MLPs report partners' capital, not stockholders' equity) are filled from Yahoo."""
    need = ["revenue_ttm", "np_ttm", "equity", "rev_yoy", "np_yoy"]
    return (table["gap"].astype(str) == "False") & table.reindex(columns=need).notna().all(axis=1)


def gaps(codes: list[str]) -> list[str]:
    table = pd.read_csv(TABLE, dtype={"code": str}) if TABLE.exists() else pd.DataFrame(columns=["code", "gap"])
    done = set(table.loc[covered(table), "code"])
    return [c for c in codes if c not in done]


def facts(client: Http, job: tuple[str, int, date]) -> tuple[dict, list[dict]]:
    code, cik, today = job
    resp = client.get(FACTS.format(cik=cik), ok=(200, 404))  # 404: no XBRL facts at all (some foreign filers)
    payload = resp.json() if resp.status_code == 200 else {"cik": cik}
    years = parse_annual(code, payload)
    roe_years = sum(r["ni"] is not None and r["equity"] is not None for r in years)
    return parse_facts(code, payload, today) | {"annual_years": roe_years}, years


def update_facts(today: date, codes: list[str]) -> None:
    """Weekly per company (4 at a time, under SEC's 10 requests/s); the same files give the annual
    history. Companies read before the history existed (no annual_years) are read again once."""
    update_ciks(today)
    cik = load_ciks()
    table = pd.read_csv(TABLE, dtype={"code": str}) if TABLE.exists() else pd.DataFrame(columns=["code"])
    again = set(stale(TABLE, codes, today)) | set(table.loc[table.reindex(columns=["annual_years"])["annual_years"].isna(), "code"])
    todo = [(c, int(cik[c]), today) for c in codes if c in again and c in cik.index]
    upsert_each(TABLE, make_http, facts, todo, today, 4, "sec facts", history=ANNUAL)


def annual_gaps(codes: list[str]) -> list[str]:
    """Codes SEC has no annual history for (no CIK, no XBRL facts or no annual report): Yahoo's turn."""
    table = pd.read_csv(TABLE, dtype={"code": str}) if TABLE.exists() else pd.DataFrame(columns=["code"])
    years = table.set_index("code").reindex(columns=["annual_years"])["annual_years"]
    return [c for c in codes if not years.get(c, 0) > 0]


def history_currencies() -> set[str]:
    """Reporting currencies in the US annual history other than USD (for their monthly FX)."""
    if not ANNUAL.exists():
        return set()
    return set(pd.read_csv(ANNUAL, usecols=["currency"])["currency"].dropna()) - {"USD"}


def org_ids() -> dict[str, int]:
    """Ticker -> CIK, the id the filing list is keyed by (same role as CNINFO's orgId)."""
    return load_ciks().to_dict()


def parse_titles(payload: dict, today: date, days: int, limit: int) -> list[str]:
    """Newest-first 'YYYY-MM-DD form: description' lines from the last `days` days; routine forms
    (insider trades, prospectuses, ...) are skipped and repeats dropped."""
    recent, start = payload["filings"]["recent"], (today - timedelta(days=days)).isoformat()
    out, seen = [], set()
    for form, day, items in zip(recent["form"], recent["filingDate"], recent["items"]):
        if day < start:
            break
        if form in ("8-K", "8-K/A"):
            text = "; ".join(ITEMS[i] for i in items.split(",") if i in ITEMS)
        else:
            text = FORMS.get(form, "")
        if not text or f"{form} {text}" in seen:
            continue
        seen.add(f"{form} {text}")
        out.append(f"{day} {form}: {text}")
        if len(out) >= limit:
            break
    return out


_titles_http = None


def titles(code: str, cik: int, today: date, days: int = 60, limit: int = 10) -> list[str]:
    global _titles_http
    _titles_http = _titles_http or make_http()
    return parse_titles(_titles_http.get(SUBMISSIONS.format(cik=int(cik))).json(), today, days, limit)
