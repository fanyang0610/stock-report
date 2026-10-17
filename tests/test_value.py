from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stockreport.value import disagree, fit, justified_pb, peer_groups, predict, residual_income, value

SAMPLE = Path(__file__).parent / "data" / "cn_sample.csv"
R = 0.0765  # 1.65% ChinaBond 10y (2026-10-16) + 6% premium


def load_sample() -> pd.DataFrame:
    return pd.read_csv(SAMPLE, dtype={"code": str}).set_index("code")


def test_fit_recovers_known_coefficients():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(50, 2))
    y = 1.0 + 2.0 * x[:, 0] - 0.5 * x[:, 1]
    assert fit(y, x) == pytest.approx([1.0, 2.0, -0.5])
    assert predict(fit(y, x), x) == pytest.approx(y)


def test_justified_pb():
    assert justified_pb(0.12, 0.03, 0.08) == pytest.approx(1.8)


def test_residual_income():
    # ROE equal to r earns nothing above book
    assert residual_income([10.0], [R], R, [0.6], 10)[0] == pytest.approx(10.0)
    # one year: book + (ROE - r) * book / (1 + r)
    assert residual_income([10.0], [0.2], 0.1, [1.0], 1)[0] == pytest.approx(10 + 1 / 1.1)
    # value rises with ROE
    low, high = residual_income([10.0, 10.0], [0.08, 0.20], R, [0.6, 0.6], 10)
    assert high > low > 0


def test_small_groups_are_compared_market_wide():
    df = pd.DataFrame({"industry": ["A"] * 8 + ["B"] * 3 + ["银行Ⅱ"] * 2,
                       "financial": [False] * 11 + [True] * 2})
    groups = peer_groups(df, 8)
    assert list(groups[:8]) == ["A"] * 8
    assert set(groups[8:11]) == {"全市场(合并)"}
    assert set(groups[11:]) == {"金融(合并)"}


def test_fair_value_on_saved_sample():
    df = value(load_sample(), R)
    valued = df[df["fv_mid"].notna()]
    assert len(valued) >= 0.9 * len(df)
    assert (valued["fv_low"] < valued["fv_mid"]).all() and (valued["fv_mid"] < valued["fv_high"]).all()
    assert valued["upside"].to_numpy() == pytest.approx((valued["fv_mid"] / valued["price"] - 1).to_numpy())
    assert (df["g"] <= 0.03 + 1e-12).all()
    assert set(df.loc[df["financial"], "method"].dropna()) == {"P/B+justified"}
    assert set(df.loc[~df["financial"] & (df["np_ttm"] > 0), "method"].dropna()) == {"P/B"}
    assert set(df.loc[~df["financial"] & (df["np_ttm"] <= 0), "method"].dropna()) == {"P/S"}


def test_trailing_lens_is_the_groups_fitted_pb_times_own_book():
    df = value(load_sample(), R)
    group = df[(df["method"] == "P/B") & (df["fit_group"] == df["peer_group"])]["peer_group"].iloc[0]
    members = df[(df["peer_group"] == group) & ~df["financial"] & (df["np_ttm"] > 0)]
    x = members[["roe", "rev_growth"]].to_numpy()
    coef = fit(np.log(members["pb"]), x)
    expected = np.exp(predict(coef, x)) * members["bps"]
    assert members["fv_trailing"].to_numpy() == pytest.approx(expected.to_numpy())


def test_bank_fair_value_blends_justified_and_peer_pb():
    df = value(load_sample(), R)
    banks = df[df["method"] == "P/B+justified"]
    members = banks[banks["fit_group"] == banks["fit_group"].iloc[0]]
    coef = fit(np.log(members["pb"]), members[["roe"]].to_numpy())
    peer = np.exp(predict(coef, members[["roe"]].to_numpy())) * members["bps"]
    just = justified_pb(members["roe"], members["g"], R) * members["bps"]
    assert members["fv_trailing"].to_numpy() == pytest.approx((0.5 * peer + 0.5 * just).to_numpy())
    assert members["fv_forward"].isna().all()  # no forward lens for financials


def test_disagree_needs_opposite_directions_and_a_wide_gap():
    price = pd.Series([100.0, 100.0, 100.0])
    a = pd.Series([200.0, 200.0, 120.0])
    b = pd.Series([50.0, 150.0, 90.0])
    assert list(disagree(a, b, price, 0.5)) == [True, False, False]  # same side / gap only 33%


def test_forward_lens_is_peer_forward_pe_times_next_years_eps():
    df = value(load_sample(), R)
    eligible = (~df["financial"] & (df["analysts"] >= 3) & (df["eps_e2"] > 0)
                & df["fwd_growth"].notna() & (df["fwd_pe"] > 0))
    pooled = df[(df["peer_group"] == "全市场(合并)") & eligible].index  # small industries: fit on all eligible
    coef = fit(np.log(df.loc[eligible, "fwd_pe"]), df.loc[eligible, ["fwd_growth"]].to_numpy())
    expected = np.exp(predict(coef, df.loc[pooled, ["fwd_growth"]].to_numpy())) * df.loc[pooled, "eps_e2"]
    assert len(pooled) and df.loc[pooled, "fv_forward"].to_numpy() == pytest.approx(expected.to_numpy())


def test_fair_value_blends_both_lenses_and_its_range_covers_them():
    df = value(load_sample(), R)
    both = df["fv_trailing"].notna() & df["fv_forward"].notna()
    blended = 0.5 * df["fv_trailing"] + 0.5 * df["fv_forward"]
    assert df.loc[both, "fv_mid"].to_numpy() == pytest.approx(blended[both].to_numpy())
    only = df["fv_trailing"].notna() & df["fv_forward"].isna()
    assert df.loc[only, "fv_mid"].to_numpy() == pytest.approx(df.loc[only, "fv_trailing"].to_numpy())
    lo = df.loc[both, ["fv_trailing", "fv_forward"]].min(axis=1)
    hi = df.loc[both, ["fv_trailing", "fv_forward"]].max(axis=1)
    assert (df.loc[both, "fv_low"] <= lo + 1e-9).all() and (df.loc[both, "fv_high"] >= hi - 1e-9).all()


def test_negative_book_is_valued_on_the_forward_lens_alone():
    df = load_sample()
    code = df[~df["financial"] & (df["np_ttm"] > 0) & (df["analysts"] >= 3) & (df["eps_e2"] > 0)
              & df["fwd_growth"].notna()].index[0]
    df.loc[code, ["bps", "pb", "roe"]] = [-5.0, np.nan, np.nan]  # buybacks took book value below zero
    row = value(df, R).loc[code]
    assert np.isnan(row["fv_trailing"]) and row["method"] == "fwd P/E"
    assert row["fv_mid"] == pytest.approx(row["fv_forward"])
    assert row["fv_low"] < row["fv_mid"] < row["fv_high"]
