"""Research stage 10: the valuation math against published examples and hand computations."""

from datetime import date

import pytest

from stockreport.research import dcf, fade, judge, market, rating, texts, value

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
    r = dcf.fcff(a["revenue"], p["growth"], p["margin"], p["tax"], [a["s2c"]] * 10, p["wacc"], a["rf"], stable, [], 0.25)
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
    r = dcf.fcff(100, [0.0] * 10, [-0.1, 0.1] + [0.2] * 8, [0.25] * 10, [1.0] * 10, [0.1] * 10, 0.0, 0.1, [], 0.25, nol=5)
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
    # (excess returns lasting 3,000 years stand for ever)
    roe, payout, coe = 0.12, 0.5, 0.09
    r = dcf.excess_return(100, [roe] * 10, [payout] * 10, [coe] * 10, [roe] * 3000, coe, roe * (1 - payout))
    assert r["value"] / 100 == pytest.approx(dcf.justified_pb(roe, coe, roe * (1 - payout)))
    assert dcf.excess_return(100, [coe] * 10, [payout] * 10, [coe] * 10, [], coe, 0.03)["value"] == pytest.approx(100)
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


def test_moat_is_graded():
    # a return above its 8% cost in all 8 years, median 21.5% against a 6% stable cost: an excess of 15.5 points kept
    # 90% a year, so stable year 1 (year 11) earns 6% + 15.5% x 0.9^11 on new capital, for Morningstar's 15 years
    import pandas as pd
    always = pd.Series([0.20, 0.25, 0.18, 0.22, 0.30, 0.21, 0.24, 0.19])
    m = value.moat(always, 0.08, 0.06, 0.9)
    assert m["moat"] and m["track"] == 1.0 and m["ronic"][0] == pytest.approx(0.06 + 0.155 * 0.9 ** 11)
    assert len(m["ronic"]) == 15 and m["start"] == pytest.approx(0.06 + 0.155 * 0.9 ** 10)
    weak = value.moat(always.replace(0.18, 0.07), 0.08, 0.06, 0.9)  # one year below its cost: 7 of 8, not none
    assert weak["track"] == 7 / 8 and weak["ronic"][0] == pytest.approx(0.06 + 7 / 8 * (weak["edge"]) * 0.9 ** 11)
    assert value.moat(always[:4], 0.08, 0.06, 0.9)["ronic"] == []  # under 5 years: no record
    assert not value.moat(pd.Series([0.05] * 8), 0.08, 0.06, 0.9)["moat"]  # below its cost


def test_terminal_value_fades_to_the_cost_of_capital():
    # no excess years: the Ginzu's NOPAT (1 - g / WACC) / (WACC - g) = NOPAT / WACC; one year at 20% then the cost
    assert dcf.terminal(10.0, 0.03, 0.08, []) == pytest.approx(10 * (1 - 0.03 / 0.08) / 0.05) == pytest.approx(125)
    assert dcf.terminal(10.0, 0.03, 0.08, [0.20]) == pytest.approx(10 * (1 - 0.03 / 0.2) / 1.08 + 10.3 / 0.08 / 1.08)
    assert dcf.excess_terminal(100.0, [0.15, 0.12], 0.10, 0.02) == pytest.approx(5 / 1.1 + 2 * 1.02 / 1.1 ** 2)


def test_stable_growth_passes_the_sensitivity_test():
    # a fixed payout's perpetuity 1 / (r - g): +0.5 point raises it at most 1/9 when r - g >= 5 points (the skill's rule)
    assert dcf.tested_growth(lambda g: 1 / (0.08 - g), 0.04) == pytest.approx(0.03, abs=1e-6)
    assert dcf.tested_growth(lambda g: 1 / (0.10 - g), 0.04) == 0.04
    # a return on new capital equal to its cost: growth adds nothing, so the riskless rate stands even 1 point from r
    assert dcf.tested_growth(lambda g: dcf.terminal(1.0, g, 0.058, []), 0.048) == 0.048


def test_uncertainty_level_from_the_scenarios_widened_by_a_red_flag():
    # bear-to-bull half-range 15%: low (a 20% discount covers it); 25%: medium; a red flag one level up
    assert judge.uncertainty(100, 85, 115, False, 0.08)["level"] == "low"
    assert judge.uncertainty(100, 75, 125, False, 0.08)["level"] == "medium"
    assert judge.uncertainty(100, 75, 125, True, 0.08)["level"] == "high"
    assert judge.uncertainty(100, 0, 160, False, 0.08)["level"] == "extreme"  # 80% is more than very high's 50%
    assert judge.uncertainty(0.0, 0.0, 0.0, False, 0.08)["level"] == "extreme"  # no fair value: the widest
    u = judge.uncertainty(100, 65, 135, False, 0.08)  # high: 5 stars at 0.60 of fair value, 1 star at 1.55
    assert (u["discount"], u["premium"]) == (0.40, 0.55)
    assert u["buy"] == pytest.approx(1.08 / 0.6 - 1.08) and u["sell"] == pytest.approx(1.08 - 1.08 / 1.55)


def test_rating_on_price_over_fair_value_two_sided():
    # Morningstar's high uncertainty, the market's 8%: today's fair value is (12-month value + dividend) / 1.08; 买入 at
    # 0.60 of it or less, 卖出 at 1.55 times or more; between them 持有, however far apart the two sides are
    u = {"discount": 0.40, "premium": 0.55}
    at = lambda ratio: judge.gap(100 * 1.08 / ratio, 100, 0, 0.08)  # the gap of a stock priced at `ratio` x fair value
    assert judge.view(at(0.60), u, 0.08) == "买入" and judge.view(at(0.61), u, 0.08) == "持有"
    assert judge.view(at(1.55), u, 0.08) == "卖出" and judge.view(at(1.54), u, 0.08) == "持有"
    assert judge.view(judge.gap(0.0, 100, 0, 0.08), u, 0.08) == "卖出"  # no value at all
    # each scenario input's quartile effect combined as independent: 30 and 40 down give 50; up 10 and 0 give 10
    assert judge.scenarios(100, {"a": (70, 110), "b": (60, 100)}) == (pytest.approx(50), pytest.approx(110))
    assert judge.scenarios(100, {"a": (0, 150), "b": (10, 100)})[0] == 0  # never below 0


