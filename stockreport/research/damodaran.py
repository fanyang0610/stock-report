"""Damodaran's datasets (pages.stern.nyu.edu/~adamodar/pc/datasets, .xls read with xlrd, parsed in memory), refreshed
after each January and July update: country equity risk premiums; per region (US, China, Global) each industry's beta,
unlevered beta, debt to equity, tax rate, margins, sales to invested capital, cost of equity and of capital; the
interest-cover -> rating -> default-spread tables; and his own classification of every listed company into those
industries (indname.xls, 22 MB, kept only for CN, HK and US listings), so no industry map is typed by hand."""

import logging
from datetime import date

import pandas as pd
import xlrd

from stockreport.fetch import Http, write
from stockreport.research import ROOT

log = logging.getLogger(__name__)
URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/{}"
FOLDER = ROOT / "damodaran"
REGIONS = {"US": "", "China": "China", "Global": "Global"}  # region -> file suffix (US: betas.xls, margin.xls, ...)
MIN_FIRMS = 10  # a regional industry average over fewer firms is too thin to use: the global one replaces it
COLUMNS = {  # file stem -> (column name, header prefix), matched case-insensitively on the 'Industry Name' row
    "beta": [("firms", "number of firms"), ("beta", "beta"), ("de", "d/e ratio"), ("tax", "effective tax"),
             ("unlevered_beta", "unlevered beta"), ("cash_firm", "cash/firm value"),
             ("unlevered_beta_cash", "unlevered beta corrected")],
    "margin": [("gross_margin", "gross margin"), ("net_margin", "net margin"), ("op_margin", "pre-tax unadjusted"),
               ("ebitda_margin", "ebitda/sales")],
    "capex": [("capex_sales", "net cap ex/sales"), ("sales_to_capital", "sales/ invested capital")],
    "wacc": [("cost_of_equity", "cost of equity"), ("cost_of_debt", "cost of debt"), ("debt_weight", "d/(d+e)"),
             ("cost_of_capital", "cost of capital")]}
EXCHANGES = {"SHSE": "cn", "SZSE": "cn", "BJSE": "cn", "SEHK": "hk", "NasdaqGS": "us", "NasdaqGM": "us", "NasdaqCM": "us",
             "NYSE": "us", "NYSEAM": "us", "NYSEArca": "us"}


def due(today: date) -> date:
    """The latest refresh point: Damodaran updates his datasets in early January and the risk premiums again in July."""
    points = [date(today.year, 1, 15), date(today.year, 7, 15)]
    past = [p for p in points if p <= today]
    return past[-1] if past else date(today.year - 1, 7, 15)


def book(content: bytes) -> xlrd.book.Book:
    return xlrd.open_workbook(file_contents=content, on_demand=True)


def industry_sheet(content: bytes, spec: list[tuple[str, str]]) -> pd.DataFrame:
    """The 'Industry Averages' sheet: the header row starts with 'Industry Name'; data rows until a blank name."""
    s = book(content).sheet_by_name("Industry Averages")
    top = next(r for r in range(s.nrows) if str(s.cell_value(r, 0)).strip() == "Industry Name")
    heads = [str(h).strip().lower() for h in s.row_values(top)]
    cols = {name: next(i for i, h in enumerate(heads) if h.startswith(prefix)) for name, prefix in spec}
    rows = []
    for r in range(top + 1, s.nrows):
        name = str(s.cell_value(r, 0)).strip()
        if not name:
            break
        rows.append({"industry": name} | {k: pd.to_numeric(s.cell_value(r, i), errors="coerce") for k, i in cols.items()})
    return pd.DataFrame(rows)


def countries(content: bytes) -> pd.DataFrame:
    """'ERPs by country': each country's total equity risk premium and country risk premium (rating-based), its
    sovereign rating and default spread."""
    s = book(content).sheet_by_name("ERPs by country")
    top = next(r for r in range(s.nrows) if str(s.cell_value(r, 0)).strip() == "Country")
    rows = []
    for r in range(top + 1, s.nrows):
        v = s.row_values(r)
        if not str(v[0]).strip():
            break
        rows.append({"country": str(v[0]).strip(), "region": v[1], "rating": v[2], "default_spread": v[3], "erp": v[4], "crp": v[5]})
    df = pd.DataFrame(rows)
    return df.assign(**{k: pd.to_numeric(df[k], errors="coerce") for k in ("default_spread", "erp", "crp")})


