"""End-to-end dry run: a saved CN universe (the 400 largest, 2026-10-24, without free-float values: sector places by
market value) -> score -> the three ratings -> lists CSV -> PDF + text summary + data/picks.csv, with one of your
vetoes, HK's lists only from the day before, and the same lists as US's (no index-core advice anywhere); then the same day built again with a results review that found a hard red flag
on the top buy and a soft concern on a Hold name."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stockreport import deliver, lists, report, track, verdicts
from stockreport.render import text_summary
from stockreport.render.testdata import test_report as fake_report
from stockreport.score import score

SAMPLES = Path(__file__).parent / "data"
DAY = date(2026, 10, 24)


def test_report_dry_run(tmp_path, monkeypatch):
    for module, attr, path in ((verdicts, "PATH", "verdicts.csv"),
                               (track, "PICKS_LOG", "picks.csv"), (track, "SENT_LOG", "sent.csv"),
                               (track, "COHORTS", "cohorts.csv.gz"), (track, "MARKS", "marks.csv"),
                               (report, "REPORTS", "reports"),
                               (report, "EXPECT", "expect.json")):
        monkeypatch.setattr(module, attr, tmp_path / path)
    monkeypatch.setattr(report, "date", type("Day", (date,), {"today": staticmethod(lambda: DAY)}))  # built on its day
    monkeypatch.setattr(verdicts, "periods", lambda m: pd.Series(dtype=str))
    df = pd.read_csv(SAMPLES / "cn_universe_sample.csv", dtype={"code": str, "period": str}).set_index("code")
    scored = score(df, "cn", df[["deduct_ttm", "sue"]])
    top = scored.sort_values("score", ascending=False).index[0]
    verdicts.add(top, "veto", "2026-12-31", "测试否决", DAY)
    fell = {"fall_median": -0.12, "fall_fund_median": -0.10, "fall_worst": -0.30, "fall_worst_fund": -0.28}
    run = {"first": "2019-01", "last": "2025-09", "windows": 81, "fund_drawdown": -0.365, "portfolios": {
        n: {"excess": 0.025, "beat": 0.63, "worst": -0.18, "worst_fund": -0.20, "worst_excess": -0.28, "drawdown": -0.23} | fell
        for n in ("20", "10", "5")}, "ratings": {
        "hold": {"excess": -0.004, "beat": 0.48, "half": 0.06, "vol": 0.15, "fund_vol": 0.2, "drawdown": -0.2} | fell,
        "sell": {"excess": -0.04, "beat": 0.3, "mean": 0.02, "fund_mean": 0.06, "vol": 0.3, "fund_vol": 0.2, "drawdown": -0.5}
        | fell}, "neutral": {"excess": 0.03, "picks": -0.005, "picks_beat": 0.4}}
    (tmp_path / "expect.json").write_text(json.dumps({"cn": run, "us": run}), encoding="utf-8")

    out = lists.build(scored, "cn", DAY)
    folder = tmp_path / "reports" / DAY.isoformat()
    folder.mkdir(parents=True)
    out.to_csv(folder / "cn_lists.csv", index=False)
    out.to_csv(folder / "us_lists.csv", index=False)
    (tmp_path / "reports" / "2026-10-23").mkdir()
    out.to_csv(tmp_path / "reports" / "2026-10-23" / "hk_lists.csv", index=False)
    report.save_failed(DAY, "cn", ["prices"])
    pdf, summary, sent = report.build(DAY)

    buys, sell, hold = (out[out["list"] == k] for k in ("buy", "sell", "hold"))
    field = scored.drop(index=top)[~lists.screened(scored.drop(index=top))]  # the whole scored market, screened
    places = lists.slots(scored.groupby("sector")["mcap"].sum(), 20, field["sector"].value_counts())
    assert len(buys) == 20 and buys["sector"].value_counts().to_dict() == places[places > 0].to_dict()  # the market's mix
    for sector, k in places[places > 0].items():  # each sector's best scores
        assert set(buys.loc[buys["sector"] == sector, "code"]) == set(field[field["sector"] == sector].nlargest(k, "score").index)
    assert (buys["weight"] == 0.05).all() and buys["score"].is_monotonic_decreasing  # equal amounts
    assert len(sell) == 10 and sell["sector"].value_counts().max() <= 2 and len(hold) == 10
    assert set(sell["code"]) == set(lists.sells(scored, 10).index)
    assert set(out.loc[out["list"].isin(["hold", "hold_next"]), "code"]).isdisjoint(out.loc[out["list"].isin(["buy", "next"]), "code"])
    assert top not in set(buys["code"]) and out.loc[out["list"] == "veto", "code"].tolist() == [top]
    assert (buys["lot_cost"] == buys["price"] * 100).all() and (out.loc[out["list"] != "veto", "recheck"] == "2027-10-24").all()

    lines = summary.splitlines()
    assert lines[0] == "股票报告 2026-10-24" and len(summary.encode("utf-8")) <= 4000 and "已截断" not in summary
    assert lines[1].startswith("评级：买入 = 预计跑赢大盘；持有 = 评分居中、不偏涨也不偏跌")  # the three ratings first
    cn = summary.split("【A股】")[1].split("【美股】")[0]
    assert "预期：历史模拟（简化版）：买入平均每年比沪深300ETF多赚 2.5%" in cn and "买入 20 只，每只等额，持有到 2027-10-24" in cn
    assert "基金同期 -20%）。持有少赚 0.4%、波动小于基金；卖出 70% 的时候跑输、平均少赚 4.0%。" in cn
    assert "注意：今日部分数据获取失败（prices）" in cn and "持有 10 只：" + "、".join(hold["name"]) in cn
    assert "卖出 10 只：" + "、".join(sell["name"]) in cn and cn.splitlines()[2].count("、") == 19  # the 20 buys by name
    hk = summary.split("【港股】")[1]
    assert "注意：今日未能更新，沿用 2026-10-23 的名单" in hk and "历史模拟尚未运行。" in hk and "卖出 10 只：" in hk
    html = (folder / "report.html").read_text(encoding="utf-8")
    assert "你的否决（至 2026-12-31）：测试否决" in html and html.count('class="card buy"') == 60  # CN, US and HK buys
    assert html.count('class="card hold"') == 30 and html.count('class="card sell"') == 30
    assert not any(w in html + summary for w in ("持仓检查", "持有建议", "复核", "继续持有", "回避"))
    assert html.index("今天要做什么") < html.index('class="card buy"') < html.index("附：方法、依据和审核规则")
    us = summary.split("【美股】")[1].split("【港股】")[0]
    assert "预期：历史模拟（简化版）：买入平均每年比标普500基金多赚 2.5%" in us and f"{buys.iloc[0]['code']} " in us
    assert "从美股市值前 800 只里选" in html
    assert "一般 12%（沪深300ETF 10%），最差 30%（沪深300ETF同期 28%）" in html  # each held year's own fall
    assert "对照组合用同样的行业名额" in html and "20 只又比对照组合少赚 0.5%" in html  # the neutral basket, back pages
    need = buys["lot_cost"].max() / 0.05  # one lot of every buy at equal amounts: the dearest lot over its 5%
    assert f"买齐这 20 只约需 {need / 1e4:,.1f} 万元" in html
    assert not any(w in summary + html for w in ("建议配置", "指数基金", "标普500指数基金", "只买 20 只", "指数权重", "从标普500"))
    assert pdf.stat().st_size > 10_000 and report.newest() == ("2026-10-24", pdf, summary)
    assert sent["ticker"].tolist() == buys["code"].tolist() * 3  # what this text names, in its order
    track.log_sent(DAY, sent)
    track.log_sent(DAY, sent)  # a second reply the same day adds nothing new
    assert len(track.load_sent()) == 60 and set(track.load_sent()["market"]) == {"cn", "us", "hk"}
    assert set(track.load_sent().loc[track.load_sent()["market"] == "hk", "listed"]) == {"2026-10-23"}
    logged = track.load()
    assert len(logged) == 80 and set(logged["market"]) == {"cn", "us"}  # today's lists only (HK's are from the day before)
    assert set(logged["bucket"]) == {"buy", "hold", "sell"} and logged["score"].notna().all()

    first, steady = buys.iloc[0]["code"], hold.iloc[0]["code"]
    hard = {"kind": "investigation", "words": "监管立案调查或欺诈认定", "hard": True, "quote": "关于公司收到立案告知书的公告",
            "date": "2026-10-20", "type": "公告"}
    soft = hard | {"kind": "downturn", "words": "行业下行或产品价格下跌", "hard": False, "quote": "白酒批价下跌", "type": "新闻"}
    states = {"cn": {first: {"status": "done", "findings": [hard], "note": "测试点评"},
                     steady: {"status": "done", "findings": [soft], "note": ""}},
              "us": {first: {"status": "pending"}}}
    pdf, summary, _ = report.build(DAY, states)
    assert summary.splitlines()[2].startswith("审核剔除：A股 ") and "（监管立案调查或欺诈认定）→ " in summary
    assert "审核进行中 1 只" in summary.split("【美股】")[1].split("【港股】")[0]
    html = (folder / "report.html").read_text(encoding="utf-8")
    assert "1 只，由同行业的下一名替补" in html and "关于公司收到立案告知书的公告" in html and "AI 点评：测试点评" not in html
    assert "市场可能在担心：行业下行或产品价格下跌" in html.split('class="card hold"')[1]  # annotated, still a Hold
    assert html.count('class="card buy"') == 60  # 20 buys a market: the next name took the removed one's place
    logged = track.load()
    assert logged.loc[(logged["market"] == "cn") & (logged["bucket"] == "removed"), "ticker"].tolist() == [first]
    stand_in = logged.loc[(logged["market"] == "cn") & (logged["bucket"] == "replacement"), "ticker"].tolist()
    assert len(stand_in) == 1 and stand_in[0] in set(logged.loc[logged["bucket"] == "buy", "ticker"])
    assert f"由 {logged.loc[logged['ticker'] == stand_in[0], 'name'].iloc[0]} 替补" in html  # named as its card names it
    assert first not in set(logged.loc[(logged["market"] == "cn") & (logged["bucket"] == "buy"), "ticker"])


def test_summary_fits():
    """A full three-market summary (20 Buy, 10 Hold and 10 Sell names, a removed buy, 预期 with all three) fits under
    WeChat's 4,000 bytes without cutting a line, with every market's buys by name and its Hold, Sell and 预期 lines:
    with every US name long and in English (the worst case: Hold and Sell then go by count), and with US names in
    Chinese as Eastmoney gives them, when every Hold and Sell name is shown."""
    worst, usual = fake_report(DAY), fake_report(DAY)
    for k in ("buys", "holds", "sells", "removed"):
        for p in usual["markets"][1][k]:
            p["short"] = f"{p['ticker']} 测试美股"
    for report_ in (worst, usual):
        summary = text_summary(report_, deliver.MAX_TEXT_BYTES)
        assert len(summary.encode("utf-8")) <= deliver.MAX_TEXT_BYTES and "已截断" not in summary
        for market in ("【A股】", "【美股】", "【港股】"):
            part = summary.split(market)[1].split("\n\n")[0]
            assert part.splitlines()[1].count("、") == 19 and "持有 10 只" in part and "卖出 10 只" in part and "预期：" in part
            if report_ is usual and market != "【美股】":
                assert "持有 10 只：" in part and "卖出 10 只：" in part
        assert summary.splitlines()[-1].startswith("每家公司做什么") and "审核剔除：A股 " in summary


def test_live_line_leaves_out_missing_figures():
    """A group without a value that month (every name unresolved) drops out of the line; nothing half-written."""
    cohorts = pd.DataFrame({"market": ["hk"], "cohort": ["2026-11-07"]})
    t = pd.DataFrame({"cohort": ["2026-11-07"], "start": ["2026-11-09"], "mark": ["2026-12-31"], "months": [1.7],
                      "buy": [0.03], "hold": [float("nan")], "sell": [-0.03], "basket": [0.01], "fund": [0.005]})
    line = report.live_line("hk", cohorts, t, 1)
    assert "持有比" not in line and "、。" not in line and "比对照组合多赚 2.0%" in line and "停牌或退市的 1 只" in line
    assert report.live_line("hk", cohorts, t.assign(buy=float("nan"), sell=float("nan")), 0) == ""
    assert "第一个月末之后" in report.live_line("hk", cohorts, pd.DataFrame(), 0)
