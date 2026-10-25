"""Results review (PLAN.md, "Results review"; stage 2), only when you ask for a report. The build gathers each name's
sources without DeepSeek (gather(): non-routine filings of the last 90 days, fetch/filings.recent, and headlines of
the last 30, fetch/news). On request DeepSeek reads them at temperature 0 against a fixed checklist, JSON out; every
finding quotes one of those lines and code checks the quote (quotes.py), and a hard red flag must also name its
subject in the quote (KINDS) without denying it (deepdive.DENIAL). The 20 buys, the next 5, your holdings and the 10
avoid names are reviewed, buys first, `workers` calls at a time within `budget` seconds; each review is cached per
stock (data/review/<market>/<code>.json) and redone only for a name new to its list, a new filing or headline, or a
review over `keep_days` old. apply() turns the findings (and the deep-dive lane's, deepdive.py) into the lists."""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date

import httpx
import pandas as pd
from dotenv import dotenv_values

from stockreport import deepdive, notes, quotes
from stockreport.config import CONFIG, DATA, REPORTS, ROOT
from stockreport.fetch import filings, news

log = logging.getLogger(__name__)
CFG = CONFIG["review"]
CACHE = DATA / "review"
ROLES = ("buy", "next", "holding", "avoid")  # the review's order: buys first
# kind -> (words, hard red flag, what a hard flag's quote must name; a hard kind whose quote doesn't is a soft concern)
KINDS = {
    "investigation": ("监管立案调查或欺诈认定", True,
                      r"立案|调查|調查|稽查|留置|欺诈|欺詐|造假|虚假记载|investigat|probe|subpoena|Wells notice|fraud"),
    "audit": ("非标准审计意见或审计师辞任", True,
              r"保留意见|保留意見|否定意见|否定意見|无法表示意见|無法表示意見|辞任|辭任|辞职|辭職|qualified opinion|adverse opinion|"
              r"disclaimer of opinion|resign"),
    "going_concern": ("持续经营疑虑或债务违约", True,
                      r"持续经营|持續經營|重大不确定|违约|違約|逾期|无法兑付|清盘|清盤|破产|破產|重整|going concern|substantial doubt|"
                      r"default|bankrupt|Chapter 11|receivership|winding.up"),
    "delisting": ("退市、ST 或停牌", True,
                  r"退市|终止上市|終止上市|(?-i:(?<![A-Za-z])\*?ST(?![A-Za-z]))|风险警示|停牌|暫停買賣|除牌|delist|suspen|"
                  r"listing-rule failure"),
    "takeover": ("以固定价格被收购或私有化", True,
                 r"要约|要約|私有化|吸收合并|吸收合併|协议安排|協議安排|tender offer|merger proxy|privatization|go(ing)?.private|"
                 r"to be acquired|scheme of arrangement"),
    "sanctions": ("制裁或禁令", True, r"制裁|实体清单|實體清單|禁令|sanction|entity list|\bban\b|banned"),
    "downturn": ("行业下行或产品价格下跌", False, None),
    "customer": ("失去大客户或订单", False, None),
    "guidance": ("下调指引或业绩下滑", False, None),
    "management": ("高管离职或被调查", False, None),
    "litigation": ("诉讼或仲裁", False, None),
    "one_off": ("利润来自一次性收益", False, None),
    "other": ("其他负面事件", False, None),
}
STATUS = {"pending": "审核进行中", "unavailable": "审核暂不可用", "no_sources": "审核暂不可用（未取到公告和新闻）"}

