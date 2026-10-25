"""Free headlines for the results review (PLAN.md, "Results review"), one source per market, verified 2026-10-25:
CN and HK Eastmoney's per-stock news list (the 资讯 tab of its quote pages; market 1 = Shanghai, 0 = Shenzhen,
116 = HK), US Yahoo Finance's RSS feed per ticker. Titles only; nothing is stored but the day's review sources."""

import html
import re
import uuid
from datetime import date, timedelta
from email.utils import parsedate_to_datetime

from stockreport.fetch import Http

EM_LIST = "https://np-listapi.eastmoney.com/comm/web/getListInfo"
# Eastmoney's list is ~40% daily data items (margin balances, fund and Stock Connect flows, block trades, market
# roundups): not news about the company, and new every day, so they'd redo every cached review. Left out.
DATA_ITEMS = re.compile(r"融资(净偿还|净买入|净卖出|余额)|两融余额|融券余额|主力(资金|动向)|资金流向|资金风向标|特大单|大单净|北向资金|南向资金|"
                        r"港股通|沪股通|深股通|龙虎榜|大宗交易|成交活跃股|百元股|盘中(涨|跌)幅达|收评|午评|早盘|盘前速递|港股速报")
YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline"


def em_market(market: str, code: str) -> str:
    return f"116.{code}" if market == "hk" else f"{1 if code.startswith(('6', '9')) else 0}.{code}"


def parse_em(payload: dict, since: str) -> list[dict]:
    """Eastmoney's list: newest first, {date, title}; items before `since` dropped."""
    out = []
    for a in (payload.get("data") or {}).get("list") or []:
        day, title = str(a.get("Art_ShowTime") or "")[:10], " ".join(str(a.get("Art_Title") or "").split())
        if title and day >= since:
            out.append({"date": day, "title": title})
    return out


def parse_rss(text: str, since: str) -> list[dict]:
    """Yahoo's RSS items as {date, title}, newest first; items before `since` dropped."""
    out = []
    for item in re.findall(r"<item>(.*?)</item>", text, re.S):
        title, when = re.search(r"<title>(.*?)</title>", item, re.S), re.search(r"<pubDate>(.*?)</pubDate>", item)
        if not title or not when:
            continue
        day = parsedate_to_datetime(when.group(1)).date().isoformat()
        words = " ".join(html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", title.group(1))).split())
        if words and day >= since:
            out.append({"date": day, "title": words})
    return sorted(out, key=lambda x: x["date"], reverse=True)


def headlines(http: Http, market: str, code: str, today: date, days: int, limit: int) -> list[dict]:
    since = (today - timedelta(days=days)).isoformat()
    if market == "us":
        resp = http.get(YAHOO_RSS, params={"s": code.replace(".", "-"), "region": "US", "lang": "en-US"})
        found = parse_rss(resp.text, since)
    else:
        resp = http.get(EM_LIST, params={"client": "web", "biz": "web_stock_news", "type": "1", "pageSize": "50",
                                         "mTypeAndCode": em_market(market, code), "req_trace": uuid.uuid4().hex})
        found = parse_em(resp.json(), since)
    seen, out = set(), []
    for h in found:  # the same story from several outlets counts once
        if h["title"] not in seen and not DATA_ITEMS.search(h["title"]):
            seen.add(h["title"])
            out.append(h)
    return out[:limit]


def client(market: str) -> Http:
    """Eastmoney: at most ~2 requests a second (its rate limits). Yahoo answers 429 to a full browser User-Agent."""
    if market == "us":
        return Http(min_interval=0.3, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    return Http(min_interval=0.6, timeout=20, headers={"Referer": "https://quote.eastmoney.com/"})
