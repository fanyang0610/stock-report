"""FRED (api.stlouisfed.org): the US 10-year Treasury yield DGS10 (%), key FRED_API_KEY in .env."""

import pandas as pd
from dotenv import dotenv_values

from stockreport.config import ROOT
from stockreport.fetch import Http, save_rates

URL = "https://api.stlouisfed.org/fred/series/observations"
http = Http(min_interval=0.5)


def parse_observations(payload: dict, market: str) -> pd.DataFrame:
    """FRED marks holidays with '.'; those rows are skipped."""
    return pd.DataFrame([{"date": o["date"], "market": market, "y10": float(o["value"])}
                         for o in payload["observations"] if o["value"] not in (".", "")])


def update_yield() -> None:
    key = dotenv_values(ROOT / ".env").get("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY is missing from .env")
    resp = http.get(URL, params={"series_id": "DGS10", "api_key": key, "file_type": "json",
                                 "sort_order": "desc", "limit": 20})
    save_rates(parse_observations(resp.json(), "us"), "us")
