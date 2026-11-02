"""Results review (PLAN.md, "Results review") on saved sources: real non-routine filing titles and headlines of six
names (2026-10-25) and DeepSeek's real answers to the checklist. A quote not in its source is rejected; a hard red
flag removes a Buy or Hold name (the next name of its bench takes its place) and is only noted on a Sell name; a soft
concern only annotates; the review's order, the cache, the budget and the parsers of the sources."""

import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stockreport import review
from stockreport.events import classify
from stockreport.fetch import filings, news

SAMPLES = Path(__file__).parent / "data"
DAY = date(2026, 10, 25)
SOURCES = json.loads((SAMPLES / "review_sources_sample.json").read_text(encoding="utf-8"))
ANSWERS = json.loads((SAMPLES / "review_answers_sample.json").read_text(encoding="utf-8"))


def verified(market: str, code: str, answer: dict | None = None) -> tuple[list[dict], int, int]:
    return review.verify(answer or ANSWERS[code], review.lines_of(SOURCES[market][code]))


def test_quotes_are_checked_against_their_sources():
    found, rejected, _ = verified("cn", "600576")  # 祥源文旅: its actual controller is under a CSRC investigation
    assert rejected == 0 and [(f["kind"], f["hard"], f["type"]) for f in found] == [
        ("investigation", True, "公告"), ("investigation", False, "新闻")]  # a headline alone is a soft concern
    assert found[0]["quote"] == "关于公司实际控制人收到立案告知书的公告"
    made_up = {"findings": [{"kind": "investigation", "source": 1, "quote": "关于公司收到中国证监会立案告知书的公告"},
                            {"kind": "audit", "source": 2, "quote": "南京银行2025年度财务报告被出具保留意见"}]}
    assert verified("cn", "601009", made_up)[:2] == ([], 2)  # neither is in 南京银行's sources: both rejected
    edited = {"findings": [{"kind": "guidance", "source": 1, "quote": "中国电信第三季度营收净利润大降"}]}
    assert verified("hk", "00728", edited)[:2] == ([], 1)  # one changed character is enough
    found, rejected, _ = verified("hk", "02650")  # the whole four-character title 「盈利警告」 counts as a quote
    assert rejected == 0 and found[0]["kind"] == "guidance" and found[0]["quote"] == "盈利警告"


def test_a_hard_flag_must_name_its_subject():
    lines = review.lines_of(SOURCES["cn"]["601009"])
    check = lambda kind, title, lines=lines: review.verify({"findings": [{"kind": kind, "source": 1, "quote": title}]}, lines)[0]
    filed = lambda title: [{"type": "公告", "date": "2026-10-20", "title": title}]
    heard = lambda title: [{"type": "新闻", "date": "2026-10-20", "title": title}]
    one = lambda kind, title, where=filed: check(kind, title, where(title))
    preferred = next(x["title"] for x in lines if "优先股停牌" in x["title"])
    assert check("delisting", preferred) == []  # its preferred shares, not the stock
    resign = next(x["title"] for x in lines if "董事辞任" in x["title"])
    assert not check("investigation", resign)[0]["hard"] and not check("audit", resign)[0]["hard"]  # no subject named
    assert check("management", resign) == []  # an ordinary director: routine
    assert one("audit", "关于会计师事务所辞任的公告")[0]["hard"]
    assert not one("takeover", "关于吸收合并全资子公司的公告")[0]["hard"]  # the company absorbing its own subsidiary
    assert one("takeover", "关于收到私有化要约暨预计于年底前完成的提示性公告")[0]["hard"]  # a live offer
    assert verified("cn", "688585")[0] == []  # a sponsor's supervision report on 上纬新材's completed tender offer
    assert one("delisting", "25-NSE: Delisting notice") == []  # which security?
    assert review.lines_of({"filings": [{"date": "2026-09-14", "kind": "risk", "title": "25-NSE: Delisting notice"}],
                            "headlines": []}) == []  # left out of the sources
    assert one("investigation", "关于公司不存在被立案调查情形的说明") == []
    for routine in ("8-K: Director or officer change", "关于副总经理辞职的公告", "公司全资子公司总经理辞职",
                    "中国石油天然气销售分公司原总经理、党委副书记钱治家接受审查调查", "Vice Chair to retire"):
        assert one("management", routine) == [], routine
    assert one("management", "公司总会计师离任暨总经理代行总会计师职责的公告")[0]["kind"] == "management"
    assert not one("investigation", "70后浙商大佬、祥源文旅实控人两度遭证监会立案", heard)[0]["hard"]  # a headline: soft


