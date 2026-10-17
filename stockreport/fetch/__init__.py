"""Fetching: a polite HTTP client and `fetch(market)`, which brings data/ up to date."""

import gzip
import json
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd

from stockreport.config import CONFIG, DATA

log = logging.getLogger(__name__)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


class Http:
    """Serial requests with a minimum gap between calls, retried with backoff."""

    def __init__(self, min_interval: float = 1.0, timeout: float = 30.0, headers: dict | None = None):
        self.client = httpx.Client(headers={"User-Agent": UA} | (headers or {}), timeout=timeout)
        self.min_interval = min_interval
        self._last = 0.0

    def get(self, url: str, params: dict | None = None, ok=(200,), tries: int = 4) -> httpx.Response:
        return self.request("GET", url, params=params, ok=ok, tries=tries)

    def post(self, url: str, data: dict, ok=(200,), tries: int = 4) -> httpx.Response:
        return self.request("POST", url, data=data, ok=ok, tries=tries)

    def request(self, method: str, url: str, params: dict | None = None, data: dict | None = None,
                ok=(200,), tries: int = 4) -> httpx.Response:
        err = ""
        for attempt in range(1, tries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait + random.uniform(0, 0.3 * self.min_interval))
            try:
                resp = self.client.request(method, url, params=params, data=data)
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


def each(make_http, fn, items: list, workers: int):
    """fn(http, item) for every item on `workers` threads, one Http client per thread, in order.
    An item that fails yields None (logged), so one bad stock never stops a fetch."""
    local = threading.local()

    def run(item):
        if not hasattr(local, "http"):
            local.http = make_http()
        try:
            return fn(local.http, item)
        except Exception as e:
            log.warning("%s: %s", item, e)
            return None
    with ThreadPoolExecutor(workers) as pool:
        yield from pool.map(run, items)


def upsert_each(path: Path, make_http, fn, todo: list, today: date, workers: int, label: str) -> None:
    """Rows from fn(http, item) for every item, stamped `fetched` = today and upserted into the
    per-stock table every 100 items, so an interrupted fetch keeps what it got."""
    rows = []
    for i, row in enumerate(each(make_http, fn, todo, workers), 1):
        if row:
            rows.append(row | {"fetched": today.isoformat()})
        if rows and (i % 100 == 0 or i == len(todo)):
            merge(path, pd.DataFrame(rows), ["code"])
            rows = []
            log.info("%s: %d of %d", label, i, len(todo))


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


def stale(path: Path, codes: list[str], today: date, days: int | None = None) -> list[str]:
    """Codes missing from a per-stock table (column `fetched`) or fetched more than `days` ago."""
    days = days or CONFIG["fetch"]["fundamentals_refresh_days"]
    if not path.exists():
        return list(codes)
    fetched = pd.read_csv(path, usecols=["code", "fetched"], dtype=str).set_index("code")["fetched"]
    cutoff = (today - timedelta(days=days)).isoformat()
    return [c for c in codes if fetched.get(c, "") <= cutoff]


def write(df: pd.DataFrame, path: Path) -> None:
    """Gzipped CSV, written atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_csv(tmp, index=False, compression="gzip")
    tmp.replace(path)


def save_rates(new: pd.DataFrame, market: str) -> None:
    """Upsert 10-year yields (date, market, y10 in %) into data/rates.csv."""
    if new.empty:
        raise RuntimeError(f"no recent {market.upper()} 10-year yield")
    path = DATA / "rates.csv"
    old = pd.read_csv(path, dtype={"date": str}) if path.exists() else new.iloc[:0]
    df = pd.concat([old, new]).drop_duplicates(["date", "market"], keep="last").sort_values(["market", "date"])
    df.to_csv(path, index=False)


def merge(path: Path, new: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    """Upsert rows into a gzipped CSV table."""
    old = pd.read_csv(path, dtype={"code": str}) if path.exists() else new.iloc[:0]
    df = pd.concat([old, new]).drop_duplicates(key, keep="last") if len(new) else old
    write(df, path)
    return df


def steps(market: str, today: date) -> list:
    if market == "cn":
        from stockreport.fetch import eastmoney, tdx
        return [("prices", lambda: tdx.update_prices(today)),
                ("quotes", lambda: eastmoney.update_quotes()),
                ("fundamentals", lambda: eastmoney.update_fundamentals(today)),
                ("dividends", lambda: eastmoney.update_dividends(today)),
                ("consensus", lambda: eastmoney.update_consensus(today)),
                ("10y yield", lambda: eastmoney.update_yield())]
    if market == "us":
        from stockreport.fetch import fred, nasdaq, sec, yahoo
        return [("listing", nasdaq.update_list),
                ("prices", lambda: yahoo.update_prices(today, nasdaq.candidates())),
                ("SEC fundamentals", lambda: sec.update_facts(today, nasdaq.candidates())),
                ("Yahoo fundamentals for SEC gaps", lambda: yahoo.update_gaps(today, sec.gaps(nasdaq.candidates()))),
                ("FX", lambda: yahoo.update_fx(set(pd.read_csv(yahoo.GAPS)["currency"].dropna()))),
                ("consensus", lambda: nasdaq.update_consensus(today, nasdaq.candidates())),
                ("10y yield", fred.update_yield)]
    if market == "hk":
        from stockreport.fetch import eastmoney, hkgb, yahoo
        return [("company list", lambda: eastmoney.update_hk_list(today)),
                ("fundamentals", lambda: eastmoney.update_hk_fundamentals(today)),
                ("prices", lambda: yahoo.update_prices(today, eastmoney.hk_candidates(), "hk")),
                ("consensus and reporting currency", lambda: yahoo.update_consensus(today, eastmoney.hk_candidates())),
                ("FX", lambda: hk_fx(yahoo)),
                ("US issuer ids", lambda: eastmoney.update_us_orgs(today)),
                ("10y yield", hkgb.update_yield)]
    raise SystemExit(f"unknown market {market!r}")


def hk_fx(yahoo) -> None:
    """Today's rates for HKD and the HK reporting and estimate currencies, and their CNY history."""
    cons = pd.read_csv(yahoo.CONSENSUS)
    currencies = set(cons["currency"].dropna()) | set(cons["report_currency"].dropna())
    yahoo.update_fx(currencies | {"HKD"})
    yahoo.update_cny_rates(currencies)


def fetch(market: str, today: date | None = None) -> list[str]:
    """Update all cached data for a market. Returns the steps that failed (cache is kept for those)."""
    today = today or date.today()
    failed = []
    for name, step in steps(market, today):
        try:
            step()
        except Exception as e:  # keep going: the last good cache is used for this step
            log.error("fetch %s %s failed: %s", market, name, e)
            failed.append(name)
    return failed