def test_rating_against_the_main_method_and_its_cross_checks():
    found = {"dcf": {"target": 70.0}, "pe_own": {"target": 140.0}, "pe_peers": {"target": 145.0}}
    order, u, none = ["dcf", "pe_own", "pe_peers"], {"discount": 0.20, "premium": 0.25}, {"block": [], "widen": []}
    # price 100, no dividend, the market's 8%, low uncertainty: the DCF prices it at 1.54 times its fair value, 卖出;
    # the cross-checks at 0.77 and 0.74 times, 买入
    j = judge.judge("dcf", found, order, 100, 0, 0.08, u, none)
    assert (j["rating"], j["state"], j["main_view"], j["checks_view"]) == ("持有", "unresolved", "卖出", "买入")
    assert j["fair_excess"] == pytest.approx(-0.38) and [x["view"] for x in j["cross"]] == ["买入", "买入"]
    found["pe_own"]["target"] = 110.0  # 0.98 times, 持有, and a 买入: one of two isn't most, the main method's stands
    assert judge.judge("dcf", found, order, 100, 0, 0.08, u, none)["rating"] == "卖出"
    found["pe_own"]["target"] = 60.0  # one 卖出, one 买入: nothing averaged, no majority against the 卖出
    assert judge.judge("dcf", found, order, 100, 0, 0.08, u, none)["state"] == "resolved"
    cheap = {"dcf": {"target": 140.0}, "pe_own": {"target": 120.0}}
    assert judge.judge("dcf", cheap, order, 100, 0, 0.08, u, none)["rating"] == "买入"
    blocked = judge.judge("dcf", cheap, order, 100, 0, 0.08, u, {"block": [{"check": "quality_screen"}], "widen": []})
    assert (blocked["rating"], blocked["state"]) == ("持有", "blocked")  # a failed check blocks 买入, never moves a 卖出


def test_main_method_is_the_first_with_a_value():
    order = value.METHODS["loss_making"]
    found = {"dcf": {"target": 0.0}, "evs_peers": {"target": 12.0}}  # the DCF's equity value is negative: counted as 0
    assert rating.main_of(found, order) == "evs_peers"
    assert rating.main_of({"pe_own": {"target": 9.0}}, value.METHODS["ordinary"]) == "pe_own"
    assert rating.main_of({}, order) is None


def test_skills_checks_block_or_widen():
    base = {"quality_screen": {"result": "exclude", "failed": ["net_margin_avg"]}, "checklist": {"fcf_negative_3y": False},
            "income": {"uncovered_years_5y": 3}, "beneish": {"m_score": -1.5},
            "earnings_signals": {"receivables_faster": True, "inventory_faster": False, "cash_below_profit_widening": True}}
    acts = judge.checks({"checks": base}, "ordinary")
    assert [a["check"] for a in acts["block"]] == ["quality_screen"]  # the dividend gate is the income types'
    assert [a["check"] for a in acts["widen"]] == ["beneish", "earnings_signals"]
    assert [a["check"] for a in judge.checks({"checks": base}, "income")["block"]] == ["quality_screen", "dividend_uncovered"]
    assert judge.checks({"checks": base}, "reit")["block"] == []  # a REIT's free cash flow isn't measured
    assert judge.checks({"checks": base}, "loss_making")["block"] == []  # the screen fails a loss-maker by construction
    assert judge.checks({"checks": base}, "bank")["widen"] == []  # financials skip the industrial tests


def test_dividend_cover_over_five_years():
    years = [{"fcf": 80.0, "div_paid": -100.0}] * 4 + [{"fcf": 120.0, "div_paid": -100.0}]
    assert judge.cover({"history": years}) == pytest.approx(440 / 500)
    assert judge.cover({"history": years[:4]}) is None  # fewer than 5 years
    assert judge.cover({"history": years[:4] + [{"fcf": None, "div_paid": -100.0}]}) is None  # a REIT reports no capex


def test_an_income_stock_paying_far_below_its_fcfe_is_valued_on_free_cash_flow():
    # 五粮液's shape: 5 years of FCF 145 against dividends 87 (60%), no debt: Damodaran's FCFE model (the DCF) is the
    # main method; dividends 81% of FCFE stay with the dividend model; debt repaid lowers FCFE (more paid out of it)
    def f(fcf, div, debt=(0.0, 0.0)):
        h = [{"debt": debt[0]}] + [{"fcf": fcf / 5, "div_paid": -div / 5, "debt": None} for _ in range(5)]
        h[-1]["debt"] = debt[1]
        return {"history": h}
    assert judge.fcfe_payout(f(145.0, 87.0)) == pytest.approx(0.6)
    assert judge.main_order(f(145.0, 87.0), "income") == (["dcf", "ddm", "yield_own"], pytest.approx(0.6))
    assert judge.main_order(f(100.0, 81.0), "income") == (value.METHODS["income"], None)
    assert judge.fcfe_payout(f(100.0, 81.0, (64.0, 0.0))) == pytest.approx(81 / 36)  # FCFE 100 - 64 repaid: above 110%
    assert judge.main_order(f(-10.0, 50.0), "income")[1] == float("inf")  # no free cash flow to pay it from
    assert judge.main_order(f(145.0, 87.0), "reit") == (value.METHODS["reit"], None)  # a REIT's FCF isn't measured


