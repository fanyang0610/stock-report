"""Deep-dive lane (AGENTS.md rule 3; PLAN.md, "Results review"): the latest periodic report of each buy, the next 5
and your scored holdings, read once per filing (data/deepdive/<market>/<code>_<filing>.json), at most `per_day` new
filings per market a day, after the results review (never inside the keyword reply's budget). DeepSeek answers a
fixed questionnaire with quoted sentences; code verifies every quote (quotes.py), takes each number from it and
decides what it means (findings()): the data check (the period's net profit 20%+ off the figure behind the card:
data_suspect), hard red flags (a non-standard audit opinion, a going-concern doubt, a regulator's investigation, an
offer price for the company) and a soft concern (non-recurring items 30%+ of the period's profit)."""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx
import pandas as pd

from stockreport import quotes
from stockreport.config import CONFIG, DATA
from stockreport.fetch import filings

log = logging.getLogger(__name__)
CFG = CONFIG["deepdive"]
CACHE = DATA / "deepdive"
CURRENCY = {"cn": "CNY", "us": "USD", "hk": "HKD"}
NUMERIC = ("net_profit", "non_recurring", "offer_price")
TEXTUAL = ("period_end", "audit_opinion", "going_concern", "investigation")
# Where the questionnaire's answers usually are: windows of text around these words go to DeepSeek
KEYWORDS = re.compile(
    r"非经常性损益|非經常性|一次性|审计意见|審計意見|核數師意見|持续经营|持續經營|立案|行政处罚|行政處罰|要约|要約|收购价|收購價|"
    r"归属于上市公司股东的净利润|本公司擁有人應佔|报告期末|截至|non-recurring|one-time|gain on (the )?(sale|disposal)|"
    r"going concern|substantial doubt|subpoena|Wells notice|investigation|per share in cash|merger consideration|"
    r"offer price|attributable to (common|ordinary|owners|equity holders)|period ended|year ended", re.I)

SYSTEM = """你是财报事实摘录员。下面是一份上市公司定期报告的节选文本。按固定问卷从文本中找事实，每项都附原文引文。
规则：
1. quote 必须从给出的文本中逐字复制（一个句子或表格中的一行，不超过 200 字），不得改写、翻译、拼接或补字；找不到就留空字符串。
2. number 必须是 quote 中逐字出现的那个数字，保持原样（如 "1,234,567.89"、"(12.3)"、"35.2%"），不得换算或计算。
3. unit_quote：quote 中数字后面没有单位时（常见于表格），从文本中逐字复制该表格上方说明单位的原文（如 "单位：元 币种：人民币"、
   "(in millions)"、"人民幣百萬元"、"RMB'000"）；数字后面已有单位时留空。
4. 不推断、不估算，不给出文本里没有的数字。文本里没有的项一律留空。
问卷（JSON 键）：
- net_profit：报告期（年初至报告期末）归属于母公司股东（本公司拥有人）的净利润；表格行整行引用。
- non_recurring：与 net_profit 同一期间的非经常性损益合计；美股、港股为报告明确列示的一次性收益或损失合计。
- period_end：说明报告期截止日期的原句（如"截至2026年9月30日"、"for the quarterly period ended September 30, 2026"）。
- offer_price：本公司是被收购方时，针对本公司股份的每股要约价、收购价或私有化价格。
- audit_opinion：审计师对最近年度财务报表发表审计意见的原句。
- going_concern：关于持续经营能力存在重大不确定性的原句。
- investigation：监管机构对公司或其控股股东、实际控制人立案调查、行政处罚或调查的原句。
只输出 JSON：{"net_profit": {"quote": "", "number": "", "unit_quote": ""}, "non_recurring": {...同上},
"offer_price": {...同上}, "period_end": {"quote": ""}, "audit_opinion": {"quote": ""}, "going_concern": {"quote": ""},
"investigation": {"quote": ""}}"""


def excerpt(text: str) -> str:
    """The whole filing if short, else windows around the questionnaire's keywords within `max_chars`: the first hit
    of every keyword, then the second, then the third, merged and in document order."""
    if len(text) <= CFG["max_chars"]:
        return text
    before, after = CFG["window"]
    spans, seen = [], {}
    for m in KEYWORDS.finditer(text):
        key = m.group(0).lower()
        seen[key] = seen.get(key, 0) + 1
        if seen[key] <= 3:
            spans.append((seen[key], max(0, m.start() - before), m.end() + after))
    chosen, used = [], 0
    for _, a, b in sorted(spans):
        if used + b - a <= CFG["max_chars"]:
            chosen.append([a, b])
            used += b - a
    merged = []
    for a, b in sorted(chosen):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return "\n……\n".join(text[a:b] for a, b in merged)


