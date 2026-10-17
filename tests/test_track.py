"""Scorecard math: returns chained from close / prev_close, against the index over the same days."""

import pandas as pd
import pytest

from stockreport import track


def prices() -> pd.DataFrame:
    """Weekdays from 2026-10-01: AAA +1% a day, BBB flat, the index +0.5% a day; AAA pays a dividend on 10-06
    (close drops, prev_close is adjusted), so its return stays +1% that day."""
    days = [d.date().isoformat() for d in pd.bdate_range("2026-10-01", "2026-11-13")]
    rows = []
    for code, step in (("AAA", 1.01), ("BBB", 1.0), ("SPX", 1.005)):
        close = 100.0
        for d in days:
            prev = close
            close = close * step - (1.0 if code == "AAA" and d == "2026-10-06" else 0)
            rows.append({"date": d, "code": code, "close": close,
                         "prev_close": prev - (1.0 / step if code == "AAA" and d == "2026-10-06" else 0)})
    return pd.DataFrame(rows)


def test_returns_by_horizon():
    picks = pd.DataFrame({"ticker": ["AAA", "BBB", "CCC"], "price_date": ["2026-10-02", "2026-10-02", "2026-10-02"]})
    r = track.returns(picks, prices(), "SPX")
    # 1 week after Fri 10-02 is Fri 10-09: 5 trading days.
    assert r.loc[(0, "1w"), "avg"] == pytest.approx(1.01 ** 5 - 1)
    assert r.loc[(0, "1w"), "vs index"] == pytest.approx(1.01 ** 5 - 1.005 ** 5)
    assert r.loc[(1, "1w"), "vs index"] == pytest.approx(-(1.005 ** 5 - 1))
    # 30 days -> Sun 11-01, so the close of Fri 10-30 (20 trading days); 3 months hasn't ended yet.
    assert r.loc[(0, "1m"), "avg"] == pytest.approx(1.01 ** 20 - 1)
    assert pd.isna(r.loc[(0, "3m"), "avg"])
    assert r.loc[(1, "to date"), "avg"] == pytest.approx(0)
    assert r.loc[2].isna().all().all()  # no prices for CCC: not counted


def test_table_counts_and_averages():
    picks = pd.DataFrame({"market": ["us"] * 3, "bucket": ["buy", "buy", "sell"], "ticker": ["AAA", "BBB", "BBB"],
                          "price_date": ["2026-10-02"] * 3})
    t = track.table(picks, {"us": prices})
    assert t.loc[("US", "buy"), ("1w", "n")] == 2
    assert t.loc[("US", "buy"), ("1w", "avg")] == pytest.approx((1.01 ** 5 - 1) / 2)
    assert t.loc[("US", "sell"), ("1m", "vs index")] == pytest.approx(-(1.005 ** 20 - 1))
    assert t.loc[("US", "sell"), ("3m", "n")] == 0
