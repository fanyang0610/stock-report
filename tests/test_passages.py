"""Periodic-report passages (PLAN.md, "Results review"): code cuts the text around the hard-flag words of saved
filings (Kenvue's 10-Q, 贵州茅台's half-year report, a CN contract-win PDF), what a hard flag quoted from a passage must
say, the daily limit and the per-filing cache; and your verdicts."""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport import passages, quotes, verdicts
from stockreport.fetch import filings

SAMPLES = Path(__file__).parent / "data"


def test_passages_hold_the_hard_flag_sentences():
    kvue = passages.cut((SAMPLES / "filing_us_kvue_sample.txt").read_text(encoding="utf-8"))  # its 10-Q, 2026-10-30
    assert len(kvue) == 1 and "Company shareholders will receive 1) 0.14625 shares of K-C common stock" in kvue[0]
    moutai = passages.cut((SAMPLES / "filing_cn_sample.txt").read_text(encoding="utf-8"))  # 2026 half-year report
    assert any("不存在影响持续经营能力的重大事项" in p for p in moutai)  # a denial: the review drops it (review.DENIAL)
    assert passages.cut("Revenue grew in every segment. " * 200) == []  # nothing to cut: no passage
    pledge = "本公司董事会及全体董事保证本公告内容不存在任何虚假记载、误导性陈述或者重大遗漏。董事会保证没有虚假记载。"
    assert passages.cut(pledge * 20) == []  # every CN report's pledge
    assert passages.cut(pledge + "公司因年报虚假记载收到中国证监会《行政处罚决定书》。")
    long = ("x" * 2000 + " investigation ") * 40
    assert sum(map(len, passages.cut(long))) <= passages.CFG["max_chars"]


def test_a_hard_flag_from_a_passage_must_say_it_plainly():
    kind = lambda kind, quote: passages.strict(kind, quote)
    assert kind("audit", "我们对贵公司财务报表发表了保留意见。") == ("audit", True)
    assert kind("audit", "后附的财务报表在所有重大方面公允反映了……（标准无保留意见）") == (None, False)  # no finding
    assert kind("going_concern", "公司持续经营能力存在重大不确定性。") == ("going_concern", True)
    assert kind("going_concern", "财务报表以持续经营为基础编制。") == (None, False)
    assert kind("investigation", "公司于2026年7月收到中国证监会《立案告知书》") == ("investigation", True)
    assert kind("investigation", "In May 2026 we received a subpoena from the SEC Division of Enforcement.") \
        == ("investigation", True)
    note = "We are subject to various investigations, claims and legal proceedings in the ordinary course."
    assert kind("investigation", note) == ("other", False)  # a 10-Q's legal note: a soft concern at most
    assert kind("investigation", "公司收到上海证券交易所监管工作函") == ("other", False)
    sale = ("Pursuant to the terms and subject to the conditions of the Merger Agreement, Company shareholders will "
            "receive 1) 0.14625 shares of K-C common stock")  # Kenvue: a pending sale for shares and cash
    assert kind("takeover", sale) == ("takeover", True)
    assert kind("takeover", "本公司拟以协议安排方式私有化") == ("takeover", True)
    acquirer = ("On May 1, 2026, the Company entered into an Agreement and Plan of Merger with Target Inc., pursuant to "
                "which the Company will acquire all of the outstanding shares of Target Inc.")
    assert kind("takeover", acquirer) == (None, False)  # the company buying another isn't being sold
    done = "The merger, under which K-C will acquire all of the outstanding shares of the Company, was completed."
    assert kind("takeover", done) == (None, False)
    assert kind("delisting", "本公司股票可能被终止上市") == ("delisting", False)  # filing titles carry these
    assert kind("guidance", "预计全年利润下降") == ("guidance", False)


def test_pdf_text_is_read_and_unreadable_fonts_are_caught():
    text = filings.pdf_text((SAMPLES / "filing_cn_contract_sample.pdf").read_bytes())  # 浦东建设 contract wins
    assert filings.readable(text) and "中标金额总计为人民币138,829.16万元" in quotes.norm(text)
    assert not filings.readable("ᅱഅၿྛٺܢႵཋ܄ඳ 2026୍϶୍؇Бۡ čAܢĎ " * 40)  # fonts without a Unicode map


def test_daily_limit_and_cache(tmp_path, monkeypatch):
    """Six names on the lists, three new filings a day: Buy first, the Sell name never; a cached filing costs nothing."""
    monkeypatch.setattr(passages, "CACHE", tmp_path / "cache")
    monkeypatch.setitem(passages.CFG, "per_day", 3)
    monkeypatch.setitem(passages.CFG, "workers", 1)
    codes = [f"60000{i}" for i in range(1, 6)]
    rows = pd.DataFrame({"list": ["hold", "buy", "buy", "next", "hold_next", "sell"], "code": codes + ["600009"],
                         "rank": [1, 2, 1, 1, 1, 1]})
    monkeypatch.setattr(filings, "periodic", lambda m, c, today: {
        "url": f"http://static.cninfo.com.cn/finalpage/2026-08-20/{c}.PDF", "title": f"{c} 半年报", "date": "2026-08-20"})
    read = []
    monkeypatch.setattr(filings, "text", lambda m, url: read.append(url[-10:-4]) or "公司收到中国证监会《立案告知书》。")
    got = passages.update("cn", rows, date(2026, 10, 19))
    assert read == ["600003", "600002", "600004"] and set(got) == set(read)  # Buy by rank, then the bench, then Hold
    assert got["600003"]["passages"] == ["公司收到中国证监会《立案告知书》。"] and got["600003"]["date"] == "2026-08-20"
    assert passages.update("cn", rows, date(2026, 10, 19)) == got and len(read) == 3  # same day: nothing more
    assert set(passages.update("cn", rows, date(2026, 10, 20))) == set(codes) and len(read) == 5
    saved = json.loads(next((tmp_path / "cache" / "cn").glob("600001_*.json")).read_text(encoding="utf-8"))
    assert saved["read"] == "2026-10-20" and "600009" not in "".join(read)


def test_verdicts(tmp_path, monkeypatch):
    monkeypatch.setattr(verdicts, "PATH", tmp_path / "verdicts.csv")
    monkeypatch.setattr(verdicts, "periods", lambda m: pd.Series({"600519": "2026-06-30"}))
    verdicts.add("600519", "veto", "2026-12-31", "测试", date(2026, 10, 19))
    verdicts.add("700", "confirm", "2026-10-25", "测试", date(2026, 10, 19))
    assert verdicts.active("cn", date(2026, 10, 20), pd.Series({"600519": "2026-06-30"}))["600519"]["verdict"] == "veto"
    assert verdicts.active("cn", date(2026, 10, 20), pd.Series({"600519": "2026-09-30"})) == {}  # a newer report
    assert verdicts.active("hk", date(2026, 10, 25), pd.Series(dtype=str))["00700"]["verdict"] == "confirm"
    assert verdicts.active("hk", date(2026, 10, 26), pd.Series(dtype=str)) == {}  # past its date
