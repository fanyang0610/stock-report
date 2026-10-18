"""Valuation v2 math (docs/REVIEW.md A2): residual income, history weights, quality screen, regime episodes."""

import numpy as np
import pandas as pd
import pytest

from stockreport import anchors, engine, history


def inputs(**kw) -> pd.DataFrame:
    """One stock's engine inputs: book 10, no consensus, ROE 15% today and normal, no history weight."""
    row = {"bps_c": 10.0, "w_hist": 0.0, "roe_norm": 0.15, "phi": 1.0, "roe_cur": 0.15, "g0": 0.03,
           "has_cons": False, "e1": np.nan, "e2": np.nan, "e3": np.nan} | kw
    return pd.DataFrame([row])


def test_residual_income_hand_checked_gordon_case():
    # constant ROE 15% on a book growing 3% at r = 10%: V = B + (ROE − r) × B / (r − g) = 10 + 0.5 / 0.07
    assert engine.ri(0.10, inputs(), 0.03)[0] == pytest.approx(10 + 0.05 * 10 / 0.07)
    # the expected return at that price is r, and the ROE the price implies at r = 10% for book value is r
    assert engine.solve(lambda r: engine.ri(r, inputs(), 0.03), np.array([10 + 0.5 / 0.07]), -0.05, 0.4)[0] == pytest.approx(0.10, abs=1e-6)
    assert engine.implied_roe(inputs(), np.array([10.0]), np.array([0.10]))[0] == pytest.approx(0.10, abs=1e-6)


def test_residual_income_consensus_years_and_haircut():
    # consensus EPS 1.8, 1.854, 1.90962 = 18% on a book growing 3%; normal ROE 18%, φ = 1: at r = 8%,
    # V = 10 + (0.18 − 0.08) × 10 / (0.08 − 0.03) = 30
    cons = {"has_cons": True, "e1": 1.8, "e2": 1.854, "e3": 1.90962, "roe_cur": 0.18, "roe_norm": 0.18}
    assert engine.ri(0.08, inputs(**cons), 0.03)[0] == pytest.approx(30.0, rel=1e-6)
    # year 3 consensus 0.5 higher, at full history weight: half of it is kept (haircut 50% toward the
    # normal path 0.18 × 10.609 = 1.90962), year 4 restarts at normal ROE, so V = 30 + 0.25 / 1.08^3
    up = inputs(**cons | {"e3": 2.40962, "w_hist": 1.0})
    assert engine.ri(0.08, up, 0.03)[0] == pytest.approx(30 + 0.25 / 1.08 ** 3, rel=1e-6)


def test_terminal_spread_has_a_floor():
    # r − g below 3 points is held at 3: at r = 5% and g = 4%, 13 explicit years of 0.5 × 1.04^(t−1),
    # then the year-14 excess return divided by 0.03, not 0.01
    v = engine.ri(0.05, inputs(g0=0.04, roe_norm=0.10, roe_cur=0.10), 0.04)[0]
    explicit = sum(0.5 * 1.04 ** (t - 1) / 1.05 ** t for t in range(1, 14))
    assert v == pytest.approx(10 + explicit + 0.5 * 1.04 ** 13 / 0.03 / 1.05 ** 13)


def history_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Seven stocks: steady, cyclical, grower, grower with early losses, structural decline, cyclical
    trough with analysts' support, many loss years."""
    h = pd.DataFrame({
        "roe_hist": [0.20, 0.15, 0.10, 0.10, 0.25, 0.20, 0.08],
        "roe_vol": [0.02, 0.15, 0.07, 0.07, 0.10, 0.20, 0.01],
        "loss_years": [0, 0, 0, 2, 0, 1, 3],
        "rev_down_years": [0, 3, 0, 0, 2, 3, 0],
        "early_losses_only": [False, False, False, True, False, False, False],
        "roe_slope": [0.0, 0.0, 0.0, 0.0, -0.04, 0.0, 0.0],
        "roe_r2": [0.1, 0.1, 0.1, 0.1, 0.9, 0.1, 0.1],
        "rev_cagr_5y": [0.05, 0.02, 0.25, 0.25, 0.0, 0.02, 0.05],
        "gm_hist": [0.4] * 7, "n_years": [10] * 7,
    })
    d = pd.DataFrame({
        "roe_cur": [0.25, 0.40, 0.30, 0.30, 0.10, 0.05, 0.08], "roe_c3": [np.nan, np.nan, np.nan, np.nan, 0.12, 0.15, np.nan],
        "has_cons": [False, False, False, False, True, True, False], "e2": [1.0] * 7,
        "g_exp": [0.06, 0.02, 0.25, 0.25, 0.0, 0.02, 0.06], "g_cons": [np.nan] * 7,
    })
    return d, h


