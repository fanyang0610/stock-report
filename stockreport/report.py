"""The report (PLAN.md, "Goal", "Cards" and "Report"): first each market's three ratings by name and what changed,
then per market (CN → US → HK) the 预期 line, the 20 Buy names (the portfolio), the 10 Hold and the 10 Sell, from each
market's lists CSV (a market without one for the day shows its newest earlier lists, with their date); the method and
the evidence at the back -> reports/<date>/report.pdf and summary.txt; the day's lists go to data/picks.csv.
On request (fresh()) the results review runs first and build() applies it (review.apply)."""

import json
import logging
import re
import time
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport import deliver, review, track, verdicts
from stockreport.cleanup import size_of
from stockreport.config import CONFIG, DATA, REPORTS
from stockreport.fetch import profiles
from stockreport.notes import SHORT, shorten
from stockreport.render import html_to_pdf, render_html, text_summary
from stockreport.score import NAMES

log = logging.getLogger(__name__)

MARKETS = {"cn": ("A股 CN", "CNY", "元", "沪深300ETF"), "us": ("美股 US", "USD", "美元", "标普500基金"),
           "hk": ("港股 HK", "HKD", "港元", "盈富基金")}
EXPECT = DATA / "history" / "expect.json"  # written by the history run (backtest/qvm.py)
EVIDENCE = {
    "cn": "已发表研究：A 股的价值（尤其 E/P）、业绩超预期后的漂移和低波动长期有效（低波动：Blitz、Hanauer、van Vliet 2021），"
          "中证红利低波按股息率和低波动选股；价格动量在 A 股 20 年不赚钱，所以 A 股的动量用业绩意外和分析师预测调整"
          "（含 A 股、港股的亚洲 7 个市场里，多数市场股价随预测调整同向：S&P DJI 2017）。",
    "us": "已发表研究：价值（含 EBIT/EV：Greenblatt、Gray-Carlisle）、质量、成长（Seeking Alpha 量化评级的五项之一）、动量和"
          "分析师预测调整在美国有几十年记录（预测调整：Chan、Jegadeesh、Lakonishok 1996），但公开后超额收益平均缩水过半"
          "（McLean-Pontiff 2016）。",
    "hk": "已发表研究：港股价值和质量的证据较多，恒生港股通红利低波按股息率和低波动选股，价格动量的证据不一；含港股的亚洲 7 个市场里，"
          "多数市场股价随分析师预测调整同向（S&P DJI 2017）。",
}
FIELD = {"cn": "A 股市值前 800 只", "us": "美股市值前 800 只", "hk": "流动性达标的港股"}  # the buys' field: the scored market
GUIDE = [  # page 1: how to read it, in five lines
    "<b>三种评级</b>，像券商分析师给股票评级一样只看股票本身，不看任何人的持仓：<b>买入</b> = 预计跑赢大盘；<b>持有</b> = 评分居中，"
    "不偏涨也不偏跌，股价较稳；<b>卖出</b> = 预计跑输大盘（大盘涨时它也可能涨，只是涨得少）。评级看 12 个月，名单每天按最新数据更新。",
    "<b>买入 20 只</b>从整个市场按评分选，各行业的只数按它在市场里的分量分配，每只买相同金额、持有 12 个月；<b>持有 10 只</b>是大公司里"
    "评分居中、过去一年每日涨跌最小的（10 只合起来历史上比基金波动小，大盘涨得多时落后；单只仍可能大涨大跌）；<b>卖出 10 只</b>"
    "是大公司里评分最低的（每个行业最多 2 只）。",
    "<b>评级 A–E</b>：价值（价格相对利润和资产贵不贵）、质量（赚钱能力和稳定性）、成长（营收和利润在不在增长）、动量（股价和分析师预期在不在"
    "变好），都和同行业比：A 是同行最好的五分之一，E 是最差的五分之一。<b>风险</b>是亏损、负债率 70% 以上或半年跌超 30%；没有这些"
    "时写<b>短板</b>，即和同行比最弱的一项。",
    "<b>审核</b>：DeepSeek 读每只股票近期的公告、最新定期报告的相关段落和新闻，引文由程序核对；有硬风险的买入和持有会被换掉，"
    "卖出名单上的只做标注。这是唯一用 AI 的一步，其余全部由程序完成。",
    "<b>不是保证</b>：这类方法平均每年跑赢指数几个百分点，但约 4 成年份跑输。历史模拟只含今天仍上市的公司，退市的差公司不在里面，"
    "对卖出名单最偏乐观。所有数字来自程序和公开数据，不构成投资建议。",
]
METHOD = [  # the back pages
    ("怎么打分", "每只股票按四类打分，各占四分之一，每项都和同行业比（银行、保险、券商等金融股另算；同行不足 10 只的和全市场比）："
     "价值（市盈率、未来 12 个月预期市盈率、市净率、市销率、EBIT/EV、股息率）；质量（盈利能力、利润的现金支撑、负债率、8 年平均资产回报率、"
     "毛利率稳定性、股价波动）；成长（营收和利润同比、5 年利润增长）；动量（美股、港股：过去 12 个月除最近 1 个月的涨幅；A 股："
     "最新季度扣非利润相对往年同期的意外；三个市场都加上分析师 3 个月内对下一个完整财年盈利预测的调整）。成分借自 Stockopedia、Seeking Alpha "
     "量化评级、Alpha Architect 的量化价值（Gray-Carlisle）、Greenblatt 神奇公式和红利低波指数，权重相等，不按回测调整。"),
    ("怎么选", "买入组合从整个市场选（A 股、美股市值前 800 只，港股流动性达标的股票，不只是指数成分股）：每个行业按它在市场自由流通"
     "市值里的份额分到名额，名额给行业里评分最高的股票，每只等额，持有 12 个月。最可能陷入财务困境（Campbell-Hilscher-Szilagyi "
     "概率）和应计利润最大的各 5% 不买（量化价值的第一步），港股小盘股和美股合伙企业也不买。组合只有 20 只，收益会明显偏离指数，"
     "好坏都可能。"),
    ("三种评级", "评级是相对大盘的，和摩根大通、摩根士丹利等券商的评级一样（跑赢 / 持平 / 跑输所覆盖股票的平均回报）：研究里评分最高的五分之一"
     "跑赢、最低的五分之一跑输，中间的没有明显优势。买入 = 上面的 20 只。持有 = 市值前 400 里、评分在全市场正中间五分之一的股票中，近一年"
     "每日涨跌（波动率）最小的 10 只（每个行业最多 2 只，不含买入和候补，也不含可能陷入财务困境或应计利润最大的）：评分不偏向涨也不偏向跌，"
     "过去波动小的股票以后波动通常也小。波动小说的是每天的涨跌，不是一年的涨跌：缓慢而持续的下跌也可能波动小，卡片上的「风险」会写出半年"
     "跌超 30%。卖出 = 市值前 400 里评分最低的 10 只，每个行业最多 2 只。复查日都是 12 个月后，即评级的期限；名单每天更新，评级可能提前改变。"),
    ("审核（你请求报告时进行，唯一用 AI 的一步）", "DeepSeek 读每只股票近 90 天的非例行公告标题、程序从最新定期报告里截取的相关段落"
     "（审计意见、持续经营、立案调查、公司被收购）和近 30 天的新闻标题，每条结论都引用原文，由程序核对引文确实出自该来源。硬风险（监管"
     "立案调查或欺诈认定、非标审计意见或审计师辞任、持续经营疑虑或债务违约、退市/ST/停牌、已签署尚未完成的被收购或私有化（现金或换股）、"
     "制裁）只认公司自己的公告和定期报告：买入和持有被剔除（由同行业的下一名替补，没有则由下一名，列在「审核剔除」），卖出只标注；软风险"
     "只标注「市场可能在担心」。数据本身由程序和第二个数据源核对，AI 不读也不改任何数字。"),
    ("文字从哪里来", "所有数字都来自程序和公开数据。AI 点评只用文字，不含数字。公司业务：A 股、港股取自东方财富的公司资料（主营业务），"
     "美股取自雅虎财经的公司简介，审核时由 DeepSeek 写成一句中文（不含数字；没有时显示原句）。"),
]
COMMON = ("公开的因子组合平均每年跑赢指数几个百分点，但约 4 成年份跑输（AAII 实盘组合 55% 的滚动年份跑赢）；"
          "证据针对整个组合，只买其中几只结果更分散。任何名单都不保证收益。")
