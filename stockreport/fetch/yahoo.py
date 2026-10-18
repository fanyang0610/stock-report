"""Yahoo (query1.finance.yahoo.com). Yahoo answers 429 to a full browser User-Agent; a bare one works.
- Chart API (v8/finance/chart): US and HK daily prices and dividends, one call per stock, updated incrementally.
  Daily returns come from the adjusted close inside each response, so splits and dividends between
  fetches never break the chain; they are stored as close and an implied prev_close (like the CN table).
- Fundamentals timeseries: trailing-12-month numbers for the companies SEC companyfacts can't cover
  (mostly foreign filers), in their reporting currency. Weekly per company.
- '<CUR>=X' FX rates for those reporting currencies (and HK's), and daily '<CUR>CNY=X' history to undo
  Eastmoney's conversion of HK companies' figures to CNY at each period-end rate.
- quoteSummary: HK consensus EPS for this and next fiscal year, and the reporting currency (needs a
  cookie + crumb).
- History (weekly, on Sundays): annual results for the US companies SEC has no annual history for
  (Yahoo keeps 4-5 years), and ~11 years of month-end closes, monthly returns and splits for US/HK
  stocks, their index and the FX rates own-history P/B needs (HKDCNY, US reporting currencies)."""

import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import HISTORY, Http, each, merge, stale, upsert_each, write

log = logging.getLogger(__name__)
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
TIMESERIES = "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"
SUMMARY = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
PRICES, DIVIDENDS = DATA / "prices" / "{}.csv.gz", DATA / "fundamentals" / "{}_dividends.csv.gz"
GAPS, FX, CONSENSUS = DATA / "fundamentals" / "us_yahoo.csv.gz", DATA / "fx.csv", DATA / "fundamentals" / "hk_consensus.csv.gz"
FX_CNY = DATA / "fx_cny.csv.gz"
MONTHLY, SPLITS = HISTORY / "{}_monthly.csv.gz", HISTORY / "{}_splits.csv.gz"
HISTORY_YEARS = 11
# annual history columns as in sec.TAXONOMIES; capex and dividends paid are negative in Yahoo, stored positive
ANNUAL_FIELDS = {"revenue": "TotalRevenue", "gp": "GrossProfit", "op_income": "OperatingIncome", "ni": "NetIncome",
                 "ni_common": "NetIncomeCommonStockholders", "ni_cont": "NetIncomeContinuousOperations",
                 "ocf": "OperatingCashFlow", "capex": "CapitalExpenditure", "div": "CashDividendsPaid",
                 "dil_shares": "DilutedAverageShares", "equity": "StockholdersEquity", "pref": "PreferredStockEquity",
                 "assets": "TotalAssets", "liabilities": "TotalLiabilitiesNetMinorityInterest", "shares": "OrdinarySharesNumber"}
# ni (net income before preferred dividends, like SEC's NetIncomeLoss) and shares: for the US cross-checks
FIELDS = {"revenue": "TotalRevenue", "np": "NetIncomeCommonStockholders", "gp": "GrossProfit",
          "ocf": "OperatingCashFlow", "equity": "StockholdersEquity",
          "liabilities": "TotalLiabilitiesNetMinorityInterest", "assets": "TotalAssets",
          "ni": "NetIncome", "shares": "OrdinarySharesNumber"}
MAX_AGE_DAYS = 200  # same freshness rule as SEC
# market -> (index symbol, its code in the price table, ticker -> Yahoo symbol); the index is the
# trading calendar (and the benchmark in Phase 6): S&P 500, Hang Seng
MARKETS = {"us": ("^GSPC", "SPX", lambda c: c.replace(".", "-")), "hk": ("^HSI", "HSI", lambda c: f"{int(c):04d}.HK")}
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


def load_prices(market: str = "us") -> pd.DataFrame:
    return pd.read_csv(str(PRICES).format(market), dtype={"code": str, "date": str})


