"""The scorecard's cohorts (track.py): the first close, the month-end marks, an unresolved name, the neutral basket's
weights, and marks kept as observed once the price file has moved on."""

from datetime import date

import pandas as pd
import pytest

from stockreport import track


def prices(suspend: tuple[str, str] = ("CCC", "2026-11-30")) -> pd.DataFrame:
    """Weekdays 2026-11-02..2027-01-08: AAA +1% a day, BBB flat, SPY +0.5% a day, CCC +2% a day but with no trade on
    `suspend` (a row with volume 0 at the last close, as a suspended name shows); AAA pays a dividend on 11-17 (close
    drops, prev_close is lowered by it), so its return that day stays +1%."""
    days = [d.date().isoformat() for d in pd.bdate_range("2026-11-02", "2027-01-08")]
    rows = []
    for code, step in (("AAA", 1.01), ("BBB", 1.0), ("SPY", 1.005), ("CCC", 1.02)):
        close = 100.0
        for d in days:
            prev, div = close, 1.0 if code == "AAA" and d == "2026-11-17" else 0.0
            off = (code, d) == suspend
            close = close if off else close * step - div
            rows.append({"date": d, "code": code, "close": close, "prev_close": prev - div / step,
                         "volume": 0 if off else 1000})
    return pd.DataFrame(rows)


DAYS = pd.Index(sorted(prices()["date"].unique()))


def test_first_close():
    # Saturday's report priced at Friday's close: Monday's close.
    assert track.start(DAYS, "2026-11-07", "2026-11-06") == "2026-11-09"
    # A Monday report is the day's last build (an evening review may change it after Monday's close): Tuesday's close,
    # whether it was priced at Friday's close or at Monday's.
    assert track.start(DAYS, "2026-11-09", "2026-11-06") == "2026-11-10"
    assert track.start(DAYS, "2026-11-09", "2026-11-09") == "2026-11-10"
    assert track.start(DAYS, "2027-02-01", "2027-01-29") is None  # not in yet


def test_marks_due():
    # Month ends after the first close, each due once a later close is in; the last day in the file isn't due.
    assert track.due(DAYS, "2026-11-09") == ["2026-11-30", "2026-12-31"]
    assert track.due(DAYS[DAYS <= "2026-11-30"], "2026-11-09") == []
    # The 12-month close: the last trading day on or before the anniversary, due once a later close is in.
    year = pd.Index([d.date().isoformat() for d in pd.bdate_range("2026-11-02", "2027-11-12")])
    marks = track.due(year, "2026-11-09")
    assert marks[-2:] == ["2027-10-29", "2027-11-09"] and len(marks) == 13
    assert track.due(year[year <= "2027-11-09"], "2026-11-09")[-1] == "2027-10-29"


def test_first_reports():
    picks = pd.DataFrame({"date": ["2026-11-02", "2026-11-07", "2026-11-08", "2026-12-01", "2026-12-01"],
                          "market": ["us", "us", "us", "us", "cn"], "bucket": ["buy", "buy", "sell", "hold", "removed"]})
    got = track.first_reports(picks).set_index(["market", "month"])["date"]
    assert got.to_dict() == {("us", "2026-11"): "2026-11-07", ("us", "2026-12"): "2026-12-01"}


def cohort() -> pd.DataFrame:
    return pd.DataFrame({"market": "us", "cohort": "2026-11-07", "priced": "2026-11-06",
                         "group": ["buy", "buy", "sell", "fund"], "code": ["AAA", "CCC", "BBB", "SPY"],
                         "name": "", "weight": [0.5, 0.5, 1.0, 1.0]})


def test_month_end_values_and_an_unresolved_name():
    p = prices()
    rows = pd.DataFrame(track.marks_for(cohort(), p, DAYS, "2026-11-09", ["2026-11-30", "2026-12-31"]))
    rows = rows.set_index(["mark", "group"])
    # From Monday 11-09's close to Monday 11-30's: 15 trading days, the dividend day included.
    nov = rows.loc[("2026-11-30", "buy")]
    assert nov["value"] == pytest.approx(1.01 ** 15)  # CCC didn't trade on 11-30: left out, not counted as flat
    assert (nov["names"], nov["unresolved"]) == (1, 1)
    assert nov["missing"] == f"CCC={1.02 ** 14:.4f}"  # kept for the record: its growth to its last close
    assert rows.loc[("2026-11-30", "fund"), "value"] == pytest.approx(1.005 ** 15)
    assert rows.loc[("2026-11-30", "sell"), "value"] == pytest.approx(1.0)
    assert nov["start"] == "2026-11-09" and nov["months"] == 0.7
    # 12-31: 38 trading days; CCC traded again, its return running from its last close (37 up days).
    dec = rows.loc[("2026-12-31", "buy")]
    assert dec["value"] == pytest.approx((1.01 ** 38 + 1.02 ** 37) / 2)
    assert (dec["names"], dec["unresolved"]) == (2, 0)


