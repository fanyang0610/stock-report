"""The report: each market's picks with notes and swaps -> reports/<date>/report.pdf and summary.txt
(PLAN.md Method sections 7, 9 and 10). A market without a picks CSV for the day shows its newest
earlier one, marked as such; the final picks of the day go to data/picks.csv for `track`."""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport import deliver, track
from stockreport.cleanup import size_of
from stockreport.config import CONFIG, DATA, REPORTS
from stockreport.fetch import eastmoney
from stockreport.notes import FLAG_WORDS, annotate
from stockreport.render import html_to_pdf, render_html, text_summary

MARKETS = {"us": ("美股 US", "USD"), "hk": ("港股 HK", "HKD"), "cn": ("A股 CN", "CNY")}  # PDF order
# An issuer picked in two markets keeps the listing first in this order and is swapped out of the
# other (PLAN.md Method 6): the A-share is the primary listing of an A/H issuer, and the US-listed
# China ADRs listed in New York first (their HK lines are mostly secondary listings).
PRIORITY = ["cn", "us", "hk"]
METHOD = ("各市场取市值前 800（剔除 ST、上市不满 1 年和成交过少的股票），在行业同业组内估值：盈利公司看同业为同等 "
          "ROE 和增长支付的 P/B（银行、券商、保险只看 ROE），并与按分析师一致预期 EPS 的远期 P/E 各占一半；净资产为负时只用远期 P/E；"
          "亏损公司用 P/S。再按价值、质量、成长、动量、风险综合打分，每档取 5 只。")


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


def issuers() -> dict[str, pd.Series]:
    """Ticker -> Eastmoney org code per market: one id for every listing of the same issuer."""
    paths = {"cn": DATA / "quotes" / "cn.csv.gz", "us": eastmoney.US_ORGS, "hk": eastmoney.HK_LIST}
    read = lambda p: pd.read_csv(p, usecols=["code", "org_code"], dtype=str).drop_duplicates("code").set_index("code")["org_code"]
    return {m: read(p) if p.exists() else pd.Series(dtype=str) for m, p in paths.items()}


def save_failed(today: date, market: str, failed: list[str]) -> None:
    """Remember a market's failed fetch steps for the day's report (an empty list clears them)."""
    path = REPORTS / today.isoformat() / "fetch_failed.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state | {market: failed}, ensure_ascii=False), encoding="utf-8")


def latest_picks(market: str, today: date) -> Path | None:
    """Today's picks CSV for the market, else the newest earlier one."""
    found = [p for p in sorted(REPORTS.glob(f"????-??-??/{market}_picks.csv")) if p.parent.name <= today.isoformat()]
    return found[-1] if found else None


def build(today: date, use_ai: bool = True) -> tuple[Path, str]:
    """Write report.html/.pdf and summary.txt for the day; returns the PDF path and the summary."""
    out, orgs, kept, done, logged = REPORTS / today.isoformat(), issuers(), {}, {}, {}
    status = out / "fetch_failed.json"
    failed = json.loads(status.read_text(encoding="utf-8")) if status.exists() else {}
    for code in PRIORITY:
        path = latest_picks(code, today)
        if not path:
            continue
        day = date.fromisoformat(path.parent.name)
        picks = pd.read_csv(path, dtype={"code": str, "price_date": str})
        org = picks["code"].map(orgs[code])
        taken = {c: f"同一发行人已在{kept[o]}入选" for c, o in zip(picks["code"], org) if o in kept}
        final, swaps = annotate(picks, code, day, use_ai, taken)
        if day == today:
            logged[code] = final
        final_org = final["code"].map(orgs[code])
        kept |= {o: f" {MARKETS[code][0]}（{c} {n}）" for o, c, n in zip(final_org, final["code"], final["name"]) if pd.notna(o)}
        for s in swaps:
            s["ai"], s["flag"] = s["flag"] != "dual_listed", FLAG_WORDS[s["flag"]]
        done[code] = {"code": code.upper(), "name": MARKETS[code][0], "currency": MARKETS[code][1],
                      "r": final["r"].iloc[0], "data_date": final["price_date"].max(), "swaps": swaps,
                      "ai_notes": int((final["note_source"] != "template").sum()),
                      "stale": (f"今日未能更新，沿用 {day} 的选股" if day != today else
                                f"今日部分数据获取失败（{'、'.join(failed[code])}），沿用上次的缓存数据" if failed.get(code) else ""),
                      "picks": [card(p) for p in final.to_dict("records")]}
    markets = [done[code] for code in MARKETS if code in done]
    if not markets:
        raise SystemExit(f"no picks CSV in {REPORTS}; run `run` first")
    if logged:
        track.log_picks(today, logged)
    size_gb = (size_of(DATA) + size_of(REPORTS)) / 1e9
    report = {"title": "股票报告", "date": today.isoformat(), "markets": markets, "method": METHOD,
              "storage_warning": (f"注意：data/ + reports/ 已占用 {size_gb:.1f} GB，超过 "
                                  f"{CONFIG['storage']['warn_gb']} GB 上限。")
              if size_gb > CONFIG["storage"]["warn_gb"] else ""}
    out.mkdir(parents=True, exist_ok=True)
    pdf = html_to_pdf(render_html(report, out / "report.html"), out / "report.tmp.pdf").replace(out / "report.pdf")
    summary = text_summary(report, deliver.MAX_TEXT_BYTES)
    (out / "summary.tmp").write_text(summary, encoding="utf-8")
    (out / "summary.tmp").replace(out / "summary.txt")  # the listener may send the report at any moment
    return pdf, summary


def newest() -> tuple[str, Path, str] | None:
    """(date, PDF, summary) of the newest complete report, or None."""
    for folder in sorted(REPORTS.glob("????-??-??"), reverse=True):
        pdf, summary = folder / "report.pdf", folder / "summary.txt"
        if pdf.exists() and summary.exists():
            return folder.name, pdf, summary.read_text(encoding="utf-8")
    return None
