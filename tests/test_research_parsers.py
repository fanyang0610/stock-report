"""Research stage 9: the per-stock parsers on small saved samples (tests/data/research_*, damodaran_*; captured
2026-11-08)."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stockreport.research import cn, damodaran, hk, listings, sources, us

DATA = Path(__file__).parent / "data"
CN = json.loads((DATA / "research_cn_sample.json").read_text())


def test_cn_general_statements():
    s = CN["600519"]
    df = cn.statement_rows(s["income"], s["balance"], s["cash"], s["main"])
    fy = df[df["period"] == "2025-12-31"].iloc[0]
    assert fy["months"] == 12 and fy["currency"] == "CNY" and fy["notice"] == "2026-04-17"
    assert fy["revenue"] == pytest.approx(172054171890.91) and fy["ni"] == pytest.approx(82320067101.68)
    assert fy["gp"] == pytest.approx(fy["revenue"] - fy["cogs"]) and fy["shares"] == pytest.approx(1250081601)
    assert fy["equity"] == pytest.approx(244637811032.18) and fy["ocf"] == pytest.approx(61522204989.35)
    assert df.loc[df["period"] == "2026-09-30", "months"].iloc[0] == 9


def test_cn_bank_statements():
    s = CN["600036"]
    fy = cn.statement_rows(s["income"], s["balance"], s["cash"], s["main"]).query("period == '2025-12-31'").iloc[0]
    assert fy["revenue"] == pytest.approx(337532e6) and fy["ni"] == pytest.approx(150181e6) and pd.isna(fy["cogs"])
    assert fy["npl"] == pytest.approx(0.94) and fy["car"] == pytest.approx(18.24) and fy["nim"] == pytest.approx(1.87)


def test_cn_consensus_and_flows(monkeypatch):
    rec = CN["flows_600519"]
    monkeypatch.setattr(cn, "get", lambda report, *a, **k: rec.get(report, []))

    class Reports:  # the broker-report archive: no reports in the sample
        def __init__(self, *a, **k): pass
        def get(self, *a, **k): return type("R", (), {"json": lambda self: {"data": []}})()
    monkeypatch.setattr(cn, "Http", Reports)
    c = cn.consensus("600519", date(2026, 11, 8))
    assert c["eps"]["2026"] == pytest.approx(66.815) and c["analysts"] == 42 and c["target_high"] == 2030
    f = cn.flows("600519", date(2026, 11, 8))
    assert f["margin"]["balance"] > 0 and f["pledge"]["ratio"] == pytest.approx(0.14)
    assert f["dividends"][0]["dps"] == pytest.approx(28.02423) and f["holders"][0]["count"] == 278364


def test_hk_statements_back_in_the_reporting_currency(monkeypatch):
    """Eastmoney's HK amounts are CNY at the period end's rate: SHKP's FY2026 profit CNY 18.61bn = HKD 21.43bn."""
    rows = json.loads((DATA / "research_hk_sample.json").read_text())
    monkeypatch.setattr(hk.yahoo, "cny_per", lambda cur, day: pd.Series(0.8686, index=cur.index))
    shares = hk.shares_of({"HOLDER_PROFIT": 18.61e9, "BASIC_EPS": 6.42, "ISSUED_COMMON_SHARES": 2897780274})
    df = hk.to_currency(hk.statement_rows(rows, {"2026-06-30": shares}), "HKD")
    fy = df[df["period"] == "2026-06-30"].iloc[0]
    assert fy["currency"] == "HKD" and fy["months"] == 12 and fy["issued"] == 2897780274
    assert fy["shares"] == pytest.approx(18.61e9 / 6.42)  # the weighted average, by profit over basic EPS
    assert fy["ni"] == pytest.approx(21.43e9, rel=0.005) and fy["revenue"] == pytest.approx(94.19e9, rel=0.005)
    assert fy["capex"] > 0 and fy["div_paid"] > 0


def test_us_statements_and_ttm():
    payload = json.loads((DATA / "research_us_aapl_facts.json").read_text())
    df = us.parse_statements("AAPL", payload)
    fy = df[df["period"] == "2026-09-26"].iloc[0]
    assert fy["revenue"] == 478834e6 and fy["ni"] == 132175e6 and fy["cur_assets"] == 173857e6
    assert fy["buyback"] == 86390e6 and fy["debt"] == pytest.approx(80111e6) and fy["eps"] == pytest.approx(8.98)
    latest = us.latest("AAPL", payload, date(2026, 11, 8))
    assert latest["period"] == "2026-09-26" and latest["revenue"] == 478834e6 and latest["revenue_prior"] == 416161e6


def test_nasdaq_consensus_and_flows():
    n = json.loads((DATA / "research_nasdaq_sample.json").read_text())
    c = us.parse_consensus(n["forecast"], n["target"], n["ratings"])
    assert c["eps"]["2027"] == pytest.approx(9.7) and c["target_mean"] == pytest.approx(340.14) and c["ratings"]["buy"] == 15
    f = us.parse_flows(n["short"], n["insider"])
    assert f["short"][0]["shares"] == 131591865 and f["insider"]["sells"] == (26, 46)


def test_yahoo_annual_and_summary():
    y = json.loads((DATA / "research_yahoo_sample.json").read_text())
    a = sources.parse_annual(y["annual_aapl"])
    assert a.iloc[-1]["revenue"] == 478834e6 and a.iloc[-1]["capex"] > 0 and a.iloc[-1]["currency"] == "USD"
    s = sources.parse_summary(y["summary_0700"], date(2026, 11, 8))
    assert s["currency"] == "HKD" and s["report_currency"] == "CNY" and s["analysts"] > 0 and s["target_mean"] > 0
    assert set(sources.eps_years(s["estimates"])) == {"2026", "2027"}


def test_damodaran_tables():
    r = damodaran.ratings((DATA / "damodaran_ratings_sample.xls").read_bytes())
    assert set(r["table"]) == {"large", "financial", "smaller", "infrastructure"}
    large = r[r["table"] == "large"]
    assert large.iloc[-1]["rating"] == "Aaa/AAA" and large.iloc[-1]["spread"] == pytest.approx(0.004) and len(large) == 15
    capex = damodaran.industry_sheet((DATA / "damodaran_capex_sample.xls").read_bytes(), damodaran.COLUMNS["capex"])
    adv = capex[capex["industry"] == "Advertising"].iloc[0]
    assert adv["sales_to_capital"] == pytest.approx(3.8532841) and len(capex) > 90


def test_listings_parsers():
    hkx = listings.parse_hkex((DATA / "hkex_lots_sample.xlsx").read_bytes())
    assert set(hkx["kind"]) <= {"ordinary", "reit"} and hkx["code"].str.fullmatch(r"\d{5}").all() and len(hkx) > 0
    cninfo = listings.parse_cninfo({"stockList": [{"code": "600519", "zwjc": "贵州茅台", "pinyin": "gzmt", "category": "A股"},
                                                  {"code": "900901", "zwjc": "云赛B股", "pinyin": "ysbg", "category": "B股"}]}, "A股")
    assert list(cninfo["code"]) == ["600519"] and cninfo.iloc[0]["name"] == "贵州茅台"
