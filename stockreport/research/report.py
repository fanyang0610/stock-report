"""Research stage 11, part 4: the report (`research CODE`; PLAN.md "What it delivers"). In order: the fact sheet (stage
9), the source lines (texts.py), the report's own results review (the review's prompt and rules on 90 days of filings,
30 of headlines and the latest periodic report's passages, so a hard red flag stops the rating as for a listed name),
the valuation (stage 10), the comparisons (compare.py), the words (words.py), then the Chinese PDF (render/research.html.j2
through headless Chrome) at reports/<date>/research_<code>.pdf, and the WeChat text summary (at most 4,000 bytes).
report.json beside the fact sheet keeps the words, the timings and DeepSeek's usage, so a report can be rendered again
from saved data (render())."""

import json
import logging
import time
from datetime import date, timedelta

import httpx
import pandas as pd
from dotenv import dotenv_values

from stockreport import passages, review
from stockreport.config import CONFIG, REPORTS, ROOT
from stockreport.render import _env, fit_bytes, html_to_pdf
from stockreport.research import (CUR, charts, compare, folder, load, money, pct, price, rating, save, sheet, sources,
                                  stamp, texts, times, words)
from stockreport.research import facts as fact_sheet

log = logging.getLogger(__name__)
NAMES_CN = {"dcf": "现金流折现（DCF）", "dcf_normal": "现金流折现（正常化利润率）", "pe_own": "市盈率 × 自身历史",
            "pe_peers": "市盈率 × 同行", "pe_normal": "自身市盈率 × 正常化盈利", "pb_own": "市净率 × 自身历史",
            "pb_roe": "合理市净率（平均 ROE）", "evs_peers": "企业价值/销售额 × 同行", "peg_peers": "PEG × 同行",
            "ddm": "股息折现（两阶段）", "yield_own": "股息率 × 自身 5 年均值", "excess_return": "超额收益模型（账面权益）"}
TYPES = {"ordinary": "普通盈利企业", "fast_grower": "快速成长企业", "loss_making": "亏损但有收入", "pre_revenue": "尚无收入（未盈利生物科技等）",
         "bank": "银行", "insurer": "保险", "broker": "券商 / 资管", "cyclical": "周期性企业", "income": "高股息成熟企业 / 公用事业",
         "reit": "房地产信托（REIT）", "holding": "控股公司 / 多元集团"}
INDEX_NAME = {"cn": "沪深300ETF", "us": "标普500", "hk": "恒生指数"}
MARKET_NAME = {"cn": "A股", "hk": "港股", "us": "美股"}


def red_flags(f: dict, today: date) -> dict | None:
    """The report's own results review: the review's checklist and quote checks on this stock's sources, cached as the
    daily review's are (data/review/<market>/<code>.json), so rating.flags() reads it."""
    market, code = f["market"], f["code"]
    since90, since30 = (today - timedelta(days=90)).isoformat(), (today - timedelta(days=30)).isoformat()
    titles = load(folder(market, code) / "filings.json") if (folder(market, code) / "filings.json").exists() else []
    try:
        heads = texts.headlines(market, code, today)
    except Exception as e:
        log.warning("%s headlines: %s", code, e)
        heads = None
    try:
        cut = passages.latest(market, code, today)
    except Exception as e:
        log.warning("%s passages: %s", code, e)
        cut = None
    src = {"filings": [t for t in titles if t["kind"] != "routine" and t["date"] >= since90],
           "headlines": None if heads is None else [h for h in heads if h["date"] >= since30], "passages": cut}
    lines = review.lines_of(src)
    entry = review.cached(market, code)
    if entry and set(review.ids_of(lines)) <= set(entry["sources"]) and \
            (today - date.fromisoformat(entry["date"])).days <= review.CFG["keep_days"]:
        return entry
    key = dotenv_values(ROOT / ".env").get("DEEPSEEK_API_KEY")
    if not key:
        return None
    sc = f["screening"]
    row = {"code": code, "name": f["name"], "rank": None, "sector": f.get("industry"), "why": sc.get("why"), "risk": sc.get("risk")}
    row |= {k: sc.get(k) if sc.get(k) else float("nan") for k in ("g_value", "g_quality", "g_growth", "g_momentum")}
    client = httpx.Client(base_url=CONFIG["notes"]["base_url"], timeout=review.CFG["timeout"],
                          headers={"Authorization": f"Bearer {key}"})
    try:
        return review.review_one(client, market, row, "research", lines, today)
    except Exception as e:
        log.warning("%s research review: %s", code, e)
        return None


