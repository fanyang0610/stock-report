"""Research stage 12, part 1: reading a WeChat message that isn't the screening keyword (PLAN.md "The router").
Layers, so the bot keeps answering when DeepSeek is slow or down:
- 2, no AI: an exact code (600519, 0700, $AAPL) or an exact full name (贵州茅台, Apple Inc.) that names one company;
- 3, DeepSeek (the fast model, JSON, temperature 0): the intent and the companies mentioned with its guessed names and
  tickers. They are hints: code confirms each against the official listings (research/listings.py, US lines only if
  the Nasdaq screener has them as ordinary shares, so no ETFs, notes or warrants) and Eastmoney's search box;
- 4, ask: several companies fit, none does, the text is vague, or DeepSeek can't be reached: one short numbered
  question, answered by "1" or a name without AI (the listener keeps it open in data/state.json).
Layer 1, the exact keyword, is the listener's (listener.is_keyword). One issuer's lines are one company (Eastmoney's
ORG_CODE, else the SEC's CIK): 比亚迪 is 002594 and 01211, led by the code you named, else its A, then H, then US line."""

import functools
import logging
import re
import unicodedata

import httpx
import pandas as pd

from stockreport.config import CONFIG
from stockreport.fetch import nasdaq
from stockreport.research import listings, words

log = logging.getLogger(__name__)
CFG = CONFIG["router"]
MARKETS = ("cn", "hk", "us")
SEARCH = "https://searchapi.eastmoney.com/api/suggest/get"
TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"  # the public token Eastmoney's own pages send with the search box
CLASSES = {"AStock": "cn", "HK": "hk", "UsStock": "us"}
TRAIL = re.compile(r"[\s.,!?;:~。，！？；：…、～]+$")
CHINESE_NAMES: dict[tuple[str, str], str] = {}  # (market, code) -> the search box's Chinese name (苹果, 英伟达)

HELP = ("可以发：\n1. 「股票报告」：每日A股、美股、港股的买入、持有、卖出名单\n"
        "2. 一家公司的名字或代码（如 贵州茅台、600519、腾讯、0700、AAPL）：个股研究报告\n一次发一家公司。")
UNSUPPORTED = {"index": "暂不分析指数和大盘。", "crypto": "不分析加密货币。", "fund": "暂不分析基金和 ETF。",
               "unlisted": "只研究已在A股、港股或美股上市的公司，这家还没有上市。", "other": "只研究在A股、港股或美股上市的公司。"}

PROMPT = """你是一个微信股票机器人的消息分类器。机器人只做两件事：(1) 每日股票筛选报告（A股、美股、港股的买入、持有、卖出名单）；(2) 一家在A股、港股或美股上市的公司的个股研究报告。
读用户的消息，只输出 JSON：{"intent": "", "companies": [], "choice": null, "unsupported": ""}
intent 取一个：
- "screening"：要每日筛选报告、今天的名单、该买哪些股票的列表。
- "research"：问一家或几家具体的公司（中文名、简称、英文名、日文名、拼音、代码、错别字都算），包括问它的股价、估值、前景、能不能买。
- "answer"：消息是在回答下面的「待回答的问题」（选第几个，或说出其中一家）；choice 填所选的编号（整数）。
- "help"：打招呼、问机器人能做什么、道谢。
- "unsupported"：问指数或大盘、加密货币、基金或 ETF、未上市的公司、期货、外汇、债券；unsupported 填 "index"、"crypto"、"fund"、"unlisted" 或 "other"。
- "unclear"：看不出要什么。
companies：消息里提到的每一家公司，按出现的顺序，每家一项：{"said": "消息里的原文", "candidates": [{"name": "中文简称", "name_en": "英文名", "ticker": "股票代码", "market": "cn、hk 或 us"}]}
- candidates 是这段原文可能指的上市公司，最可能的在前。只有原文确实可能指几家不同的公司时才列多家（例如「平安」可能是中国平安，也可能是平安银行）；全称和常用简称（茅台、腾讯、宁德、英伟达、苹果）只列一家。
- 同一家公司在A股、港股或美股都上市时只列一项。拿不准的代码留空，不要编造。未上市的公司不放进 companies。"""


