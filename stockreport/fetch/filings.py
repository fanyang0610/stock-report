"""Filings for the results review and its periodic-report passages: a stock's non-routine filings of the last 90 days (CNINFO,
HKEXnews, SEC's filing list), its latest periodic report (CN: CNINFO annual, half-year and quarterly reports; HK:
HKEXnews annual, interim and quarterly reports in English; US: the newest 10-K, 10-Q, 20-F or 40-F) and the text of
any filing. Documents are read in memory and never stored."""

import html
import io
import json
import logging
import re
from datetime import date, datetime, timedelta
from functools import cache

from stockreport.fetch import Http, cninfo, hkex, sec

log = logging.getLogger(__name__)
logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings on most filings; unreadable text is checked below
CN_PERIODIC = "category_ndbg_szsh;category_bndbg_szsh;category_yjdbg_szsh;category_sjdbg_szsh"
US_PERIODIC = ("10-K", "10-Q", "20-F", "40-F")
SKIP = re.compile(r"摘要|英文|取消|更正|補充|环境|環境|ESG|社會責任|社会责任|Environmental|Sustainab|Supplement", re.I)


@cache
def client(market: str) -> Http:
    return sec.make_http() if market == "us" else Http(min_interval=0.5, timeout=90)


@cache
def ids(market: str) -> dict:
    """Code -> the id the market's filing search needs (CNINFO orgId, HKEXnews stockId, SEC CIK)."""
    return {"cn": cninfo.org_ids, "hk": hkex.org_ids, "us": sec.org_ids}[market]()


def periodic(market: str, code: str, today: date) -> dict | None:
    """The newest periodic report of the last 400 days: {id, url, date, title}, or None."""
    sid, start = ids(market).get(code), today - timedelta(days=400)
    if sid is None:
        return None
    http = client(market)
    if market == "cn":
        found = http.post(cninfo.QUERY_URL, data={
            "stock": f"{code},{sid}", "tabName": "fulltext", "pageSize": 30, "pageNum": 1,
            "column": "sse" if code.startswith("6") else "szse", "category": CN_PERIODIC, "plate": "",
            "seDate": f"{start}~{today}", "searchkey": "", "secid": "", "trade": "", "sortName": "", "sortType": "",
            "isHLtitle": "false"}).json().get("announcements") or []
        for a in found:
            title = re.sub(r"<[^>]+>", "", a["announcementTitle"] or "")
            if not SKIP.search(title):
                return {"id": f"cn-{a['announcementId']}", "url": "http://static.cninfo.com.cn/" + a["adjunctUrl"],
                        "date": a["adjunctUrl"].split("/")[1], "title": title}
        return None
    if market == "hk":
        payload = http.get(hkex.SEARCH_URL, params={
            "sortDir": "0", "sortByOptions": "DateTime", "category": "0", "market": "SEHK", "stockId": sid,
            "documentType": "-1", "fromDate": f"{start:%Y%m%d}", "toDate": f"{today:%Y%m%d}", "title": "",
            "searchType": "1", "t1code": "40000", "t2Gcode": "-2", "t2code": "-2", "rowRange": "20", "lang": "en"}).json()
        for a in json.loads(payload["result"] or "[]"):  # English: many Chinese report PDFs have fonts without Unicode
            title, kind = html.unescape(a["TITLE"] or ""), html.unescape(a["LONG_TEXT"] or "").split(" - ", 1)[-1]
            if re.search(r"Annual Report|Interim|Quarterly", kind + title, re.I) and not SKIP.search(kind + title):
                day = a["DATE_TIME"][6:10] + "-" + a["DATE_TIME"][3:5] + "-" + a["DATE_TIME"][:2]
                return {"id": "hk-" + a["FILE_LINK"].rsplit("/", 1)[-1].split(".")[0], "date": day,
                        "url": "https://www1.hkexnews.hk" + a["FILE_LINK"], "title": " ".join(title.split())}
        return None
    recent = http.get(sec.SUBMISSIONS.format(cik=int(sid))).json()["filings"]["recent"]
    for form, day, acc, doc in zip(recent["form"], recent["filingDate"], recent["accessionNumber"], recent["primaryDocument"]):
        if form in US_PERIODIC and day >= start.isoformat():
            return {"id": f"us-{acc}", "date": day, "title": f"{form} {day}",
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(sid)}/{acc.replace('-', '')}/{doc}"}
    return None


