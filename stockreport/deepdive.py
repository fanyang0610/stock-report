"""Deep-dive lane, tier 3 (PLAN.md Method 15, docs/REVIEW.md A3): rule-triggered reading of one filing per stock,
at most `per_day` new filings per market a day, among the picks and the first runners-up. DeepSeek answers a fixed
questionnaire with quoted sentences; code verifies every quote (stockreport/quotes.py), takes each number from its
quote and works out what it means for the pick: a veto (swapped like an AI flag), 低信心, or a line on the card.
Verified facts are cached per filing in data/deepdive/<market>/<filing>.json; the day's results go to
reports/<date>/<market>_deepdive.json."""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import httpx
import pandas as pd
from dotenv import dotenv_values

from stockreport import events, quotes
from stockreport.config import CONFIG, DATA, REPORTS, ROOT
from stockreport.fetch import filings

log = logging.getLogger(__name__)
CFG = CONFIG["deepdive"]
CACHE = DATA / "deepdive"
CURRENCY = {"cn": "CNY", "us": "USD", "hk": "HKD"}
NUMERIC = ("non_recurring", "net_profit", "embedded_value", "underlying_profit", "offer_price", "deal_size",
           "related_party_pct")
TEXTUAL = ("audit_opinion", "going_concern", "investigation", "price_driver")
# Where the questionnaire's answers usually are: windows of text around these words go to DeepSeek
KEYWORDS = re.compile(
    r"非经常性损益|非經常性|一次性|审计意见|審計意見|核數師意見|持续经营|持續經營|立案|行政处罚|行政處罰|关联交易|關連交易|"
    r"内含价值|內含價值|投资性房地产|投資物業|基础盈利|基礎盈利|核心盈利|核心溢利|基本溢利|证券投资|持有.{0,20}股份|"
    r"要约|要約|收购价|收購價|代價|对价|交易价格|合同金额|中标|合約|归属于上市公司股东的净利润|本公司擁有人應佔|"
    r"non-recurring|one-time|gain on (the )?(sale|disposal)|impairment|going concern|substantial doubt|subpoena|"
    r"Wells notice|investigation|related part(y|ies)|embedded value|equity method|per share in cash|"
    r"merger consideration|offer price|aggregate (purchase price|consideration)|attributable to (common|ordinary)",
    re.I)

SYSTEM = """你是财报事实摘录员。下面是一份上市公司文件（定期报告或临时公告）的节选文本。按固定问卷从文本中找事实，每项都附原文引文。
规则：
1. quote 必须从给出的文本中逐字复制（一个句子或表格中的一行，不超过 200 字），不得改写、翻译、拼接或补字；找不到就留空字符串。
2. number 必须是 quote 中逐字出现的那个数字，保持原样（如 "1,234,567.89"、"(12.3)"、"35.2%"），不得换算或计算。
3. unit_quote：quote 中数字后面没有单位时（常见于表格），从文本中逐字复制该表格上方说明单位的原文（如 "单位：元 币种：人民币"、
   "(in millions)"、"人民幣百萬元"）；数字后面已有单位时留空。
4. 不推断、不估算，不给出文本里没有的数字。文本里没有的项一律留空。
问卷（JSON 键）：
- non_recurring：最新报告期（年初至报告期末）非经常性损益合计；美股、港股为报告明确列示的一次性收益或损失合计。
- net_profit：与 non_recurring 同一期间、归属于母公司股东（本公司拥有人）的净利润。
- embedded_value：保险公司集团内含价值总额。
- underlying_profit：物业投资公司剔除投资物业公允值变动后的基础盈利（核心盈利、基本溢利），与 net_profit 同一期间。
- offer_price：本公司是被收购方时，针对本公司股份的每股要约价、收购价或私有化价格。
- deal_size：本文件所述交易或合同的总金额（收购、出售、重大合同、中标）。
- related_party_pct：向关联方销售占营业收入的比例。
- audit_opinion：审计师对最近年度财务报表发表审计意见的原句。
- going_concern：关于持续经营能力存在重大不确定性的原句。
- investigation：监管机构对公司或其控股股东、实际控制人立案调查、行政处罚或调查的原句。
- listed_stakes：公司持有的其他上市公司股份，最多 5 个；code 为 quote 中出现的证券代码，number 为持股数量。
- price_driver：决定公司利润的主要商品或产品价格（如锂、生猪、铜、存储芯片）；name 为 quote 中出现的商品名称。
只输出 JSON：{"non_recurring": {"quote": "", "number": "", "unit_quote": ""}, "net_profit": {...同上}, "embedded_value": {...},
"underlying_profit": {...}, "offer_price": {...}, "deal_size": {...}, "related_party_pct": {"quote": "", "number": ""},
"audit_opinion": {"quote": ""}, "going_concern": {"quote": ""}, "investigation": {"quote": ""},
"listed_stakes": [{"quote": "", "code": "", "number": "", "unit_quote": ""}], "price_driver": {"quote": "", "name": ""}}"""


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
        fact = quotes.check(item, full, cur, numeric=key in NUMERIC)
        if fact and key == "price_driver":
            name = str(item.get("name") or "").strip()
            fact = fact | {"name": name} if name and quotes.norm(name) in quotes.norm(item["quote"]) else None
        if fact:
            facts[key] = fact
    stakes = []
    for item in [s for s in answer.get("listed_stakes") or [] if isinstance(s, dict) and s.get("quote")][:5]:
        asked += 1
        fact, code = quotes.check(item, full, None), quotes.code_in(item)
        if fact and code:
            stakes.append(fact | {"code": code})
    if stakes:
        facts["listed_stakes"] = stakes
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
             len(out["facts"]) + len(out["facts"].get("listed_stakes", [])) - ("listed_stakes" in out["facts"]),
             out["asked"], len(text), time.monotonic() - started)
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