SUFFIX = re.compile(r"(,?\s+(Inc\.?|Corp\.?|Corporation|Company|Co\.?|Ltd\.?|Limited|plc|PLC|N\.V\.|S\.A\.B\.? de C\.V\.?|"
                    r"S\.A\.?|AG|SE|Holdings?|Group|\(The\)|ADR)|-[A-C])+$")
CJK = re.compile(r"[一-鿿]")


def expect(market: str) -> dict:
    """The 预期 lines in plain words (the Buy portfolio's; Hold's and Sell's, under their headings), the summary's
    shorter ones (the buys'; then Hold's and Sell's, `rated`), and the details for the back pages (the history run's
    numbers and the evidence)."""
    fund = MARKETS[market][3]
    runs = json.loads(EXPECT.read_text(encoding="utf-8")) if EXPECT.exists() else {}
    if market not in runs:
        none = "历史模拟尚未运行。"
        return {"line": none, "short": none, "rated": "", "hold": none, "sell": none, "detail": [EVIDENCE[market]]}
    e, n20 = runs[market], runs[market]["portfolios"]["20"]
    more = lambda x: f"{'多' if x >= 0 else '少'}赚 {abs(x):.1%}"
    fell = lambda r: (f"持有的一年里从高点的最大跌幅（按月末价格），一般 {-r['fall_median']:.0%}（{fund} {-r['fall_fund_median']:.0%}），"
                      f"最差 {-r['fall_worst']:.0%}（{fund}同期 {-r['fall_worst_fund']:.0%}）")
    line = (f"按历史模拟（简化版方法：历史数据里没有分析师预测、EBIT/EV 和困境筛选），过去每月建仓、持有一年的 {e['windows']} 个 12 "
            f"个月里：平均比{fund}{more(n20['excess'])}，{n20['beat']:.0%} 跑赢；最差的一个 {n20['worst']:+.0%}（{fund}同期 "
            f"{n20['worst_fund']:+.0%}）；{fell(n20)}。模拟偏乐观，不是保证。")
    short = (f"历史模拟（简化版）：买入平均每年比{fund}{more(n20['excess'])}（{n20['beat']:.0%} 的时候跑赢，最差一年 "
             f"{n20['worst']:+.0%}，基金同期 {n20['worst_fund']:+.0%}）。")
    hold = sell = "历史模拟尚未运行。"
    rated = ""
    if r := e.get("ratings"):
        h, x = r["hold"], r["sell"]
        hold = (f"历史模拟（简化版）里每月的持有 10 只拿 12 个月：平均比{fund}{more(h['excess'])}；股价波动是{fund}的 "
                f"{h['vol'] / h['fund_vol']:.1f} 倍；{fell(h)}。10 只合起来每月的涨跌通常比大盘小，大盘涨得多时会落后。")
        sell = (f"历史模拟（简化版）里每月的卖出 10 只拿 12 个月：{1 - x['beat']:.0%} 的时候跑输{fund}，平均{more(x['excess'])}"
                f"（它们自己平均 {x['mean']:+.1%}，{fund} {x['fund_mean']:+.1%}）；波动是{fund}的 {x['vol'] / x['fund_vol']:.1f} 倍；"
                f"{fell(x)}。跑输不等于下跌。模拟里没有已退市的公司，而退市多发生在亏损、股价大跌的公司，"
                "即评分低的一端，所以卖出这一段的模拟最偏乐观。")
        rated = f"持有{more(h['excess'])}、波动小于基金；卖出 {1 - x['beat']:.0%} 的时候跑输、平均{more(x['excess'])}。"
    detail = [f"模拟回测：{e['first']} 至 {e['last']} 每月建仓的 {e['windows']} 个 12 个月，扣交易成本。只买 10 只 / 5 只：最差的 12 个月"
              "相对基金 " + " / ".join(f"{e['portfolios'][n]['worst_excess']:+.0%}" for n in ("10", "5")) +
              f"（20 只 {n20['worst_excess']:+.0%}），名单越短结果越分散。每月建仓、同时持有 12 批的组合，整段历史里从高点的最大跌幅 "
              f"{-n20['drawdown']:.0%}（{fund} {-e['fund_drawdown']:.0%}）。",
              ("历史只含今天仍上市的公司（A 股的财务数字还是后来修订过的版本），模拟结果偏乐观" if market == "cn" else
               "历史只含今天仍上市的公司，模拟结果偏乐观") + "；模拟的 12 个月里没有分析师预测，也没有 EBIT、有息负债和现金的历史，"
              "评分不含预期 E/P、预测调整和 EBIT/EV，也没有财务困境和应计利润筛选" +
              ("；行业份额用今天的自由流通比例近似。" if market != "us" else "。")]
    if nb := e.get("neutral"):
        detail.append(f"20 只比{fund}{more(n20['excess'])}，拆开看：对照组合用同样的行业名额，把每个行业里所有可买的股票等额持有，"
                      f"平均比{fund}{more(nb['excess'])}，这是等额持有和行业名额的作用；20 只又比对照组合{more(nb['picks'])}"
                      f"（{nb['picks_beat']:.0%} 的时候领先），这是选股的作用。")
    backwards = [f"{NAMES[f]}（前五分之一比后五分之一每 12 个月少 {-x:.1%}）"
                 for f, x in ((f, e.get("families", {}).get(f"f_{f}", 0)) for f in NAMES) if x <= -0.0005]
    if backwards:
        detail.append(f"这段历史里{'、'.join(backwards)}与已发表研究的方向相反；已发表研究的样本长得多，方法不变。")
    return {"line": line, "short": short, "rated": rated, "hold": hold, "sell": sell, "detail": detail + [EVIDENCE[market]]}