def test_tail_scenario_breakeven():
    f = {"damodaran": {"country": "China"}, "market": "us", "valuation": {"report_currency": "CNY"}, "other_listings": []}
    u = {"buy": 0.20, "sell": 0.20}  # the gaps at which it is 买入 and 卖出
    t = judge.tail(f, {"vie": True}, 150.0, 100.0, 2.0, 0.08, u, "买入")
    # a 买入 falls a step when (1 - p) x 152 / 100 - 1 - 8% < 20%: p = 1 - 128 / 152
    assert [x["risk"] for x in t] == ["vie", "delisting"] and t[0]["breakeven"] == pytest.approx(1 - 128 / 152)
    f["other_listings"] = [{"market": "hk", "code": "09988"}]
    assert judge.tail(f, {"vie": False}, 150.0, 100.0, 2.0, 0.08, u, "买入") == [
        {"risk": "delisting", "value": None, "line": "09988", "breakeven": None}]  # ADSs convert into the HK line
    f["market"] = "cn"
    assert judge.tail(f, {"vie": True}, 150.0, 100.0, 2.0, 0.08, u, "买入") == []  # listed at home


def test_market_comes_out_at_its_price(monkeypatch):
    import pandas as pd
    # members at 1.25 times book earning 10%, no consensus growth, a flat 10% ROE history: at r = 8% (the yield 3%, base
    # growth 3% then the yield) the market's value is its price by construction
    snap = pd.DataFrame({"code": ["a", "b"], "mcap": [300.0, 100.0], "ey": [0.08, 0.08], "by": [0.8, 0.8],
                         "fwd_growth": [None, None], "snap_date": "2026-11-14"})
    history = pd.DataFrame({str(y): [0.10, 0.10] for y in range(2016, 2026)}, index=["a", "b"])
    monkeypatch.setattr(market.sheet, "snapshot", lambda m, today: snap)
    monkeypatch.setattr(market.fade, "return_table", lambda m: history)
    monkeypatch.setattr(market.fade, "base_rates", lambda m, rev, rates: {"fifth_recent": 0.03})
    monkeypatch.setattr(market.fade, "margin_keep", lambda m: {"above": 0.9, "below": 0.6})
    monkeypatch.setattr(market.fade, "excess_keep", lambda m: 0.9)
    monkeypatch.setattr(market.value, "rate", lambda m: (0.03, "2026-11-14"))
    market.implied.cache_clear()
    got = market.implied("cn", date(2026, 11, 14))
    assert got["value"] == pytest.approx(1.0, abs=1e-6) and got["erp"] == pytest.approx(got["r"] - 0.03)
    assert got["pb"] == pytest.approx(1.25) and got["roe_next"] == pytest.approx(0.10) and 0.08 < got["r"] < 0.13
    a = market.aggregate(snap, "cn")
    p = market.paths(a, 0.03, {"above": 0.9, "below": 0.6})
    assert market.worth(a, p, got["r"], 0.9)["value"] == pytest.approx(1.0, abs=1e-6)
    market.implied.cache_clear()


def test_market_at_book_earning_its_return_implies_that_return(monkeypatch):
    # members at book earning 10% a year, every year (no moat above a 10% cost): the market is worth its book only at
    # r = 10%, so the implied return is 10% whatever the growth (not the solver's own check: a closed form)
    import pandas as pd
    snap = pd.DataFrame({"code": ["a", "b"], "mcap": [300.0, 100.0], "ey": [0.10, 0.10], "by": [1.0, 1.0],
                         "fwd_growth": [None, None], "snap_date": "2026-11-14"})
    history = pd.DataFrame({str(y): [0.10, 0.10] for y in range(2016, 2026)}, index=["a", "b"])
    monkeypatch.setattr(market.sheet, "snapshot", lambda m, today: snap)
    monkeypatch.setattr(market.fade, "return_table", lambda m: history)
    monkeypatch.setattr(market.fade, "base_rates", lambda m, rev, rates: {"fifth_recent": 0.05})
    monkeypatch.setattr(market.fade, "margin_keep", lambda m: {"above": 0.9, "below": 0.6})
    monkeypatch.setattr(market.fade, "excess_keep", lambda m: 0.9)
    monkeypatch.setattr(market.value, "rate", lambda m: (0.03, "2026-11-14"))
    market.implied.cache_clear()
    got = market.implied("hk", date(2026, 11, 14))
    assert got["r"] == pytest.approx(0.10, abs=1e-6) and got["erp"] == pytest.approx(0.07, abs=1e-6)
    market.implied.cache_clear()


def test_each_group_comes_out_at_its_price(monkeypatch):
    import pandas as pd
    # 10 financials at 0.8 times book earning 8% and 10 others at 2 times book earning 10%: each group is solved on its
    # own members and is worth its price at its own return; the banks' is the higher, the whole market's in between
    rows = [{"code": f"f{i}", "mcap": 100.0, "ey": 0.10, "by": 1.25, "financial": True} for i in range(10)] + \
           [{"code": f"o{i}", "mcap": 100.0, "ey": 0.05, "by": 0.5, "financial": False} for i in range(10)]
    snap = pd.DataFrame(rows).assign(fwd_growth=None, snap_date="2026-11-14")
    history = pd.DataFrame({str(y): [0.08] * 10 + [0.10] * 10 for y in range(2016, 2026)}, index=snap["code"])
    monkeypatch.setattr(market.sheet, "snapshot", lambda m, today: snap)
    monkeypatch.setattr(market.fade, "return_table", lambda m: history)
    monkeypatch.setattr(market.fade, "base_rates", lambda m, rev, rates: {"fifth_recent": 0.03})
    monkeypatch.setattr(market.fade, "margin_keep", lambda m: {"above": 0.9, "below": 0.6})
    monkeypatch.setattr(market.fade, "excess_keep", lambda m: 0.9)
    monkeypatch.setattr(market.value, "rate", lambda m: (0.03, "2026-11-14"))
    market.implied.cache_clear()
    d = date(2026, 11, 14)
    fin, other, every = market.implied("cn", d, True), market.implied("cn", d, False), market.implied("cn", d)
    assert fin["members"] == other["members"] == 10 and fin["value"] == pytest.approx(1.0, abs=1e-6)
    assert other["value"] == pytest.approx(1.0, abs=1e-6) and fin["r"] > every["r"] > other["r"]
    a = market.aggregate(market.select(snap, "cn", True, None), "cn")
    assert market.worth(a, market.paths(a, 0.03, {"above": 0.9, "below": 0.6}), fin["r"], 0.9)["value"] == pytest.approx(1.0, abs=1e-6)
    market.implied.cache_clear()
    small = snap.iloc[5:]  # 5 financials: under Damodaran's 10-firm floor, they take the market's return
    monkeypatch.setattr(market.sheet, "snapshot", lambda m, today: small)
    assert market.implied("cn", d, True)["r"] == pytest.approx(market.implied("cn", d)["r"])
    market.implied.cache_clear()


