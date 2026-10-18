"""Tencent quotes (qt.gtimg.cn): CN's second source for the daily quote, in batches of 60 codes (GBK,
fields separated by ~; layout as in the a-stock-data skill, checked 2026-10-19 on 600519 and 688146):
3 price, 4 previous close, 30 time (YYYYMMDDhhmmss), 39 PE-TTM, 45 total market value (100m CNY),
46 P/B, 73 total shares. Only the extracted table is kept (data/quotes/cn_tencent.csv.gz, daily)."""

import logging

import pandas as pd

from stockreport.config import DATA
from stockreport.fetch import Http, write

log = logging.getLogger(__name__)
URL = "https://qt.gtimg.cn/q="
PATH = DATA / "quotes" / "cn_tencent.csv.gz"
FIELDS = {"price": 3, "prev_close": 4, "pe_ttm": 39, "mcap": 45, "pb": 46, "shares": 73}
http = Http(min_interval=0.3, headers={"User-Agent": "Mozilla/5.0"})


def parse(text: str) -> pd.DataFrame:
    """One row per quote line: code, session date, the FIELDS as numbers (market value in CNY)."""
    rows = []
    for line in text.split(";"):
        if '"' not in line:
            continue
        v = line.split('"')[1].split("~")
        if len(v) <= max(FIELDS.values()):
            continue
        num = lambda i: pd.to_numeric(v[i], errors="coerce")
        rows.append({"code": v[2], "date": f"{v[30][:4]}-{v[30][4:6]}-{v[30][6:8]}"}
                    | {k: num(i) for k, i in FIELDS.items()})
    df = pd.DataFrame(rows, columns=["code", "date", *FIELDS])
    df["mcap"] *= 1e8
    return df


def update_quotes(codes: list[str]) -> None:
    """Today's Tencent quote for `codes` (6-digit A-share codes)."""
    prefixed = [("sh" if c.startswith("6") else "sz") + c for c in codes]
    frames = [parse(http.get(URL + ",".join(prefixed[i:i + 60])).content.decode("gbk", "replace"))
              for i in range(0, len(prefixed), 60)]
    df = pd.concat(frames)
    if len(df) < 0.9 * len(codes):
        raise RuntimeError(f"Tencent returned {len(df)} quotes for {len(codes)} codes")
    write(df, PATH)
    log.info("tencent quotes: %d stocks for %s", len(df), df["date"].max())


def load() -> pd.DataFrame:
    return pd.read_csv(PATH, dtype={"code": str, "date": str}).set_index("code") if PATH.exists() else pd.DataFrame()