def lot_money(buys: list[dict], unit: str) -> str:
    """The money one board lot of every buy takes at equal amounts: the largest lot cost over its share of the money.
    Arithmetic, not advice."""
    known = [b for b in buys if b.get("lot_cost") and b.get("weight")]
    if not known:
        return ""
    top = max(known, key=lambda b: b["lot_cost"] / b["weight"])
    need, missing = top["lot_cost"] / top["weight"], len(buys) - len(known)
    return (f"每只金额相等、每只至少一手，买齐这 {len(buys)} 只约需 {need / 1e4:,.{1 if need >= 1e5 else 2}f} 万{unit}（一手最贵的是 "
            f"{top['short']}，约 {top['lot_cost']:,.0f} {unit}）" + (f"，另有 {missing} 只一手股数未知、未计入" if missing else "")
            + "。这只是算术，不是建议投入的金额。")


def business(market: str, code: str, table: pd.DataFrame) -> str:
    """What the company does, in one line: the review's line (notes.line: a US text, or a long CN/HK one), else the
    source's first sentence (CN/HK as written, cut with … past notes.SHORT; US in English, cut past 150 characters)."""
    if code not in table.index:
        return ""
    line, text = table.at[code, "line"], profiles.first(table.at[code, "source"])
    if isinstance(line, str) and line != "-":
        return line
    if market == "us":
        return text if len(text) <= 150 else text[:text.rfind(", ", 0, 150) if ", " in text[:150] else 150] + "…"
    cut = shorten(text.replace(",", "，"), SHORT)
    return cut if cut == text.replace(",", "，") else cut.rstrip("。") + "…"


