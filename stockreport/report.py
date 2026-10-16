"""The report: each market's picks with notes and swaps -> reports/<date>/report.pdf and summary.txt
(PLAN.md Method sections 7 and 9). Markets without a picks CSV for the day are left out."""

from datetime import date
from pathlib import Path

import pandas as pd

from stockreport import deliver
from stockreport.cleanup import size_of
from stockreport.config import CONFIG, DATA, REPORTS
from stockreport.notes import FLAG_WORDS, annotate
from stockreport.render import html_to_pdf, render_html, text_summary

MARKETS = [("us", "美股 US", "USD"), ("hk", "港股 HK", "HKD"), ("cn", "A股 CN", "CNY")]  # PDF order
METHOD = ("各市场取市值前 800（剔除 ST、上市不满 1 年和成交过少的股票），在行业同业组内估值：盈利公司看同业为同等 "
          "ROE 和增长支付的 P/B，并与按分析师一致预期 EPS 的远期 P/E 各占一半；亏损公司用 P/S；银行、券商、保险用"
          "同业 P/B 与合理 P/B 各半。再按价值、质量、成长、动量、风险综合打分，每档取 5 只。")


def trigger(p: dict) -> str:
    """Rule-based re-check condition (PLAN.md Method section 7)."""
    lo, hi = CONFIG["buckets"]["hold_upside"]
    if p["bucket"] == "buy":
        return f"股价跌破公允价下限 {p['fv_low']:,.2f}，或下季净利润同比转负时复查"
    if p["bucket"] == "hold":
        return (f"股价低于 {p['fv_mid'] / (1 + hi):,.2f}（空间超过 {hi:+.0%}）"
                f"或高于 {p['fv_mid'] / (1 + lo):,.2f}（空间低于 {lo:+.0%}）时复查")
    return f"股价回落到 {p['fv_mid'] / (1 + lo):,.2f} 以下（空间回到 {lo:+.0%} 以内），或净利润转为增长时复查"


def card(p: dict) -> dict:
    return {"ticker": p["code"], "name": p["name"], "bucket": p["bucket"], "action": p["action"],
            "price": p["price"], "price_date": p["price_date"], "fv_low": p["fv_low"], "fv_mid": p["fv_mid"],
            "fv_high": p["fv_high"], "upside": p["upside"], "drivers": str(p["drivers"]).split("；"),
            "risk": p["key_risk"], "ai_risk": p["ai_risk"], "note": p["note"], "trigger": trigger(p),
            "low_conviction": p["conviction"] == "低信心", "flag": FLAG_WORDS.get(p["flag"])}


def build(today: date, use_ai: bool = True) -> tuple[Path, str]:
    """Write report.html/.pdf and summary.txt for the day; returns the PDF path and the summary."""
    out = REPORTS / today.isoformat()
    markets = []
    for code, name, currency in MARKETS:
        path = out / f"{code}_picks.csv"
        if not path.exists():
            continue
        final, swaps = annotate(pd.read_csv(path, dtype={"code": str, "price_date": str}), code, today, use_ai)
        for s in swaps:
            s["flag"] = FLAG_WORDS[s["flag"]]
        markets.append({"code": code.upper(), "name": name, "currency": currency, "r": final["r"].iloc[0],
                        "data_date": final["price_date"].max(), "swaps": swaps,
                        "ai_notes": int((final["note_source"] != "template").sum()),
                        "picks": [card(p) for p in final.to_dict("records")]})
    if not markets:
        raise SystemExit(f"no picks CSV in {out}; run `run --market cn` first")
    size_gb = (size_of(DATA) + size_of(REPORTS)) / 1e9
    report = {"title": "股票报告", "date": today.isoformat(), "markets": markets, "method": METHOD,
              "storage_warning": (f"注意：data/ + reports/ 已占用 {size_gb:.1f} GB，超过 "
                                  f"{CONFIG['storage']['warn_gb']} GB 上限。")
              if size_gb > CONFIG["storage"]["warn_gb"] else ""}
    pdf = html_to_pdf(render_html(report, out / "report.html"), out / "report.pdf")
    summary = text_summary(report, deliver.MAX_TEXT_BYTES)
    (out / "summary.txt").write_text(summary, encoding="utf-8")
    return pdf, summary


def newest() -> tuple[str, Path, str] | None:
    """(date, PDF, summary) of the newest complete report, or None."""
    for folder in sorted(REPORTS.glob("????-??-??"), reverse=True):
        pdf, summary = folder / "report.pdf", folder / "summary.txt"
        if pdf.exists() and summary.exists():
            return folder.name, pdf, summary.read_text(encoding="utf-8")
    return None