SYSTEM = """你是上市公司审核员。下面是一只股票的卡片（程序根据公开数据计算）和它近 90 天的非例行公告标题、近 30 天的新闻标题，每条有编号。
按固定清单找事实，只依据给出的标题，不推断，不用你自己的知识。
硬风险（kind）：
- investigation：监管机构对公司或其控股股东、实际控制人立案调查，认定欺诈或财务造假，或 SEC 的 Wells notice；
- audit：非标准审计意见（保留、否定、无法表示意见），或审计师辞任；
- going_concern：持续经营存在重大疑虑，债务违约或逾期，破产、重整、清盘；
- delisting：本公司普通股（A 股、H 股或美股普通股）退市风险、被实施 ST 或 *ST、终止上市或停牌；优先股、债券、可转债的停牌或摘牌不算，
  美股 25-NSE、15-12B 表格标题没说明是普通股的也不算（常是债券到期或赎回）；
- takeover：本公司作为被收购方，被以固定价格收购、要约收购或私有化（本公司去收购别人不算）；
- sanctions：制裁、实体清单或禁令点名本公司。
软风险（kind，市场可能在担心的事）：downturn 行业下行或产品价格下跌；customer 失去大客户或订单；guidance 下调指引、业绩预减、预亏或明显下滑、盈利警告；
management 董事长、总经理（CEO）、财务总监（CFO）离职，或公司高管被调查；litigation 重大诉讼或仲裁；
one_off 利润主要来自一次性收益（出售资产、公允价值变动、补贴等收益；减值等一次性损失不算）；other 其他明确的负面事件。
规则：
1. 每条 finding 的 quote 必须从编号为 source 的那条标题里逐字复制：整条标题，或其中说明这件事的完整短语（至少 6 个字），不得改写、翻译、拼接或补字。
2. 只列与本公司有关的事；只讲整个市场或其他公司的标题不算，行业新闻只能算 downturn。同一件事只列一次，没有就输出空列表。
3. 不算风险的例行事项：董事会决议、股东大会、权益分派、回购和增持、业绩说明会，普通董事、监事、独立董事、董秘、证券代表的变动
   （美股 8-K 的 Director or officer change 没说明是董事长、CEO、CFO 的也算例行），股东或高管的减持计划，以及利好消息。
4. note：一句中文，不超过 40 个字，用文字说明这只股票为什么在这个名单上、最需要注意什么（参考卡片和 findings）；
   不得出现任何数字，不写价格、目标价或预测。
只输出 JSON：{"findings": [{"kind": "", "source": 1, "quote": ""}], "note": ""}"""
# A suspension or delisting of another security of the company (preferred shares, bonds, convertibles) isn't the stock's;
# nor is a bare SEC delisting or deregistration form, which doesn't say which security (often notes redeemed or matured)
OTHER_SECURITY = r"优先股|優先股|债券|債券|可转债|可轉債|转债|轉債|票据|票據|preferred|bond|notes due|warrant|25-NSE|15-12[BG]"


def gather(market: str, rows: pd.DataFrame, today: date, day: str | None = None) -> dict:
    """Each reviewed name's sources as of today -> reports/<day: the lists' date>/<market>_sources.json: {code:
    {filings, headlines}}, either None when its fetch failed. Filing searches run a few at a time (HKEXnews takes
    3-6 s each), headlines one at a time."""
    started, codes = time.monotonic(), list(dict.fromkeys(rows.loc[rows["list"].isin(ROLES), "code"]))
    filings.ids(market)  # the code -> filing id table, once before the threads
    http = news.client(market)

    def filed(code):
        try:
            return filings.recent(market, code, today, CFG["filing_days"])
        except Exception as e:
            log.warning("%s %s filings failed: %s", market, code, e)

    def heard(code):
        try:
            return news.headlines(http, market, code, today, CFG["headline_days"], CFG["max_headlines"])
        except Exception as e:
            log.warning("%s %s headlines failed: %s", market, code, e)

    with ThreadPoolExecutor(CFG["filing_workers"]) as fp, ThreadPoolExecutor(1) as hp:
        out = {c: {"filings": f, "headlines": h} for c, f, h in zip(codes, fp.map(filed, codes), hp.map(heard, codes))}
    path = REPORTS / (day or today.isoformat()) / f"{market}_sources.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    missing = [c for c, s in out.items() if s["filings"] is None or s["headlines"] is None]
    log.info("%s review sources for %d names in %.0fs%s", market.upper(), len(out), time.monotonic() - started,
             f"; incomplete: {' '.join(missing)}" if missing else "")
    return out