def key(text, loose: bool = False) -> str:
    """A name for matching: NFKC, lower case, no HK share-class tail (-W, -SW, -B), spaces or punctuation. Loose (for
    DeepSeek's hints only, never layer 2) also drops company words: 腾讯 = 腾讯控股, Apple = Apple Inc."""
    s = unicodedata.normalize("NFKC", text if isinstance(text, str) else "").lower().strip()
    s = re.sub(r"-(?:w|sw|b|s|ss|p|pf|r|wr)$", "", s)
    if loose:
        s = re.sub(r"\b(?:the|inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|hldgs|group|"
                   r"grp|class [a-c])\b", " ", re.sub(r"[(),.&'’]", " ", s))
        s = re.sub(r"(?:股份有限公司|有限公司|股份|控股|集团)$", "", s.strip())
    return re.sub(r"[\W_]+", "", s)


@functools.cache
def companies() -> pd.DataFrame:
    """The listings a message may name (built once per process): US lines only if the Nasdaq screener, which lists
    stocks only, has them as ordinary shares (no ETFs, notes or SPACs' units)."""
    us = None
    if nasdaq.LIST.exists():
        us = nasdaq.load_list()
        us = us[nasdaq.ordinary(us)].drop_duplicates("code").set_index("code")["name"]
    return prepare(listings.load(), us)


def prepare(df: pd.DataFrame, us: pd.Series | None) -> pd.DataFrame:
    """The listings with an issuer key and the names to match (us: the screener's US code -> name)."""
    df = df.assign(name_us=None)
    if us is not None:
        df = df[(df["market"] != "us") | df["code"].isin(us.index)]
        df["name_us"] = df["code"].map(us).where(df["market"] == "us")
    df = df[~((df["market"] == "hk") & df["name_en"].fillna("").str.contains(r"-OLD$| RTS$"))]  # parallel counters
    cik = df["cik"].map(lambda x: f"cik{int(float(x))}" if pd.notna(x) else None)
    df["issuer"] = df["org_code"].fillna(cik).fillna(df["market"] + ":" + df["code"])
    for col in ("name", "name_en", "name_us"):
        df[f"k_{col}"] = df[col].map(key)
        df[f"l_{col}"] = df[col].map(lambda x: key(x, True))
    return df.reset_index(drop=True)


def code_of(text: str, hint: bool = False) -> tuple[str, str] | None:
    """(market, code) a code names: 600519, SH600519, 600519.SH; 0700, 00700, 700.HK, HK700; $aapl, aapl.US. A US
    ticker counts only when marked: bare letters are also words and names (HELP, NOW, BYD is Boyd Gaming and 比亚迪's
    English name), so DeepSeek reads them. DeepSeek's hints (hint) need no mark, and HK hints may be 1-3 digits."""
    t = unicodedata.normalize("NFKC", str(text or "")).strip()
    if m := re.fullmatch(r"(?:SH|SZ|BJ)?(\d{6})(?:\.(?:SH|SZ|SS|BJ))?", t, re.I):
        return "cn", m[1]
    if m := re.fullmatch(r"(?:HK)?(\d{4,5})(?:\.HK)?|HK(\d{1,3})|(\d{1,3})\.HK" + (r"|(\d{1,3})" if hint else ""), t, re.I):
        return "hk", next(g for g in m.groups() if g).zfill(5)
    m = re.fullmatch(r"\$?([A-Za-z]{1,5}(?:[.\-/][A-Za-z])?)(\.US)?", t, re.I)
    if m and (hint or t.startswith("$") or m[2]):
        return "us", re.sub(r"[\-/]", ".", m[1].upper())
    return None


def at(found: tuple[str, str] | None) -> list[str]:
    """The issuer key of a (market, code), if it is in the listings."""
    df = companies()
    rows = df[(df["market"] == found[0]) & (df["code"] == found[1])] if found else df.iloc[:0]
    return rows["issuer"].tolist()[:1]