def row(code: str, lst: str, rank, score: float, **kw) -> dict:
    return {"list": lst, "code": code, "name": code, "rank": rank, "score": score, "sector": "s", "status": None,
            "reason": None, "weight": 0.05, "vol_1y": 0.2} | kw


def states(*codes: str) -> dict:
    out = {}
    for code in codes:
        market = "hk" if code.startswith("0") and len(code) == 5 else "cn"
        found, rejected, _ = verified(market, code)
        out[code] = {"status": "done", "findings": found, "rejected": rejected, "note": ANSWERS[code]["note"]}
    return out


def test_a_hard_flag_removes_a_buy_or_a_hold_and_is_noted_on_a_sell_name():
    rows = pd.DataFrame([row("601225", "buy", 1, 0.95), row("600576", "buy", 2, 0.94, sector="t"),
                         row("601009", "buy", 3, 0.93), row("688585", "next", 4, 0.92),
                         row("00728", "next", 5, 0.91, sector="t"),
                         row("H1", "hold", 1, 0.5, vol_1y=0.15), row("H2", "hold", 2, 0.5, vol_1y=0.16),
                         row("H3", "hold_next", 3, 0.5, vol_1y=0.19, sector="u"), row("H4", "hold_next", 4, 0.5, vol_1y=0.18),
                         row("600576", "sell", 1, 0.10)])
    st = states("601225", "600576", "601009", "688585", "00728")
    hard = verified("cn", "600576")[0]  # a Hold name with the same finding, from a deep dive
    out = review.apply(rows, "cn", st, {"H1": hard})
    buys = out[out["list"] == "buy"]
    assert set(buys["code"]) == {"601225", "601009", "00728"} and buys["rank"].tolist() == [1, 2, 3]
    assert buys.set_index("code").at["00728", "replaces"] == "600576"  # its sector's next name; the scoreboard pairs them
    assert buys["weight"].tolist() == pytest.approx([1 / 3] * 3)  # equal amounts again
    removed = out[out["list"] == "removed"].set_index("from")
    assert removed.at["buy", "code"] == "600576" and "立案告知书" in removed.at["buy", "reason"]
    assert removed.at["buy", "status"] == "由 00728 00728 替换"
    holds = out[out["list"] == "hold"]  # H1 off the Hold list; the next of its sector in Hold's bench takes its place
    assert holds["code"].tolist() == ["H2", "H4"] and holds["rank"].tolist() == [1, 2]  # the steadiest first
    assert removed.at["hold", "code"] == "H1" and holds.set_index("code").at["H4", "replaces"] == "H1"
    sell = out[out["list"] == "sell"].iloc[0]
    assert sell["review"].startswith("审核：监管立案调查或欺诈认定") and len(out[out["list"] == "sell"]) == 1
    assert not {"next", "hold_next"} & set(out["list"])
    mine = review.apply(rows, "cn", st, {"H1": hard}, confirmed={c: {"until": "2026-12-31", "reason": "已读公告"}
                                                                for c in ("600576", "H1")})
    assert "600576" in set(mine.loc[mine["list"] == "buy", "code"]) and "removed" not in set(mine["list"])
    kept = mine[(mine["list"] == "hold") & (mine["code"] == "H1")].iloc[0]
    assert kept["review"].endswith("（你已确认，至 2026-12-31：已读公告）")