def risk(r: dict) -> tuple[str, str, str]:
    """The card's risk line: 风险 for a loss, heavy debt or a big fall (score.card_lines), else 短板, the weakest
    component; and a Sell card's reasons, without a fact the weak line already shows (负债率高（88%） and 负债率 88%)."""
    text, weak = r.get("risk") or "", r.get("weak") or ""
    label, text = ("短板", text.removeprefix("最弱一项：")) if text.startswith("最弱一项：") else ("风险", text)
    figure = lambda x: (m := re.search(r"[\d.]+%", x)) and m.group() in weak and x[:3] in weak
    extra = [x for x in text.split("；") if x and x not in weak and not figure(x)]
    return label, text, "；".join([weak] * bool(weak) + extra)


def names(market: str, code: str, name, table: pd.DataFrame) -> tuple[str, str, str]:
    """The card's name, the English name under a US Chinese one (美光科技 / Micron Technology Inc), and the summary's
    short name (US: the ticker and the Chinese name, else the English one without Inc, Corp...)."""
    name, zh = name if isinstance(name, str) and name else code, table["name_cn"].get(code)
    if market != "us":
        return name, "", name
    if isinstance(zh, str) and CJK.search(zh):
        zh = re.sub(r"\(.*?\)|（.*?）|-[A-Z]$", "", zh).strip()
        return zh, SUFFIX.sub("", name), f"{code} {zh}"
    return name, "", f"{code} {SUFFIX.sub('', name)}"


