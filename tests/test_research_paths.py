"""Stage 25: growth companies valued over comparable companies' revenue paths, and what the price needs."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from stockreport.research import comparables as cp
from stockreport.research import compare, rating, value

YEARS = [str(y) for y in range(2009, 2026)]


def facts(revenue: float = 100.0) -> dict:
    return {"market": "us", "valuation": {"ttm": {"revenue": revenue}, "book_common": 80.0, "balance": {"period": "2026-06-30"}},
            "latest": {"period": "2026-06-30"}, "history": [], "summary": {}}


K = {"wacc": 0.08, "stable_wacc": 0.08, "tax_effective": 0.2, "tax_marginal": 0.25, "g": 0.03, "debt": 10.0, "minority": 0.0,
     "cash": 30.0, "nonop": 0.0, "pref": 0.0, "shares": 10.0, "fx": 1.0}
PATH = {"growth": [0.1] * 10, "margin": [0.2] * 10, "target_margin": 0.2, "fixed_years": 0}


def steady(n: int, rate: float = 0.1) -> dict:
    """n companies of rising size, each growing at `rate` every year."""
    return {f"f{i}": [(100.0 + i) * (1 + rate) ** t for t in range(len(YEARS))] for i in range(n)}


def use_panel(monkeypatch, rows: dict):
    monkeypatch.setattr(cp, "panel", lambda market: pd.DataFrame(rows, index=YEARS).T)
    cp.windows.cache_clear()


def test_windows_keep_failures_and_leave_out_the_bought_and_the_faulty(monkeypatch):
    rows = steady(20)
    base = rows["f0"]
    rows["failed"] = base[:9] + [base[8] * 0.3] + [np.nan] * 7  # fell to under half its peak, then stopped
    rows["bought"] = base[:10] + [np.nan] * 7  # stopped with its revenue intact: most likely acquired
    rows["unit"] = base[:6] + [base[5] * 1000] + [base[5] * 1000 * 1.1 ** t for t in range(1, 11)]  # a 1,000-fold year
    rows["hole"] = base[:6] + [np.nan] + base[7:]
    use_panel(monkeypatch, rows)
    w = cp.windows("us")
    assert w["years"] == 10 and w["cohorts"] == 4
    assert {"bought", "unit", "hole"}.isdisjoint(w["code"])
    assert w["failed"][w["code"] == "failed"].all() and not w["failed"][w["code"] == "f3"].any()


def test_windows_restate_growth_in_todays_nominal_terms(monkeypatch):
    fast = {k: [v[0] * 1.2 ** min(t, 11) * 1.05 ** max(t - 11, 0) for t in range(len(YEARS))] for k, v in steady(20).items()}
    use_panel(monkeypatch, fast)  # everyone grew 20% a year to 2020, 5% since: the 2010s' rate isn't today's
    assert cp.windows("us")["growth"] == pytest.approx(np.full_like(cp.windows("us")["growth"], 0.05), abs=1e-9)


def test_a_short_table_gives_shorter_paths(monkeypatch):
    monkeypatch.setattr(cp, "panel", lambda m: pd.DataFrame(steady(20), index=YEARS).T.iloc[:, 6:])  # 2015-2025, as HK's
    cp.windows.cache_clear()
    w = cp.windows("hk")
    assert w["years"] == 7 and w["cohorts"] == 1 and np.isnan(w["growth"][:, 7:]).all() and not np.isnan(w["growth"][:, :7]).any()


def fake_windows(fifths: list[int], bands: list[int], codes: list[str]) -> dict:
    n = len(codes)
    return {"growth": np.full((n, 10), 0.1), "failed": np.zeros(n, bool), "code": np.array(codes), "fifth": np.array(fifths),
            "band": np.array(bands), "years": 10, "cohorts": 4, "latest": np.arange(1.0, 101.0)}


def test_group_widens_until_enough_companies_and_counts_each_once(monkeypatch):
    codes = [f"a{i}" for i in range(20)] * 2 + [f"b{i}" for i in range(15)] + [f"c{i}" for i in range(30)]
    fifths = [4] * 40 + [3] * 15 + [0] * 30
    monkeypatch.setattr(cp, "windows", lambda m: fake_windows(fifths, [2] * len(codes), codes))
    c = cp.group("cn", 95.0, 0.3)  # the top fifth has 20 companies: the adjacent fifth brings it to 35
    assert (c["near"], c["firms"], c["windows"], c["fifth"]) == (1, 35, 55, 5)
    assert c["weight"][:40].sum() == pytest.approx(20 / 35)  # 20 companies with two windows each weigh as 20
    assert cp.group("cn", 95.0, 0.9) is None and cp.group("cn", None, 0.3) is None  # no one in its band; no revenue


def test_the_mean_over_paths_is_above_the_median_path_and_a_failure_takes_the_distress_value():
    f, g = facts(), np.array([[0.0] * 10, [0.1] * 10, [0.3] * 10])
    c = {"growth": g, "failed": np.array([False] * 3), "weight": np.full(3, 1 / 3), "firms": 3, "windows": 3, "fifth": 5, "band": "x",
         "near": 0, "years": 10, "cohorts": 4, "failed_share": 0.0}
    one = value.dcf_value(f, K, PATH, 2.0, [], g_term=0.03)[0]
    s = cp.spread(f, K, PATH, 2.0, [], 0.03, c)
    assert s["median"] == pytest.approx(one) and s["mean"] > one and s["p25"] < one < s["p75"]  # value is convex in growth
    bad = cp.spread(f, K, PATH, 2.0, [], 0.03, c | {"failed": np.array([False, False, True])})
    assert cp.distress(f, K) == pytest.approx((0.25 * 60 + 30 - 10) / 10)  # a quarter of book operating assets, cash, less debt
    assert bad["mean"] == pytest.approx((s["p25"] + one + cp.distress(f, K)) / 3)


def test_the_margin_spread_widens_the_range_and_consensus_years_stay_fixed():
    f, g = facts(), np.array([[0.09] * 10, [0.11] * 10])
    c = {"growth": g, "failed": np.zeros(2, bool), "weight": np.full(2, 0.5), "firms": 2, "windows": 2, "fifth": 5, "band": "x",
         "near": 0, "years": 10, "cohorts": 4, "failed_share": 0.0}
    a, b = cp.spread(f, K, PATH, 2.0, [], 0.03, c), cp.spread(f, K, PATH, 2.0, [], 0.03, c, 0.05)
    assert b["p75"] - b["p25"] > a["p75"] - a["p25"] and b["mean"] == pytest.approx(a["mean"])  # value is linear in margin
    assert cp.spread(f, K, PATH, 2.0, [], 0.03, c, 0.05, -0.01)["mean"] > b["mean"]  # the sensitivity grid's cost of capital
    assert cp.filled(np.array([0.3] * 10), [0.5, 0.4] + [0.1] * 8, 2)[:3] == [0.5, 0.4, 0.3]  # the consensus's, then the window's
    assert cp.filled(np.array([0.3] * 7 + [np.nan] * 3), [0.1] * 10, 0)[6:8] == [0.3, 0.1]  # past its data: the company's fade


def test_what_the_price_needs_and_who_got_there():
    f = facts()
    d = {"path": PATH, "sales_to_capital": 2.0, "moat": {"ronic": []}, "g": 0.03}
    mult = 5.0
    g = mult ** (1 / 10) - 1
    price = value.dcf_value(f, K, PATH | {"growth": [g] * 10}, 2.0, [], g_term=0.03)[0]
    c = {"growth": np.array([[g + 0.02] * 10, [0.0] * 10, [g + 0.05] * 10, [g + 0.05] * 10]), "failed": np.array([False, False, False, True]),
         "weight": np.full(4, 0.25)}
    rows = cp.needs(f, K, d, price, c)
    assert rows[0]["margin"] == pytest.approx(0.2) and rows[0]["multiple"] == pytest.approx(mult, abs=1e-2)
    assert rows[0]["share"] == pytest.approx(0.5)  # two of four got there; the failed one doesn't count
    assert rows[1]["multiple"] < rows[0]["multiple"] and rows[2]["multiple"] < rows[1]["multiple"]  # a higher margin needs less
    poor = cp.needs(f, K, d | {"sales_to_capital": 0.2}, price * 3, c)  # new capital earns 3% against an 8% cost
    assert poor[0]["multiple"] is None and poor[0]["share"] is None


def one_year_deal(eps: dict | None = None, cagr: float = -0.18, revenue: float = 739.0) -> dict:
    return {"market": "hk", "kind": "general", "name": "X-B", "damodaran": {"industry": "Drugs (Biotechnology)", "sector": "Health Care"},
            "summary": {"rev_cagr_3y": cagr, "rev_cagr_5y": -0.3}, "consensus": {"eps": eps or {}},
            "valuation": {"ttm": {"revenue": revenue, "ebit": 491.0}},
            "history": [{"period": f"{y}-12-31", "revenue": r, "ebit_margin": -2.0} for y, r in zip(range(2021, 2026), (153.0, 96.0, 64.0, 156.0, 54.0))]}


def test_a_one_year_deal_is_not_read_as_a_business(monkeypatch):
    monkeypatch.setattr(value.sheet, "ebit", lambda m, t: t["ebit"])
    f = one_year_deal({"2026": 0.6, "2027": -0.02})  # its analysts see the profit gone by their last year
    assert value.one_off(f) == {"revenue": 64.0, "margin": -2.0}
    assert value.kind_of(f, {"ebit": 491.0}, 0.067)[0] == "pre_revenue"  # a normal year's costs are over twice its revenue
    milder = f | {"history": [x | {"ebit_margin": -0.4} for x in f["history"]]}
    assert value.kind_of(milder, {"ebit": 491.0}, 0.067)[0] == "loss_making"
    assert value.one_off(one_year_deal({"2026": 0.6, "2027": 0.7})) is None  # analysts expect it to last
    assert value.one_off(one_year_deal(cagr=0.8)) is None  # a company whose revenue was growing into it
    assert value.one_off(one_year_deal(revenue=150.0)) is None  # not out of line with its years
    k = {"ebit": 491.0, "base_growth": 0.05, "mature_margin": 0.2, "ind_margin": 0.1, "growth_shares": [0.1] * 5, "trend_shares": [0.1] * 5}
    p = value.paths(f, k, "loss_making", {"eps": [0.6, -0.02], "revenue": [766.0, 313.0]}, 0.03)
    assert p["revenue0"] == 64.0 and p["margin"][0] == -2.0 and p["fixed_years"] == 0 and p["margin"][4] == pytest.approx(0.2)


def test_an_a_and_h_issuer_settles_on_one_peer_margin(monkeypatch):
    a = {"market": "cn", "kind": "general", "code": "688180"}
    h = {"market": "hk", "kind": "general", "code": "01877"}
    groups = {"cn": {"mature_margin": None, "profitable": 7}, "hk": {"mature_margin": 0.243, "profitable": 22}}
    monkeypatch.setattr(value, "peer_medians", lambda x, today, q=0.5: groups[x["market"]])
    monkeypatch.setattr(rating, "other_lines", lambda x, today: [({"market": "hk"}, h)] if x is a else [({"market": "cn"}, a)])
    today = date(2026, 11, 23)
    assert rating.shared_peers(a, today)["mature_margin"] == 0.243 and rating.shared_peers(h, today)["mature_margin"] == 0.243
    groups["cn"] = {"mature_margin": 0.18, "profitable": 22}  # as many in each: the A line's, for both
    assert rating.shared_peers(a, today)["mature_margin"] == 0.18 and rating.shared_peers(h, today)["mature_margin"] == 0.18


def test_an_a_and_h_issuer_is_valued_on_the_a_markets_paths(monkeypatch):
    a = {"market": "cn", "summary": {"rev_cagr_3y": None}}
    h = {"market": "hk", "summary": {"rev_cagr_3y": 0.6}}
    seen = []
    monkeypatch.setattr(cp, "group", lambda m, r, g: seen.append((m, g)))
    monkeypatch.setattr(rating, "other_lines", lambda x, today: [({"market": "hk"}, h)] if x is a else [({"market": "cn"}, a)])
    today = date(2026, 11, 23)
    rating.path_group(a, 100.0, today), rating.path_group(h, 100.0, today)  # the A line has no 3 clean years: the H line's
    monkeypatch.setattr(rating, "other_lines", lambda x, today: [])
    rating.path_group(h, 100.0, today)  # Hong Kong only: its own market's
    assert seen == [("cn", 0.6), ("cn", 0.6), ("hk", 0.6)]


def test_page_one_leads_with_what_the_price_needs():
    paths = {"firms": 131, "near": 0, "band": "年增 50% 以上", "years": 10, "failed_share": 0.0}
    v = {"currency": "CNY", "market": "cn", "main": "dcf", "fair_value": 78.8, "fair_bear": 22.7, "fair_bull": 75.0,
         "methods": {"dcf": {"paths": paths, "path": {}}},
         "reverse": {"needs": [{"margin": 0.181, "multiple": 38.8, "share": 0.004}, {"margin": 0.272, "multiple": 19.5, "share": 0.027},
                               {"margin": 0.362, "multiple": 12.7, "share": 0.046}]}}
    need = compare.price_needs(v)
    assert need.startswith("现价需要") and "38.8 倍" in need and "12.7 倍" in need and "0.4%" in need and "19.5" not in need
    line = compare.path_value(v)
    assert "131 家" in line and "拉到了这个区间之上" in line and "仍上市" in line
    assert compare.path_value(v | {"market": "us", "fair_value": 60.0}).count("仍上市") == 0
    assert compare.price_needs({"reverse": {"needs": [{"margin": 0.2, "multiple": None, "share": None}]}}) is None
