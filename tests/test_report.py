"""End-to-end dry run: a saved CN universe (the 400 largest, 2026-10-24) -> score -> lists -> lists CSV -> PDF + text
summary + data/picks.csv, with one recorded holding, one of your vetoes, HK's lists only from the day before, and the
same lists as US's to check its index-fund core line."""

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport import lists, report, track, verdicts
from stockreport.score import score

SAMPLES = Path(__file__).parent / "data"
DAY = date(2026, 10, 24)


def test_report_dry_run(tmp_path, monkeypatch):
    for module, attr, path in ((lists, "HOLDINGS", "holdings.csv"), (verdicts, "PATH", "verdicts.csv"),
                               (track, "PICKS_LOG", "picks.csv"), (report, "REPORTS", "reports"),
                               (report, "EXPECT", "expect.json")):
        monkeypatch.setattr(module, attr, tmp_path / path)
    monkeypatch.setattr(verdicts, "periods", lambda m: pd.Series(dtype=str))
    df = pd.read_csv(SAMPLES / "cn_universe_sample.csv", dtype={"code": str, "period": str}).set_index("code")
    scored = score(df, "cn", df[["deduct_ttm", "sue"]])
    top = scored[scored["mcap_rank"] <= 300].sort_values("score", ascending=False).index[0]
    verdicts.add(top, "veto", "2026-12-31", "测试否决", DAY)
    lists.hold("600519", "2025-06-30", False, DAY)
    run = {"first": "2019-01", "last": "2025-09", "windows": 81, "fund_drawdown": -0.365, "portfolios": {
        n: {"excess": 0.025, "beat": 0.63, "worst": -0.18, "worst_fund": -0.20, "worst_excess": -0.28, "drawdown": -0.23}
        for n in ("20", "10", "5")}}
    core = {"share": 0.5, "excess": -0.015, "beat": 0.24, "worst": -0.115, "worst_fund": -0.155, "worst_excess": -0.10,
            "drawdown": -0.217}
    (tmp_path / "expect.json").write_text(json.dumps({"cn": run, "us": run | {"core": core}}), encoding="utf-8")

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
    assert len(buys) == 20 and buys["sector"].value_counts().max() <= 2 and (buys["score_rank"] < 300).all()
    assert len(avoid) == 10 and avoid["sector"].value_counts().max() <= 2
    assert top not in set(buys["code"]) and out.loc[out["list"] == "veto", "code"].tolist() == [top]
    held = out[out["list"] == "holding"].iloc[0]
    assert held["code"] == "600519" and held["since"] == "2025-06-30" and held["recheck"] in ("2026-10-24", "2027-06-30")
    assert held["status"] in ("继续持有", "复核")  # its anniversary passed in June: a new year, judged by the in-year rule
    assert (buys["lot_cost"] == buys["price"] * 100).all() and (buys["recheck"] == "2027-10-24").all()

    lines = summary.splitlines()
    assert lines[0] == "股票报告 2026-10-24" and len(summary.encode("utf-8")) <= 4000
    cn = summary.split("【A股 CN】")[1].split("【美股 US】")[0]
    assert "预期：模拟回测（2019-01 至 2025-09 每月建仓的 81 个 12 个月" in cn and "多赚 2.5%" in cn
    assert "注意：今日部分数据获取失败（prices）" in cn and "持仓检查：" in cn and "回避：" in cn
    assert len([x for x in cn.splitlines() if re.match(r"\d+\. ", x)]) == 10  # the top 10 buys
    assert "注意：今日未能更新，沿用 2026-10-23 的名单" in summary.split("【港股 HK】")[1]
    assert "历史模拟尚未运行。" in summary.split("【港股 HK】")[1]
    html = (folder / "report.html").read_text(encoding="utf-8")
    assert "你的否决（至 2026-12-31）：测试否决" in html and html.count('class="card"') == 60  # CN, US and HK buys
    us = summary.split("【美股 US】")[1].split("【港股 HK】")[0]
    assert "建议配置：50% 的资金买标普500指数基金" in us and "其余 50% 等额买下面 20 只（每只约 2.5%）" in us
    assert "预期：模拟回测（2019-01 至 2025-09 每月建仓的 81 个 12 个月，扣交易成本）：50% 指数基金" in us and "少赚 1.5%" in us
    assert "这样配置也跑输了基金" in us
    assert "建议配置" not in cn and "只买 20 只：" in html
    assert pdf.stat().st_size > 10_000 and report.newest() == ("2026-10-24", pdf, summary)
    logged = track.load()
    assert len(logged) == 60 and set(logged["market"]) == {"cn", "us"}  # today's lists only (HK's are from the day before)
    assert set(logged["bucket"]) == {"buy", "avoid"} and logged["score"].notna().all()
