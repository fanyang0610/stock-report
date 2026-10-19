"""Valuation v3 (Phase 13): the base-rate panel on saved samples, the implied-duration solver and the
residual-income / value-driver formulas on hand-checked cases."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stockreport import baserates as br, v3
from stockreport.fetch import frames

DATA = Path(__file__).parent / "data"


def stock(**kw) -> pd.DataFrame:
    base = dict(e0=1.0, book=10.0, e1=np.nan, e2=np.nan, e3=np.nan, t0=0, g=0.0, light=False)
    return pd.DataFrame([base | kw])


FLAT = np.stack([np.zeros(br.H), np.ones(br.H)])[None]  # ROE path: stays where it started (A = 0, B = 1)


def test_residual_income_constant_roe():
    # book 10, ROE 15% held forever (long-run ROE 15%), no growth, r = 10%: 10 + (0.15 - 0.10) * 10 / 0.10 = 15
    x = stock(e0=1.5, book=10.0, g=0.0)
    v = v3.paths(x, FLAT, 0.10, np.array([[0, 5, 30]]), roe_long=0.15, g_long=0.0, fade=5)
    assert v == pytest.approx(15.0, rel=1e-9)


def test_value_driver_as_residual_income():
    # book-light: capital = earnings / 40% = 10; next year's earnings 4 × 1.05 = 4.2 on it (RONIC 42%), held
    # forever, growth g = g_long = 5%, r = 10%. The value-driver formula E1 × (1 − g / RONIC) / (r − g):
    # 4.2 × (1 − 0.05 / 0.42) / 0.05 = 74
    x = stock(e0=4.0, book=4.0 / 0.4, g=0.05, light=True)
    v = v3.paths(x, FLAT, 0.10, np.array([[0, 7, 30]]), roe_long=0.42, g_long=0.05, fade=5)
    assert v == pytest.approx(4.2 * (1 - 0.05 / 0.42) / 0.05, rel=1e-9)


def test_book_light_inputs():
    df = pd.DataFrame({"eps_ttm": [5.0, 2.0, 1.0], "bps": [-3.0, 2.0, 10.0], "price": [50.0] * 3, "analysts": [0] * 3,
                       "rev_growth": [0.05] * 3, "eps_e1": np.nan, "eps_e2": np.nan, "eps_e3": np.nan},
                      index=["buyback", "high_roe", "normal"])
    h = pd.DataFrame({"n_years": [8] * 3, "rev_cagr_5y": [0.05] * 3, "roe_5y": [np.nan, 0.9, 0.1],
                      "loss_5y": [0, 0, 0]}, index=df.index)
    x = v3.inputs(df, h, "us")
    assert x["light"].tolist() == [True, True, False]
    assert x["book"].tolist() == pytest.approx([5.0 / 0.4, 2.0 / 0.4, 10.0])  # the capital earning 40%
    h.loc["buyback", "loss_5y"] = 2  # negative book after losses: distress, no value
    assert not v3.inputs(df, h, "us").at["buyback", "ok"]


def test_consensus_years_then_held_roe():
    # analysts' EPS 1.1, 1.2, 1.3 on book 10 growing at min(g, ROE): D = 3, then ROE flat (year 3's) and no fade
    x = stock(e0=1.0, book=10.0, e1=1.1, e2=1.2, e3=1.3, t0=3, g=0.05)
    r, b = 0.10, [10.0]
    for e in (1.1, 1.2):
        b.append(b[-1] * (1 + min(0.05, e / b[-1])))
    roe3 = 1.3 / b[2]
    by_hand = 10.0 + sum((e - r * bk) / 1.1 ** (t + 1) for t, (e, bk) in enumerate(zip((1.1, 1.2, 1.3), b)))
    b3 = b[2] * 1.05
    by_hand += (roe3 - r) * b3 / (r - 0.05) / 1.1 ** 3  # ROE held, book growing at 5% forever
    v = v3.paths(x, FLAT, r, np.array([[3]]), roe_long=roe3, g_long=0.05, fade=5)
    assert v[0, 0] == pytest.approx(by_hand, rel=1e-9)


def test_implied_duration_solver():
    grid = np.arange(br.DMAX + 1)
    V = np.vstack([100 + 10 * grid, 100 + 10 * grid, 100 + 10 * grid, 500 - 5 * grid])  # rising x3, falling
    S = np.vstack([np.clip(1 - grid / 20, 0, 1)] * 4)  # half the similar companies kept up 10 years
    out = v3.implied(V, np.array([175.0, 90.0, 500.0, 420.0]), S, np.zeros(4, int))
    assert out.loc[0, "d_implied"] == pytest.approx(7.5)  # 100 + 10 × 7.5 = 175
    assert out.loc[0, "implied_share"] == pytest.approx(1 - 7.5 / 20)
    assert out.loc[0, "implied_label"] == ""
    assert out.loc[1, "implied_side"] == "below" and out.loc[1, "implied_label"] == "价格隐含过低"
    assert out.loc[2, "implied_side"] == "above" and out.loc[2, "implied_label"] == "价格隐含过高"
    assert out.loc[3, "d_implied"] == pytest.approx(16) and not out.loc[3, "rising"]  # 500 − 5 × 16 = 420
    assert out.loc[3, "implied_label"] == ""  # 20% of similar companies kept that path: not rare either way


def test_quantile_durations():
    S = np.clip(1 - np.arange(br.DMAX + 1) / 20, 0, 1)[None]
    assert v3.quantile_durations(S)[0] == pytest.approx([5, 10, 15])


def test_kaplan_meier_counts_companies_while_they_report():
    # three starts; profit over the start's for years 1..H. A keeps up 10% for 2 years then falls behind; B keeps
    # up and stops reporting after year 2 (taken over); C falls behind in year 1.
    ratio = np.full((3, br.H), np.nan)
    ratio[0, :3] = [1.1, 1.25, 0.8]
    ratio[1, :2] = [1.1, 1.25]
    ratio[2, :2] = [0.5, 0.6]
    cum = np.cumsum(ratio, axis=1)
    s, risk = br.km(cum, br.track(0.10, tol=0.0))
    assert risk[:3].tolist() == [3, 2, 1]  # B leaves after year 2 without counting as a failure
    assert s[1] == pytest.approx(2 / 3) and s[2] == pytest.approx(2 / 3) and s[3] == pytest.approx(0)


def test_base_rate_panel_sample():
    p = pd.read_csv(DATA / "cn_panel_sample.csv", dtype={"code": str, "avail": str})
    st = br.starts(p, "2026-10-19", "cn")
    assert set(st["sector"]) == {"银行", "食品饮料"}
    assert len(st) == ((p["earn"] > 0) & (p["rev"] > 0) & (p["year"] > p["year"].min())).sum()  # profitable years
    early = br.starts(p, "2016-06-30", "cn")  # only what was public then: no outcome after FY2015
    assert early["year"].max() == 2015 and early.loc[early["year"] == 2015, "e1"].isna().all()
    want = pd.DataFrame({"sector": ["银行", "食品饮料"], "gb": [1, 1], "qb": [1, 3], "sb": [2, 2]}, index=["bank", "spirit"])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(br, "MIN_STARTS", 30)
        S, path, cells = br.survival(st, want, pd.Series([0.05, 0.05], index=want.index), 0.1)
    assert (np.diff(S, axis=1) <= 1e-12).all() and (S[:, 0] == 1).all()
    assert (cells["level"] <= 2).all()  # cells with the sector (the sample has 2 sectors, under 30 starts in some bands)
    A, B = path[0]
    assert ((B >= 0) & (B <= 1)).all() and np.isfinite(A).all()


def test_roe_path_drift_and_persistence():
    # every start's ROE falls 1 point a year and keeps its distance from the cell's mean
    q0 = np.linspace(0.05, 0.25, 60)
    q = np.column_stack([q0 - 0.01 * k for k in range(br.H + 1)])
    A, B = br.roe_path(q)
    assert B == pytest.approx(np.ones(br.H))
    assert (A + B * 0.15) == pytest.approx(0.15 - 0.01 * np.arange(1, br.H + 1))


def test_frames_year(monkeypatch):
    sample = json.loads((DATA / "us_frames_cy2019_sample.json").read_text())

    class Fake:
        def get(self, url, ok=(200,)):
            name = url.split("/")[-3] + ("Q4I" if "Q4I" in url else "")
            return type("R", (), {"status_code": 200 if name in sample else 404,
                                  "json": lambda self: sample.get(name, {})})()
    df = frames.frame_year(Fake(), 2019).set_index("cik")
    assert df.at[320193, "revenue"] == 260174000000  # Apple FY2019 (Sept), the larger of its revenue concepts
    assert df.at[320193, "ni"] == 55256000000
    assert df["equity"].notna().all()
