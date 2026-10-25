"""The score (PLAN.md, "The score: three families, equal weights"): a family is the percentile rank of the mean of its
components' percentiles (a missing component skipped, a missing family 50), so each family spreads alike, as
Stockopedia ranks each family before combining them; value and quality, whose components differ for financials, are
ranked among financials and among the rest, so a one-component mean doesn't outrank three-component ones. The score
is the mean of the three. Grades A-E are fifths of each
family; a card's why-line names its two strongest components, its key risk a loss, heavy debt, a 30%+ fall in
6 months, or else its weakest component."""

import pandas as pd

from stockreport.config import CONFIG
from stockreport.signals import FAMILIES, components, percentiles

NAMES = {"value": "价值", "quality": "质量", "momentum": "动量"}
BY_GROUP = {"value", "quality"}  # ranked among financials and among the rest (fewer components spread wider)
SIGNED = {"cash", "mom", "sue"}  # worded by the figure's sign; the others by their side of the market's median
WORDS = {  # component -> (good, bad, the figure shown)
    "ep": ("市盈率低", "市盈率高", lambda x: f"PE {1 / x:.1f}" if x > 0 else "亏损"),
    "bp": ("市净率低", "市净率高", lambda x: f"PB {1 / x:.2f}"),
    "sp": ("市销率低", "市销率高", lambda x: f"PS {1 / x:.2f}"),
    "roe": ("ROE 高", "ROE 低", lambda x: f"{x:.0%}"),
    "gpa": ("毛利/总资产高", "毛利/总资产低", lambda x: f"{x:.0%}"),
    "cash": ("经营现金流多于利润", "利润缺少现金支撑", lambda x: f"差额占营收 {x:+.0%}"),
    "debt": ("负债率低", "负债率高", lambda x: f"{x:.0%}"),
    "mom": ("近一年股价走强", "近一年股价走弱", lambda x: f"{x:+.0%}"),
    "sue": ("最新季度扣非利润好于往年同期", "最新季度扣非利润差于往年同期", lambda x: f"SUE {x:+.1f}"),
}


def grade(x: pd.Series) -> pd.Series:
    """A for the top fifth of the market, E for the bottom fifth."""
    return pd.cut(x.rank(pct=True), [0, 0.2, 0.4, 0.6, 0.8, 1], labels=list("EDCBA")).astype(str)


def score(df: pd.DataFrame, market: str, cn: pd.DataFrame | None = None, lines: bool = True) -> pd.DataFrame:
    """The universe plus each component (c_), its percentile (p_), the families (f_), grades (g_), the score, its
    rank in the market, and (`lines`) the card's lines."""
    comp = components(df, market, cn)
    pct = percentiles(comp, df, market)
    out = pd.concat([df, comp.add_prefix("c_"), pct.add_prefix("p_")], axis=1)
    for fam, parts in FAMILIES.items():
        mean = pct[parts[market]].mean(axis=1)
        ranked = mean.groupby(df["financial"].astype(bool)).rank(pct=True) if fam in BY_GROUP else mean.rank(pct=True)
        out[f"f_{fam}"] = ranked.fillna(0.5)
        out[f"g_{fam}"] = grade(out[f"f_{fam}"])
    out["score"] = out[[f"f_{fam}" for fam in FAMILIES]].mean(axis=1)
    out["score_rank"] = out["score"].rank(ascending=False, method="first").astype(int)
    if lines and len(out):
        used = sorted({c for fam in FAMILIES.values() for c in fam[market]})
        out["why"], out["weak"], out["risk"] = zip(*(card_lines(row, used, market) for _, row in out.iterrows()))
    return out


def phrase(row: pd.Series, c: str, market: str) -> str:
    key = "roe" if c == "gpa" and market == "us" and row["financial"] else c  # US financials' profitability is ROE
    good, bad, fmt = WORDS[key]
    x = row[f"c_{key}"]
    text = f"{good if (x > 0 if key in SIGNED else row[f'p_{c}'] >= 0.5) else bad}（{fmt(x)}）"
    return text.replace("市盈率", "扣非市盈率") if market == "cn" and c == "ep" else text


def card_lines(row: pd.Series, used: list[str], market: str) -> tuple[str, str, str]:
    """The two strongest components, the two weakest, and the key risk."""
    have = sorted((c for c in used if pd.notna(row[f"p_{c}"])), key=lambda c: row[f"p_{c}"])
    why = "；".join(phrase(row, c, market) for c in reversed(have[-2:]))
    weak = "；".join(phrase(row, c, market) for c in have[:2])
    cfg, facts = CONFIG["cards"], []
    if row["np_ttm"] <= 0:
        facts.append("近 12 个月亏损")
    if not row["financial"] and row["debt_ratio"] >= cfg["heavy_debt"]:
        facts.append(f"负债率 {row['debt_ratio']:.0%}")
    if row.get("ret_6m", 0) <= cfg["big_fall"]:
        facts.append(f"近 6 个月下跌 {-row['ret_6m']:.0%}")
    weakest = f"{'最弱一项' if have and row[f'p_{have[0]}'] < 0.5 else '无明显短板，最弱一项'}：" + (phrase(row, have[0], market) if have else "")
    risk = "；".join(facts) or (weakest if have else "")
    return why, weak, risk