def load_sources(market: str, day: str) -> dict:
    path = REPORTS / day / f"{market}_sources.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def lines_of(src: dict) -> list[dict]:
    """The numbered source lines DeepSeek reads: the newest filings, then the newest headlines."""
    filed = [{"type": "公告", "date": f["date"], "title": f["title"], "kind": f["kind"]}
             for f in (src.get("filings") or [])[:CFG["max_filings"]]]
    return filed + [{"type": "新闻", "date": h["date"], "title": h["title"]} for h in src.get("headlines") or []]


def ids_of(lines: list[dict]) -> list[str]:
    return [f"{x['date']} {x['title']}" for x in lines]


def prompt(row: dict, market: str, role: str, lines: list[dict]) -> str:
    from stockreport.events import KINDS as FILING_KINDS
    numbered = [f"[{i}] {x['date']} {x['type']}{'（' + FILING_KINDS.get(x.get('kind'), '其他') + '）' if x['type'] == '公告' else ''}："
                f"{x['title']}" for i, x in enumerate(lines, 1)]
    return notes.card(row, market, role) + "\n来源：\n" + ("\n".join(numbered) or "（无）")


def ask(client: httpx.Client, content: str) -> dict:
    """The checklist's JSON answer; retried once on an API error or invalid JSON."""
    err = None
    for _ in (1, 2):
        try:
            resp = client.post("/chat/completions", json={
                "model": CONFIG["notes"]["model"], "temperature": 0, "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"}, "max_tokens": CFG["max_tokens"],
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]})
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip().removeprefix("```json").removesuffix("```")
            answer = json.loads(text)
            if isinstance(answer, dict):
                return answer
            err = ValueError("not a JSON object")
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
            err = e
    raise RuntimeError(f"review failed: {type(err).__name__}: {err}")


def verify(answer: dict, lines: list[dict]) -> tuple[list[dict], int]:
    """The findings whose quotes are in a source line (the cited one first; a short title quoted whole counts), with
    their kind's words and whether they are a hard red flag; and how many were rejected (quote not in any source)."""
    texts, found, rejected, seen = [quotes.norm(x["title"]) for x in lines], [], 0, set()
    for f in answer.get("findings") or []:
        if not isinstance(f, dict) or not f.get("quote"):
            continue
        quote, cited = quotes.norm(f["quote"]), f.get("source")
        order = ([cited - 1] if isinstance(cited, int) and 1 <= cited <= len(lines) else []) + list(range(len(lines)))
        at = next((i for i in order if quotes.find(texts[i], quote) >= 0 or (quote and quote == texts[i])), None)
        if at is None:
            rejected += 1
            log.info("review: quote not in its source, rejected: %s", f["quote"])
            continue
        kind = f.get("kind") if f.get("kind") in KINDS else "other"
        raw = " ".join(str(f["quote"]).split())
        if KINDS[kind][1] and deepdive.DENIAL.search(raw) or kind == "delisting" and re.search(OTHER_SECURITY, raw, re.I):
            continue  # "不存在立案调查的情形", or another security's suspension: not a finding about the stock
        if KINDS[kind][1] and not re.search(KINDS[kind][2], raw, re.I):
            kind = "other"
        if (kind, quote) not in seen:
            seen.add((kind, quote))
            src = lines[at]
            found.append({"kind": kind, "words": KINDS[kind][0], "hard": KINDS[kind][1], "quote": raw,
                          "date": src["date"], "type": src["type"]})
    return found, rejected


def cached(market: str, code: str) -> dict | None:
    path = CACHE / market / f"{code}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def valid(entry: dict | None, role: str, ids: list[str], today: date) -> bool:
    return bool(entry) and entry["role"] == role and set(ids) <= set(entry["sources"]) \
        and (today - date.fromisoformat(entry["date"])).days <= CFG["keep_days"]


