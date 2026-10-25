"""HKEXnews (www1.hkexnews.hk): the stockIds and the title search that fetch/filings.py reads a stock's filings
with. Also each stock's board lot from HKEX's daily List of Securities (the cards' cost of one lot), weekly."""

import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import date

import pandas as pd

from stockreport.config import DATA
from stockreport.fetch import Http, write

STOCKS_URL = "https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_c.json"  # every SEHK security with its stockId
SEARCH_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
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

