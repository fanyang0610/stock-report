"""End-to-end dry run: a saved CN universe (the 400 largest, 2026-10-24, without free-float values: sector places by
market value) -> score -> lists -> lists CSV -> PDF + text summary + data/picks.csv, with one recorded
holding, one of your vetoes, HK's lists only from the day before, and the same lists as US's (no index-core advice
anywhere); then the same day built again with a results review that found a hard red flag on the top buy and a soft
concern on the holding."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stockreport import deepdive, deliver, lists, report, track, verdicts
from stockreport.render import text_summary
from stockreport.render.testdata import test_report as fake_report
from stockreport.score import score

SAMPLES = Path(__file__).parent / "data"
DAY = date(2026, 10, 24)


def test_report_dry_run(tmp_path, monkeypatch):
    for module, attr, path in ((lists, "HOLDINGS", "holdings.csv"), (verdicts, "PATH", "verdicts.csv"),
                               (track, "PICKS_LOG", "picks.csv"), (report, "REPORTS", "reports"),
                               (report, "EXPECT", "expect.json"), (deepdive, "CACHE", "deepdive")):
        monkeypatch.setattr(module, attr, tmp_path / path)
    monkeypatch.setattr(verdicts, "periods", lambda m: pd.Series(dtype=str))
    df = pd.read_csv(SAMPLES / "cn_universe_sample.csv", dtype={"code": str, "period": str}).set_index("code")
    scored = score(df, "cn", df[["deduct_ttm", "sue"]])
    top = scored.sort_values("score", ascending=False).index[0]
    verdicts.add(top, "veto", "2026-12-31", "测试否决", DAY)
    lists.hold("600519", "2025-06-30", False, DAY)
    run = {"first": "2019-01", "last": "2025-09", "windows": 81, "fund_drawdown": -0.365, "portfolios": {
        n: {"excess": 0.025, "beat": 0.63, "worst": -0.18, "worst_fund": -0.20, "worst_excess": -0.28, "drawdown": -0.23}
        for n in ("20", "10", "5")}}
    (tmp_path / "expect.json").write_text(json.dumps({"cn": run, "us": run}), encoding="utf-8")

    out = lists.build(scored, "cn", DAY, {})
    folder = tmp_path / "reports" / DAY.isoformat()
    folder.mkdir(parents=True)
    out.to_csv(folder / "cn_lists.csv", index=False)
    out.to_csv(folder / "us_lists.csv", index=False)
    (tmp_path / "reports" / "2026-10-23").mkdir()
    out.to_csv(tmp_path / "reports" / "2026-10-23" / "hk_lists.csv", index=False)
    report.save_failed(DAY, "cn", ["prices"])
    pdf, summary = report.build(DAY)

    buys, avoid = out[out["list"] == "buy"], out[out["list"] == "avoid"]
    field = scored.drop(index=top)[~lists.screened(scored.drop(index=top))]  # the whole scored market, screened
    places = lists.slots(scored.groupby("sector")["mcap"].sum(), 20, field["sector"].value_counts())
    assert len(buys) == 20 and buys["sector"].value_counts().to_dict() == places[places > 0].to_dict()  # the market's mix
    for sector, k in places[places > 0].items():  # each sector's best scores
        assert set(buys.loc[buys["sector"] == sector, "code"]) == set(field[field["sector"] == sector].nlargest(k, "score").index)
    assert (buys["weight"] == 0.05).all() and buys["score"].is_monotonic_decreasing  # equal amounts
    assert len(avoid) == 10 and avoid["sector"].value_counts().max() <= 2
    assert top not in set(buys["code"]) and out.loc[out["list"] == "veto", "code"].tolist() == [top]
    held = out[out["list"] == "holding"].iloc[0]
    assert held["code"] == "600519" and held["since"] == "2025-06-30" and held["recheck"] in ("2026-10-24", "2027-06-30")
    assert held["status"] in ("继续持有", "复核")  # its anniversary passed in June: a new year, judged by the in-year rule
    assert (buys["lot_cost"] == buys["price"] * 100).all() and (buys["recheck"] == "2027-10-24").all()

    lines = summary.splitlines()
    assert lines[0] == "股票报告 2026-10-24" and len(summary.encode("utf-8")) <= 4000 and "已截断" not in summary
    assert lines[2] == "今天要做的：" and lines[3].startswith("· 卖出：")  # the actions first
    cn = summary.split("【A股】")[1].split("【美股】")[0]
    assert "预期：历史模拟（简化版）平均每年比沪深300ETF多赚 2.5%" in cn and "买入 20 只，每只等额，持有到 2027-10-24" in cn
    assert "注意：今日部分数据获取失败（prices）" in cn and "回避：" in cn
    assert cn.splitlines()[2].count("、") == 19  # the 20 buys by name
    assert "注意：今日未能更新，沿用 2026-10-23 的名单" in summary.split("【港股】")[1]
    assert "历史模拟尚未运行。" in summary.split("【港股】")[1]
    html = (folder / "report.html").read_text(encoding="utf-8")
    assert "你的否决（至 2026-12-31）：测试否决" in html and html.count('class="card buy"') == 60  # CN, US and HK buys
    assert html.index("今天要做什么") < html.index('class="card buy"') < html.index("附：方法、依据和审核规则")
    us = summary.split("【美股】")[1].split("【港股】")[0]
    assert "预期：历史模拟（简化版）平均每年比标普500基金多赚 2.5%" in us and f"{buys.iloc[0]['code']} " in us
    assert "从美股市值前 800 只里选" in html
    assert not any(w in summary + html for w in ("建议配置", "指数基金", "标普500指数基金", "只买 20 只", "指数权重", "从标普500"))
    assert pdf.stat().st_size > 10_000 and report.newest() == ("2026-10-24", pdf, summary)
    logged = track.load()
    assert len(logged) == 60 and set(logged["market"]) == {"cn", "us"}  # today's lists only (HK's are from the day before)
    assert set(logged["bucket"]) == {"buy", "avoid"} and logged["score"].notna().all()

    first, holding = buys.iloc[0]["code"], held["code"]
    hard = {"kind": "investigation", "words": "监管立案调查或欺诈认定", "hard": True, "quote": "关于公司收到立案告知书的公告",
            "date": "2026-10-20", "type": "公告"}
    soft = hard | {"kind": "downturn", "words": "行业下行或产品价格下跌", "hard": False, "quote": "白酒批价下跌", "type": "新闻"}
    states = {"cn": {first: {"status": "done", "findings": [hard], "note": "测试点评"},
                     holding: {"status": "done", "findings": [soft], "note": ""}},
              "us": {first: {"status": "pending"}}}
    pdf, summary = report.build(DAY, states)
    cn = summary.split("【A股】")[1].split("【美股】")[0]
    assert "· 审核剔除：A股 " in summary and "（监管立案调查或欺诈认定）→ " in summary and "复核 1 只：贵州茅台" in cn
    assert "审核进行中 1 只" in summary.split("【美股】")[1].split("【港股】")[0]
    html = (folder / "report.html").read_text(encoding="utf-8")
    assert "1 只，由同行业下一名替补" in html and "关于公司收到立案告知书的公告" in html and "AI 点评：测试点评" not in html
    assert html.count('class="card buy"') == 60  # 20 buys a market: the next name took the removed one's place
    logged = track.load()
    assert logged.loc[(logged["market"] == "cn") & (logged["bucket"] == "removed"), "ticker"].tolist() == [first]
    stand_in = logged.loc[(logged["market"] == "cn") & (logged["bucket"] == "replacement"), "ticker"].tolist()
    assert len(stand_in) == 1 and stand_in[0] in set(logged.loc[logged["bucket"] == "buy", "ticker"])
    assert f"由 {logged.loc[logged['ticker'] == stand_in[0], 'name'].iloc[0]} 替补" in html  # named as its card names it
    assert first not in set(logged.loc[(logged["market"] == "cn") & (logged["bucket"] == "buy"), "ticker"])


def test_summary_fits():
    """A full three-market summary (20 buys, 10 avoid names, holdings to sell and re-check, a removed buy; every US name
    long and in English, the worst case) fits under WeChat's 4,000 bytes without cutting a line, with every market's
    buys, avoid names and 预期 line; so does an anniversary day with 12 holdings to sell in each market."""
    calm = fake_report(DAY)
    busy = fake_report(DAY)
    for m in busy["markets"]:
        m["sell"] = [h | {"status": "卖出"} for h in m["holdings"][:12]]
    for report_ in (calm, busy):
        summary = text_summary(report_, deliver.MAX_TEXT_BYTES)
        assert len(summary.encode("utf-8")) <= deliver.MAX_TEXT_BYTES and "已截断" not in summary
        for market in ("【A股】", "【美股】", "【港股】"):
            part = summary.split(market)[1].split("\n\n")[0]
            assert part.splitlines()[1].count("、") == 19 and "回避：" in part and "预期：" in part
        assert summary.splitlines()[-1].startswith("每家公司做什么") and "· 卖出：A股 " in summary