def stake_prices() -> dict[str, float]:
    """Latest close per code in all three price tables (listed stakes are valued at our own prices)."""
    out = {}
    for m in ("cn", "hk", "us"):
        p = pd.read_csv(DATA / "prices" / f"{m}.csv.gz", dtype={"code": str}, usecols=["date", "code", "close"])
        out |= {c: (v, CURRENCY[m]) for c, v in p.sort_values("date").groupby("code")["close"].last().items()}
    return out


NON_STANDARD = re.compile(r"(?<![无無非])保留意[见見]|否定意[见見]|无法表示意见|無法表示意見|不發表意見|"
                          r"(?<!un)qualified opinion|adverse opinion|disclaimer of opinion", re.I)
STANDARD = re.compile(r"标准无保留|標準無保留|无保留意见|無保留意見|unqualified opinion|present fairly", re.I)
DENIAL = re.compile(r"不存在|未发现|未發現|没有|沒有|并无|並無|no substantial doubt|not (been )?subject|no (material )?"
                    r"(investigation|proceeding)", re.I)


def meaning(row: pd.Series, found: dict, market: str) -> dict:
    """What the verified facts mean for this pick: the card line, and veto (swapped), low (低信心) or none."""
    f, parts, low, veto = found["facts"], [], [], None
    cur, price, mcap = CURRENCY[market], row["price"], row["mcap"]
    buyhold, yi = row["bucket"] in ("buy", "hold"), lambda v: f"{v / 1e8:,.1f} 亿"
    local = lambda x: x["value"] * r if (r := fx_rate(x["currency"], cur)) else None  # in the quote currency
    profit = f.get("net_profit", {}).get("value")
    if "non_recurring" in f and profit and profit > 0:
        share = f["non_recurring"]["value"] / profit
        parts.append(f"非经常性损益占同期归母净利润 {share:.0%}")
        if buyhold and share >= CFG["one_off_share"]:
            veto = f"非经常性损益占同期净利润 {share:.0%}，近期利润不能代表正常水平"
    if "underlying_profit" in f and profit and profit > 0:
        ratio = f["underlying_profit"]["value"] / profit
        parts.append(f"剔除重估后基础盈利为净利润的 {ratio:.0%}")
        if buyhold and ratio < 0.5:
            low.append("基础盈利不到报表净利润一半")
    if "embedded_value" in f and (ev := local(f["embedded_value"])) and ev > 0:
        per = ev / (mcap / price)
        parts.append(f"内含价值每股 {per:,.2f}（P/EV {price / per:.2f}）")
        if row["bucket"] == "sell" and per > price:
            low.append("股价低于内含价值")
    if "listed_stakes" in f:
        px, total, n = stake_prices(), 0.0, 0
        for s in f["listed_stakes"]:
            close, ccy = px.get(s["code"], (None, None))
            if close and s["value"] > 0 and (r := fx_rate(ccy, cur)):
                total, n = total + s["value"] * close * r, n + 1
        if n:
            parts.append(f"所持 {n} 家上市公司股权按现价约 {yi(total)}，为市值的 {total / mcap:.0%}（未扣母公司负债）")
            if row["bucket"] == "sell" and total >= mcap:
                low.append("所持上市股权市值超过自身市值")
    if "offer_price" in f and (offer := local(f["offer_price"])) and offer > 0:
        parts.append(f"每股要约/收购价 {offer:,.2f}（较现价 {offer / price - 1:+.0%}）")
        veto = veto or f"每股要约/收购价 {offer:,.2f}，股价由交易决定"
    if "deal_size" in f and found.get("source") == "event" and (amount := local(f["deal_size"])) and amount > 0:
        rev = row.get("revenue_ttm")
        of_rev = amount / rev if pd.notna(rev) and rev > 0 else float("nan")
        big = max(amount / mcap, of_rev if of_rev == of_rev else 0) >= CFG["material"]
        parts.append(f"交易/合同金额 {yi(amount)}（占近 12 个月营收 {of_rev:.0%}、市值 {amount / mcap:.0%}，"
                     f"{'重大' if big else '影响较小'}）".replace("营收 nan%、", ""))
    if "related_party_pct" in f and f["related_party_pct"]["pct"]:
        pct = f["related_party_pct"]["value"]
        parts.append(f"关联销售占营收 {pct:.0%}")
        if buyhold and pct >= CFG["related_party"]:
            low.append(f"关联销售占营收 {pct:.0%}")
    opinion = f.get("audit_opinion", {}).get("quote", "")
    if NON_STANDARD.search(opinion) and not STANDARD.search(opinion):
        parts.append("审计意见非标准")
        veto = veto or (buyhold and "审计意见非标准")
    elif STANDARD.search(opinion):
        parts.append("审计意见为无保留意见")
    doubt = f.get("going_concern", {}).get("quote", "")
    if re.search(r"重大不确定|重大不確定|重大疑虑|重大疑慮|substantial doubt", doubt, re.I) and not DENIAL.search(doubt):
        parts.append("持续经营存在重大不确定性")
        veto = veto or (buyhold and "持续经营存在重大不确定性")
    probe = f.get("investigation", {}).get("quote", "")
    if re.search(r"立案|调查|調查|处罚|處罰|investigation|subpoena|Wells", probe, re.I) and not DENIAL.search(probe):
        parts.append("监管调查/处罚：" + events.short(probe, 30))
        if buyhold and re.search(r"立案|Wells", probe, re.I):
            veto = veto or "被监管机构立案调查"
        elif buyhold:
            low.append("涉及监管调查或处罚")
    if "price_driver" in f:
        parts.append(f"主要价格驱动：{f['price_driver']['name']}")
    n = len(f) + len(f.get("listed_stakes", [])) - ("listed_stakes" in f)
    head = f"深度核查（{found['title']}，{found['date']}）："
    body = "；".join(parts) or found.get("note") or ("未发现需要调整的事项" if n else "未找到可核实的事实")
    action = "veto" if veto else "low" if low else "none"
    return {"line": f"{head}{body}（{n}/{found['asked']} 条引文已核实）", "action": action,
            "reason": "深度核查：" + (veto or "；".join(low)) if action != "none" else ""}


