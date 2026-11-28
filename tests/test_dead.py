"""Stage 27: the names a survivor-only history leaves out (backtest/dead.py)."""

import pandas as pd
import pytest

from backtest import dead


def months(n):
    return [f"2020-{m:02d}" for m in range(1, n + 1)]


def test_total_return_adds_the_dividend_the_adjustment_carries():
    # raw close 10, 10, 10; a 1.0 dividend in the second month adds 1.0 to every later adjusted close
    raw = pd.Series([10.0, 10.0, 10.0], index=months(3))
    adj = pd.Series([10.0, 11.0, 11.0], index=months(3))
    r = dead.total_return(raw, adj)
    assert r.iloc[1] == pytest.approx(0.10)  # (10 + 1) / 10 - 1: the dividend on a flat price
    assert r.iloc[2] == pytest.approx(0.0)


def test_total_return_takes_a_split_out_and_scales_later_dividends():
    # a 1:5 split in the third month (raw 50 -> 11 on a 10% rise), then a 0.5 dividend in the fourth month on the new shares
    raw = pd.Series([50.0, 50.0, 11.0, 11.0], index=months(4))
    adj = pd.Series([50.0, 50.0, 55.0, 57.5], index=months(4))  # before the split x5 from there on, the dividend x5 too
    r = dead.total_return(raw, adj)
    assert r.iloc[2] == pytest.approx(0.10)  # the split month's return is the adjusted move
    assert r.iloc[3] == pytest.approx(0.5 / 11)  # 0.5 per new share on an 11 close


def test_total_return_reads_the_scale_an_earlier_split_left():
    # the series starts after a 1:5 split: the adjusted closes are 5 x the raw ones; no dividend in these months
    raw = pd.Series([10.0, 10.2, 10.0, 10.3, 10.5], index=months(5))
    adj = raw * 5
    r = dead.total_return(raw, adj)
    assert list(r.iloc[1:].round(4)) == [0.02, round(-0.2 / 10.2, 4), 0.03, round(0.2 / 10.3, 4)]


def test_total_return_keeps_a_collapse_a_collapse():
    raw = pd.Series([10.0, 10.0, 1.0], index=months(3))  # -90%: not a split ratio against an adjusted close that fell too
    adj = pd.Series([10.0, 10.0, 1.0], index=months(3))
    assert dead.total_return(raw, adj).iloc[2] == pytest.approx(-0.9)


def test_us_haircut_puts_the_bankruptcies_back():
    rates = pd.DataFrame({"bankrupt_rate": [0.001, 0.02]}, index=pd.Index([False, True], name="loss"))
    snap = pd.DataFrame({"np_ttm": [1.0, -1.0, 1.0, -1.0], "bps": [1.0] * 4}, index=list("abcd"))
    picks = {"2020-01": pd.Series(0.25, index=list("abcd"))}
    windows = pd.DataFrame({"ret": [0.10]}, index=["2020-01"])
    out = dead.us_haircut(rates, {"2020-01": {"snap": snap}}, picks, windows, -0.30)
    p = 0.5 * 0.02 + 0.5 * 0.001  # half the list loses money
    assert out["2020-01"] == pytest.approx((1 - p) * 0.10 + p * -0.30)
