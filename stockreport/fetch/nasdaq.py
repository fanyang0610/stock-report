"""Nasdaq (api.nasdaq.com): the US stock screener (every NASDAQ/NYSE/AMEX listing with market value,
sector and industry, one call) and analyst consensus EPS per stock (earnings-forecast, refreshed weekly).
Market value is company-wide on every share class and ADR, so shares = market value / price."""

import logging
import re
from datetime import date, datetime

import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import Http, stale, upsert_each, write

log = logging.getLogger(__name__)
SCREENER = "https://api.nasdaq.com/api/screener/stocks"
FORECAST = "https://api.nasdaq.com/api/analyst/{symbol}/earnings-forecast"
LIST, CONSENSUS = DATA / "quotes" / "us_list.csv.gz", DATA / "fundamentals" / "us_consensus.csv.gz"
# Listings that are not ordinary shares: preferreds, notes, warrants, rights, units (MLP common units stay),
# fractional depositary shares of preferreds; SPACs by industry. ADRs and names that say ordinary or
# common shares are kept (e.g. ITUB's ADR of preferred shares, BNS "Pfd 3 Ordinary Shares").
NOT_ORDINARY = re.compile(r"Preferred|Pfd|\bNotes?\b|Debenture|Warrants?|\bRights?\b|ZONES|Tangible Equity|"
                          r"Corporate Units?|(?<!Common )\bUnits?\b|\d/\d+(?:st|nd|rd|th)\b|\d%", re.I)
ORDINARY = re.compile(r"American Depositary|Ordinary Shares?|Common (?:Stock|Shares?)", re.I)
NOT_COMPANY = ["Blank Checks"]
NAME_TAIL = re.compile(r"\s+(Class [A-C] )?(Common Stock|Common Shares?|Ordinary Shares?|Capital Stock|"
                       r"American Depositary|Sponsored ADR|ADS\b|New York Registry|NY Registry|Registry Shares|"
                       r"Subordinate Voting|Limited Voting|Common Units).*$", re.I)
http = Http(min_interval=0.5, headers={"Accept": "application/json"})


def money(text: str) -> float:
    try:
        return float(str(text).replace("$", "").replace(",", ""))
    except ValueError:
        return float("nan")


def parse_screener(payload: dict) -> pd.DataFrame:
    rows = payload["data"]["rows"]
    df = pd.DataFrame({
        "code": [r["symbol"].strip().replace("/", ".") for r in rows],
        "listing": [r["name"].strip() for r in rows],
        "name": [NAME_TAIL.sub("", r["name"].strip()).rstrip(" ,.") or r["name"].strip() for r in rows],
        "last": [money(r["lastsale"]) for r in rows],
        "mcap": [money(r["marketCap"]) for r in rows],
        "sector": [r["sector"] or "" for r in rows],
        "industry": [r["industry"] or "" for r in rows],
        "country": [r["country"] or "" for r in rows],
    })
    return df[df["mcap"] > 0]


def update_list() -> None:
    """Today's screener table (one call). Kept small: a few hundred KB."""
    df = parse_screener(http.get(SCREENER, params={"tableonly": "true", "download": "true"}).json())
    if len(df) < 4000:
        raise RuntimeError(f"only {len(df)} US listings with a market value")
    df["fetched"] = datetime.now().isoformat(timespec="minutes")
    write(df, LIST)
    log.info("us listing: %d stocks", len(df))


def load_list() -> pd.DataFrame:
    return pd.read_csv(LIST, dtype={"code": str}, keep_default_na=False, na_values={"mcap": [""], "last": [""]})


def named(df: pd.DataFrame) -> pd.DataFrame:
    """The company's name from Yahoo's quote (longName, fetched daily with the share counts: yahoo.SHARES), else the
    screener's. About 20 of the 800 screener names carry share-class, registry or domicile words ("Bank Nova Scotia
    Halifax Pfd 3", "Kimco Realty Corporation (HC)", "Mizuho Financial Group Inc. Sponosred ADR (Japan)") that a card
    shows and the review's prompt reads as facts: DeepSeek called BNS's common share a preferred one."""
    from stockreport.fetch import yahoo
    if not yahoo.SHARES.exists() or "name" not in pd.read_csv(yahoo.SHARES, nrows=0).columns:
        return df
    quote = pd.read_csv(yahoo.SHARES, dtype={"code": str}).drop_duplicates("code", keep="last").set_index("code")
    return df.assign(name=quote["name"].reindex(df.index).fillna(df["name"]))


def ordinary(df: pd.DataFrame) -> pd.Series:
    return ((~df["listing"].str.contains(NOT_ORDINARY) | df["listing"].str.contains(ORDINARY))
            & ~df["industry"].isin(NOT_COMPANY))


def candidates() -> list[str]:
    """Ordinary shares, largest first: the stocks whose prices and fundamentals are kept up to date."""
    df = load_list()
    return list(df[ordinary(df)].sort_values("mcap", ascending=False)["code"].head(CONFIG["universe"]["us_candidates"]))


def parse_forecast(code: str, payload: dict) -> dict | None:
    """Consensus EPS for the first three fiscal years not yet reported (like the CN table)."""
    rows = ((payload.get("data") or {}).get("yearlyForecast") or {}).get("rows") or []
    est = sorted((datetime.strptime(r["fiscalEnd"], "%b %Y"), r["consensusEPSForecast"], r["noOfEstimates"])
                 for r in rows if r.get("consensusEPSForecast") is not None)
    if len(est) < 3:
        return None
    return {"code": code, "analysts": est[1][2] or 0, "e1_year": est[0][0].strftime("%Y-%m"),
            "eps_e1": est[0][1], "eps_e2": est[1][1], "eps_e3": est[2][1]}


def forecast(client: Http, code: str) -> dict:
    payload = client.get(FORECAST.format(symbol=code.replace(".", "-")), params={"assetclass": "stocks"}).json()
    return parse_forecast(code, payload) or {"code": code, "analysts": 0}


def update_consensus(today: date, codes: list[str]) -> None:
    """Weekly per stock (4 at a time: each call takes 2-4 s); a stock without three years of
    estimates is stored with analysts = 0, a failed one is retried next run."""
    make = lambda: Http(min_interval=0.5, headers={"Accept": "application/json"})
    upsert_each(CONSENSUS, make, forecast, stale(CONSENSUS, codes, today), today, 4, "us consensus")
