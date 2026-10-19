"""Filings for the deep-dive lane (PLAN.md Method 15): a stock's latest periodic report (CN: CNINFO annual,
half-year and quarterly reports; HK: HKEXnews annual, interim and quarterly reports in English; US: the newest 10-K, 10-Q,
20-F or 40-F in SEC's filing list) and the text of any filing. Documents are read in memory and never stored."""

import html
import io
import json
import logging
import re
from datetime import date, timedelta
from functools import cache

from stockreport.fetch import Http, cninfo, hkex, sec

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
