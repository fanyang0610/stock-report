"""Stage 11: the words' checks (AGENTS.md rule 2), the agreement with the screening, the annual report's section cutting
on small samples, and the end-to-end dry run of one report from saved data with DeepSeek mocked."""

import json
import shutil
from pathlib import Path

import pytest

from stockreport import research
from stockreport.research import compare, report, texts, words

DATA = Path(__file__).parent / "data" / "research_report"
K = {"rating": ("我们的评级", "持有"), "rev_cagr_5y": ("近 5 年营收年均增长", "+11.9%"), "pe_ttm": ("市盈率", "22.1倍"),
     "pb": ("市净率", "0.8倍"), "pe_peers": ("同行市盈率中位数", "21.5倍")}
LINES = [{"type": "年报", "date": "2026-04-17", "text": "公司营收增长15.3%，C919 订单饱满。"},
         {"type": "新闻", "date": "2026-11-01", "text": "某公司：维持高分红政策不变"}]


@pytest.mark.parametrize("text, src, why", [
    ("营收增长{rev_cagr_5y}，估值{pe_ttm}", [], None),  # figures as keys
    ("近5年营收增长{rev_cagr_5y}", [], None),  # a horizon the keys' labels use
    ("营收增长11.9%", [], "figure"),  # a key's value written out
    ("营收增长15.3%，C919 订单饱满", [1], None),  # figures in the source it cites
    ("营收增长15%", [1], "figure"),  # rounded: not the source's figure
    ("营收增长15.3%", [2], "figure"),  # in a source it doesn't cite
    ("「维持高分红政策不变」", [2], None),
    ("「维持高分红政策大幅提高」", [2], "quote"),
    ("{brand_value}", [], "unknown key"),
    ("建议买入", [1], "rating word"),  # a rating other than code's
    ("维持持有的看法", [1], None),
    ("2025 年营收增长{rev_cagr_5y}", [], None),  # a year in the material
    ("2031 年营收翻三倍", [1], "figure"),
    ("行业竞争加剧", [], "no source"),
    ("营收增长十五%", [1], "figure"), ("营收将增长三分之一", [1], "figure"), ("利润翻番", [1], "figure"),
    ("增长约十五", [1], "figure"), ("营收接近一半来自海外", [1], "figure"), ("一体化程度高，两大品牌领先", [1], None),
    ("市盈率{pe_ttm}高于同行{pe_peers}", [], None),
    ("市盈率{pe_ttm}低于同行{pe_peers}", [], "contradicts"),
    ("市盈率{pe_ttm}，低于同行{pe_peers}", [], "contradicts"),  # the comparison after a comma
    ("市净率{pb}低于市盈率{pe_ttm}", [], "different measures"),
])
def test_check(text, src, why):
    got = words.check(text, src, K, LINES, {"2025"})
    assert (got is None) if why is None else (got is not None and why in got)


def test_fill_drops_a_unit_written_after_a_key():
    assert words.fill("增长{rev_cagr_5y}%，市盈率{pe_ttm}倍", K) == "增长+11.9%，市盈率22.1倍"
    assert words.fill("共{x}看多", {"x": ("", "42 家中 39 家看多")}) == "共42 家中 39 家看多"


def view(rating, fifth, momentum="C", value="C"):
    f = {"screening": {"rating": rating, "fifth": fifth, "in_universe": True, "g_momentum": momentum, "g_value": value,
                       "g_quality": "C", "g_growth": "C", "score_rank": 10, "universe": 800}, "peers": {}}
    return f


@pytest.mark.parametrize("ours, rating, fifth, agreement", [
    ("买入", None, "偏多", "一致"), ("持有", None, "中性", "一致"), ("买入", None, "中性", "部分一致"),
    ("持有", "卖出", "偏空", "部分一致"), ("买入", None, "偏空", "相反"), ("卖出", "买入", "偏多", "相反"), ("不评级", None, "中性", None)])
def test_agreement(ours, rating, fifth, agreement):
    assert compare.screening(view(rating, fifth), {"rating": ours, "type": "ordinary"}, 20.0)["agreement"] == agreement


def test_a_strong_momentum_name_research_rates_sell_names_momentum():
    got = compare.screening(view("买入", "偏多", momentum="A"), {"rating": "卖出", "type": "ordinary"}, 20.0)
    assert got["agreement"] == "相反" and any(d.startswith("动量") for d in got["drivers"])


CN = """第二节 公司简介和主要财务指标 ......5
第三节 管理层讨论与分析 ......8
第四节 公司治理 ......23
第三节 管理层讨论与分析
一、报告期内公司从事的业务情况
公司主要业务是茅台酒及系列酒的生产与销售。
√适用 □不适用
二、报告期内核心竞争力分析
公司拥有品质、品牌、工艺组成的核心竞争力。
三、公司关于公司未来发展的讨论与分析
(一)行业格局和趋势
行业进入调整期。
(二)可能面对的风险
一是宏观经济风险；二是安全风险。
第四节 公司治理
一、公司治理相关情况说明"""

US = """Item 1. Business 3
Item 1A. Risk Factors 9
Item 7. Management's Discussion 20
Item 1. Business
The Company designs, manufactures and markets smartphones and personal computers.
Item 1A. Risk Factors
The Company's business can be affected by economic conditions.
""" + "Long paragraph explaining the risk in detail and at length. " * 10 + """
Item 2. Properties
The Company's headquarters are in Cupertino.
Item 7. Management's Discussion and Analysis
Net sales grew because of iPhone and Services.
Item 8. Financial Statements"""