def parse_cn(payload: dict) -> list[dict]:
    return [{"date": datetime.fromtimestamp(a["announcementTime"] / 1000, cninfo.BEIJING).date().isoformat(),
             "title": re.sub(r"<[^>]+>", "", a["announcementTitle"] or "").strip(),
             "url": "http://static.cninfo.com.cn/" + a["adjunctUrl"]} for a in payload.get("announcements") or []]


def parse_hk(items: list[dict]) -> list[dict]:
    return [{"date": datetime.strptime(a["DATE_TIME"], "%d/%m/%Y %H:%M").date().isoformat(),
             "title": " ".join(html.unescape(a.get("TITLE") or "").split()),
             "category": re.sub(r"<[^>]+>.*", "", html.unescape(a.get("LONG_TEXT") or "")).strip(),
             "url": "https://www1.hkexnews.hk" + a["FILE_LINK"]} for a in items]


def us_title(form: str, items: str, description: str) -> str:
    """'form: description': an 8-K's item names, else the form's name, else the filing's own description."""
    if form.startswith("8-K"):
        text = "; ".join(sec.ITEMS.get(i, f"Item {i}") for i in items.split(",") if i)
    else:
        text = sec.FORMS.get(form, description or "")
    return f"{form}: {text}" if text else form


def parse_us(payload: dict, cik: int) -> list[dict]:
    r = payload["filings"]["recent"]
    return [{"date": day, "form": form, "items": items, "title": us_title(form, items, desc),
             "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"}
            for form, day, items, acc, doc, desc in zip(r["form"], r["filingDate"], r["items"], r["accessionNumber"],
                                                        r["primaryDocument"], r["primaryDocDescription"])]


# An 8-K's Item 3.01 covers both a notice of delisting or of failing a listing rule and a company's own move to another
# exchange (Skydance, Nasdaq to the NYSE, 2026-09-25): the item's text tells them apart (the item's fixed heading,
# which names both, is skipped).
ITEM_301 = re.compile(r"(?is)Item\s*3\.01\.?\s*(?:Notice of Delisting or Failure to Satisfy a Continued Listing Rule or\s*"
                      r"Standard;?\s*Transfer of Listing\.?)?(.*?)(?=Item\s*\d\.\d\d|$)")
MOVED = re.compile(r"(?i)\b(?:transfer|mov)\w*\b[^.]{0,120}?\bto\s+(?:the\s+)?(?:New\s+York\s+Stock\s+Exchange|NYSE|Nasdaq)")
# any sign of a listing problem keeps the item a notice (a move offered as a cure, a hearing, a bid-price rule...)
FAILED = re.compile(r"(?i)deficien|complian|fail\w*\s+to\s+(?:satisfy|comply|meet|regain)|did\s+not\s+(?:comply|meet|satisfy)|"
                    r"no\s+longer\s+(?:meet|satisf)|delisting\s+determination|suspen|minimum|bid\s+price|hearing|panel|"
                    r"listing\s+rule|section\s+80\d|receiv\w*\s+(?:a\s+)?(?:written\s+)?(?:letter|notice|notification)|"
                    r"merger|form\s+25")


def listing_moved(body: str) -> bool:
    """True when an 8-K's Item 3.01 only moves the listing to another exchange, which is no delisting risk; any doubt
    (no readable text, a sign of a listing problem) keeps it a notice."""
    item = ITEM_301.search(body)
    return bool(item) and bool(MOVED.search(item.group(1))) and not FAILED.search(item.group(1))


