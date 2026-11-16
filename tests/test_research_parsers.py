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
    # the income of non-operating assets kept apart: 财务费用's interest income plus the finance subsidiary's 利息收入
    q = df[df["period"] == "2026-09-30"].iloc[0]
    assert q["interest_income"] == pytest.approx(402102001.51 + 2312908859.91) and q["invest_income"] == pytest.approx(230947.61)
    assert q["nonop"] > 0 and fy["nonop"] > 0


def test_operating_profit_without_the_income_of_non_operating_assets():
    from stockreport.research import sheet
    # CN (茅台, 2026 Q1-Q3, 亿元): 营业利润 889.80 - 投资收益 0.00 - 公允价值变动 1.21 - interest income 27.15 + interest 0.32
    cn_row = {"op_income": 889.80, "pretax": 890.18, "interest": 0.32, "invest_income": 0.0, "fv_change": 1.21,
              "interest_income": 4.02 + 23.13}
    assert sheet.ebit("cn", cn_row) == pytest.approx(889.80 - 1.21 - 27.15 + 0.32)
    # HK (Tencent 2025, 亿元): pretax 2772.5 + finance costs 151.3 - interest income 169.1 - associates 237.4
    hk_row = {"op_income": 2415.6, "pretax": 2772.5, "interest": 151.3, "interest_income": 169.1, "invest_income": 237.4}
    assert sheet.ebit("hk", hk_row) == pytest.approx(2517.3)
    assert sheet.ebit("us", {"op_income": 104.0, "pretax": 179.0, "interest": 2.0}) == 104.0  # Amazon's gains out
    assert sheet.ebit("cn", {"op_income": None, "pretax": 10.0, "interest": 1.0}) == 11.0  # without the lines: as before
    years = pd.DataFrame({"op_income": [100.0, None], "pretax": [90.0, 50.0], "interest": [5.0, 2.0],
                          "invest_income": [20.0, None], "fv_change": [None, None], "interest_income": [3.0, None]})
    assert list(sheet.ebit("cn", years)) == [82.0, 52.0]
    # a line empty in the latest report is zero there, not the last period's (五粮液's fair-value line)
    st = pd.DataFrame({"period": ["2024-09-30", "2024-12-31", "2025-09-30"], "months": [9, 12, 9],
                       "fv_change": [-7.0, -8.0, None]})
    assert sheet.ttm(st, "fv_change", sparse=True) == pytest.approx(-1.0) and sheet.ttm(st, "fv_change") == -8.0


def test_hk_statements_keep_associates_and_interest_income_apart():
    rows = [{"REPORT_DATE": "2025-12-31 00:00:00", "DATE_TYPE_CODE": "001", "STD_ITEM_NAME": n, "AMOUNT": v}
            for n, v in (("除税前溢利", 2772.5), ("融资成本", 151.3), ("利息收入", 169.1), ("应占联营公司溢利", 237.4),
                         ("联营公司权益", 3424.1), ("合营公司权益", 63.0), ("指定以公允价值记账之金融资产", 5638.0))]
    fy = hk.statement_rows(rows, {}).iloc[0]
    assert fy["interest_income"] == 169.1 and fy["invest_income"] == 237.4
    assert fy["nonop"] == pytest.approx(3487.1)  # stakes at book; fair-value assets stay out, their gains in profit


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
    assert fy["nonop"] > 50e9  # its long-term marketable securities, outside cash and operating income
    latest = us.latest("AAPL", payload, date(2026, 11, 8))
    assert latest["period"] == "2026-09-26" and latest["revenue"] == 478834e6 and latest["revenue_prior"] == 416161e6


def test_nasdaq_consensus_and_flows():
    n = json.loads((DATA / "research_nasdaq_sample.json").read_text())
    c = us.parse_consensus(n["forecast"], n["target"], n["ratings"], n["surprise"])
    assert c["eps"]["2027"] == pytest.approx(9.7) and c["target_mean"] == pytest.approx(340.14) and c["ratings"]["buy"] == 15
    assert [a["quarter"] for a in c["actuals"]] == ["2026-09", "2026-06", "2026-03", "2025-12"]
    assert sum(a["eps"] for a in c["actuals"]) == pytest.approx(8.81)
    f = us.parse_flows(n["short"], n["insider"])
    assert f["short"][0]["shares"] == 131591865 and f["insider"]["sells"] == (26, 46)


