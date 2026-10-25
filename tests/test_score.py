"""The score's math (PLAN.md, "The score" and "Lists"): percentiles, families, grades, the SUE, the sector cap, the
holding rule and the card's key risk, on small made-up frames."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from stockreport import lists, track
from stockreport.score import grade, score
from stockreport.signals import cn_deduct, quarters

DAY = date(2026, 10, 24)


def universe(n: int = 10, **cols) -> pd.DataFrame:
    """n stocks whose every input improves with the position (stock 9 is the best on everything)."""
    i = np.arange(n, dtype=float)
    df = pd.DataFrame({
        "name": [f"S{k}" for k in range(n)], "sector": ["a", "b"] * (n // 2), "financial": False,
        "mcap": 100.0, "price": 10.0, "np_ttm": 1 + i, "revenue_ttm": 10 + i, "bps": 1 + i, "roe": 0.05 + i / 100,
        "debt_ratio": 0.9 - i / 20, "ocf_ytd": 2 + i, "np_ytd": np.full(n, 2.0), "revenue_ytd": np.full(n, 10.0),
        "ocf_ttm": 2 + i, "gp_ttm": 1 + i, "assets": np.full(n, 10.0), "mom_12_1": i / 10, "ret_6m": 0.0,
        "shares": 10.0, "mcap_rank": np.arange(n, 0, -1), "country": "United States", "period": "2026-06-30"},
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
    assert np.isnan(s.loc["C0", "p_sp"]) and np.isnan(s.loc["C1", "p_bp"])
    value = s[["p_ep", "p_bp", "p_sp"]].mean(axis=1)  # C1: E/P and S/P only
    assert value["C1"] == pytest.approx((s.loc["C1", "p_ep"] + s.loc["C1", "p_sp"]) / 2)
    assert s["f_value"].tolist() == pytest.approx(value.rank(pct=True).tolist())  # each family ranked before combining
    quality = s[["p_roe", "p_cash", "p_debt"]].mean(axis=1)
    assert quality["C0"] == pytest.approx(s.loc["C0", "p_roe"])  # the bank: ROE alone
    cn = score(universe(), "cn", pd.DataFrame(index=[]).assign(deduct_ttm=[], sue=[]))  # no SUE anywhere
    assert (cn["f_momentum"] == 0.5).all()
    assert cn["score"].tolist() == pytest.approx(((cn["f_value"] + cn["f_quality"] + 0.5) / 3).tolist())


def test_us_financials_profitability_is_roe_among_financials():
    df = universe(financial=[True, True, True] + [False] * 7, np_ttm=[3.0, 1.0, 2.0] + [1.0] * 7, bps=1.0)  # ROE 30/10/20%
    s = score(df, "us")
    assert s.loc[["C0", "C1", "C2"], "p_gpa"].tolist() == pytest.approx([1.0, 1 / 3, 2 / 3])
    assert s.loc["C9", "p_gpa"] == pytest.approx(1.0)  # the best gross profit ÷ assets among the others
    assert "ROE 高（30%）" in s.loc["C0", "why"]  # the card words it as ROE, not gross profit


def test_grades_are_fifths():
    assert grade(pd.Series(range(10))).tolist() == list("EEDDCCBBAA")


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


def test_buys_keep_at_most_two_per_sector():
    ranked = pd.DataFrame({"sector": list("aaabbbcd")}, index=list("12345678"))
    assert list(lists.capped(ranked, 5, 2).index) == ["1", "2", "4", "5", "7"]


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
    assert out.loc["C10", "status"] == "复核"                      # before the anniversary, in the bottom half
    assert out.loc["C90", "status"] == "继续持有" and out.loc["C90", "recheck"] == "2027-10-01"
    assert out.loc["C60", "status"] == "卖出" and "C99 S99" in out.loc["C60", "reason"]  # outside the top fifth at 12 months
    assert out.loc["X1", "status"] == "复核" and "missing fundamentals" in out.loc["X1", "reason"]
    # held since 2024-06: its second year started 2025-06 (kept then), so in-year rules apply until 2027-06-01
    assert out.loc["C70", "status"] == "继续持有" and out.loc["C70", "recheck"] == "2027-06-01"


def test_without_holdings_the_check_covers_the_last_years_buy_lists(tmp_path, monkeypatch):
    monkeypatch.setattr(lists, "HOLDINGS", tmp_path / "none.csv")
    monkeypatch.setattr(track, "PICKS_LOG", tmp_path / "picks.csv")
    pd.DataFrame({"date": ["2025-10-01", "2026-03-02", "2026-03-03", "2026-03-02"], "market": "cn", "bucket": "buy",
                  "ticker": ["OLD", "C5", "C5", "C9"], "name": "x", "score": 0.9}).to_csv(track.PICKS_LOG, index=False)
    held = lists.held("cn", DAY, pd.Index(["C9"]))  # C9 is in today's list; OLD is over a year old
    assert held.index.tolist() == ["C5"] and held.loc["C5", "since"] == "2026-03-02"


def test_key_risk_names_a_loss_heavy_debt_or_a_big_fall_first():
    df = universe(np_ttm=[-1.0] + [1.0] * 9, ret_6m=[0.0, -0.4] + [0.0] * 8, debt_ratio=[0.5, 0.5, 0.75] + [0.3] * 7)
    s = score(df, "hk")
    assert s.loc["C0", "risk"] == "近 12 个月亏损"
    assert s.loc["C1", "risk"] == "近 6 个月下跌 40%" and s.loc["C2", "risk"] == "负债率 75%"
    assert s.loc["C9", "risk"].startswith("无明显短板，最弱一项：") and s.loc["C3", "risk"].startswith("最弱一项：")


def test_words_follow_the_figure_not_the_rank():
    s = score(universe(mom_12_1=[-0.1] + [-0.2] * 9), "hk")  # C0's best component is momentum, still a fall
    assert s.loc["C0", "why"].startswith("近一年股价走弱（-10%）")
    assert s.loc["C0", "weak"].startswith("市净率高（PB 10.00）")  # its worst ratios, worded as such
