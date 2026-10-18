import numpy as np
import pandas as pd

from stockreport import signal


def panel(n_dates: int = 3, n: int = 40) -> pd.DataFrame:
    rows = []
    for d in range(n_dates):
        for i in range(n):
            rows.append({"date": f"2024-0{d + 1}-30", "code": str(i), "up": i / n, "ret_12m": 0.01 * i, "idx_12m": 0.1,
                         "bucket": "buy" if i >= n - 5 else "sell" if i < 5 else None})
    return signal.add_excess(pd.DataFrame(rows))


def test_rank_ic_perfect_and_reversed():
    df = panel()
    assert np.allclose(signal.rank_ic(df, "up", "ret_12m"), 1.0)
    assert np.allclose(signal.rank_ic(df.assign(up=-df["up"]), "up", "ret_12m"), -1.0)
    assert signal.rank_ic(df.head(20), "up", "ret_12m").empty  # fewer than 30 stocks on the date


def test_bucket_table_against_universe():
    t = signal.bucket_table(panel(), "bucket", "12m")
    # universe average 0.195; buys 0.35..0.39 → +0.175; sells 0..0.04 → -0.175
    assert np.isclose(t.at["buy", "vs_universe"], 0.175)
    assert np.isclose(t.at["sell", "vs_universe"], -0.175)
    assert np.isclose(t.at["buy-sell", "vs_universe"], 0.35)
    assert t.at["buy", "hit"] == 1.0 and t.at["sell", "hit"] == 1.0
    assert np.isclose(t.at["buy", "vs_index"], 0.37 - 0.1)


def test_beta_recovers_the_share_of_the_gap_that_closed():
    rng = np.random.default_rng(0)
    gap = rng.normal(0, 0.5, 400)
    df = pd.DataFrame({"date": np.repeat(["a", "b"], 200), "gap": gap, "ret_12m": np.expm1(0.3 * gap)})
    b = signal.beta(df, "gap", "12m")
    assert np.isclose(b["beta"].iloc[0], 0.3, atol=1e-6)


def test_overlap_adjusted_t():
    s = signal.summarize(pd.Series([0.1, 0.2, 0.1, 0.2] * 6), 12)
    assert s["n"] == 24 and np.isclose(s["mean"], 0.15)
    assert np.isclose(s["t"], 0.15 / (pd.Series([0.1, 0.2, 0.1, 0.2] * 6).std() / np.sqrt(2)))