def test_history_weight_rules():
    d, h = history_frame()
    out = engine.normal(d.copy(), h, pd.Series([False] * 7), pd.Series([1.0] * 7))
    w, nn = out["w_hist"], out["roe_norm"]
    assert w[0] == 0 and nn[0] == pytest.approx(0.25)  # stable ROE: today
    assert w[1] == 1 and nn[1] == pytest.approx(0.15)  # volatile ROE, revenue down years: history
    assert w[2] == pytest.approx((0.7 - 0.3) / 0.7 * 0.3)  # grower: cycle factor 0.3
    assert nn[2] == pytest.approx(w[2] * 0.10 + (1 - w[2]) * 0.30)
    assert w[3] == 0 and nn[3] == pytest.approx(0.30)  # early losses only: today and consensus (A1)
    assert out["structural_decline"][4] and nn[4] == pytest.approx(0.12)  # steady decline: no reversion past consensus
    assert not out["structural_decline"][5] and nn[5] == pytest.approx(0.20)  # trough, analysts halfway back: reverts
    assert w[6] == pytest.approx(0.6)  # 3+ loss years count as fully volatile (cycle factor 0.6)
    assert list(out["archetype"][:3]) == ["steady", "cyclical", "growth"]


def test_quality_screen():
    df = pd.DataFrame({"financial": [False, False, False, False, True, False, False, True],
                       "gross_margin": [0.4, 0.4, 0.5, 0.4, np.nan, 0.1, 0.4, np.nan]})
    h = pd.DataFrame({
        "roe_hist": [0.15, 0.05, 0.05, 0.15, 0.12, 0.25, 0.15, 0.06],
        "n_years": [10, 10, 6, 10, 10, 10, 10, 10],
        "ocf_2y_pos": [True] * 8,
        "ocf_ni_5y": [1.1, 1.1, 1.1, 0.5, 0.3, 1.2, 1.0, 1.0],
        "fcf_5y": [1.0, 1.0, 1.0, 1.0, np.nan, 1.0, -1.0, np.nan],
        "margin_hist": [0.12, 0.12, 0.12, 0.12, 0.3, 0.03, 0.12, 0.3],
        "margin_2y": [0.12, 0.12, 0.12, 0.12, 0.3, 0.03, 0.12, 0.3],
    })
    fails = anchors.screen(df, h)["screen_fails"].tolist()
    assert fails == ["", "ROE<8%", "", "OCF/NI<0.7", "", "", "FCF<0", "ROE<8%"]
    # (2: young, gross margin > 30%, cash positive: exemption A; 4: a bank is judged on ROE alone;
    # 5: margin 3% but ROE 25% and OCF/NI 1.2: exemption C)
    h.loc[5, ["roe_hist", "ocf_ni_5y"]] = [0.15, 0.9]
    assert anchors.screen(df, h)["screen_fails"][5] == "净利率<5%"


def test_regime_episodes_and_base_rates():
    years = range(2015, 2025)
    kept = [0.05] * 5 + [0.30, 0.28, 0.25, 0.22, 0.20]
    faded = [0.05] * 5 + [0.30, 0.12, 0.08, 0.06, 0.05]
    panel = pd.DataFrame([{"code": c, "year": y, "roe": r, "rev": 100.0} for c, roes in (("A", kept), ("B", faded))
                          for y, r in zip(years, roes)])
    eps = history.episodes(panel)
    assert eps[["code", "year", "dir"]].values.tolist() == [["A", 2020, "up"], ["B", 2020, "up"]]
    assert eps.set_index("code")["kept"].to_dict() == {"A": True, "B": False}  # 2023: 0.22 vs 0.05 + 0.25 / 2
    assert history.base_rates(eps).loc[("up", "all"), "mean"] == pytest.approx(0.5)


def test_split_factor_picks_the_later_splits_that_match():
    # NVDA: SEC restated FY2021's share count after the 2021 split but not FY2020's
    splits = pd.DataFrame({"date": ["2021-07-20", "2024-06-10"], "ratio": [4.0, 10.0]})
    assert history.closest(splits, "2020-01-26", 24.3e9 / 612e6) == 40
    assert history.closest(splits, "2021-01-31", 24.3e9 / 2479e6) == 10
    assert history.closest(splits, "2025-01-26", 24.3e9 / 24.48e9) == 1


def test_small_industry_keeps_its_own_median_level():
    # 16 stocks on log P/B = 1 + 5 × ROE and a 3-stock industry at half that P/B: the small industry takes the
    # pooled slope at its own median level, so its middle member's peer value is its own price (book 10)
    roe = list(np.linspace(0.05, 0.20, 16)) + [0.08, 0.12, 0.16]
    pb = [np.exp(1 + 5 * r) for r in roe[:16]] + [0.5 * np.exp(1 + 5 * r) for r in roe[16:]]
    df = pd.DataFrame({"price": [10 * p for p in pb], "financial": True, "industry": ["big"] * 16 + ["small"] * 3})
    d = pd.DataFrame({"bps_c": 10.0, "roe_norm": roe, "g_exp": 0.03, "valued": True}, index=df.index)
    v = anchors.peer(df, d, pd.Series("", df.index))
    assert v[17] == pytest.approx(df["price"][17])
    assert (v[16:] / df["price"][16:]).between(0.9, 1.1).all()
