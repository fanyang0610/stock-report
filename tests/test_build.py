"""A market whose daily prices couldn't be updated isn't built (AGENTS.md rule 4): its newest earlier lists stand."""

from datetime import date

import pytest

from stockreport import __main__ as app
from stockreport import report


def test_a_market_without_todays_prices_keeps_its_last_lists(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "REPORTS", tmp_path)
    monkeypatch.setattr(app, "fetch_market", lambda market, today: ["Yahoo share counts", "prices"])
    monkeypatch.setattr(app, "scored", lambda *a: pytest.fail("scored a market whose prices are a day old"))
    with pytest.raises(RuntimeError, match="daily prices not updated"):
        app.build_market("us", date(2026, 11, 7))
    assert (tmp_path / "2026-11-07" / "fetch_failed.json").exists()  # the report still says what failed
    assert not list(tmp_path.glob("*/us_lists.csv"))
