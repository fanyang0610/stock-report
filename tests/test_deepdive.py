"""Deep-dive lane (AGENTS.md rule 3; PLAN.md, "Results review"): quotes checked against saved filings (CN half-year
report, HK interim report in English, US 10-Q, a CN contract-win PDF), the data check and what verified facts mean for
a name, the daily limit and the per-filing cache, and manual verdicts."""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport import deepdive, quotes, verdicts
from stockreport.fetch import filings

SAMPLES = Path(__file__).parent / "data"


def saved(market: str) -> tuple[str, dict]:
    return ((SAMPLES / f"filing_{market}_sample.txt").read_text(encoding="utf-8"),
            json.loads((SAMPLES / f"filing_{market}_answer.json").read_text(encoding="utf-8")))


def test_quotes_verified_on_saved_filings():
    text, answer = saved("cn")  # 贵州茅台 2026 half-year: table rows under "单位：元 币种：人民币"
    f = deepdive.verify(answer, text, "cn")["facts"]
    assert f["non_recurring"]["value"] == 52_672_775.85 and f["non_recurring"]["currency"] == "CNY"
    assert f["net_profit"]["value"] == 44_516_880_421.86
    assert "不存在" in f["going_concern"]["quote"]  # quoted, but a denial: meaning() must not flag it
    text, answer = saved("hk")  # AIA interim report, "US$m" and "US$ millions" unit lines
    f = deepdive.verify(answer, text, "hk")["facts"]
    assert f["net_profit"]["value"] == 4_294e6 and f["net_profit"]["currency"] == "USD" and f["net_profit"]["scale"] == 1e6
    text, answer = saved("us")  # MetLife 10-Q, "(In millions, except per share data)"
    assert deepdive.verify(answer, text, "us")["facts"]["net_profit"]["value"] == 1_845e6


def test_unverifiable_answers_are_dropped():
    text, answer = saved("cn")
    full, row = quotes.norm(text), dict(answer["net_profit"])
    assert quotes.check(row | {"quote": row["quote"].replace("44,516", "45,516")}, full) is None  # not in the filing
    assert quotes.check(row | {"number": "45,516,880,421.86"}, full) is None  # number not in the quote
    assert quotes.check(row | {"number": "516,880,421.86"}, full) is None  # only part of a number
    assert quotes.check(row | {"unit_quote": "单位：万元"}, full) is None  # unit line not in the filing
    assert quotes.check(row | {"unit_quote": ""}, full) is None  # a table row needs its unit line
    assert quotes.check({"quote": "合计", "number": ""}, full) is None  # too short to locate


def test_pdf_text_and_inline_units():
    text = filings.pdf_text((SAMPLES / "filing_cn_contract_sample.pdf").read_bytes())  # 浦东建设 contract wins
    assert filings.readable(text)
    item = {"quote": "中标金额总计为人民币138,829.16万元", "number": "138,829.16", "unit_quote": ""}
    fact = quotes.check(item, quotes.norm(text))
    assert round(fact["value"]) == 1_388_291_600 and fact["currency"] == "CNY"
    assert not filings.readable("ᅱഅၿྛٺܢႵཋ܄ඳ 2026୍϶୍؇Бۡ čAܢĎ " * 40)  # fonts without a Unicode map


def aia(**row) -> tuple[dict, dict]:
    """AIA's interim report read with its period end, and a card row for the same period (US$, reporting currency)."""
    text, answer = saved("hk")
    found = deepdive.verify(answer | {"period_end": {"quote": "Six months ended 30 June 2026"}}, text, "hk")
    return {"code": "01299", "period": "2026-06-30", "np_ytd": 4_294e6, "report_currency": "USD", "price": 80.0} | row, \
        found | {"title": "2026 Interim Report", "date": "2026-08-20"}


def test_data_check_on_a_saved_filing():
    row, found = aia()
    assert deepdive.period_of("for the quarterly period ended September 27, 2026") == "2026-09-27"
    assert deepdive.period_of("截至2026年9月30日止九个月") == "2026-09-30" and deepdive.period_of("no date") is None
    assert deepdive.period_of("Financial position as at 30th June 2026.") == "2026-06-30"  # Cathay's interim report
    assert deepdive.title_period("中国铝业2026年半年度报告") == "2026-06-30"
    assert deepdive.title_period("2026年第三季度报告") == "2026-09-30" and deepdive.title_period("2025年年度报告") == "2025-12-31"
    assert deepdive.data_gap(row, found, "hk") is None  # the report agrees with the card's figure
    gap = deepdive.data_gap(row | {"np_ytd": 6_000e6}, found, "hk")
    assert gap == "最新报告的归母净利润 42.94 亿与卡片所用数据 60.00 亿相差 28%"
    assert deepdive.data_gap(row | {"np_ytd": 2_400e6}, found, "hk") is None  # within 20% of the row's 2025 column
    assert deepdive.data_gap(row | {"np_ytd": 4_294e3}, found, "hk") is None  # a power of ten: a unit misread
    assert deepdive.data_gap(row | {"np_ytd": 6_000e6, "period": "2026-09-30"}, found, "hk") is None  # another period
    assert deepdive.data_gap(row | {"np_ytd": 6_000e6, "report_currency": None}, found, "hk") is None
    rows_read = lambda quote: found | {"facts": found["facts"] | {"net_profit": found["facts"]["net_profit"] | {"quote": quote}}}
    for quote in ("Net profit 4,314 2,549", "Non-controlling interests attributable to minority holders 4,314 2,549",
                  "归属于上市公司股东的扣除非经常性损益的净利润 4,294 2,534"):
        assert deepdive.data_gap(row | {"np_ytd": 6_000e6}, rows_read(quote), "hk") is None  # not the shareholders' profit
    odd = deepdive.findings(row | {"np_ytd": 6_000e6}, found, "hk")
    assert [(f["kind"], f.get("suspect")) for f in odd] == [("data_suspect", True)] and odd[0]["type"] == "2026 Interim Report"


