import json
from datetime import date
from pathlib import Path

import pytest

from stockreport.fetch import fred, nasdaq, sec, yahoo

SAMPLES = Path(__file__).parent / "data"
load = lambda name: json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def test_screener_keeps_ordinary_shares_and_adrs():
    # Real rows, 2026-10-17: preferred depositary shares (GOOGM), notes and a SPAC go; ADRs of
    # preferred shares (ITUB), BNS ("Pfd 3 Ordinary Shares") and MLP common units (MPLX) stay.
    df = nasdaq.parse_screener(load("us_screener_sample.json")).set_index("code")
    kept = set(df.index[nasdaq.ordinary(df)])
    assert {"AAPL", "BRK.B", "ITUB", "BNS", "MPLX", "T", "TSM"} <= kept
    assert "GOOGM" not in kept and "ABXL" not in kept and "AACI" not in kept
    assert df.loc["AAPL", "name"] == "Apple Inc"
    assert df.loc["BRK.B", "last"] == pytest.approx(525.68)


def test_forecast_takes_the_first_three_fiscal_years():
    row = nasdaq.parse_forecast("AAPL", load("us_forecast_sample.json"))
    assert (row["e1_year"], row["analysts"]) == ("2026-09", 10)  # analysts behind next year's estimate
    assert [row["eps_e1"], row["eps_e2"], row["eps_e3"]] == [8.75, 9.59, 10.96]
    assert nasdaq.parse_forecast("X", {"data": None}) is None


def test_chart_returns_chain_through_split_and_dividend():
    # NVDA, 2024-06-03..13: 10-for-1 split on 06-10 and a $0.01 dividend on 06-11.
    prices, divs = yahoo.parse_chart("NVDA", load("us_chart_nvda_sample.json"), now=0)
    p = prices.set_index("date")
    assert "2024-06-03" not in p.index  # first day has no return
    split_day = p.loc["2024-06-10"]
    assert split_day["prev_close"] == pytest.approx(p.loc["2024-06-07", "close"], rel=1e-4)  # no -90% jump
    ex_day = p.loc["2024-06-11"]
    assert ex_day["prev_close"] == pytest.approx(p.loc["2024-06-10", "close"] - 0.01, abs=0.005)
    assert divs.to_dict("records") == [{"code": "NVDA", "ex_date": "2024-06-11", "dps": 0.01}]


def test_chart_drops_the_bar_of_an_open_session():
    payload = load("us_chart_nvda_sample.json")
    res = payload["chart"]["result"][0]
    last = res["timestamp"][-1]
    res["meta"]["currentTradingPeriod"] = {"regular": {"start": last - 3600, "end": last + 3600}}
    prices, _ = yahoo.parse_chart("NVDA", payload, now=last)
    assert prices["date"].max() == "2024-06-12"


def test_fred_skips_holidays():
    df = fred.parse_observations(load("us_fred_sample.json"), "us")
    assert "2026-10-12" not in set(df["date"])  # Columbus Day, value "."
    assert df.iloc[0].to_dict() == {"date": "2026-10-15", "market": "us", "y10": 5.1}


def test_companyfacts_ttm_is_ytd_plus_last_year_minus_prior_ytd():
    # Cut from AAPL's real companyfacts (2026-10-17): the concepts used, 10-Q/10-K filings since 2024-07.
    row = sec.parse_facts("AAPL", load("us_companyfacts_aapl_sample.json"), date(2026, 10, 17))
    assert (row["gap"], row["period"], row["notice_date"]) == (False, "2026-06-27", "2026-07-31")
    assert row["revenue_ttm"] == 364_357e6 + 416_161e6 - 313_695e6  # 9M FY26 + FY25 - 9M FY25
    assert row["np_ttm"] == pytest.approx(128.93e9)
    assert row["gp_ttm"] / row["revenue_ttm"] == pytest.approx(0.4865, abs=1e-4)
    assert (row["equity"], row["liabilities"], row["assets"]) == (107_520e6, 275_746e6, 383_266e6)
    assert row["rev_yoy"] == pytest.approx(0.1424, abs=1e-4)


def test_companyfacts_gaps():
    assert sec.parse_facts("TSM", {"cik": 1046179, "facts": {"ifrs-full": {}}}, date(2026, 10, 17))["gap"]
    stale = sec.parse_facts("AAPL", load("us_companyfacts_aapl_sample.json"), date(2027, 6, 1))
    assert stale["gap"]  # last 10-Q period more than 200 days old


def test_filing_titles_skip_routine_forms():
    payload = load("us_submissions_pfe_sample.json")  # real PFE list: Form 4s, 13G, 13F, N-PX, a 10-Q and an 8-K
    assert sec.parse_titles(payload, date(2026, 10, 17), 60, 10) == []
    assert sec.parse_titles(payload, date(2026, 10, 17), 90, 10) == [
        "2026-08-04 10-Q: Quarterly report", "2026-08-04 8-K: Results of operations"]


def test_bank_revenue_is_net_interest_plus_noninterest_income():
    # BNY (real facts, 2026-10-17) tags no revenue total.
    row = sec.parse_facts("BNY", load("us_companyfacts_bny_sample.json"), date(2026, 10, 17))
    assert not row["gap"]
    assert row["revenue_ttm"] == row["nii_ttm"] + row["nonint_ttm"] == pytest.approx(21.367e9)


def test_yahoo_fundamentals_for_sec_gaps():
    # Real Yahoo fundamentals-timeseries (2026-10-17), one company per growth path.
    s, day = load("us_yahoo_timeseries_sample.json"), date(2026, 10, 17)
    asml = yahoo.parse_timeseries("ASML", s["ASML"], day)  # TTM a year earlier is in the series
    assert (asml["yahoo"], asml["period"], asml["currency"]) == ("ok", "2026-06-30", "EUR")
    assert asml["revenue_ttm"] == pytest.approx(35.3275e9) and asml["rev_yoy"] == pytest.approx(35.3275 / 32.1614 - 1, abs=1e-3)
    bhp = yahoo.parse_timeseries("BHP", s["BHP"], day)  # semiannual: last fiscal year vs the one before
    assert bhp["rev_yoy"] == pytest.approx(58.76 / 51.262 - 1, abs=1e-3)
    ry = yahoo.parse_timeseries("RY", s["RY"], day)  # latest quarter vs the same quarter a year earlier
    assert ry["np_yoy"] == pytest.approx(5.877 / 5.29 - 1, abs=2e-3)
    assert yahoo.parse_timeseries("RY", s["RY"], date(2027, 6, 1))["yahoo"] == "no recent TTM"


def test_timeseries_net_income_and_shares_for_the_cross_checks():
    row = yahoo.parse_timeseries("SOFI", load("us_yahoo_timeseries_sofi_sample.json"), date(2026, 10, 19))  # real reply
    assert row["revenue_ttm"] == pytest.approx(4305695000) and row["ni_ttm"] == pytest.approx(636264000)
    assert row["shares"] == pytest.approx(1290312404) and row["period"] == "2026-06-30"
