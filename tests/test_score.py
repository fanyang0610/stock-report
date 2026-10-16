from pathlib import Path

import pandas as pd
import pytest

from stockreport.config import CONFIG
from stockreport.pick import pick
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