def test_china_based_members_and_the_stocks_group(monkeypatch):
    import pandas as pd
    # a CNY reporter, a USD reporter Damodaran lists in China (SMIC), Link (HKD, Hong Kong) and a red chip Damodaran
    # lists in Hong Kong that reports in CNY (CNOOC): China-based, all but Link
    snap = pd.DataFrame({"code": ["a", "b", "c", "d"], "report_currency": ["CNY", "USD", "HKD", "CNY"]})
    co = pd.DataFrame({"market": "hk", "code": ["b", "c", "d"], "country": ["China", "Hong Kong", "Hong Kong"]})
    monkeypatch.setattr(market.damodaran, "load", lambda name: co)
    assert market.china(snap, "hk").tolist() == [True, True, False, True]
    monkeypatch.setattr(value.damodaran, "country", lambda name: {"crp": 0.01} if name in ("China", "Hong Kong") else {})
    stock = lambda kind, market_, ccy, country: {"kind": kind, "market": market_, "damodaran": {"country": country},
                                                 "valuation": {"report_currency": ccy}}
    assert value.group_of(stock("reit", "hk", "HKD", "Hong Kong")) == (False, False)  # Link: HK's non-mainland others
    assert value.group_of(stock("insurer", "hk", "CNY", "China")) == (True, True)  # Ping An H
    assert value.group_of(stock("general", "us", "CNY", "China")) == (False, True)  # Alibaba's US line: priced in HK
    assert value.group_of(stock("bank", "cn", "CNY", "China")) == (True, None)  # no home split outside Hong Kong


def test_dividend_model_pays_what_free_cash_flow_covers():
    # 5 years of free cash flow 25 against dividends of 50: half covered, so the model's dividend is half the consensus's
    f = {"kind": "general", "market": "cn", "valuation": {"price": 10.0, "ttm": {"ni": 100.0, "revenue": 1000.0},
         "own_history": {}, "book_common": 500.0, "dps_12m": 0.5},
         "history": [{"dps": 0.5, "shares": 100.0, "ni": 100.0, "fcf": 25.0, "div_paid": -50.0}] * 5,
         "checks": {"income": {}}}
    k = {"shares": 100.0, "fx": 1.0, "cost_equity": 0.08, "wacc": 0.08, "stable_cost": 0.08, "g": 0.02}
    cons = {"eps": [1.0, 1.05], "ntm_eps": 1.0, "range": None}
    x = rating.methods(f, k, "income", cons, date(2026, 11, 14), only={"ddm"})["ddm"]
    assert x["fcf_cover"] == pytest.approx(0.5) and x["dividend"] == pytest.approx(0.25) and x["dividend_consensus"] == 0.5
    assert x["value"] == pytest.approx(dcf.ddm(0.25 / 1.05, 0.05, 5, 0.08, 0.02))
    for h in f["history"]:
        h["fcf"] = -10.0  # paid out of debt for 5 years: nothing covered
    assert rating.methods(f, k, "income", cons, date(2026, 11, 14), only={"ddm"})["ddm"]["dividend"] == 0.0


def test_vie_needs_a_section_of_its_own():
    assert texts.vie("The Structure Contracts allow us ... " * 10) and texts.vie("variable interest entities; " * 10)
    assert not texts.vie("contractual arrangements with a connected person. " * 9)


def test_fcfe_is_the_book_at_the_cost_of_equity():
    # ROE equal to the cost every year and no excess after: the book, whatever the growth
    assert dcf.fcfe(100.0, [0.08] * 10, [0.05] * 5 + [0.04] * 5, 0.08, 0.03, [])["value"] == pytest.approx(100.0)
    # a constant 12% ROE paid out in full (no growth): a perpetuity of 12 at 8%
    assert dcf.fcfe(100.0, [0.12] * 10, [0.0] * 10, 0.08, 0.0, [])["value"] == pytest.approx(150.0)


