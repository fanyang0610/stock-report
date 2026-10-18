from pathlib import Path

import pandas as pd
import pytest

from stockreport.config import CONFIG
from stockreport.pick import one_off, pick
from stockreport.score import COMPONENTS, explain, neutral_z, score
from stockreport.value import value

SAMPLE = Path(__file__).parent / "data" / "cn_sample.csv"
R = 0.0765


@pytest.fixture(scope="module")
def scored() -> pd.DataFrame:
    return score(value(pd.read_csv(SAMPLE, dtype={"code": str}).set_index("code"), R))


def test_neutral_z_removes_group_means():
    x = pd.Series([1.0, 2.0, 3.0, 10.0, 11.0, 12.0])
    groups = pd.Series(["a", "a", "a", "b", "b", "b"])
    z = neutral_z(x, groups)
    assert z.groupby(groups).mean().abs().max() == pytest.approx(0)
    assert z.iloc[0] == pytest.approx(z.iloc[3])  # same position within its group, same score


def test_composite_is_the_weighted_sum(scored):
    w = CONFIG["score"]["weights"]
    assert sum(w.values()) == pytest.approx(1.0)
    expected = sum(w[c] * scored[f"z_{c}"].fillna(0) for c in COMPONENTS)
    assert scored["composite"].to_numpy() == pytest.approx(expected.to_numpy())
    assert scored["z_value"].mean() == pytest.approx(0, abs=1e-9)


def test_buckets_follow_the_rules(scored):
    c = CONFIG["buckets"]
    picks = pick(scored)
    picks = picks[picks["role"] != "excluded"]
    main = picks[picks["role"] == "pick"]
    assert main.groupby("bucket").size().to_dict() == {"buy": 5, "hold": 5, "sell": 5}
    assert not picks["code"].duplicated().any()  # one bucket per stock, runners-up included
    assert (picks.groupby(["bucket", "industry"]).size() <= c["max_per_group"]).all()
    strict = main[main["tier"] == 1]
    buy, hold, sell = (strict[strict["bucket"] == b] for b in ("buy", "hold", "sell"))
    assert (buy["upside"] >= c["buy_min_upside"]).all() and (buy["z_momentum"] >= c["buy_min_momentum_z"]).all()
    assert hold["upside"].between(*c["hold_upside"]).all()
    assert (hold["quality_pct"] >= 1 - c["hold_quality_top"]).all()
    assert (sell["upside"] <= c["sell_max_upside"]).all() and (sell["mcap_rank"] <= c["sell_largest_n"]).all()
    assert (main.loc[main["tier"] > 1, "conviction"] == "低信心").all()
    assert buy["composite"].is_monotonic_decreasing and sell["composite"].is_monotonic_increasing
    assert hold["z_quality"].is_monotonic_decreasing


def test_drivers_point_the_right_way(scored):
    row = scored.iloc[0]
    drivers, risk = explain(row, "buy")
    assert len(drivers.split("；")) == 2 and risk


def test_one_off_checks_apply_at_pick_time(scored):
    # Checks 1-2 run in pick(), not only in the DeepSeek path: in the sample, 寒武纪 (buy) and 中微公司 (hold)
    # grew profit 123% / 300% on cash conversion 0.13 / 0.17. They take no place and are listed as excluded.
    picks = pick(scored).set_index("code")
    checks = one_off(scored)
    spiked = checks.index[checks["c1"].eq(True) | checks["c2"].eq(True)]
    placed = picks[picks["role"].isin(["pick", "runner_up"]) & (picks["bucket"] != "sell")]
    assert not placed.index.isin(spiked).any()
    excluded = picks[picks["role"] == "excluded"]
    assert excluded["bucket"].to_dict() == {"688256": "buy", "688012": "hold"}
    assert excluded.loc["688012", "exclusion"] == "净利润同比 +300%，但经营现金流/净利润只有 0.17，利润缺少现金支撑。"
    assert (picks.loc[picks["role"] == "pick"].groupby("bucket").size() == 5).all()


def test_check_2_and_financials():
    row = {"method": "P/B", "cash_conv": 1.0, "np_ttm": 10.0, "analysts": 5, "eps_ttm": 2.0, "eps_e2": 1.0,
           "np_growth": 2.0, "rev_growth": 0.1}
    bank = row | {"method": "P/B on ROE", "cash_conv": 0.1, "analysts": 0}
    c = one_off(pd.DataFrame([row, bank], index=["A", "BANK"]))
    assert c.loc["A", "c2"] and not c.loc["A", "c1"]  # EPS expected to halve; cash conversion is fine
    assert c.loc["A", "eps_ratio"] == pytest.approx(0.5)
    assert pd.isna(c.loc["BANK", "c1"]) and pd.isna(c.loc["BANK", "c2"])  # banks' investment income is core


def test_quality_spread_is_similar_for_financials_and_the_rest(scored):
    # Financial quality is one metric (ROE), the rest four; each side is standardized before combining.
    spread = scored.groupby("financial")["z_quality"].std()
    assert spread[True] == pytest.approx(spread[False], rel=0.1)
