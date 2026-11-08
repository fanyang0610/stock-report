"""Quote checks for the results review (AGENTS.md rule 2): a finding counts only when its quote is in the source line
it cites (whitespace and full-width forms normalized); about() reads what a hard finding's quote is about."""

import re
import unicodedata

MIN_QUOTE = 6


def norm(text) -> str:
    """NFKC (full-width digits, brackets and colons to ASCII) without any whitespace."""
    return "".join(unicodedata.normalize("NFKC", str(text or "")).split())


def find(full: str, quote: str) -> int:
    """Position of the normalized quote in the normalized source text, -1 if absent or too short."""
    return full.find(quote) if len(quote) >= MIN_QUOTE else -1


# a going-concern quote about a subsidiary alone is soft: its insolvency isn't the company's
SUBSIDIARY = (re.compile(r"子公司|附属公司|附屬公司|subsidiar", re.I),
              re.compile(r"(公司|集团|集團|本行)(及|和|与|與|以及)其?(全资|全資|控股|下属|下屬)?(子公司|附属|附屬)|and (its|their) subsid", re.I))
OPINION = re.compile(r"(?<![无無非])保留意[见見]|否定意[见見]|无法表示意见|無法表示意見|不發表意見|(?<!un)qualified opinion|"
                     r"adverse opinion|disclaimer of opinion", re.I)
# what an audit opinion is on: internal control (a SOX 404 or 内部控制审计报告 opinion) or the accounts
SUBJECT = re.compile(r"(?P<control>internal control|内部控制|內部控制)|(?P<accounts>financial statements|财务报表|財務報表|"
                     r"会计报表|會計報表|财务报告(?!内部控制)|財務報告(?!內部控制))", re.I)
AFTER = re.compile(r"\s*(?:的|on|of)\s*(?:the Company's\s*)?", re.I)  # 否定意见的内部控制…, adverse opinion on internal control
SENTENCE = re.compile(r"[。！？；]|\.\s+(?=[A-Z])")


def about(kind: str, quote: str, text: str) -> str:
    """The kind a hard finding is about, from its quote and the source text it was cut from: "other" for a going concern
    of a subsidiary alone; "control" for an audit opinion on internal control rather than on the accounts (the subject
    named right after the opinion word, else the nearest one before it in its sentence; none named: the accounts); else
    the kind itself."""
    if kind == "going_concern":
        return "other" if SUBSIDIARY[0].search(quote) and not SUBSIDIARY[1].search(quote) else kind
    full, q = " ".join(str(text).split()), " ".join(str(quote).split())
    at = full.find(q)
    full, at = (full, at) if at >= 0 else (q, 0)
    opinion = OPINION.search(full, at, at + len(q)) if kind == "audit" else None
    if opinion is None:
        return kind
    after = AFTER.match(full, opinion.end())
    subject = SUBJECT.match(full, after.end()) if after and after.end() > opinion.end() else None
    if subject is None:
        start = max((m.end() for m in SENTENCE.finditer(full, 0, opinion.start())), default=0)
        subject = ([None] + list(SUBJECT.finditer(full, start, opinion.start())))[-1]
    return "control" if subject is not None and subject.group("control") else kind
