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


def test_an_item_301_move_to_another_exchange_is_no_delisting_notice():
    moved = (SAMPLES / "filing_us_skyd_301_sample.txt").read_text()  # Skydance, 2026-09-25: Nasdaq to the NYSE
    assert filings.listing_moved(moved)
    notice = ("Item 3.01. Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard; Transfer of "
              "Listing. On May 1, 2026 the Company received a letter from Nasdaq stating that it is not in compliance "
              "with Listing Rule 5250(c)(1), as it has not filed its Form 10-K. Item 9.01. Exhibits.")
    assert not filings.listing_moved(notice) and not filings.listing_moved("Item 7.01. Regulation FD Disclosure.")
    head = "Item 3.01. Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard; Transfer of Listing.\n"
    cure = (head + "The Company received a written notice from Nasdaq that the closing bid price of its common stock was "
            "below $1. If it does not regain compliance, it may transfer the listing to The Nasdaq Capital Market.\nItem 9.01")
    wrapped = head + "The Company received a letter stating that it is not in\ncompliance and may transfer to Nasdaq.\nItem 9.01"
    move = head + "The Board approved the transfer of the listing of its common stock from Nasdaq to\nthe NYSE.\nItem 9.01"
    assert not filings.listing_moved(cure) and not filings.listing_moved(wrapped) and filings.listing_moved(move)
