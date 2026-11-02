"""The CSI 300's constituent weights from China Securities Index's month-end file, read daily (a small file; a failed
read keeps the last one), for CN's free-float factors only: how much of each company trades freely, which total market
value overstates for state-held banks and oil companies (PLAN.md, "Lists"). The buys come from the whole market, not
from the index."""

from datetime import datetime

import pandas as pd
import xlrd

from stockreport.config import DATA
from stockreport.fetch import Http, write

URL = "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/closeweight/000300closeweight.xls"
WEIGHTS = DATA / "fundamentals" / "cn_index.csv.gz"  # code, weight (share of the index), date
http = Http(min_interval=1.0)


def parse_csi(content: bytes) -> pd.DataFrame:
    """CSI's weight file: one row per constituent, the date first, the code fifth, the weight in % last."""
    sheet = xlrd.open_workbook(file_contents=content).sheet_by_index(0)
    rows = [sheet.row_values(i) for i in range(1, sheet.nrows)]
    day = lambda x: datetime.strptime(str(x)[:8], "%Y%m%d").date().isoformat()
    return pd.DataFrame({"code": [str(r[4]).zfill(6) for r in rows], "weight": [float(r[-1]) / 100 for r in rows],
                         "date": [day(r[0]) for r in rows]})


def update() -> None:
    df = parse_csi(http.get(URL).content)
    if len(df) < 290 or not 0.97 <= df["weight"].sum() <= 1.01:
        raise RuntimeError(f"CSI 300 file: {len(df)} names, weights sum to {df['weight'].sum():.1%}")
    write(df, WEIGHTS)


def load() -> pd.Series:
    """Code -> share of the CSI 300 (empty without a file)."""
    return pd.read_csv(WEIGHTS, dtype={"code": str}).groupby("code")["weight"].sum() if WEIGHTS.exists() \
        else pd.Series(dtype=float)


def as_of() -> str | None:
    """The weights' date (CSI's month end), or None without a file."""
    return pd.read_csv(WEIGHTS, usecols=["date"])["date"].max() if WEIGHTS.exists() else None
