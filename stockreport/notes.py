"""AI notes (PLAN.md Method section 8). DeepSeek writes a short note and risk per pick from the
card's numbers plus recent announcement titles, and may flag a pick; a flagged pick is swapped for
the next-ranked runner-up in its bucket. The model never changes or produces numbers."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx
import pandas as pd
from dotenv import dotenv_values

from stockreport.config import CONFIG, REPORTS, ROOT
from stockreport.fetch import cninfo

log = logging.getLogger(__name__)
FLAGS = ("none", "one_off_gain", "pending_deal", "delisting_or_st", "data_suspect")
FLAG_WORDS = {"one_off_gain": "利润一次性/异常", "pending_deal": "重大交易进行中",
              "delisting_or_st": "退市/ST 风险", "data_suspect": "数据可疑"}
NOTE_MAX, RISK_MAX = 60, 30

SYSTEM = """你是 A 股研究助理，为程序生成的选股卡片写简短中文点评。卡片上的所有数字都由程序根据公开数据计算，你不能修改它们。
规则：
1. 只依据给出的数字和公告标题。不得给出任何新的价格、目标价、公允价、盈利预测或评分；可以引用给出的数字。
2. note：一到两句话，不超过 60 个字（数字、字母和标点都算），说明这个动作（买入 / 持有·不追高 / 卖出·回避）的主要依据和最需要注意的地方。
3. risk：不超过 30 个字（数字、字母和标点都算），最主要的风险。
4. flag 只能取以下之一，只有当数字或公告标题给出明确依据时才标记，否则为 none：
   - one_off_gain：估值所依据的近期利润被一次性或短期异常因素明显扭曲（非经常性损益、资产处置、投资收益、补贴，或周期高点、低基数反弹造成的利润暴增），不能代表正常盈利水平。
   - pending_deal：正在进行重大资产重组、收购、私有化、吸收合并或停牌筹划，股价主要由交易决定。
   - delisting_or_st：有退市风险警示、ST、可能终止上市，或被立案调查可能导致退市。
   - data_suspect：给出的数字彼此明显矛盾，或与公告标题明显不符。
