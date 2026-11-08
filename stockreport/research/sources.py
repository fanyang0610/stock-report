"""Yahoo for any market (query1.finance.yahoo.com, via fetch/yahoo.py's client): the annual fundamentals timeseries (the
second source of the fact sheet's reported figures, financial-data's two-source rule; the first source where Eastmoney
has no statements, e.g. HK REITs), quoteSummary (the street's targets and ratings, estimates, earnings surprises, the
calendar, short interest and insider activity), and daily (2 years) and monthly (11 years, as traded) prices."""

import time
from datetime import date, timedelta

import pandas as pd

from stockreport.fetch import yahoo
from stockreport.research import num

INDEX = {"cn": ("510300.SS", "510300"), "us": ("^GSPC", "SPX"), "hk": ("^HSI", "HSI")}  # CN: the CSI 300 fund (Yahoo's index bars have no volume)
SECOND = {"revenue": "TotalRevenue", "gp": "GrossProfit", "op_income": "OperatingIncome", "ni": "NetIncomeCommonStockholders",
          "ocf": "OperatingCashFlow", "capex": "CapitalExpenditure", "equity": "StockholdersEquity", "assets": "TotalAssets",
          "liabilities": "TotalLiabilitiesNetMinorityInterest", "debt": "TotalDebt",
          "cash": "CashCashEquivalentsAndShortTermInvestments", "shares": "OrdinarySharesNumber",
          "pretax": "PretaxIncome", "interest": "InterestExpense", "da": "DepreciationAndAmortization",
          "receivables": "AccountsReceivable", "inventory": "Inventory", "cur_assets": "CurrentAssets",
          "cur_liab": "CurrentLiabilities", "retained": "RetainedEarnings", "div_paid": "CashDividendsPaid",
          "buyback": "RepurchaseOfCapitalStock", "sga": "SellingGeneralAndAdministration", "ppe": "NetPPE",
          "lt_debt": "LongTermDebt", "goodwill": "Goodwill", "eps": "DilutedEPS"}
SUMMARY_MODULES = ("financialData,recommendationTrend,earningsTrend,earningsHistory,calendarEvents,defaultKeyStatistics,"
                   "summaryDetail,netSharePurchaseActivity,upgradeDowngradeHistory,assetProfile")


def tencent(market: str, code: str) -> dict:
    """Tencent's live quote (qt.gtimg.cn, every market): price and market value in the quote currency, the second
    source of Yahoo's and Eastmoney's."""
    prefix = {"hk": "hk", "us": "us"}.get(market) or ("sh" if code.startswith(("6", "9")) else
                                                      "bj" if code.startswith(("4", "8", "92")) else "sz")
    text = yahoo.make_http().get(f"https://qt.gtimg.cn/q={prefix}{code}").content.decode("gbk", "replace")
    v = text.split('"')[1].split("~") if '"' in text else []
    return {"price": num(v[3]), "mcap": (num(v[45]) or 0) * 1e8 or None, "time": v[30]} if len(v) > 45 else {}


def symbol(market: str, code: str) -> str:
    return yahoo.MARKETS[market][2](code)


def parse_annual(payload: dict) -> pd.DataFrame:
    """Fiscal years (period, currency) x SECOND's keys; outflows (capex, dividends, buybacks) as positive amounts."""
    by = {}
    for item in payload["timeseries"]["result"]:
        name = item["meta"]["type"][0]
        key = next((k for k, t in SECOND.items() if "annual" + t == name), None)
        for v in item.get(name) or []:
            if v and key:
                row = by.setdefault(v["asOfDate"], {"period": v["asOfDate"], "currency": v.get("currencyCode")})
                val = v["reportedValue"]["raw"]
                row[key] = abs(val) if key in ("capex", "div_paid", "buyback") else val
    return pd.DataFrame([by[k] for k in sorted(by)]).assign(months=12)


def annual(market: str, code: str) -> pd.DataFrame:
    types = ",".join("annual" + t for t in SECOND.values())
    payload = yahoo.make_http().get(yahoo.TIMESERIES.format(symbol=symbol(market, code)), params={
        "type": types, "period1": int(time.time()) - 11 * 365 * 86400, "period2": int(time.time())}).json()
    return parse_annual(payload)


def raw(d, key):
    v = (d or {}).get(key)
    return v.get("raw") if isinstance(v, dict) else v


