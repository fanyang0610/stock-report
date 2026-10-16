"""Fetching: a polite HTTP client and `fetch(market)`, which brings data/ up to date."""

import gzip
import json
import logging
import random
import time
from datetime import date
from pathlib import Path

import httpx

from stockreport.config import CONFIG, DATA

log = logging.getLogger(__name__)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


class Http:
    """Serial requests with a minimum gap between calls, retried with backoff."""

    def __init__(self, min_interval: float = 1.0, timeout: float = 30.0):
        self.client = httpx.Client(headers={"User-Agent": UA}, timeout=timeout)
        self.min_interval = min_interval
        self._last = 0.0

    def get(self, url: str, params: dict | None = None, ok=(200,), tries: int = 4) -> httpx.Response:
        err = ""
        for attempt in range(1, tries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait + random.uniform(0, 0.3 * self.min_interval))
            try:
                resp = self.client.get(url, params=params)
                if resp.status_code in ok:
                    return resp
                if resp.status_code < 500 and resp.status_code != 429:
                    raise RuntimeError(f"HTTP {resp.status_code} from {url}")
                err = f"HTTP {resp.status_code}"
            except httpx.HTTPError as e:
                err = type(e).__name__
            finally:
                self._last = time.monotonic()
            log.warning("%s failed (%s), attempt %d/%d", url, err, attempt, tries)
            time.sleep(2 * attempt)
        raise RuntimeError(f"giving up on {url}: {err}")


def save_raw(name: str, payload) -> None:
    """Keep a raw response under data/raw/<date>/ (deleted by cleanup after a few days)."""
    folder = DATA / "raw" / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    with gzip.open(folder / f"{name}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def needs_refresh(path: Path, today: date, open_period: bool = False) -> bool:
    """Open report periods refresh daily; everything else weekly (and on Sundays)."""
    if not path.exists():
        return True
    fetched = date.fromtimestamp(path.stat().st_mtime)
    if fetched >= today:
        return False
    return (open_period or today.weekday() == 6
            or (today - fetched).days >= CONFIG["fetch"]["fundamentals_refresh_days"])


def fetch(market: str, today: date | None = None) -> list[str]:
    """Update all cached data for a market. Returns the steps that failed (cache is kept for those)."""
    from stockreport.fetch import eastmoney, tdx

    today = today or date.today()
    if market != "cn":
        raise SystemExit(f"market {market!r} is not built yet (Phase 2 covers cn only)")
    steps = [("prices", lambda: tdx.update_prices(today)),
             ("quotes", lambda: eastmoney.update_quotes()),
             ("fundamentals", lambda: eastmoney.update_fundamentals(today)),
             ("dividends", lambda: eastmoney.update_dividends(today)),
             ("consensus", lambda: eastmoney.update_consensus(today)),
             ("10y yield", lambda: eastmoney.update_yield())]
    failed = []
    for name, step in steps:
        try:
            step()
        except Exception as e:  # keep going: the last good cache is used for this step
            log.error("fetch %s %s failed: %s", market, name, e)
            failed.append(name)
    return failed
