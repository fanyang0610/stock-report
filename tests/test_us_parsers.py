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


def test_bank_revenue_is_net_interest_plus_noninterest_income():
    # BNY (real facts, 2026-10-17) tags no revenue total.
    row = sec.parse_facts("BNY", load("us_companyfacts_bny_sample.json"), date(2026, 10, 17))
    assert not row["gap"]
    assert row["revenue_ttm"] == row["nii_ttm"] + row["nonint_ttm"] == pytest.approx(21.367e9)


# Real facts (2026-10-19) behind Phase 12's SEC-vs-Yahoo gaps, cut to the TTM to 2026-06-30 (H1 2026 + FY2025 - H1 2025).
FIXES = load("us_companyfacts_fixes_sample.json")
facts = lambda code: sec.parse_facts(code, FIXES[code], date(2026, 10, 19))


def test_revenue_is_the_concept_the_income_statement_implies_else_the_largest():
    # No gross profit or operating income: the largest. SoFi's and M&T's ASC 606 revenue is only their fee
    # revenue; Camden's is the 1% that isn't rent.
    assert facts("SOFI")["revenue_ttm"] == 2_319_044e3 + 3_613_354e3 - 1_626_703e3  # RevenuesNetOfInterestExpense
    assert facts("MTB")["revenue_ttm"] == (3_544 + 6_948 - 3_408 + 1_429 + 2_742 - 1_294) * 1e6  # net interest + noninterest
    assert facts("CPT")["revenue_ttm"] == 781_717e3 + 1_573_544e3 - 787_074e3  # OperatingLeaseLeaseIncome
    # Williams' ASC 606 total (14.9bn for 2025) is before eliminations: operating income + costs = Revenues.
    assert facts("WMB")["revenue_ttm"] == (6_083 + 11_950 - 5_829) * 1e6
    # Centene's gross profit + cost (18.9bn) is its services' only, no concept within 5%: operating income + costs.
    assert facts("CNC")["revenue_ttm"] == (103_523 + 194_777 - 95_362) * 1e6


def test_fiscal_year_comes_from_the_10k():
    # Comfort Systems' Q1 2026 10-Q tagged Q1 2025 revenue (1.83bn) as the 2025 fiscal year.
    assert facts("FIX")["revenue_ttm"] == 6_130_988e3 + 9_101_641e3 - 4_004_605e3


def test_ttm_chains_periods_without_a_fiscal_year_a_year_back():
    # Paramount Skydance: H1 2026 + the successor (Aug 8 - Dec 31 2025) + the predecessor's Jul 1 - Aug 6 (the closing
    # day is in neither); a year earlier H1 2025 + FY2024 - 9M 2024 + Q3 2024.
    skyd = facts("SKYD")
    assert skyd["revenue_ttm"] == (14_260 + 12_269 + 2_581) * 1e6 and skyd["np_ttm"] == (209 - 586 - 244) * 1e6
    assert skyd["revenue_prior"] == (14_041 + 29_213 - 21_229 + 6_731) * 1e6 and not skyd["gap"]
    # Ferguson moved its year end from July to December (a 5-month 10-KT): H1 2026 + Aug-Dec 2025 + FY to Jul 2025
    # - Aug-Dec 2024 - H1 2025. July 2024 is reported in no period, so there is no TTM a year earlier.
    ferg = facts("FERG")
    assert ferg["revenue_ttm"] == (16_223 + 12_833 + 30_762 - 12_279 - 15_576) * 1e6 and ferg["revenue_prior"] is None
    # Only after an annual report for less than a year: L3Harris (a normal year) tags its 2025 revenue (21.9bn) with
    # Q4's dates, which would chain to 11.6 + 21.9 + 5.7 = 39.1bn; no TTM revenue instead (Yahoo fills it).
    lhx = facts("LHX")
    assert lhx["revenue_ttm"] is None and lhx["np_ttm"] == (1_112 + 1_606 - 844) * 1e6


def test_equity_and_net_income_are_the_parents():
    # AT&T tags equity only including minorities; Invesco tags no NetIncomeLoss (its profit available to
    # common is after preferred dividends and the 2025 preferred buyback).
    assert facts("T")["equity"] == (126_434 - 15_990) * 1e6
    assert facts("IVZ")["np_ttm"] == pytest.approx(((558.0 + 92.9) + (-174.8 - 106.9) - (464.7 - 31.0)) * 1e6)  # -64.5m
    # the annual history follows the same rules
    assert [(r["fy_end"], r["equity"]) for r in sec.parse_annual("T", FIXES["T"])] == [("2025-12-31", (126_491 - 15_958) * 1e6)]
    assert sec.parse_annual("MTB", FIXES["MTB"])[0]["revenue"] == (6_948 + 2_742) * 1e6


def test_basic_shares_are_the_latest_quarters():
    # Cut from Monster's real companyfacts (2026-10-25): profit and basic weighted-average shares, 10-Q/10-K since 2025.
    # The June quarter (filed 2026-08-07, before the 2:1 split of 2026-08-11), not the half year to June.
    row = sec.parse_facts("MNST", load("us_companyfacts_mnst_shares_sample.json"), date(2026, 10, 25))
    assert (row["period"], row["notice_date"], row["shares_basic"]) == ("2026-06-30", "2026-08-07", 978_662_000)