def parse_summary(payload: dict, today: date) -> dict:
    """The street's view and the market facts quoteSummary carries; None where Yahoo has nothing."""
    res = (payload.get("quoteSummary", {}).get("result") or [{}])[0]
    fd, ks, sd = res.get("financialData", {}), res.get("defaultKeyStatistics", {}), res.get("summaryDetail", {})
    trend = {t["period"]: t for t in res.get("earningsTrend", {}).get("trend", [])}
    est = {p: {"end": t.get("endDate"), "eps": raw(t.get("earningsEstimate"), "avg"), "eps_low": raw(t.get("earningsEstimate"), "low"),
               "eps_high": raw(t.get("earningsEstimate"), "high"), "analysts": raw(t.get("earningsEstimate"), "numberOfAnalysts"),
               "revenue": raw(t.get("revenueEstimate"), "avg"), "eps_90d": raw(t.get("epsTrend"), "90daysAgo")}
           for p, t in trend.items() if p in ("0y", "+1y")}
    rec = (res.get("recommendationTrend", {}).get("trend") or [{}])[0]
    since = (today - timedelta(days=180)).isoformat()
    moves = [m for m in res.get("upgradeDowngradeHistory", {}).get("history", [])
             if date.fromtimestamp(m.get("epochGradeDate", 0)).isoformat() >= since]
    cal = res.get("calendarEvents", {})
    nsp = res.get("netSharePurchaseActivity", {})
    profile = res.get("assetProfile", {})
    return {
        "currency": raw(sd, "currency") or raw(fd, "financialCurrency"), "report_currency": raw(fd, "financialCurrency"),
        "target_mean": raw(fd, "targetMeanPrice"), "target_median": raw(fd, "targetMedianPrice"),
        "target_high": raw(fd, "targetHighPrice"), "target_low": raw(fd, "targetLowPrice"),
        "rec_mean": raw(fd, "recommendationMean"), "rec_key": raw(fd, "recommendationKey"),
        "analysts": raw(fd, "numberOfAnalystOpinions"),
        "ratings": {k: rec.get(k) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")} if rec else None,
        "estimates": est, "est_currency": ((trend.get("0y") or {}).get("earningsEstimate") or {}).get("earningsCurrency"),
        "surprises": [{"quarter": raw(h, "quarter") and date.fromtimestamp(raw(h, "quarter")).isoformat(),
                       "actual": raw(h, "epsActual"), "estimate": raw(h, "epsEstimate")}
                      for h in res.get("earningsHistory", {}).get("history", [])],
        "next_earnings": [d.get("fmt") for d in cal.get("earnings", {}).get("earningsDate", [])][:1],
        "ex_dividend": (cal.get("exDividendDate") or {}).get("fmt"),
        "beta": raw(ks, "beta"), "short_float": raw(ks, "shortPercentOfFloat"), "short_ratio": raw(ks, "shortRatio"),
        "insiders": raw(ks, "heldPercentInsiders"), "institutions": raw(ks, "heldPercentInstitutions"),
        "float_shares": raw(ks, "floatShares"), "market_cap": raw(sd, "marketCap"),
        "high_52w": raw(sd, "fiftyTwoWeekHigh"), "low_52w": raw(sd, "fiftyTwoWeekLow"),
        "insider_buys_6m": raw(nsp, "buyInfoCount"), "insider_sells_6m": raw(nsp, "sellInfoCount"),
        "insider_net_shares_6m": raw(nsp, "netInfoShares"),
        "upgrades_6m": sum(m.get("action") == "up" for m in moves), "downgrades_6m": sum(m.get("action") == "down" for m in moves),
        "target_moves_6m": [{"date": date.fromtimestamp(m["epochGradeDate"]).isoformat(), "firm": m.get("firm"),
                             "grade": m.get("toGrade"), "action": m.get("action"), "target": m.get("currentPriceTarget")}
                            for m in moves[:10]],
        "sector": profile.get("sector"), "industry": profile.get("industry"), "employees": profile.get("fullTimeEmployees"),
        "business": (profile.get("longBusinessSummary") or "")[:600]}


def summary(market: str, code: str, today: date) -> dict:
    http = yahoo.crumb_http()
    resp = http.get(yahoo.SUMMARY.format(symbol=symbol(market, code)), ok=(200, 404),
                    params={"modules": SUMMARY_MODULES, "crumb": http.crumb})
    return parse_summary(resp.json() if resp.status_code == 200 else {}, today)


def prices(market: str, code: str, today: date) -> dict[str, pd.DataFrame]:
    """Two years of daily closes for the stock and its market's index, 11 years of monthly closes as traded with the
    splits, and 11 years of dividends (split-adjusted, by ex-date) (Yahoo's chart API)."""
    http, start = yahoo.make_http(), today - timedelta(days=731)
    daily, _ = yahoo.chart(http, (code, symbol(market, code), start)) or (None, None)
    if daily is None or daily.empty:
        raise RuntimeError(f"no Yahoo prices for {code}")
    index, _ = yahoo.chart(http, (INDEX[market][1], INDEX[market][0], start))
    first = int(time.mktime(date(today.year - 11, today.month, 1).timetuple()))
    payload = http.get(yahoo.URL.format(symbol=symbol(market, code)), params={
        "period1": first, "period2": int(time.time()), "interval": "1mo", "events": "div,split"}).json()
    monthly, splits = yahoo.parse_monthly(code, payload)
    res = payload["chart"]["result"][0]
    divs = pd.DataFrame([{"code": code, "ex_date": date.fromtimestamp(d["date"]).isoformat(), "dps": d["amount"]}
                         for d in (res.get("events") or {}).get("dividends", {}).values()], columns=["code", "ex_date", "dps"])
    since = res["meta"].get("firstTradeDate")
    listed = date.fromtimestamp(since).isoformat() if since else None
    return {"daily": pd.concat([daily, index]), "dividends": divs, "monthly": monthly.assign(listed=listed), "splits": splits}


def price_facts(daily: pd.DataFrame, code: str, index_code: str) -> dict:
    """Last close and its date, the 52-week range, returns against the index over 1, 3, 6 and 12 months, volatility
    and beta (weekly returns, 2 years), the worst fall from a high in the last year, and news-pulse's unusual moves
    in the last 90 days: a day of 5% or more, or 10% or more over 5 trading days (with the index's move)."""
    px = daily.pivot_table(index="date", columns="code", values="close").sort_index()
    ret = (daily.assign(r=daily["close"] / daily["prev_close"] - 1).pivot_table(index="date", columns="code", values="r")
           .reindex(px.index))
    s, ix = ret[code].dropna(), ret[index_code].reindex(ret[code].dropna().index).fillna(0)
    last = px[code].dropna()
    year = last[last.index >= (pd.Timestamp(last.index[-1]) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")]
    growth = lambda r, n: float((1 + r.tail(n)).prod() - 1) if len(r) >= n else None
    weekly = lambda r: (1 + r).groupby(pd.to_datetime(r.index).to_period("W")).prod() - 1
    ws, wi = weekly(s.tail(504)), weekly(ix.tail(504))
    out = {"close": float(last.iloc[-1]), "date": last.index[-1], "high_52w": float(year.max()), "low_52w": float(year.min()),
           "drawdown_1y": float((year / year.cummax() - 1).min()), "vol_1y": float(s.tail(252).std() * 252 ** 0.5),
           "beta_2y": float(ws.cov(wi) / wi.var()) if len(ws) > 26 else None}
    for months, n in ((1, 21), (3, 63), (6, 126), (12, 252)):
        r, i = growth(s, n), growth(ix, n)
        out[f"ret_{months}m"], out[f"rel_{months}m"] = r, None if r is None or i is None else r - i
    recent, moves = s.tail(63), []
    five, five_ix = (1 + s).rolling(5).apply(lambda x: x.prod()) - 1, (1 + ix).rolling(5).apply(lambda x: x.prod()) - 1
    for day in recent.index:
        if abs(recent[day]) >= 0.05:
            moves.append({"date": day, "days": 1, "move": float(recent[day]), "index": float(ix[day])})
        elif abs(five[day]) >= 0.10 and not any(m["date"] >= ret.index[max(0, ret.index.get_loc(day) - 4)] for m in moves):
            moves.append({"date": day, "days": 5, "move": float(five[day]), "index": float(five_ix[day])})
    return out | {"moves_90d": moves}


def dividend_years(divs: pd.DataFrame) -> dict[str, float]:
    """Dividends per share a year (Yahoo's split-adjusted amounts, by the calendar year they went ex), annualized as the
    year's average payment x the usual number of payments: a monthly payer's ex-dates around New Year put 11 or 13 in a
    calendar year (Realty Income 2024 and 2025), and the window's first year is partial."""
    if divs is None or divs.empty:
        return {}
    g = divs.groupby(divs["ex_date"].str[:4])["dps"]
    usual = min((1, 2, 3, 4, 12), key=lambda n: abs(n - g.size().median()))  # the payment schedule: yearly ... monthly
    return {str(k): float(v) for k, v in (g.mean() * usual).items()}


def eps_years(estimates: dict) -> dict[str, float]:
    """Yahoo's current (0y) and next (+1y) fiscal year EPS keyed by the fiscal year's end year; +1y is the year after
    0y (Yahoo sometimes repeats 0y's end date for it: AAPL, 2026-11-08)."""
    e0, e1 = estimates.get("0y") or {}, estimates.get("+1y") or {}
    if not e0.get("end"):
        return {}
    year = int(e0["end"][:4])
    return {str(y): num(e["eps"]) for y, e in ((year, e0), (year + 1, e1)) if num(e.get("eps")) is not None}
