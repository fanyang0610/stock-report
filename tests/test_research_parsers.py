"""Research stage 9: the per-stock parsers on small saved samples (tests/data/research_*, damodaran_*; captured
2026-11-08)."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stockreport.research import cn, damodaran, hk, listings, sources, us

DATA = Path(__file__).parent / "data"
CN = json.loads((DATA / "research_cn_sample.json").read_text())


def test_cn_general_statements():
    s = CN["600519"]
    df = cn.statement_rows(s["income"], s["balance"], s["cash"], s["main"])
    fy = df[df["period"] == "2025-12-31"].iloc[0]
    assert fy["months"] == 12 and fy["currency"] == "CNY" and fy["notice"] == "2026-04-17"
    assert fy["revenue"] == pytest.approx(172054171890.91) and fy["ni"] == pytest.approx(82320067101.68)
    assert fy["gp"] == pytest.approx(fy["revenue"] - fy["cogs"]) and fy["shares"] == pytest.approx(1250081601)
    assert fy["equity"] == pytest.approx(244637811032.18) and fy["ocf"] == pytest.approx(61522204989.35)
    assert df.loc[df["period"] == "2026-09-30", "months"].iloc[0] == 9


def test_cn_bank_statements():
    s = CN["600036"]
    fy = cn.statement_rows(s["income"], s["balance"], s["cash"], s["main"]).query("period == '2025-12-31'").iloc[0]
    assert fy["revenue"] == pytest.approx(337532e6) and fy["ni"] == pytest.approx(150181e6) and pd.isna(fy["cogs"])
    assert fy["npl"] == pytest.approx(0.94) and fy["car"] == pytest.approx(18.24) and fy["nim"] == pytest.approx(1.87)


def test_cn_consensus_and_flows(monkeypatch):
    rec = CN["flows_600519"]
    monkeypatch.setattr(cn, "get", lambda report, *a, **k: rec.get(report, []))

    class Reports:  # the broker-report archive: no reports in the sample
        def __init__(self, *a, **k): pass
        def get(self, *a, **k): return type("R", (), {"json": lambda self: {"data": []}})()
    monkeypatch.setattr(cn, "Http", Reports)
    c = cn.consensus("600519", date(2026, 11, 8))
    assert c["eps"]["2026"] == pytest.approx(66.815) and c["analysts"] == 42 and c["target_high"] == 2030
    f = cn.flows("600519", date(2026, 11, 8))
    assert f["margin"]["balance"] > 0 and f["pledge"]["ratio"] == pytest.approx(0.14)
    assert f["dividends"][0]["dps"] == pytest.approx(28.02423) and f["holders"][0]["count"] == 278364


def test_hk_statements_back_in_the_reporting_currency(monkeypatch):
    """Eastmoney's HK amounts are CNY at the period end's rate: SHKP's FY2026 profit CNY 18.61bn = HKD 21.43bn."""
    rows = json.loads((DATA / "research_hk_sample.json").read_text())
    monkeypatch.setattr(hk.yahoo, "cny_per", lambda cur, day: pd.Series(0.8686, index=cur.index))
    shares = hk.shares_of({"HOLDER_PROFIT": 18.61e9, "BASIC_EPS": 6.42, "ISSUED_COMMON_SHARES": 2897780274})
    df = hk.to_currency(hk.statement_rows(rows, {"2026-06-30": shares}), "HKD")
    fy = df[df["period"] == "2026-06-30"].iloc[0]
    assert fy["currency"] == "HKD" and fy["months"] == 12 and fy["issued"] == 2897780274
    assert fy["shares"] == pytest.approx(18.61e9 / 6.42)  # the weighted average, by profit over basic EPS
    assert fy["ni"] == pytest.approx(21.43e9, rel=0.005) and fy["revenue"] == pytest.approx(94.19e9, rel=0.005)
    assert fy["capex"] > 0 and fy["div_paid"] > 0


