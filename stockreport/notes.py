"""AI notes (PLAN.md, "Results review" and "Cards"): the card text DeepSeek reads in the results review, and the note
it writes back. The note is words only (rule 2): one with any digit is dropped, so a number on a card always comes
from code and data."""

import re

import pandas as pd

MARKET_NAMES = {"cn": "A股", "us": "美股", "hk": "港股"}
NOTE_MAX = 40  # width in Chinese characters; digits, Latin letters and ASCII symbols count half


def card(row: dict, market: str, role: str) -> str:
    """The card's own lines for one name, as DeepSeek reads them."""
    rank = int(row["rank"]) if pd.notna(row.get("rank")) else None
    where = {"buy": f"买入组合第 {rank} 名（评分最高的 20 只之一）", "next": "买入候补（排在买入组合之后，有买入被剔除时替补）",
             "holding": f"你的持仓，持仓检查结论：{row.get('status')}（{row.get('reason')}）",
             "avoid": "回避名单（市值前 400 中评分最低）"}[role]
    graded = pd.notna(row.get("g_value"))
    lines = [f"股票：{row['code']} {row['name']}（{MARKET_NAMES[market]}，行业：{row.get('sector') or '未知'}）", f"名单：{where}",
             f"评级：价值{row['g_value']} 质量{row['g_quality']} 动量{row['g_momentum']}（A 最好，E 最差）；"
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


def words_only(text) -> str:
    """The AI note as shown: '' when it has a digit (it may only use words), else at most NOTE_MAX wide."""
    text = " ".join(str(text or "").split())
    return "" if re.search(r"[0-9０-９]", text) else shorten(text, NOTE_MAX)
