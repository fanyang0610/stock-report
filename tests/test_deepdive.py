"""Deep-dive lane (PLAN.md Method 15): quotes checked against saved filings (CN half-year report, HK interim report
in English, US 10-Q, a CN contract-win PDF), what verified facts mean for a pick, the daily limit and the per-filing
cache, and manual verdicts."""

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
    assert f["net_profit"]["value"] == 4_294e6 and f["embedded_value"]["value"] == 80_555e6
    assert f["embedded_value"]["currency"] == "USD"
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


def pick(bucket: str = "buy", **kw) -> pd.Series:
    return pd.Series({"code": "600001", "bucket": bucket, "price": 10.0, "mcap": 1e10, "revenue_ttm": 5e9} | kw)


def found(source: str = "periodic", **facts) -> dict:
    return {"facts": facts, "asked": len(facts), "title": "2026年半年度报告", "date": "2026-08-20", "source": source}


def test_meaning():
    money = lambda v: {"quote": "x", "value": v, "currency": "CNY", "pct": False}
    one_off = found(non_recurring=money(4e8), net_profit=money(1e9))
    assert deepdive.meaning(pick("buy"), one_off, "cn")["action"] == "veto"
    assert deepdive.meaning(pick("sell"), one_off, "cn")["action"] == "none"  # a one-off only adds to overvaluation
    small = deepdive.meaning(pick("buy"), found(non_recurring=money(1e8), net_profit=money(1e9)), "cn")
    assert small["action"] == "none" and "非经常性损益占同期归母净利润 10%" in small["line"]
    offer = deepdive.meaning(pick("sell"), found(offer_price=money(12.0)), "cn")
    assert offer["action"] == "veto" and "较现价 +20%" in offer["line"]
    deal = deepdive.meaning(pick("hold"), found("event", deal_size=money(3.045e9)), "cn")
    assert "占近 12 个月营收 61%、市值 30%，重大" in deal["line"] and deal["action"] == "none"
    assert "交易" not in deepdive.meaning(pick("hold"), found(deal_size=money(3.045e9)), "cn")["line"]  # periodic
    standard = {"quote": "我们认为，后附的财务报表在所有重大方面按照企业会计准则的规定编制，公允反映了……（标准无保留意见）"}
    assert "审计意见为无保留意见" in deepdive.meaning(pick(), found(audit_opinion=standard), "cn")["line"]
    qualified = {"quote": "我们对贵公司财务报表发表了保留意见。"}
    assert deepdive.meaning(pick(), found(audit_opinion=qualified), "cn")["action"] == "veto"
    denial = {"quote": "本公司自本报告期末至少 12 个月内不存在影响持续经营能力的重大事项。"}
    assert deepdive.meaning(pick(), found(going_concern=denial), "cn")["action"] == "none"
    related = {"quote": "x", "value": 0.42, "currency": None, "pct": True}
    assert deepdive.meaning(pick(), found(related_party_pct=related), "cn")["action"] == "low"


def test_daily_limit_and_cache(tmp_path, monkeypatch):
    """Five triggered names, three new filings a day; the other two wait, and a cached filing costs nothing."""
    monkeypatch.setattr(deepdive, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(deepdive, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(deepdive, "dotenv_values", lambda p: {"DEEPSEEK_API_KEY": "test"})
    codes = [f"60000{i}" for i in range(1, 6)]
    rows = {c: pick(code=c, name=f"测试{c[-1]}") for c in codes}
    monkeypatch.setattr(deepdive, "triggers", lambda m, cands, today: [
        {"code": c, "name": rows[c]["name"], "row": rows[c], "why": "测试", "filing": None} for c in codes])
    monkeypatch.setattr(deepdive, "candidates", lambda picks, df: picks)
    monkeypatch.setattr(deepdive.filings, "periodic", lambda m, c, today: {
        "url": f"http://static.cninfo.com.cn/finalpage/2026-08-20/{c}.PDF", "title": f"{c} 半年报", "date": "2026-08-20"})
    read = []
    monkeypatch.setattr(deepdive, "study", lambda client, m, c, n, f: read.append(c) or found())
    first = deepdive.run("cn", date(2026, 10, 19), pd.DataFrame(), pd.DataFrame(), use_ai=True)
    assert first["fresh"] == codes[:3] and set(first["results"]) == set(codes[:3])
    again = deepdive.run("cn", date(2026, 10, 19), pd.DataFrame(), pd.DataFrame(), use_ai=True)
    assert again["fresh"] == codes[:3] and len(read) == 3  # same day: nothing more
    nextday = deepdive.run("cn", date(2026, 10, 20), pd.DataFrame(), pd.DataFrame(), use_ai=True)
    assert nextday["fresh"] == codes[3:] and len(nextday["results"]) == 5 and len(read) == 5
    off = deepdive.run("cn", date(2026, 10, 21), pd.DataFrame(), pd.DataFrame(), use_ai=False)
    assert off["fresh"] == [] and len(off["results"]) == 5  # without DeepSeek: cached filings only


def test_verdicts(tmp_path, monkeypatch):
    monkeypatch.setattr(verdicts, "PATH", tmp_path / "verdicts.csv")
    monkeypatch.setattr(verdicts, "periods", lambda m: pd.Series({"600519": "2026-06-30"}))
    verdicts.add("600519", "veto", "2026-12-31", "测试", date(2026, 10, 19))
    verdicts.add("700", "confirm", "2026-10-25", "测试", date(2026, 10, 19))
    assert verdicts.active("cn", date(2026, 10, 20), pd.Series({"600519": "2026-06-30"}))["600519"]["verdict"] == "veto"
    assert verdicts.active("cn", date(2026, 10, 20), pd.Series({"600519": "2026-09-30"})) == {}  # a newer report
    assert verdicts.active("hk", date(2026, 10, 25), pd.Series(dtype=str))["00700"]["verdict"] == "confirm"
    assert verdicts.active("hk", date(2026, 10, 26), pd.Series(dtype=str)) == {}  # past its date