def test_us_statements_and_ttm():
    payload = json.loads((DATA / "research_us_aapl_facts.json").read_text())
    df = us.parse_statements("AAPL", payload)
    fy = df[df["period"] == "2026-09-26"].iloc[0]
    assert fy["revenue"] == 478834e6 and fy["ni"] == 132175e6 and fy["cur_assets"] == 173857e6
    assert fy["buyback"] == 86390e6 and fy["debt"] == pytest.approx(80111e6) and fy["eps"] == pytest.approx(8.98)
    latest = us.latest("AAPL", payload, date(2026, 11, 8))
    assert latest["period"] == "2026-09-26" and latest["revenue"] == 478834e6 and latest["revenue_prior"] == 416161e6


def test_nasdaq_consensus_and_flows():
    n = json.loads((DATA / "research_nasdaq_sample.json").read_text())
    c = us.parse_consensus(n["forecast"], n["target"], n["ratings"])
    assert c["eps"]["2027"] == pytest.approx(9.7) and c["target_mean"] == pytest.approx(340.14) and c["ratings"]["buy"] == 15
    f = us.parse_flows(n["short"], n["insider"])
    assert f["short"][0]["shares"] == 131591865 and f["insider"]["sells"] == (26, 46)


def test_yahoo_annual_and_summary():
    y = json.loads((DATA / "research_yahoo_sample.json").read_text())
    a = sources.parse_annual(y["annual_aapl"])
    assert a.iloc[-1]["revenue"] == 478834e6 and a.iloc[-1]["capex"] > 0 and a.iloc[-1]["currency"] == "USD"
    s = sources.parse_summary(y["summary_0700"], date(2026, 11, 8))
    assert s["currency"] == "HKD" and s["report_currency"] == "CNY" and s["analysts"] > 0 and s["target_mean"] > 0
    assert set(sources.eps_years(s["estimates"])) == {"2026", "2027"}


def test_damodaran_tables():
    r = damodaran.ratings((DATA / "damodaran_ratings_sample.xls").read_bytes())
    assert set(r["table"]) == {"large", "financial", "smaller", "infrastructure"}
    large = r[r["table"] == "large"]
    assert large.iloc[-1]["rating"] == "Aaa/AAA" and large.iloc[-1]["spread"] == pytest.approx(0.004) and len(large) == 15
    capex = damodaran.industry_sheet((DATA / "damodaran_capex_sample.xls").read_bytes(), damodaran.COLUMNS["capex"])
    adv = capex[capex["industry"] == "Advertising"].iloc[0]
    assert adv["sales_to_capital"] == pytest.approx(3.8532841) and len(capex) > 90


def test_listings_parsers():
    hkx = listings.parse_hkex((DATA / "hkex_lots_sample.xlsx").read_bytes())
    assert set(hkx["kind"]) <= {"ordinary", "reit"} and hkx["code"].str.fullmatch(r"\d{5}").all() and len(hkx) > 0
    cninfo = listings.parse_cninfo({"stockList": [{"code": "600519", "zwjc": "贵州茅台", "pinyin": "gzmt", "category": "A股"},
                                                  {"code": "900901", "zwjc": "云赛B股", "pinyin": "ysbg", "category": "B股"}]}, "A股")
    assert list(cninfo["code"]) == ["600519"] and cninfo.iloc[0]["name"] == "贵州茅台"


