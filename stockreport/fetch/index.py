"""The index funds' own indexes, the buy lists' parent (PLAN.md, "Lists"): the CSI 300's constituent weights from China
Securities Index's month-end file (510300 tracks it) and the S&P 500's from SPY's daily holdings file (State Street),
read daily (two small files; a failed read keeps the last one). HK has no free current file for the Hang Seng Index
(the Tracker Fund's holdings file on State Street's site stopped in 2022): its parent is the largest by HK-listed value
(lists.parent)."""

import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime

import pandas as pd
import xlrd

from stockreport.config import DATA
from stockreport.fetch import Http, write

URLS = {"cn": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/closeweight/000300closeweight.xls",
        "us": "https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"}
WEIGHTS = DATA / "fundamentals" / "{}_index.csv.gz"  # code, weight (share of the index), date
SHEET = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
http = Http(min_interval=1.0)
http.client.follow_redirects = True  # State Street moves its file paths


def parse_csi(content: bytes) -> pd.DataFrame:
    """CSI's weight file: one row per constituent, the date first, the code fifth, the weight in % last."""
    sheet = xlrd.open_workbook(file_contents=content).sheet_by_index(0)
    rows = [sheet.row_values(i) for i in range(1, sheet.nrows)]
    day = lambda x: datetime.strptime(str(x)[:8], "%Y%m%d").date().isoformat()
    return pd.DataFrame({"code": [str(r[4]).zfill(6) for r in rows], "weight": [float(r[-1]) / 100 for r in rows],
                         "date": [day(r[0]) for r in rows]})


def xlsx_rows(content: bytes) -> list[list[str]]:
    """The first sheet's rows as text (shared strings resolved), with the standard library: no Excel package."""
    book = zipfile.ZipFile(io.BytesIO(content))
    shared = [] if "xl/sharedStrings.xml" not in book.namelist() else [
        "".join(si.itertext()) for si in ET.fromstring(book.read("xl/sharedStrings.xml")).iterfind("x:si", SHEET)]
    text = lambda c: shared[int(c.findtext("x:v", "0", SHEET))] if c.get("t") == "s" else "".join(c.itertext())
    return [[text(c) for c in row.iterfind("x:c", SHEET)]
            for row in ET.fromstring(book.read("xl/worksheets/sheet1.xml")).iterfind(".//x:row", SHEET)]


def parse_spy(content: bytes) -> pd.DataFrame:
    """SPY's holdings: an 'As of' line, then Name, Ticker, Identifier, SEDOL, Weight (%)...; cash lines have no ticker."""
    rows = xlsx_rows(content)
    day = next(datetime.strptime(r[1].split("As of ")[-1], "%d-%b-%Y").date().isoformat() for r in rows
               if r and r[0].startswith("Holdings"))
    start = next(i for i, r in enumerate(rows) if r[:2] == ["Name", "Ticker"]) + 1
    held = [(r[1].strip(), float(r[4])) for r in rows[start:] if len(r) > 4 and r[1].strip() not in ("", "-")
            and r[4].replace(".", "", 1).isdigit()]
    return pd.DataFrame({"code": [c for c, _ in held], "weight": [w / 100 for _, w in held], "date": day})


def update(market: str) -> None:
    df = (parse_csi if market == "cn" else parse_spy)(http.get(URLS[market]).content)
    if len(df) < {"cn": 290, "us": 490}[market] or not 0.97 <= df["weight"].sum() <= 1.01:
        raise RuntimeError(f"{market} index file: {len(df)} names, weights sum to {df['weight'].sum():.1%}")
    write(df, WEIGHTS.with_name(WEIGHTS.name.format(market)))


def load(market: str) -> pd.Series:
    """Code -> share of the index (empty without a file)."""
    path = WEIGHTS.with_name(WEIGHTS.name.format(market))
    return pd.read_csv(path, dtype={"code": str}).groupby("code")["weight"].sum() if path.exists() else pd.Series(dtype=float)