def test_a_soft_concern_only_annotates():
    rows = pd.DataFrame([row("00728", "buy", 1, 0.9), row("02650", "next", 2, 0.8), row("00728", "hold", 1, 0.5)])
    out = review.apply(rows, "hk", states("00728", "02650"), {})
    buy = out[out["list"] == "buy"].iloc[0]
    assert buy["code"] == "00728" and buy["review"].startswith("市场可能在担心：下调指引或业绩下滑")
    assert "removed" not in set(out["list"]) and buy["note"] and not any(ch.isdigit() for ch in buy["note"])
    assert out[out["list"] == "hold"].iloc[0]["review"].startswith("市场可能在担心")  # kept, annotated
    clean = review.apply(pd.DataFrame([row("601225", "buy", 1, 0.9)]), "cn", states("601225"), {})
    assert clean.iloc[0]["review"] == "审核未见重大风险"
    pending = review.apply(pd.DataFrame([row("601225", "buy", 1, 0.9)]), "cn", {"601225": {"status": "pending"}}, {})
    assert pending.iloc[0]["review"] == "审核进行中"


def test_data_suspect_removes_a_buy():
    rows = pd.DataFrame([row("601225", "buy", 1, 0.9), row("601009", "next", 2, 0.8)])
    odd = {"601225": [{"kind": "data_suspect", "words": "最新报告的归母净利润 1.00 亿与卡片所用数据 2.00 亿相差 50%",
                       "hard": False, "suspect": True, "quote": "x", "date": "2026-08-20", "type": "2026年半年度报告"}]}
    out = review.apply(rows, "cn", states("601225", "601009"), odd)
    assert out[out["list"] == "buy"]["code"].tolist() == ["601009"]
    assert out[out["list"] == "removed"].iloc[0]["reason"].startswith("数据存疑：最新报告的归母净利润")


def test_cache_is_redone_for_a_new_source_a_new_list_a_new_name_or_after_seven_days():
    ids = ["2026-10-20 a", "2026-10-21 b"]
    entry = {"date": "2026-10-20", "role": "buy", "name": "The Bank of Nova Scotia", "sources": ids}
    valid = lambda role, ids, day=DAY, name="The Bank of Nova Scotia": review.valid(entry, role, ids, day, name)
    assert valid("buy", ids[:1])  # a source that aged out of the window changes nothing
    assert not valid("buy", ids + ["2026-10-24 c"])  # a new headline or filing
    assert not valid("hold", ids)  # new to its list
    assert not valid("buy", ids, date(2026, 10, 28))  # over 7 days old
    assert not valid("buy", ids, name="Bank Nova Scotia Halifax Pfd 3")  # renamed: the note read the old name


def test_the_note_goes_when_code_changes_a_finding(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "CACHE", tmp_path)
    monkeypatch.setattr(review, "ask", lambda client, content: ANSWERS["688585"])  # its takeover finding is dropped
    lines = review.lines_of(SOURCES["cn"]["688585"])
    assert review.review_one(None, "cn", row("688585", "sell", 1, 0.1), "sell", lines, DAY)["note"] == ""
    monkeypatch.setattr(review, "ask", lambda client, content: ANSWERS["00728"])  # kept as it was
    entry = review.review_one(None, "hk", row("00728", "buy", 1, 0.9), "buy", review.lines_of(SOURCES["hk"]["00728"]), DAY)
    assert entry["note"] == ANSWERS["00728"]["note"]


def test_budget_leaves_slow_reviews_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "CACHE", tmp_path)
    monkeypatch.setattr(review, "dotenv_values", lambda p: {"DEEPSEEK_API_KEY": "test"})
    monkeypatch.setattr(review, "ask", lambda client, content: time.sleep(2 if "601009" in content else 0) or
                        ANSWERS["601009" if "601009" in content else "601225"])
    lists = {"cn": pd.DataFrame([row("601225", "buy", 1, 0.9), row("601009", "buy", 2, 0.8)])}
    sources = {"cn": {c: SOURCES["cn"][c] for c in ("601225", "601009")}}
    started = time.monotonic()
    st = review.run(lists, sources, DAY, budget=0.5)["cn"]
    assert time.monotonic() - started < 1.5 and st["601225"]["status"] == "done" and st["601009"]["status"] == "pending"
    time.sleep(2)  # the slow one finishes in its thread and saves its cache: the next request is warm
    assert review.run(lists, sources, DAY, budget=0.5)["cn"]["601009"]["status"] == "done"
    monkeypatch.setattr(review, "dotenv_values", lambda p: {})
    monkeypatch.setattr(review, "CACHE", tmp_path / "empty")
    assert review.run(lists, sources, DAY, budget=0.5)["cn"]["601225"]["status"] == "unavailable"  # no DeepSeek


