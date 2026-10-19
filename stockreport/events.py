"""Event layer (PLAN.md Method 14, docs/REVIEW.md A2.8): announcements from the market-wide daily feeds
(stockreport/fetch/events.py), classified by rules, and abnormal price moves on the picks labelled with or
without a matching event. Events only label the cards; numbers from a filing come from the deep-dive lane."""

import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch.events import load
from stockreport.track import INDEX

KINDS = {"earnings": "业绩", "deal": "交易", "risk": "风险", "capital": "股本", "holders": "增减持", "business": "经营",
         "other": "其他"}
INDEX_NAMES = {"cn": "沪深300", "hk": "恒指", "us": "标普500"}
# Title (CN; HK: title and HKEX's headline category) patterns, tried in this order after the routine ones.
# The exchange-mandated 股票交易异常波动 notice says nothing new, so it never "explains" a move.
RULES = {
    "cn": [("routine", r"法律意见|核查意见|股东会决议|股东大会决议|召开.*股东|股东.*通知|董事会.*决议|监事会|独立董事|工作细则|"
                       r"制度|章程|鉴证报告|保荐|路演|翌日披露|异常波动|专门委员会|职工代表|选举|聘任|授信|担保|套期保值|"
                       r"募集资金|摘要|英文|更正|工商变更|证券事务代表|会计师事务所|内部控制|社会责任|ESG|转股|赎回|融资券|公司债|"
                       r"会议资料|H股公告|已回购股份|通知债权人|资本债|永续债|中期票据|短期融资|债券.*(发行结果|付息|兑付|评级)"),
           ("deal", r"重大资产重组|重组|收购|出售|吸收合并|换股|要约|股权转让|资产置换|购买资产|控制权|分拆|私有化|筹划"),
           ("risk", r"立案|调查|处罚|警示|监管函|问询函|关注函|诉讼|仲裁|退市|终止上市|停牌|停业|\*?ST|无法表示|保留意见|否定意见|持续经营|冻结|"
                    r"违规|逾期|失信|破产|重整|减值"),
           ("earnings", r"业绩|预增|预减|预亏|扭亏|季度报告|年度报告|半年度报告|利润"),
           ("capital", r"回购|增发|向特定对象发行|定向发行|配股|可转换|可转债|股权激励|限制性股票|股票期权|员工持股|权益分派|"
                       r"利润分配|分红|送转|注销|解除限售|上市流通|发行.*股票"),
           ("holders", r"减持|增持|质押|权益变动|持股.*变动"),
           ("business", r"合同|中标|订单|协议|合作|批准|注册证|一致性评价|临床|投产|项目|专利|产品")],
    "hk": [("routine", r"通知信函|回條|董事名單|董事會召開日期|股東周年大會|股東特別大會|股東大會|投票結果|更換董事|"
                       r"董事委任|董事辭任|董事委員會|決議|環境、社會及管治|股份計劃|股份獎勵|購股權|章程|職權範圍|英文版面|"
                       r"法律意見|債券|理財|擔保|致.*股東|函件|任職資格|註冊辦事處|營業地點|聘任.*核數師|續聘|投資者關係|說明會|"
                       r"票據|^海外監管公告$"),
           ("earnings", r"盈利警告|盈利預告|業績"),
           ("deal", r"須予披露|主要交易|非常重大|關連交易|收購|出售|要約|私有化|合併|分拆|反收購|收購守則|協議安排|重組"),
           ("risk", r"停牌|暫停買賣|清盤|訴訟|調查|立案|處罰|處分|批評|紀律|除牌|更換核數師|核數師辭任|延遲|監管者|呈請|違約"),
           ("earnings", r"業績|盈利|虧損|年報|中期報告|季度報告|財務報表"),
           ("capital", r"購回|回購|配售|供股|發行股份|可換股|股息|派息|紅股|以股代息|股本"),
           ("holders", r"增持|減持|質押|抵押股份"),
           ("business", r"業務|合約|協議|合作|批准|項目|產品|營運|投資"),
           ("other", r"內幕消息")],
}
# HK document types (HKEX's top-level category) that are never news
HK_ROUTINE = r"翌日披露報表|月報表|交易所買賣基金|債券及結構性產品|委任代表表格|展示文件|槓桿及反向|公司資料報表"
# US: 8-K items, then forms (an 8-K whose items are all routine, e.g. 7.01 Reg FD or 9.01 exhibits, is routine)
US_ITEMS = {"2.02": "earnings", "1.01": "deal", "1.02": "deal", "2.01": "deal", "5.01": "deal", "1.03": "risk",
            "1.05": "risk", "2.04": "risk", "2.05": "risk", "2.06": "risk", "3.01": "risk", "4.01": "risk",
            "4.02": "risk", "2.03": "capital", "3.02": "capital", "3.03": "capital", "5.02": "other"}
US_FORMS = {"10-K": "earnings", "10-Q": "earnings", "20-F": "earnings", "40-F": "earnings", "6-K": "other",
            "SC TO-T": "deal", "SC TO-I": "capital", "SC 14D9": "deal", "PREM14A": "deal", "DEFM14A": "deal",
            "S-4": "deal", "NT 10-K": "risk", "NT 10-Q": "risk", "15-12B": "risk", "25-NSE": "risk"}


