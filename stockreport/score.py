"""The score (PLAN.md, "The score: four families, equal weights"): a family is the percentile rank among the stock's
peers (its sector, financials apart; signals.peers) of the mean of its components' percentiles (a missing component
skipped, a missing family 50), so each family spreads alike, as Stockopedia ranks each family before combining them,
and a stock is judged against its own sector, as Seeking Alpha's quant grades and MSCI's multi-factor indexes judge
it. The score is the mean of the four. Grades A-E are fifths of each family among the peers; a card's why-line names
its two strongest components, its key risk a loss, heavy debt, a 30%+ fall in 6 months, or else its weakest component.
The distress logit (signals.distress) goes with the score for the buys' screen (lists.screened)."""

import pandas as pd

from stockreport.config import CONFIG
from stockreport.signals import FAMILIES, components, distress, peer_rank, peers, percentiles

NAMES = {"value": "价值", "quality": "质量", "growth": "成长", "momentum": "动量"}
SIGNED = {"cash", "mom", "sue", "rev", "rg", "pg", "roe5"}  # worded by the figure's sign; the rest by the peers' median
WORDS = {  # component -> (good, bad, the figure shown)
    "ep": ("市盈率低", "市盈率高", lambda x: f"PE {1 / x:.1f}" if x > 0 else "亏损"),
    "fep": ("预期市盈率低", "预期市盈率高", lambda x: f"明年 PE {1 / x:.1f}" if x > 0 else "明年预期亏损"),
    "bp": ("市净率低", "市净率高", lambda x: f"PB {1 / x:.2f}"),
    "sp": ("市销率低", "市销率高", lambda x: f"PS {1 / x:.2f}"),
    "roe": ("ROE 高", "ROE 低", lambda x: f"{x:.0%}"),
    "gpa": ("毛利/总资产高", "毛利/总资产低", lambda x: f"{x:.0%}"),
    "cash": ("经营现金流多于利润", "利润缺少现金支撑", lambda x: f"差额占营收 {x:+.0%}"),
    "debt": ("负债率低", "负债率高", lambda x: f"{x:.0%}"),
    "mom": ("近一年股价走强", "近一年股价走弱", lambda x: f"{x:+.0%}"),
    "sue": ("最新季度扣非利润好于往年同期", "最新季度扣非利润差于往年同期", lambda x: f"SUE {x:+.1f}"),
    "rev": ("分析师 3 个月上调明年盈利预测", "分析师 3 个月下调明年盈利预测", lambda x: f"相当于股价的 {x:+.1%}"),
    "ev": ("企业价值/息税前利润低", "企业价值/息税前利润高", lambda x: f"EV/EBIT {1 / x:.1f}" if x > 0 else "EBIT 为负"),
    "dy": ("股息率高", "股息率低", lambda x: f"{x:.1%}"),
    "prof8": ("8 年平均回报率高", "8 年平均回报率低", lambda x: f"{x:.0%}"),
    "gm8": ("毛利率多年稳定", "毛利率多年波动大", lambda x: f"均值/标准差 {x:.1f}"),
    "vol": ("股价波动小", "股价波动大", lambda x: f"年化 {x:.0%}"),
    "rg": ("营收同比增长", "营收同比下降", lambda x: f"{x:+.0%}"),
    "pg": ("利润同比增长", "利润同比下降", lambda x: f"{x:+.0%}"),
    "roe5": ("5 年利润增长", "5 年利润下降", lambda x: f"相当于 5 年前净资产的 {x:+.0%}"),
}


DIGITS = 12  # a score's float noise is ~1e-16; real differences are at least 1/(4 × peers)


def ranked(df: pd.DataFrame) -> pd.DataFrame:
    """Best score first. An exact tie (common: each family is a percentile among a sector's few dozen peers) goes to the
    larger free-float value, then the lower code, so the same data always gives the same order and lists. Scores are
    compared at DIGITS decimals: equal means can differ in the last bit of a float (25/29 as 26,28,20,26 and as
    29,16,28,27), and a snapshot read back from CSV can too."""
    value = df["float_value"] if "float_value" in df else df["mcap"] if "mcap" in df else pd.Series(0.0, index=df.index)
    key = pd.DataFrame({"score": df["score"].round(DIGITS).to_numpy(), "value": value.to_numpy(),
                        "code": df.index.astype(str)})
    return df.iloc[key.sort_values(["score", "value", "code"], ascending=[False, False, True], kind="stable").index]