def named(text, loose: bool = False) -> list[str]:
    """Issuer keys whose name, English name or Nasdaq name matches (exactly, or loosely for a hint)."""
    k, df, p = key(text, loose), companies(), "l" if loose else "k"
    if len(k) < 2:
        return []
    hit = (df[f"{p}_name"] == k) | (df[f"{p}_name_en"] == k) | (df[f"{p}_name_us"] == k)
    return list(dict.fromkeys(df.loc[hit, "issuer"]))


def search(text: str) -> list[str]:
    """Issuer keys of the A shares, HK and US securities Eastmoney's search box suggests that are in the listings, in
    its order (searchapi suggest/get, type 14); its Chinese names are kept for display. Nothing when it fails."""
    try:
        resp = httpx.get(SEARCH, params={"input": text, "type": "14", "token": TOKEN, "count": "10"}, timeout=8,
                         headers={"User-Agent": "Mozilla/5.0"})
        rows = (resp.json().get("QuotationCodeTable") or {}).get("Data") or []
    except (httpx.HTTPError, ValueError) as e:
        log.warning("search box: %s", e)
        return []
    out = []
    for x in rows:
        if (market := CLASSES.get(x.get("Classify"))) and (found := code_of(x.get("Code", "").replace("_", "."), True)):
            if found[0] == market and (k := at(found)):
                CHINESE_NAMES.setdefault(found, x.get("Name") or "")
                out += k
    return list(dict.fromkeys(out))


def issuer(k: str, lead: tuple[str, str] | None = None) -> dict:
    """One company: its name and its lines, the lead first (the code named, else A, H, then US, in listing order)."""
    df = companies()
    rows = df[df["issuer"] == k].assign(o=lambda d: d["market"].map(MARKETS.index)).sort_values("o", kind="stable")
    if lead:
        rows = pd.concat([rows[(rows["market"] == lead[0]) & (rows["code"] == lead[1])], rows]).drop_duplicates(["market", "code"])
    lines = [{"market": r["market"], "code": r["code"], "name": shown(r)} for _, r in rows.iterrows()]
    chinese = next((x["name"] for x in lines if re.search(r"[一-鿿]", x["name"])), None)
    return {"key": k, "name": chinese or lines[0]["name"], "lines": lines}


def shown(r: pd.Series) -> str:
    """A listing's name to show: its Chinese short name without the HK share-class tail, the search box's Chinese name
    (US lines), else its English name."""
    if isinstance(r["name"], str) and r["name"]:
        return re.sub(r"-[A-Z]+$", "", unicodedata.normalize("NFKC", r["name"]))
    return CHINESE_NAMES.get((r["market"], r["code"])) or next(
        (x for x in (r["name_us"], r["name_en"]) if isinstance(x, str) and x), r["code"])


def label(o: dict) -> str:
    codes = [x["code"] + (".HK" if x["market"] == "hk" else "") for x in o["lines"][:3]]
    return f"{o['name']}（{' / '.join(codes)}）"


def research(o: dict, layer: int, rest: list[str] | None = None) -> dict:
    return {"action": "research", "layer": layer, "issuer": o, "rest": rest or []}


def ask(options: list[dict], layer: int) -> dict:
    options = options[:CFG["options"]]
    text = (f"你是指 {label(options[0])}吗？是的话回复 1。" if len(options) == 1 else
            "你指的是哪一家？回复数字或名称：\n" + "\n".join(f"{i} {label(o)}" for i, o in enumerate(options, 1)))
    return {"action": "ask", "layer": layer, "text": text, "options": options}


def reply(text: str, layer: int) -> dict:
    return {"action": "reply", "layer": layer, "text": text}


def pick(text: str, options: list[dict]) -> dict | None:
    """The option a reply to the question names, without AI: its number (1, 第一个, ２) or its name or code alone."""
    k = key(text)
    if m := re.fullmatch(r"第?([1-9]|[一二三四五六七八九])(?:个|家|号)?", k):
        i = int(m[1]) if m[1].isdigit() else "一二三四五六七八九".index(m[1]) + 1
        return options[i - 1] if i <= len(options) else None
    hits = [o for o in options if len(k) >= 2 and (k in key(o["name"]) or any(k == key(x["code"]) for x in o["lines"]))]
    return hits[0] if len(hits) == 1 else None