def market_pe(market: str, today: date) -> float | None:
    snap = sheet.snapshot(market, today)
    return float(snap["pe"][snap["pe"] > 0].median()) if len(snap) and "pe" in snap else None


def build(market: str, code: str, today: date | None = None, model: str | None = None) -> dict:
    """The whole report from today's data: report.json, the PDF and the text summary."""
    today, code, t = today or date.today(), fact_sheet.normal(market, code), {}
    started = time.monotonic()
    path = folder(market, code) / "facts.json"
    f = load(path) if path.exists() else None
    if not f or f["built"][:10] != today.isoformat() or "own_series" not in f["valuation"]:
        f = fact_sheet.build(market, code, today)
    t["data"] = time.monotonic() - started
    lines, sec = texts.bundle(f, today)
    t["sources"] = time.monotonic() - started - t["data"]
    flags = red_flags(f, today)
    t["review"] = time.monotonic() - started - t["data"] - t["sources"]
    v = rating.build(market, code, today)
    t["valuation"] = time.monotonic() - started - sum(t.values())
    screen = compare.screening(f, v, market_pe(market, today), (flags or {}).get("findings"))
    street = compare.street(f, v)
    w = words.write(f, v, lines, screen["keys"], street, screen, model)
    t["words"] = time.monotonic() - started - sum(t.values())
    doc = {"code": code, "market": market, "name": f["name"], "date": today.isoformat(), "built": stamp(), "lines": lines,
           "sections": {k: sec.get(k) for k in ("doc", "date", "url", "market", "note")} | {"parts": list((sec.get("parts") or {}))},
           "words": w, "screen": screen | {"keys": None}, "review": flags, "timings": t}
    save(folder(market, code) / "report.json", doc)
    pdf = render(market, code)
    t["pdf"] = time.monotonic() - started - sum(t.values())
    t["total"] = time.monotonic() - started
    doc["timings"] = {k: round(x, 1) for k, x in t.items()}
    save(folder(market, code) / "report.json", doc)
    log.info("%s research report %s in %.0fs (%s); DeepSeek %s", code, pdf, t["total"], doc["timings"], w.get("usage"))
    return doc | {"pdf": str(pdf), "summary": summary(f, v, doc)}


def render(market: str, code: str) -> "Path":
    """The PDF from the saved fact sheet, valuation and report.json (no fetch, no DeepSeek call)."""
    f, v = (load(folder(market, code) / n) for n in ("facts.json", "valuation.json"))
    doc = load(folder(market, code) / "report.json")
    ctx = context(f, v, doc)
    out = REPORTS / doc["date"] / f"research_{code}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    html = out.with_suffix(".html")
    html.write_text(_env.get_template("research.html.j2").render(r=ctx), encoding="utf-8")
    html_to_pdf(html, out)
    html.unlink()
    return out


