"""Research stage 10: the valuation math against published examples and hand computations."""

from datetime import date

import pytest

from stockreport.research import dcf, rating, value

# Damodaran's simple Ginzu (fcffsimpleginzu.xlsx, downloaded 2026-11-09 from pages.stern.nyu.edu/~adamodar): his
# worked example, Almarai (SAR millions), with the spreadsheet's default assumptions. Its valuation output sheet shows
# PV of the 10 years' cash flows 16,394.54, terminal value 43,858.82, value of operating assets 37,517.53, equity
# 31,015.53 and 7.1878 a share; the cost of capital worksheet 7.0550%.
ALMARAI = {"revenue": 21765.4, "ebit": 3060.9, "rf": 0.0458, "mature_erp": 0.0423, "wacc": 0.070550157406465405,
           "s2c": 1.7085376710318929, "debt": 45063, "minority": 1558, "cash": 19000, "nonop": 21119, "shares": 4315}


def ginzu_paths(g1: float, g2_5: float, g_term: float, m1: float, m_target: float, convergence: int, tax_eff: float,
                tax_marginal: float, wacc0: float, wacc_term: float) -> dict:
    """The simple Ginzu's year 1-10 paths: growth g1 in year 1, g2_5 in years 2-5, falling in equal steps to the stable
    growth by year 10; the margin m1 in year 1 moving in equal steps to the target by the convergence year; the
    effective tax rate in years 1-5 moving to the marginal rate by year 10; the cost of capital in years 1-5 moving to
    the stable one by year 10."""
    growth = [g1] + [g2_5] * 4 + [g2_5 - (g2_5 - g_term) / 5 * k for k in range(1, 6)]
    margin = [m1] + [m_target if t > convergence else m_target - (m_target - m1) / convergence * (convergence - t)
                     for t in range(2, 10 + 1)]
    return {"growth": growth, "margin": margin, "tax": dcf.steps(tax_eff, tax_marginal), "wacc": dcf.steps(wacc0, wacc_term)}


def test_dcf_matches_damodarans_ginzu_example():
    a, margin = ALMARAI, ALMARAI["ebit"] / ALMARAI["revenue"]
    stable = a["rf"] + a["mature_erp"]
    p = ginzu_paths(0.05, 0.05, a["rf"], margin, margin, 5, 0.175, 0.25, a["wacc"], stable)
    assert p["growth"][5] == pytest.approx(0.04916) and p["tax"][5] == pytest.approx(0.19) and p["wacc"][9] == pytest.approx(0.0881)
    r = dcf.fcff(a["revenue"], p["growth"], p["margin"], p["tax"], [a["s2c"]] * 10, p["wacc"], a["rf"], stable, stable, 0.25)
    assert r["fcff"][0] == pytest.approx(1982.6967, abs=1e-3) and r["reinvestment"][9] == pytest.approx(939.0341, abs=1e-3)
    assert r["pv_flows"] == pytest.approx(16394.5389, abs=1e-3) and r["terminal_value"] == pytest.approx(43858.8187, abs=1e-3)
    assert r["operating"] == pytest.approx(37517.5308, abs=1e-3)
    equity = dcf.equity_value(r["operating"], a["debt"], a["minority"], a["cash"], a["nonop"])
    assert equity == pytest.approx(31015.5308, abs=1e-3) and equity / a["shares"] == pytest.approx(7.18784, abs=1e-5)


def test_cost_of_capital_matches_ginzu_worksheet():
    # the worksheet: unlevered beta 0.46942, ERP 5.5808%, market equity 4,315 x 72.28, debt 39,953.64 at market
    # value, pre-tax cost of debt 5.2803%, marginal tax 25% -> cost of equity 7.4515%, cost of capital 7.0550%
    equity, debt = 4315 * 72.28, 351841.84461186395 - 4315 * 72.28
    beta = dcf.relever(0.46942377677075875, debt / equity, 0.25)
    coe = dcf.capm(0.0458, beta, 0.055808146436763538)
    assert coe == pytest.approx(0.074514660, abs=1e-8)
    assert dcf.wacc(equity, debt, coe, 0.052803, 0.25) == pytest.approx(0.070550157, abs=1e-8)


def test_nol_shields_income_until_used():
    r = dcf.fcff(100, [0.0] * 10, [-0.1, 0.1] + [0.2] * 8, [0.25] * 10, [1.0] * 10, [0.1] * 10, 0.0, 0.1, 0.1, 0.25, nol=5)
    assert r["nopat"][:3] == pytest.approx([-10, 10, 20 - 15 * 0.25])  # the loss adds 10 to 5; 15 shields 10, then 5 of 20


def test_synthetic_rating_spread():
    table = [{"low": -1e5, "high": 1.249999, "rating": "Caa/CCC", "spread": 0.0885},
             {"low": 1.25, "high": 8.499999, "rating": "A2/A", "spread": 0.0078},
             {"low": 8.5, "high": 1e5, "rating": "Aaa/AAA", "spread": 0.004}]
    assert dcf.spread(3.0, table) == ("A2/A", 0.0078) and dcf.spread(None, table) == ("Aaa/AAA", 0.004)
    assert dcf.spread(8.4999995, table)[0] == "A2/A" and dcf.spread(-2, table)[0] == "Caa/CCC"


