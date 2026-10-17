"""SEC EDGAR (data.sec.gov): trailing-12-month US fundamentals from companyfacts (XBRL, us-gaap, USD),
and recent filing titles from the submissions list for the AI notes. At most 10 requests/s, with the
User-Agent SEC_USER_AGENT from .env. companyfacts files are several MB each: they are parsed in memory
and never written to disk; only the extracted row per company is kept (refreshed weekly)."""

import logging
from datetime import date, timedelta

import pandas as pd
from dotenv import dotenv_values

from stockreport.config import DATA, ROOT
from stockreport.fetch import Http, each, merge, stale, write

log = logging.getLogger(__name__)
TICKERS = "https://www.sec.gov/files/company_tickers_exchange.json"
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
CIKS, TABLE = DATA / "fundamentals" / "us_cik.csv.gz", DATA / "fundamentals" / "us_facts.csv.gz"
# Concepts in order of preference. Companies switch concepts between filings, so the values of all
# of them are merged per period, the first concept winning.
DURATION = {
    "np": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"],
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                "RevenuesNetOfInterestExpense", "RegulatedAndUnregulatedOperatingRevenue"],
    "nii": ["InterestIncomeExpenseNet"],  # banks without a revenue total: net interest + noninterest income
    "nonint": ["NoninterestIncome"],
    "gp": ["GrossProfit"],
    "cost": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
}
INSTANT = {
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "liabilities": ["Liabilities"],
    "assets": ["Assets"],
}
MAX_AGE_DAYS = 200  # no 10-Q/10-K period this recent (e.g. 20-F/40-F filers): a gap, filled from FMP
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


def values(gaap: dict, names: list[str]) -> dict:
    """(start, end) -> value from 10-Q/10-K filings in USD, keeping the most recently filed figure
    (restatements win) and the first concept in `names` that has the period. Instants have start None."""
    out = {}
    for name in names:
        best = {}
        for f in gaap.get(name, {}).get("units", {}).get("USD", []):
            if f.get("form", "").startswith(("10-Q", "10-K")):
                key = (f.get("start"), f["end"])
                if key not in best or f["filed"] > best[key][0]:
                    best[key] = (f["filed"], f["val"])
        for key, (_, val) in best.items():
            out.setdefault(key, val)
    return out


def near(vals: dict, end: str, length: int | None, tol: int):
    """The value whose period ends within `tol` days of `end` and lasts ~`length` days (any if None)."""
    for (s, e), v in vals.items():
        if abs(days(e, end)) <= tol and (length is None or (s and abs(days(s, e) - length) <= tol)):
            return v
    return None


def ttm(vals: dict, end: str) -> float | None:
    """Trailing 12 months to the period ending near `end` (52/53-week years move period ends): the
    fiscal year itself, or year-to-date + the last fiscal year - the same year-to-date a year earlier."""
    fy = near(vals, end, 365, tol=15)
    if fy is not None:
        return fy
    ytd = [(days(s, e), s, e) for s, e in vals if s and abs(days(e, end)) <= 12 and 80 <= days(s, e) < 340]
    if not ytd:
        return None
    length, s, e = max(ytd)
    last_fy, prior = near(vals, shift(s, -1), 365, tol=15), near(vals, shift(e, -364), length, tol=12)
    return None if last_fy is None or prior is None else vals[(s, e)] + last_fy - prior


def parse_facts(code: str, payload: dict, today: date) -> dict:
    """One row per company: latest period, TTM revenue / profit / gross profit / operating cash flow,
    growth against the TTM a year earlier (same concept), and the latest equity, liabilities and
    assets. gap = True when there is no recent us-gaap 10-Q/10-K period in USD or no TTM profit/revenue."""
    gaap = payload.get("facts", {}).get("us-gaap", {})
    filed = {}  # period end -> first filing date (when the company reported it)
    for n in DURATION["np"]:
        for f in gaap.get(n, {}).get("units", {}).get("USD", []):
            if f.get("form", "").startswith(("10-Q", "10-K")) and "start" in f:
                filed[f["end"]] = min(filed.get(f["end"], f["filed"]), f["filed"])
    row = {"code": code, "cik": payload.get("cik")}
    if not filed or days(max(filed), today.isoformat()) > MAX_AGE_DAYS:
        return row | {"gap": True}
    end = max(filed)
    for key, names in DURATION.items():
        vals = values(gaap, names)
        row[f"{key}_ttm"], row[f"{key}_prior"] = ttm(vals, end), ttm(vals, shift(end, -364))
    instant = lambda names: near(values(gaap, names), end, None, 5)
    for key, names in INSTANT.items():
        row[key] = instant(names)
    for when in ("ttm", "prior"):
        if row[f"revenue_{when}"] is None and None not in (row[f"nii_{when}"], row[f"nonint_{when}"]):
            row[f"revenue_{when}"] = row[f"nii_{when}"] + row[f"nonint_{when}"]
    if row["gp_ttm"] is None and None not in (row["cost_ttm"], row["revenue_ttm"]):
        row["gp_ttm"] = row["revenue_ttm"] - row["cost_ttm"]
    if row["liabilities"] is None:  # total liabilities and equity - equity including minorities
        total, equity = instant(["LiabilitiesAndStockholdersEquity"]), instant(INSTANT["equity"][::-1])
        row["liabilities"] = None if None in (total, equity) else total - equity
    growth = lambda now, before: None if now is None or not before else (now - before) / abs(before)
    # no TTM profit or revenue (e.g. a new holding-company CIK without a year of history) is a gap too
    return row | {"gap": row["np_ttm"] is None or row["revenue_ttm"] is None, "period": end, "notice_date": filed[end],
                  "rev_yoy": growth(row["revenue_ttm"], row["revenue_prior"]),
                  "np_yoy": growth(row["np_ttm"], row["np_prior"])}


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


def facts(client: Http, job: tuple[str, int, date]) -> dict:
    code, cik, today = job
    resp = client.get(FACTS.format(cik=cik), ok=(200, 404))  # 404: no XBRL facts at all (some foreign filers)
    return parse_facts(code, resp.json() if resp.status_code == 200 else {"cik": cik}, today)


def update_facts(today: date, codes: list[str]) -> None:
    """Weekly per company (4 at a time, under SEC's 10 requests/s)."""
    update_ciks(today)
    cik = load_ciks()
    todo = [(c, int(cik[c]), today) for c in stale(TABLE, codes, today) if c in cik.index]
    rows = []
    for i, row in enumerate(each(make_http, facts, todo, workers=4), 1):
        if row:
            rows.append(row | {"fetched": today.isoformat()})
        if i % 100 == 0 or i == len(todo):
            merge(TABLE, pd.DataFrame(rows), ["code"])
            rows = []
            log.info("sec facts: %d of %d companies", i, len(todo))


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