def card(r: dict, market: str, table: pd.DataFrame) -> dict:
    unit, lot = MARKETS[market][2], r.get("lot")
    lot_text = "一手股数未知" if pd.isna(lot) else (f"1 股约 {r['lot_cost']:,.0f} {unit}" if lot == 1 else
                                                 f"一手 {lot:,.0f} 股约 {r['lot_cost']:,.0f} {unit}")
    fams = {f: r.get(f"f_{f}") for f in NAMES}
    weakest = min((f for f in fams if pd.notna(fams[f])), key=fams.get, default=None)
    ranks = {k: int(r[k]) for k in ("rank", "score_rank") if r.get(k) is not None}  # floats after the CSV
    name, name_en, short = names(market, r["code"], r["name"], table)
    label, risk_text, sell_why = risk(r)
    review_text, reason = r.get("review") or "", r.get("reason") or ""
    dup = reason and (review_text in reason or reason in review_text)  # a removed name's reason is the finding
    return r | ranks | {
        "ticker": r["code"], "name": name, "name_en": name_en, "lot_text": lot_text, "business": business(market, r["code"], table),
        "short": short,
        "grades": {NAMES[f]: r.get(f"g_{f}") for f in NAMES},
        "weakest": f"{NAMES[weakest]} {r[f'g_{weakest}']}" if weakest else "",
        "risk_label": label, "risk_text": risk_text, "sell_why": sell_why,
        "review_kind": ("hard" if review_text.startswith(("审核：", "数据存疑")) else "soft" if review_text.startswith("市场可能在担心")
                        else "ok" if review_text.endswith("未见重大风险") else "wait" if review_text else ""),
        "review_shown": "" if dup else review_text}


def live(market: str) -> str:
    """The live scorecard in one line (track.py), or "" if it fails: it never stops the report."""
    try:
        return live_line(market, track.load_cohorts(), *track.standing(track.load_marks(), market))
    except Exception:
        log.exception("%s scorecard line failed", market.upper())
        return ""