5. reason：一句话说明 flag 的依据；flag 为 none 时写"无"。
增速、ROE 等指标已在全市场 2%/98% 分位截尾，处于截尾值说明实际值更极端。
只输出 JSON：{"note": "...", "risk": "...", "flag": "...", "reason": "..."}"""


def pct(x) -> str:
    return "无" if pd.isna(x) else f"{x:+.1%}"


def card_numbers(row: pd.Series) -> str:
    """The numbers DeepSeek sees: the card plus the metrics behind it."""
    num = lambda x, d=2: "无" if pd.isna(x) else f"{x:,.{d}f}"
    financial = row["method"] == "P/B+justified"  # margins, cash flow and leverage mean little for banks/brokers/insurers
    lines = [
        f"股票：{row['code']} {row['name']}（行业：{row['industry']}）",
        f"动作：{row['action']}；信心：{row['conviction']}",
        f"现价 {num(row['price'])}（{row['price_date']}）；公允价 低/中/高 {num(row['fv_low'])} / "
        f"{num(row['fv_mid'])} / {num(row['fv_high'])}；空间 {pct(row['upside'])}",
        f"估值方法：{row['method']}；按近期利润/净资产的公允价 {num(row['fv_trailing'])}；"
        f"按分析师一致预期 EPS 的公允价 {num(row['fv_forward'])}（覆盖分析师 {num(row['analysts'], 0)} 家）",
        f"最新报告期 {row['period']}；近 12 个月营收 {num(row['revenue_ttm'] / 1e8)} 亿元，"
        f"净利润 {num(row['np_ttm'] / 1e8)} 亿元",
        f"营收同比 {pct(row['rev_growth'])}；净利润同比 {pct(row['np_growth'])}；ROE {pct(row['roe'])}"
        + ("" if financial else f"；毛利率 {pct(row['gross_margin'])}"),
        ("" if financial else f"经营现金流/净利润 {num(row['cash_conv'])}；资产负债率 {pct(row['debt_ratio'])}；")
        + f"股息率 {pct(row['div_yield'])}；市盈率 TTM {num(row['pe'], 1)}；市净率 {num(row['pb'])}",
        f"过去 12 个月（剔除最近 1 个月）涨幅 {pct(row['mom_12_1'])}；年化波动率 {pct(row['vol_1y'])}",
        f"程序给出的驱动：{row['drivers']}；程序给出的主要短板：{row['key_risk']}",
    ]
    return "\n".join(lines)


class TooLong(ValueError):
    pass


def parse_reply(text: str, enforce_length: bool = True) -> dict:
    """Validate the model's JSON. Raises ValueError when it can't be used."""
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    obj = json.loads(text)
    out = {k: str(obj.get(k) or "").strip() for k in ("note", "risk", "flag", "reason")}
    if out["flag"] not in FLAGS:
        raise ValueError(f"unknown flag {out['flag']!r}")
    if not out["note"] or not out["risk"]:
        raise ValueError("empty note or risk")
    if len(out["note"]) > NOTE_MAX or len(out["risk"]) > RISK_MAX:
        if enforce_length:
            raise TooLong(f"note 有 {len(out['note'])} 字（上限 {NOTE_MAX}），risk 有 {len(out['risk'])} 字（上限 {RISK_MAX}）")
        cut = lambda t, n: t if len(t) <= n else t[:n - 1] + "…"
        out["note"], out["risk"] = cut(out["note"], NOTE_MAX), cut(out["risk"], RISK_MAX)
    return out


def ask(client: httpx.Client, content: str) -> dict:
    """One note; retried once on an API error or invalid reply. Text that is too long is sent back
    to be shortened, and cut if the second answer is still too long."""
    cfg, err = CONFIG["notes"], None
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]
    for attempt in (1, 2):
        try:
            resp = client.post("/chat/completions", json={
                "model": cfg["model"], "temperature": cfg["temperature"], "messages": messages,
                "thinking": {"type": "disabled"}, "response_format": {"type": "json_object"}})
            resp.raise_for_status()
            reply = resp.json()["choices"][0]["message"]["content"]
            return parse_reply(reply, enforce_length=attempt == 1)
        except TooLong as e:
            err = e
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"{e}。请缩短后重新输出完整 JSON。"}]
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as e:
            err = e
    raise RuntimeError(f"DeepSeek note failed: {type(err).__name__}: {err}")


def template_note(row: pd.Series) -> dict:
    """Used when notes are off or the API fails; the report still ships."""
    return {"note": f"程序生成：{row['drivers']}。", "risk": str(row["key_risk"]), "flag": "none",
            "reason": "", "source": "template"}


class Notes:
    """Notes per ticker for one market and day; DeepSeek notes are saved in reports/<date>/<market>_notes.json.
    With use_ai off, every pick gets the template note and that file is neither read nor written."""

    def __init__(self, market: str, today: date, use_ai: bool):
        self.today = today
        self.path = REPORTS / today.isoformat() / f"{market}_notes.json"
        self.cache, self.client, self.org_ids = {}, None, {}
        if not use_ai:
            return
        if self.path.exists():
            self.cache = json.loads(self.path.read_text(encoding="utf-8"))
        key = dotenv_values(ROOT / ".env").get("DEEPSEEK_API_KEY")
        if key:
            self.client = httpx.Client(base_url=CONFIG["notes"]["base_url"], timeout=60,
                                       headers={"Authorization": f"Bearer {key}"})
        else:
            log.warning("DEEPSEEK_API_KEY is missing from .env; using template notes")
        try:
            self.org_ids = cninfo.org_ids() if market == "cn" and key else {}
        except Exception as e:
            log.warning("CNINFO stock list failed (%s); notes get no announcement titles", e)

    def titles(self, code: str) -> list[str]:
        if code not in self.org_ids:
            return []
        cfg = CONFIG["notes"]
        try:
            return cninfo.titles(code, self.org_ids[code], self.today, cfg["title_days"], cfg["max_titles"])
        except Exception as e:
            log.warning("CNINFO titles for %s failed: %s", code, e)
            return []

    def fetch(self, row: pd.Series, titles: list[str]) -> dict:
        """Ask DeepSeek; touches no shared state, so it can run in worker threads."""
        if not self.client:
            return template_note(row)
        content = card_numbers(row) + "\n近 60 日公告标题：\n" + ("\n".join(titles) or "（无）")
        try:
            return ask(self.client, content) | {"source": CONFIG["notes"]["model"], "titles": titles}
        except RuntimeError as e:
            log.warning("%s %s: %s; using the template note", row["code"], row["name"], e)
            return template_note(row)

    def store(self, code: str, note: dict) -> None:
        self.cache[code] = note
        if note["source"] == "template":  # not saved, so a later run retries the API
            return
        saved = {k: v for k, v in self.cache.items() if v["source"] != "template"}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")

    def get(self, row: pd.Series) -> dict:
        if row["code"] not in self.cache:
            self.store(row["code"], self.fetch(row, self.titles(row["code"])))
        return self.cache[row["code"]]


def annotate(picks: pd.DataFrame, market: str, today: date, use_ai: bool = True) -> tuple[pd.DataFrame, list[dict]]:
    """Final picks with notes, and the swaps made. A flagged pick is replaced by the next runner-up
    in its bucket that isn't flagged; if none is left, it stays, marked 低信心."""
    notes = Notes(market, today, use_ai)
    todo = [r for _, r in picks[picks["role"] == "pick"].iterrows() if r["code"] not in notes.cache]
    titles = {r["code"]: notes.titles(r["code"]) for r in todo}  # one at a time, politely
    with ThreadPoolExecutor(CONFIG["notes"]["workers"]) as pool:
        for row, note in zip(todo, pool.map(lambda r: notes.fetch(r, titles[r["code"]]), todo)):
            notes.store(row["code"], note)

    rows, swaps = [], []
    for bucket, part in picks.groupby("bucket", sort=False):
        bench = [r for _, r in part[part["role"] == "runner_up"].sort_values("rank").iterrows()]
        for _, row in part[part["role"] == "pick"].sort_values("rank").iterrows():
            note = notes.get(row)
            while note["flag"] != "none" and bench:
                nxt = bench.pop(0)
                swaps.append({"bucket": bucket, "out": f"{row['code']} {row['name']}", "flag": note["flag"],
                              "reason": note["reason"], "in": f"{nxt['code']} {nxt['name']}"})
                log.info("swap %s %s %s (%s: %s) -> %s %s", market, bucket, row["code"], note["flag"],
                         note["reason"], nxt["code"], nxt["name"])
                row, note = nxt, notes.get(nxt)
            if note["flag"] != "none":
                row = row.copy()
                row["conviction"] = "低信心"
            rows.append(row.to_dict() | {"note": note["note"], "ai_risk": note["risk"], "flag": note["flag"],
                                         "flag_reason": note["reason"], "note_source": note["source"]})
    return pd.DataFrame(rows), swaps