def test_yahoo_annual_and_summary():
    y = json.loads((DATA / "research_yahoo_sample.json").read_text())
    a = sources.parse_annual(y["annual_aapl"])
    assert a.iloc[-1]["revenue"] == 478834e6 and a.iloc[-1]["capex"] > 0 and a.iloc[-1]["currency"] == "USD"
    s = sources.parse_summary(y["summary_0700"], date(2026, 11, 8))
    assert s["currency"] == "HKD" and s["report_currency"] == "CNY" and s["analysts"] > 0 and s["target_mean"] > 0
    assert set(sources.eps_years(s["estimates"])) == {"2026", "2027"}


def test_an_unclassified_listing_takes_its_snapshot_industrys_damodaran_industry(monkeypatch):
    # HK: 8 classified 综合性银行 all Bank (Money Center): HSBC, which Damodaran's list lacks, is one; a group of 4 classified
    # is too few, and one without a majority (Nasdaq's "Business Services": 3 of 7) gives nothing
    banks = [f"0{i:04d}" for i in range(1, 9)]
    co = pd.DataFrame({"market": "hk", "code": banks + ["00100", "00101", "00102", "00103"] + [f"1{i:04d}" for i in range(7)],
                       "industry": ["Bank (Money Center)"] * 8 + ["Insurance (Life)"] * 4 + ["Retail (General)"] * 3 +
                       ["Transportation"] * 2 + ["Financial Svcs. (Non-bank & Insurance)"] * 2, "sector": "x", "region": "China"})
    rows = lambda ind: pd.DataFrame({"industry": [ind], "firms": [50], "beta": [0.7]})
    tables = {"companies": co, "industries_Global": pd.concat([rows("Bank (Money Center)"), rows("Retail (General)")]),
              "industries_China": rows("Bank (Money Center)").assign(firms=5)}
    monkeypatch.setattr(damodaran, "load", lambda name: tables[name])
    snap = pd.DataFrame({"code": banks + ["00005", "00100", "00101", "00102", "00103", "00200"] + [f"1{i:04d}" for i in range(7)] + ["09988"],
                         "industry_type": ["综合性银行"] * 9 + ["人寿与健康保险"] * 5 + ["多品类零售"] * 8})
    hsbc = damodaran.industry_like("hk", "00005", snap, "United Kingdom")
    assert hsbc["industry"] == "Bank (Money Center)" and hsbc["region"] == "Global" and hsbc["beta"] == 0.7
    assert hsbc["country"] is None and hsbc["inferred"].startswith("8 of the 8")
    assert damodaran.industry_like("hk", "00200", snap, "Hong Kong") == {}  # 4 classified: too few
    assert damodaran.industry_like("hk", "09988", snap, "China") == {}  # 3 of 7: no majority
    assert damodaran.industry_like("hk", "99999", snap, None) == {}  # not in the snapshot
    from stockreport.research import facts
    assert facts.kind_of("hk", pd.DataFrame(), hsbc["industry"], None) == "bank"


def test_yahoo_figures_in_dollars_under_a_yuan_label():
    # 中芯国际's A line, 2025: ours in CNY at that year's rates, Yahoo's its HK line's USD labelled CNY (6.67 to the dollar)
    from stockreport.research import facts
    fx = pd.Series({"CNY": 6.6705, "USD": 1.0})
    a = pd.DataFrame({"period": ["2025-12-31"], "revenue": [67.32e9], "ni": [5.04e9], "equity": [150.8e9], "ocf": [20.08e9], "assets": [367.7e9]})
    second = pd.DataFrame({"period": ["2025-12-31"], "revenue": [9.327e9], "ni": [0.685e9], "equity": [21.44e9], "ocf": [3.194e9], "assets": [52.27e9]})
    assert facts.second_in_usd(a, second, "CNY", fx)
    assert not facts.second_in_usd(a, second.assign(revenue=60e9, ni=4.9e9, equity=150e9, ocf=19e9, assets=360e9), "CNY", fx)  # agree
    assert not facts.second_in_usd(a, second.assign(revenue=60e9), "CNY", fx)  # one figure apart: a definition, not units
    assert not facts.second_in_usd(a, second, "USD", fx)


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