def ask(client: httpx.Client, content: str) -> dict:
    """The questionnaire's JSON answer; retried once on an API error or invalid JSON."""
    err = None
    for _ in (1, 2):
        try:
            resp = client.post("/chat/completions", json={
                "model": CONFIG["notes"]["model"], "temperature": 0, "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]})
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip().removeprefix("```json").removesuffix("```")
            answer = json.loads(text)
            if isinstance(answer, dict):
                return answer
            err = ValueError("not a JSON object")
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as e:
            err = e
    raise RuntimeError(f"deep dive failed: {type(err).__name__}: {err}")


def verify(answer: dict, text: str, market: str) -> dict:
    """Only the facts whose quotes are in the filing, with numbers parsed from the quotes."""
    full, cur = quotes.norm(text), CURRENCY[market] if market != "hk" else None
    facts, asked = {}, 0
    for key in NUMERIC + TEXTUAL:
        item = answer.get(key) if isinstance(answer.get(key), dict) else {}
        if not item.get("quote"):
            continue
        asked += 1
        if fact := quotes.check(item, full, cur, numeric=key in NUMERIC):
            facts[key] = fact
    return {"facts": facts, "asked": asked}


def study(client: httpx.Client, market: str, code: str, name: str, filing: dict) -> dict:
    """Read one filing and answer the questionnaire with verified quotes."""
    started = time.monotonic()
    text = filings.text(market, filing["url"])
    if not text:
        return {"facts": {}, "asked": 0, "note": "文件无可读文本（扫描件或字体无编码），未核查"}
    answer = ask(client, f"公司：{code} {name}\n文件：{filing['title']}（{filing['date']}）\n文本节选：\n{excerpt(text)}")
    out = verify(answer, text, market)
    log.info("deep dive %s %s %s: %d of %d answers verified, %d chars, %.0fs", market, code, filing["title"],
             len(out["facts"]), out["asked"], len(text), time.monotonic() - started)
    return out


def filing_id(market: str, url: str) -> str:
    parts = url.rstrip("/").split("/")
    return f"{market}-{parts[-2] if market == 'us' else parts[-1].split('.')[0]}"


def fx_rate(src: str | None, dst: str) -> float | None:
    """Units of dst per unit of src (yahoo per-USD rates; None if unknown)."""
    from stockreport.fetch.yahoo import load_fx
    if src is None or src == dst:
        return 1.0 if src else None
    per_usd = load_fx().to_dict() | {"USD": 1.0}
    return per_usd[dst] / per_usd[src] if src in per_usd and dst in per_usd else None


NON_STANDARD = re.compile(r"(?<![无無非])保留意[见見]|否定意[见見]|无法表示意见|無法表示意見|不發表意見|"
                          r"(?<!un)qualified opinion|adverse opinion|disclaimer of opinion", re.I)
STANDARD = re.compile(r"标准无保留|標準無保留|无保留意见|無保留意見|unqualified opinion|present fairly", re.I)
DENIAL = re.compile(r"不存在|未发现|未發現|没有|沒有|并无|並無|no substantial doubt|not (been )?subject|no (material )?"
                    r"(investigation|proceeding)", re.I)
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
MONTH = "|".join(MONTHS)


def period_of(quote: str) -> str | None:
    """The latest date written in a quote ('2026年9月30日', '30th June 2026', 'September 27, 2026', '2026-06-30')."""
    found = [(int(y), int(m), int(d)) for y, m, d in re.findall(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", quote)]
    found += [(int(y), MONTHS[m.lower()], int(d)) for d, m, y in
              re.findall(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH}),?\s+(\d{{4}})", quote, re.I)]
    found += [(int(y), MONTHS[m.lower()], int(d)) for m, d, y in
              re.findall(rf"({MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", quote, re.I)]
    found += [(int(y), int(m), int(d)) for y, m, d in re.findall(r"(\d{4})-(\d{2})-(\d{2})", quote)]
    try:
        return max(date(*x) for x in found).isoformat() if found else None
    except ValueError:
        return None


CN_PERIODS = (("第一季度|一季度", "03-31"), ("半年度", "06-30"), ("第三季度|三季度", "09-30"), ("年度", "12-31"))
AFTER_DEDUCTING = re.compile(r"扣除非经常性损益|扣除非經常性損益|扣非|after deducting|excluding non-recurring", re.I)
# the data check reads only a row that says it is the shareholders' profit: not a consolidated row (minorities
# included), the minorities' own, or the profit after deducting non-recurring items
ATTRIBUTABLE = re.compile(r"归属于(上市公司|母公司)?(普通股)?股东|歸屬於.{0,8}股東|归母|擁有人應佔|股東應佔|attributable to|"
                          r"available to (common|ordinary)|shareholders of|equity holders of|owners of", re.I)
MINORITY = re.compile(r"少数股东|少數股東|非控股|non-controlling|minority", re.I)


def title_period(title: str) -> str | None:
    """A CN periodic report's period end from its standard title ('2026年半年度报告' -> 2026-06-30)."""
    year = re.search(r"(\d{4})\s*年", title)
    end = next((d for words, d in CN_PERIODS if re.search(words, title)), None)
    return f"{year.group(1)}-{end}" if year and end else None


def data_gap(row: dict, found: dict, market: str) -> str | None:
    """The data check: the report's net profit for the card's period (the period end quoted in the report; CN: else its
    title) against the figure behind the card (CN and HK: profit to shareholders year to date; US: the year's profit,
    from a 10-K), only from a row that says it is the shareholders' profit. The quoted row's figures are all tried
    (a table row holds the quarter and the year to date); a gap that is a power of ten is a unit misread of the row,
    not our data (a fault that size fails the second-source cross-checks), and isn't counted."""
    f = found["facts"]
    np_, end = f.get("net_profit"), period_of(f.get("period_end", {}).get("quote", ""))
    end = end or (title_period(found["title"]) if market == "cn" else None)
    if not np_ or end is None or end != str(row.get("period")) or not ATTRIBUTABLE.search(np_["quote"]) \
            or MINORITY.search(np_["quote"]) or AFTER_DEDUCTING.search(np_["quote"]):
        return None
    if market == "us" and not found["title"].startswith("10-K"):
        return None  # 10-Qs are year to date; the card's figure is the trailing 12 months
    ours = row.get("np_ttm") if market == "us" else row.get("np_ytd")
    cur = {"cn": "CNY", "us": "USD"}.get(market) or row.get("report_currency")
    rate = fx_rate(np_["currency"], cur) if isinstance(cur, str) else None
    if rate is None or pd.isna(ours) or not ours:
        return None
    figures = [quotes.number(x) for x in re.findall(r"\(?-?\d[\d,]*(?:\.\d+)?\)?", np_["quote"])]
    theirs = [v * np_["scale"] * rate for v in figures if v]
    gap = lambda t: abs(t - ours) / max(abs(t), abs(ours))
    main = np_["value"] * rate
    if not theirs or min(map(gap, theirs)) < CFG["data_gap"]:
        return None
    if any(abs(abs(main / ours) / 10 ** k - 1) < 0.03 for k in (-8, -6, -4, -3, 3, 4, 6, 8)):
        log.info("deep dive %s %s: net profit off by a power of ten, read as a unit misread", market, row["code"])
        return None
    return f"最新报告的归母净利润 {main / 1e8:,.2f} 亿与卡片所用数据 {ours / 1e8:,.2f} 亿相差 {gap(main):.0%}"


def findings(row: dict, found: dict, market: str) -> list[dict]:
    """What a read filing means for one name, as review findings ({kind, words, hard, quote, date, type}). A
    'non-recurring' quote that names the profit after deducting them is that profit, not the items, and is skipped."""
    f, out = found["facts"], []
    add = lambda kind, words, hard, quote, **kw: out.append(
        {"kind": kind, "words": words, "hard": hard, "quote": quote, "date": found["date"], "type": found["title"]} | kw)
    if gap := data_gap(row, found, market):
        add("data_suspect", gap, False, f["net_profit"]["quote"], suspect=True)
    profit = f.get("net_profit", {}).get("value")
    one_off = f.get("non_recurring") if not AFTER_DEDUCTING.search(f.get("non_recurring", {}).get("quote", "")) else None
    if one_off and profit and profit > 0 and one_off["value"] / profit >= CFG["one_off_share"]:
        add("one_off", f"非经常性损益占同期归母净利润 {f['non_recurring']['value'] / profit:.0%}", False,
            f["non_recurring"]["quote"])
    opinion = f.get("audit_opinion", {}).get("quote", "")
    if NON_STANDARD.search(opinion) and not STANDARD.search(opinion):
        add("audit", "审计意见非标准", True, opinion)
    doubt = f.get("going_concern", {}).get("quote", "")
    if re.search(r"重大不确定|重大不確定|重大疑虑|重大疑慮|substantial doubt", doubt, re.I) and not DENIAL.search(doubt):
        add("going_concern", "持续经营存在重大不确定性", True, doubt)
    probe = f.get("investigation", {}).get("quote", "")
    if re.search(r"立案|Wells notice", probe, re.I) and not DENIAL.search(probe):  # an investigation opened, not legal-note wording
        add("investigation", "监管立案调查", True, probe)
    elif re.search(r"调查|調查|处罚|處罰|警示|监管|investigation|subpoena", probe, re.I) and not DENIAL.search(probe):
        add("other", "涉及监管调查或处罚", False, probe)
    rate = fx_rate(f.get("offer_price", {}).get("currency"), CURRENCY[market])
    if "offer_price" in f and rate and pd.notna(row.get("price")):
        offer = f["offer_price"]["value"] * rate
        add("takeover", f"每股要约/收购价 {offer:,.2f}（较现价 {offer / row['price'] - 1:+.0%}）", True, f["offer_price"]["quote"])
    return out


def candidates(rows: pd.DataFrame) -> list[dict]:
    """The names whose latest report is read: the buys and the next 5 by rank, then your scored holdings."""
    order = [rows[rows["list"] == k].sort_values("rank") for k in ("buy", "next")] + \
            [rows[(rows["list"] == "holding") & rows["score"].notna()]]
    return [r for part in order for r in part.to_dict("records")]


def run(market: str, rows: pd.DataFrame, today: date, client: httpx.Client) -> int:
    """Read the latest periodic report of the candidates not read yet, at most `per_day` new filings per market a
    day; returns how many were read. Cached filings older than `keep_days` are deleted."""
    folder = CACHE / market
    folder.mkdir(parents=True, exist_ok=True)
    read = sum(json.loads(p.read_text(encoding="utf-8")).get("read") == today.isoformat() for p in folder.glob("*_*.json"))
    todo = []
    for row in candidates(rows):
        if len(todo) >= CFG["per_day"] - read:
            break
        try:
            filing = filings.periodic(market, row["code"], today)
        except Exception as e:
            log.warning("deep dive %s %s: no filing (%s)", market, row["code"], e)
            continue
        path = folder / f"{row['code']}_{filing_id(market, filing['url'])}.json" if filing else None
        if path and not path.exists():
            todo.append((row, filing, path))

    def work(job):
        row, filing, path = job
        try:
            found = study(client, market, row["code"], row["name"], filing)
        except Exception as e:
            log.warning("deep dive %s %s failed: %s", market, row["code"], e)
            return False
        found |= {k: filing[k] for k in ("title", "date", "url")} | {"read": today.isoformat()}
        path.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    with ThreadPoolExecutor(CFG["workers"]) as pool:
        done = sum(pool.map(work, todo))
    cutoff = time.time() - CFG["keep_days"] * 86400
    for old in folder.glob("*.json"):
        if old.stat().st_mtime < cutoff:
            old.unlink()
    log.info("deep dives %s: %d new filings read (%d earlier today, limit %d)", market.upper(), done, read, CFG["per_day"])
    return done


def results(market: str, rows: pd.DataFrame) -> dict[str, list[dict]]:
    """Code -> the findings of the newest filing read for it."""
    out = {}
    for row in rows.drop_duplicates("code").to_dict("records"):
        read = [json.loads(p.read_text(encoding="utf-8")) for p in (CACHE / market).glob(f"{row['code']}_*.json")]
        if read:
            out[row["code"]] = findings(row, max(read, key=lambda x: x["date"]), market)
    return out
