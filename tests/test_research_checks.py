"""Research stage 9: the accounting checks and the fact sheet's arithmetic, on small hand-computed samples."""

import pandas as pd
import pytest

from stockreport.research import checks, sheet

YEARS = pd.DataFrame([  # t-2, t-1, t
    {"period": "2023-12-31", "revenue": 900, "assets": 900, "ni": 60},
    {"period": "2024-12-31", "revenue": 1000, "cogs": 600, "gp": 400, "receivables": 100, "cur_assets": 400, "ppe": 300,
     "assets": 1000, "da": 50, "sga": 100, "cur_liab": 200, "lt_debt": 200, "ni": 80, "ocf": 90, "shares": 100},
    {"period": "2025-12-31", "revenue": 1200, "cogs": 700, "gp": 500, "receivables": 150, "cur_assets": 500, "ppe": 330,
     "assets": 1200, "da": 55, "sga": 115, "cur_liab": 260, "lt_debt": 220, "ni": 100, "ocf": 70, "shares": 100,
     "retained": 300, "pretax": 140, "interest": 10, "equity": 500, "liabilities": 700}])


def test_beneish_m_score():
    b = checks.beneish(YEARS)
    assert b["dsri"] == pytest.approx(1.25) and b["gmi"] == pytest.approx(0.96) and b["aqi"] == pytest.approx(1.027778, abs=1e-6)
    assert b["depi"] == pytest.approx(1.0) and b["sgai"] == pytest.approx(0.958333, abs=1e-6) and b["tata"] == pytest.approx(0.025)
    assert b["m_score"] == pytest.approx(-1.957356, abs=1e-5) and b["flag"] is False  # Beneish 1999 cut-off: -1.78


def test_beneish_needs_every_input():
    b = checks.beneish(YEARS.drop(columns="sga"))
    assert b["m_score"] is None and b["missing"] == ["sgai"]


def test_piotroski_f_score():
    f = checks.piotroski(YEARS)
    assert f["f_score"] == 7 and f["signals_known"] == 9
    assert f["cfo_above_profit"] is False and f["current_ratio_up"] is False and f["leverage_down"] is True


def test_altman_z_and_z2():
    z = checks.altman(YEARS, market_cap=2000)
    assert z["z"] == pytest.approx(3.716786, abs=1e-5) and z["z_zone"] == "safe"
    assert z["z2"] == pytest.approx(3.717, abs=1e-6) and z["z2_zone"] == "safe"


def test_quality_screen_exemption_b():
    """A thin net margin with a high gross margin, back above 5% last year: exemption B, not an exclusion."""
    rows = [{"period": f"{y}-12-31", "revenue": 100, "gp": 50, "ni": n, "ocf": n * 1.2, "capex": 1, "equity": 40,
             "shares": 10, "pretax": n * 1.3, "interest": 0} for y, n in zip(range(2016, 2026), [1, 1, 1, 2, 2, 2, 3, 3, 4, 6])]
    q = checks.quality_screen(pd.DataFrame(rows), "general", listed_years=20)
    assert q["tests"]["net_margin_avg"]["pass"] is False and q["tests"]["net_margin_avg"]["exempt"] == "B"
    assert q["tests"]["roe_10y"]["pass"] is False and "exempt" not in q["tests"]["roe_10y"]  # listed 20 years: no A
    assert q["failed"] == ["roe_10y"]


def test_income_counts_raises_and_cuts():
    out = checks.income(YEARS, {"2021": 1.0, "2022": 1.0, "2023": 1.2, "2024": 1.1, "2025": 1.3}, price=26, yields={})
    assert (out["raises"], out["holds"], out["cuts"]) == (2, 1, 1) and out["yield"] == pytest.approx(0.05)


def test_ttm_from_year_to_date():
    st = pd.DataFrame([{"period": "2025-09-30", "months": 9, "ni": 70}, {"period": "2025-12-31", "months": 12, "ni": 100},
                       {"period": "2026-09-30", "months": 9, "ni": 80}])
    assert sheet.ttm(st, "ni") == 110  # 80 + 100 - 70


