"""Event layer (PLAN.md Method 14): the market-wide feeds parsed from saved samples, the rule classification,
and abnormal moves labelled with or without a matching filing."""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from stockreport import events
from stockreport.fetch import events as feeds

SAMPLES = Path(__file__).parent / "data"


class Saved:
    """Stands in for Http: every call returns the saved payload."""

    def __init__(self, name: str):
        self.payload = json.loads((SAMPLES / name).read_text(encoding="utf-8"))

    def get(self, url, params=None):
        return self

    def post(self, url, data=None):
        return self

    def json(self):
        return self.payload


def test_cn_feed_and_rules():
    rows = feeds.cn_day(Saved("events_cn_sample.json"), "2026-10-16")
    assert len(rows) == 6 and rows[0]["url"].startswith("http://static.cninfo.com.cn/finalpage/2026-10-16/")
    got = [events.classify("cn", r) for r in rows]
    # 业绩预增, a lawyer's opinion, a restructuring, the exchange's abnormal-move notice, a buyback, a contract win
    assert got == ["earnings", "routine", "deal", "routine", "capital", "business"]


def test_hk_feed_and_rules():
    rows = feeds.hk_day(Saved("events_hk_sample.json"), "2026-10-16")
    got = {r["code"]: events.classify("hk", r) for r in rows}
    # a positive profit alert, a next-day return, a discloseable transaction, an ETF filing for 9 counters (one row
    # each), a rights issue, inside information on a 立案调查
    assert got == {"01304": "earnings", "02137": "routine", "01122": "deal", **dict.fromkeys(
        ["02802", "03121", "03133", "03149", "03431", "03469", "03473", "03499", "03537"], "routine"),
        "02369": "capital", "03347": "risk"}
    assert all(r["url"].startswith("https://www1.hkexnews.hk/listedco/") for r in rows)


def test_us_feed_and_rules():
    tickers = {1705284: ["PBAM"], 2115436: ["XOM"], 1467761: ["FIEE"], 314227: ["TOMZ"], 1988894: ["AS"]}
    rows = feeds.us_day(Saved("events_us_sample.json"), "2026-10-16", tickers)
    got = {r["code"]: (events.classify("us", r), r["title"]) for r in rows}
    assert got["PBAM"] == ("earnings", "8-K: Results of operations; Item 7.01")
    assert got["XOM"][0] == "routine"  # Reg FD only
    assert got["FIEE"][0] == "deal" and got["TOMZ"][0] == "other" and got["AS"][0] == "other"
    assert rows[0]["url"].startswith("https://www.sec.gov/Archives/edgar/data/1705284/")
    assert events.classify("us", {"form": "SC TO-T/A", "items": ""}) == "deal"


def test_abnormal_move():
    rng = np.random.default_rng(0)
    days = pd.Index([f"2026-{m:02d}-{d:02d}" for m in range(1, 11) for d in range(1, 29)][:250])
    quiet = pd.Series(rng.normal(0, 0.01, 250), days)
    assert events.move(quiet, 5, 2.5) is None
    jump = quiet.copy()
    jump.iloc[-3:] = [0.04, 0.03, 0.03]  # +10% over 3 days against a 1% daily sd: z ≈ 5.8
    found = events.move(jump, 5, 2.5)
    assert found["days"] in (3, 4) and found["z"] > 4 and found["end"] == days[-1]
    assert found["before"] == days[-found["days"] - 1]


def test_lines_label_moves(tmp_path, monkeypatch):
    """One stock jumps after a filing, another without one; both moves get a label."""
    rng = np.random.default_rng(1)
    days = pd.bdate_range("2025-10-01", "2026-10-16").strftime("%Y-%m-%d")
    rows = []
    for code in ("600001", "600002", "CSI300"):
        r = rng.normal(0, 0.01, len(days))
        if code != "CSI300":
            r[-2:] = 0.06
        close = 10 * np.exp(np.cumsum(r))
        rows.append(pd.DataFrame({"date": days, "code": code, "close": close, "prev_close": close / np.exp(r)}))
    (tmp_path / "prices").mkdir()
    pd.concat(rows).to_csv(tmp_path / "prices" / "cn.csv.gz", index=False)
    monkeypatch.setattr(events, "DATA", tmp_path)
    monkeypatch.setattr(events, "load", lambda m: pd.DataFrame(
        {"date": ["2026-10-14"], "code": ["600001"], "kind": ["earnings"], "title": ["2026年前三季度业绩预增公告"],
         "url": ["x"]}))
    picks = pd.DataFrame({"code": ["600001", "600002"], "price_date": ["2026-10-16"] * 2})
    out = events.lines("cn", picks, date(2026, 10, 17))
    assert out["600001"]["matched"] is True and "对应 10-14 业绩公告" in out["600001"]["move"]
    assert out["600002"]["matched"] is False and "按噪音处理" in out["600002"]["move"]
    assert out["600001"]["events"].startswith("10-14 业绩：") and out["600002"]["events"] == "近 30 日无重要公告"