def test_cost_of_equity_is_the_markets_implied_return(monkeypatch):
    import pandas as pd
    countries = {"China": {"erp": 0.0514, "crp": 0.0091}, "Hong Kong": {"erp": 0.0501, "crp": 0.0078},
                 "United States": {"erp": 0.0446, "crp": 0.0023}}
    monkeypatch.setattr(value, "rate", lambda m: (0.016, "2026-11-14"))
    monkeypatch.setattr(value.damodaran, "country", lambda name: countries.get(name))
    monkeypatch.setattr(value.damodaran, "load", lambda name: pd.DataFrame(
        [{"table": t, "low": -1e5, "high": 1e5, "rating": "A", "spread": 0.01} for t in ("large", "smaller", "financial")]))
    monkeypatch.setattr(value, "industry", lambda dam, kind: {"name": "X", "region": "Global", "beta": 0.8,
                                                              "unlevered_beta_cash": 1.2, "op_margin": 0.1, "sales_to_capital": 1.0})
    monkeypatch.setattr(value.yahoo, "load_fx", lambda: {"USD": 1.0, "CNY": 7.1})
    f = {"market": "us", "kind": "general", "damodaran": {}, "valuation": {
        "report_currency": "CNY", "ttm": {"revenue": 1000.0, "op_income": 100.0, "interest": 0.0, "ni": 80.0, "pretax": 100.0},
        "balance": {"debt": 0.0, "cash": 0.0, "minority": 0.0, "nonop": 0.0}, "market_cap_report": 1e12, "shares": 100.0,
        "fx_quote_to_report": 7.1}}
    assert value.priced_in(f) == "hk"  # a CNY reporter listed in the US is China-based: priced with Hong Kong's premium
    k = value.inputs(f, {"r": 0.10, "erp": 0.08})
    assert k["cost_equity"] == pytest.approx(0.016 + 0.08 + 0.0091 - 0.0078) == pytest.approx(k["stable_cost"])
    assert k["market_return"] == pytest.approx(0.096) and k["published"]["cost_equity"] == pytest.approx(0.016 + 1.2 * 0.0514)
    assert k["stable_wacc"] == pytest.approx(k["wacc"]) == pytest.approx(k["cost_equity"])  # no debt: the WACC is the equity's
    china = value.inputs(f, {"r": 0.10, "erp": 0.08, "country": "China"})  # HK's China-based group: its premium already
    assert china["cost_equity"] == pytest.approx(0.016 + 0.08) and china["crp"] == 0  # carries China's risk
    assert value.inputs(f, None)["erp_market"] == pytest.approx(0.0501)  # no implied return: the published premium
    # a 20-F filer missing from Damodaran's list (his list has TSMC's home listing, not the ADR): its home, not the US
    countries["Taiwan"] = {"erp": 0.0501, "crp": 0.0078}
    tw = f | {"home": "Taiwan", "valuation": f["valuation"] | {"report_currency": "TWD"}}
    assert value.country_of(tw) == "Taiwan" and value.priced_in(tw) == "us"
    assert value.inputs(tw, {"r": 0.07, "erp": 0.05})["crp"] == pytest.approx(0.0078 - 0.0023)
    assert value.country_of(tw | {"home": "Atlantis"}) == "United States"  # a home Damodaran doesn't list: the listing's


def test_excess_return_on_the_average_roe():
    # a broker at book (100 a share) with a 10-year ROE of 8% and a cost of equity of 8%: no excess, the book
    f = {"kind": "broker", "market": "cn", "valuation": {"price": 100.0, "ttm": {"ni": 800.0, "revenue": 4000.0},
         "own_history": {"pe": {}, "pb": {}}, "book_common": 10000.0, "dps_12m": 0.0},
         "history": [{"roe": 0.08, "dps": 2.4, "shares": 100.0, "ni": 800.0}] * 10, "checks": {"income": {}}}
    k = {"shares": 100.0, "fx": 1.0, "cost_equity": 0.08, "wacc": 0.08, "stable_cost": 0.08, "stable_wacc": 0.08, "g": 0.02, "excess_keep": 0.9,
         "debt_to_equity": 0.0, "cost_debt": None, "tax_marginal": 0.25}
    cons = {"eps": [], "ntm_eps": None, "range": None}
    x = rating.methods(f, k, "broker", cons, date(2026, 11, 14), only={"pb_roe"})["pb_roe"]
    assert x["value"] == pytest.approx(100.0) and x["roe_avg"] == pytest.approx(0.08)
    assert rating.implied(f, k, "broker", cons, date(2026, 11, 14), "pb_roe") == pytest.approx(0.08, abs=1e-4)
    for h in f["history"]:
        h["roe"] = 0.14  # 14% against 8%: above book, below the old perpetual justified P/B (0.14 - 2%) / (8% - 2%)
    y = rating.methods(f, k, "broker", cons, date(2026, 11, 14), only={"pb_roe"})["pb_roe"]
    assert 100.0 < y["value"] < 100.0 * dcf.justified_pb(0.14, 0.08, 0.02)


def test_rates_at_another_equity_return():
    k = {"cost_equity": 0.08, "wacc": 0.07, "stable_cost": 0.08, "debt_to_equity": 0.5, "cost_debt": 0.05, "tax_marginal": 0.2}
    got = rating.at_cost(k, 0.10)
    assert got["cost_equity"] == got["stable_cost"] == 0.10 and got["wacc"] == pytest.approx((0.10 + 0.5 * 0.04) / 1.5)
    assert got["stable_wacc"] == got["wacc"]  # the DCF's cost doesn't step: a beta of 1 from year 1


KEEP = {"margin_keep": {"above": 0.9, "below": 0.6}}


def test_forecast_paths_follow_the_consensus_then_fade():
    # consensus revenue and EPS +10% a year for two years: the margin holds; growth then falls in equal steps to g by
    # year 10; the margin's 5-point gap below the own 8-year median (20%) keeps 60% a year (the measured share below)
    f = {"valuation": {"ttm": {"revenue": 100.0, "ni": 10.0}}, "summary": {},
         "history": [{"ebit_margin": 0.2}] * 8}
    k = {"ebit": 15.0, "shares": 10.0, "ind_margin": 0.1} | KEEP
    p = value.paths(f, k, "ordinary", {"eps": [1.1, 1.21], "revenue": [110.0, 121.0], "eps0": 1.0}, 0.02)
    assert p["growth"][:2] == pytest.approx([0.1, 0.1]) and p["growth"][9] == pytest.approx(0.02)
    assert p["growth"][2] == pytest.approx(0.1 - 0.08 / 8) and p["margin"][:2] == pytest.approx([0.15, 0.15])
    assert p["margin"][2:] == pytest.approx([0.2 - 0.05 * 0.6 ** t for t in range(1, 9)])
    high = value.paths(f, k | {"ebit": 30.0}, "ordinary", {"eps": [1.1], "revenue": [110.0], "eps0": 1.0}, 0.02)
    assert high["margin"][9] == pytest.approx(0.2 + 0.1 * 0.9 ** 9)  # 10 points above it keep 90% a year
    young = value.paths(f, k, "loss_making", {"eps": [], "revenue": []}, 0.02)
    assert young["target_margin"] == 0.1 and young["margin"][4:] == pytest.approx([0.1] * 6)  # industry's, by year 5


