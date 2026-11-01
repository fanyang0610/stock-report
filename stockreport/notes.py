"""AI notes (PLAN.md, "Results review" and "Cards"): the card text DeepSeek reads in the results review, and the note
it writes back. The note is words only (rule 2): one with any digit is dropped, so a number on a card always comes
from code and data. lines() writes one Chinese line on what a company does from the text code fetched (PLAN.md,
"Report"), words only too."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor

import httpx
import pandas as pd

from stockreport.config import CONFIG
from stockreport.fetch import profiles

log = logging.getLogger(__name__)

MARKET_NAMES = {"cn": "A股", "us": "美股", "hk": "港股"}
NOTE_MAX = 40  # width in Chinese characters; digits, Latin letters and ASCII symbols count half


def card(row: dict, market: str, role: str) -> str:
    """The card's own lines for one name, as DeepSeek reads them."""
    rank = int(row["rank"]) if pd.notna(row.get("rank")) else None
    where = {"buy": f"买入组合第 {rank} 名（评分最高的 20 只之一）", "next": "买入候补（排在买入组合之后，有买入被剔除时替补）",
             "holding": f"你的持仓，持仓检查结论：{row.get('status')}（{row.get('reason')}）",
             "avoid": f"回避名单第 {rank} 名（市值前 400 中评分最低的 10 只之一）"}[role]
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


LINE = ("把用户给的公司业务介绍（中文或英文）写成一句简短的中文，说明这家公司主要做什么，不超过 25 个字，可以省略地区和细项。"
        "只用介绍里已有的内容，不加评价，不写任何数字，不写公司名称。只输出这句中文。")
SHORT = 50  # a CN/HK business sentence this wide is shown as the source writes it; a longer one, and US's, get a line


def needs_line(market: str, source) -> bool:
    return isinstance(source, str) and bool(source) and (market == "us" or width(profiles.first(source)) > SHORT)


def lines(client: httpx.Client, workers: int = 10) -> int:
    """One Chinese line per company whose business text is English (US) or too long to show (CN/HK), and has no line
    yet: one DeepSeek call each (temperature 0, only that text in), kept only in Chinese and without a figure (FIGURE),
    else marked dropped and the card shows the source cut to size. A failed call is asked again at the next review.
    Returns the lines kept."""
    def one(text: str) -> str | None:
        try:
            resp = client.post("/chat/completions", json={
                "model": CONFIG["notes"]["model"], "temperature": 0, "thinking": {"type": "disabled"},
                "max_tokens": 120, "messages": [{"role": "system", "content": LINE}, {"role": "user", "content": text}]})
            resp.raise_for_status()
            line = " ".join(resp.json()["choices"][0]["message"]["content"].split()).strip("「」\"“”")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as e:
            log.warning("business line: %s", e)
            return None
        return shorten(line, SHORT) if re.search(r"[\u4e00-\u9fff]", line) and not FIGURE.search(line) else ""

    kept = 0
    for market in MARKET_NAMES:
        table = profiles.load(market)
        todo = table[table["line"].isna() & table["source"].map(lambda x: needs_line(market, x))]
        with ThreadPoolExecutor(workers) as pool:
            got = dict(zip(todo.index, pool.map(one, todo["source"])))
        if got:
            profiles.save_lines(market, got)
        kept += sum(bool(x) for x in got.values())
        log.info("%s business lines: %d of %d", market.upper(), sum(bool(x) for x in got.values()), len(got))
    return kept
