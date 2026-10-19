"""US base-rate panel (Phase 13, PLAN.md Method 16): SEC's yearly XBRL frames, each one concept's figure for
one calendar year from every filer, dead companies included (data.sec.gov/api/xbrl/frames), and each filer's
SIC code from its submissions file. Kept: one row per company and year (revenue, net income, equity) and
cik -> SIC; the frame files (~1 MB each) are read in memory and never stored."""

import logging
from datetime import date

import pandas as pd

from stockreport.fetch import HISTORY, merge, upsert_each, write
from stockreport.fetch.sec import SUBMISSIONS, WITH_NCI, make_http

log = logging.getLogger(__name__)
FRAME = "https://data.sec.gov/api/xbrl/frames/us-gaap/{concept}/USD/CY{year}{instant}.json"
# revenue: the largest of these concepts a company tagged that year (sec.revenue's fallback); net income and
# equity: the first concept tagged. Equity is the instant at the calendar year end (10-Q balance sheets count).
CONCEPTS = {"revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                        "RevenuesNetOfInterestExpense", "RegulatedAndUnregulatedOperatingRevenue"],
            "ni": ["NetIncomeLoss", "ProfitLoss"], "equity": ["StockholdersEquity", WITH_NCI]}
PANEL, SIC = HISTORY / "us_frames.csv.gz", HISTORY / "us_sic.csv.gz"
FIRST_YEAR = 2009
REFETCH_DAYS = 30  # the last two calendar years still fill in as late filers report
MIN_REVENUE = 1e8  # SIC codes only for filers with $100m+ revenue in some year (the base rates' size floor)


def frame_year(http, year: int) -> pd.DataFrame:
    """One calendar year: revenue, net income and equity per filer (cik), with the filer's name."""
    out = {}
    for field, names in CONCEPTS.items():
        for name in names:
            instant = "Q4I" if field == "equity" else ""
            resp = http.get(FRAME.format(concept=name, year=year, instant=instant), ok=(200, 404))
            for d in resp.json().get("data", []) if resp.status_code == 200 else []:
                row = out.setdefault(d["cik"], {"cik": d["cik"], "name": d["entityName"], "year": year})
                if field == "revenue":
                    row[field] = max(row.get(field, d["val"]), d["val"])
                else:
                    row.setdefault(field, d["val"])
    log.info("sec frames CY%d: %d filers", year, len(out))
    return pd.DataFrame(list(out.values()), columns=["cik", "name", "year", "revenue", "ni", "equity"])


def sic(http, cik: int) -> dict:
    payload = http.get(SUBMISSIONS.format(cik=cik)).json()
    return {"code": str(cik), "sic": payload.get("sic") or "", "sic_name": payload.get("sicDescription") or ""}


def update(today: date, ciks: list[int] = ()) -> None:
    """New calendar years once; the last two again every 30 days. Then SIC codes for new filers with $100m+
    revenue and for `ciks` (the candidates: foreign filers report in IFRS and aren't in the us-gaap frames)."""
    have = pd.read_csv(PANEL) if PANEL.exists() else pd.DataFrame(columns=["year"])
    age = (today - date.fromtimestamp(PANEL.stat().st_mtime)).days if PANEL.exists() else 999
    todo = [y for y in range(FIRST_YEAR, today.year)
            if y not in set(have["year"]) or (y >= today.year - 2 and age >= REFETCH_DAYS)]
    if todo:
        http = make_http()
        new = pd.concat([frame_year(http, y) for y in todo])
        write(pd.concat([have[~have["year"].isin(todo)], new]).sort_values(["cik", "year"]), PANEL)
    panel = pd.read_csv(PANEL)
    big = panel.groupby("cik")["revenue"].max()
    known = set(pd.read_csv(SIC, dtype=str)["code"]) if SIC.exists() else set()
    want = set(big.index[big >= MIN_REVENUE]) | {int(c) for c in ciks}
    missing = sorted(int(c) for c in want if str(int(c)) not in known)
    upsert_each(SIC, make_http, sic, missing, today, 4, "sec sic")


def load() -> pd.DataFrame:
    """The panel: one row per filer (cik) and calendar year."""
    panel = pd.read_csv(PANEL)
    return panel.assign(cik=panel["cik"].astype(int))
