"""Research stage 11, part 1: the outside text the report's words read (PLAN.md "The analysis in words"), gathered by
code into numbered source lines. The latest annual report's sections, cut by their standard headings:
- CN (CSRC format): the 管理层讨论与分析 section, and in it 主要业务, 核心竞争力, 经营情况, 未来发展 and 可能面对的风险;
- US 10-K: Item 1 (business), the risk headings of Item 1A and Item 7 (MD&A); a 20-F's Items 4, 3 and 5;
- HK (the English annual report): the Chairman's Statement, the MD&A, the outlook and the principal risks.
A CN report whose PDF fonts have no Unicode map (招商银行's) gives way to its issuer's HK annual report. Then the
latest US results release (8-K Ex-99.1), 12 months of non-routine filing titles, 90 days of headlines, and 6 months of
broker report titles (CN) or rating changes (US, HK). The cut sections are a small extract cached per stock
(sections.json); the documents are read in memory and never stored."""

import logging
import re
from collections import Counter
from datetime import date, timedelta

from stockreport.fetch import filings, news
from stockreport.research import cached, days, folder, listings, load

log = logging.getLogger(__name__)
CAP = {"cn": 4500, "hk": 6000, "us": 6000}  # characters a section keeps
LINE = {"cn": 260, "hk": 520, "us": 520}  # characters a source line holds at most
PARTS = {"business": "主要业务", "moat": "核心竞争力", "review": "经营情况", "outlook": "未来发展", "risks": "风险",
         "chairman": "主席报告", "mdna": "管理层讨论与分析"}
CN_SECTION = re.compile(r"第[一二三四五六七八九十]+[节章]\s*\S{2,24}")
CN_MDNA = re.compile(r"管理层讨论与分析|经营情况讨论与分析|董事会报告")
CN_TOPICS = {"business": r"从事的.{0,6}业务|主要业务|业务概要|所处行业", "moat": r"核心竞争力",
             "review": r"经营情况.{0,3}讨论与分析|主要经营情况|总体经营情况|经营情况分析|经营情况回顾", "outlook": r"未来发展|发展战略|经营计划|发展展望",
             "risks": r"可能面对的风险|面临的.{0,6}风险|风险因素"}
US_ITEM = re.compile(r"item\s*(\d+[a-c]?)\s*[.:]?", re.I)
US_ITEMS = {"10-K": {"business": "1", "risks": "1A", "mdna": "7"}, "20-F": {"business": "4", "risks": "3", "mdna": "5"}}
# HK headings, as a line reads with everything but letters and digits removed (a contents line keeps its page number)
HK_HEAD = {"chairman": r"chairmans?(statement|letter|report)|lettertoshareholders|(statement|message)fromthechairman",
           "mdna": r"managements?discussionandanalysis|businessreview|operationalreview|reviewofoperations|businessandfinancialreview"}
HK_STOP = re.compile(r"directorsreport|reportofthedirectors|corporategovernance(report)?|independentauditorsreport|"
                     r"environmentalsocialandgovernance[a-z]*|biographical[a-z]*|directorsandseniormanagement|[a-z]*profilesof[a-z]*|"
                     r"consolidated[a-z]*statement[a-z]*|financialsummary|fiveyear[a-z]*|corporateinformation|definitions?|glossary")
HK_SUB = {"outlook": re.compile(r"[a-z]{0,24}(outlook|prospects)[a-z]{0,16}"),
          "risks": re.compile(r"[a-z]{0,12}(principal|key|major)risks[a-z]{0,24}|riskfactors|[a-z]{0,12}risksanduncertainties")}


def key(line: str) -> str:
    return re.sub(r"[^a-z0-9]", "", line.lower())


def heading(line: str) -> bool:
    """A section heading of any market (kept even when it repeats as a page header)."""
    k = key(line)
    return len(line) <= 60 and bool(CN_SECTION.fullmatch(line) or HK_STOP.fullmatch(k) or any(re.fullmatch(p, k) for p in HK_HEAD.values()))


def lines_of(text: str) -> list[str]:
    """The document's lines without page furniture: lines repeated 4 times or more (headers, footers; not section
    headings), page numbers, the CSRC's 适用 / 不适用 boxes, and table rows (mostly figures)."""
    raw = [" ".join(x.split()) for x in text.splitlines()]
    seen = Counter(x for x in raw if x)
    out = []
    for x in raw:
        if not x or seen[x] >= 4 and not heading(x) or re.fullmatch(r"[\d\s/|\-–第页]+", x) or re.fullmatch(r"[√□\s]*(适用|不适用)[√□\s适用不]*", x):
            continue
        if len(x) > 8 and len(re.findall(r"[\d,.%()\-]", x)) > 0.4 * len(x.replace(" ", "")):
            continue
        out.append(x)
    return out


