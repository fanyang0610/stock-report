"""Business segments for US and HK listings, in the layout of CN's 主营构成 (cn.segments): one row per fiscal year,
breakdown (segment, product, region) and item, with its revenue, share of the total, gross margin and operating
profit. US: the latest annual report's XBRL instance (10-K, 20-F or 40-F; SEC's companyfacts carries no dimensions)
with the labels of its MetaLinks.json. HK: an A+H issuer's A line, an issuer's own SEC filing, else the annual
report's segment note. A breakdown is kept only for a year whose parts add up to the reported total, and a figure
only under a name read for certain; what can't be checked is left out (rule 5)."""

import html
import io
import re
import xml.etree.ElementTree as ET
from datetime import date
from itertools import combinations

import pandas as pd

from stockreport.fetch import filings
from stockreport.research import cn, listings

XBRLI, XDI = "{http://www.xbrl.org/2003/instance}", "{http://xbrl.org/2006/xbrldi}"
AXES = {"segment": {"us-gaap:StatementBusinessSegmentsAxis", "ifrs-full:SegmentsAxis"},
        "product": {"srt:ProductOrServiceAxis", "us-gaap:ProductOrServiceAxis", "ifrs-full:ProductsAndServicesAxis"},
        "region": {"srt:StatementGeographicalAxis", "us-gaap:StatementGeographicalAxis", "ifrs-full:GeographicalAreasAxis"}}
CONSOLIDATION, OPERATING_SEGMENTS = "srt:ConsolidationItemsAxis", ("us-gaap:OperatingSegmentsMember", "srt:OperatingSegmentsMember")
REVENUE = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax",
           "SalesRevenueNet", "Revenue", "RevenueFromContractsWithCustomers")
OPERATING = ("OperatingIncomeLoss", "ProfitLossFromOperatingActivities")
GROSS, COST = ("GrossProfit",), ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfSales", "CostOfGoodsSold")
TOLERANCE = 0.005  # the parts' sum within 0.5% of the total: SEC amounts are exact to the filing's rounding
MAX_PARTS = 14
UNALLOCATED = "未分配（总部及调节项）"
SPECIAL = {"us-gaap:CorporateNonSegmentMember": "总部及其他", "us-gaap:IntersegmentEliminationMember": "分部间抵消",
           "us-gaap:ConsolidationEliminationsMember": "合并抵消", "us-gaap:SegmentReconcilingItemsMember": "调节项",
           "us-gaap:MaterialReconcilingItemsMember": "调节项"}
COLUMNS = ["period", "by", "item", "revenue", "share", "gross_margin", "op_income", "op_share", "op_margin"]


def parse_instance(raw: bytes) -> list[dict]:
    """Every numeric fact of an XBRL instance over a fiscal year (350-380 days): concept (local name), end date, its
    dimensions {axis: member}, unit, value."""
    root = ET.fromstring(raw)
    contexts = {}
    for c in root.iter(XBRLI + "context"):
        p = c.find(XBRLI + "period")
        start, end = p.findtext(XBRLI + "startDate"), p.findtext(XBRLI + "endDate")
        if start and end and 350 <= (date.fromisoformat(end) - date.fromisoformat(start)).days <= 380:
            if c.find(f".//{XDI}typedMember") is None:
                contexts[c.get("id")] = (end, {m.get("dimension"): (m.text or "").strip() for m in c.iter(XDI + "explicitMember")})
    units = {u.get("id"): (u.findtext(f"{XBRLI}measure") or "").split(":")[-1] for u in root.iter(XBRLI + "unit")}
    out, seen = [], set()
    for el in root:
        ctx = contexts.get(el.get("contextRef"))
        if ctx is None or el.get("unitRef") is None or not (el.text or "").strip():
            continue
        try:
            value = float(el.text)
        except ValueError:
            continue
        concept = el.tag.split("}")[-1]
        key = (concept, el.get("contextRef"))
        if key not in seen:
            seen.add(key)
            out.append({"concept": concept, "end": ctx[0], "dims": ctx[1], "unit": units.get(el.get("unitRef")), "value": value})
    return out


