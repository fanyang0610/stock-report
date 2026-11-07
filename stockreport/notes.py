"""AI notes (PLAN.md, "Results review" and "Cards"): the card text DeepSeek reads in the results review, and the words
it writes back in that same call: the note, and one Chinese line on what a company does from the text code fetched
(PLAN.md, "Report"). Both are words only (rule 2): a note with any figure is dropped, so a number on a card always
comes from code and data, and so is a line."""

import re

import pandas as pd

from stockreport.fetch import profiles

MARKET_NAMES = {"cn": "A股", "us": "美股", "hk": "港股"}
NOTE_MAX = 40  # width in Chinese characters; digits, Latin letters and ASCII symbols count half


def card(row: dict, market: str, role: str) -> str:
    """The card's own lines for one name, as DeepSeek reads them."""
    rank = int(row["rank"]) if pd.notna(row.get("rank")) else None
    where = {"buy": f"评级买入，第 {rank} 名（预计跑赢大盘：评分最高的 20 只之一）", "next": "买入候补（有买入被剔除时替补）",
             "hold": f"评级持有，第 {rank} 名（评分居中、不偏涨也不偏跌：大公司里股价最稳的 10 只之一；{row.get('reason')}）",
             "hold_next": "持有候补（有持有被剔除时替补）",
             "sell": f"评级卖出，第 {rank} 名（预计跑输大盘：市值前 400 中评分最低的 10 只之一）"}[role]
    graded = pd.notna(row.get("g_value"))
    lines = [f"股票：{row['code']} {row['name']}（{MARKET_NAMES[market]}，行业：{row.get('sector') or '未知'}）", f"名单：{where}",
             f"评级：价值{row['g_value']} 质量{row['g_quality']} 成长{row['g_growth']} 动量{row['g_momentum']}（A 最好，E 最差）；"
             f"理由：{row.get('why')}；风险：{row.get('risk')}" if graded else "评级：今日未评分"]
    return "\n".join(lines)


def width(text: str) -> float:
    """Length in Chinese characters: digits, Latin letters and ASCII symbols count as half."""
    return sum(0.5 if ord(ch) < 128 else 1 for ch in text)


def shorten(text: str, limit: int) -> str:
    """Fit `text` in `limit` by ending at the last clause break, so it never stops mid-phrase."""
    if width(text) <= limit:
        return text
    head, used = "", 0.0
    for ch in text:
        used += width(ch)
        if used > limit - 1:  # room for the closing 。
            break
        head += ch
    stop = max(head.rfind(mark) for mark in "。；，、")
    if stop < len(head) // 2:  # no break in the second half: hard cut
        return head + "…"
    return head[:stop] + "。"


FIGURE = re.compile(r"[0-9０-９]|[零〇一二两三四五六七八九十百千万]+(成|倍|个百分点|亿|万元|元|美元|港元)|百分之")


def words_only(text) -> str:
    """The AI note as shown: '' when it has a figure (a digit, or one written in characters like 三成: it may only use
    words), else at most NOTE_MAX wide."""
    text = " ".join(str(text or "").split())
    return "" if FIGURE.search(text) else shorten(text, NOTE_MAX)


SHORT = 50  # a CN/HK business sentence this wide is shown as the source writes it; a longer one, and US's, get a line


def needs_line(market: str, source) -> bool:
    """A US text (English) or a CN/HK one too long to show as written gets a line from the review."""
    return isinstance(source, str) and bool(source) and (market == "us" or width(profiles.first(source)) > SHORT)


def line(text) -> str:
    """The company line as kept: Chinese, without a figure (FIGURE), at most SHORT wide; else '' (the card shows the
    source cut to size)."""
    text = " ".join(str(text or "").split()).strip("「」\"“”")
    return shorten(text, SHORT) if re.search(r"[\u4e00-\u9fff]", text) and not FIGURE.search(text) else ""