def join(lines: list[str]) -> str:
    """Lines into running text: a PDF breaks Chinese sentences mid-line (no space then), English words take one."""
    out = ""
    for x in lines:
        if out and not (re.search(r"[一-鿿，。、；：（）「」“”]$", out) and re.match(r"[一-鿿，。、；：（）「」“”]", x)):
            out += " "
        out += x
    return out


def capped(lines: list[str], cap: int) -> str:
    """The running text of `lines` up to `cap` characters, ended at a sentence."""
    text = join(lines)
    if len(text) <= cap:
        return text
    head = text[:cap]
    stop = max(head.rfind(m) for m in ("。", "；", ". ", "! ", "? "))
    return head[:stop + 1] if stop > cap // 2 else head


def level(line: str) -> int | None:
    """A CN heading's level from its numbering: 一、 is 1, （一） 2, 3.1 1 and 3.1.1 2 (banks' sections), 1. 3."""
    if re.match(r"[一二三四五六七八九十]+、", line):
        return 1
    if re.match(r"[（(][一二三四五六七八九十]+[）)]", line):
        return 2
    if m := re.match(r"\d+(\.\d+)+(?!\d)", line):
        return m.group(0).count(".")
    return 3 if re.match(r"\d+[.、](?!\d)", line) else None


def cut_cn(text: str) -> dict[str, str]:
    lines = lines_of(text)
    heads = [i for i, x in enumerate(lines) if CN_SECTION.fullmatch(x)]  # a contents line carries dots or a page number
    start = next((i for i in heads if CN_MDNA.search(lines[i])), None)
    body = lines[start + 1:next((i for i in heads if i > start), len(lines))] if start is not None else lines
    out = {}
    for topic, words in CN_TOPICS.items():  # every heading of the topic, in order, up to the cap
        taken = []
        for at in (i for i, x in enumerate(body) if len(x) <= 40 and level(x) and re.search(words, x)):
            lv = level(body[at])
            end = next((j for j in range(at + 1, len(body)) if len(body[j]) <= 40 and (level(body[j]) or 9) <= lv), len(body))
            taken += [x for x in body[at:end] if x not in taken]
        if text := capped(taken, CAP["cn"]):
            out[topic] = text
    return out


def cut_us(text: str, form: str) -> dict[str, str]:
    lines, items = lines_of(text), US_ITEMS["20-F" if form.startswith(("20-F", "40-F")) else "10-K"]
    heads = [(i, m.group(1).upper()) for i, x in enumerate(lines) if len(x) < 200 and (m := US_ITEM.match(x))]
    spans = {}  # each item's longest span (the contents list it with no text under it)
    for (i, item), (j, _) in zip(heads, heads[1:] + [(len(lines), None)]):
        if j - i > (lambda s: s[1] - s[0])(spans.get(item, (0, 0))):
            spans[item] = (i, j)
    out = {}
    for topic, item in items.items():
        if item not in spans:
            continue
        body = lines[spans[item][0] + 1:spans[item][1]]
        if topic == "risks":  # the risk headings: one-sentence paragraphs between the long ones
            body = [x for x in body if 40 <= len(x) <= 350 and x.endswith(".")]
        if text := capped(body, CAP["us"]):
            out[topic] = text
    return out


