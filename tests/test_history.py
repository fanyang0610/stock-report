"""History tables (Phase 7): SEC and Yahoo annual results, Yahoo monthly prices, weekly snapshots."""

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stockreport import fetch
from stockreport.fetch import sec, yahoo

SAMPLES = Path(__file__).parent / "data"
load = lambda name: json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def test_sec_annual_from_10k():
    rows = {r["fy_end"]: r for r in sec.parse_annual("AAPL", load("us_companyfacts_aapl_sample.json"))}
    fy = rows["2025-09-27"]
    assert (fy["source"], fy["taxonomy"], fy["currency"], fy["filed"]) == ("SEC", "us-gaap", "USD", "2025-10-31")
    assert (fy["ni"], fy["equity"], fy["revenue"], fy["gp"]) == (112010000000, 73733000000, 416161000000, 195201000000)
    assert rows["2024-09-28"]["ni"] == 93736000000  # the prior year, from the 10-K comparatives


def test_sec_annual_from_20f_in_ifrs_and_home_currency():
    # TSM files 20-F in ifrs-full, in TWD, plus USD convenience figures for the same years: TWD wins;
    # its 6-K half-year figures are not annual.
    rows = {r["fy_end"]: r for r in sec.parse_annual("TSM", load("us_companyfacts_tsm_sample.json"))}
    assert sorted(rows) == ["2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31"]
    fy = rows["2024-12-31"]
    assert (fy["taxonomy"], fy["currency"]) == ("ifrs-full", "TWD")
    assert fy["ni"] == 1158380200000 and fy["equity"] > fy["ni"] and fy["capex"] > 0
    assert fy["shares"] == pytest.approx(25.93e9, rel=1e-3)  # cover-page count after the year end
    assert sec.parse_annual("X", {"cik": 1}) == []


def test_yahoo_annual_rows_are_positive_cash_outflows():
    rows = yahoo.parse_annual("SAP", load("us_yahoo_annual_sap_sample.json"))
    assert [r["fy_end"] for r in rows] == ["2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"]
    last = rows[-1]
    assert (last["source"], last["currency"], last["ni"], last["equity"]) == ("Yahoo", "EUR", 7.161e9, 4.4586e10)
    assert last["capex"] == 7.39e8 and last["div"] == 2.743e9  # Yahoo reports both negative


def test_monthly_closes_as_traded_with_total_returns():
    # NVDA: 4:1 split on 2021-07-20 and 10:1 on 2024-06-10; the sample ends in the unfinished October 2026.
    m, splits = yahoo.parse_monthly("NVDA", load("us_chart_monthly_nvda_sample.json"), now=1792180800)
    close = m.set_index("month")["close"]
    assert splits["ratio"].tolist() == [4.0, 10.0]
    assert close["2021-06"] == pytest.approx(800.10, abs=0.05) and close["2021-07"] == pytest.approx(194.99, abs=0.01)
    assert close["2024-05"] == pytest.approx(1096.33, abs=0.05) and close["2024-06"] == pytest.approx(123.54, abs=0.01)
    assert close.index[0] == "2015-11" and close.index[-1] == "2026-09"  # whole months only, no repeats
    ret = m.set_index("month")["ret"]
    assert ret["2021-07"] == pytest.approx(-0.025, abs=0.001)  # through the split, not -75%
    assert pd.isna(ret["2015-11"])


def test_consensus_snapshot_once_a_week(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "HISTORY", tmp_path)
    src = tmp_path / "cons.csv.gz"
    pd.DataFrame({"code": ["600519"], "eps_e1": [67.2]}).to_csv(src, index=False)
    fetch.snapshot(src, "cn", date(2026, 10, 18))
    pd.DataFrame({"code": ["600519"], "eps_e1": [66.0]}).to_csv(src, index=False)
    fetch.snapshot(src, "cn", date(2026, 10, 19))  # same week: skipped
    dest = tmp_path / "cn_consensus.csv.gz"
    week_ago = date(2026, 10, 18).toordinal() - date(1970, 1, 1).toordinal()
    os.utime(dest, (week_ago * 86400, week_ago * 86400))
    fetch.snapshot(src, "cn", date(2026, 10, 25))
    df = pd.read_csv(dest, dtype={"code": str})
    assert df[["snapshot", "eps_e1"]].values.tolist() == [["2026-10-18", 67.2], ["2026-10-25", 66.0]]


def test_upsert_each_writes_the_yearly_rows(tmp_path):
    table, history = tmp_path / "facts.csv.gz", tmp_path / "annual.csv.gz"
    fn = lambda http, code: ({"code": code, "annual_years": 1}, [{"code": code, "fy_end": "2025-12-31", "ni": 1.0}])
    fetch.upsert_each(table, lambda: None, fn, ["A", "B"], date(2026, 10, 18), 1, "test", history=history)
    years = pd.read_csv(history)
    assert years["code"].tolist() == ["A", "B"] and (years["fetched"] == "2026-10-18").all()
    assert fetch.stale(history, ["A", "B", "C"], date(2026, 10, 18), days=90) == ["C"]


def test_history_is_point_in_time(tmp_path, monkeypatch):
    """The backtest runs v2 on past days: a report filed after `today` must not be used (Phase 9)."""
    from stockreport import history
    rows = [{"code": "X", "fy_end": f"{y}-12-31", "filed": f"{y + 1}-02-20", "currency": "USD", "ni": 10.0 * y,
             "equity": 100.0, "shares": 10.0} for y in (2020, 2021, 2022)]
    rows.append({"code": "Y", "fy_end": "2022-12-31", "filed": None, "currency": "USD", "ni": 1.0, "equity": 5.0, "shares": 1.0})
    pd.DataFrame(rows).to_csv(tmp_path / "us_annual.csv.gz", index=False, compression="gzip")
    monkeypatch.setattr(history, "HISTORY", tmp_path)
    assert history.us_annual(date(2022, 6, 30))["fy_end"].tolist() == ["2020-12-31", "2021-12-31"]
    assert history.us_annual(date(2023, 3, 1))["fy_end"].tolist() == ["2020-12-31", "2021-12-31", "2022-12-31"]
    # no filing date: public 90 days after the year end
    assert history.us_annual(date(2023, 3, 31))["code"].tolist().count("Y") == 1
    assert history.us_annual(date(2023, 3, 30))["code"].tolist().count("Y") == 0

