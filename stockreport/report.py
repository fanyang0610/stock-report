"""The report (PLAN.md, "Goal" and "Cards"): per market (CN → US → HK) the 预期 line, the 20-name buy portfolio, the
holdings check and the 10 avoid names, from each market's lists CSV (a market without one for the day shows its newest
earlier lists, with their date) -> reports/<date>/report.pdf and summary.txt; the day's lists go to data/picks.csv."""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport import deliver, track
from stockreport.cleanup import size_of
from stockreport.config import CONFIG, DATA, REPORTS
from stockreport.render import html_to_pdf, render_html, text_summary
from stockreport.score import NAMES

MARKETS = {"cn": ("A股 CN", "CNY", "元", "沪深300ETF"), "us": ("美股 US", "USD", "美元", "标普500基金"),
           "hk": ("港股 HK", "HKD", "港元", "盈富基金")}
EXPECT = DATA / "history" / "expect.json"  # written by the history run (backtest/qvm.py)
CORE = {"us": ("标普500指数基金", "如 SPY、VOO，市值最大的公司都在里面")}  # the index-core markets' fund
EVIDENCE = {
    "cn": "已发表研究：A 股的价值（尤其 E/P）和业绩超预期后的漂移长期有效；价格动量在 A 股 20 年不赚钱，所以 A 股的动量用业绩意外。",
    "us": "已发表研究：价值、质量、动量在美国有几十年记录，但公开后超额收益平均缩水过半（McLean-Pontiff 2016）。",
    "hk": "已发表研究：港股价值和质量的证据较多，价格动量的证据不一。",
}
COMMON = ("公开的因子组合平均每年跑赢指数几个百分点，但约 4 成年份跑输（AAII 实盘组合 55% 的滚动年份跑赢）；"
          "证据针对整个组合，只买其中几只结果更分散。任何名单都不保证收益。")
METHOD = ("每个市场按价值（E/P、B/P、S/P）、质量（盈利能力、利润的现金支撑、负债率）和动量（美股、港股：过去 12 个月除最近 1 个月的"
          "涨幅；A 股：最新季度扣非利润相对往年同期的意外 SUE）三类打分，各占三分之一，每项取市场内百分位，A-E 为各类的五分位（价值、质量在金融股之间和其他股票之间分别排）。"
          "买入组合：市值前 300（港股前 200，美股只含美国本土公司）里评分最高的 20 只，每个行业最多 2 只，等额买入，持有 12 个月。"
          "回避：市值前 400 里评分最低的 10 只。数字全部来自程序和公开数据。")


def expect_lines(market: str) -> list[str]:
    """The 预期 line from the history run's numbers, plus the published evidence."""
    fund = MARKETS[market][3]
    runs = json.loads(EXPECT.read_text(encoding="utf-8")) if EXPECT.exists() else {}
    if market not in runs:
        return ["历史模拟尚未运行。", EVIDENCE[market]]
    e, n20 = runs[market], runs[market]["portfolios"]["20"]
    period = f"模拟回测（{e['first']} 至 {e['last']} 每月建仓的 {e['windows']} 个 12 个月，扣交易成本）："
    say = lambda r: (f"平均每 12 个月比{fund}{'多' if r['excess'] >= 0 else '少'}赚 {abs(r['excess']):.1%}，{r['beat']:.0%} 的 12 个月"
                     f"跑赢；最差 12 个月 {r['worst']:+.0%}（同期{fund} {r['worst_fund']:+.0%}）；最大回撤 {r['drawdown']:.0%}（{fund} "
                     f"{e['fund_drawdown']:.0%}）。")
    lines = [period + "20 只组合" + say(n20)]
    if "core" in e:  # the recommended split first, then the 20 names alone
        lines = [f"{period}{e['core']['share']:.0%} 指数基金、其余等额买 20 只：" + say(e["core"]), "只买 20 只：" + say(n20)]
    lines += ["只买 10 只 / 5 只：最差的 12 个月相对基金 " + " / ".join(
                 f"{e['portfolios'][n]['worst_excess']:+.0%}" for n in ("10", "5")) +
             f"（20 只 {n20['worst_excess']:+.0%}），名单越短结果越分散。"]
    lines.append("历史只含今天仍上市的公司（A 股的财务数字还是后来修订过的版本），模拟结果偏乐观。" if market == "cn" else
                 "历史只含今天仍上市的公司，模拟结果偏乐观。")
    backwards = [f"{NAMES[f]}（前五分之一比后五分之一每 12 个月少 {-x:.1%}）"
                 for f, x in ((f, e.get("families", {}).get(f"f_{f}", 0)) for f in NAMES) if x < 0]
    if backwards:
        lines.append(f"这段历史里{'、'.join(backwards)}与已发表研究的方向相反；已发表研究的样本长得多，方法不变。")
    return lines + [EVIDENCE[market]]