def parse_labels(meta: dict) -> dict[str, str]:
    """QName -> the filing's own short label for each element (terse label, else the standard one without
    [Member]), from SEC's MetaLinks.json (the same for filers whose labels sit in the schema: Microsoft's)."""
    out = {}
    for doc in (meta.get("instance") or {}).values():
        for tag, info in (doc.get("tag") or {}).items():
            role = ((info.get("lang") or {}).get("en-us") or {}).get("role") or {}
            text = role.get("terseLabel") or role.get("label")
            if text:
                out[tag.replace("_", ":", 1)] = re.sub(r"\s*\[Member\]$", "", text)
    return out


def partition(values: dict[str, float], total: float, offsets: set[str] = frozenset()) -> list[str] | None:
    """The most members (at least 2) whose values add up to the total within the tolerance: a breakdown's parts, not
    its subtotals (Amazon tags both product / service and its seven sales groups). A negative member counts only if
    it is an offsetting line (eliminations between segments, corporate), so a subtotal can't be netted back out."""
    parts = sorted((m for m, v in values.items() if v > 0 or (v < 0 and m in offsets)), key=lambda m: -abs(values[m]))[:MAX_PARTS]
    for k in range(len(parts), 1, -1):
        for combo in combinations(parts, k):
            if (sum(values[m] > 0 for m in combo) >= 2
                    and abs(sum(values[m] for m in combo) - total) <= TOLERANCE * abs(total)):
                return list(combo)
    return None


def members(facts: list[dict], kind: str) -> tuple[list[dict], set[str]]:
    """(concept, end) -> {member: value} for one breakdown, in two readings that can differ (Caterpillar: a segment
    with its sales to other segments under ASU 2023-07's operating-segments member, without them on its own): the
    operating-segments facts, then the plain ones. A segment table adds the lines tagged only on the consolidation
    axis (corporate, eliminations between segments: Procter & Gamble's, JD's), which some sums need; their names
    come back apart."""
    tagged, plain, extra = {}, {}, {}
    for f in facts:
        dims, key = dict(f["dims"]), (f["concept"], f["end"])
        ops = dims.pop(CONSOLIDATION, None) if dims.get(CONSOLIDATION) in OPERATING_SEGMENTS else None
        if len(dims) == 1 and (axis := next(iter(dims))) in AXES[kind]:
            (tagged if ops else plain).setdefault(key, {})[dims[axis]] = f["value"]
        elif kind == "segment" and ops is None and len(dims) == 1 and CONSOLIDATION in dims:
            extra.setdefault(key, {})[dims[CONSOLIDATION]] = f["value"]
    readings = [{k: v | extra.get(k, {}) for k, v in m.items()} for m in (tagged, plain) if m]
    return readings, {m for v in extra.values() for m in v}


def measure(get, parts: list[str], whole: float | None, required: list[str]) -> dict[str, float]:
    """Each part's figure, kept only when every required part has one and they add up to the company's total
    within the tolerance (segment cost tags can be partial: Disney's Experiences)."""
    got = {m: v for m in parts if (v := get(m)) is not None}
    if whole is None or any(m not in got for m in required) or abs(sum(got.values()) - whole) > TOLERANCE * abs(whole):
        return {}
    return got


