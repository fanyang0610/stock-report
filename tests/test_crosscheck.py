"""Cross-checks and drift alarms (Phase 12) on saved samples: real Tencent quotes, Yahoo fundamentals and key
statistics (2026-10-19) against the figures the builds had for the same stocks that day."""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stockreport import crosscheck
from stockreport.fetch import tencent, yahoo

SAMPLES = Path(__file__).parent / "data"
sample = lambda name: pd.read_csv(SAMPLES / name, dtype={"code": str, "trade_date": str, "period": str}).set_index("code")


def dropped(drops: dict, label: str) -> list[str]:
    return sorted(drops[label].index[drops[label]])


def counts(info: dict, label: str) -> str:
    """The printed counts after a check's label, spaces squeezed: 'compared: agree / small / large[, drops n]'."""
    line = next(line for line in info["checks"] if line.strip().startswith(label))
    return " ".join(line.strip()[len(label):].split())


def test_gap_is_relative_and_signs_must_match():
    g = crosscheck.gap(pd.Series([100.0, 100.0, -5.0, np.nan, 10.0]), pd.Series([101.0, 90.0, 5.0, 1.0, np.nan]))
    assert g[0] == pytest.approx(0.01) and g[1] == pytest.approx(0.1)
    assert g[2] == np.inf and g[3:].isna().all()


def tencent_sample() -> pd.DataFrame:
    return tencent.parse((SAMPLES / "tencent_quotes_sample.txt").read_bytes().decode("gbk")).set_index("code")


def test_tencent_quotes_parse():
    t = tencent_sample()
    assert t.loc["600519", ["price", "prev_close", "pe_ttm", "pb"]].tolist() == [1329.0, 1312.97, 20.40, 6.61]
    assert t.loc["600519", "mcap"] == pytest.approx(16613.58e8) and t.loc["600519", "shares"] == 1250081601
    assert (t["date"] == "2026-10-16").all() and len(t) == 5


def test_cn_drops_what_neither_tencent_nor_eastmoney_confirms(monkeypatch):
    monkeypatch.setattr(tencent, "load", tencent_sample)
    monkeypatch.setitem(crosscheck.CFG, "drop_gap", 0.05)  # financial-data's threshold, to show the confirmation
    df, info = sample("crosscheck_cn_sample.csv"), {}
    drops = crosscheck.checks(df, "cn", info)
    # 指南针: the 业绩报表 BPS is 45% above Tencent's and Eastmoney's (shares added since the report); 紫金矿业 is
    # 6% off Tencent but Eastmoney's P/B agrees with ours, so it stays
    assert dropped(drops, "book per share vs Tencent >5%") == ["300803"]
    # 大族数控: TTM profit 19% below both; 兖矿能源 is off Tencent but Eastmoney agrees
    assert dropped(drops, "TTM profit vs Tencent >5%") == ["301200"]
    assert dropped(drops, "shares vs Tencent >5%") == []
    assert counts(info, "close vs Tencent") == "5: 5 / 0 / 0"
    assert counts(info, "book per share vs Tencent") == "5: 1 / 2 / 2, drops 1"


def test_us_compares_sec_with_yahoo_for_the_same_period(monkeypatch):
    monkeypatch.setattr(yahoo, "GAPS", SAMPLES / "crosscheck_us_yahoo_sample.csv")
    df, info = sample("crosscheck_us_sample.csv"), {}
    drops = crosscheck.checks(df, "us", info)
    # SoFi's SEC revenue concept gives 0.61bn against Yahoo's 4.31bn, Invesco's net income -0.31bn against -0.06bn:
    # dropped. Berkshire's revenue (385bn vs 438bn, 14%) and Amazon's equity (552bn vs 442bn, 19.9%) are large gaps
    # under the 20% drop line. TSM is valued on Yahoo's own numbers: nothing to compare.
    assert dropped(drops, "TTM revenue vs Yahoo >20%") == ["SOFI"]
    assert dropped(drops, "TTM net income vs Yahoo >20%") == ["IVZ"]
    assert dropped(drops, "equity vs Yahoo >20%") == []
    assert counts(info, "TTM revenue vs Yahoo") == "5: 3 / 0 / 2, drops 1"
    assert counts(info, "equity vs Yahoo") == "5: 4 / 0 / 1, drops 0"
    # Berkshire's Yahoo count is in class A shares: a large gap, counted only
    assert counts(info, "shares vs Yahoo (not ADRs)") == "5: 4 / 0 / 1"
    assert not any("shares" in label for label in drops)