def ratings(content: bytes) -> pd.DataFrame:
    """The synthetic rating tables: interest cover from `low` to `high` -> rating and default spread, one table each for
    large non-financial firms, financial firms, smaller and riskier firms (and infrastructure)."""
    s, rows = book(content).sheet_by_index(0), []
    for r in range(s.nrows):
        for c in range(2, s.ncols):
            if str(s.cell_value(r, c)).strip() != "Rating is":
                continue
            label = next(str(s.cell_value(k, c - 2)) for k in range(r - 1, max(r - 4, -1), -1)
                         if str(s.cell_value(k, c - 2)).startswith("For "))  # "For large non-...", "For financial ..."
            kind = label.split()[1].lower()
            for k in range(r + 1, s.nrows):
                low, high, rating, spread = s.row_values(k)[c - 2:c + 2]
                if rating == "":
                    break
                rows.append({"table": kind, "low": low, "high": high, "rating": rating, "spread": spread})
    return pd.DataFrame(rows)


def code_of(ticker: str) -> tuple[str, str] | None:
    exchange, _, symbol = ticker.partition(":")
    market = EXCHANGES.get(exchange)
    if not market or not symbol:
        return None
    return market, symbol.zfill(5) if market == "hk" else symbol


def companies(content: bytes) -> pd.DataFrame:
    s, rows = book(content).sheet_by_name("By company name"), []
    for r in range(1, s.nrows):
        name, ticker, industry, sector, _, country, _, sub = s.row_values(r)[:8]
        if found := code_of(str(ticker)):
            rows.append({"market": found[0], "code": found[1], "industry": industry, "sector": sector,
                         "country": country, "region": sub})
    return pd.DataFrame(rows).drop_duplicates(["market", "code"])


def update(today: date | None = None) -> bool:
    """Download and parse everything when the stored set predates the latest refresh point. True when refreshed."""
    today = today or date.today()
    stamp = FOLDER / "fetched.txt"
    if stamp.exists() and date.fromisoformat(stamp.read_text().strip()) >= due(today):
        return False
    http = Http(min_interval=1.0, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    FOLDER.mkdir(parents=True, exist_ok=True)
    get = lambda name: http.get(URL.format(name)).content
    write(countries(get("ctryprem.xls")), FOLDER / "countries.csv.gz")
    write(ratings(get("ratings.xls")), FOLDER / "ratings.csv.gz")
    for region, suffix in REGIONS.items():
        parts = [industry_sheet(get(f"{'betas' if stem == 'beta' and not suffix else stem}{suffix}.xls"), spec)
                 for stem, spec in COLUMNS.items()]
        merged = parts[0]
        for p in parts[1:]:
            merged = merged.merge(p, on="industry", how="outer")
        write(merged, FOLDER / f"industries_{region}.csv.gz")
    write(companies(get("indname.xls")), FOLDER / "companies.csv.gz")
    stamp.write_text(today.isoformat())
    log.info("damodaran datasets refreshed")
    return True


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(FOLDER / f"{name}.csv.gz", dtype={"code": str})


def industry_of(market: str, code: str) -> dict:
    """Damodaran's industry and region for one listing, with that region's industry row (beta, margins, sales to
    capital, cost of capital); {} when he doesn't classify it."""
    co = load("companies")
    hit = co[(co["market"] == market) & (co["code"] == code)]
    if hit.empty:
        return {}
    row = hit.iloc[0]
    region = {"United States": "US", "China": "China"}.get(row["region"], "Global")
    stats = lambda reg: (t := load(f"industries_{reg}"))[t["industry"] == row["industry"]]
    found = stats(region)
    if found.empty or not found.iloc[0]["firms"] >= MIN_FIRMS:  # a thin regional sample (China's REITs: none): global
        region, found = "Global", stats("Global")
    return {"industry": row["industry"], "sector": row["sector"], "country": row["country"], "region": region} | (
        found.iloc[0].drop("industry").to_dict() if len(found) else {})


def country(name: str) -> dict:
    df = load("countries")
    hit = df[df["country"] == name]
    return hit.iloc[0].to_dict() if len(hit) else {}