def context(f: dict, v: dict, doc: dict) -> dict:
    """Everything the template shows, formatted by code."""
    q, val, w = v["currency"], f["valuation"], doc["words"]
    k = v.get("inputs") or {}
    rc = k.get("currency") or val["report_currency"]
    daily = load(folder(f["market"], f["code"]) / "daily.csv.gz") if (folder(f["market"], f["code"]) / "daily.csv.gz").exists() else None
    index_code = sources.INDEX[f["market"]][1]
    ok = w.get("status") == "done"
    st = v.get("street") or {}
    sec = doc["sections"]
    used = sorted({i for x in _items(w) for i in x.get("src") or []})
    cited = [{"n": i, **doc["lines"][i - 1]} for i in used]
    finds = (doc.get("review") or {}).get("findings") or []
    return {
        "f": f, "v": v, "w": w, "ok": ok, "doc": doc, "q": q, "rc": rc, "cur": CUR.get(q, q), "rcur": CUR.get(rc, rc),
        "market_name": MARKET_NAME[f["market"]], "type_name": TYPES.get(v.get("type"), v.get("type")),
        "methods": [{"name": NAMES_CN[m], "weight": wt, **v["methods"][m]} for m, wt in (v.get("weights") or {}).items()],
        "forecast": compare.forecast(f, v), "screen": doc["screen"],
        "charts": {"price": charts.price(daily, f["code"], index_code, INDEX_NAME[f["market"]]) if daily is not None else "",
                   "history": charts.history(f["history"], f["kind"]),
                   "football": charts.football(v, NAMES_CN) if v.get("target") else "",
                   "band": charts.band(val.get("own_series") or {}, "pb" if v.get("type") in ("bank", "insurer", "broker") else "pe",
                                       None)},
        "street": st, "cited": cited, "findings": finds, "sections": sec,
        "fmt": {"pct": pct, "money": money, "price": price, "times": times},
        "review_status": "已读" if doc.get("review") else "暂不可用",
    }


def _items(w: dict) -> list[dict]:
    out = []
    for x in w.values():
        if isinstance(x, dict) and "src" in x:
            out.append(x)
        elif isinstance(x, list):
            out += [y for y in x if isinstance(y, dict) and "src" in y]
    return out


def summary(f: dict, v: dict, doc: dict, limit: int = 4000) -> str:
    """The WeChat message: the decision first, then the points, the risks, the two comparisons and a pointer to the PDF."""
    q, w, st, sc = v["currency"], doc["words"], v.get("street") or {}, doc["screen"]
    ok = w.get("status") == "done"
    lines = [f"【个股研究】{f['name']} {f['code']}（{MARKET_NAME[f['market']]}）{doc['date']}"]
    if v.get("target") is None:
        lines.append(f"评级：{v['rating']}（{v.get('reason') or '无法估值'}），现价 {price(v['price'], q)}")
    else:
        lines.append(f"评级：{v['rating']}　目标价 {price(v['target'], q)}（现价 {price(v['price'], q)}，"
                     f"{pct(v['target'] / v['price'] - 1, True, 0)}）")
        lines.append(f"预期 12 个月回报 {pct(v['expected_return'], True)}（含股息），大盘预期 {pct(v['market_return'])}；"
                     f"超额 {pct(v['excess_return'], True)} 对比门槛 ±{v['uncertainty']['band']:.0%}")
    if ok and w.get("conclusion"):
        lines.append("结论：" + w["conclusion"]["text"])
    for title, field in (("要点", "points"), ("风险", "risks")):
        items = w.get(field) or []
        if ok and items:
            lines.append(f"{title}：")
            lines += [f"{i}. {x['title']}：{x['text']}" if x.get("title") else f"{i}. {x['text']}" for i, x in enumerate(items, 1)]
    if not ok:
        lines.append("文字分析暂不可用（DeepSeek 未响应），数字部分见 PDF。")
    if sc.get("agreement"):
        lines.append(f"与每日筛选：{sc['agreement']}（筛选：{sc['view']}）" + (f"。{w['vs_screening']['text']}" if ok and w.get("vs_screening") else ""))
    elif sc.get("reason"):
        lines.append("每日筛选：不在筛选范围")
    if st.get("target"):
        lines.append(f"市场一致目标价 {price(st['target'], q)}（{pct(st['upside'], True, 0)}），我们{pct(st['ours_vs_street'], True, 0)}"
                     + (f"。{w['vs_street']['text']}" if ok and w.get("vs_street") else ""))
    lines += ["", "完整报告见 PDF：估值方法、三年预测、财务质量、催化剂和风险。程序生成，仅供参考，不构成投资建议。"]
    return fit_bytes(lines, limit)