def test_hk_key_statistics_parse_and_book_check(monkeypatch, tmp_path):
    payload = json.loads((SAMPLES / "hk_keystats_swire_sample.json").read_text(encoding="utf-8"))
    row = yahoo.parse_trend("00019", payload)  # Swire Pacific A, real reply 2026-10-19
    assert row["bvps_y"] == pytest.approx(197.452) and row["eps_ttm_y"] == pytest.approx(6.57)
    assert row["shares_y"] == 3627920500 and row["period_y"] == "2026-06-30"
    # Eastmoney's book per A share counts only the A shares (342.69 HKD): 74% above Yahoo's, dropped
    pd.DataFrame([row, {"code": "00700", "bvps_y": 148.0, "eps_ttm_y": 26.0, "shares_y": 9.1e9, "period_y": "2026-06-30"}]
                 ).to_csv(tmp_path / "hk.csv", index=False)
    monkeypatch.setattr(yahoo, "CONSENSUS", tmp_path / "hk.csv")
    df = pd.DataFrame({"bps": [342.69, 147.9], "eps_ttm": [8.1, 28.4], "shares": [778988000.0, 9.1e9],
                       "period": ["2026-06-30", "2026-06-30"], "np_ttm": [6.3e9, 2.58e11], "revenue_ttm": [9e10, 8e11],
                       "eps_e1": [9.8, 30.0], "eps_e2": [9.8, 32.0], "analysts": [7, 33]}, index=["00019", "00700"])
    info = {}
    drops = crosscheck.checks(df, "hk", info)
    assert dropped(drops, "book per share vs Yahoo >20%") == ["00019"]
    assert counts(info, "trailing EPS vs Yahoo") == "2: 0 / 0 / 2"  # counted only


def test_consensus_units_drop_and_basis_gaps_count():
    df = pd.DataFrame({"eps_ttm": [1.0, 1.0, 0.01, 1.0], "eps_e1": [1.1, 2.5, 0.9, 1.0], "eps_e2": [25.0, 2.6, 1.0, 1.1],
                       "np_ttm": [10.0, 10.0, 0.1, 10.0], "revenue_ttm": [100.0] * 4, "analysts": [5, 5, 5, 1]},
                      index=["units", "basis", "low base", "few analysts"])
    (_, units, drop_units), (_, basis, drop_basis) = crosscheck.consensus(df)
    assert list(df.index[units]) == ["units"] and drop_units  # 25x a 1.0 EPS on a 10% margin; "low base": 0.1%
    assert list(df.index[basis]) == ["basis", "low base"] and not drop_basis  # under 3 analysts: skipped


def test_drift_alarms_against_the_previous_snapshot(monkeypatch, tmp_path):
    prev = pd.DataFrame({"code": list("ABCDE"), "price": 10.0, "mcap": 1000.0, "shares": 100.0, "bps": 5.0,
                         "np_ttm": 50.0, "period": "2026-06-30", "eps_e2": 1.0, "fv_mid": 12.0, "price_date": "2026-10-16"})
    (tmp_path / "snapshots" / "2026-10-18").mkdir(parents=True)
    prev.to_csv(tmp_path / "snapshots" / "2026-10-18" / "cn.csv.gz", index=False, compression="gzip")
    now = prev.set_index("code").assign(price_date="2026-10-19", e1_year="2026")
    now.loc["A", "mcap"] = 2000.0  # market value doubled on a flat return: the share count changed
    now.loc["B", "np_ttm"] = 60.0  # profit moved without a new report
    now.loc["C", ["np_ttm", "period"]] = [80.0, "2026-09-30"]  # a new report: no alarm
    now.loc["D", "eps_e2"] = 1.5
    now.loc["E", "fv_mid"] = 18.0
    monkeypatch.setattr(crosscheck, "DATA", tmp_path)
    monkeypatch.setattr(crosscheck, "returns", lambda market, start, end: pd.Series(1.0, index=list("ABCDE")))
    line = crosscheck.drift(now, "cn", date(2026, 10, 19))[0]
    assert line.startswith("Drift alarms since 2026-10-18 (5 stocks in both")
    assert ("price vs the stock's return (a split?) 0, market value vs the stock's return 1, "
            "TTM profit without a new report 1, book without a new report 0, "
            "next year's consensus EPS 1, fair value with a flat price 1") in line
