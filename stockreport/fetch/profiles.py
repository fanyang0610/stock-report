"""What each company does, for the cards' business line (PLAN.md, "Report"): Eastmoney's F10 profile tables, one call per
market for the lists' names (CN 主营业务, RPT_F10_BASIC_ORGINFO; HK 主营业务, RPT_HKF10_INFO_ORGPROFILE; the profile where
either is blank) and, for US, Eastmoney's Chinese short name (RPT_USF10_INFO_ORGPROFILE) and the opening of Yahoo's
business summary (assetProfile), which says what the company does, while Eastmoney's US profiles often open with where
and when it was incorporated. The review writes one Chinese line from a US text or a long CN/HK one (notes.line).
Kept in data/fundamentals/<market>_profiles.csv.gz (source: the text as fetched, up to SOURCE_MAX characters; line: the
review's line), fetched again after REFRESH days."""

import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport.config import DATA
from stockreport.fetch import each, merge, stale
from stockreport.fetch.eastmoney import datacenter
from stockreport.fetch.yahoo import MARKETS, SUMMARY, crumb_http

log = logging.getLogger(__name__)
PATH = str(DATA / "fundamentals" / "{}_profiles.csv.gz")
REFRESH = 180  # days: a company's business rarely changes faster
SOURCE_MAX = 400  # characters of the source text kept (US: Yahoo's first few sentences)
TABLES = {"cn": "RPT_F10_BASIC_ORGINFO", "hk": "RPT_HKF10_INFO_ORGPROFILE", "us": "RPT_USF10_INFO_ORGPROFILE"}
COLUMNS = ["code", "name_cn", "source", "line"]
# a sentence ends at 。；;!? (Chinese), or at '. ' before a capital (English; "Inc. designs" goes on)
SENTENCE = re.compile(r"(?<=[。；;！？!?])|(?<=[a-z)]\.)\s+(?=[A-Z])")


def sentences(text) -> list[str]:
    """The text's sentences, without the leading 是 of Eastmoney's HK lines ("是一家主要从事…的公司")."""
    text = re.sub(r"^是(?=一家)", "", " ".join(text.split()) if isinstance(text, str) else "")
    return [s.strip() for s in SENTENCE.split(text) if s.strip()]


def lead(text) -> str:
    """The whole sentences that fit in SOURCE_MAX characters (at least the first, cut there)."""
    out = ""
    for s in sentences(text):
        if out and len(out) + len(s) + 1 > SOURCE_MAX:
            break
        out += (" " if out.endswith(".") else "") + s
    return out[:SOURCE_MAX]


def first(text) -> str:
    return next(iter(sentences(text)), "")


def summary(http, code: str) -> str | None:
    payload = http.get(SUMMARY.format(symbol=MARKETS["us"][2](code)),
                       params={"modules": "assetProfile", "crumb": http.crumb}).json()
    found = ((payload.get("quoteSummary") or {}).get("result") or [{}])[0].get("assetProfile") or {}
    return lead(found.get("longBusinessSummary")) or None


def update(market: str, codes: list[str], today: date) -> None:
    """The profiles of `codes` not fetched in the last REFRESH days (one Eastmoney call; US also one Yahoo call each)."""
    path = Path(PATH.format(market))
    todo = stale(path, list(dict.fromkeys(codes)), today, REFRESH)
    if not todo:
        return
    columns = "SECURITY_CODE,SECURITY_NAME_ABBR,ORG_PROFILE" + ("" if market == "us" else ",MAIN_BUSINESS")
    rows = datacenter(TABLES[market], "(SECURITY_CODE in (" + ",".join(f'"{c}"' for c in todo) + "))", columns)
    found = pd.DataFrame([{"code": r["SECURITY_CODE"], "name_cn": r["SECURITY_NAME_ABBR"],
                           "source": None if market == "us" else lead(r.get("MAIN_BUSINESS")) or lead(r.get("ORG_PROFILE"))}
                          for r in rows], columns=COLUMNS[:3]).drop_duplicates("code").set_index("code")
    new = found.reindex(todo).rename_axis("code").assign(line=None)
    if market == "us":
        new["source"] = list(each(crumb_http, summary, todo, 2))
    new = new[new["source"].notna() & (new["source"] != "")]  # nothing found: asked again next build
    merge(path, new.reset_index().assign(fetched=today.isoformat()), ["code"])
    log.info("%s profiles: %d of %d found", market.upper(), len(new), len(todo))


def load(market: str) -> pd.DataFrame:
    path = Path(PATH.format(market))
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS).set_index("code")
    return pd.read_csv(path, dtype=str).set_index("code").reindex(columns=COLUMNS[1:] + ["fetched"])


def save_lines(market: str, lines: dict[str, str]) -> None:
    """The review's lines (code -> line; '' when the line was dropped, so it isn't asked for again)."""
    table = load(market)
    for code, line in lines.items():
        if code in table.index and line is not None:
            table.at[code, "line"] = line or "-"
    merge(Path(PATH.format(market)), table.reset_index(), ["code"])
