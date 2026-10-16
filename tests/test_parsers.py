import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stockreport.fetch.eastmoney import consensus_table, is_open, quarter_ends
from stockreport.fetch.tdx import parse_package
from stockreport.universe import ttm

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


def test_note_reply_is_validated():
    from stockreport.notes import TooLong, parse_reply

    ok = parse_reply('```json\n{"note": "估值低于同行。", "risk": "周期回落", "flag": "none", "reason": "无"}\n```')
    assert ok == {"note": "估值低于同行。", "risk": "周期回落", "flag": "none", "reason": "无"}
    with pytest.raises(ValueError):
        parse_reply('{"note": "x", "risk": "y", "flag": "buy_more", "reason": ""}')
    with pytest.raises(ValueError):
        parse_reply('{"note": "", "risk": "y", "flag": "none", "reason": ""}')
    with pytest.raises(ValueError):
        parse_reply("not json")
    long = '{"note": "%s", "risk": "风险", "flag": "one_off_gain", "reason": "r"}' % ("字" * 70)
    with pytest.raises(TooLong):
        parse_reply(long)
    cut = parse_reply(long, enforce_length=False)
    assert len(cut["note"]) == 60 and cut["note"].endswith("…") and cut["flag"] == "one_off_gain"


def test_keyword_match():
    from stockreport.listener import is_keyword

    for text in ["股票报告", "股票简报。", " Stock Report! ", "stock  brief？", "股票报告～"]:
        assert is_keyword(text), text
    for text in ["股票报告呢", "请发股票报告", "stock", "hi", ""]:
        assert not is_keyword(text), text