def test_a_20f_filer_takes_its_last_fiscal_year_as_trailing():
    # Novo Nordisk files 20-F (no 10-Q): the last annual row stands for the trailing twelve months
    import pandas as pd
    from stockreport.research import us
    st = pd.DataFrame({"period": ["2024-12-31", "2025-12-31", "2025-06-30"], "months": [12, 12, 6],
                       "revenue": [290.4, 309.1, 150.0], "ni": [101.0, 102.4, 50.0], "gp": [246.0, 258.0, 125.0],
                       "ocf": [121.0, 119.1, 60.0], "pretax": [128.0, 130.5, 64.0], "interest": [1.0, 6.8, 3.0],
                       "da": [12.0, 14.7, 7.0], "capex": [47.0, 60.1, 30.0], "equity": [143.5, 194.0, 170.0],
                       "shares": [4.44, 4.44, 4.44], "notice": ["2025-02-05", "2026-02-04", "2025-08-06"]})
    x = us.from_annual(st)
    assert x["period"] == "2025-12-31" and x["basis"] == "FY" and x["revenue"] == 309.1 and x["revenue_prior"] == 290.4
    assert x["ni_prior"] == 101.0 and x["capex"] == 60.1 and x["equity"] == 194.0 and x["notice"] == "2026-02-04"
    assert us.from_annual(st.iloc[:0]) == {}


def test_an_adr_counts_shares_in_its_own_units():
    # TSMC: 25.93bn shares, an ADR of 5 at 413.35 against a 2,143.8bn market value -> 5.0 shares a unit; Apple 1
    from stockreport.research import facts
    assert facts.units(413.35, 25.93e9, {"mcap": 2143.8e9}, None) == pytest.approx(5.0, rel=0.01)
    assert facts.units(355.63, 14.53e9, {"mcap": 5168e9}, None) == 1.0
    assert facts.units(413.35, 25.93e9, {}, 2141.6e9) == pytest.approx(5.0, rel=0.01)  # Nasdaq's value when Tencent fails
    assert facts.units(413.35, 25.93e9, {}, None) == 1.0


def test_a_20f_filers_newest_year_from_the_second_source():
    import pandas as pd
    from stockreport.research import facts
    st = pd.DataFrame({"period": ["2023-12-31", "2024-12-31"], "months": [12, 12], "revenue": [2161.7, 2894.3]})
    second = pd.DataFrame({"period": ["2024-12-31", "2025-12-31"], "revenue": [2894.3, 3809.1], "currency": ["TWD"] * 2})
    out, years = facts.newer_years(st, second)
    assert years == ["2025-12-31"] and out["revenue"].tolist() == [2161.7, 2894.3, 3809.1] and out["months"].tolist() == [12] * 3
    assert facts.newer_years(st, second.iloc[:1])[1] == []


def us_segments(name: str) -> pd.DataFrame:
    from stockreport.research import segments
    facts = segments.parse_instance((DATA / f"segments_us_{name}_sample.xml").read_bytes())  # trimmed 10-K / 20-F
    return segments.breakdowns(facts, segments.parse_labels(json.loads((DATA / f"segments_us_{name}_labels.json").read_text())))


def test_us_segments_are_parts_that_add_up_not_subtotals():
    # Amazon's FY2025 10-K: three segments with operating income; the seven sales groups, not product / service
    df = us_segments("amzn")
    fy = df[df["period"] == "2025-12-31"].set_index(["by", "item"])
    aws = fy.loc[("segment", "AWS")]
    assert aws["revenue"] == pytest.approx(128725e6) and aws["op_income"] == pytest.approx(45606e6)
    assert aws["op_margin"] == pytest.approx(0.3543, abs=1e-4) and aws["op_share"] == pytest.approx(0.5703, abs=1e-4)
    assert len(fy.loc["segment"]) == 3 and fy.loc["segment", "share"].sum() == pytest.approx(1)
    assert ("product", "Advertising services") in fy.index and len(fy.loc["product"]) == 7
    assert fy.loc["product", "share"].sum() == pytest.approx(1) and fy.loc["region", "share"].sum() == pytest.approx(1)
    assert fy.loc["product", "gross_margin"].isna().all() and sorted(df["period"].unique()) == ["2023-12-31", "2024-12-31", "2025-12-31"]
    assert segments_unallocated(df, "2025-12-31") is None  # Amazon's segments carry all of its operating income


def segments_unallocated(df, period):
    rows = df[(df["period"] == period) & (df["item"] == "未分配（总部及调节项）")]
    return rows["op_income"].iloc[0] if len(rows) else None


