import json
from pathlib import Path

import pandas as pd
import pytest

from stockreport import universe
from stockreport.fetch import eastmoney, hkex, hkgb, yahoo

SAMPLES = Path(__file__).parent / "data"
load = lambda name: json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def test_hk_amounts_back_in_the_reporting_currency_then_hkd(tmp_path, monkeypatch):
    # Real main-indicator rows (2026-10-17), all in CNY: Tencent (CNY, December year), Alibaba (CNY,
    # March year, latest is the June quarter) and SHKP (HKD, June year, latest is the annual report).
    path, fx_cny, fx = tmp_path / "hk.csv", tmp_path / "fx_cny.csv", tmp_path / "fx.csv"
    eastmoney.hk_results(load("hk_mainindicator_sample.json")).to_csv(path, index=False)
    pd.DataFrame({"currency": "HKD", "date": ["2025-06-30", "2026-06-30"], "close": [0.9137, 0.8665]}).to_csv(fx_cny, index=False)
    pd.DataFrame({"currency": ["CNY", "HKD"], "per_usd": [6.6862, 7.8479]}).to_csv(fx, index=False)
    for module, name, value in ((eastmoney, "HK_RESULTS", path), (yahoo, "FX_CNY", fx_cny), (yahoo, "FX", fx)):
        monkeypatch.setattr(module, name, value)
    t = universe.hk_fundamentals(pd.Series({"00700": "CNY", "09988": "CNY", "00016": "HKD"}))
    hkd_per_cny = 7.8479 / 6.6862
    assert t.loc["00700", "np_ttm"] == pytest.approx((114115e6 + 224842e6 - 103449e6) * hkd_per_cny)  # H1 26 + FY25 - H1 25
    assert t.loc["09988", "revenue_ttm"] == pytest.approx((268953e6 + 1023670e6 - 247652e6) * hkd_per_cny)  # Q1 FY27 + FY26 - Q1 FY26
    assert t.loc["00016", "np_ttm"] == pytest.approx(18609552300 / 0.8665)  # annual report, back at the June 2026 rate
    assert t.loc["09988", "rev_yoy"] == pytest.approx(100 * (268953 / 247652 - 1), abs=1e-3)  # year-to-date growth, %


def test_trend_takes_this_and_next_fiscal_year():
    row = yahoo.parse_trend("00939", load("hk_trend_sample.json"))  # CCB, real reply 2026-10-17 (no key statistics)
    no_stats = dict.fromkeys(["bvps_y", "eps_ttm_y", "shares_y", "period_y"])
    assert row == {"code": "00939", "analysts": 12, "report_currency": "CNY", "e1_year": "2026-12", "eps_e0": 1.3,
                   "eps_e1": 1.32888, "eps_e2": 1.39175, "currency": "CNY"} | no_stats
    assert yahoo.parse_trend("X", {"quoteSummary": {"result": None}}) == {"code": "X", "analysts": 0,
                                                                         "report_currency": None} | no_stats


def test_hkex_titles_skip_routine_filings():
    # Ping An, real rows 2026-10-17: board lists, dividend forms and reposted A-share governance rules go.
    lines = hkex.parse_titles(load("hkex_titles_sample.json"), 10)
    assert lines[0] == "2026-10-15 非執行董事辭任"
    assert "2026-09-07 公告 選舉職工董事" in lines  # line breaks in a title collapse to a space
    assert not any(k in x for x in lines for k in ("表格", "制度", "海外監管公告 -", "&ldquo;"))


def test_hkgb_benchmark_10_year_yield():
    df = hkgb.parse_closings((SAMPLES / "hkgb_closings_sample.xls").read_bytes())  # real workbook 2026-10-16
    assert df.iloc[-1].to_dict() == {"date": "2026-10-16", "market": "hk", "y10": 3.994}
    assert len(df) == 11 and df["date"].is_monotonic_increasing


def test_trading_days_ignore_a_stray_row_and_a_lagging_index():
    # Real HK prices (Yahoo, 2026-10-08..20): ^HSI has no 2026-10-20 row though its stocks traded (10-19 was a holiday).
    prices = pd.read_csv(SAMPLES / "hk_prices_2026-10-20_sample.csv", dtype={"code": str, "date": str})
    assert universe.trading_days(prices)[-1] == "2026-10-20"
    # The 2026-10-21 06:30 table: only 02945 had a 10-20 row, which made "the last day" one stock's and emptied HK.
    stray = prices[(prices["date"] < "2026-10-20") | (prices["code"] == "02945")]
    assert universe.trading_days(stray)[-1] == "2026-10-16"