def test_yahoo_quote_share_counts_in_the_listed_units():
    # Real quote reply (2026-10-25), cut to the fields used: Ares' class A and every class (its LLC units included),
    # Berkshire's B shares and every class in B shares, TSM's depositary shares
    df = yahoo.parse_quotes(load("us_quote_shares_sample.json")).set_index("code")
    assert df.loc["BRK.B"].tolist() == [1_408_035_161, 2_140_709_794]
    assert df.loc["ARES"].tolist() == [223_957_742, 331_775_947] and df.at["TSM", "shares_all"] == 5_186_474_013


def test_yahoo_fundamentals_for_sec_gaps():
    # Real Yahoo fundamentals-timeseries (2026-10-17), one company per growth path.
    s, day = load("us_yahoo_timeseries_sample.json"), date(2026, 10, 17)
    asml = yahoo.parse_timeseries("ASML", s["ASML"], day)  # TTM a year earlier is in the series
    assert (asml["yahoo"], asml["period"], asml["currency"]) == ("ok", "2026-06-30", "EUR")
    assert asml["revenue_ttm"] == pytest.approx(35.3275e9) and asml["rev_yoy"] == pytest.approx(35.3275 / 32.1614 - 1, abs=1e-3)
    assert asml["balance_period"] == "2026-06-30"
    it = yahoo.parse_timeseries("IT", s["IT"], day)  # Gartner (2026-10-19): the latest equity is a quarter older than the TTM
    assert (it["period"], it["balance_period"], it["equity"]) == ("2026-06-30", "2026-03-31", 63_384_000)
    bhp = yahoo.parse_timeseries("BHP", s["BHP"], day)  # semiannual: last fiscal year vs the one before
    assert bhp["rev_yoy"] == pytest.approx(58.76 / 51.262 - 1, abs=1e-3)
    ry = yahoo.parse_timeseries("RY", s["RY"], day)  # latest quarter vs the same quarter a year earlier
    assert ry["np_yoy"] == pytest.approx(5.877 / 5.29 - 1, abs=2e-3)
    assert yahoo.parse_timeseries("RY", s["RY"], date(2027, 6, 1))["yahoo"] == "no recent TTM"
    # freshness: RY reports quarterly, 200 days; BHP has no quarterly figures (half-year reporter), 300 days
    assert yahoo.parse_timeseries("RY", s["RY"], date(2027, 2, 18))["yahoo"] == "no recent TTM"  # 202 days
    assert yahoo.parse_timeseries("BHP", s["BHP"], date(2027, 2, 18))["period"] == "2026-06-30"  # 233 days
    assert yahoo.parse_timeseries("BHP", s["BHP"], date(2027, 4, 28))["yahoo"] == "no recent TTM"  # 302 days


def test_timeseries_net_income_and_shares_for_the_cross_checks():
    row = yahoo.parse_timeseries("SOFI", load("us_yahoo_timeseries_sofi_sample.json"), date(2026, 10, 19))  # real reply
    assert row["revenue_ttm"] == pytest.approx(4305695000) and row["ni_ttm"] == pytest.approx(636264000)
    assert row["shares"] == pytest.approx(1290312404) and row["period"] == "2026-06-30"


def test_spy_holdings_give_the_sp500_weights():
    from stockreport.fetch import index
    df = index.parse_spy((SAMPLES / "spy_holdings_sample.xlsx").read_bytes())  # State Street's real file, 2026-10-23
    w = df.set_index("code")["weight"]
    assert len(df) == 503 and set(df["date"]) == {"2026-10-23"} and "-" not in w.index  # cash lines left out
    assert w["NVDA"] == pytest.approx(0.07770484) and {"GOOGL", "GOOG", "BRK.B"} <= set(w.index)
    assert w.sum() == pytest.approx(0.9962, abs=0.004)  # the rest is cash


def test_index_weights_sum_an_issuers_share_classes(tmp_path, monkeypatch):
    import pandas as pd
    from stockreport import universe
    from stockreport.fetch import index
    monkeypatch.setattr(index, "load", lambda m: pd.Series({"GOOGL": 0.035, "GOOG": 0.028, "NVDA": 0.078}))
    monkeypatch.setattr(sec, "load_ciks", lambda: pd.Series({"GOOGL": 1652044.0, "GOOG": 1652044.0, "NVDA": 1045810.0}))
    df = pd.DataFrame({"cik": [1652044.0, 1045810.0, None]}, index=["GOOG", "NVDA", "TSM"])  # the universe keeps one class
    w = universe.index_weights(df, "us")
    assert w["GOOG"] == pytest.approx(0.063) and w["NVDA"] == pytest.approx(0.078) and pd.isna(w["TSM"])


def test_us_trend_takes_next_years_estimate_now_and_90_days_ago():
    payload = load("us_trend_nvda_sample.json")  # NVIDIA, real reply 2026-10-26
    client = type("C", (), {"crumb": "x", "get": lambda self, url, ok=None, params=None:
                            type("R", (), {"json": lambda r: payload})()})()
    assert yahoo.us_trend(client, "NVDA") == {"code": "NVDA", "analysts": 52, "e1_year": "2027-01", "eps_e2": 15.9146,
                                              "eps_e2_90": 12.81483, "currency": "USD"}  # FY to January 2028
