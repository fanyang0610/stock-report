"""Filing rules (events.classify) on real filings of 2026-10-16: CNINFO's and HKEXnews' saved replies, parsed as the
review's per-stock queries parse them (fetch/filings.py), and SEC forms with their 8-K items."""

import json
from pathlib import Path

from stockreport import events
from stockreport.fetch import filings

SAMPLES = Path(__file__).parent / "data"


def load(name: str):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def test_cn_rules():
    rows = filings.parse_cn(load("events_cn_sample.json"))
    assert len(rows) == 6 and rows[0]["url"].startswith("http://static.cninfo.com.cn/finalpage/2026-10-16/")
    got = [events.classify("cn", r) for r in rows]
    # 业绩预增, a lawyer's opinion, a restructuring, the exchange's abnormal-move notice, a buyback, a contract win
    assert got == ["earnings", "routine", "deal", "routine", "capital", "business"]


def test_hk_rules():
    rows = filings.parse_hk(json.loads(load("events_hk_sample.json")["result"]))
    got = [events.classify("hk", r) for r in rows]
    # a positive profit alert, a next-day return, a discloseable transaction, an ETF filing for 9 counters, a rights
    # issue, inside information on a 立案调查
    assert got == ["earnings", "routine", "deal", "routine", "capital", "risk"]
    assert all(r["url"].startswith("https://www1.hkexnews.hk/listedco/") for r in rows)


def test_us_rules():
    # results with Reg FD, Reg FD alone, a material agreement with exhibits, an officer change, a 6-K, an amended
    # tender offer
    rows = [{"form": "8-K", "items": "2.02,7.01"}, {"form": "8-K", "items": "7.01"}, {"form": "8-K", "items": "1.01,9.01"},
            {"form": "8-K", "items": "5.02"}, {"form": "6-K", "items": ""}, {"form": "SC TO-T/A", "items": ""}]
    assert [events.classify("us", r) for r in rows] == ["earnings", "routine", "deal", "other", "other", "deal"]
    assert filings.us_title("8-K", "2.02,7.01", "8-K") == "8-K: Results of operations; Item 7.01"
    assert filings.us_title("6-K", "", "6-K") == "6-K: Report of foreign issuer"