def recent(market: str, code: str, today: date, days: int, routine: bool = False) -> list[dict]:
    """A stock's non-routine filings of the last `days` days, newest first: {date, kind, title, url}, classified by
    the filing rules (events.classify); with `routine`, the routine ones too (research reads director and auditor
    changes from their titles). None when the stock has no filing id."""
    from stockreport.events import classify
    sid, start, http = ids(market).get(code), today - timedelta(days=days), client(market)
    if sid is None:
        return None
    if market == "cn":
        rows, page = [], 1
        while page <= 5:  # 30 a page; large issuers file ~100 a quarter, most of them routine
            payload = http.post(cninfo.QUERY_URL, data={
                "stock": f"{code},{sid}", "tabName": "fulltext", "pageSize": 30, "pageNum": page,
                "column": "sse" if code.startswith("6") else "szse", "category": "", "plate": "",
                "seDate": f"{start}~{today}", "searchkey": "", "secid": "", "trade": "", "sortName": "", "sortType": "",
                "isHLtitle": "false"}).json()
            rows += parse_cn(payload)
            if not payload.get("hasMore"):
                break
            page += 1
    elif market == "hk":
        payload = http.get(hkex.SEARCH_URL, params={
            "sortDir": "0", "sortByOptions": "DateTime", "category": "0", "market": "SEHK", "stockId": sid,
            "documentType": "-1", "fromDate": f"{start:%Y%m%d}", "toDate": f"{today:%Y%m%d}", "title": "",
            "searchType": "0", "t1code": "-2", "t2Gcode": "-2", "t2code": "-2", "rowRange": "300", "lang": "zh"}).json()
        rows = parse_hk(json.loads(payload["result"] or "[]"))
    else:
        rows = [r for r in parse_us(http.get(sec.SUBMISSIONS.format(cik=int(sid))).json(), int(sid))
                if r["date"] >= start.isoformat()]
        for r in rows:  # a move to another exchange under Item 3.01 isn't a delisting notice (one more read, rare)
            if r["form"].startswith("8-K") and "3.01" in r["items"].split(",") and listing_moved(body(r["url"])):
                r["items"] = ",".join(i for i in r["items"].split(",") if i != "3.01")
                r["title"] = r["title"].replace(sec.ITEMS["3.01"], "Transfer of listing to another exchange")
    out, seen = [], set()
    for r in rows:
        kind = classify(market, r)
        if (routine or kind != "routine") and (r["date"], r["title"]) not in seen:
            seen.add((r["date"], r["title"]))
            out.append({"date": r["date"], "kind": kind, "title": r["title"], "url": r["url"]})
    return sorted(out, key=lambda r: r["date"], reverse=True)


def body(url: str) -> str:
    """A US filing's text, '' when it can't be read (the filing then stays as filed)."""
    try:
        return text("us", url)
    except Exception as e:
        log.warning("%s: %s", url, e)
        return ""


def html_text(markup: str) -> str:
    """Visible text of an HTML filing (inline XBRL's hidden header, scripts and styles removed)."""
    markup = re.sub(r"(?is)<(script|style|ix:header)\b.*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader  # CN and HK filings are PDFs; scanned ones have no text and are skipped
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def readable(text: str) -> bool:
    """False for PDF text from fonts without a Unicode map (mojibake in unrelated scripts instead of Chinese)."""
    chars = re.sub(r"\s", "", text)
    good = re.findall(r"[\x21-\x7e\u00a0-\u024f\u2000-\u206f\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]", chars)
    return len(chars) >= 500 and len(good) / len(chars) >= 0.9


def text(market: str, url: str) -> str:
    """The filing's text, or '' when it has none that can be read (scanned, or fonts without a Unicode map)."""
    resp = client(market).get(url)
    if resp.content[:5] == b"%PDF-":
        found = pdf_text(resp.content)
    else:
        found = html_text(resp.content.decode(resp.encoding or "utf-8", errors="replace"))
    return found if readable(found) else ""
