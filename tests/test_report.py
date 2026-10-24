"""End-to-end dry run: a saved CN universe (the 400 largest, 2026-10-24) -> score -> lists -> lists CSV -> PDF + text
summary + data/picks.csv, with one recorded holding, one of your vetoes and HK's lists only from the day before."""

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
    (tmp_path / "expect.json").write_text(json.dumps({"cn": {
        "first": "2019-01", "last": "2025-09", "windows": 81, "fund_drawdown": -0.365, "portfolios": {
            n: {"excess": 0.025, "beat": 0.63, "worst": -0.18, "worst_fund": -0.20, "worst_excess": -0.28, "drawdown": -0.23}
            for n in ("20", "10", "5")}}}), encoding="utf-8")

    out = lists.build(scored, "cn", DAY, {})
    folder = tmp_path / "reports" / DAY.isoformat()
    folder.mkdir(parents=True)
    out.to_csv(folder / "cn_lists.csv", index=False)
    (tmp_path / "reports" / "2026-10-23").mkdir()
    out.to_csv(tmp_path / "reports" / "2026-10-23" / "hk_lists.csv", index=False)
    report.save_failed(DAY, "cn", ["prices"])
    pdf, summary = report.build(DAY)

    buys, avoid = out[out["list"] == "buy"], out[out["list"] == "avoid"]
    assert len(buys) == 20 and buys["sector"].value_counts().max() <= 2 and (buys["score_rank"] < 300).all()
    assert len(avoid) == 10 and avoid["sector"].value_counts().max() <= 2
    assert top not in set(buys["code"]) and out.loc[out["list"] == "veto", "code"].tolist() == [top]
    held = out[out["list"] == "holding"].iloc[0]
    assert held["code"] == "600519" and held["status"] in ("继续持有", "卖出") and held["since"] == "2025-06-30"
    assert (buys["lot_cost"] == buys["price"] * 100).all() and (buys["recheck"] == "2027-10-24").all()

    lines = summary.splitlines()
    assert lines[0] == "股票报告 2026-10-24" and len(summary.encode("utf-8")) <= 4000
    cn = summary.split("【A股 CN】")[1].split("【港股 HK】")[0]
    assert "预期：模拟回测（2019-01 至 2025-09 每月建仓的 81 个 12 个月" in cn and "多赚 2.5%" in cn
    assert "注意：今日部分数据获取失败（prices）" in cn and "持仓检查：" in cn and "回避：" in cn
    assert len([x for x in cn.splitlines() if re.match(r"\d+\. ", x)]) == 10  # the top 10 buys
    assert "注意：今日未能更新，沿用 2026-10-23 的名单" in summary.split("【港股 HK】")[1]
    assert "历史模拟尚未运行。" in summary.split("【港股 HK】")[1]
    html = (folder / "report.html").read_text(encoding="utf-8")
    assert "你的否决（至 2026-12-31）：测试否决" in html and html.count('class="card"') == 40  # CN and HK buys
    assert pdf.stat().st_size > 10_000 and report.newest() == ("2026-10-24", pdf, summary)
    logged = track.load()
    assert len(logged) == 30 and set(logged["bucket"]) == {"buy", "avoid"} and logged["score"].notna().all()