def test_half_day_volume_zero_still_traded():
    """Yahoo gives every HK row volume 0 on a half day (2025-12-31): a moved price is a trade; a suspended name shows
    the last close with volume 0."""
    p = pd.DataFrame({"date": "2026-12-31", "code": ["A", "B", "C"], "close": [10.5, 20.0, 30.0],
                      "prev_close": [10.0, 20.0, 29.0], "volume": [0, 0, 500]})
    assert track.traded(p, "2026-12-31") == {"A", "C"}


def test_basket_weights():
    """US: 20 places by free-float share (technology 60%, finance 30%, utilities 10%) give 12, 6 and 2; each sector's
    money spread equally over its names that can be bought; the partnership can't be bought but counts in its sector's
    value."""
    sectors = ["Technology"] * 20 + ["Finance"] * 10 + ["Utilities"] * 6
    value = [3.0] * 20 + [3.0] * 10 + [1.8] * 5 + [1.0]
    snap = pd.DataFrame({"name": [f"N{i}" for i in range(35)] + ["Pipe Partners L.P."], "sector": sectors,
                         "float_value": value, "financial": [False] * 20 + [True] * 10 + [False] * 6,
                         "distress": float("nan"), "sta": float("nan")}, index=[f"C{i}" for i in range(36)])
    w = track.basket(snap, "us")
    assert "C35" not in w and w.sum() == pytest.approx(1.0)
    assert w["C0"] == pytest.approx(12 / 20 / 20) and w["C20"] == pytest.approx(6 / 20 / 10)
    assert w["C30"] == pytest.approx(2 / 20 / 5)


def test_update_records_once_and_keeps_marks(tmp_path, monkeypatch):
    for name, path in (("DATA", tmp_path), ("PICKS_LOG", tmp_path / "picks.csv"),
                       ("COHORTS", tmp_path / "cohorts.csv.gz"), ("MARKS", tmp_path / "marks.csv")):
        monkeypatch.setattr(track, name, path)
    pd.DataFrame({"date": "2026-11-07", "market": "us", "bucket": ["buy", "buy", "sell"], "ticker": ["AAA", "CCC", "BBB"],
                  "name": ["A", "C", "B"], "price": 1.0, "price_date": "2026-11-06", "score": 0.5, "rank": 1}
                 ).to_csv(tmp_path / "picks.csv", index=False)
    p = prices()
    # On the report's own day nothing is recorded: its last build may still change the lists.
    track.update(date(2026, 11, 7), {"us": lambda: p})
    assert track.load_cohorts().empty
    # November's mark has an unresolved name (CCC): with 4 later closes it waits (a failed fetch may have left the gap),
    # with 5 or more it is taken; December's, all priced, is taken once a later close is in.
    track.update(date(2027, 1, 2), {"us": lambda: p[p["date"] <= "2026-12-04"]})
    assert track.load_marks().empty
    track.update(date(2027, 1, 9), {"us": lambda: p})  # no snapshot of the day: no basket, logged
    marks = track.load_marks()
    c = track.load_cohorts()
    assert sorted(c["group"]) == ["buy", "buy", "fund", "sell"] and c.loc[c["group"] == "fund", "code"].item() == "SPY"
    assert sorted(marks["mark"].unique()) == ["2026-11-30", "2026-12-31"] and len(marks) == 6
    # The price file rolls on and November is gone from it: the November marks stay as observed, nothing is redone,
    # and the first close stays the one the marks recorded.
    later = p[p["date"] > "2026-12-15"]
    again = track.update(date(2027, 1, 10), {"us": lambda: later})
    assert again.equals(marks) and track.first_close(again, DAYS[DAYS > "2026-12-15"], "us", c) == "2026-11-09"
    s, gone = track.standing(again, "us")
    assert s["mark"].item() == "2026-12-31" and s["buy"].item() == pytest.approx((1.01 ** 38 + 1.02 ** 37) / 2 - 1)
    assert gone == 0
    assert track.tracked("us", date(2027, 1, 10), ["MSFT"]) == ["MSFT", "AAA", "BBB", "CCC", "SPY"]