def update_prices(today: date, codes: list[str], market: str = "us") -> None:
    """Append the days since each stock's last stored day; new stocks get `history_days` of history."""
    keep_from = today - timedelta(days=CONFIG["universe"]["history_days"])
    path, (index_symbol, index_code, symbol) = Path(str(PRICES).format(market)), MARKETS[market]
    old = load_prices(market) if path.exists() else pd.DataFrame(columns=["date", "code"])
    last = old.groupby("code")["date"].max()
    start = lambda c: date.fromisoformat(last[c]) - timedelta(days=10) if c in last else keep_from
    index, _ = chart(make_http(), (index_code, index_symbol, start(index_code)))
    latest = index["date"].max()
    todo = [(c, symbol(c), start(c)) for c in codes if last.get(c, "") < latest]
    log.info("yahoo %s prices: %d of %d stocks to update to %s", market, len(todo), len(codes), latest)
    frames, divs = [old, index], []
    for i, got in enumerate(each(make_http, chart, todo, workers=2), 1):
        if got:
            frames.append(got[0])
            divs.append(got[1])
        if i % 200 == 0:
            log.info("yahoo prices: %d of %d", i, len(todo))
    df = pd.concat(frames).drop_duplicates(["date", "code"], keep="last")
    write(df[df["date"] >= keep_from.isoformat()].sort_values(["date", "code"]), path)
    if divs:
        merge(Path(str(DIVIDENDS).format(market)), pd.concat(divs), ["code", "ex_date"])


def load_fx() -> pd.Series:
    """Units of each currency per US dollar (USD = 1)."""
    fx = pd.read_csv(FX).set_index("currency")["per_usd"] if FX.exists() else pd.Series(dtype=float)
    return pd.concat([fx, pd.Series({"USD": 1.0})])


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
    for key in ("revenue", "np", "gp", "ocf", "ni"):
        row[f"{key}_ttm"] = near("trailing" + FIELDS[key], end)
    for key in ("equity", "liabilities", "assets", "shares"):
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
    """Weekly per company: the codes SEC has no recent quarterly numbers for first, then the rest of the
    candidates, whose Yahoo numbers are only the second source of the cross-checks."""
    upsert_each(GAPS, make_http, timeseries, [(c, today) for c in stale(GAPS, codes, today)], today, 2, "yahoo fundamentals")


def crumb_http() -> Http:
    """quoteSummary needs Yahoo's A3 cookie (set by fc.yahoo.com, itself a 404) and the crumb for it."""
    http = make_http()
    http.client.get("https://fc.yahoo.com")
    http.crumb = http.get("https://query1.finance.yahoo.com/v1/test/getcrumb").text
    return http


def parse_trend(code: str, payload: dict) -> dict:
    """The reporting currency, and consensus EPS for the current fiscal year (0y) and the next (+1y)
    with last year's actual EPS (0y's yearAgoEps), in the estimate currency; analysts = estimates
    behind next year's EPS. Key statistics for the cross-checks: book value and trailing EPS per share in
    HKD (the quote currency), the shares Yahoo's market value counts, and the latest reported period."""
    result = (payload.get("quoteSummary") or {}).get("result") or [{}]
    trend = {t["period"]: t for t in (result[0].get("earningsTrend") or {}).get("trend", [])}
    est = lambda period, key: ((trend.get(period, {}).get("earningsEstimate") or {}).get(key) or {}).get("raw")
    stats, detail = result[0].get("defaultKeyStatistics") or {}, result[0].get("summaryDetail") or {}
    hkd = detail.get("currency") == "HKD"
    stat = lambda d, key: (d.get(key) or {}).get("raw") if hkd and isinstance(d.get(key), dict) else None
    quarter = stat(stats, "mostRecentQuarter")
    row = {"code": code, "analysts": 0, "report_currency": (result[0].get("earnings") or {}).get("financialCurrency"),
           "bvps_y": stat(stats, "bookValue"), "eps_ttm_y": stat(stats, "trailingEps"),
           "shares_y": stat(stats, "impliedSharesOutstanding"),
           "period_y": datetime.fromtimestamp(quarter, timezone.utc).date().isoformat() if quarter else None}
    if None in (est("0y", "avg"), est("+1y", "avg"), est("0y", "yearAgoEps")):
        return row
    return row | {"analysts": est("+1y", "numberOfAnalysts") or 0, "e1_year": trend["0y"]["endDate"][:7],
                  "eps_e0": est("0y", "yearAgoEps"), "eps_e1": est("0y", "avg"), "eps_e2": est("+1y", "avg"),
                  "currency": trend["0y"]["earningsEstimate"].get("earningsCurrency")}


