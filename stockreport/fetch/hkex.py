"""HKEXnews (www1.hkexnews.hk): recent announcement titles for HK stocks, used as context for the
AI notes (PLAN.md Method section 8). Nothing is stored; titles are fetched when notes are written."""

import html
import json
import re
from datetime import date, datetime, timedelta

from stockreport.fetch import Http

STOCKS_URL = "https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_c.json"  # every SEHK security with its stockId
SEARCH_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
# Routine filings: next-day disclosure and monthly returns, share awards, board lists, letters and
# forms to holders, governance rules (A+H issuers repost every A-share filing as an "overseas
# regulatory announcement") and the placeholder for an English-only announcement.
ROUTINE = re.compile(r"翌日披露報表|月報表|股份計劃|董事名單|董事會召開日期|通知信函|回條|表格|制度|辦法|規定|英文版面"
                     r"|^公告$|^海外監管公告$")
http = Http(min_interval=0.5)


def org_ids() -> dict[str, int]:
    """HK code -> HKEXnews stockId (needed by the title search)."""
    return {s["c"]: s["i"] for s in http.get(STOCKS_URL).json()}


def parse_titles(items: list[dict], limit: int) -> list[str]:
    """Newest-first 'YYYY-MM-DD title' lines, routine filings and duplicates dropped. The search
    returns its rows as a JSON string inside the JSON reply."""
    out, seen = [], set()
    for a in items:
        title = " ".join(html.unescape(a.get("TITLE") or "").split()).removeprefix("海外監管公告 - ")
        kind = a.get("LONG_TEXT") or ""
        if not title or title in seen or ROUTINE.search(title) or ROUTINE.search(kind):
            continue
        seen.add(title)
        out.append(f"{datetime.strptime(a['DATE_TIME'], '%d/%m/%Y %H:%M').date().isoformat()} {title}")
        if len(out) >= limit:
            break
    return out


def titles(code: str, stock_id: int, today: date, days: int = 60, limit: int = 10) -> list[str]:
    payload = http.get(SEARCH_URL, params={
        "sortDir": "0", "sortByOptions": "DateTime", "category": "0", "market": "SEHK", "stockId": stock_id,
        "documentType": "-1", "fromDate": f"{today - timedelta(days=days):%Y%m%d}", "toDate": f"{today:%Y%m%d}",
        "title": "", "searchType": "0", "t1code": "-2", "t2Gcode": "-2", "t2code": "-2", "rowRange": "50", "lang": "zh"}).json()
    return parse_titles(json.loads(payload["result"] or "[]"), limit)
