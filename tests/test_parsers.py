import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stockreport.fetch.eastmoney import (consensus_table, deduct_table, forecast_table, is_open, quarter_ends,
                                         results_table)
from stockreport.fetch.tdx import parse_package
from stockreport.universe import finish, ttm

SAMPLES = Path(__file__).parent / "data"


def test_tdx_package_keeps_a_shares_and_csi300():
    # Cut from the real 2026-10-16 package: 5 A-shares, the CSI 300 index and an ETF (510300).
    df = parse_package((SAMPLES / "tdx_20261016_sample.zip").read_bytes(), "20261016", min_rows=1)
    assert sorted(df["code"]) == ["000001", "300750", "600519", "601398", "688981", "CSI300"]
    icbc = df.set_index("code").loc["601398"]
    assert (icbc["date"], icbc["close"], icbc["prev_close"]) == ("2026-10-16", 8.48, 8.5)
    assert icbc["amount"] == pytest.approx(2723358570.0)  # same turnover as Eastmoney reports
    assert (df["volume"] > 0).all()


def test_tdx_package_rejects_a_thin_file():
    with pytest.raises(RuntimeError):
        parse_package((SAMPLES / "tdx_20261016_sample.zip").read_bytes(), "20261016")


def test_quarter_ends_and_open_periods():
    assert quarter_ends(date(2026, 10, 17), 4) == [date(2026, 9, 30), date(2026, 6, 30),
                                                  date(2026, 3, 31), date(2025, 12, 31)]
    assert quarter_ends(date(2026, 2, 1), 1) == [date(2025, 12, 31)]
    assert is_open(date(2026, 9, 30), date(2026, 10, 17))
    assert not is_open(date(2026, 6, 30), date(2026, 10, 17))
    assert is_open(date(2025, 12, 31), date(2026, 4, 2))


def test_consensus_keeps_the_first_three_estimate_years():
    rows = json.loads((SAMPLES / "consensus_sample.json").read_text(encoding="utf-8"))  # real rows, 2026-10-17
    df = consensus_table(rows).set_index("code")
    moutai = df.loc["600519"]
    assert (moutai["e1_year"], moutai["analysts"]) == (2026, 43)
    assert [moutai["eps_e1"], moutai["eps_e2"], moutai["eps_e3"]] == pytest.approx([67.2493, 71.1259, 75.18], abs=1e-3)
    assert df.loc["688331", "eps_e2"] == pytest.approx(1.25)  # licensing spike: EPS falls in 2027
    two_estimates = dict(rows[0], YEAR_MARK2="A", SECURITY_CODE="000000")
    assert "000000" not in set(consensus_table([two_estimates])["code"])


def test_ttm_adds_last_full_year_and_removes_last_years_same_period():
    results = pd.DataFrame({
        "code": ["A"] * 3 + ["B"] * 2,
        "period": ["2026-06-30", "2025-12-31", "2025-06-30", "2025-12-31", "2024-12-31"],
        "revenue": [60.0, 100.0, 50.0, 80.0, 70.0],
        "np": [6.0, 10.0, 4.0, 8.0, 7.0],
    })
    out = ttm(results)
    assert out.loc["A", "revenue_ttm"] == 110.0  # 60 + 100 - 50
    assert out.loc["A", "np_ttm"] == 12.0
    assert out.loc["B", "revenue_ttm"] == 80.0  # annual report is already trailing-12-month
    assert out.loc["A", "period"] == "2026-06-30"


def test_ttm_is_missing_without_last_years_same_period():
    results = pd.DataFrame({"code": ["A", "A"], "period": ["2026-06-30", "2025-12-31"],
                            "revenue": [60.0, 100.0], "np": [6.0, 10.0]})
    assert pd.isna(ttm(results).loc["A", "revenue_ttm"])


def test_cninfo_titles_drop_routine_filings():
    # Cut from the real 2026-10-17 CNINFO query for 301308 (14 announcements, newest first).
    from stockreport.fetch.cninfo import parse_titles

    payload = json.loads((SAMPLES / "cninfo_sample.json").read_text(encoding="utf-8"))
    titles = parse_titles(payload, limit=10)
    assert titles[0] == "2026-10-15 2026年前三季度业绩预告"  # times are converted to Beijing dates
    assert not any("翌日披露报表" in t or "董事会会议召开日期" in t for t in titles)
    assert len(titles) == len(set(titles)) <= 10
    assert parse_titles(payload, limit=2) == titles[:2]


