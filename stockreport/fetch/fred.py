"""FRED (api.stlouisfed.org), key FRED_API_KEY in .env: the US 10-year Treasury yield DGS10 (%), and the OECD's monthly
long-term government yields (IRLTLT01) for the other currencies the companies report in, stored under the lowercase
currency code (research/value.yield_of reads them; a currency with no series takes the US yield, said)."""

import logging

import pandas as pd
from dotenv import dotenv_values

from stockreport.config import ROOT
from stockreport.fetch import Http, save_rates

URL = "https://api.stlouisfed.org/fred/series/observations"
http = Http(min_interval=0.5)
log = logging.getLogger(__name__)
# currency -> the OECD country of its 10-year government yield (the euro: Germany's, the benchmark; Taiwan, Brazil,
# India and the rest are not in FRED's OECD series: no free source found, so they take the US yield)
OECD = {"AUD": "AU", "CAD": "CA", "CHF": "CH", "CLP": "CL", "DKK": "DK", "EUR": "DE", "GBP": "GB", "JPY": "JP",
        "KRW": "KR", "MXN": "MX", "SEK": "SE", "ZAR": "ZA"}


def parse_observations(payload: dict, market: str) -> pd.DataFrame:
    """FRED marks holidays with '.'; those rows are skipped."""
    return pd.DataFrame([{"date": o["date"], "market": market, "y10": float(o["value"])}
                         for o in payload["observations"] if o["value"] not in (".", "")])


def update_yield() -> None:
    key = dotenv_values(ROOT / ".env").get("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY is missing from .env")
    get = lambda series, limit: http.get(URL, params={"series_id": series, "api_key": key, "file_type": "json",
                                                      "sort_order": "desc", "limit": limit}).json()
    save_rates(parse_observations(get("DGS10", 20), "us"), "us")
    for cur, country in OECD.items():  # a currency whose series fails keeps its last rows (else the US yield, said)
        try:
            save_rates(parse_observations(get(f"IRLTLT01{country}M156N", 3), cur.lower()), cur.lower())
        except Exception as e:
            log.warning("%s 10-year yield: %s", cur, e)
