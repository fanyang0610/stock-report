"""CNINFO (www.cninfo.com.cn): recent announcement titles for CN stocks, used as context for the
AI notes (PLAN.md Method section 8). Nothing is stored; titles are fetched when notes are written."""

import re
from datetime import date, datetime, timedelta, timezone

from stockreport.fetch import Http

STOCKS_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"  # every A-share with its CNINFO orgId
QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
# Routine filings that say nothing about the business (H-share forms, legal opinions, English copies).
ROUTINE = re.compile(r"翌日披露报表|证券变动月报表|董事会会议召开日期|法律意见|核查意见|英文版|摘要$")
BEIJING = timezone(timedelta(hours=8))
http = Http(min_interval=0.5)


def org_ids() -> dict[str, str]:
    """A-share code -> CNINFO orgId (needed by the announcement query)."""
    return {s["code"]: s["orgId"] for s in http.get(STOCKS_URL).json()["stockList"]}


def parse_titles(payload: dict, limit: int) -> list[str]:
    """Newest-first 'YYYY-MM-DD title' lines, routine filings and duplicates dropped."""
    out, seen = [], set()
    for a in payload.get("announcements") or []:
        title = re.sub(r"<[^>]+>", "", a.get("announcementTitle") or "").strip()
        if not title or title in seen or ROUTINE.search(title):
            continue
        seen.add(title)
        day = datetime.fromtimestamp(a["announcementTime"] / 1000, BEIJING).date().isoformat()
        out.append(f"{day} {title}")
        if len(out) >= limit:
            break
    return out


def titles(code: str, org_id: str, today: date, days: int = 60, limit: int = 10) -> list[str]:
    start = (today - timedelta(days=days)).isoformat()
    payload = http.post(QUERY_URL, data={
        "stock": f"{code},{org_id}", "tabName": "fulltext", "pageSize": 30, "pageNum": 1,
        "column": "sse" if code.startswith("6") else "szse", "category": "", "plate": "",
        "seDate": f"{start}~{today.isoformat()}", "searchkey": "", "secid": "", "trade": "",
        "sortName": "", "sortType": "", "isHLtitle": "false"}).json()
    return parse_titles(payload, limit)