CONTRACT = re.compile(r"合同|中标|订单|合約|Material definitive", re.I)
ARCHETYPES = {"insurer": "保险公司（内含价值）", "property": "地产/物业投资（重估损益）", "holdco": "综合/控股公司（所持股权）"}


def triggers(market: str, cands: pd.DataFrame, today: date) -> list[dict]:
    """Rule triggers per candidate, the strongest first: a deal, risk or contract filing in the event feed (that
    filing is read); a value 2× or ½ the price without v3's 高; v3's quality screen failing on a strong buy or hold
    signal; an archetype the rules can't read (insurer, landlord, holding company, a 40% share-count change); an
    abnormal move without a matching event (the latest periodic report is read)."""
    ev = events.load(market)
    ev = ev[ev["date"] >= (today - timedelta(days=CONFIG["events"]["recent_days"])).isoformat()]
    hot = ev[ev["kind"].isin(["deal", "risk"]) | ((ev["kind"] == "business") & ev["title"].str.contains(CONTRACT))]
    moves, out = events.lines(market, cands, today), []
    for _, r in cands.iterrows():
        found, mine = [], hot[hot["code"] == r["code"]].sort_values("date")
        if len(mine):
            e = mine.iloc[-1]
            found.append((1, f"{e['date'][5:]} {events.KINDS[e['kind']]}公告",
                          {"url": e["url"], "date": e["date"], "title": events.short(e["title"], 24)}))
        ratio, conf = r["fv_mid"] / r["price"], r.get("v3_confidence")
        if (ratio >= CFG["value_ratio"] or ratio <= 1 / CFG["value_ratio"]) and conf != "高":
            found.append((2, f"估值为现价的 {ratio:.1f} 倍，v3 把握度{conf if isinstance(conf, str) and conf else '无'}", None))
        fails = r.get("v3_screen_fails")
        if r["bucket"] != "sell" and isinstance(fails, str) and fails and r["upside"] >= CFG["strong_upside"]:
            found.append((3, f"质量筛查未通过（{fails}）但空间 {r['upside']:+.0%}", None))
        kind = next((k for k, words in CFG["archetypes"].items() if any(w in str(r["industry"]) for w in words)), None)
        if kind or abs(r.get("v3_dilution") or 0) > CFG["share_change"]:
            found.append((4, ARCHETYPES.get(kind, "5 年股本变化超过 40%"), None))
        if moves[r["code"]]["matched"] is False:
            found.append((5, "异动未见对应公告", None))
        if found:
            best = min(found, key=lambda x: x[0])
            out.append({"code": r["code"], "name": r["name"], "row": r, "why": best[1], "filing": best[2],
                        "order": (best[0], r["role"] != "pick", ["buy", "hold", "sell"].index(r["bucket"]), r["rank"])})
    return sorted(out, key=lambda t: t["order"])


