"""End-to-end dry run: picks CSV -> notes (one flagged pick, no network) -> PDF + text summary + data/picks.csv."""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport import notes, report, track

SAMPLES = Path(__file__).parent / "data"
DAY = date(2026, 10, 17)


def build(tmp_path, monkeypatch, markets: list[str]):
    """report.build on the CN picks sample, saved as each market's picks file."""
    folder = tmp_path / DAY.isoformat()
    folder.mkdir(exist_ok=True)
    for market in markets:
        (folder / f"{market}_picks.csv").write_bytes((SAMPLES / "cn_picks_sample.csv").read_bytes())
    monkeypatch.setattr(report, "REPORTS", tmp_path)
    monkeypatch.setattr(notes, "REPORTS", tmp_path)
    monkeypatch.setattr(track, "PICKS_LOG", tmp_path / "picks.csv")
    for source in notes.TITLE_SOURCES.values():
        monkeypatch.setattr(source, "org_ids", lambda: {})

    def fake_fetch(self, row, titles):  # stands in for DeepSeek: flags 江波龙 and nothing else
        flag = "one_off_gain" if row["code"] == "301308" else "none"
        return {"note": f"{row['name']}测试点评。", "risk": "测试风险", "flag": flag, "reason": "测试", "source": "test"}

    monkeypatch.setattr(notes.Notes, "fetch", fake_fetch)
    return report.build(DAY, use_ai=True)


def test_report_dry_run(tmp_path, monkeypatch):
    pdf, summary = build(tmp_path, monkeypatch, ["cn"])
    assert pdf.stat().st_size > 10_000
    lines = summary.splitlines()
    assert lines[0] == "股票报告 2026-10-17"
    assert len([x for x in lines if " 买入 " in x]) == 5
    assert len([x for x in lines if " 持有/不追高 " in x]) == 5
    assert len([x for x in lines if " 卖出/回避 " in x]) == 5
    assert "301308" not in "".join(x for x in lines if " 买入 " in x)  # swapped out ...
    assert any(x.startswith("000792 盐湖股份 买入") for x in lines)   # ... for the first runner-up
    assert lines[-3] == "AI 标记后替换：江波龙"
    assert len(summary.encode("utf-8")) <= 4000
    assert report.newest() == ("2026-10-17", pdf, summary)
    saved = json.loads((tmp_path / DAY.isoformat() / "cn_notes.json").read_text(encoding="utf-8"))
    assert saved["301308"]["flag"] == "one_off_gain" and saved["000792"]["flag"] == "none"
    logged = track.load()
    assert len(logged) == 15 and "301308" not in set(logged["ticker"]) and "000792" in set(logged["ticker"])


def test_market_without_todays_picks_shows_its_last_ones(tmp_path, monkeypatch):
    # HK picks only from the day before, and a failed CN fetch step today: both are said in the report.
    earlier = tmp_path / "2026-10-16"
    earlier.mkdir()
    (earlier / "hk_picks.csv").write_bytes((SAMPLES / "cn_picks_sample.csv").read_bytes())
    monkeypatch.setattr(report, "REPORTS", tmp_path)
    report.save_failed(DAY, "cn", ["prices"])
    monkeypatch.setattr(report, "issuers", lambda: {m: pd.Series(dtype=str) for m in ("cn", "hk", "us")})
    pdf, summary = build(tmp_path, monkeypatch, ["cn"])
    assert "注意：今日未能更新，沿用 2026-10-16 的选股" in summary.split("港股 HK")[1].split("A股 CN")[0]
    assert "注意：今日部分数据获取失败（prices），沿用上次的缓存数据" in summary.split("A股 CN")[1]
    assert set(track.load()["market"]) == {"cn"}  # only today's picks are logged


def test_issuer_picked_in_two_markets_is_listed_once(tmp_path, monkeypatch):
    # 603259 stands for one issuer listed in CN and HK (same org code); the CN listing stays.
    same = pd.Series({"603259": "10001"})
    monkeypatch.setattr(report, "issuers", lambda: {"cn": same, "hk": same, "us": pd.Series(dtype=str)})
    pdf, summary = build(tmp_path, monkeypatch, ["cn", "hk"])
    hk, cn = summary.split("港股 HK")[1].split("A股 CN")
    assert "603259" not in hk and "600061 国投资本 持有/不追高" in hk  # the next HK hold moves up
    assert "其他市场已入选、不重复列出：药明康德" in hk and "AI 标记后替换：江波龙" in hk
    assert "603259 药明康德 持有/不追高" in cn and "其他市场已入选" not in cn
    assert "同一发行人已在 A股 CN（603259 药明康德）入选" in (tmp_path / DAY.isoformat() / "report.html").read_text(encoding="utf-8")