def live_line(market: str, cohorts: pd.DataFrame, t: pd.DataFrame, gone: int) -> str:
    """Each cohort's newest month-end mark: Buy against the fund and the 对照组合, Hold and Sell against the fund (the
    average over the cohorts with both figures); before the first mark, when it comes."""
    fund, mine = MARKETS[market][3], cohorts.loc[cohorts["market"] == market, "cohort"]
    if mine.empty:
        return ""
    if t.empty:
        return (f"实盘记录：从 {mine.min()} 起，每月第一份报告的名单各持有 12 个月，按月末收盘价（含股息）和{fund}、对照组合比，"
                f"第一个月末之后有数字。")

    def vs(a: str, b: str, name: str, word: str = "领先", note: str = "") -> str:
        d = (t[a] - t[b]).dropna() if {a, b} <= set(t.columns) else pd.Series(dtype=float)
        if d.empty:
            return ""
        count = f"{len(d)} 批中 {int((d < 0 if word == '跑输' else d > 0).sum())} 批{word}" if len(d) > 1 else ""
        why = "；".join(x for x in (count, note) if x)
        return f"{name}{'多' if d.mean() >= 0 else '少'}赚 {abs(d.mean()):.1%}" + (f"（{why}）" if why else "")

    months = f"{t['months'].min():.1f}" + (f"-{t['months'].max():.1f}" if len(t) > 1 else "")
    parts = [p for p in (vs("buy", "fund", f"买入比{fund}"), vs("buy", "basket", "比对照组合")) if p]
    rest = [p for p in (vs("hold", "fund", f"持有比{fund}"),
                        vs("sell", "fund", f"卖出比{fund}", "跑输", "卖出跑输才算判断对")) if p]
    text = (f"实盘记录（月末收盘价，含股息）：{len(t)} 批名单，已持有 {months} 个月"
            + "".join(f"；{p}" for p in ["，".join(parts)] + rest if p) + "。")
    return (text + (f"停牌或退市的 {gone} 只未计入。" if gone else "") + ("各批平均。" if len(t) > 1 else "")) \
        if parts or rest else ""


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


def changes(market: str, day: str, buys: list[dict], log: pd.DataFrame, table: pd.DataFrame) -> dict:
    """The buys new since the last report sent to you before `day` (data/sent.csv), and the names gone from it."""
    past = log[(log["market"] == market) & (log["date"] < day)]
    if past.empty:
        return {}
    last = past[past["date"] == past["date"].max()]
    now = {b["ticker"] for b in buys}
    return {"since": last["date"].iloc[0], "new": [b for b in buys if b["ticker"] not in set(last["ticker"])],
            "gone": [names(market, t, n, table)[2] for t, n in zip(last["ticker"], last["name"]) if t not in now]}


def section(market: str, rows: pd.DataFrame, day: str, today: date, failed: list[str], log: pd.DataFrame) -> dict:
    name, currency, unit, _ = MARKETS[market]
    rows, table = rows.astype(object).where(rows.notna(), None), profiles.load(market)
    cards = {k: [card(r, market, table) for r in rows[rows["list"] == k].to_dict("records")]
             for k in ("buy", "hold", "sell", "veto", "removed")}
    for p in cards["removed"]:  # the name that took its place, as the cards name it
        p["replaced_by"] = next((b["short"] for b in cards[p.get("from") or "buy"] if b.get("replaces") == p["ticker"]), "")
    return {"code": market.upper(), "name": name, "short": name.split()[0], "currency": currency, "unit": unit, "day": day,
            "expect": expect(market), "live": live(market), "field": FIELD[market],
            "data_date": max((c["price_date"] for c in cards["buy"] if c["price_date"]), default=day),
            "recheck": cards["buy"][0]["recheck"] if cards["buy"] else "",
            "share": f"{cards['buy'][0]['weight']:.0%}" if cards["buy"] and cards["buy"][0].get("weight") else "",
            "stale": (f"今日未能更新，沿用 {day} 的名单" if day != today.isoformat() else
                      f"今日部分数据获取失败（{'、'.join(failed)}），沿用上次的缓存数据" if failed else ""),
            "buys": cards["buy"], "lots": lot_money(cards["buy"], unit), "holds": cards["hold"], "sells": cards["sell"],
            "vetoes": cards["veto"],
            "removed": cards["removed"],
            "changes": changes(market, today.isoformat(), cards["buy"], log, table), "review": review_status(cards)}


def review_status(cards: dict) -> str:
    """The section's line on the review when not every name was reviewed (empty when all were, or no review ran)."""
    lines = [c["review"] for k in ("buy", "hold", "sell") for c in cards[k] if c.get("review")]
    counts = {s: sum(x.startswith(s) for x in lines) for s in ("审核进行中", "审核暂不可用")}
    return "；".join(f"{s} {n} 只" for s, n in counts.items() if n) + ("（完成后下次请求即可看到）" if counts["审核进行中"] else "")


