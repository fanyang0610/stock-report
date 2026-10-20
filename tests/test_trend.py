"""Business trend (Phase 13, "Trend first"): the evidence on the saved CN panel sample, by hand; the votes and the
class; the band per base-rate start (backtest); the trend × valuation map's never-buy and never-sell rules."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest import v3 as bt
from stockreport import baserates as br, shadow, trend

DATA = Path(__file__).parent / "data"


def sample() -> pd.DataFrame:
    return pd.read_csv(DATA / "cn_panel_sample.csv", dtype={"code": str, "avail": str}).rename(columns={"earn": "core"})


def test_evidence_by_hand_ping_an_bank():
    # 000001 FY2022-25 revenue 179.9, 164.7, 146.7, 131.4 bn; 扣非 profit 45.31, 46.46, 44.72, 42.63 bn; ROE 12.3%,
    # 11.4%, 10.1%, 9.2%
    ev = trend.evidence(sample(), ["000001"], "2026-10-19").loc["000001"]
    g = [131.442 / 146.695 - 1, 146.695 / 164.699 - 1, 164.699 / 179.895 - 1]
    sym = lambda a, b: (a - b) / ((abs(a) + abs(b)) / 2)
    p = [sym(42.633, 44.71501), sym(44.71501, 46.455), sym(46.455, 45.30911)]
    assert ev["acc_rev"] == pytest.approx(g[0] - (g[1] + g[2]) / 2, rel=1e-3)  # −0.7 points: no vote
    assert ev["acc_profit"] == pytest.approx(p[0] - (p[1] + p[2]) / 2, rel=1e-2)  # −4 points: no vote
    assert ev["acc_roe"] == pytest.approx(0.0915 - (0.1138 + 0.1230) / 2)  # −2.7 points: −1


def test_evidence_point_in_time():
    # on 2019-06-30 the latest public year is FY2018: its ROE against FY2015-16
    ev = trend.evidence(sample(), ["000001"], "2019-06-30").loc["000001"]
    assert ev["acc_roe"] == pytest.approx(0.1149 - (0.1318 + 0.1494) / 2)
    stale = trend.evidence(sample(), ["000001"], "2029-06-30").loc["000001"]  # latest year over 2 years old
    assert stale.isna().all()


def test_accelerations_with_a_loss_year():
    # revenue 100 → 110 → 121 → 145.2 (10%, 10%, then 20%: +10 points); profit −10 → 10 → 10 → 30 (symmetric
    # growth 2, 0, 1: 1 − 1 = 0); ROE 5%, 8%, 10%, 15% (15% − mean(8%, 5%) = +8.5 points), columns latest first
    rev, earn, roe = np.array([[145.2, 121, 110, 100]]), np.array([[30, 10, 10, -10]]), np.array([[0.15, 0.10, 0.08, 0.05]])
    acc = trend.accelerations(rev, earn, roe)
    assert acc["rev"][0] == pytest.approx(0.10)
    assert acc["profit"][0] == pytest.approx(0.0)
    assert acc["roe"][0] == pytest.approx(0.085)
    assert bt.band(rev, earn, roe)[0] == 2  # revenue and ROE vote +1: improving


def test_classify_counts_the_markets_evidence(monkeypatch):
    ev = pd.DataFrame({"acc_rev": [0.10, -0.10, 0.0], "acc_profit": [0.5, -0.5, 0.0], "acc_roe": [0.03, -0.03, 0.0]},
                      index=["up", "down", "flat"])
    momentum = pd.Series([0.6, -0.4, 0.1], index=ev.index)  # median 0.1: +50%, −50%, 0 over it
    revision = pd.Series([0.05, np.nan, -0.05], index=ev.index)
    monkeypatch.setitem(trend.EVIDENCE, "cn", list(trend.TEXT))
    monkeypatch.setitem(trend.NEED, "cn", 2)
    t = trend.classify(ev, momentum, revision, "cn")
    assert t["trend"].tolist() == [1, -1, 0] and t["trend_score"].tolist() == [5, -4, -1]
    assert t.at["up", "trend_why"] == "营收增速 +10pt、利润增速 +50pt、ROE +3pt、12-1 月动量 +50%、预期修正 +5%"
    monkeypatch.setitem(trend.EVIDENCE, "cn", ["momentum", "revision"])  # a market that counts the price only
    monkeypatch.setitem(trend.NEED, "cn", 1)
    t = trend.classify(ev, momentum, revision, "cn")
    assert t["trend"].tolist() == [1, -1, -1] and t.at["flat", "trend_why"] == "预期修正 -5%"


def test_trend_band_per_base_rate_start():
    # the persistence study's band, aligned with br.starts' rows; 000001's FY2025 start: one business vote, stable
    p = sample().rename(columns={"core": "earn"})
    st = br.starts(p, "9999-12-31", "cn")
    st["tb"] = bt.start_bands(p, "cn")
    assert set(st["tb"]) <= {0, 1, 2} and len(st) == len(bt.start_bands(p, "cn"))
    bank25 = st[(st["year"] == 2025) & (st["sector"] == "银行") & (st["q0"].round(4) == 0.0915)]
    assert bank25["tb"].tolist() == [1]


def test_map_never_buys_a_value_trap_never_sells_an_improver(monkeypatch):
    # 12 stocks: 6 cheap (upside +60%), 6 expensive (−60%); half improving, half deteriorating; all else equal
    n, idx = 12, [f"s{i}" for i in range(12)]
    up = np.r_[[0.6] * 6, [-0.6] * 6]
    tr = np.tile([1, -1], 6)
    v = pd.DataFrame({"valued": True, "verdict": "", "upside": up, "confidence": "高", "screen_ok": True, "trend": tr,
                      "v_low": 1 + up * 0.9, "v_high": 1 + up * 1.1}, index=idx)
    df = pd.DataFrame({"z_momentum": 0.0, "mcap_rank": np.arange(1, n + 1), "np_growth": 0.1, "quality_pct": 0.8,
                       "z_quality": np.linspace(1, 0, n), "industry": [f"ind{i}" for i in range(n)], "country": "United States"},
                      index=idx)
    monkeypatch.setitem(shadow.MAP, "cn", True)
    monkeypatch.setitem(shadow.BUY, "cn", "improving")
    b = shadow.buckets(v, df, "cn")
    assert set(b.index[b["bucket"] == "buy"]) == {"s0", "s2", "s4"}  # cheap and improving only
    assert not ((b["bucket"] == "buy") & (v["trend"] == -1)).any()
    sells = b.index[b["bucket"] == "sell"]
    assert len(sells) and (v.loc[sells, "trend"] == -1).all()  # expensive and improving: never a sell
    assert (b.loc[b["bucket"] == "hold"].index.isin(v.index[(v["trend"] == 1) & (v["upside"] < 0)])).any()