def breakdowns(facts: list[dict], labels: dict[str, str]) -> pd.DataFrame:
    """The segment, product and region tables from an instance's facts, each year checked against the total, with
    the gross margin and (segments) operating profit where those add up too, and the operating profit no segment
    carries (corporate costs, reconciling items). The reporting currency is the one most revenue facts use (a
    Chinese 20-F adds the latest year in US dollars)."""
    units = [f["unit"] for f in facts if f["concept"] in REVENUE and not f["dims"]]
    facts = [f for f in facts if units and f["unit"] == max(set(units), key=units.count)]
    plain = {(f["concept"], f["end"]): f["value"] for f in facts if not f["dims"]}
    first = lambda names, end: next((plain[(n, end)] for n in names if (n, end) in plain), None)
    rows = []
    for kind in AXES:
        readings, extras = members(facts, kind)
        for end in sorted({f["end"] for f in facts}):
            best = None  # the most parts over the readings and revenue concepts; the total: the same concept's,
            for by in readings:  # else another's (Alphabet's parts are contract revenue, its total Revenues, hedging in)
                for c in REVENUE:
                    values = by.get((c, end))
                    for total in [plain[(n, end)] for n in (c,) + REVENUE if values and plain.get((n, end))]:
                        if (m := partition(values, total, extras | offsetting(values, labels))) and (
                                best is None or len(m) > len(best[3])):
                            best = (by, c, total, m)
                        if m:
                            break
            if best is None:
                continue
            by, c, total, parts = best
            value = {m: by[(c, end)][m] for m in parts}
            pick = lambda names, m: next((r[(n, end)][m] for r in [by] + readings for n in names if m in r.get((n, end), {})), None)
            cost = lambda m: None if (x := pick(COST, m)) is None else value[m] - x
            businesses = [m for m in parts if value[m] > 0 and m not in extras]
            whole_gross = first(GROSS, end)
            if whole_gross is None and (x := first(COST, end)) is not None:
                whole_gross = total - x
            gross = measure(lambda m: pick(GROSS, m) if pick(GROSS, m) is not None else cost(m), parts, whole_gross, businesses)
            op = {m: v for m in parts if kind == "segment" and (v := pick(OPERATING, m)) is not None}
            op = op if all(m in op for m in businesses) else {}
            # each segment's share of the segments' operating profit (before corporate costs), when none lost money
            business = sum(op[m] for m in businesses) if op and all(op[m] >= 0 for m in businesses) else 0
            group = []
            for m in parts:
                own = m not in extras  # margins only for a business, not for corporate lines or eliminations
                group.append({"period": end, "by": kind, "item": label(m, labels), "revenue": value[m], "share": value[m] / total,
                              "gross_margin": gross[m] / value[m] if own and m in gross and value[m] > 0 else None,
                              "op_income": op.get(m), "op_share": op[m] / business if m in businesses and business > 0 else None,
                              "op_margin": op[m] / value[m] if own and m in op and value[m] > 0 else None})
            group.sort(key=lambda r: (r["item"] in SPECIAL.values() or r["revenue"] < 0, -r["revenue"]))
            whole = first(OPERATING, end)
            if op and whole is not None and abs(rest := whole - sum(op.values())) > TOLERANCE * abs(whole):
                group.append({"period": end, "by": kind, "item": UNALLOCATED, "revenue": None, "share": None,
                              "gross_margin": None, "op_income": rest, "op_share": None, "op_margin": None})
            rows += group
    return pd.DataFrame(rows, columns=COLUMNS)


def offsetting(values: dict[str, float], labels: dict[str, str]) -> set[str]:
    """Members on the breakdown's own axis that offset the others by name (Disney's segment eliminations)."""
    return {m for m in values if re.search(r"(?i)eliminat|inter-?segment|reconcil|corporate|unallocated", f"{m} {labels.get(m, '')}")}


def label(qname: str, labels: dict[str, str]) -> str:
    """The filing's label (HTML entities undone, a trailing 'Segment' dropped), the standard consolidation lines in
    Chinese, else the member's name split into words."""
    if qname in SPECIAL:
        return SPECIAL[qname]
    text = labels.get(qname) or re.sub(r"(?<=[a-z])(?=[A-Z])", " ", qname.split(":")[-1].removesuffix("Member"))
    return re.sub(r"\s+[Ss]egment$", "", html.unescape(text))


def us(code: str, today: date) -> pd.DataFrame:
    """The latest annual report's breakdowns (its instance and labels read in memory, never stored)."""
    filing = filings.periodic("us", code, today, annual=True)
    if filing is None:
        return pd.DataFrame(columns=COLUMNS)
    http, base = filings.client("us"), filing["url"].rsplit("/", 1)[0]
    names = [x["name"] for x in http.get(base + "/index.json").json()["directory"]["item"]]
    instance = next((n for n in names if n.endswith("_htm.xml")), None) or next(
        (n for n in names if n.endswith(".xml") and not re.search(r"_(cal|def|lab|pre)\.xml$|FilingSummary", n)), None)
    if instance is None:
        return pd.DataFrame(columns=COLUMNS)
    labels = parse_labels(http.get(f"{base}/MetaLinks.json").json()) if "MetaLinks.json" in names else {}
    return breakdowns(parse_instance(http.get(f"{base}/{instance}").content), labels).assign(source=filing["title"])


# HK: the annual report's segment note (HKFRS 8), read from the PDF's layout text so that each column keeps its place.
NOTE = re.compile(r"(?i)segment information|operating segments|segment reporting|segmental information")
NUMBER = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?|[–—-](?=\s|$)")
REVENUE_ROWS = (r"revenues? from external customers|external (?:customer )?(?:revenues?|sales)|sales to external customers",
                r"(?:total |reportable )?segment (?:revenues?|turnover|sales)|revenues?|turnover|total revenues?")
