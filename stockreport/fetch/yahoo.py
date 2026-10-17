"""Yahoo (query1.finance.yahoo.com). Yahoo answers 429 to a full browser User-Agent; a bare one works.
- Chart API (v8/finance/chart): US daily prices and dividends, one call per stock, updated incrementally.
  Daily returns come from the adjusted close inside each response, so splits and dividends between
  fetches never break the chain; they are stored as close and an implied prev_close (like the CN table).
- Fundamentals timeseries: trailing-12-month numbers for the companies SEC companyfacts can't cover
  (mostly foreign filers), in their reporting currency. Weekly per company.
- '<CUR>=X' FX rates for those reporting currencies."""

import logging
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import Http, each, merge, stale, write

log = logging.getLogger(__name__)
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
TIMESERIES = "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"
PRICES, DIVIDENDS = DATA / "prices" / "us.csv.gz", DATA / "fundamentals" / "us_dividends.csv.gz"
GAPS, FX = DATA / "fundamentals" / "us_yahoo.csv.gz", DATA / "fx.csv"
FIELDS = {"revenue": "TotalRevenue", "np": "NetIncomeCommonStockholders", "gp": "GrossProfit",
          "ocf": "OperatingCashFlow", "equity": "StockholdersEquity",
          "liabilities": "TotalLiabilitiesNetMinorityInterest", "assets": "TotalAssets"}
MAX_AGE_DAYS = 200  # same freshness rule as SEC
INDEX = ("^GSPC", "SPX")  # S&P 500: the trading calendar (and the benchmark in Phase 6)
make_http = lambda: Http(min_interval=0.3, headers={"User-Agent": "Mozilla/5.0"})


def parse_chart(code: str, payload: dict, now: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily rows (date, code, close, prev_close, volume, amount) and dividends (code, ex_date, dps).
    The first row has no return and is dropped; so is today's bar while the session is still open."""
    res = payload["chart"]["result"][0]
    meta, quote = res["meta"], res["indicators"]["quote"][0]
    offset = timedelta(seconds=meta.get("gmtoffset", 0))
    day = lambda ts: (datetime.fromtimestamp(ts, timezone.utc) + offset).date().isoformat()
    df = pd.DataFrame({"date": [day(t) for t in res.get("timestamp") or []], "close": quote["close"],
                       "adj": res["indicators"]["adjclose"][0]["adjclose"], "volume": quote["volume"]})
    df = df.dropna().drop_duplicates("date", keep="last")
    session = meta.get("currentTradingPeriod", {}).get("regular", {})
    if session and session["start"] <= (now or time.time()) < session["end"]:
        df = df[df["date"] != day(session["start"])]
    df["prev_close"] = df["close"] / (df["adj"] / df["adj"].shift(1))
    df["amount"] = df["close"] * df["volume"]
    df = df.dropna(subset=["prev_close"]).assign(code=code)
    divs = [{"code": code, "ex_date": day(d["date"]), "dps": d["amount"]}
            for d in (res.get("events") or {}).get("dividends", {}).values()]
    prices = df[["date", "code", "close", "prev_close", "volume", "amount"]].round(
        {"close": 4, "prev_close": 4, "amount": 0})
    return prices, pd.DataFrame(divs, columns=["code", "ex_date", "dps"])


def chart(client: Http, job: tuple[str, str, date]) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    code, symbol, start = job
    resp = client.get(URL.format(symbol=symbol), ok=(200, 404), params={
        "period1": int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()),
        "period2": int(time.time()), "interval": "1d", "events": "div,split"})
    if resp.status_code == 404:  # delisted or renamed: dropped later for missing price history
        log.info("yahoo: no data for %s", symbol)
        return None
    return parse_chart(code, resp.json())


def load_prices() -> pd.DataFrame:
    return pd.read_csv(PRICES, dtype={"code": str, "date": str})


def update_prices(today: date, codes: list[str]) -> None:
    """Append the days since each stock's last stored day; new stocks get `history_days` of history."""
    keep_from = today - timedelta(days=CONFIG["universe"]["history_days"])
    old = load_prices() if PRICES.exists() else pd.DataFrame(columns=["date", "code"])
    last = old.groupby("code")["date"].max()
    start = lambda c: date.fromisoformat(last[c]) - timedelta(days=10) if c in last else keep_from
    index, _ = chart(make_http(), (INDEX[1], INDEX[0], start(INDEX[1])))
    latest = index["date"].max()
    todo = [(c, c.replace(".", "-"), start(c)) for c in codes if last.get(c, "") < latest]
    log.info("yahoo prices: %d of %d stocks to update to %s", len(todo), len(codes), latest)
    frames, divs = [old, index], []
    for i, got in enumerate(each(make_http, chart, todo, workers=2), 1):
        if got:
            frames.append(got[0])
            divs.append(got[1])
        if i % 200 == 0:
            log.info("yahoo prices: %d of %d", i, len(todo))
    df = pd.concat(frames).drop_duplicates(["date", "code"], keep="last")
    write(df[df["date"] >= keep_from.isoformat()].sort_values(["date", "code"]), PRICES)
    if divs:
        merge(DIVIDENDS, pd.concat(divs), ["code", "ex_date"])