def trend(client: Http, code: str) -> dict:
    payload = client.get(SUMMARY.format(symbol=MARKETS["hk"][2](code)), ok=(200, 404),
                         params={"modules": "earningsTrend,earnings,defaultKeyStatistics,summaryDetail",
                                 "crumb": client.crumb}).json()
    return parse_trend(code, payload)


def update_consensus(today: date, codes: list[str]) -> None:
    """HK consensus EPS, reporting currency and key statistics, weekly per stock; no estimates: analysts = 0.
    A table fetched before the key statistics were added (Phase 12) is fetched again for every stock."""
    todo = stale(CONSENSUS, codes, today)
    if CONSENSUS.exists() and "bvps_y" not in pd.read_csv(CONSENSUS, nrows=0).columns:
        todo = list(codes)
    upsert_each(CONSENSUS, crumb_http, trend, todo, today, 2, "hk consensus")


def update_cny_rates(currencies: set[str], days: int = 900) -> None:
    """Daily CNY per unit of each currency for the last `days` days ('<CUR>CNY=X' closes)."""
    client, frames = make_http(), []
    for cur in sorted(set(currencies) - {"CNY"}):
        res = client.get(URL.format(symbol=f"{cur}CNY=X"), params={"period1": int(time.time()) - days * 86400,
                                                                   "period2": int(time.time()), "interval": "1d"})
        res = res.json()["chart"]["result"][0]
        day = lambda ts: (datetime.fromtimestamp(ts, timezone.utc) + timedelta(seconds=res["meta"]["gmtoffset"])).date()
        frames.append(pd.DataFrame({"currency": cur, "date": [day(t).isoformat() for t in res["timestamp"]],
                                    "close": res["indicators"]["quote"][0]["close"]}).dropna())
    write(pd.concat(frames), FX_CNY)


def cny_per(currency: pd.Series, day: pd.Series) -> pd.Series:
    """CNY per unit of `currency` at the last close on or before `day` (1 for CNY)."""
    rates = pd.read_csv(FX_CNY, parse_dates=["date"]).sort_values("date")
    rows = pd.DataFrame({"row": range(len(day)), "currency": currency.to_numpy(), "date": pd.to_datetime(day.to_numpy())})
    rate = pd.merge_asof(rows.sort_values("date"), rates, on="date", by="currency").sort_values("row")["close"]
    return pd.Series(rate.to_numpy(), index=currency.index).where(currency != "CNY", 1.0)


def parse_annual(code: str, payload: dict) -> list[dict]:
    """One row per fiscal year (asOfDate) in the reporting currency, columns as in the SEC history."""
    by = {}
    for item in payload["timeseries"]["result"]:
        name = item["meta"]["type"][0]
        key = next((k for k, t in ANNUAL_FIELDS.items() if "annual" + t == name), None)
        for v in item.get(name) or []:
            if v and key:
                row = by.setdefault(v["asOfDate"], {"code": code, "fy_end": v["asOfDate"], "source": "Yahoo"})
                row["currency"] = row.get("currency") or v.get("currencyCode")
                row[key] = abs(v["reportedValue"]["raw"]) if key in ("capex", "div") else v["reportedValue"]["raw"]
    return [by[k] for k in sorted(by)]


def annual_series(client: Http, code: str) -> list[dict]:
    types = ",".join("annual" + t for t in ANNUAL_FIELDS.values())
    payload = client.get(TIMESERIES.format(symbol=code.replace(".", "-")), params={
        "type": types, "period1": int(time.time()) - HISTORY_YEARS * 365 * 86400, "period2": int(time.time())}).json()
    return parse_annual(code, payload)


