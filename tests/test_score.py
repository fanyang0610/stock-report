"""The score's math (PLAN.md, "The score" and "Lists"): percentiles among sector peers, families, grades, the SUE, the
revisions and forward E/P, the long-run components, the distress logit, the list's places, picks, screen and equal
amounts, the avoid list's sector cap, the holding rule and the card's key risk, on small made-up frames."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from stockreport import lists, track
from stockreport import universe as uni
from stockreport.fetch import frames
from stockreport.config import CONFIG
from stockreport.score import grade, phrase, ranked, score
from stockreport.signals import CHS, cn_deduct, cn_revisions, distress, long_run, quarters

DAY = date(2026, 10, 24)


def universe(n: int = 10, **cols) -> pd.DataFrame:
    """n stocks whose every input improves with the position (stock 9 is the best on everything)."""
    i = np.arange(n, dtype=float)
    df = pd.DataFrame({
        "name": [f"S{k}" for k in range(n)], "sector": ["a", "b"] * (n // 2), "financial": False,
        "mcap": 100.0, "price": 10.0, "np_ttm": 1 + i, "revenue_ttm": 10 + i, "bps": 1 + i, "roe": 0.05 + i / 100,
        "debt_ratio": 0.9 - i / 20, "ocf_ytd": 2 + i, "np_ytd": np.full(n, 2.0), "revenue_ytd": np.full(n, 10.0),
        "ocf_ttm": 2 + i, "gp_ttm": 1 + i, "assets": np.full(n, 10.0), "mom_12_1": i / 10, "ret_6m": 0.0,
        "shares": 10.0, "mcap_rank": np.arange(n, 0, -1), "country": "United States", "period": "2026-06-30",
        "div_yield": i / 100, "vol_1y": 0.5 - i / 50, "rev_growth": i / 10, "np_growth": i / 10},
        index=[f"C{k}" for k in range(n)])
    return df.assign(**cols)


def test_percentiles_rank_within_the_market_and_low_debt_is_better():
    s = score(universe(), "hk")
    assert s["p_ep"].tolist() == pytest.approx(np.arange(1, 11) / 10)
    assert s["p_debt"].tolist() == pytest.approx(np.arange(1, 11) / 10)  # lower debt, higher percentile
    assert s.loc["C9", "score"] == pytest.approx(1.0) and s.loc["C9", "score_rank"] == 1
    assert s.loc["C0", "g_value"] == "E" and s.loc["C9", "g_quality"] == "A"


def test_a_family_skips_missing_components_and_a_missing_family_counts_50():
    df = universe(financial=[True] + [False] * 9)  # a bank: no S/P, cash backing or debt
    df.loc["C1", "bps"] = -1.0                     # negative book: no B/P
    s = score(df, "hk")
    assert np.isnan(s.loc["C0", "p_sp"]) and np.isnan(s.loc["C1", "p_bp"]) and np.isnan(s.loc["C0", "p_ev"])
    value = s[["p_ep", "p_bp", "p_sp", "p_dy"]].mean(axis=1)  # C1: E/P, S/P and the dividend yield; no EBIT/EV here
    assert value["C1"] == pytest.approx((s.loc["C1", "p_ep"] + s.loc["C1", "p_sp"] + s.loc["C1", "p_dy"]) / 3)
    ranked = value.groupby(s["financial"]).rank(pct=True)  # ranked among financials and among the rest
    assert s["f_value"].tolist() == pytest.approx(ranked.tolist()) and s.loc["C0", "f_value"] == 1.0
    quality = s[["p_roe", "p_cash", "p_debt", "p_vol"]].mean(axis=1)
    assert quality["C0"] == pytest.approx((s.loc["C0", "p_roe"] + s.loc["C0", "p_vol"]) / 2)  # the bank: no cash, debt
    cn = score(universe(), "cn", pd.DataFrame(index=[]).assign(deduct_ttm=[], sue=[]))  # no SUE anywhere
    assert (cn["f_momentum"] == 0.5).all()
    four = (cn["f_value"] + cn["f_quality"] + cn["f_growth"] + 0.5) / 4
    assert cn["score"].tolist() == pytest.approx(four.tolist())


def test_us_financials_profitability_is_roe_among_financials():
    df = universe(financial=[True, True, True] + [False] * 7, np_ttm=[3.0, 1.0, 2.0] + [1.0] * 7, bps=1.0)  # ROE 30/10/20%
    s = score(df, "us")
    assert s.loc[["C0", "C1", "C2"], "p_gpa"].tolist() == pytest.approx([1.0, 1 / 3, 2 / 3])
    assert s.loc["C9", "p_gpa"] == pytest.approx(1.0)  # the best gross profit ÷ assets among the others
    assert "ROE 高（30%）" in s.loc["C0", "why"]  # the card words it as ROE, not gross profit


def test_us_financials_are_banks_insurers_brokers_and_lenders(tmp_path, monkeypatch):
    monkeypatch.setattr(frames, "SIC", tmp_path / "sic.csv.gz")
    pd.DataFrame({"code": ["1", "2", "3", "4"], "sic": [6199.0, 7320.0, 6324.0, 6282.0]}).to_csv(frames.SIC, index=False)
    industry = pd.Series(["Finance: Consumer Services", "Finance: Consumer Services", "Medical Specialities",
                          "Investment Managers", "Major Banks"], index=["AXP", "MCO", "UNH", "BX", "JPM"])
    cik = pd.Series([1, 2, 3, 4, None], index=industry.index)
    assert uni.us_financial(industry, cik).tolist() == [True, False, True, False, True]  # lender, ratings, insurer


def test_grades_are_fifths():
    assert grade(pd.Series(range(1, 11)) / 10).tolist() == list("EEDDCCBBAA")  # percentiles among the peers


def ytd_table(single: list[float], start: int = 2022, code: str = "A") -> pd.DataFrame:
    """Year-to-date rows from single-quarter values, each noticed a month after its quarter."""
    rows, ytd = [], 0.0
    for k, q in enumerate(single):
        year, quarter = start + k // 4, k % 4 + 1
        ytd = q if quarter == 1 else ytd + q
        end = pd.Period(f"{year}Q{quarter}").end_time
        rows.append({"code": code, "period": end.strftime("%Y-%m-%d"), "deduct": ytd,
                     "notice_date": (end + pd.Timedelta(days=30)).strftime("%Y-%m-%d")})
    return pd.DataFrame(rows)


def test_sue_is_the_quarters_change_over_its_spread():
    single = [10, 11, 12, 13, 12, 12, 15, 14, 13, 16, 15, 18, 20, 15, 17, 25]  # 2022Q1..2025Q4
    ttm, sue = quarters(ytd_table(single))
    change = np.array(single[4:]) - np.array(single[:-4])  # 12 year-on-year changes
    assert sue.loc["A", "2025-12-31"] == pytest.approx(change[-1] / change[-9:-1].std(ddof=1))  # the preceding 8
    assert ttm.loc["A", "2025-12-31"] == pytest.approx(sum(single[-4:]))
    assert np.isnan(sue.loc["A", "2024-03-31"])  # 4 preceding changes known, 6 needed


def test_sue_uses_only_reports_noticed_by_the_day():
    table = ytd_table([10, 11, 12, 13, 12, 12, 15, 14, 13, 16, 15, 18, 20, 15, 17, 25, 30])  # .. 2026Q1, noticed 2026-04-30
    before, after = cn_deduct(table, "2026-04-29"), cn_deduct(table, "2026-04-30")
    assert before.loc["A", "deduct_period"] == "2025-12-31" and after.loc["A", "deduct_period"] == "2026-03-31"
    assert after.loc["A", "deduct_ttm"] == pytest.approx(15 + 17 + 25 + 30)


def test_avoid_names_keep_at_most_two_per_sector():
    ranked = pd.DataFrame({"sector": list("aaabbbcd")}, index=list("12345678"))
    assert list(lists.capped(ranked, 5, 2).index) == ["1", "2", "4", "5", "7"]


def test_peers_are_the_sector_and_a_small_sector_ranks_with_the_market():
    s = score(universe(30, sector=["a"] * 12 + ["b"] * 12 + ["c"] * 6), "hk")
    assert s.loc["C11", "p_ep"] == 1.0 and s.loc["C12", "p_ep"] == pytest.approx(1 / 12)  # the best of a, the worst of b
    assert s.loc["C24", "peers"] == "全市场" and s.loc["C24", "p_ep"] == pytest.approx(25 / 30)  # 6 in c: all 30
    assert s.loc["C11", "g_value"] == "A" and s.loc["C12", "g_value"] == "E"
    assert s.loc["C11", "why"].startswith("同行中")  # worded against its sector


def test_forward_ep_and_revisions_need_three_estimates():
    s = score(universe(eps_e2=2.0, analysts=[2] + [5] * 9, est_now=1.2, est_90=1.0, est_n=[5, 2] + [3] * 8), "hk")
    assert np.isnan(s.loc["C0", "c_fep"]) and s.loc["C1", "c_fep"] == pytest.approx(0.2)  # 2.0 ÷ the price 10
    assert np.isnan(s.loc["C1", "c_rev"]) and s.loc["C0", "c_rev"] == pytest.approx(0.02)  # (1.2 − 1.0) ÷ 10
    assert phrase(s.loc["C0"], "rev", "hk") == "分析师 3 个月上调明年盈利预测（+20%）"


def test_cn_revisions_take_each_brokers_latest_estimate_and_undo_bonus_shares():
    rows = [("A", "2026-03-01", "x", 1.00), ("A", "2026-09-01", "x", 1.30), ("A", "2026-05-01", "y", 1.10),
            ("A", "2026-06-01", "z", 1.20), ("A", "2026-10-01", "z", 1.50), ("A", "2025-12-01", "w", 0.50),
            ("B", "2026-05-01", "p", 2.0), ("B", "2026-05-01", "q", 2.2), ("B", "2026-05-01", "r", 2.4),
            ("B", "2026-09-01", "p", 1.2), ("B", "2026-09-01", "q", 1.1), ("B", "2026-09-01", "r", 1.3),
            ("C", "2026-05-01", "p", 1.0), ("C", "2026-09-01", "p", 1.1), ("C", "2026-09-01", "q", 1.2)]
    rep = pd.DataFrame(rows, columns=["code", "publish", "org", "eps"]).assign(year=2027)
    rep = pd.concat([rep, pd.DataFrame([{"code": "A", "publish": "2026-09-01", "org": "x", "year": 2028, "eps": 9.0}])])
    bonus = pd.DataFrame({"code": ["B"], "ex_date": ["2026-06-15"], "bonus": [1.0]})  # 10 送 10 between the dates
    est = cn_revisions(rep, bonus, pd.Series(2027, index=["A", "B", "C"]), "2026-10-26")
    # A 91 days ago (to 07-27): x 1.00, y 1.10, z 1.20; today: x 1.30, y 1.10 (still within 180 days), z 1.50
    assert est.loc["A"].tolist() == pytest.approx([1.30, 1.10, 3])
    assert est.loc["B"].tolist() == pytest.approx([1.2, 1.1, 3])  # the older 2.0 / 2.2 / 2.4 per share before the bonus
    assert est.loc["C", "est_n"] == 1  # one broker 91 days ago: too few for the score (MIN_ANALYSTS)


def test_places_follow_the_market_share_within_each_sectors_room():
    w = pd.Series({"a": 0.47, "b": 0.33, "c": 0.20})
    assert lists.slots(w, 10, pd.Series({"a": 9, "b": 9, "c": 9})).to_dict() == {"a": 5, "b": 3, "c": 2}
    assert lists.slots(w, 10, pd.Series({"c": 9, "a": 3, "b": 9})).to_dict() == {"a": 3, "b": 4, "c": 3}  # a full


def picks_field() -> pd.DataFrame:
    a = pd.DataFrame({"sector": "a", "score": np.linspace(0.9, 0.1, 20), "float_value": 1.0}, index=[f"A{k}" for k in range(20)])
    a.loc["A19", "float_value"] = 40.0  # the sector's largest company, with the worst score
    b = pd.DataFrame({"sector": "b", "score": [0.8, 0.7, 0.6, 0.5, 0.4], "float_value": 6.0}, index=[f"B{k}" for k in range(5)])
    df = pd.concat([a, b])
    return df.assign(financial=False, distress=0.0, sta=0.0, name=df.index)


def test_picks_are_each_sectors_best_scores_in_equal_amounts():
    buys, bench = lists.positions(picks_field(), 4, "us")  # a holds 60 of 90 by free float: 3 places, b 1
    assert buys.index.tolist() == ["A0", "A1", "A2", "B0"] and set(bench.index) == {"A3", "B1"}  # by score, not size
    assert buys["weight"].tolist() == pytest.approx([0.25] * 4)


def test_exact_ties_go_to_the_larger_free_float_then_the_lower_code_whatever_the_row_order():
    df = picks_field()
    df.loc[["A1", "A2", "A3"], "score"] = 0.9  # four names tie with A0 for sector a's three places
    df.loc["A1", "float_value"] = 2.0  # the largest of the four
    for rows in (df, df.iloc[::-1], df.sample(frac=1, random_state=7)):
        buys, bench = lists.positions(rows, 4, "us")
        assert buys.index.tolist() == ["A1", "A0", "A2", "B0"] and bench.index.tolist() == ["A3", "B1"]
        assert ranked(rows).index[:4].tolist() == ["A1", "A0", "A2", "A3"]
    families = pd.DataFrame([[26, 28, 20, 26], [29, 16, 28, 27]], index=["X1", "X2"]) / 29  # both average 25/29
    noisy = pd.DataFrame({"score": families.mean(axis=1), "float_value": [1.0, 4.0]})  # one bit apart as floats
    assert noisy["score"].iloc[0] != noisy["score"].iloc[1] and ranked(noisy).index.tolist() == ["X2", "X1"]
    same = universe(10, mom_12_1=0.0, np_ttm=1.0, revenue_ttm=10.0, bps=1.0, roe=0.05, debt_ratio=0.5, ocf_ttm=2.0,
                    gp_ttm=1.0, ocf_ytd=2.0, div_yield=0.0, vol_1y=0.3, rev_growth=0.0, np_growth=0.0)
    s = score(same.iloc[::-1], "hk")  # every name ties, listed backwards: ranked by code, not by row
    assert s["score"].nunique() == 1 and s.sort_index()["score_rank"].tolist() == list(range(1, 11))


def test_the_most_distressed_and_the_largest_accruals_are_not_bought(monkeypatch):
    monkeypatch.setitem(CONFIG["lists"], "screen", 0.05)
    df = picks_field()
    df.loc["A0", "distress"], df.loc["A1", "sta"] = 5.0, 0.3  # the worst of 25 on each: the top 5% (1.25 names)
    buys, _ = lists.positions(df, 4, "us")
    assert "A0" not in buys.index and "A1" not in buys.index and buys.index.tolist() == ["A2", "B0", "A3", "A4"]
    df.loc["A0", "financial"] = True  # a bank isn't judged on it
    assert lists.screened(df).sum() == 1


def test_hk_small_caps_and_partnerships_cant_be_bought(monkeypatch):
    monkeypatch.setitem(CONFIG["lists"], "small_share", {"hk": 0.05})
    df = picks_field()  # 89 of free-float value: A19 40, B 30, the other 19 A names 1 each
    hk = lists.buyable(df, "hk")  # the names that start past 95% of the value (84.55 of 89): A15 to A18
    assert lists.buyable(df, "us").all() and hk.sum() == 21 and not hk[["A15", "A16", "A17", "A18"]].any() and hk["A14"]
    df.loc["B0", "name"] = "Western Midstream Partners LP"
    buys, _ = lists.positions(df, 4, "us")
    assert "B0" not in buys.index and "B1" in buys.index


def test_distress_logit_weighs_campbell_hilscher_szilagyi_with_winsorized_inputs():
    k = np.arange(21.0)
    df = pd.DataFrame({"mcap": 100.0, "liabilities": 100.0 + 10 * k, "np_ttm": 8.0 - k, "bps": 5.0, "shares": 10.0,
                       "ret_12m": 0.2 - k / 50, "vol_3m": 0.2 + k / 50, "cash": 20.0 - k / 2, "financial": False},
                      index=[f"S{i}" for i in range(21)])
    x = distress(df)
    mta = 300.0  # S10, the median on every input, isn't clipped: market value 100 + liabilities 200
    want = (CHS["nimta"] * (-2 / 4) / mta + CHS["tlmta"] * 200 / mta + CHS["exret"] * 0 + CHS["sigma"] * 0.4
            + CHS["rsize"] * np.log(100) + CHS["cashmta"] * 15 / mta + CHS["mb"] * 100 / (50 + 0.1 * 50))
    assert x["S10"] == pytest.approx(want) and x["S20"] > x["S10"] > x["S0"]
    df.loc["S0", "bps"], df.loc["S1", "bps"] = -30.0, -2000.0  # negative books: the highest market-to-book, capped
    y = distress(df)
    assert np.isfinite(y["S1"]) and y["S1"] - x["S1"] == pytest.approx(y["S0"] - x["S0"])  # both at the 95th percentile


def test_long_run_takes_the_years_public_by_the_day():
    years = pd.DataFrame({"code": "A", "year": range(2015, 2026), "roe": [0.1] * 10 + [0.3], "core": range(10, 21),
                          "book": 100.0, "gm": [0.4, 0.5] * 5 + [0.45], "avail": [f"{y + 1}-03-31" for y in range(2015, 2026)]})
    lr = long_run(years, "2026-03-30").loc["A"]  # FY2025 not yet public: 2017-2024
    assert lr["prof8"] == pytest.approx(0.1) and lr["gm8"] == pytest.approx(0.45 / pd.Series([0.4, 0.5] * 4).std())
    assert lr["roe5"] == pytest.approx((19 - 14) / 100)  # FY2024 against FY2019, over FY2019's book
    assert long_run(years, "2026-03-31").loc["A", "prof8"] == pytest.approx((0.1 * 7 + 0.3) / 8)
    assert long_run(years[years["year"] >= 2022], "2026-03-31").isna().all(axis=None)  # 4 years: too few


def test_holding_rule(tmp_path, monkeypatch):
    df = universe(100).assign(score=np.linspace(0, 1, 100), mcap_rank=np.arange(1, 101))
    df["score_rank"] = df["score"].rank(ascending=False).astype(int)
    monkeypatch.setattr(lists, "HOLDINGS", tmp_path / "holdings.csv")
    pd.DataFrame({"market": "cn", "code": ["C95", "C10", "C90", "C60", "C70", "X1"], "name": "",
                  "since": ["2026-07-01", "2026-07-01", "2025-10-01", "2025-10-01", "2024-06-01", "2026-01-05"]}
                 ).to_csv(lists.HOLDINGS, index=False)
    buys = df.sort_values("score", ascending=False).head(3)  # C99, C98, C97: none held
    out = lists.check(df, "cn", DAY, buys, {"X1": "missing fundamentals"}).set_index("code")
    assert out.loc["C95", "status"] == "继续持有" and out.loc["C95", "recheck"] == "2027-07-01"
    assert out.loc["C10", "status"] == "复核"                      # before the anniversary, in its sector's bottom half
    assert "同行业 50 只中第 45 名" in out.loc["C10", "reason"]  # judged within its sector, as buys are picked
    assert out.loc["C90", "status"] == "继续持有" and out.loc["C90", "recheck"] == "2027-10-01"
    assert out.loc["C60", "status"] == "卖出" and "C99 S99" in out.loc["C60", "reason"]  # outside the top fifth at 12 months
    assert out.loc["X1", "status"] == "复核" and "数据缺失或与第二来源对不上" in out.loc["X1", "reason"]
    # held since 2024-06: its second year started 2025-06 (kept then), so in-year rules apply until 2027-06-01
    assert out.loc["C70", "status"] == "继续持有" and out.loc["C70", "recheck"] == "2027-06-01"


def test_without_holdings_the_hold_rating_covers_the_buys_sent_to_you_until_their_review_window_ends(tmp_path, monkeypatch):
    monkeypatch.setattr(lists, "HOLDINGS", tmp_path / "holdings.csv")
    lists.HOLDINGS.write_text("market,code,name,since\n")  # an empty file (the last one sold) is no holdings
    monkeypatch.setattr(track, "SENT_LOG", tmp_path / "sent.csv")
    pd.DataFrame({"date": ["2025-10-20", "2025-10-25", "2025-09-30", "2025-09-01", "2026-10-01", "2025-09-30"],
                  "market": "cn", "ticker": ["C5", "C5", "C6", "C7", "C9", "C96"], "name": "x"}).to_csv(track.SENT_LOG, index=False)
    held = lists.held("cn", DAY, pd.Index(["C9"]))  # C9 is in today's list: a buy, not a hold
    assert held["since"].to_dict() == {"C5": "2025-10-25", "C6": "2025-09-30", "C96": "2025-09-30"}  # the last list sent
    # C6's year ended 2026-09-30: judged now, in the 30 days to act; C7's ended 2026-09-01, past them: no longer rated
    df = universe(100).assign(score=np.linspace(0, 1, 100), mcap_rank=np.arange(1, 101))
    out = lists.check(df, "cn", DAY, df.sort_values("score").tail(3), {}).set_index("code")
    assert out.loc["C6", "reason"].startswith("满 1 年") and out.loc["C5", "reason"].startswith("未到满年")
    # still in its sector's top fifth at 12 months: the rating's last word, with no re-check date (it then drops off)
    assert out.loc["C96", "status"] == "继续持有" and "此后不再列出" in out.loc["C96", "reason"] and out.loc["C96", "recheck"] == ""


def test_key_risk_names_a_loss_heavy_debt_or_a_big_fall_first():
    df = universe(np_ttm=[-1.0] + [1.0] * 9, ret_6m=[0.0, -0.4] + [0.0] * 8, debt_ratio=[0.5, 0.5, 0.75] + [0.3] * 7)
    s = score(df, "hk")
    assert s.loc["C0", "risk"] == "近 12 个月亏损"
    assert s.loc["C1", "risk"] == "近 6 个月下跌 40%" and s.loc["C2", "risk"] == "负债率 75%"
    assert s.loc["C9", "risk"] == "无明显短板" and s.loc["C3", "risk"].startswith("最弱一项：")


def test_a_reason_reads_well_and_a_weakness_reads_badly():
    s = score(universe(mom_12_1=np.linspace(-0.5, -0.05, 10)), "hk")  # C9 is best on everything but still fell 5%
    assert "走弱" not in s.loc["C9", "why"]  # its best percentile, but not a reason to buy
    assert s.loc["C9", "risk"] == "最弱一项：近一年股价走弱（-5%）"  # the one figure that reads badly


def test_words_follow_the_figure_not_the_rank():
    s = score(universe(mom_12_1=[-0.1] + [-0.2] * 9), "hk")  # C0's best component is momentum, still a fall
    assert s.loc["C0", "why"].startswith("近一年股价走弱（-10%）")
    assert s.loc["C0", "weak"].startswith("市净率高（PB 10.00）")  # its worst ratios, worded as such