PROFIT_ROWS = {"gross": r"(?:segment )?gross profit",
               "op": r"(?:reportable )?segment (?:results?|profit|operating profit|operating results?)|operating profit"
                     r"|profit from operations|results?(?=\s{2})"}
LEAD = r"\s*(?:[–—•-]\s*)?"  # a row label's indent and bullet (Anta's "– Revenue from external customers")
UNITS = re.compile(r"(?i)^(?:RMB|HK\$|US\$|S\$|MOP\$?|NT\$|\$)?\s*['’]?\s*(?:000|m|mn|million|billion)?$|^%$")
SCALES = (1.0, 1e3, 1e6, 1e9)


def amount(token: str) -> float:
    if token in "–—-":
        return 0.0
    value = float(token.strip("()").replace(",", ""))
    return -value if token.startswith("(") else value


def amounts(line: str, start: int = 0) -> list[tuple[float, int, int]]:
    return [(amount(x.group()), x.start(), x.end()) for x in NUMBER.finditer(line, start)]


def revenue_row(lines: list[str], i: int) -> list[tuple[float, int, int]] | None:
    """The amounts of a revenue row starting at line i, also when its label wraps and the amounts sit on the next
    line after the label's last words (Galaxy's "Revenue recognised under HKFRS Accounting / Standards")."""
    for label in REVENUE_ROWS:
        if m := re.match(rf"(?i){LEAD}(?:{label})\b[^\d(–—-]*", lines[i]):
            got = amounts(lines[i], m.end())
            if not got and i + 1 < len(lines) and (n := re.match(r"\s*[A-Za-z][A-Za-z ,&'’-]*?(?=\s{2,}|$)", lines[i + 1])):
                got = amounts(lines[i + 1], n.end())
            return got if len(got) >= 3 else None
    return None


def header(lines: list[str], at: int, row: list[tuple[float, int, int]]) -> tuple[list[str], int | None]:
    """The column names above a row and the fiscal year named above it ("Year ended 31 December 2025", or a bare
    year over the columns). The header's cells inside the amounts' area are grouped where they overlap (a name
    wrapped over lines), and only as many groups as columns name the columns, in order (Anta's names sit to the
    right of its amounts); any other header (MTR's column groups over sub-columns) gives no names, so the table is
    left out rather than a figure put under the wrong name. The table's other rows above (HKEX's revenue-recognition
    lines) are passed over; the header ends at the first line above it with text only left of the amounts."""
    ends = [e for _, _, e in row]
    reach = min((b - a for a, b in zip(ends, ends[1:])), default=20) / 2
    left, cells, year = row[0][1] - reach, [], None
    for n, line in enumerate(reversed(lines[max(0, at - 25):at])):
        if y := re.search(r"(?i)(?:year|period)s? ended.*?((?:19|20)\d\d)", line):
            year = year or int(y.group(1))
            continue
        found = [(c.group(), c.start(), c.end(), -n) for c in re.finditer(r"\S+(?: \S+)*", line) if c.start() >= left]
        found = [c for c in found if not UNITS.match(c[0])]
        if len(amounts(line)) >= len(ends) - 1 or not line.strip() or not found:
            if cells and line.strip():
                break  # a row of the table above the header, or text left of the amounts
            continue
        for c in found:
            if re.fullmatch(r"(?:19|20)\d\d", c[0]):
                year = year or int(c[0])
            else:
                cells.append(c)
    groups = []
    for c in sorted(cells, key=lambda c: c[1]):
        if groups and c[1] <= max(x[2] for x in groups[-1]):
            groups[-1].append(c)
        else:
            groups.append([c])
    if len(groups) != len(ends):
        return [""] * len(ends), year
    names = [" ".join(t for t, *_ in sorted(g, key=lambda c: (c[3], c[1]))) for g in groups]
    return [re.sub(r"\s*(?:[*#†]+|\(\d\)|\(note \d+\))$", "", n, flags=re.I) for n in names], year  # footnote marks


