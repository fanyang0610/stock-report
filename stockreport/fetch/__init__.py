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
HISTORY = DATA / "history"  # multi-year tables for valuation v2 (PLAN.md Storage)
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


def upsert_each(path: Path, make_http, fn, todo: list, today: date, workers: int, label: str,
                history: Path | None = None) -> None:
    """Rows from fn(http, item) for every item, stamped `fetched` = today and upserted into the
    per-stock table every 100 items, so an interrupted fetch keeps what it got. With `history`, fn
    returns (row, yearly rows) and the yearly rows go to that table (keyed by code and fy_end) first."""
    rows, years = [], []
    for i, got in enumerate(each(make_http, fn, todo, workers), 1):
        row, more = got if history and got else (got, [])
        if row:
            rows.append(row | {"fetched": today.isoformat()})
            years += [r | {"fetched": today.isoformat()} for r in more]
        if rows and (i % 100 == 0 or i == len(todo)):
            if years:
                merge(history, pd.DataFrame(years), ["code", "fy_end"])
            merge(path, pd.DataFrame(rows), ["code"])
            rows, years = [], []
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
    fetched = pd.read_csv(path, usecols=["code", "fetched"], dtype=str).groupby("code")["fetched"].max()
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
    """Upsert rows into a gzipped CSV table (key columns are compared as text, e.g. "004")."""
    old = pd.read_csv(path, dtype={"code": str} | dict.fromkeys(key, str)) if path.exists() else new.iloc[:0]
    df = pd.concat([old, new]).drop_duplicates(key, keep="last") if len(new) else old
    write(df, path)
    return df


def snapshot(src: Path, market: str, today: date, days: int = 7) -> None:
    """Append the market's consensus table to data/history/<market>_consensus.csv.gz once a week
    (column `snapshot`), so estimate revisions have a record."""
    dest = HISTORY / f"{market}_consensus.csv.gz"
    if not src.exists() or (dest.exists() and (today - date.fromtimestamp(dest.stat().st_mtime)).days < days):
        return
    new = pd.read_csv(src, dtype={"code": str}).assign(snapshot=today.isoformat())
    old = pd.read_csv(dest, dtype={"code": str, "snapshot": str}) if dest.exists() else new.iloc[:0]
    write(pd.concat([old[old["snapshot"] != today.isoformat()], new]), dest)


def steps(market: str, today: date) -> list:
    from stockreport.track import tracked
    if market == "cn":
        from stockreport.fetch import eastmoney, tdx, tencent
        return [("prices", lambda: tdx.update_prices(today)),
                ("quotes", lambda: eastmoney.update_quotes()),
                ("Tencent quotes", lambda: tencent.update_quotes(eastmoney.cn_largest())),
                ("fundamentals", lambda: eastmoney.update_fundamentals(today)),
                ("dividends", lambda: eastmoney.update_dividends(today)),
                ("consensus", lambda: eastmoney.update_consensus(today)),
                ("10y yield", lambda: eastmoney.update_yield()),
                ("history", lambda: eastmoney.update_cn_history(today)),
                ("pre-announcements", lambda: eastmoney.update_forecasts(today)),
                ("consensus snapshot", lambda: snapshot(DATA / "fundamentals" / "cn_consensus.csv.gz", "cn", today))]
    if market == "us":
        from stockreport.fetch import fred, nasdaq, sec, yahoo
        return [("listing", nasdaq.update_list),
                ("prices", lambda: yahoo.update_prices(today, tracked("us", today, nasdaq.candidates()))),
                ("SEC fundamentals", lambda: sec.update_facts(today, nasdaq.candidates())),
                ("Yahoo fundamentals", lambda: yahoo.update_gaps(today, us_yahoo_codes(sec, nasdaq))),
                ("FX", lambda: yahoo.update_fx(set(pd.read_csv(yahoo.GAPS)["currency"].dropna()))),
                ("consensus", lambda: nasdaq.update_consensus(today, nasdaq.candidates())),
                ("10y yield", fred.update_yield),
                ("Yahoo annual history", lambda: yahoo.update_annual(today, sec.annual_gaps(nasdaq.candidates()), sec.ANNUAL)),
                ("monthly prices", lambda: yahoo.update_monthly(
                    today, "us", nasdaq.candidates(), {f"{c}=X" for c in sec.history_currencies()})),
                ("consensus snapshot", lambda: snapshot(nasdaq.CONSENSUS, "us", today))]
    if market == "hk":
        from stockreport.fetch import eastmoney, hkgb, yahoo
        return [("company list", lambda: eastmoney.update_hk_list(today)),
                ("fundamentals", lambda: eastmoney.update_hk_fundamentals(today)),
                ("prices", lambda: yahoo.update_prices(today, tracked("hk", today, eastmoney.hk_candidates()), "hk")),
                ("consensus and reporting currency", lambda: yahoo.update_consensus(today, eastmoney.hk_candidates())),
                ("FX", lambda: hk_fx(yahoo)),
                ("US issuer ids", lambda: eastmoney.update_us_orgs(today)),
                ("10y yield", hkgb.update_yield),
                ("history", lambda: eastmoney.update_hk_history(today)),
                ("monthly prices", lambda: yahoo.update_monthly(today, "hk", eastmoney.hk_candidates(), {"HKDCNY=X"})),
                ("consensus snapshot", lambda: snapshot(yahoo.CONSENSUS, "hk", today))]
    raise SystemExit(f"unknown market {market!r}")


def us_yahoo_codes(sec, nasdaq) -> list[str]:
    """The companies SEC can't cover first (Yahoo values them), then the rest (Yahoo is their second source)."""
    gaps = sec.gaps(nasdaq.candidates())
    return gaps + [c for c in nasdaq.candidates() if c not in set(gaps)]


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