def test_a_20f_filer_takes_its_last_fiscal_year_as_trailing():
    # Novo Nordisk files 20-F (no 10-Q): the last annual row stands for the trailing twelve months
    import pandas as pd
    from stockreport.research import us
    st = pd.DataFrame({"period": ["2024-12-31", "2025-12-31", "2025-06-30"], "months": [12, 12, 6],
                       "revenue": [290.4, 309.1, 150.0], "ni": [101.0, 102.4, 50.0], "gp": [246.0, 258.0, 125.0],
                       "ocf": [121.0, 119.1, 60.0], "pretax": [128.0, 130.5, 64.0], "interest": [1.0, 6.8, 3.0],
                       "da": [12.0, 14.7, 7.0], "capex": [47.0, 60.1, 30.0], "equity": [143.5, 194.0, 170.0],
                       "shares": [4.44, 4.44, 4.44], "notice": ["2025-02-05", "2026-02-04", "2025-08-06"]})
    x = us.from_annual(st)
    assert x["period"] == "2025-12-31" and x["basis"] == "FY" and x["revenue"] == 309.1 and x["revenue_prior"] == 290.4
    assert x["ni_prior"] == 101.0 and x["capex"] == 60.1 and x["equity"] == 194.0 and x["notice"] == "2026-02-04"
    assert us.from_annual(st.iloc[:0]) == {}


def test_a_20f_filers_trailing_twelve_months_from_yahoos_interim_figures():
    # TSMC (TWD bn): Yahoo's trailing values at 2026-09-30; interest from four quarters, one missing: none
    from stockreport.research import facts
    y = json.loads((DATA / "research_yahoo_trailing_tsm_sample.json").read_text())
    t = sources.parse_trailing(y)
    assert t["period"] == "2026-09-30" and t["currency"] == "TWD" and t["basis"] == "TTM (Yahoo)"
    assert t["ni"] == pytest.approx(2527.57e9, rel=1e-4) and t["revenue"] == pytest.approx(4944.82e9, rel=1e-4)
    assert t["capex"] == pytest.approx(1651.44e9, rel=1e-4) and t["interest"] is None
    assert t["equity"] == pytest.approx(6997.9e9, rel=1e-4) and t["shares"] == pytest.approx(25.93e9, rel=1e-3)
    st = pd.DataFrame({"period": ["2024-12-31", "2025-12-31"], "months": [12, 12], "currency": ["TWD", "TWD"],
                       "revenue": [2894.3e9, 3809.1e9], "ni": [1173.3e9, 1717.9e9]})
    assert facts.trailing_or_annual(st, t) is t
    assert facts.trailing_or_annual(st, t | {"currency": "USD"})["basis"] == "FY"  # another currency: the fiscal year
    assert facts.trailing_or_annual(st, {})["period"] == "2025-12-31"


def test_an_adr_counts_shares_in_its_own_units():
    # TSMC: 25.93bn shares, an ADR of 5 at 413.35 against a 2,143.8bn market value -> 5.0 shares a unit; Apple 1
    from stockreport.research import facts
    assert facts.units(413.35, 25.93e9, {"mcap": 2143.8e9}, None) == pytest.approx(5.0, rel=0.01)
    assert facts.units(355.63, 14.53e9, {"mcap": 5168e9}, None) == 1.0
    assert facts.units(413.35, 25.93e9, {}, 2141.6e9) == pytest.approx(5.0, rel=0.01)  # Nasdaq's value when Tencent fails
    assert facts.units(413.35, 25.93e9, {}, None) == 1.0


def xbrl(ni: dict, eps: dict) -> "ET.Element":
    """A filing's XBRL instance in miniature: net income per period, basic EPS per period and share class."""
    import xml.etree.ElementTree as ET
    ctx, facts = [], []
    for i, ((s, e), v) in enumerate(ni.items()):
        ctx.append(f'<xbrli:context id="n{i}"><xbrli:period><xbrli:startDate>{s}</xbrli:startDate>'
                   f'<xbrli:endDate>{e}</xbrli:endDate></xbrli:period></xbrli:context>')
        facts.append(f'<us-gaap:NetIncomeLoss contextRef="n{i}">{v}</us-gaap:NetIncomeLoss>')
    for i, ((s, e, m), v) in enumerate(eps.items()):
        ctx.append(f'<xbrli:context id="e{i}"><xbrli:entity><xbrli:segment><xbrldi:explicitMember dimension='
                   f'"us-gaap:StatementClassOfStockAxis">{m}</xbrldi:explicitMember></xbrli:segment></xbrli:entity>'
                   f'<xbrli:period><xbrli:startDate>{s}</xbrli:startDate><xbrli:endDate>{e}</xbrli:endDate>'
                   f'</xbrli:period></xbrli:context>')
        facts.append(f'<us-gaap:EarningsPerShareBasic contextRef="e{i}">{v}</us-gaap:EarningsPerShareBasic>')
    return ET.fromstring('<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/'
                         '2006/xbrldi" xmlns:us-gaap="http://fasb.org/us-gaap/2025">' + "".join(ctx + facts) + "</xbrli:xbrl>")