def update_fx(currencies: set[str]) -> None:
    """Latest '<CUR>=X' close = units of CUR per US dollar, for companies that report in another currency
    (ECB rates via frankfurter have no TWD, which TSM reports in)."""
    client, rows = make_http(), []
    for cur in sorted(set(currencies) - {"USD"}):
        meta = client.get(URL.format(symbol=f"{cur}=X"), params={"range": "5d", "interval": "1d"}).json()["chart"]["result"][0]["meta"]
        rows.append({"currency": cur, "per_usd": meta["regularMarketPrice"],
                     "date": datetime.fromtimestamp(meta["regularMarketTime"], timezone.utc).date().isoformat()})
    if rows:
        old = pd.read_csv(FX) if FX.exists() else pd.DataFrame(columns=["currency"])
        pd.concat([old, pd.DataFrame(rows)]).drop_duplicates("currency", keep="last").to_csv(FX, index=False)


def parse_timeseries(code: str, payload: dict, today: date) -> dict:
    """TTM revenue / profit / gross profit / operating cash flow at the latest trailing period, the latest
    equity, liabilities and assets, and growth: TTM vs the TTM a year earlier, else the fiscal year a year
    earlier, else the latest quarter vs the same quarter a year earlier, else the last two fiscal years
    (semiannual reporters)."""
    series = {}
    for item in payload["timeseries"]["result"]:
        name = item["meta"]["type"][0]
        series[name] = sorted((v["asOfDate"], v["reportedValue"]["raw"], v.get("currencyCode"))
                              for v in item.get(name) or [] if v)
    near = lambda name, day: next((v for d, v, _ in series.get(name, [])
                                   if abs((date.fromisoformat(d) - day).days) <= 20), None)
    profit = series.get("trailing" + FIELDS["np"])
    if not profit or (today - date.fromisoformat(profit[-1][0])).days > MAX_AGE_DAYS:
        return {"code": code, "yahoo": "no recent TTM"}
    end = date.fromisoformat(profit[-1][0])
    row = {"code": code, "yahoo": "ok", "period": end.isoformat(), "currency": profit[-1][2]}
    for key in ("revenue", "np", "gp", "ocf"):
        row[f"{key}_ttm"] = near("trailing" + FIELDS[key], end)
    for key in ("equity", "liabilities", "assets"):
        points = series.get("quarterly" + FIELDS[key]) or series.get("annual" + FIELDS[key]) or []
        row[key] = points[-1][1] if points and abs((date.fromisoformat(points[-1][0]) - end).days) <= MAX_AGE_DAYS else None
    year_ago = end - timedelta(days=365)
    for key, out in (("revenue", "rev_yoy"), ("np", "np_yoy")):
        now = row[f"{key}_ttm"]
        before = near("trailing" + FIELDS[key], year_ago) or near("annual" + FIELDS[key], year_ago)
        if before is None:  # latest quarter vs the same quarter a year earlier
            now, before = near("quarterly" + FIELDS[key], end), near("quarterly" + FIELDS[key], year_ago)
        if before is None and len(series.get("annual" + FIELDS[key], [])) >= 2:  # else the last two fiscal years
            (_, before, _), (_, now, _) = series["annual" + FIELDS[key]][-2:]
        row[out] = (now - before) / abs(before) if now is not None and before else None
    return row


def timeseries(client: Http, job: tuple[str, date]) -> dict:
    code, today = job
    types = ",".join(f + FIELDS[k] for f in ("trailing", "quarterly", "annual") for k in FIELDS)
    payload = client.get(TIMESERIES.format(symbol=code.replace(".", "-")), params={
        "type": types, "period1": int(time.time()) - 5 * 365 * 86400, "period2": int(time.time())}).json()
    return parse_timeseries(code, payload, today)


def update_gaps(today: date, codes: list[str]) -> None:
    """Weekly per company, for the codes SEC has no recent quarterly numbers for."""
    rows = [r | {"fetched": today.isoformat()} for r in each(make_http, timeseries, [(c, today) for c in stale(GAPS, codes, today)], workers=2) if r]
    if rows:
        merge(GAPS, pd.DataFrame(rows), ["code"])
        log.info("yahoo fundamentals: %d gap companies, %s", len(rows), pd.Series([r["yahoo"] for r in rows]).value_counts().to_dict())