def test_us_segments_with_eliminations_in_the_reporting_currency():
    # JD's 20-F: CNY (its USD convenience translation of the latest year left out), the eliminations between segments
    # tagged on the consolidation axis, a loss-making segment (no profit shares), corporate costs as the remainder
    df = us_segments("jd")
    fy = df[(df["period"] == "2025-12-31") & (df["by"] == "segment")].set_index("item")
    assert fy.loc["JD Retail", "revenue"] == pytest.approx(1126.399e9, rel=1e-6)
    assert fy.loc["分部间抵消", "revenue"] == pytest.approx(-83.742e9, rel=1e-6) and pd.isna(fy.loc["分部间抵消", "op_margin"])
    assert fy["share"].sum() == pytest.approx(1, abs=0.005) and fy["op_share"].isna().all()
    assert fy.loc["New Businesses", "op_margin"] < 0 and fy.loc["JD Retail", "gross_margin"] == pytest.approx(0.1759, abs=1e-4)
    assert segments_unallocated(df, "2025-12-31") == pytest.approx(-7.256e9, rel=1e-3)


def test_segment_partition_and_checked_measures():
    from stockreport.research import segments
    values = {"product": 60, "service": 40, "a": 30, "b": 30, "c": 25, "d": 15, "elim": -5}
    assert sorted(segments.partition(values, 95, {"elim"})) == ["a", "b", "c", "d", "elim"]  # the parts, eliminations in
    # a negative that isn't an offsetting line can't net a subtotal back out: {product, a, b, c, d, odd} would add up
    assert sorted(segments.partition(values | {"elim": 0, "odd": -60}, 100)) == ["a", "b", "c", "d"]
    assert segments.partition({"a": 50, "b": 30}, 100) is None and segments.partition({"a": 100}, 100) is None
    got = {"a": 10.0, "b": 5.0}
    assert segments.measure(got.get, ["a", "b"], 15.0, ["a", "b"]) == got
    assert segments.measure(got.get, ["a", "b"], 20.0, ["a", "b"]) == {}  # partial tags don't add up: dropped
    assert segments.measure(got.get, ["a", "b", "c"], 15.0, ["a", "b", "c"]) == {}


def test_hk_segment_note_from_the_annual_reports_layout_text():
    from stockreport.research import segments
    tencent = segments.page_tables((DATA / "segments_hk_tencent_page.txt").read_text())  # 2025 annual report p.194
    assert [t["year"] for t in tencent] == [2025, 2024]
    assert tencent[0]["names"][:4] == ["VAS", "Marketing Services", "FinTech and Business Services", "Others"]
    revenue = {2025: ("2025-12-31", 751.766e9), 2024: ("2024-12-31", 660.257e9)}  # the statements', CNY
    df = segments.from_report(tencent, revenue, "ANNUAL REPORT 2025").set_index(["period", "item"])
    vas = df.loc[("2025-12-31", "VAS")]
    assert vas["revenue"] == pytest.approx(369.281e9) and vas["gross_margin"] == pytest.approx(222296 / 369281)
    assert df.loc["2024-12-31", "share"].sum() == pytest.approx(1) and df["op_income"].isna().all()
    assert segments.from_report(tencent, {2025: ("2025-12-31", 700e9)}, "x").empty  # not the company's revenue
    # Anta: names offset to the right of the amounts, a bulleted row label, segment results, an unallocated column
    anta = segments.page_tables((DATA / "segments_hk_anta_page.txt").read_text())[0]
    assert anta["names"][:3] == ["ANTA brand", "FILA brand", "All other brands"] and anta["op"][3] == -274
    df = segments.from_report([anta], {2025: ("2025-12-31", 80.219e9)}, "Annual Report 2025").set_index("item")
    assert df.loc["FILA brand", "op_margin"] == pytest.approx(7418 / 28469) and len(df) == 4
