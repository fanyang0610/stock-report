"""CN 申万 industry codes (2021 scheme) per stock, weekly, from swsresearch.com's public change-history file:
each stock's level-1 industry for the Phase 13 base rates and peer groups (PLAN.md Method 16). The file has
codes only; the 31 level-1 names are fixed by the scheme. The site's certificate chain isn't in Python's
trust store, so it is fetched with curl (macOS trust store), as the backtest does."""

import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport.fetch import HISTORY, write

URL = "https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls"
TABLE = HISTORY / "cn_sw.csv.gz"
L1 = {"11": "农林牧渔", "22": "基础化工", "23": "钢铁", "24": "有色金属", "27": "电子", "28": "汽车", "33": "家用电器",
      "34": "食品饮料", "35": "纺织服饰", "36": "轻工制造", "37": "医药生物", "41": "公用事业", "42": "交通运输",
      "43": "房地产", "45": "商贸零售", "46": "社会服务", "48": "银行", "49": "非银金融", "51": "综合", "61": "建筑材料",
      "62": "建筑装饰", "63": "电力设备", "64": "机械设备", "65": "国防军工", "71": "计算机", "72": "传媒", "73": "通信",
      "74": "煤炭", "75": "石油石化", "76": "环保", "77": "美容护理"}


def update(today: date) -> None:
    if TABLE.exists() and (today - date.fromtimestamp(TABLE.stat().st_mtime)).days < 7:
        return
    with tempfile.TemporaryDirectory() as tmp:
        xls = Path(tmp) / "sw.xls"
        for attempt in range(5):  # it answers 508 or drops the connection now and then
            if subprocess.run(["curl", "-sSf", "-o", str(xls), "-A", "Mozilla/5.0", URL]).returncode == 0:
                break
            time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError("申万 download failed")
        df = pd.read_excel(xls, dtype=str)
    df.columns = ["code", "start", "sw", "updated"]
    write(df.assign(code=df["code"].str.zfill(6), start=df["start"].str[:10])[["code", "start", "sw"]], TABLE)


def level1() -> pd.Series:
    """code -> today's 申万 level-1 name (the latest change per stock in the 2021 scheme)."""
    sw = pd.read_csv(TABLE, dtype=str).sort_values("start").groupby("code")["sw"].last()
    return sw.str[:2].map(L1).dropna()