def read_lists(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"code": str, "price_date": str, "recheck": str, "period": str})


def fresh(today: date, budget: float | None) -> tuple[Path, str, pd.DataFrame]:
    """The report on request: each market's newest lists reviewed (within `budget` seconds; None: until done), then
    built with the review applied."""
    started, lists_, sources = time.monotonic(), {}, {}
    for market in MARKETS:
        if path := latest_lists(market, today):
            lists_[market], sources[market] = read_lists(path), review.load_sources(market, path.parent.name)
    out = build(today, review.run(lists_, sources, today, budget))
    log.info("reviewed report built in %.1fs", time.monotonic() - started)
    return out


def build(today: date, states: dict | None = None) -> tuple[Path, str, pd.DataFrame]:
    """Write report.html/.pdf and summary.txt for the day, with the results review applied when given (states: market
    -> code -> review state); returns the PDF path, the summary and the buys it names (market, ticker, name, listed:
    the lists' date), which the sender logs once the text has gone out (track.log_sent)."""
    out = REPORTS / today.isoformat()
    status = out / "fetch_failed.json"
    failed = json.loads(status.read_text(encoding="utf-8")) if status.exists() else {}
    markets, logged, sent = [], {}, track.load_sent()
    for market in MARKETS:
        path = latest_lists(market, today)
        if not path:
            continue
        rows = read_lists(path)
        period = rows.drop_duplicates("code").set_index("code")["period"] if "period" in rows else pd.Series(dtype=str)
        confirmed = {c: v for c, v in verdicts.active(market, today, period).items() if v["verdict"] == "confirm"}
        rows = review.apply(rows, market, None if states is None else states.get(market, {}), confirmed)
        if path.parent.name == today.isoformat():  # the scoreboard follows removed names against their replacements
            replacing = rows[rows["list"].isin(["buy", "hold"]) & rows["replaces"].notna()].assign(list="replacement")
            logged[market] = pd.concat([rows[rows["list"].isin(["buy", "hold", "sell", "removed"])], replacing]).rename(
                columns={"list": "bucket"})
        markets.append(section(market, rows, path.parent.name, today, failed.get(market, []), sent))
    if not markets:
        raise SystemExit(f"no lists CSV in {REPORTS}; run `run` first")
    if logged and today == date.today():  # a past day's record isn't rewritten by re-rendering its report
        track.log_picks(today, logged)
    size_gb = (size_of(DATA) + size_of(REPORTS)) / 1e9
    report = {"title": "股票报告", "date": today.isoformat(), "markets": markets, "guide": GUIDE, "method": METHOD,
              "common": COMMON,
              "storage_warning": (f"注意：data/ + reports/ 已占用 {size_gb:.1f} GB，超过 {CONFIG['storage']['warn_gb']} GB 上限。"
                                  if size_gb > CONFIG["storage"]["warn_gb"] else "")}
    out.mkdir(parents=True, exist_ok=True)
    pdf = html_to_pdf(render_html(report, out / "report.html"), out / "report.tmp.pdf").replace(out / "report.pdf")
    buys = pd.DataFrame([{"market": m["code"].lower(), "ticker": b["ticker"], "name": b["name"], "listed": m["day"]}
                         for m in markets for b in m["buys"]], columns=["market", "ticker", "name", "listed"])
    summary = text_summary(report, deliver.MAX_TEXT_BYTES)
    (out / "summary.tmp").write_text(summary, encoding="utf-8")
    (out / "summary.tmp").replace(out / "summary.txt")  # the listener may send the report at any moment
    return pdf, summary, buys


def newest() -> tuple[str, Path, str] | None:
    """(date, PDF, summary) of the newest complete report, or None."""
    for folder in sorted(REPORTS.glob("????-??-??"), reverse=True):
        pdf, summary = folder / "report.pdf", folder / "summary.txt"
        if pdf.exists() and summary.exists():
            return folder.name, pdf, summary.read_text(encoding="utf-8")
    return None