def update_annual(today: date, codes: list[str], path: Path, days: int = 90) -> None:
    """Sundays: Yahoo annual results for `codes` (the companies SEC has no annual history for) that
    have none yet or were fetched more than `days` ago, upserted into the US annual history."""
    if today.weekday() != 6 and path.exists():
        return
    todo, rows = stale(path, codes, today, days), []
    for got in each(make_http, annual_series, todo, 2):
        rows += [r | {"fetched": today.isoformat()} for r in got or []]
    if rows:
        merge(path, pd.DataFrame(rows), ["code", "fy_end"])
    log.info("yahoo annual history: %d rows for %d of %d companies", len(rows), len({r["code"] for r in rows}), len(todo))


def parse_monthly(code: str, payload: dict, now: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Complete months only (code, month, close, ret) and splits (code, date, ratio). Yahoo divides closes
    before a split by its ratio; close here is as traded (the ratios of later splits multiplied back), so
    it matches the per-share book value reported at the time. ret is the month's total return (adjclose)."""
    res = payload["chart"]["result"][0]
    offset = timedelta(seconds=res["meta"].get("gmtoffset", 0), hours=12)  # bars start at local midnight; DST moves it an hour
    local = lambda ts: datetime.fromtimestamp(ts, timezone.utc) + offset
    df = pd.DataFrame({"month": [local(t).strftime("%Y-%m") for t in res.get("timestamp") or []],
                       "close": res["indicators"]["quote"][0]["close"], "adj": res["indicators"]["adjclose"][0]["adjclose"]})
    df = df.dropna().drop_duplicates("month")
    df = df[df["month"] < local(now or time.time()).strftime("%Y-%m")].reset_index(drop=True)  # the current month isn't over
    splits = pd.DataFrame([{"code": code, "date": local(s["date"]).date().isoformat(), "ratio": s["numerator"] / s["denominator"]}
                           for s in (res.get("events") or {}).get("splits", {}).values()], columns=["code", "date", "ratio"])
    for day, ratio in zip(splits["date"], splits["ratio"]):
        df.loc[df["month"] < day[:7], "close"] *= ratio
    df["ret"] = df["adj"] / df["adj"].shift(1) - 1
    return df.assign(code=code)[["code", "month", "close", "ret"]].round({"close": 4, "ret": 6}), splits


def monthly(client: Http, job: tuple[str, str, date]) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    code, symbol, start = job
    resp = client.get(URL.format(symbol=symbol), ok=(200, 404), params={
        "period1": int(datetime(start.year, start.month, 1, tzinfo=timezone.utc).timestamp()),
        "period2": int(time.time()), "interval": "1mo", "events": "div,split"})
    return parse_monthly(code, resp.json()) if resp.status_code == 200 else None


def update_monthly(today: date, market: str, codes: list[str], fx: set[str] = frozenset()) -> None:
    """Sundays (or when missing): months since each code's last stored one, ~11 years for new codes;
    the index under its price-table code and FX rates under their Yahoo symbols (e.g. HKDCNY=X).
    Saved every 300 codes, so an interrupted run keeps what it got."""
    path, (index_symbol, index_code, symbol) = Path(str(MONTHLY).format(market)), MARKETS[market]
    if path.exists() and today.weekday() != 6:
        return
    old = pd.read_csv(path, dtype={"code": str, "month": str}) if path.exists() else pd.DataFrame(columns=["code", "month"])
    last, done = old.groupby("code")["month"].max(), (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    first = date(today.year - HISTORY_YEARS, today.month, 1)
    jobs = [(c, symbol(c)) for c in codes] + [(index_code, index_symbol)] + [(f, f) for f in sorted(fx)]
    todo = [(c, s, date.fromisoformat(last[c] + "-01") if c in last else first) for c, s in jobs if last.get(c, "") < done]
    frames, splits, updated = [old], [], 0
    for i, got in enumerate(each(make_http, monthly, todo, 2), 1):
        if got:
            frames.append(got[0])
            splits.append(got[1])
            updated += 1
        if i % 300 == 0 or i == len(todo):
            frames = [pd.concat(frames).drop_duplicates(["code", "month"]).sort_values(["code", "month"])]  # stored months win
            write(frames[0], path)
            if splits:
                merge(Path(str(SPLITS).format(market)), pd.concat(splits), ["code", "date"])
                splits = []
            log.info("yahoo %s monthly: %d of %d", market, i, len(todo))
    log.info("yahoo %s monthly: %d of %d codes updated to %s", market, updated, len(todo), done)