def test_a_multi_class_filers_count_in_its_listed_lines_units(monkeypatch):
    # Visa-like: class A listed, class B earns 1.55 times A's EPS (its conversion rate), class C 4 times. The line's
    # market value over its price is 1.87bn class A shares. Years 2021-2023 come from an older 10-K with renamed members,
    # where class A counted 2.40bn and B 1.55bn: B is nearer the line, the year shared with the newer 10-K picks A.
    monkeypatch.setattr(us.sec, "make_http", lambda: None)
    y = lambda n: (f"{n - 1}-10-01", f"{n}-09-30")
    q = ("2026-10-01", "2026-12-31")
    filings = {
        "Q": xbrl({q: 6.0e9}, {q + ("A",): 3.2, q + ("B",): 4.96, q + ("C",): 12.8}),
        "K25": xbrl({y(n): v for n, v in ((2025, 20.0e9), (2024, 19.6e9), (2023, 18.0e9))},
                    {y(n) + (m,): e for n, ea in ((2025, 10.5), (2024, 9.8), (2023, 8.8)) for m, e in (("A", ea), ("B", ea * 1.55), ("C", ea * 4))}),
        "K23": xbrl({y(n): v for n, v in ((2023, 18.0e9), (2022, 16.0e9), (2021, 14.4e9))},
                    {y(n) + (m,): e for n, ea in ((2023, 8.8), (2022, 7.2), (2021, 6.0)) for m, e in (("OldA", ea), ("OldB", ea * 1.55))}),
    }
    ni = [{"start": s, "end": e, "val": 1, "accn": a, "form": f} for a, f, (s, e) in (
        ("Q", "10-Q", q), ("K25", "10-K", y(2025)), ("K23", "10-K", y(2023)))]
    payload = {"cik": 1, "facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": ni}}}}}
    st = pd.DataFrame({"period": [f"{n}-09-30" for n in range(2020, 2026)], "months": 12, "shares": None})
    got, last = us.with_classes(st, {"shares": None}, payload, 1.87e9, fetch=lambda http, cik, accn: filings[accn])
    assert last["shares"] == pytest.approx(6.0e9 / 3.2)  # the latest quarter's, in class A units
    counts = dict(zip(got["period"].str[:4], got["shares"]))
    assert counts["2025"] == pytest.approx(20.0e9 / 10.5) and counts["2023"] == pytest.approx(18.0e9 / 8.8)
    assert counts["2021"] == pytest.approx(2.4e9)  # class A's, not B's 1.55bn nearer the line
    assert pd.isna(counts["2020"])  # no 10-K reports it
    full = st.assign(shares=1e9)  # a count in companyfacts: nothing fetched
    assert us.with_classes(full, {"shares": 1e9}, payload, 1.87e9, fetch=None)[0] is full


def test_a_20f_filers_newest_year_from_the_second_source():
    import pandas as pd
    from stockreport.research import facts
    st = pd.DataFrame({"period": ["2023-12-31", "2024-12-31"], "months": [12, 12], "revenue": [2161.7, 2894.3]})
    second = pd.DataFrame({"period": ["2024-12-31", "2025-12-31"], "revenue": [2894.3, 3809.1], "currency": ["TWD"] * 2})
    out, years = facts.newer_years(st, second)
    assert years == ["2025-12-31"] and out["revenue"].tolist() == [2161.7, 2894.3, 3809.1] and out["months"].tolist() == [12] * 3
    assert facts.newer_years(st, second.iloc[:1])[1] == []