def test_consensus_margins_on_the_consensus_basis():
    # adjusted consensus EPS 1.375 against 1.25 adjusted trailing (reported 1.0): operating income grows 10% with
    # revenue, the margin holds at 15% (from reported profit it would jump to 15% x 1.375 = 20.6%); a second window
    # past the revenue consensus ends the consensus years (NVIDIA's 79%), its profit forecast unused
    f = {"valuation": {"ttm": {"revenue": 100.0, "ni": 10.0}}, "summary": {}, "history": [{"ebit_margin": 0.15}] * 8}
    k = {"ebit": 15.0, "shares": 10.0, "ind_margin": 0.1, "base_growth": 0.05} | KEEP
    p = value.paths(f, k, "ordinary", {"eps": [1.375, 2.5], "revenue": [110.0, None], "eps0": 1.25}, 0.02)
    assert p["consensus_years"] == 1 and p["margin"][:2] == pytest.approx([0.15, 0.15]) and p["growth"][1] == 0.05


def test_trailing_eps_on_the_consensus_basis(monkeypatch):
    from datetime import date
    monkeypatch.setattr(value.yahoo, "load_fx", lambda: {"USD": 0.14, "TWD": 4.5})  # units per CNY
    q = [{"quarter": m, "eps": e} for m, e in (("2025-12", 7.54), ("2026-03", 8.55), ("2026-06", 8.38), ("2026-09", 7.48))]
    f = {"consensus": {"source": "Nasdaq", "currency": "USD", "actuals": q}, "latest": {"period": "2026-09-30"},
         "valuation": {"ttm": {"ni": 26.3e9}}}
    k = {"shares": 0.897e9, "currency": "USD"}
    assert value.trailing_eps(f, k) == (pytest.approx(31.95), "Nasdaq's last four quarters")  # Lilly's, not GAAP's 29.3
    late = f | {"latest": {"period": "2026-06-30"}}  # quarters that end after the trailing figures: the reported basis
    assert value.trailing_eps(late, k)[0] == pytest.approx(26.3 / 0.897)
    tsm = f | {"consensus": f["consensus"] | {"actuals": [r | {"eps": r["eps"] / 2} for r in q]}}  # USD per ADR
    assert value.trailing_eps(tsm, k | {"currency": "TWD"})[0] == pytest.approx(31.95 / 2 * 4.5 / 0.14)
    cn = {"consensus": {"source": "Eastmoney 研报一致预期"}, "latest": {"period": "2026-09-30"}, "valuation": {"ttm": {"ni": 10.0}}}
    assert value.trailing_eps(cn, {"shares": 4.0})[0] == 2.5
    assert value.month_end("2026-02") == date(2026, 2, 28)


def test_growth_beyond_the_consensus_is_the_base_rate():
    # one revenue consensus year (+20%), profit +30% then +25%: year 2 grows revenue at the size class's median (5%),
    # not with profit (Chan, Karceski and Lakonishok 2003), when no excess is kept; years 3-5 at 5%; then down to g
    f = {"valuation": {"ttm": {"revenue": 100.0, "ni": 10.0}}, "summary": {}, "history": [{"ebit_margin": 0.2}] * 8}
    k = {"ebit": 15.0, "shares": 10.0, "ind_margin": 0.1, "base_growth": 0.05} | KEEP
    p = value.paths(f, k, "ordinary", {"eps": [1.3, 1.625], "revenue": [120.0, None], "eps0": 1.0}, 0.02)
    assert p["growth"][:5] == pytest.approx([0.2, 0.05, 0.05, 0.05, 0.05])
    assert p["growth"][5:] == pytest.approx([0.05 - 0.03 * i / 5 for i in range(1, 6)])
    m1 = 15 * 1.3 / 120  # operating income grows with profit in the consensus year, then its gap below the median shrinks
    assert p["margin"][:2] == pytest.approx([m1, 0.2 + (m1 - 0.2) * 0.6])


def test_sales_growth_keeps_its_measured_shares_and_established_margins_stay():
    # shares kept 0.3, 0.1, 0.1, 0.05 in the years after the consensus year: 5% + share x (20% - 5%), no cliff to the
    # base rate, ending near it by year 5; a 3-year trend without a consensus takes the 3-year shares
    f = {"valuation": {"ttm": {"revenue": 100.0, "ni": 10.0}}, "summary": {"rev_cagr_3y": 0.25}, "history": [{"ebit_margin": 0.06}] * 8}
    k = {"ebit": 6.0, "shares": 10.0, "ind_margin": 0.1, "mature_margin": 0.085, "base_growth": 0.05,
         "growth_shares": [0.3, 0.1, 0.1, 0.05, 0.0], "trend_shares": [0.2, 0.2, 0.1, 0.1, 0.0]} | KEEP
    p = value.paths(f, k, "fast_grower", {"eps": [1.3, 1.625], "revenue": [120.0, None]}, 0.02)
    assert p["growth"][:5] == pytest.approx([0.2, 0.095, 0.065, 0.065, 0.0575])
    trend = value.paths(f, k, "fast_grower", {"eps": [], "revenue": []}, 0.02)
    assert trend["growth"][:5] == pytest.approx([0.25, 0.09, 0.09, 0.07, 0.07])
    assert p["target_margin"] == 0.06  # profitable every year: its own margin, not mature peers'
    young = f | {"history": [{"ebit_margin": -0.01}] + [{"ebit_margin": 0.06}] * 7}
    assert value.paths(young, k, "fast_grower", {"eps": [], "revenue": []}, 0.02)["target_margin"] == 0.085


def test_growth_shares_from_the_history(monkeypatch):
    # 40 companies whose growth never changes (0-19.5% a year): all of the past excess carries on, each year
    import pandas as pd
    rev = pd.DataFrame({str(y): [100.0 * (1 + 0.005 * i) ** (y - 2010) for i in range(40)] for y in range(2010, 2023)},
                       index=[f"c{i}" for i in range(40)])
    monkeypatch.setattr(fade, "revenue_table", lambda market: rev)
    assert fade.growth_shares.__wrapped__("cn", 1) == pytest.approx([1.0] * 5, abs=0.02)
    assert fade.pav([0.30, 0.06, 0.10, 0.20, 0.15]) == pytest.approx([0.30, 0.1275, 0.1275, 0.1275, 0.1275])


