"""End-to-end dry run: picks CSV -> notes (one flagged pick, no network) -> PDF + text summary."""

import json
from datetime import date
from pathlib import Path

from stockreport import notes, report

SAMPLES = Path(__file__).parent / "data"


def test_report_dry_run(tmp_path, monkeypatch):
    day = date(2026, 10, 17)
    folder = tmp_path / day.isoformat()
    folder.mkdir()
    (folder / "cn_picks.csv").write_bytes((SAMPLES / "cn_picks_sample.csv").read_bytes())
    monkeypatch.setattr(report, "REPORTS", tmp_path)
    monkeypatch.setattr(notes, "REPORTS", tmp_path)
    monkeypatch.setattr(notes.cninfo, "org_ids", lambda: {})

    def fake_fetch(self, row, titles):  # stands in for DeepSeek: flags 江波龙 and nothing else
        flag = "one_off_gain" if row["code"] == "301308" else "none"
        return {"note": f"{row['name']}测试点评。", "risk": "测试风险", "flag": flag, "reason": "测试", "source": "test"}

    monkeypatch.setattr(notes.Notes, "fetch", fake_fetch)
    pdf, summary = report.build(day, use_ai=True)

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
    saved = json.loads((folder / "cn_notes.json").read_text(encoding="utf-8"))
    assert saved["301308"]["flag"] == "one_off_gain" and saved["000792"]["flag"] == "none"