HK = "\n".join(["CONTENTS", " 4 CHAIRMAN’S STATEMENT", " 7 MANAGEMENT DISCUSSION AND ANALYSIS", "Chairman’s Statement",
                "We sustained healthy growth in 2025.", "BUSINESS REVIEW AND OUTLOOK", "AI improved our ad targeting.",
                "Management Discussion and Analysis", "Revenues grew on games and ads."]
               + [x for i in range(4) for x in ("Management Discussion and Analysis", "Revenues 751,766 660,257", f"Marketing services rose in part {'ABCD'[i]}.")]
               + ["Five Year Plan, with GDP surpassing a record level, and growth was steady.", "Directors’ Report",
                  "The directors present their report."])


def test_cut_cn_takes_the_mdna_topics_not_the_contents():
    got = texts.cut_cn(CN)
    assert got["business"].endswith("茅台酒及系列酒的生产与销售。") and "适用" not in got["business"]
    assert "核心竞争力" in got["moat"] and "宏观经济风险" in got["risks"] and "公司治理" not in got["outlook"]


def test_cut_us_takes_each_item_body_and_the_risk_headings():
    got = texts.cut_us(US, "10-K 2026-11-03")
    assert got["business"].startswith("The Company designs") and "Cupertino" not in got["business"]
    assert got["risks"] == "The Company's business can be affected by economic conditions."
    assert got["mdna"] == "Net sales grew because of iPhone and Services."


def test_cut_hk_keeps_a_heading_repeated_as_page_header_and_stops_at_the_next_section():
    got = texts.cut_hk(HK)
    assert got["chairman"].startswith("We sustained") and "Revenues grew" not in got["chairman"]
    assert "rose in part D." in got["mdna"] and "Five Year Plan" in got["mdna"] and "directors present" not in got["mdna"]
    assert "Discussion and Analysis" not in got["mdna"] and "751,766" not in got["mdna"]  # page headers, table rows
    assert got["outlook"].startswith("AI improved")


def test_report_from_saved_data(tmp_path, monkeypatch):
    """End-to-end dry run: 贵州茅台's saved fact sheet, valuation and prices (2026-11-09), DeepSeek mocked; the words are
    checked and filled, the PDF renders and the text summary fits WeChat's 4,000 bytes."""
    home = tmp_path / "research" / "cn" / "600519"
    shutil.copytree(DATA / "600519", home)
    monkeypatch.setattr(research, "ROOT", tmp_path / "research")
    monkeypatch.setattr(report, "REPORTS", tmp_path / "reports")
    f, v = (json.loads((home / n).read_text()) for n in ("facts.json", "valuation.json"))
    lines = [{"type": "年报", "part": "主要业务", "date": "2026-04-17", "doc": "贵州茅台2025年年度报告",
              "text": "公司主要业务是茅台酒及系列酒的生产与销售。"},
             {"type": "新闻", "date": "2026-11-03", "text": "茅台品牌价值达583.80亿美元，蝉联全球烈酒品牌第一"}]
    item = lambda text, src=(1,), title="": {"title": title, "text": text, "src": list(src)}
    answers = {
        words.BUSINESS: {"business": [item("主要业务是茅台酒及系列酒的生产与销售"), item("行业龙头地位稳固", [])], "industry": [],
                         "moat": [item("品牌价值达583.80亿美元", [2])], "management": [], "model": "其他"},
        words.BULL: {"bull": [item("近5年营收年均增长{rev_cagr_5y}", [], "成长稳健")]},
        words.BEAR: {"bear": [item("市盈率{pe_ttm}，高于同行中位数{ind_pe}", [], "估值不低")]},
        words.THESIS: {"conclusion": item("品牌和现金流强，现价{price}低于目标价{target}", []),
                       "points": [item("护城河来自品牌", [2], "品牌")], "risks": [item("需求疲软，营收增长放缓到 3%", [1], "需求")],
                       "outlook": [], "catalysts": [], "change_view": [], "vs_street": item("我们用的资本成本{wacc}", []),
                       "vs_screening": item("筛选的价值评级{scr_value}", []), "moves": []}}

    class Fake:
        def __init__(self, model):
            self.calls = []

        def ask(self, system, user):
            return next(a for task, a in answers.items() if user.startswith(task))

        def cost(self):
            return {"model": "mock", "calls": 4}

    monkeypatch.setattr(words, "Client", Fake)
    screen, street = compare.screening(f, v, 22.4), compare.street(f, v)
    w = words.write(f, v, lines, screen["keys"], street, screen)
    assert w["status"] == "done" and w["moat"][0]["text"] == "品牌价值达583.80亿美元"
    assert [d["why"] for d in w["dropped"]] == ["no source and no key", "figure not in a cited source: 3"]
    assert v["rating"] in w["conclusion"]["raw"] or "{price}" in w["conclusion"]["raw"]
    assert "{" not in w["conclusion"]["text"] and w["bear"][0]["text"].startswith("市盈率22.1倍")
    doc = {"code": "600519", "market": "cn", "name": f["name"], "date": "2026-11-09", "lines": lines, "words": w,
           "sections": {"doc": "贵州茅台2025年年度报告", "date": "2026-04-17", "note": None, "parts": ["business"]},
           "screen": screen | {"keys": None}, "review": {"findings": []}, "timings": {}}
    (home / "report.json").write_text(json.dumps(doc, ensure_ascii=False))
    pdf = report.render("cn", "600519")
    assert pdf.exists() and pdf.stat().st_size > 20_000
    text = report.summary(f, v, doc)
    assert len(text.encode("utf-8")) <= 4000 and f"评级：{v['rating']}" in text and "品牌和现金流强" in text