def grade(pct: pd.Series) -> pd.Series:
    """A for the top fifth of a family's percentile ranks among the peers, E for the bottom."""
    return pd.cut(pct, [0, 0.2, 0.4, 0.6, 0.8, 1], labels=list("EDCBA"), include_lowest=True).astype(str)


def score(df: pd.DataFrame, market: str, cn: pd.DataFrame | None = None, lines: bool = True) -> pd.DataFrame:
    """The universe plus each component (c_), its percentile (p_), the families (f_), grades (g_), the score, its
    rank in the market, and (`lines`) the card's lines."""
    comp = components(df, market, cn)
    pct, group = percentiles(comp, df, market), peers(df)
    out = pd.concat([df, comp.add_prefix("c_"), pct.add_prefix("p_")], axis=1).assign(peers=group)
    for fam, parts in FAMILIES.items():
        out[f"f_{fam}"] = peer_rank(pct[parts[market]].mean(axis=1), group).fillna(0.5)
        out[f"g_{fam}"] = grade(out[f"f_{fam}"])
    out["score"] = out[[f"f_{fam}" for fam in FAMILIES]].mean(axis=1).round(DIGITS)  # equal means compare equal
    out["score_rank"] = pd.Series(range(1, len(out) + 1), index=ranked(out).index)
    out["distress"] = distress(df)
    if lines and len(out):
        used = sorted({c for fam in FAMILIES.values() for c in fam[market]})
        out["why"], out["weak"], out["risk"] = zip(*(card_lines(row, used, market) for _, row in out.iterrows()))
    return out


def reads_well(row: pd.Series, c: str, market: str) -> bool:
    """A component's words are the good ones: a positive figure, else above the peers' median."""
    key = "roe" if c == "gpa" and market == "us" and row["financial"] else c
    return bool(row[f"c_{key}"] > 0) if key in SIGNED else bool(row[f"p_{c}"] >= 0.5)


def phrase(row: pd.Series, c: str, market: str) -> str:
    """A component in words: by its sign, else by its side of the peers' median (同行 when the peers are a sector)."""
    key = "roe" if c == "gpa" and market == "us" and row["financial"] else c  # US financials' profitability is ROE
    good, bad, fmt = WORDS[key]
    x = row[f"c_{key}"]
    change = row["est_now"] / row["est_90"] - 1 if key == "rev" and row.get("est_90", 0) > 0 else None
    figure = fmt(x) if change is None else f"{change:+.1%}" if abs(change) < 0.1 else f"{change:+.0%}"
    words = good if reads_well(row, c, market) else bad
    peers = "" if key in SIGNED or str(row.get("peers", "")).startswith("全市场") else "同行中" + " " * words[0].isascii()
    text = f"{peers}{words}（{figure}）"
    return text.replace("市盈率", "扣非市盈率") if market == "cn" and c == "ep" else text


def card_lines(row: pd.Series, used: list[str], market: str) -> tuple[str, str, str]:
    """The two strongest components that read well (else the strongest), the two weakest that read badly (else the
    weakest), and the key risk: a loss, heavy debt, a big fall, else the weakest that reads badly, else 无明显短板."""
    have = sorted((c for c in used if pd.notna(row[f"p_{c}"])), key=lambda c: row[f"p_{c}"])
    bad = [c for c in have if not reads_well(row, c, market)]
    good = [c for c in reversed(have) if reads_well(row, c, market)]
    why = "；".join(phrase(row, c, market) for c in (good or have[::-1])[:2])
    weak = "；".join(phrase(row, c, market) for c in (bad or have)[:2])
    cfg, facts = CONFIG["cards"], []
    if row["np_ttm"] <= 0:
        facts.append("近 12 个月亏损")
    if not row["financial"] and row["debt_ratio"] >= cfg["heavy_debt"]:
        facts.append(f"负债率 {row['debt_ratio']:.0%}")
    if row.get("ret_6m", 0) <= cfg["big_fall"]:
        facts.append(f"近 6 个月下跌 {-row['ret_6m']:.0%}")
    risk = "；".join(facts) or (f"最弱一项：{phrase(row, bad[0], market)}" if bad else "无明显短板" if have else "")
    return why, weak, risk
