"""Outliers are checked, not normalized (your rule, 2026-10-20; Phase 13, PLAN.md Method 16): an industry
that is off as a whole points at the method for that industry; a single stock far from its value gets a
verdict from the evidence the build already collects (business trend, cross-checks, filings, deep dives)."""

import json
from datetime import date

import pandas as pd

from stockreport import baserates as br, trend
from stockreport.config import CONFIG, REPORTS

LIVE = True  # the backtest sets False: today's second-source tables don't apply to past dates


def far_industries(v: pd.DataFrame, df: pd.DataFrame) -> pd.Series:
    """Industries (5+ valued) whose median upside is beyond ±30%: the method is checked for the industry as a whole."""
    ind = v.loc[v["valued"], "upside"].groupby(df["industry"][v["valued"]]).agg(["median", "count"])
    return ind[(ind["count"] >= 5) & (ind["median"].abs() > 0.3)]["median"]


def verdicts(v: pd.DataFrame, df: pd.DataFrame, market: str, today: date) -> pd.DataFrame:
    """One verdict with its reason per valued stock beyond ±100% or labelled 价格隐含过高/过低: 行业 (its industry
    is off as a whole), 数据错误 (out of the lists: profit, EPS or book 20%+ off its second source, revenue too for
    own-trend growth, or a deep-dive veto), 证据支持 (kept, risk flagged: the business trend explains the price,
    or a deal, risk or capital filing in the last 30 days), else 需复核 (your review list, with what the value
    rests on). Kept in the snapshot (v3_verdict): `track --signal` shows which kinds the market was right about."""
    ok, up, label = v["valued"], v["upside"], v["implied_label"].fillna("")
    cheap, rich = ok & ((up > 1) | (label == "价格隐含过低")), ok & (label == "价格隐含过高") & ~(up > 1)
    out = pd.DataFrame({"verdict": "", "verdict_why": ""}, index=v.index)
    far, events, dives = far_industries(v, df), recent_events(market, today), deep_dives(market, today)
    gaps = second_gaps(df, market, own=v["t0"] == 0) if LIVE else {}
    for code in v.index[cheap | rich]:
        x, side, ind = v.loc[code], "便宜" if cheap[code] else "昂贵", df.at[code, "industry"]
        if ind in far.index:
            out.loc[code] = "行业", f"{ind} 整体偏离 {far[ind]:+.0%}：按行业检查方法"
        elif code in gaps or dives.get(code, ("", ""))[0] == "veto":
            out.loc[code] = "数据错误", gaps.get(code) or "深度核查否决：" + dives[code][1]
        elif (cheap[code] and x["trend"] == -1) or (rich[code] and x["trend"] == 1):
            risk = "价值陷阱风险：价格反映下滑" if cheap[code] else "价格反映改善，须持续"
            out.loc[code] = "证据支持", f"{side}且业务{trend.LABELS[x['trend']]}（{x['trend_why']}）；{risk}"
        elif code in events or code in dives:
            out.loc[code] = "证据支持", f"{side}；" + (events.get(code) or "深度核查：" + dives[code][1])
        else:
            out.loc[code] = "需复核", f"{side}，业务{trend.LABELS[x['trend']]}" + (f"（{x['trend_why']}）" if x["trend_why"] else "") \
                + "；估值依赖：" + drivers(x)
    return out


def drivers(x: pd.Series) -> str:
    """What an unexplained outlier's value rests on (the inputs at or near the model's limits)."""
    parts = [f"增长率 {x['g']:.0%}" + ("（上限）" if x["g"] >= CONFIG["v3"]["growth"][1] - 1e-9 else "")
             + ("，按自身营收趋势（分析师不足 3 位）" if x["t0"] == 0 else "，前 3 年按分析师预测")]
    if x["d50"] >= br.DMAX - 0.01:
        parts.append(f"中位久期到 {br.DMAX} 年上限（类似公司 10 年后仍有 {x['s10']:.0%} 保持）")
    if x["starts"] < 100:
        parts.append(f"基础比率仅 {x['starts']:.0f} 例")
    if x["light"]:
        parts.append("轻资产（按 40% 回报的资本估值）")
    return "；".join(parts)


def second_gaps(df: pd.DataFrame, market: str, own: pd.Series) -> dict[str, str]:
    """Profit, EPS or book (revenue for `own`-trend stocks) 20%+ (`drop_gap`) off the second source (live only;
    smaller gaps are mostly definitions, share counts differ by share class: crosscheck.py)."""
    from stockreport import crosscheck
    try:
        sources = crosscheck.second_sources(df, market)
    except Exception:  # the backtest and a missing table: no second source
        return {}
    out = {}
    for label, g, *_ in sources:
        if "close" in label or "shares" in label:
            continue
        for code in g.index[(g > crosscheck.CFG["drop_gap"]) & (own | ~label.startswith("TTM revenue"))]:
            out.setdefault(code, f"{label} 相差 {g[code]:.0%}")
    return out


def recent_events(market: str, today: date, days: int = 30) -> dict[str, str]:
    """The newest deal, risk or capital filing of the last 30 days per stock (fetch/events.py)."""
    from stockreport.events import KINDS, short
    from stockreport.fetch import events as feed
    ev = feed.load(market)
    since = (pd.Timestamp(today) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    ev = ev[ev["kind"].isin(["deal", "risk", "capital"]) & (ev["date"] >= since) & (ev["date"] <= today.isoformat())]
    ev = ev.sort_values("date").groupby("code").tail(1)
    return {c: f"{d[5:]} {KINDS[k]}公告：{short(t)}" for c, d, k, t in ev[["code", "date", "kind", "title"]].itertuples(index=False)}


def deep_dives(market: str, today: date) -> dict[str, tuple[str, str]]:
    """The newest deep-dive results up to `today` (reports/<date>/<market>_deepdive.json): action and line."""
    days = sorted(p for p in REPORTS.glob(f"*/{market}_deepdive.json") if p.parent.name <= today.isoformat())
    res = json.loads(days[-1].read_text(encoding="utf-8")).get("results", {}) if days else {}
    return {c: (r.get("action", ""), r.get("line", "")) for c, r in res.items() if r.get("action") != "none" or r.get("line")}
