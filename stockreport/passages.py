"""Periodic-report passages for the results review (PLAN.md, "Results review"): code, not DeepSeek, cuts from each
name's latest periodic report (fetch/filings.periodic) the text around the words of the hard red flags a filing title
rarely names: a non-standard audit opinion, a going-concern doubt, a regulator's investigation, an agreed sale of the
company (Kenvue's pending sale to Kimberly-Clark is only in its 10-Q's text). Read in the build for the names whose hard
flag changes a list (the buys, the Hold names and their benches), at most `per_day` new filings per market a day,
cached per filing (data/passages/<market>/<code>_<filing>.json); the review reads them with the name's filing titles
and headlines, in its one DeepSeek call. strict() is what a hard flag quoted from a passage must say."""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import filings

log = logging.getLogger(__name__)
CFG = CONFIG["passages"]
CACHE = DATA / "passages"
ROLES = ("buy", "next", "hold", "hold_next")  # where a hard red flag removes a name; on a Sell name it only annotates
# The words the passages are cut around: the hard red flags a periodic report states in its text
KEYWORDS = re.compile(
    r"(?<![无無非])保留意[见見]|否定意[见見]|无法表示意见|無法表示意見|不發表意見|(?<!un)qualified opinion|adverse opinion|"
    r"disclaimer of opinion|持续经营能力|持續經營能力|重大不确定性|重大不確定性|going concern|substantial doubt|"
    r"立案|行政处罚|行政處罰|Wells notice|subpoena|Division of Enforcement|investigation|欺诈|欺詐|"
    r"(?<![何有在无無])(虚假记载|虛假記載)|"  # not every CN report's pledge: 不存在任何虚假记载, 没有虚假记载
    r"要约收购|要約收購|私有化|吸收合[并併]|协议安排|協議安排|scheme of arrangement|Agreement and Plan of Merger|"
    r"Pending Transaction|merger agreement|merger consideration|tender offer", re.I)

NON_STANDARD = re.compile(r"(?<![无無非])保留意[见見]|否定意[见見]|无法表示意见|無法表示意見|不發表意見|"
                          r"(?<!un)qualified opinion|adverse opinion|disclaimer of opinion", re.I)
STANDARD = re.compile(r"标准无保留|標準無保留|无保留意见|無保留意見|unqualified opinion|present fairly", re.I)
DOUBT = re.compile(r"重大不确定|重大不確定|重大疑虑|重大疑慮|substantial doubt", re.I)
OPENED = re.compile(r"立案|Wells notice|subpoena|Division of Enforcement|欺诈|欺詐|虚假记载|虛假記載|造假|fraud", re.I)
# legal-proceedings boilerplate in a periodic report: no investigation opened
BOILERPLATE = re.compile(r"ordinary course|from time to time|various (investigations|claims|legal)|日常经营|日常業務", re.I)
# an agreed sale of the company itself (it is the one acquired: a filer's 10-Q says "acquire the Company" and "Company
# shareholders will receive"; an acquirer's names the target), not completed or terminated
ACQUIRED = re.compile(r"acquire (the|all (of )?the (outstanding )?(shares|common stock) of the) Company|"
                      r"Company'?s? (share|stock)holders will receive|merger consideration|被.{0,10}(吸收合[并併]|收[购購])|"
                      r"(吸收合[并併]|收[购購])本公司|私有化|协议安排|協議安排|scheme of arrangement", re.I)
DONE = re.compile(r"已完成|已經完成|已终止|已終止|(has|have|was|were) (been )?(completed|consummated|terminated)", re.I)
# kind -> (what the quote must say, what it mustn't, the kind when it doesn't: None = no finding at all)
STRICT = {"audit": (NON_STANDARD, STANDARD, None), "going_concern": (DOUBT, None, None),
          "investigation": (OPENED, BOILERPLATE, "other"), "takeover": (ACQUIRED, DONE, None)}