def test_margin_gap_kept_net_of_the_market_drift():
    # 20 companies at 10% for 5 years; then 5 jump to 20% and are at 13% 3 years on, while the other 15 (the market's
    # median) fall to 8%: net of that 2-point drift the 5 keep (13% - 10% + 2%) / 10% = 50% of their gap
    import pandas as pd
    years = [str(y) for y in range(2010, 2019)]
    rows = {f"c{i}": [0.10] * 5 + ([0.20, 0.18, 0.16, 0.13] if i < 5 else [0.10, 0.09, 0.085, 0.08]) for i in range(20)}
    m = pd.DataFrame(rows, index=years).T
    r = fade.margin_kept(m, 5, False, 3, "above")
    assert r["n"] == 5 and r["median"] == pytest.approx(0.5)
    assert fade.margin_kept(m, 5, False, 3, "above", net=False)["median"] == pytest.approx(0.3)


def test_twelve_month_target_closes_a_third_of_the_gap():
    # price 100, cost of equity 8%, dividend 2: 106 a year on; a fair value of 106 x 1.331 closes 10% of it a year
    carry = 100 * 1.08 - 2
    assert rating.converge(carry * 1.1 ** 3, carry) == pytest.approx(carry * 1.1)
    assert rating.converge(carry / 1.1 ** 3, carry) == pytest.approx(carry / 1.1)  # the same way down
    assert rating.converge(carry, carry) == pytest.approx(carry) and rating.converge(0.0, carry) == 0.0


def test_base_rate_of_the_latest_complete_window(monkeypatch):
    # 10 companies growing 0-9% a year, the largest fastest; 2015-2021 with 2021 possibly partial (cols[-1]): today's
    # base rate is the largest fifth's median over 2015-2020 (rank 80% and up: c7-c9, 7-9%)
    import pandas as pd
    years = range(2015, 2022)
    rev = pd.DataFrame({str(y): [100.0 * (i + 1) * (1 + 0.01 * i) ** (y - 2015) for i in range(10)] for y in years},
                       index=[f"c{i}" for i in range(10)])
    monkeypatch.setattr(fade, "revenue_table", lambda market: rev)
    b = fade.base_rates("cn", 5000.0, {})
    assert b["recent_window"] == "2015-2020" and b["fifth"] == 5 and b["fifth_recent"] == pytest.approx(0.08)


def test_a_cyclical_normalized_on_its_capital():
    # 10 years: the return on operating capital (equity + debt - cash - stakes) alternates 10% and 30% (average 20%) at
    # margins of 10% and 30% (average 20%); today's capital 500 (equity 400 + debt 200 - cash 50 - stakes 50): normal
    # operating profit 20% x 500 = 100 on a normal revenue of 100 / 20% = 500, whatever the trailing revenue (1000 at a
    # price peak); new capital earns the normal 20% (sales to capital 1)
    h = [{"ebit_margin": m, "revenue": 100.0, "equity": 80.0, "debt": 30.0, "cash": 10.0, "nonop": 0.0,  # capital 100
          "period": f"{2016 + i}-12-31"} for i, m in enumerate((0.1, 0.3) * 5)]
    f = {"history": h, "valuation": {"book_common": 400.0, "ttm": {"revenue": 1000.0}, "balance": {"period": "2025-12-31"}},
         "summary": {}, "latest": {"period": "2025-12-31"}}
    k = {"debt": 200.0, "cash": 50.0, "nonop": 50.0, "ebit": 300.0, "shares": 10.0, "ind_margin": 0.1,
         "base_growth": 0.05, "growth_shares": [0.3] * 5} | KEEP
    nm = value.normal(f, k)
    assert nm["roc"] == pytest.approx(0.2) and nm["capital"] == 500 and nm["ebit"] == pytest.approx(100)
    assert nm["margin"] == pytest.approx(0.2) and nm["revenue"] == pytest.approx(500)
    # the consensus years are earned as forecast (+20% then +10% on 1000 at 30% and 35%), and growth past them is the
    # base rate from the normal year: none of their excess is carried on
    p = value.paths(f, k, "cyclical", {"eps": [1.2 * 3, 1.32 * 3.5], "revenue": [1200.0, 1320.0], "eps0": 3.0}, 0.02)
    assert p["earned"] == [pytest.approx((1200, 360)), pytest.approx((1320, 1320 * 0.35))]
    assert p["revenue0"] == pytest.approx(500) and p["sales_to_capital"] == pytest.approx(1.0)
    assert p["growth"][:5] == pytest.approx([0.05] * 5) and p["growth"][9] == pytest.approx(0.02)
    assert p["margin"] == pytest.approx([0.2] * 10)
    # a US filer's equity from a later 10-Q, its cash and debt from the 10-K: the 10-K's equity too (one balance sheet)
    later = f | {"latest": {"period": "2026-06-30"}, "history": h[:-1] + [h[-1] | {"equity": 300.0}]}
    assert value.normal(later, k)["capital"] == 400
    low = f | {"history": h[:4]}  # under 5 years of returns: the margin variant on the trailing revenue
    assert value.normal(low, k)["revenue"] == 1000.0 and value.normal(low, k)["roc"] is None


def test_earned_years_add_their_income_above_normal():
    # a normal path at 10% margin on 100, flat; the first year earns 50 instead of 10: the value rises by the 40 after
    # tax (25%) discounted a year at 10%, the reinvestment unchanged, the revenue shown as forecast
    args = (100.0, [0.0] * 10, [0.1] * 10, [0.25] * 10, [1.0] * 10, [0.1] * 10, 0.0, 0.1, [], 0.25)
    plain, peak = dcf.fcff(*args), dcf.fcff(*args, earned=[(300.0, 50.0)])
    assert peak["operating"] - plain["operating"] == pytest.approx(40 * 0.75 / 1.1)
    assert peak["revenue"][0] == 300 and peak["reinvestment"] == plain["reinvestment"] and peak["ebit"][1] == 10