def cut_hk(text: str) -> dict[str, str]:
    lines = lines_of(text)
    keys = [key(x) for x in lines]
    out = {}
    for topic, pattern in HK_HEAD.items():
        at = next((i for i, k in enumerate(keys) if re.fullmatch(pattern, k)), None)
        if at is None:
            continue
        others = [p for t, p in HK_HEAD.items() if t != topic]
        end = next((j for j in range(at + 1, len(keys)) if len(lines[j]) <= 60 and (
            HK_STOP.fullmatch(keys[j]) or any(re.fullmatch(p, keys[j]) for p in others))), len(keys))
        if text := capped([x for x, k in zip(lines[at + 1:end], keys[at + 1:end]) if k != keys[at]], CAP["hk"]):  # no page headers
            out[topic] = text
    for topic, pattern in HK_SUB.items():
        at = next((i for i, k in enumerate(keys) if len(lines[i]) <= 40 and pattern.fullmatch(k)), None)
        if at is not None and (text := capped(lines[at + 1:at + 200], CAP["hk"] // 2)):
            out[topic] = text
    return out


def read(market: str, filing: dict) -> dict[str, str]:
    text = filings.text(market, filing["url"])
    if not text:
        return {}
    return cut_cn(text) if market == "cn" else cut_hk(text) if market == "hk" else cut_us(text, filing["title"])


def release(titles: list[dict], today: date) -> dict | None:
    """The newest US results release of the last 120 days: its 8-K's Ex-99.1, the opening text (headline, the CEO's
    words, the outlook) without its tables."""
    since = (today - timedelta(days=120)).isoformat()
    eight = next((t for t in titles if t["title"].startswith("8-K") and "results of operations" in t["title"].lower()
                  and t["date"] >= since), None)
    if eight is None:
        return None
    base = eight["url"].rsplit("/", 1)[0]
    found = filings.client("us").get(base + "/index.json").json()["directory"]["item"]
    name = next((x["name"] for x in found if re.search(r"ex-?99", x["name"], re.I) and x["name"].endswith((".htm", ".html"))), None)
    text = filings.text("us", f"{base}/{name}") if name else ""
    return {"date": eight["date"], "title": "8-K 业绩公告", "text": capped(lines_of(text), CAP["us"])} if text else None


def sections(market: str, code: str, today: date) -> dict:
    """The latest annual report's cut sections (cached weekly): {doc, date, url, market (of the document), parts,
    release, note}."""
    def make():
        out = {"doc": None, "date": None, "url": None, "market": market, "parts": {}, "release": None, "note": None}
        filing = filings.periodic(market, code, today, annual=True)
        if filing:
            out |= {"doc": filing["title"], "date": filing["date"], "url": filing["url"], "parts": read(market, filing)}
        if not out["parts"] and market == "cn":  # unreadable fonts: the issuer's HK annual report, in English
            for _, o in listings.issuer(market, code).query("market == 'hk'").iterrows():
                if (h := filings.periodic("hk", o["code"], today, annual=True)) and (parts := read("hk", h)):
                    out |= {"doc": f"{h['title']}（H 股 {o['code']}）", "date": h["date"], "url": h["url"], "market": "hk",
                            "parts": parts, "note": "A 股年报的 PDF 文字无法读取，改读 H 股英文年报"}
                    break
        if not out["parts"]:
            out["note"] = "未取到可读的年报" if not filing else "年报的 PDF 文字无法读取"
        if market == "us":
            try:
                out["release"] = release(load(folder(market, code) / "filings.json"), today)
            except Exception as e:
                log.warning("%s results release: %s", code, e)
        log.info("%s sections: %s %s", code, out["doc"], {k: len(v) for k, v in out["parts"].items()})
        return out
    return cached(folder(market, code) / "sections.json", days("statements"), make)


def chunks(text: str, size: int) -> list[str]:
    """Running text as source lines of at most `size` characters, broken at sentences."""
    parts = [p for p in re.split(r"(?<=[。！？；])|(?<=[.!?;])\s+(?=[A-Z“\"(])", text) if p and p.strip()]
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) > size:
            out.append(cur.strip())
            cur = ""
        cur += (" " if cur and re.search(r"[A-Za-z.,;]$", cur) else "") + p
        while len(cur) > size * 1.5:
            out.append(cur[:size].strip())
            cur = cur[size:]
    return out + ([cur.strip()] if cur.strip() else [])


def headlines(market: str, code: str, today: date) -> list[dict]:
    path = folder(market, code) / "headlines.json"
    return cached(path, days("daily"), lambda: news.headlines(news.client(market), market, code, today, 90, 30))


def bundle(facts: dict, today: date) -> tuple[list[dict], dict]:
    """The numbered source lines the words cite ({type, date, text, part?, doc?}) and the sections' record."""
    market, code = facts["market"], facts["code"]
    try:
        s = sections(market, code, today)
    except Exception as e:
        log.warning("%s sections: %s", code, e)
        s = {"parts": {}, "release": None, "note": f"年报读取失败（{type(e).__name__}）", "market": market}
    out = [{"type": "年报", "part": PARTS[t], "date": s["date"], "doc": s["doc"], "text": c}
           for t, text in s["parts"].items() for c in chunks(text, LINE[s["market"]])]
    if s.get("release"):
        out += [{"type": "业绩公告", "date": s["release"]["date"], "text": c} for c in chunks(s["release"]["text"], LINE["us"])]
    titles = load(folder(market, code) / "filings.json") if (folder(market, code) / "filings.json").exists() else []
    out += [{"type": "公告", "date": t["date"], "text": t["title"]} for t in titles if t["kind"] != "routine"][:25]
    try:
        out += [{"type": "新闻", "date": h["date"], "text": h["title"]} for h in headlines(market, code, today)]
    except Exception as e:
        log.warning("%s headlines: %s", code, e)
    since = (today - timedelta(days=183)).isoformat()
    c = facts["consensus"]
    if market == "cn":
        out += [{"type": "研报", "date": r["date"], "text": f"{r['broker']}：{r['title']}（{r.get('rating') or '无评级'}）"}
                for r in c.get("reports") or [] if r["date"] >= since][:20]
    else:
        out += [{"type": "评级变动", "date": m["date"], "text": f"{m['firm']}: {m['grade']}" + (f", target {m['target']:g}" if m.get("target") else "")}
                for m in facts["street"].get("target_moves_6m") or [] if m["date"] >= since][:15]
    return out, s