def test_an_h_line_takes_its_a_lines_consensus():
    # 平安 H: Eastmoney's A-line forecasts (CNY, its brokers' reports for the range), Yahoo's targets and ratings (on the
    # H price); without an A line, Yahoo's as before
    from stockreport.research import facts
    street = {"estimates": {"0y": {"end": "2026-12-31", "eps": 7.02}, "+1y": {"end": "2027-12-31", "eps": 8.88}},
              "est_currency": "CNY", "target_mean": 80.0, "analysts": 20, "ratings": {"buy": 15}}
    a = {"source": "Eastmoney 研报一致预期", "eps": {"2026": 6.52, "2027": 7.53}, "analysts": 27, "target_high": 89.8,
         "reports": [{"date": "2026-11-01", "eps": {"2026": 6.4}}]}
    out = facts.consensus("hk", {"street": street, "consensus": a}, 2025)
    assert out["eps"] == {"2026": 6.52, "2027": 7.53} and out["currency"] == "CNY" and len(out["reports"]) == 1
    assert out["target_mean"] == 80.0 and out["analysts"] == 20 and out["eps_yahoo"]["2026"] == 7.02
    alone = facts.consensus("hk", {"street": street, "consensus": None}, 2025)
    assert alone["source"] == "Yahoo" and alone["eps"]["2027"] == 8.88 and "reports" not in alone


def test_us_cash_with_securities_under_the_filers_own_tag():
    # NVIDIA FY2026: no short-term investments in SEC's standard tags (its own nvda: tag holds 51.95bn), Yahoo's cash and
    # short-term investments 62.56bn; a year whose securities are tagged, or within the large gap, keeps SEC's cash
    st = pd.DataFrame({"period": ["2024-01-28", "2025-01-26", "2026-01-25", "2026-01-25"], "months": [12, 12, 12, 9],
                       "cash": [26.0, 43.2, 10.6, 10.6], "securities": [18.7, None, None, None]})
    second = pd.DataFrame({"period": ["2024-01-31", "2025-01-31", "2026-01-31"], "cash": [40.0, 44.0, 62.56]})
    out, years = us.with_securities(st, second, 0.05)
    assert years == ["2026-01-25"] and out["cash"].tolist() == [26.0, 43.2, 62.56, 10.6]
    assert us.with_securities(st, None, 0.05)[1] == []


def us_segments(name: str) -> pd.DataFrame:
    from stockreport.research import segments
    facts = segments.parse_instance((DATA / f"segments_us_{name}_sample.xml").read_bytes())  # trimmed 10-K / 20-F
    return segments.breakdowns(facts, segments.parse_labels(json.loads((DATA / f"segments_us_{name}_labels.json").read_text())))


def test_us_segments_are_parts_that_add_up_not_subtotals():
    # Amazon's FY2025 10-K: three segments with operating income; the seven sales groups, not product / service
    df = us_segments("amzn")
    fy = df[df["period"] == "2025-12-31"].set_index(["by", "item"])
    aws = fy.loc[("segment", "AWS")]
    assert aws["revenue"] == pytest.approx(128725e6) and aws["op_income"] == pytest.approx(45606e6)
    assert aws["op_margin"] == pytest.approx(0.3543, abs=1e-4) and aws["op_share"] == pytest.approx(0.5703, abs=1e-4)
    assert len(fy.loc["segment"]) == 3 and fy.loc["segment", "share"].sum() == pytest.approx(1)
    assert ("product", "Advertising services") in fy.index and len(fy.loc["product"]) == 7
    assert fy.loc["product", "share"].sum() == pytest.approx(1) and fy.loc["region", "share"].sum() == pytest.approx(1)
    assert fy.loc["product", "gross_margin"].isna().all() and sorted(df["period"].unique()) == ["2023-12-31", "2024-12-31", "2025-12-31"]
    assert segments_unallocated(df, "2025-12-31") is None  # Amazon's segments carry all of its operating income


def segments_unallocated(df, period):
    rows = df[(df["period"] == period) & (df["item"] == "未分配（总部及调节项）")]
    return rows["op_income"].iloc[0] if len(rows) else None