def test_moat_off_and_on_in_the_scenarios():
    # a track of 0.6 and an edge of 10 points over a 7% cost: off, the excess ends with the explicit years; on, the
    # odds come true (a track of 1), fading at the same measured rate
    m = value.moat(pd_series([0.17] * 6 + [0.05] * 4), 0.07, 0.07, 0.9)
    assert m["track"] == pytest.approx(0.6) and m["edge"] == pytest.approx(0.10)
    off, on = value.moat_case(m, "off"), value.moat_case(m, "on")
    assert off["ronic"] == [] and off["start"] == 0.07 and not off["moat"]
    assert on["ronic"][0] == pytest.approx(0.07 + 0.10 * 0.9 ** 11) and on["track"] == 1.0
    assert value.moat_case(m, None) is m


def pd_series(values):
    import pandas as pd
    return pd.Series(values)


def test_excess_earnings_of_a_cyclical_at_a_peak():
    # consensus 30 and 20 against a normal 10, at 10%: 20 + 10 / 1.1 from now, a year less from the target date
    assert rating.excess([30.0, 20.0], 10.0, 0.10, 0) == pytest.approx(20 + 10 / 1.1)
    assert rating.excess([30.0, 20.0], 10.0, 0.10, 1) == pytest.approx(20 / 1.1 + 10 / 1.21)
    assert rating.excess([5.0], 10.0, 0.10, 0) == pytest.approx(-5)  # a trough subtracts


def test_peer_medians_need_ten_members(monkeypatch):
    import pandas as pd
    rows = [{"code": f"C{i}", "industry": "Hardware" if i < 5 else "Software", "sector": "Tech", "pe": 10.0 + i,
             "ev": 100.0, "revenue_ttm": 50.0, "ebit": 10.0 if i % 2 else -5.0, "fwd_pe": 20.0, "fwd_growth": 0.1}
            for i in range(30)]
    monkeypatch.setattr("stockreport.research.sheet.snapshot", lambda market, today: pd.DataFrame(rows))
    f = {"market": "us", "code": "C0", "peers": {"by": "industry", "group": "Hardware"}}
    p = value.peer_medians(f, date(2026, 11, 9))
    assert (p["by"], p["group"], p["count"]) == ("sector", "Tech", 29)  # 5 in its industry: the sector, itself left out
    assert p["pe"] == pytest.approx(25.0) and p["ev_sales"] == pytest.approx(2.0) and p["peg"] == pytest.approx(2.0)
    assert p["mature_margin"] == pytest.approx(0.2) and p["profitable"] == 15
    assert p["mature_quartiles"] == [pytest.approx(0.2)] * 2  # every profitable member at 20%
    assert value.peer_medians(f, date(2026, 11, 9), 0.25)["pe"] == pytest.approx(18.0)  # a scenario's quartile (11-39)
    f["peers"]["group"], f["code"] = "Software", "C10"
    assert value.peer_medians(f, date(2026, 11, 9))["by"] == "industry"  # 25 in its industry


def test_excess_return_kept_net_of_the_market_drift():
    # 5 companies at 20% against a 5% hurdle for 5 years (an excess of 15 points), at 12.5% 5 years on; 15 at 6% (too
    # close to the hurdle to count) that, as the market's median, drift down 1 point: (12.5% - 5% + 1%) / 15% kept
    import pandas as pd
    years = [str(y) for y in range(2010, 2020)]
    t = pd.DataFrame({f"c{i}": [0.20] * 5 + [0.15] * 4 + [0.125] if i < 5 else [0.06] * 9 + [0.05] for i in range(20)},
                     index=years).T
    kept, n = fade.excess_kept(t, 0.05, 5)
    assert n == 5 and kept == pytest.approx((0.125 - 0.05 + 0.01) / 0.15)


def test_a_growth_firm_in_a_cyclical_industry_is_typed_by_its_growth():
    # margins 30% with a halved year (10%) in Damodaran's Semiconductor industry: NVIDIA's shape (revenue 7 -> 216 over
    # 10 years, its 5-year averages 52% a year apart) is a fast grower; Micron's (flat, then a 4x price spike in the
    # last year: 15% a year across the cycle) stays cyclical, as does a Materials producer growing as fast as NVIDIA
    margins = [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.1, 0.3, 0.3, 0.3]
    def f(revenue, sector="Information Technology", industry="Semiconductor"):
        return {"kind": "general", "market": "us", "name": "X", "damodaran": {"sector": sector, "industry": industry},
                "valuation": {"ttm": {"revenue": revenue[-1]}}, "history": [{"ebit_margin": m, "revenue": r}
                for m, r in zip(margins[-len(revenue):], revenue)], "summary": {"rev_cagr_3y": (revenue[-1] / revenue[-4]) ** (1 / 3) - 1}}
    k = {"ebit": 30.0}
    nvda = [6.9, 9.7, 11.7, 10.9, 16.7, 26.9, 27.0, 60.9, 130.5, 215.9]
    mu = [20.3, 30.4, 23.4, 21.4, 27.7, 30.8, 15.5, 25.1, 37.4, 133.2]
    assert value.cycle_growth(f(nvda)) == pytest.approx((92.24 / 11.18) ** 0.2 - 1, rel=1e-3)
    assert value.kind_of(f(nvda), k, None)[0] == "fast_grower"
    assert value.kind_of(f(mu), k, None)[0] == "cyclical" and value.cycle_growth(f(mu)) < value.FAST
    assert value.kind_of(f(nvda, "Materials", "Chemical (Basic)"), k, None)[0] == "cyclical"  # revenue is a price
    assert value.kind_of(f(nvda[-6:]), k, None)[0] == "cyclical"  # under 10 years: the cycle can't be measured