def strict(kind: str, quote: str) -> tuple[str | None, bool]:
    """(kind, hard) of a finding quoted from a passage: a hard kind stands only when the quote says it plainly (a
    standard opinion, a going-concern note, the company buying another or a deal done are no finding; a regulator's
    letter or a legal note is a soft concern); the other hard kinds are soft here (their filings' titles carry them)."""
    if kind not in STRICT:
        return kind, False
    must, mustnt, otherwise = STRICT[kind]
    if must.search(quote) and not (mustnt and mustnt.search(quote)):
        return kind, True
    return otherwise, False


def cut(text: str) -> list[str]:
    """Windows of text around the keywords within `max_chars`: the first hit of every keyword, then the second, merged
    and in document order."""
    before, after = CFG["window"]
    spans, seen = [], {}
    for m in KEYWORDS.finditer(text):
        key = m.group(0).lower()
        seen[key] = seen.get(key, 0) + 1
        if seen[key] <= 2:
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
    return [" ".join(text[a:b].split()) for a, b in merged]


def filing_id(market: str, url: str) -> str:
    parts = url.rstrip("/").split("/")
    return f"{market}-{parts[-2] if market == 'us' else parts[-1].split('.')[0]}"


def read_filing(market: str, code: str, filing: dict, path, today: date) -> None:
    """Cut one filing's passages into its cache file (nothing written when it can't be fetched)."""
    started = time.monotonic()
    try:
        text = filings.text(market, filing["url"])
    except Exception as e:
        log.warning("passages %s %s: %s", market, code, e)
        return
    entry = {k: filing[k] for k in ("title", "date", "url")} | {"read": today.isoformat(), "passages": cut(text)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("passages %s %s %s: %d, %d of %d chars, %.0fs", market, code, filing["title"], len(entry["passages"]),
             sum(map(len, entry["passages"])), len(text), time.monotonic() - started)


def latest(market: str, code: str, today: date) -> dict | None:
    """One stock's latest periodic-report passages (the research report's own review), from the same cache."""
    filing = filings.periodic(market, code, today)
    if filing is None:
        return None
    path = CACHE / market / f"{code}_{filing_id(market, filing['url'])}.json"
    if not path.exists():
        read_filing(market, code, filing, path, today)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def update(market: str, rows: pd.DataFrame, today: date) -> dict[str, dict]:
    """Code -> the passages of its latest periodic report ({title, date, passages}), for the names in ROLES; the
    filings not read yet are read first, at most `per_day` per market a day (the rest wait for the next build).
    Cached filings older than `keep_days` are deleted."""
    folder = CACHE / market
    folder.mkdir(parents=True, exist_ok=True)
    read = sum(json.loads(p.read_text(encoding="utf-8")).get("read") == today.isoformat() for p in folder.glob("*.json"))
    codes = list(dict.fromkeys(rows.loc[rows["list"].isin(ROLES)].sort_values("rank", kind="stable")
                               .assign(o=lambda d: d["list"].map(ROLES.index)).sort_values("o", kind="stable")["code"]))

    def newest(code):
        try:
            return filings.periodic(market, code, today)
        except Exception as e:
            log.warning("passages %s %s: no filing (%s)", market, code, e)

    with ThreadPoolExecutor(CFG["workers"]) as pool:
        found = {c: f for c, f in zip(codes, pool.map(newest, codes)) if f}
    paths = {c: folder / f"{c}_{filing_id(market, f['url'])}.json" for c, f in found.items()}
    todo = [c for c in codes if c in paths and not paths[c].exists()][:max(0, CFG["per_day"] - read)]

    with ThreadPoolExecutor(CFG["workers"]) as pool:
        list(pool.map(lambda c: read_filing(market, c, found[c], paths[c], today), todo))
    cutoff = time.time() - CFG["keep_days"] * 86400
    for old in folder.glob("*.json"):
        if old.stat().st_mtime < cutoff:
            old.unlink()
    out = {c: json.loads(p.read_text(encoding="utf-8")) for c, p in paths.items() if p.exists()}
    log.info("passages %s: %d of %d names (%d filings read, %d earlier today, limit %d)", market.upper(), len(out),
             len(codes), len(todo), read, CFG["per_day"])
    return out