def test_us_segments_with_eliminations_in_the_reporting_currency():
    # JD's 20-F: CNY (its USD convenience translation of the latest year left out), the eliminations between segments
    # tagged on the consolidation axis, a loss-making segment (no profit shares), corporate costs as the remainder
    df = us_segments("jd")
    fy = df[(df["period"] == "2025-12-31") & (df["by"] == "segment")].set_index("item")
    assert fy.loc["JD Retail", "revenue"] == pytest.approx(1126.399e9, rel=1e-6)
    assert fy.loc["分部间抵消", "revenue"] == pytest.approx(-83.742e9, rel=1e-6) and pd.isna(fy.loc["分部间抵消", "op_margin"])
    assert fy["share"].sum() == pytest.approx(1, abs=0.005) and fy["op_share"].isna().all()
    assert fy.loc["New Businesses", "op_margin"] < 0 and fy.loc["JD Retail", "gross_margin"] == pytest.approx(0.1759, abs=1e-4)
    assert segments_unallocated(df, "2025-12-31") == pytest.approx(-7.256e9, rel=1e-3)


def test_segment_partition_and_checked_measures():
    from stockreport.research import segments
    values = {"product": 60, "service": 40, "a": 30, "b": 30, "c": 25, "d": 15, "elim": -5}
    assert sorted(segments.partition(values, 95, {"elim"})) == ["a", "b", "c", "d", "elim"]  # the parts, eliminations in
    # a negative that isn't an offsetting line can't net a subtotal back out: {product, a, b, c, d, odd} would add up
    assert sorted(segments.partition(values | {"elim": 0, "odd": -60}, 100)) == ["a", "b", "c", "d"]
    assert segments.partition({"a": 50, "b": 30}, 100) is None and segments.partition({"a": 100}, 100) is None
    got = {"a": 10.0, "b": 5.0}
    assert segments.measure(got.get, ["a", "b"], 15.0, ["a", "b"]) == got
    assert segments.measure(got.get, ["a", "b"], 20.0, ["a", "b"]) == {}  # partial tags don't add up: dropped
    assert segments.measure(got.get, ["a", "b", "c"], 15.0, ["a", "b", "c"]) == {}


def test_hk_segment_note_from_the_annual_reports_layout_text():
    from stockreport.research import segments
    tencent = segments.page_tables((DATA / "segments_hk_tencent_page.txt").read_text())  # 2025 annual report p.194
    assert [t["year"] for t in tencent] == [2025, 2024]
    assert tencent[0]["names"][:4] == ["VAS", "Marketing Services", "FinTech and Business Services", "Others"]
    revenue = {2025: ("2025-12-31", 751.766e9), 2024: ("2024-12-31", 660.257e9)}  # the statements', CNY
    df = segments.from_report(tencent, revenue, "ANNUAL REPORT 2025").set_index(["period", "item"])
    vas = df.loc[("2025-12-31", "VAS")]
    assert vas["revenue"] == pytest.approx(369.281e9) and vas["gross_margin"] == pytest.approx(222296 / 369281)
    assert df.loc["2024-12-31", "share"].sum() == pytest.approx(1) and df["op_income"].isna().all()
    assert segments.from_report(tencent, {2025: ("2025-12-31", 700e9)}, "x").empty  # not the company's revenue
    # Anta: names offset to the right of the amounts, a bulleted row label, segment results, an unallocated column
    anta = segments.page_tables((DATA / "segments_hk_anta_page.txt").read_text())[0]
    assert anta["names"][:3] == ["ANTA brand", "FILA brand", "All other brands"] and anta["op"][3] == -274
    df = segments.from_report([anta], {2025: ("2025-12-31", 80.219e9)}, "Annual Report 2025").set_index("item")
    assert df.loc["FILA brand", "op_margin"] == pytest.approx(7418 / 28469) and len(df) == 4


def test_hk_segment_note_whose_revenue_row_is_total_revenues():
    # Meituan's 2025 annual report (2024 table): the row is "Total revenues", which the page filter once passed over;
    # a footnote mark on a column name is dropped; a loss-making segment leaves the profit shares out
    from stockreport.research import segments
    text = (DATA / "segments_hk_meituan_page.txt").read_text()
    assert segments.note_page(text)
    table = segments.page_tables(text)[0]
    assert table["year"] == 2024 and table["names"][:3] == ["Core local commerce", "New initiatives", "Unallocated items"]
    df = segments.from_report([table], {2024: ("2024-12-31", 337.591576e9)}, "Annual Report 2025").set_index("item")
    assert df.loc["Core local commerce", "revenue"] == pytest.approx(250.247496e9)
    assert df.loc["Core local commerce", "op_margin"] == pytest.approx(52415162 / 250247496)
    assert df.loc["Unallocated items", "op_income"] == pytest.approx(-8.296892e9) and df["op_share"].isna().all()
