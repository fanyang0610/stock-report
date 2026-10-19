"""End-to-end dry run: picks CSV -> notes (one flagged pick, no network) -> PDF + text summary + data/picks.csv.
The picks sample is from before the bucket rename (持有/不追高, 卖出/回避): the report shows the new names."""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport import notes, report, track, verdicts
from stockreport.pick import CSV_COLUMNS, pick
from stockreport.score import score
from stockreport.value import value

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
    assert len([x for x in lines if " 持有 " in x]) == 5
    assert len([x for x in lines if " 卖出 " in x]) == 5
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
    assert "603259" not in hk and "600061 国投资本 持有" in hk  # the next HK hold moves up
    assert "其他市场已入选、不重复列出：药明康德" in hk and "AI 标记后替换：江波龙" in hk
    assert "603259 药明康德 持有" in cn and "其他市场已入选" not in cn
    assert "同一发行人已在 A股 CN（603259 药明康德）入选" in (tmp_path / DAY.isoformat() / "report.html").read_text(encoding="utf-8")


def test_no_notes_run_still_applies_checks_1_2(tmp_path, monkeypatch):
    # A picks CSV as `run` writes it today (CN sample), and no DeepSeek at all: 寒武纪 and 中微公司 (profit
    # +123% / +300% on cash conversion 0.13 / 0.17) never reach the report's picks and are listed instead.
    scored = score(value(pd.read_csv(SAMPLES / "cn_sample.csv", dtype={"code": str}).set_index("code"), 0.0765))
    folder = tmp_path / DAY.isoformat()
    folder.mkdir()
    pick(scored).assign(r=0.0765, price_date="2026-10-16").reindex(columns=CSV_COLUMNS).to_csv(
        folder / "cn_picks.csv", index=False, encoding="utf-8-sig")
    monkeypatch.setattr(report, "REPORTS", tmp_path)
    monkeypatch.setattr(track, "PICKS_LOG", tmp_path / "picks.csv")
    monkeypatch.setattr(report, "issuers", lambda: {m: pd.Series(dtype=str) for m in ("cn", "hk", "us")})
    pdf, summary = report.build(DAY, use_ai=False)
    lines = summary.splitlines()
    for label in ("买入", "持有", "卖出"):
        assert len([x for x in lines if f" {label} " in x]) == 5
    assert "利润异常已剔除：寒武纪、中微公司" in lines and "688256" not in summary and "688012" not in summary
    html = (folder / "report.html").read_text(encoding="utf-8")
    assert "利润异常已剔除（2）" in html and "688012 中微公司（持有候选）" in html
    assert set(track.load()["ticker"]).isdisjoint({"688256", "688012"})


def test_deep_dives_and_verdicts_reach_the_report(tmp_path, monkeypatch):
    """A deep-dive veto swaps 中信建投 out of the holds, a 低信心 result marks 沪硅产业, your veto swaps 珀莱雅 and your
    confirm lifts 荣昌生物's 低信心; the cards carry the 深度核查 and 近期事件 lines."""
    folder = tmp_path / DAY.isoformat()
    folder.mkdir()
    line = "深度核查（2026年半年度报告，2026-08-20）：非经常性损益占同期归母净利润 45%（2/2 条引文已核实）"
    (folder / "cn_deepdive.json").write_text(json.dumps({"fresh": ["601066", "688126"], "results": {
        "601066": {"name": "中信建投", "trigger": "测试", "filing": "cn-1", "line": line, "action": "veto",
                   "reason": "深度核查：非经常性损益占同期净利润 45%"},
        "688126": {"name": "沪硅产业", "trigger": "测试", "filing": "cn-2", "line": "深度核查（x，2026-08-20）：测试",
                   "action": "low", "reason": "深度核查：测试"}}}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(verdicts, "PATH", tmp_path / "verdicts.csv")
    monkeypatch.setattr(verdicts, "periods", lambda m: pd.Series(dtype=str))
    verdicts.add("603605", "veto", "2026-12-31", "测试否决", DAY)
    verdicts.add("688331", "confirm", "2026-12-31", "测试确认", DAY)
    pdf, summary = build(tmp_path, monkeypatch, ["cn"])
    lines = summary.splitlines()
    assert "深度核查或人工否决后替换：中信建投、珀莱雅" in lines
    assert not any(x.startswith(("601066", "603605")) for x in lines) and any(x.startswith("600061 国投资本 持有") for x in lines)
    assert any(x.startswith("688126 沪硅产业 卖出") and x.endswith("低信心") for x in lines)
    assert any(x.startswith("688331 荣昌生物 买入") and not x.endswith("低信心") for x in lines)
    html = (folder / "report.html").read_text(encoding="utf-8")
    assert "深度核查否决" in html and "人工否决" in html and "你的否决（至 2026-12-31）：测试否决" in html
    assert html.count("<span class=\"label\">近期事件：</span>") == 15 and "测试</span>" not in html and "深度核查（x，2026-08-20）：</span>测试" in html