def page_tables(text: str) -> list[dict]:
    """Segment tables on one page: {year, names, revenue, gross, op}, the last column the total of the others,
    at least two of them positive."""
    lines, out = text.splitlines(), []
    for i in range(len(lines)):
        got = revenue_row(lines, i)
        if not got:
            continue
        values = [v for v, _, _ in got]
        names, year = header(lines, i, got)
        if (not all(names[:-1]) or sum(v > 0 for v in values[:-1]) < 2
                or abs(sum(values[:-1]) - values[-1]) > TOLERANCE * abs(values[-1])):
            continue
        table = {"year": year, "names": names, "revenue": values}
        for j in range(i + 1, min(i + 30, len(lines))):
            if j > i + 2 and (r := revenue_row(lines, j)) and len(r) == len(got):
                break  # the next table
            for key, label in PROFIT_ROWS.items():  # a row of the same table: its columns add up to its total
                m = re.match(rf"(?i){LEAD}(?:{label})\b[^\d(–—-]*", lines[j])
                if key not in table and m and len(r := amounts(lines[j], m.end())) == len(got):
                    row_ = [v for v, _, _ in r]
                    if abs(sum(row_[:-1]) - row_[-1]) <= TOLERANCE * abs(row_[-1]) + 1:
                        table[key] = row_
        out.append(table)
    return out


def note_page(text: str) -> bool:
    """A page that names the segment note and has a line starting with a revenue row's label (the row parser's own
    labels: Meituan's "Total revenues" was passed over by a shorter list)."""
    return bool(NOTE.search(text) and re.search(rf"(?im)^{LEAD}(?:{'|'.join(REVENUE_ROWS)})\b", text))


def report_tables(pdf: bytes) -> list[dict]:
    """The segment tables of an annual report, from the pages note_page picks."""
    from pypdf import PdfReader
    out = []
    for page in PdfReader(io.BytesIO(pdf)).pages:
        if note_page(page.extract_text() or ""):
            out += page_tables(page.extract_text(extraction_mode="layout"))
    return out


def from_report(tables: list[dict], revenue: dict[int, tuple[str, float]], source: str) -> pd.DataFrame:
    """Rows from the tables whose total is the statements' revenue of a fiscal year (within 2%, at the scale of
    the table's units: Eastmoney's Techtronic 2024 is 1.5% below the report's), per year the table with the most
    measures; segments only, columns of zero dropped, and no unallocated line (the statements' operating profit
    is defined apart from the segments' results)."""
    best = {}
    for t in tables:
        for y in ([t["year"]] if t["year"] in revenue else sorted(revenue, reverse=True)):
            scale = next((s for s in SCALES if abs(t["revenue"][-1] * s - revenue[y][1]) <= 0.02 * abs(revenue[y][1])), None)
            if scale is not None:
                if y not in best or len(t) > len(best[y][0]):
                    best[y] = (t, scale)
                break
    rows = []
    for y, (t, scale) in sorted(best.items(), reverse=True):
        total = t["revenue"][-1] * scale
        ops = [v for v, r in zip(t.get("op", [])[:-1], t["revenue"]) if r > 0]
        business = sum(ops) * scale if ops and min(ops) >= 0 else 0
        for k, name in enumerate(t["names"][:-1]):
            v = t["revenue"][k] * scale
            gross, op = (t[key][k] * scale if key in t else None for key in ("gross", "op"))
            if v or gross or op:
                rows.append({"period": revenue[y][0], "by": "segment", "item": name, "revenue": v, "share": v / total,
                             "gross_margin": gross / v if gross is not None and v > 0 else None,
                             "op_income": op, "op_share": op / business if op is not None and v > 0 and business > 0 else None,
                             "op_margin": op / v if op is not None and v > 0 else None})
    return pd.DataFrame(rows, columns=COLUMNS).assign(source=source)


def hk(code: str, today: date, statements: pd.DataFrame) -> pd.DataFrame:
    """An HK issuer's segments: its A line's 主营构成 (the same accounts), else its own SEC filing (Alibaba, JD),
    else its annual report's segment note."""
    lines = listings.issuer("hk", code)
    for a in lines.query("market == 'cn'")["code"]:
        if len(found := cn.segments(a)):
            return found.assign(source=f"A 股 {a} 主营构成")
    for u in lines.query("market == 'us'")["code"]:
        if len(found := us(u, today)):
            return found
    filing = filings.periodic("hk", code, today, annual=True)
    if filing is None:
        return pd.DataFrame(columns=COLUMNS)
    years = statements[statements["months"] == 12]
    revenue = {int(p[:4]): (p, float(r)) for p, r in zip(years["period"], years["revenue"]) if pd.notna(r) and r}
    pdf = filings.client("hk").get(filing["url"]).content  # read in memory, never stored
    return from_report(report_tables(pdf), revenue, filing["title"])