def found_with(**facts) -> dict:
    return {"facts": facts, "asked": len(facts), "title": "2026年半年度报告", "date": "2026-08-20"}


def test_findings():
    money = lambda v: {"quote": "x", "value": v, "currency": "CNY", "pct": False, "scale": 1.0}
    row = {"code": "600001", "price": 10.0}
    kinds = lambda **f: [(x["kind"], x["hard"]) for x in deepdive.findings(row, found_with(**f), "cn")]
    assert kinds(non_recurring=money(4e8), net_profit=money(1e9)) == [("one_off", False)]  # a soft concern only
    assert kinds(non_recurring=money(1e8), net_profit=money(1e9)) == []
    after = money(9.99e8) | {"quote": "Net profit after deducting non-recurring profit or loss items attributable to equity "
                                      "shareholders of the Company 85,733 69,476 23.4"}  # CNOOC's interim report
    assert kinds(non_recurring=after, net_profit=money(1e9)) == []  # that's the profit, not the one-off items
    assert kinds(offer_price=money(12.0)) == [("takeover", True)]
    assert "较现价 +20%" in deepdive.findings(row, found_with(offer_price=money(12.0)), "cn")[0]["words"]
    standard = {"quote": "我们认为，后附的财务报表在所有重大方面按照企业会计准则的规定编制，公允反映了……（标准无保留意见）"}
    assert kinds(audit_opinion=standard) == []
    assert kinds(audit_opinion={"quote": "我们对贵公司财务报表发表了保留意见。"}) == [("audit", True)]
    denial = {"quote": "本公司自本报告期末至少 12 个月内不存在影响持续经营能力的重大事项。"}
    assert kinds(going_concern=denial) == []
    assert kinds(investigation={"quote": "公司于2026年7月收到中国证监会《立案告知书》"}) == [("investigation", True)]
    note = {"quote": "We are subject to various investigations, claims and legal proceedings in the ordinary course."}
    assert kinds(investigation=note) == [("other", False)]  # a 10-Q's legal note is no investigation opened
    assert kinds(investigation={"quote": "公司收到上海证券交易所监管工作函"}) == [("other", False)]


def test_daily_limit_and_cache(tmp_path, monkeypatch):
    """Five candidates, three new filings a day; the other two wait, and a cached filing costs nothing."""
    monkeypatch.setattr(deepdive, "CACHE", tmp_path / "cache")
    codes = [f"60000{i}" for i in range(1, 6)]
    rows = pd.DataFrame({"list": ["buy"] * 5, "code": codes, "name": codes, "rank": range(1, 6), "score": 0.9})
    monkeypatch.setattr(deepdive.filings, "periodic", lambda m, c, today: {
        "url": f"http://static.cninfo.com.cn/finalpage/2026-08-20/{c}.PDF", "title": f"{c} 半年报", "date": "2026-08-20"})
    read = []
    monkeypatch.setattr(deepdive, "study", lambda client, m, c, n, f: read.append(c) or {"facts": {}, "asked": 0})
    assert deepdive.run("cn", rows, date(2026, 10, 19), None) == 3 and read == codes[:3]
    assert deepdive.run("cn", rows, date(2026, 10, 19), None) == 0 and len(read) == 3  # same day: nothing more
    assert deepdive.run("cn", rows, date(2026, 10, 20), None) == 2 and read == codes
    assert set(deepdive.results("cn", rows)) == set(codes)  # each name's newest filing read, cached


def test_verdicts(tmp_path, monkeypatch):
    monkeypatch.setattr(verdicts, "PATH", tmp_path / "verdicts.csv")
    monkeypatch.setattr(verdicts, "periods", lambda m: pd.Series({"600519": "2026-06-30"}))
    verdicts.add("600519", "veto", "2026-12-31", "测试", date(2026, 10, 19))
    verdicts.add("700", "confirm", "2026-10-25", "测试", date(2026, 10, 19))
    assert verdicts.active("cn", date(2026, 10, 20), pd.Series({"600519": "2026-06-30"}))["600519"]["verdict"] == "veto"
    assert verdicts.active("cn", date(2026, 10, 20), pd.Series({"600519": "2026-09-30"})) == {}  # a newer report
    assert verdicts.active("hk", date(2026, 10, 25), pd.Series(dtype=str))["00700"]["verdict"] == "confirm"
    assert verdicts.active("hk", date(2026, 10, 26), pd.Series(dtype=str)) == {}  # past its date