def test_justified_pb_and_excess_return_agree():
    assert dcf.justified_pb(0.15, 0.10, 0.04) == pytest.approx(11 / 6)
    # constant ROE, payout and cost: the excess-return model's value over book is the justified P/B with g = ROE x retention
    roe, payout, coe = 0.12, 0.5, 0.09
    r = dcf.excess_return(100, [roe] * 10, [payout] * 10, [coe] * 10, roe, coe, roe * (1 - payout))
    assert r["value"] / 100 == pytest.approx(dcf.justified_pb(roe, coe, roe * (1 - payout)))
    assert r["years"][1]["book"] == pytest.approx(106) and r["years"][0]["excess"] == pytest.approx(3)


def test_implied_cost_of_equity_inverts_justified_pb():
    # a bank at 0.8 times book earning 12% with 1% growth prices a 14.75% cost of equity
    assert dcf.implied_cost_equity(0.12, 0.8, 0.01) == pytest.approx(0.1475)
    assert dcf.justified_pb(0.12, dcf.implied_cost_equity(0.12, 0.8, 0.01), 0.01) == pytest.approx(0.8)


def test_two_stage_dividend_discount():
    # 2.00 growing 10% for 2 years, then 3% at 8%: 2.2/1.08 + 2.42/1.08^2 + 2.42 x 1.03 / 0.05 / 1.08^2
    assert dcf.ddm(2.0, 0.10, 2, 0.08, 0.03) == pytest.approx(2.2 / 1.08 + 2.42 / 1.08 ** 2 + 49.852 / 1.08 ** 2)
    assert dcf.ddm(1.0, 0.03, 0, 0.08, 0.03) == pytest.approx(1.03 / 0.05)


def test_reverse_solves_for_the_price():
    f = lambda g: dcf.ddm(1.0, g, 5, 0.09, 0.03)
    g = dcf.solve(f, 25.0, -0.5, 1.0)
    assert f(g) == pytest.approx(25.0, abs=1e-5) and dcf.solve(f, 1e6, -0.5, 1.0) is None


def test_forward_twelve_months_weights_fiscal_years():
    eps = {"2026": 60.0, "2027": 72.0, "2028": 84.0}
    assert value.forward(eps, 12, date(2026, 11, 9), 0) == pytest.approx(60 * 2 / 12 + 72 * 10 / 12)
    assert value.forward(eps, 9, date(2026, 11, 9), 0) == pytest.approx(72 * 11 / 12 + 84 / 12)  # FY to September
    assert value.forward(eps, 12, date(2026, 11, 9), 24) is None  # December 2028-October 2029 isn't covered


def test_moat_keeps_half_the_edge():
    import pandas as pd
    always = pd.Series([0.20, 0.25, 0.18, 0.22, 0.30, 0.21, 0.24, 0.19])
    assert value.moat(always, 0.08, 0.06) == (pytest.approx(0.06 + (always.median() - 0.06) / 2), True)
    assert value.moat(always.replace(0.18, 0.07), 0.08, 0.06) == (0.06, False)  # one year below its cost: no moat
    assert value.moat(always[:7], 0.08, 0.06) == (0.06, False)  # under 8 years


def test_rating_band_scales_with_uncertainty():
    # methods 90-110 around a target of 100: half-range 10% -> band 10%; price 85, dividend 2, market 8%: +12% excess
    r = rating.rate(100, 95, 105, [90, 110], 85, 2, 0.08)
    assert r["uncertainty"]["band"] == pytest.approx(0.10) and r["excess_return"] == pytest.approx(17 / 85 - 0.08)
    assert r["rating"] == "买入"
    wide = rating.rate(100, 70, 130, [90, 110], 85, 2, 0.08)  # bear-to-bull half-range 30% -> band capped at 25%
    assert wide["uncertainty"]["band"] == pytest.approx(0.25) and wide["rating"] == "持有"
    assert rating.rate(100, 99, 101, [99, 101], 125, 0, 0.08)["rating"] == "卖出"  # -20% - 8% against a 10% band


def test_weights_pass_to_the_methods_that_ran():
    target, w = rating.weigh({"dcf": {"target": 100.0}, "pe_own": {"target": 120.0}}, "ordinary")  # no peers' P/E
    assert w == pytest.approx({"dcf": 2 / 3, "pe_own": 1 / 3}) and target == pytest.approx(100 * 2 / 3 + 40)


def test_forecast_paths_follow_the_consensus_then_fade():
    # consensus EPS +10% a year for two years, no revenue consensus: revenue grows with profit and the margin holds;
    # growth then falls in equal steps to g by year 10 and the margin reaches the own 8-year median (20%) by year 5
    f = {"valuation": {"ttm": {"revenue": 100.0, "ni": 10.0}}, "summary": {},
         "history": [{"ebit_margin": 0.2}] * 8}
    k = {"ebit": 15.0, "shares": 10.0, "ind_margin": 0.1}
    p = value.paths(f, k, "ordinary", {"eps": [1.1, 1.21], "revenue": [None, None]}, 0.02)
    assert p["growth"][:2] == pytest.approx([0.1, 0.1]) and p["growth"][9] == pytest.approx(0.02)
    assert p["growth"][2] == pytest.approx(0.1 - 0.08 / 8) and p["margin"][:2] == pytest.approx([0.15, 0.15])
    assert p["margin"][2] == pytest.approx(0.15 + 0.05 / 3) and p["margin"][4:] == pytest.approx([0.2] * 6)
    assert value.paths(f, k, "loss_making", {"eps": [], "revenue": []}, 0.02)["target_margin"] == 0.1  # industry