def card(r: dict, unit: str) -> dict:
    lot = r.get("lot")
    lot_text = "一手股数未知" if pd.isna(lot) else (f"1 股约 {r['lot_cost']:,.0f} {unit}" if lot == 1 else
                                                 f"一手 {lot:,.0f} 股约 {r['lot_cost']:,.0f} {unit}")
    fams = {f: r.get(f"f_{f}") for f in NAMES}
    weakest = min((f for f in fams if pd.notna(fams[f])), key=fams.get, default=None)
    ranks = {k: int(r[k]) for k in ("rank", "score_rank") if r.get(k) is not None}  # floats after the CSV
    return r | ranks | {"ticker": r["code"], "lot_text": lot_text, "grades": {NAMES[f]: r.get(f"g_{f}") for f in NAMES},
                "weakest": f"{NAMES[weakest]} {r[f'g_{weakest}']}" if weakest else ""}


def save_failed(today: date, market: str, failed: list[str]) -> None:
    """Remember a market's failed fetch steps for the day's report (an empty list clears them)."""
    path = REPORTS / today.isoformat() / "fetch_failed.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state | {market: failed}, ensure_ascii=False), encoding="utf-8")


def latest_lists(market: str, today: date) -> Path | None:
    """Today's lists CSV for the market, else the newest earlier one."""
    found = [p for p in sorted(REPORTS.glob(f"????-??-??/{market}_lists.csv")) if p.parent.name <= today.isoformat()]
    return found[-1] if found else None


def section(market: str, rows: pd.DataFrame, day: str, today: date, failed: list[str]) -> dict:
    name, currency, unit, _ = MARKETS[market]
    rows = rows.astype(object).where(rows.notna(), None)
    cards = {k: [card(r, unit) for r in rows[rows["list"] == k].to_dict("records")] for k in ("buy", "holding", "avoid", "veto")}
    share = CONFIG["lists"]["index_core"].get(market)
    fund, note = CORE.get(market, ("", ""))
    core = (f"建议配置：{share:.0%} 的资金买{fund}（{note}）；其余 {1 - share:.0%} 等额买下面 20 只（每只约 {(1 - share) / 20:.1%}），"
            "在指数之上加重价值、质量、动量都好的公司。美股大盘最难跑赢指数，下面的模拟里这样配置也跑输了基金；"
            "保留这 20 只依据的是几十年的已发表研究，不保证跑赢。") if share else ""
    return {"code": market.upper(), "name": name, "currency": currency, "expect": expect_lines(market), "core": core,
            "core_short": f"{share:.0%} {fund}" if share else "",
            "data_date": max((c["price_date"] for c in cards["buy"] if c["price_date"]), default=day),
            "stale": (f"今日未能更新，沿用 {day} 的名单" if day != today.isoformat() else
                      f"今日部分数据获取失败（{'、'.join(failed)}），沿用上次的缓存数据" if failed else ""),
            "buys": cards["buy"], "holdings": cards["holding"], "avoid": cards["avoid"], "vetoes": cards["veto"]}


def build(today: date) -> tuple[Path, str]:
    """Write report.html/.pdf and summary.txt for the day; returns the PDF path and the summary."""
    out = REPORTS / today.isoformat()
    status = out / "fetch_failed.json"
    failed = json.loads(status.read_text(encoding="utf-8")) if status.exists() else {}
    markets, logged = [], {}
    for market in MARKETS:
        path = latest_lists(market, today)
        if not path:
            continue
        rows = pd.read_csv(path, dtype={"code": str, "price_date": str, "since": str, "recheck": str})
        if path.parent.name == today.isoformat():
            logged[market] = rows[rows["list"].isin(["buy", "avoid"])].rename(columns={"list": "bucket"})
        markets.append(section(market, rows, path.parent.name, today, failed.get(market, [])))
    if not markets:
        raise SystemExit(f"no lists CSV in {REPORTS}; run `run` first")
    if logged:
        track.log_picks(today, logged)
    size_gb = (size_of(DATA) + size_of(REPORTS)) / 1e9
    report = {"title": "股票报告", "date": today.isoformat(), "markets": markets, "method": METHOD, "common": COMMON,
              "storage_warning": (f"注意：data/ + reports/ 已占用 {size_gb:.1f} GB，超过 {CONFIG['storage']['warn_gb']} GB 上限。"
                                  if size_gb > CONFIG["storage"]["warn_gb"] else "")}
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