def test_quarters_from_year_to_date():
    st = pd.DataFrame([{"period": p, "months": m, "revenue": r, "ni": r / 10} for p, m, r in (
        ("2025-03-31", 3, 10), ("2025-06-30", 6, 25), ("2025-09-30", 9, 45), ("2025-12-31", 12, 70),
        ("2026-03-31", 3, 12), ("2026-06-30", 6, 30))])
    q = sheet.quarters(st)
    assert list(q["revenue_q"]) == [10, 15, 20, 25, 12, 18]
    assert list(q["revenue_yoy"].tail(2)) == pytest.approx([0.2, 0.2])


def test_crosscheck_leaves_out_a_large_gap():
    """Eastmoney keeps a later report's restated year-end balance (China Shenhua 2025); Yahoo keeps the annual report's.
    financial-data: above 5% the figure isn't used, so that year's balance sheet is left out; revenue within 1% agrees."""
    a = pd.DataFrame([{"period": "2025-12-31", "revenue": 294.9, "ni": 52.8, "equity": 512.0, "ocf": 75.1, "assets": 903.8,
                       "cash": 50.0}])
    second = pd.DataFrame([{"period": "2025-12-31", "revenue": 295.0, "ni": 52.8, "equity": 409.1, "ocf": 75.1, "assets": 627.8}])
    out, kept = sheet.crosscheck(a, second, financial=False)
    assert out["revenue"]["status"] == "agree" and out["equity"]["status"] == "large gap"
    assert "cash" in out["left_out"] and pd.isna(kept.loc[0, "assets"]) and kept.loc[0, "revenue"] == 294.9
    q = sheet.quote_check({"price": 10.0, "mcap": 100.0}, {"price": 10.2, "mcap": 100.0})
    assert q["price"]["status"] == "differ" and q["market_cap"]["status"] == "agree"


def test_dividend_years_annualized():
    """A monthly payer with 11 ex-dates in one year and 13 in the next, and a partial first year: no false cut."""
    from stockreport.research import sources
    dates = ["2023-11-30", "2023-12-29"] + [f"2024-{m:02d}-01" for m in range(2, 13)] + \
            ["2025-01-02"] + [f"2025-{m:02d}-01" for m in range(1, 13)]
    divs = pd.DataFrame({"ex_date": dates, "dps": [0.25] * 2 + [0.25] * 11 + [0.26] * 13})
    out = sources.dividend_years(divs)
    assert out["2023"] == pytest.approx(3.0) and out["2024"] == pytest.approx(3.0) and out["2025"] == pytest.approx(3.12)


def test_split_basis_restores_unadjusted_years():
    """Apple: the FY2020 10-K restated FY2019 for the 4:1 split, not FY2018 and before."""
    a = pd.DataFrame({"shares": [5.13e9, 4.75e9, 17.77e9, 16.98e9]})
    splits = pd.DataFrame({"date": ["2020-08-31"], "ratio": [4.0]})
    assert list(sheet.split_basis(a, splits)) == pytest.approx([20.52e9, 19.0e9, 17.77e9, 16.98e9])


def test_management_and_auditor_titles():
    import re
    from stockreport.research import facts
    yes = ["贵州茅台关于聘任董事会秘书的公告", "董事辭任及委任執行董事", "8-K: Director or officer change", "关于变更会计师事务所的公告"]
    no = ["代表委任表格", "对会计师事务所2025年度履职情况的评估报告", "关于续聘会计师事务所的公告"]
    assert all(re.search(facts.MANAGEMENT, t) or re.search(facts.AUDITOR, t) for t in yes)
    assert not any(re.search(facts.MANAGEMENT, t) or re.search(facts.AUDITOR, t) for t in no)


def test_cn_shares_on_todays_basis():
    """股本 1.0bn, then 10送2 (ex 2021-06-10), a 5% issue in 2023 and another 10% after the last fiscal year (as
    China Shenhua's 2026 issue): the years keep their own counts on today's bonus basis."""
    a = pd.DataFrame({"period": ["2020-12-31", "2022-12-31", "2024-12-31"], "share_capital": [1.0e9, 1.2e9, 1.26e9],
                      "shares": [1.386e9] * 3})
    latest = pd.Series({"period": "2025-09-30", "share_capital": 1.386e9})
    assert list(sheet.cn_shares(a, latest, 1.386e9, [("2021-06-10", 0.2)])) == pytest.approx([1.2e9, 1.2e9, 1.26e9])