def review_one(client: httpx.Client, market: str, row: dict, role: str, lines: list[dict], today: date) -> dict:
    """One name's review, saved to its cache file (written whole, so a reader never sees half of one)."""
    answer = ask(client, prompt(row, market, role, lines))
    findings, rejected = verify(answer, lines)
    entry = {"date": today.isoformat(), "role": role, "sources": ids_of(lines), "findings": findings,
             "rejected": rejected, "note": notes.words_only(answer.get("note"))}
    path = CACHE / market / f"{row['code']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{time.monotonic_ns()}.tmp")
    tmp.write_text(json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return entry


def run(lists: dict, sources: dict, today: date, budget: float | None) -> dict:
    """Review every market's names (lists: market -> rows; sources: market -> gather()'s dict) -> market -> code ->
    state ({status: done | pending | unavailable | no_sources, findings, note}). With a budget, reviews still running
    when it ends are left to finish in their threads (they save their caches) and the rest are cancelled."""
    states, jobs, started, hits = {}, [], time.monotonic(), 0
    for market, rows in lists.items():
        st = states.setdefault(market, {})
        for role in ROLES:
            for row in rows[rows["list"] == role].to_dict("records"):
                code, src = row["code"], sources.get(market, {}).get(row["code"])
                if code in st:
                    continue  # a holding that is also a buy is reviewed once, as the buy
                if not src or (src["filings"] is None and src["headlines"] is None):
                    st[code] = {"status": "no_sources"}
                    continue
                lines = lines_of(src)
                entry = cached(market, code)
                if valid(entry, role, ids_of(lines), today):
                    st[code], hits = entry | {"status": "done"}, hits + 1
                    continue
                st[code] = {"status": "pending"}
                rank = row["rank"] if pd.notna(row.get("rank")) else 99
                jobs.append(((ROLES.index(role), rank, list(lists).index(market)), market, row, role, lines))
    key = dotenv_values(ROOT / ".env").get("DEEPSEEK_API_KEY")
    if jobs and not key:
        log.warning("DEEPSEEK_API_KEY is missing from .env: no results review")
    if not jobs or not key:
        log.info("review: %d cached, %d to review%s", hits, len(jobs), "" if key or not jobs else " (no DeepSeek key)")
        return mark(states, "unavailable")
    client = httpx.Client(base_url=CONFIG["notes"]["base_url"], timeout=CFG["timeout"],
                          headers={"Authorization": f"Bearer {key}"})
    pool = ThreadPoolExecutor(CFG["workers"])
    futures = {pool.submit(review_one, client, m, row, role, lines, today): (m, row["code"])
               for _, m, row, role, lines in sorted(jobs, key=lambda j: j[0])}
    done, _ = wait(futures, timeout=budget)
    ok, failed = 0, 0
    for f in done:
        market, code = futures[f]
        try:
            states[market][code] = f.result() | {"status": "done"}
            ok += 1
        except Exception as e:
            states[market][code] = {"status": "unavailable"}
            failed += 1
            log.warning("review %s %s: %s", market, code, e)
    pool.shutdown(wait=budget is None, cancel_futures=True)
    log.info("review: %d cached, %d reviewed, %d failed, %d left after %.0fs", hits, ok, failed,
             len(jobs) - ok - failed, time.monotonic() - started)
    return mark(states, "unavailable") if failed and not ok else states


def mark(states: dict, status: str) -> dict:
    """Every pending review as `status` (DeepSeek down or no key)."""
    return {m: {c: ({"status": status} if s["status"] == "pending" else s) for c, s in st.items()} for m, st in states.items()}


def stats(states: dict) -> str:
    """One line per market: reviews by status, hard and soft findings, quotes rejected."""
    out = []
    for market, st in states.items():
        by = pd.Series([s["status"] for s in st.values()]).value_counts().to_dict()
        found = [f for s in st.values() for f in s.get("findings") or []]
        out.append(f"{market.upper()} review: " + ", ".join(f"{n} {k}" for k, n in by.items()) +
                   f"; {sum(f['hard'] for f in found)} hard, {sum(not f['hard'] for f in found)} soft findings; "
                   f"{sum(s.get('rejected', 0) for s in st.values())} quotes rejected")
    return "\n".join(out)


def cite(f: dict) -> str:
    quote = f["quote"] if len(f["quote"]) <= 60 else f["quote"][:60] + "…"
    return f"{f['words']}（{f['date']} {f['type']}：「{quote}」）"


def line(state: dict, found: list[dict]) -> str:
    """The card's review line: hard red flags, else data_suspect, else soft concerns, else the review's status."""
    hard, odd = [f for f in found if f["hard"]], [f for f in found if f.get("suspect")]
    soft = [f for f in found if not f["hard"] and not f.get("suspect")]
    if hard:
        return "审核：" + "；".join(cite(f) for f in hard[:2])
    if odd:
        return f"数据存疑：{odd[0]['words']}（{odd[0]['date']} {odd[0]['type']}）"
    if soft:
        return "市场可能在担心：" + "；".join(cite(f) for f in soft[:2])
    return STATUS.get(state.get("status"), "审核未见重大风险") if state else ""  # not reviewed: no line


def apply(rows: pd.DataFrame, market: str, states: dict | None, deep: dict) -> pd.DataFrame:
    """The lists after the review (states: code -> state; deep: code -> deep-dive findings). A buy with a hard red
    flag or data_suspect is removed (list 'removed', with the reason) and the next-ranked name not blocked takes its
    place; a holding with a hard red flag becomes 卖出, with data_suspect or a soft concern (if it was 继续持有) 复核;
    avoid names keep their place. Every row gets its review line and AI note. Without states (the build), only the
    'next' rows are dropped."""
    rows = rows.assign(review="", note="")
    if states is None:
        return rows[rows["list"] != "next"]
    found = {c: list(states.get(c, {}).get("findings") or []) + list(deep.get(c, [])) for c in rows["code"]}
    for i, r in rows.iterrows():
        rows.at[i, "review"] = line(states.get(r["code"], {}), found[r["code"]])
        rows.at[i, "note"] = states.get(r["code"], {}).get("note") or ""
    blocked = lambda c: next((f for f in found[c] if f["hard"] or f.get("suspect")), None)
    bench = rows[rows["list"] == "next"].sort_values("rank").to_dict("records")
    keep, removed = [], []
    for b in rows[rows["list"] == "buy"].sort_values("rank").to_dict("records"):
        if not (why := blocked(b["code"])):
            keep.append(b)
            continue
        replace = next((n for n in bench if not blocked(n["code"])), None)
        bench = bench[bench.index(replace) + 1:] if replace else []
        removed.append(b | {"list": "removed", "reason": ("数据存疑：" + why["words"]) if why.get("suspect") else cite(why),
                            "status": f"由 {replace['code']} {replace['name']} 替换" if replace else "候补已用完"})
        keep += [replace] if replace else []
    keep = pd.DataFrame(keep).sort_values("score", ascending=False).assign(list="buy") if keep else pd.DataFrame()
    keep["rank"] = range(1, len(keep) + 1)
    rest = rows[~rows["list"].isin(["buy", "next"])].copy()
    for i, r in rest[rest["list"] == "holding"].iterrows():
        hard = next((f for f in found[r["code"]] if f["hard"]), None)
        odd = next((f for f in found[r["code"]] if f.get("suspect")), None)
        soft = next((f for f in found[r["code"]] if not f["hard"] and not f.get("suspect")), None)
        if hard:
            rest.loc[i, ["status", "reason"]] = ["卖出", cite(hard)]
        elif odd:
            rest.loc[i, ["status", "reason"]] = ["复核", "数据存疑：" + odd["words"]]
        elif soft and r["status"] == "继续持有":
            rest.loc[i, ["status", "reason"]] = ["复核", f"{r['reason']}；市场可能在担心：{cite(soft)}"]
    return pd.concat([keep, pd.DataFrame(removed), rest], ignore_index=True)
