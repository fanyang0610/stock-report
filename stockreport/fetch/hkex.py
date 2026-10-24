"""HKEXnews (www1.hkexnews.hk): recent announcement titles for HK stocks, used as context for the
AI notes (PLAN.md Method section 8). Nothing is stored; titles are fetched when notes are written. Also each
stock's board lot from HKEX's daily List of Securities (the cards' cost of one lot), weekly."""

import html
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta

import pandas as pd

from stockreport.config import DATA
from stockreport.fetch import Http, write

STOCKS_URL = "https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_c.json"  # every SEHK security with its stockId
SEARCH_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
# Routine filings: next-day disclosure and monthly returns, share awards, board lists, letters and
# forms to holders, governance rules (A+H issuers repost every A-share filing as an "overseas
# regulatory announcement") and the placeholder for an English-only announcement.
ROUTINE = re.compile(r"翌日披露報表|月報表|股份計劃|董事名單|董事會召開日期|通知信函|回條|表格|制度|辦法|規定|英文版面"
                     r"|^公告$|^海外監管公告$")
http = Http(min_interval=0.5)
LOTS_URL = "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx"
LOTS = DATA / "fundamentals" / "hk_lots.csv.gz"
SHEET = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def parse_lots(xlsx: bytes) -> pd.DataFrame:
    """Stock code and board lot of every equity in HKEX's List of Securities (columns A, C and E of its one sheet,
    inline strings; read with the standard library, no Excel package)."""
    rows = []
    for row in ET.fromstring(zipfile.ZipFile(io.BytesIO(xlsx)).read("xl/worksheets/sheet1.xml")).iterfind(".//x:row", SHEET):
        cells = {"".join(ch for ch in c.get("r") if ch.isalpha()): "".join(c.itertext()) for c in row.iterfind("x:c", SHEET)}
        if cells.get("C") == "Equity" and cells.get("E", "").replace(",", "").isdigit():
            rows.append((cells["A"], int(cells["E"].replace(",", ""))))
    return pd.DataFrame(rows, columns=["code", "lot"])


def update_lots(today: date) -> None:
    if LOTS.exists() and (today - date.fromtimestamp(LOTS.stat().st_mtime)).days < 7:
        return
    lots = parse_lots(http.get(LOTS_URL).content)
    if len(lots) < 2000:
        raise RuntimeError(f"only {len(lots)} board lots in HKEX's list")
    write(lots, LOTS)


def load_lots() -> pd.Series:
    return pd.read_csv(LOTS, dtype={"code": str}).set_index("code")["lot"] if LOTS.exists() else pd.Series(dtype=float)


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
