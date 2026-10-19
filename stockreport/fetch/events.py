"""Market-wide daily announcement feeds for the event layer (PLAN.md Method 14): CNINFO's whole-market query
(~45 pages a day), HKEXnews' title search for all stocks (one call a day, with HKEX's own headline categories)
and SEC full-text search (8-K items, merger and tender forms, periodic reports; ~3-10 calls a day). Each filing
becomes one row (date, code, kind, title, url), classified by rules (stockreport/events.py); routine filings are
dropped. Kept in data/events/<market>.csv.gz for `keep_days`; the newest fetched day is asked again."""

import html
import json
import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta

import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import Http, cninfo, hkex, sec, write

log = logging.getLogger(__name__)
EVENTS = DATA / "events"
COLUMNS = ["date", "code", "kind", "title", "url"]
EFTS = "https://efts.sec.gov/LATEST/search-index"
US_FORMS = ["8-K", "6-K",  # root forms: the search adds their amendments (/A)
            "10-K", "10-Q", "20-F", "40-F", "SC TO-T", "SC TO-I", "SC 14D9", "PREM14A",
            "DEFM14A", "S-4", "NT 10-K", "NT 10-Q", "15-12B", "25-NSE"]


def cn_day(http: Http, day: str) -> list[dict]:
    """Every A-share announcement published on `day` (pages of 30)."""
    rows, page = [], 1
    while True:
        payload = http.post(cninfo.QUERY_URL, data={
            "stock": "", "tabName": "fulltext", "pageSize": 30, "pageNum": page, "column": "szse", "category": "",
            "plate": "", "seDate": f"{day}~{day}", "searchkey": "", "secid": "", "trade": "", "sortName": "",
            "sortType": "", "isHLtitle": "false"}).json()
        for a in payload.get("announcements") or []:
            rows.append({"date": datetime.fromtimestamp(a["announcementTime"] / 1000, cninfo.BEIJING).date().isoformat(),
                         "code": a["secCode"], "title": re.sub(r"<[^>]+>", "", a["announcementTitle"] or "").strip(),
                         "category": "", "url": "http://static.cninfo.com.cn/" + a["adjunctUrl"]})
        if not payload.get("hasMore") or page >= 200:
            return rows
        page += 1


def hk_search(http: Http, day: str, lang: str) -> list[dict]:
    d = day.replace("-", "")
    payload = http.get(hkex.SEARCH_URL, params={
        "sortDir": "0", "sortByOptions": "DateTime", "category": "0", "market": "SEHK", "stockId": "-1",
        "documentType": "-1", "fromDate": d, "toDate": d, "title": "", "searchType": "0", "t1code": "-2",
        "t2Gcode": "-2", "t2code": "-2", "rowRange": "5000", "lang": lang}).json()
    return json.loads(payload["result"] or "[]")


def hk_day(http: Http, day: str) -> list[dict]:
    """Every SEHK filing on `day`; a filing for several stocks becomes one row per stock. Titles and categories
    are the Chinese ones; the link is the English version (same stock and minute, 99% unique) when there is one,
    since many Chinese PDFs have fonts without a Unicode map and can't be read by the deep-dive lane."""
    chinese, english = hk_search(http, day, "zh"), {}
    for a in hk_search(http, day, "en"):
        english.setdefault((a["STOCK_CODE"], a["DATE_TIME"]), []).append(a["FILE_LINK"])
    twins = Counter((a["STOCK_CODE"], a["DATE_TIME"]) for a in chinese)
    rows = []
    for a in chinese:
        key = (a["STOCK_CODE"], a["DATE_TIME"])
        link = english[key][0] if twins[key] == 1 and len(english.get(key, [])) == 1 else a["FILE_LINK"]
        title = " ".join(html.unescape(a.get("TITLE") or "").split())
        category = re.sub(r"<[^>]+>.*", "", html.unescape(a.get("LONG_TEXT") or "")).strip()
        when = datetime.strptime(a["DATE_TIME"], "%d/%m/%Y %H:%M").date().isoformat()
        for code in (a.get("STOCK_CODE") or "").split("<br/>"):
            rows.append({"date": when, "code": code.strip(), "title": title, "category": category,
                         "url": "https://www1.hkexnews.hk" + link})
    return rows


def us_title(src: dict) -> str:
    """'form: description' as in the notes' SEC titles (8-K item names, else the form's name)."""
    form = src.get("form") or ""
    if form.startswith("8-K"):
        text = "; ".join(sec.ITEMS.get(i, f"Item {i}") for i in src.get("items") or [])
    else:
        text = sec.FORMS.get(form, src.get("file_description") or "")
    return f"{form}: {text}" if text else form


def us_day(http: Http, day: str, tickers: dict[int, list[str]]) -> list[dict]:
    """SEC filings of the chosen forms on `day`, for the companies in the ticker list (pages of 100)."""
    rows, start = [], 0
    while True:
        hits = http.get(EFTS, params={"forms": ",".join(US_FORMS), "startdt": day, "enddt": day,
                                      "from": start}).json()["hits"]["hits"]
        for h in hits:
            src, (adsh, doc) = h["_source"], h["_id"].split(":", 1)
            for cik in src.get("ciks") or []:
                for code in tickers.get(int(cik), []):
                    rows.append({"date": src["file_date"], "code": code, "title": us_title(src), "category": "",
                                 "items": ",".join(src.get("items") or []), "form": src.get("form"),
                                 "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{doc}"})
        if len(hits) < 100 or start >= 9900:
            return rows
        start += 100


def load(market: str) -> pd.DataFrame:
    path = EVENTS / f"{market}.csv.gz"
    return pd.read_csv(path, dtype=str) if path.exists() else pd.DataFrame(columns=COLUMNS)


def update(market: str, today: date) -> None:
    """Fetch the days since the newest one in the table (that day again: it may have been partial), at most
    `backfill_days` back, classify, and keep `keep_days`."""
    from stockreport.events import classify
    cfg, old = CONFIG["events"], load(market)
    first = (today - timedelta(days=cfg["backfill_days"])).isoformat()
    start = max(old["date"].max(), first) if len(old) else first
    days = [d.date().isoformat() for d in pd.date_range(start, today)]
    if market == "us":
        http = sec.make_http()
        tickers = sec.load_ciks().reset_index().groupby("cik")["code"].apply(list).to_dict()
        fetch = lambda d: us_day(http, d, tickers)
    else:
        http = Http(min_interval=0.5)
        fetch = lambda d: (cn_day if market == "cn" else hk_day)(http, d)
    new = []
    for day in days:
        got = pd.DataFrame(fetch(day))
        if len(got):
            got["kind"] = [classify(market, r) for r in got.to_dict("records")]
            new.append(got[got["kind"] != "routine"][COLUMNS])
        log.info("%s events %s: %d filings", market.upper(), day, len(got))
    keep = (today - timedelta(days=cfg["keep_days"])).isoformat()
    df = pd.concat([old[old["date"] < start], *new]).drop_duplicates(["date", "code", "title", "url"])
    write(df[df["date"] >= keep].sort_values(["date", "code"]), EVENTS / f"{market}.csv.gz")