def exact(text: str) -> list[dict]:
    """Layer 2: the companies an exact code or an exact full name names (no AI)."""
    if found := code_of(text):
        return [issuer(k, found) for k in at(found)]
    return [issuer(k) for k in named(text)]


def confirm(c: dict) -> tuple[list[str], bool]:
    """The issuer keys one of DeepSeek's candidates names, confirmed by code: its ticker in the listings, its names
    there (loosely), and the search box's first hit for its name; and whether a name confirmed them. A ticker no name
    confirms isn't taken on its own (the question asks); a ticker and a name pointing at different companies give
    both, so the question asks."""
    t = at(code_of(str(c.get("ticker") or ""), True))
    n = named(c.get("name"), True) or named(c.get("name_en"), True)
    s = []
    if not (t and t[0] in n):
        for q in (c.get("name"), c.get("name_en")):
            if q and (s := search(str(q))[:1]):
                break
    if t and t[0] in n + s:
        return t, True
    return list(dict.fromkeys(t + (n or s))), bool(n or s) and not t


def read(text: str, pending: dict | None) -> dict | None:
    """DeepSeek's reading of the message (layer 3), or None when it can't be reached."""
    user = f"消息：{text}" + (f"\n\n待回答的问题：{pending['text']}" if pending else "")
    try:
        got = words.Client(CFG["model"], CFG).ask(PROMPT, user)
    except Exception as e:
        log.warning("router: DeepSeek unavailable (%s)", e)
        return None
    log.info("router: DeepSeek read %r as %s", text[:60], got)
    return got


def decide(got: dict, text: str, pending: dict | None) -> dict:
    intent, options = got.get("intent"), (pending or {}).get("options") or []
    choice = got.get("choice")
    if intent == "answer" and isinstance(choice, int) and 1 <= choice <= len(options):
        return research(options[choice - 1], 3)
    if intent == "screening":
        return {"action": "screening", "layer": 3}
    if intent == "unsupported":
        return reply(UNSUPPORTED.get(got.get("unsupported"), UNSUPPORTED["other"]) + "\n\n" + HELP, 3)
    flat = key(text)
    mentions = [m for m in got.get("companies") or [] if isinstance(m, dict) and isinstance(m.get("said"), str)
                and key(m["said"]) and key(m["said"]) in flat]  # a company the message doesn't mention is dropped
    if intent != "research" or not mentions:
        return reply(HELP, 3)
    first, rest = mentions[0], [m["said"] for m in mentions[1:]]
    checked = [confirm(c) for c in (first.get("candidates") or [])[:CFG["options"]] if isinstance(c, dict)]
    found = list(dict.fromkeys(k for keys, _ in checked for k in keys))
    if len(found) == 1 and all(sure for _, sure in checked):
        return research(issuer(found[0]), 3, rest)
    if found:
        return ask([issuer(k) for k in found], 3)
    if found := search(first["said"]):
        return ask([issuer(k) for k in found], 4)
    return reply(f"没找到「{first['said']}」对应的A股、港股或美股上市公司。请发公司全称或股票代码（如 600519、0700、AAPL）。", 3)


def route(text: str, pending: dict | None = None) -> dict:
    """The decision for a message that isn't the keyword: {action: research | ask | screening | reply, layer, and
    issuer and rest (research), text and options (ask), text (reply)}. pending: the open question {text, options}."""
    t = TRAIL.sub("", unicodedata.normalize("NFKC", text).strip())
    if not t:  # "?", "。"
        return reply(HELP, 2)
    if pending and (o := pick(t, pending["options"])):
        return research(o, 4)
    if hits := exact(t):
        return research(hits[0], 2) if len(hits) == 1 else ask(hits, 2)
    got = read(t, pending)
    if got is None:  # DeepSeek down: the search box's suggestions as a question, else what the bot can do
        found = list(dict.fromkeys(at(code_of(t, True) if re.fullmatch(r"[A-Za-z.\-]{1,7}", t) else None) + search(t)))
        return ask([issuer(k) for k in found], 4) if found else reply(HELP, 4)
    return decide(got, t, pending)