def classify(market: str, row: dict) -> str:
    """One kind per filing, by rules (KINDS or 'routine'); unmatched non-routine filings are 'other'."""
    if market == "us":
        form = (row.get("form") or "").removesuffix("/A")
        if form == "8-K":
            kinds = [US_ITEMS[i] for i in str(row.get("items") or "").split(",") if i in US_ITEMS]
            return min(kinds, key=list(KINDS).index) if kinds else "routine"
        return US_FORMS.get(form, "routine")
    if market == "cn":
        return match("cn", row["title"])
    # HK: the title first (A+H issuers' reposts of their A-share filings without the prefix), else HKEX's category
    category = row.get("category") or ""
    if re.search(HK_ROUTINE, category.split(" - ")[0]):
        return "routine"
    kind = match("hk", re.sub(r"^海外監管公告\s*-?\s*", "", row["title"]))
    return match("hk", category) if kind == "other" else kind


def match(market: str, text: str) -> str:
    for kind, pattern in RULES[market]:
        if re.search(pattern, text):
            return kind
    return "other"


def daily(prices: pd.DataFrame, codes: set[str], end: str, days: int) -> pd.DataFrame:
    """Log returns by trading day (rows: the index's calendar up to `end`, the last `days`) and code."""
    p = prices[prices["code"].isin(codes) & (prices["date"] <= end)]
    r = np.log(p["close"] / p["prev_close"]).groupby([p["date"], p["code"]]).last().unstack()
    return r.tail(days)


def move(excess: pd.Series, k_max: int, z_min: float) -> dict | None:
    """The 1..k_max-day excess return ending on the last day with the largest |z|, against the sd of daily
    excess returns over the year before it; None unless |z| ≥ z_min."""
    hist = excess.iloc[:-k_max].dropna()
    sd = hist.std()
    if len(hist) < 60 or not sd > 0:
        return None
    best = max(((k, excess.iloc[-k:].sum()) for k in range(1, k_max + 1)), key=lambda x: abs(x[1]) / np.sqrt(x[0]))
    k, total = best
    z = total / (sd * np.sqrt(k))
    if abs(z) < z_min or np.isnan(z):
        return None
    return {"start": excess.index[-k], "end": excess.index[-1], "days": k, "ret": np.expm1(total), "z": z,
            "before": excess.index[-k - 1]}


def short(title: str, n: int = 28) -> str:
    title = re.sub(r"^(.{2,40}?(股份)?有限公司|.{2,8}：)", "", title).strip("：: ")
    return title if len(title) <= n else title[:n] + "…"


def lines(market: str, picks: pd.DataFrame, today: date) -> dict[str, dict]:
    """Per pick: up to 3 recent non-routine filings (近期事件) and its abnormal move against the index, labelled
    with the filing that matches it (from the trading day before the move to its last day) or as probable noise."""
    cfg, ev = CONFIG["events"], load(market)
    ev = ev[ev["code"].isin(picks["code"])].sort_values("date", ascending=False)
    since = (today - timedelta(days=cfg["recent_days"])).isoformat()
    path = DATA / "prices" / f"{market}.csv.gz"
    prices = pd.read_csv(path, dtype={"code": str, "date": str}) if path.exists() else \
        pd.DataFrame(columns=["date", "code", "close", "prev_close"])
    index, out = INDEX[market], {}
    for end, part in picks.groupby(picks["price_date"].astype(str)):
        r = daily(prices, set(part["code"]) | {index}, end, 260)
        for code in part["code"]:
            mine = ev[ev["code"] == code]
            recent = mine[mine["date"] >= since]  # classified filings before unclassified ones, newest first
            recent = recent.iloc[(recent["kind"] == "other").argsort(kind="stable")].head(cfg["max_lines"])
            found = move(r[code] - r[index], cfg["move_days"], cfg["move_z"]) if code in r and index in r else None
            text = "；".join(f"{d[5:]} {KINDS[k]}：{short(t)}" for d, k, t in
                            recent[["date", "kind", "title"]].itertuples(index=False))
            item = {"events": text or f"近 {cfg['recent_days']} 日无重要公告", "move": "", "matched": None}
            if found:
                match = mine[(mine["date"] >= found["before"]) & (mine["date"] <= found["end"])]
                span = f"{found['days']} 日" if found["days"] > 1 else "单日"
                head = f"{found['end'][5:]} 前{span}相对{INDEX_NAMES[market]} {found['ret']:+.1%}（{found['z']:+.1f}σ）"
                item["matched"] = bool(len(match))
                if len(match):
                    d, k, t = match.iloc[0][["date", "kind", "title"]]
                    item["move"] = f"异动：{head}，对应 {d[5:]} {KINDS[k]}公告：{short(t)}"
                else:
                    item["move"] = f"异动：{head}，未见对应公告，按噪音处理（估值不变）"
            out[code] = item
    return out