def test_the_cards_are_reviewed_first_in_their_order_then_the_benches(tmp_path, monkeypatch):
    """Within the keyword reply's budget what the cards show comes first: every market's Buy, then Hold, then Sell
    names, then the benches (small point (a) of 2026-11-02)."""
    monkeypatch.setattr(review, "CACHE", tmp_path)
    monkeypatch.setattr(review, "dotenv_values", lambda p: {"DEEPSEEK_API_KEY": "test"})
    monkeypatch.setitem(review.CFG, "workers", 1)
    asked = []
    monkeypatch.setattr(review, "ask", lambda client, content: asked.append(content.split()[0].removeprefix("股票：")) or
                        {"findings": [], "note": ""})
    lists = {"cn": pd.DataFrame([row("688585", "next", 2, 0.8), row("600576", "sell", 1, 0.1),
                                 row("601009", "hold", 1, 0.5), row("601225", "buy", 1, 0.9)]),
             "hk": pd.DataFrame([row("02650", "sell", 1, 0.1), row("00728", "buy", 1, 0.9)])}
    sources = {m: {c: SOURCES[m][c] for c in rows["code"]} for m, rows in lists.items()}
    review.run(lists, sources, DAY, budget=None)
    assert asked == ["601225", "00728", "601009", "600576", "02650", "688585"]


def test_source_parsers():
    cn = filings.parse_cn(json.loads((SAMPLES / "review_cninfo_600576_sample.json").read_text(encoding="utf-8")))
    assert cn[1]["title"] == "关于公司实际控制人收到立案告知书的公告" and cn[1]["date"] == "2026-10-10"
    assert classify("cn", cn[1]) == "risk" and cn[1]["url"].startswith("http://static.cninfo.com.cn/finalpage/")
    hk = filings.parse_hk(json.loads((SAMPLES / "review_hkex_02650_sample.json").read_text(encoding="utf-8")))
    warning = next(x for x in hk if x["title"] == "盈利警告")
    assert warning["date"] == "2026-08-07" and classify("hk", warning) == "earnings"
    assert classify("hk", next(x for x in hk if x["title"] == "翌日披露報表")) == "routine"  # dropped by filings.recent
    for market, title in (("cn", "关于公司债券未能按期足额兑付本息的公告"), ("cn", "关于新增债务逾期及担保逾期的公告"),
                          ("cn", "关于会计师事务所辞任的公告"), ("hk", "有關債券違約之公告")):
        assert classify(market, {"title": title}) == "risk", title  # not dropped as bond, guarantee or auditor routine
    us = filings.parse_us(json.loads((SAMPLES / "review_sec_eonr_sample.json").read_text(encoding="utf-8")), 1934152)
    restated = next(x for x in us if x["items"] == "4.02")
    assert restated["title"] == "8-K: Non-reliance on previous financial statements" and classify("us", restated) == "risk"
    em = news.parse_em(json.loads((SAMPLES / "news_em_00728_sample.json").read_text(encoding="utf-8")), "2026-10-20")
    assert em[0]["date"] >= "2026-10-20" and all(x["title"] for x in em)
    data = ["云铝股份：融资净偿还1205.65万元，融资余额20.22亿元", "中国石油大宗交易成交376.80万元", "港股通连续净买入股名单",
            "南向资金今日净卖出近17亿港元 阿里巴巴遭卖出居前", "云铝股份10月15日盘中跌幅达5%"]  # real 2026-10 headlines
    assert all(news.DATA_ITEMS.search(t) for t in data)
    assert not any(news.DATA_ITEMS.search(t) for t in ("中国电信第三季度营收净利润双降", "港股PCB概念股走弱，覆铜板缺货涨价"))
    rss = news.parse_rss((SAMPLES / "news_yahoo_mnst_sample.xml").read_text(encoding="utf-8"), "2026-10-01")
    assert len(rss) == 6 and rss[0]["date"] >= rss[-1]["date"] and "&amp;" not in "".join(x["title"] for x in rss)