def test_note_length_counts_digits_as_half_and_cuts_at_a_clause():
    from stockreport.notes import shorten, width

    numeric = "现价19.08高于P/S公允价上限13.36，空间-60.8%；近12个月净亏21.06亿、ROE-10.9%，估值与盈利背离。"
    assert len(numeric) > 60 and width(numeric) <= 60  # a real note that used to be cut
    long = "估值低于同行且盈利质量高，" * 3 + "但股价波动较大需要控制仓位并关注下季利润变化情况。"
    assert shorten(long, 60) == "估值低于同行且盈利质量高，" * 2 + "估值低于同行且盈利质量高。"
    assert shorten("估值合理。", 60) == "估值合理。"
    from stockreport.notes import words_only
    assert words_only("利润下滑三成，需留意") == "" and words_only("近期PE 8") == ""  # figures, in characters or digits
    assert words_only("近十二个月亏损、三季度承压") == "近十二个月亏损、三季度承压"  # periods are words


def test_keyword_match():
    from stockreport.listener import is_keyword

    for text in ["股票报告", "股票简报。", " Stock Report! ", "stock  brief？", "股票报告～"]:
        assert is_keyword(text), text
    for text in ["股票报告呢", "请发股票报告", "stock", "hi", ""]:
        assert not is_keyword(text), text


def test_ttm_includes_deducted_eps_when_the_table_has_it():
    results = pd.DataFrame({"code": ["A"] * 3, "period": ["2026-06-30", "2025-12-31", "2025-06-30"],
                            "revenue": [60.0, 100.0, 50.0], "np": [6.0, 10.0, 4.0], "eps_deduct": [0.5, 0.8, 0.3]})
    assert ttm(results).loc["A", "eps_deduct_ttm"] == pytest.approx(1.0)  # 0.5 + 0.8 - 0.3
    assert "eps_deduct_ttm" not in ttm(results.drop(columns="eps_deduct"))


def test_cash_conversion_is_clipped_and_needs_a_margin():
    # 兖煤澳大利亚-like: profit down 90%, cash conversion 31.6; a near-zero margin makes the ratio meaningless. The other
    # figures are kept as reported (no winsorizing: the cards show them).
    df = pd.DataFrame({"cash_conv": [31.6, -5.0, 0.8, 2.0], "roe": [9.0, 0.1, 0.1, 0.1],
                       "np_ttm": [10.0, 10.0, 10.0, 1.0], "revenue_ttm": [100.0] * 4}, index=list("ABCD"))
    out, _ = finish(df, {"stages": {}, "dropped": {}}, {})
    assert out["cash_conv"].tolist()[:3] == [3.0, -1.0, 0.8] and out.loc["A", "roe"] == 9.0
    assert pd.isna(out.loc["D", "cash_conv"])  # net margin 1% < 2%


def test_deduct_table_keeps_the_first_notice_date():
    rows = json.loads((SAMPLES / "cn_deduct_sample.json").read_text(encoding="utf-8"))  # 主要财务指标, real rows
    df = deduct_table(rows, "2025-09-30").set_index("code")
    assert df.loc["000001", "deduct"] == 38_269_000_000 and df.loc["000001", "notice_date"] == "2025-10-25"
    assert df.loc["000002", "deduct"] < 0 and set(df["period"]) == {"2025-09-30"}


def test_results_table_keeps_deducted_eps_and_roe():
    rows = json.loads((SAMPLES / "cn_history_sample.json").read_text(encoding="utf-8"))["annual"]  # FY2025, real rows
    df = results_table(rows).set_index("code")
    assert df.loc["600519", ["eps", "eps_deduct", "roe"]].tolist() == pytest.approx([65.66, 65.64, 32.53])
    assert df.loc["002466", "eps_deduct"] == pytest.approx(0.22) and df.loc["002466", "notice_date"] == "2026-03-28"


def test_forecast_table_one_row_per_indicator():
    rows = json.loads((SAMPLES / "cn_history_sample.json").read_text(encoding="utf-8"))["forecasts"]
    df = forecast_table(rows)
    assert len(df) == 3 and set(df["code"]) == {"300505"} and set(df["period"]) == {"2026-09-30"}
    profit = df[df["item"] == "归属于上市公司股东的净利润"].iloc[0]
    assert (profit["type"], profit["amount_low"], profit["amount_high"]) == ("略减", 160000000, 180000000)
    assert (profit["yoy_low"], profit["yoy_high"], profit["notice_date"]) == (-47.44, -40.87, "2026-10-10")