def candidates(picks: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """The picks and the first runners-up per bucket, with v3's confidence, screen and dilution when it ran."""
    keep = (picks["role"] == "pick") | ((picks["role"] == "runner_up") & (picks["rank"] <= CFG["runners_up"]))
    v3 = df.reindex(columns=["v3_confidence", "v3_screen_fails", "v3_dilution"])
    return picks[keep].drop(columns=v3.columns, errors="ignore").join(v3, on="code")


def run(market: str, today: date, picks: pd.DataFrame, df: pd.DataFrame, use_ai: bool) -> dict:
    """The day's deep dives for one market: cached filings are reused; at most `per_day` new ones a day (DeepSeek
    only with use_ai and a key). Writes and returns reports/<date>/<market>_deepdive.json."""
    started, path = time.monotonic(), REPORTS / today.isoformat() / f"{market}_deepdive.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"fresh": [], "results": {}}
    key = dotenv_values(ROOT / ".env").get("DEEPSEEK_API_KEY") if use_ai else None
    client = key and httpx.Client(base_url=CONFIG["notes"]["base_url"], timeout=300,
                                  headers={"Authorization": f"Bearer {key}"})
    todo, skipped = [], []
    for t in triggers(market, candidates(picks, df), today):
        try:
            filing = t["filing"] or filings.periodic(market, t["code"], today)
        except Exception as e:
            log.warning("deep dive %s %s: no filing (%s)", market, t["code"], e)
            continue
        if filing:
            todo.append((t, filing, CACHE / market / f"{filing_id(market, filing['url'])}.json"))
    room = max(0, CFG["per_day"] - len(state["fresh"])) if client else 0
    new = [x for x in todo if not x[2].exists() and x[0]["code"] not in state["results"]]
    new, skipped = new[:room], new[room:]

    def work(job):
        t, filing, cache = job
        try:
            found = study(client, market, t["code"], t["name"], filing)
        except Exception as e:
            log.warning("deep dive %s %s failed: %s", market, t["code"], e)
            return False
        cache.parent.mkdir(parents=True, exist_ok=True)
        found |= {k: filing[k] for k in ("title", "date", "url")} | {"source": "event" if t["filing"] else "periodic"}
        cache.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    with ThreadPoolExecutor(CFG["workers"]) as pool:
        state["fresh"] += [job[0]["code"] for job, ok in zip(new, pool.map(work, new)) if ok]
    for t, filing, cache in todo:
        if cache.exists():
            found = json.loads(cache.read_text(encoding="utf-8"))
            state["results"][t["code"]] = {"name": t["name"], "trigger": t["why"], "filing": cache.stem,
                                           **meaning(t["row"], found, market)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    cutoff = time.time() - CFG["keep_days"] * 86400
    for old in (CACHE / market).glob("*.json") if (CACHE / market).exists() else []:
        if old.stat().st_mtime < cutoff:
            old.unlink()
    print(f"Deep dives: {len(todo)} triggered, {len(state['fresh'])} new today (limit {CFG['per_day']}), "
          f"{len(state['results'])} with results, {time.monotonic() - started:.0f}s"
          + (f"; over the limit: {' '.join(x[0]['code'] for x in skipped)}" if skipped else ""))
    for code, res in state["results"].items():
        print(f"  {code} {res['name']} [{res['trigger']}] {res['action']}: {res['line']}")
    return state
