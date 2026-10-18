"""通达信 official daily packages (www.tdx.com.cn): one zip per trading day with every SH/SZ
security's close, exchange prev-close (ex-rights adjusted), volume and turnover. The zip is parsed
in memory and never stored; only A-share rows (plus the CSI 300 index) are kept."""

import io
import logging
import re
import struct
import zipfile
from datetime import date, timedelta

import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import Http

log = logging.getLogger(__name__)
URL = "https://www.tdx.com.cn/products/data/data/g4day/{ymd}.zip"
PATH = DATA / "prices" / "cn.csv.gz"
A_SHARE = {"sh": re.compile(r"^(60[0-5]|68[89])\d{3}$"), "sz": re.compile(r"^(00[0-3]|30[01])\d{3}$")}
INDEXES = {("sh", "000300"): "CSI300"}
http = Http(min_interval=0.3, timeout=90)


def parse_package(content: bytes, ymd: str, min_rows: int = 4000, names: bool = False) -> pd.DataFrame:
    """Each market has a .cod code table (150-byte records) and a .md1 quote file (512-byte blocks).
    Layout as documented in the a-stock-data skill (from jing2uo/tdx2db). names: also the day's
    security name (GBK at bytes 40-72), which carries the ST prefix of that day (the backtest)."""
    archive = zipfile.ZipFile(io.BytesIO(content))
    rows = []
    for market in ("sh", "sz"):
        cod = archive.read(f"{market}{ymd[2:]}.cod")
        md1 = archive.read(f"{market}{ymd[2:]}.md1")
        if len(cod) % 150 or len(md1) % 512:
            raise RuntimeError(f"tdx {ymd} {market}: truncated file")
        for off in range(0, len(cod), 150):
            rec = cod[off:off + 150]
            code = rec[0:6].decode("ascii", "replace")
            key = INDEXES.get((market, code))
            if key is None and not A_SHARE[market].match(code):
                continue
            seq = struct.unpack("<H", rec[32:34])[0]
            block = md1[seq * 512:(seq + 1) * 512]
            prev_close = struct.unpack("<d", block[4:12])[0]
            close = struct.unpack("<d", block[36:44])[0]
            volume = struct.unpack("<Q", block[56:64])[0]
            amount = struct.unpack("<d", block[72:80])[0]
            if close > 0 and prev_close > 0:
                name = rec[40:72].split(b"\x00")[0].decode("gbk", "replace").strip() if names else None
                rows.append((key or code, round(close, 4), round(prev_close, 4), volume, round(amount, 2), name))
    df = pd.DataFrame(rows, columns=["code", "close", "prev_close", "volume", "amount", "name"])
    if not names:
        df = df.drop(columns="name")
    if len(df) < min_rows:
        raise RuntimeError(f"tdx {ymd}: only {len(df)} A-share rows")
    df.insert(0, "date", f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}")
    return df


def load_prices() -> pd.DataFrame:
    return pd.read_csv(PATH, dtype={"code": str, "date": str})


def _save(frames: list[pd.DataFrame], start: str) -> pd.DataFrame:
    df = pd.concat(frames).drop_duplicates(["date", "code"], keep="last")
    df = df[df["date"] >= start].sort_values(["date", "code"])
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    df.to_csv(tmp, index=False, compression="gzip")
    tmp.replace(PATH)
    return df


def update_prices(today: date) -> None:
    """Append every trading day since the last stored one; first run backfills `history_days`."""
    keep_from = today - timedelta(days=CONFIG["universe"]["history_days"])
    old = load_prices() if PATH.exists() else None
    day = date.fromisoformat(old["date"].max()) + timedelta(days=1) if old is not None else keep_from
    frames, added = ([old] if old is not None else []), 0
    while day <= today:
        ymd = day.strftime("%Y%m%d")
        resp = http.get(URL.format(ymd=ymd), ok=(200, 404))
        if resp.status_code == 200:  # 404 = not a trading day, or not published yet
            frames.append(parse_package(resp.content, ymd))
            added += 1
            if added % 25 == 0:  # checkpoint long backfills
                frames = [_save(frames, keep_from.isoformat())]
                log.info("tdx prices: %d days added, up to %s", added, day)
        day += timedelta(days=1)
    if added or old is None:
        df = _save(frames, keep_from.isoformat())
        log.info("tdx prices: +%d days, %s to %s, %d rows", added, df["date"].min(), df["date"].max(), len(df))
