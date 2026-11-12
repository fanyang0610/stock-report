"""The fact sheet (`research CODE --facts`): every figure the report's words may cite, computed by code under a key and
saved as data/research/<market>/<code>/facts.json. Gathers the market's per-stock tables (cached: statements and
consensus weekly, prices, quotes and flows daily), Damodaran's industry, the issuer's other listings, then the
history, valuation, accounting checks, the skills' tests, peers, the screening's view and the two-source check."""

import logging
import math
import re
from datetime import date

import pandas as pd

from stockreport.fetch import filings, yahoo
from stockreport.research import (STATEMENT, cached, checks, cn, damodaran, days, folder, fresh, hk, listings, load,
                                  save, sheet, sources, stamp, us)

log = logging.getLogger(__name__)
QUOTE = {"cn": "CNY", "hk": "HKD", "us": "USD"}
KINDS = {"银行": "bank", "保险": "insurer", "证券": "broker"}
ROLE = r"董事|总经理|總經理|总裁|總裁|行政總裁|主席|董事会秘书|財務總監|财务总监|首席"
MANAGEMENT = (rf"(辞职|辞任|辭任|辭職|聘任|委任|选举|選舉|变更|變更|更換|更换).{{0,12}}({ROLE})|({ROLE}).{{0,8}}(辞职|辞任|辭任|辭職|"
              r"变更|變更)|Director or officer change")
AUDITOR = r"(变更|更换|改聘|更換|辞任|辭任|辞职).{0,8}(会计师事务所|會計師事務所|核數師|审计机构)|(核數師|会计师事务所).{0,4}(变更|更換|辭任)|Auditor change"


def market_of(code: str) -> str:
    return "cn" if re.fullmatch(r"\d{6}", code) else "hk" if re.fullmatch(r"\d{1,5}", code) else "us"


def normal(market: str, code: str) -> str:
    return code.zfill(5) if market == "hk" else code.upper()


def prices(f, market: str, code: str, today: date) -> dict:
    names = ("daily", "dividends", "monthly", "splits")
    if not all(fresh(f / f"{n}.csv.gz", days("daily")) for n in names):
        try:
            got = sources.prices(market, code, today)
            for n in names:
                save(f / f"{n}.csv.gz", got[n] if got[n] is not None else pd.DataFrame())
        except Exception as e:
            if not (f / "daily.csv.gz").exists():
                raise
            log.warning("%s prices: %s (stale cache used)", code, e)
    return {n: load(f / f"{n}.csv.gz") for n in names}


def gather(market: str, code: str, today: date) -> dict:
    f, S, D = folder(market, code), days("statements"), days("daily")
    g = {"street": cached(f / "street.json", D, lambda: sources.summary(market, code, today)),
         "tencent": cached(f / "tencent.json", D, lambda: sources.tencent(market, code)),
         "prices": prices(f, market, code, today), "single": False}
    g["second"] = cached(f / "second.csv.gz", S, lambda: sources.annual(market, code))
    if market == "cn":
        g["statements"] = cached(f / "statements.csv.gz", S, lambda: cn.statements(code))
        g["segments"] = cached(f / "segments.csv.gz", S, lambda: cn.segments(code))
        g["consensus"] = cached(f / "consensus.json", S, lambda: cn.consensus(code, today))
        g["valuation"] = cached(f / "valuation.csv.gz", D, lambda: cn.valuation(code))
        g["flows"] = cached(f / "flows.json", D, lambda: cn.flows(code, today))
    elif market == "us":
        if not (fresh(f / "statements.csv.gz", S) and fresh(f / "latest.json", S)):
            payload = us.companyfacts(code)  # several MB, parsed in memory and not kept
            save(f / "statements.csv.gz", us.parse_statements(code, payload))
            save(f / "latest.json", us.latest(code, payload, today))
        g["statements"], g["latest"] = load(f / "statements.csv.gz"), load(f / "latest.json")
        g["consensus"] = cached(f / "consensus.json", S, lambda: us.consensus(code))
        g["flows"] = cached(f / "flows.json", D, lambda: us.flows(code))
    else:
        currency = g["street"].get("report_currency") or "HKD"
        st = cached(f / "statements.csv.gz", S, lambda: hk.statements(code, currency))
        if st.empty:  # no Eastmoney statements (REITs): Yahoo's annual series is the only source
            st, g["single"] = g["second"].reindex(columns=STATEMENT), True
        g["statements"], g["consensus"], g["flows"] = st, None, {}
        a_line = listings.issuer(market, code).query("market == 'cn'")
        if len(a_line):  # an A+H issuer's dividends as declared, per fiscal year, from its A line's 分红
            g["a_dividends"] = cached(f / "a_dividends.json", S, lambda: cn.dividends(a_line["code"].iloc[0]))
    g["filings"] = cached(f / "filings.json", S, lambda: filings.recent(market, code, today, 365, routine=True) or [])
    return g


def kind_of(market: str, st: pd.DataFrame, industry: str, listing_kind: str | None) -> str:
    if listing_kind == "reit" or "REIT" in industry or "R.E.I.T" in industry:
        return "reit"
    if market == "cn" and st["org_type"].iloc[-1] in KINDS:
        return KINDS[st["org_type"].iloc[-1]]
    return ("bank" if industry.startswith("Bank") else "insurer" if industry.startswith("Insurance")
            else "broker" if industry.startswith("Brokerage") else "general")


def consensus(market: str, g: dict, last_fy: int) -> dict:
    """EPS by fiscal year from the market's consensus source, Yahoo's beside it, and the street's targets and ratings."""
    street, c = g["street"], g["consensus"] or {}
    yahoo_eps = sources.eps_years(street.get("estimates") or {})
    eps = {y: v for y, v in (c.get("eps") or yahoo_eps).items() if int(y) > last_fy and v is not None}
    main = c if c else street  # HK: Yahoo is the consensus source; CN and US: Eastmoney and Nasdaq, Yahoo beside them
    out = {"source": c.get("source", "Yahoo"), "eps": eps, "currency": "CNY" if market == "cn" else
           street.get("est_currency") if market == "hk" else "USD", "analysts": main.get("analysts"),
           "eps_yahoo": {y: v for y, v in yahoo_eps.items() if int(y) > last_fy}, "ratings": main.get("ratings"),
           "target_mean": main.get("target_mean"), "target_high": main.get("target_high"), "target_low": main.get("target_low"),
           "target_yahoo": street.get("target_mean"), "target_yahoo_range": [street.get("target_low"), street.get("target_high")],
           "ratings_yahoo": street.get("ratings"), "upgrades_6m": street.get("upgrades_6m"),
           "downgrades_6m": street.get("downgrades_6m"), "surprises": street.get("surprises"),
           "next_earnings": street.get("next_earnings")}
    est = street.get("estimates") or {}
    e0, e1 = est.get("0y") or {}, est.get("+1y") or {}
    if e0.get("end"):  # Yahoo's revenue and EPS range by fiscal year; revenue only when +1y's end differs from 0y's
        year, same = int(e0["end"][:4]), e1.get("end") == e0.get("end")  # (Yahoo repeats 0y's end for AAPL)
        out["yahoo_years"] = {str(y): {"revenue": None if same else e.get("revenue"), "eps_low": e.get("eps_low"),
                                       "eps_high": e.get("eps_high")} for y, e in ((year, e0), (year + 1, e1)) if e}
    y0 = min(set(eps) & set(out["eps_yahoo"]), default=None)
    out["basis"] = BASIS.get(out["source"])
    out["basis_gap_yahoo"] = abs(eps[y0] - out["eps_yahoo"][y0]) / abs(out["eps_yahoo"][y0]) if y0 and out["eps_yahoo"][y0] else None
    if market == "cn":
        out["reports"] = c.get("reports", [])
    return out


BASIS = {"Eastmoney 研报一致预期": "reported profit to shareholders per share (归母)", "Nasdaq": "Nasdaq's (Zacks) consensus",
         "Yahoo": "Yahoo's consensus, often adjusted (non-GAAP) for US companies"}  # SNOW FY2027: Nasdaq -1.42, Yahoo +2.22


REIT_NOTE = "REIT: the street's per-share forecast is FFO (the industry's convention), not GAAP EPS; P/E on it isn't GAAP P/E"


def dividends(market: str, g: dict, last_fy: str, today: date, quote: str, report: str) -> dict[str, float]:
    """Dividends per share by year in the reporting currency, complete years only: CN (and an A+H issuer's H line, from
    its A line) by the fiscal year they are paid for (分红's report period, up to the last reported year), on today's
    share basis; else Yahoo's by the calendar year they went ex (before this year), each at its ex-date's rate."""
    if market == "cn" or g.get("a_dividends"):  # undone for the bonus shares (送转) issued after each
        source = g["flows"].get("dividends") if market == "cn" else g["a_dividends"]
        out, rows = {}, sorted((d for d in source or [] if d.get("progress") == "实施分配" and d["ex_date"]),
                               key=lambda d: d["ex_date"])
        for i, d in enumerate(rows):
            later = math.prod(1 + (x["bonus"] or 0) for x in rows[i + 1:]) * (1 + (d["bonus"] or 0) if d["dps"] else 1)
            if d["period"] and d["dps"] and d["period"][:4] <= last_fy:
                out[d["period"][:4]] = out.get(d["period"][:4], 0) + d["dps"] / later
        return out
    divs = g["prices"]["dividends"]
    if not len(divs):
        return {}
    if quote != report:
        rate = yahoo.cny_per(pd.Series(quote, index=divs.index), divs["ex_date"]) / \
            yahoo.cny_per(pd.Series(report, index=divs.index), divs["ex_date"])
        fx = yahoo.load_fx()
        divs = divs.assign(dps=divs["dps"] * rate.fillna(fx.get(report, math.nan) / fx.get(quote, math.nan)))
    return {y: v for y, v in sources.dividend_years(divs).items() if y < str(today.year)}


def build(market: str, code: str, today: date | None = None) -> dict:
    today, code = today or date.today(), normal(market, code)
    g = gather(market, code, today)
    st = g["statements"].sort_values("period").reset_index(drop=True)
    a = st[st["months"] == 12].tail(11).reset_index(drop=True)
    if a.empty:
        raise RuntimeError(f"{code}: no annual statements")
    try:
        damodaran.update(today)
        dam = damodaran.industry_of(market, code)
        for _, o in listings.issuer(market, code).iterrows():  # an A+H issuer may be classified under its other line
            dam = dam or damodaran.industry_of(o["market"], o["code"])
    except Exception as e:
        log.warning("damodaran: %s", e)
        dam = {}
    lst = listings.issuer(market, code)
    me = lst[(lst["market"] == market) & (lst["code"] == code)]
    kind = kind_of(market, st, dam.get("industry", ""), me["kind"].iloc[0] if len(me) else None)
    street, report_cur = g["street"], a["currency"].dropna().iloc[-1] if a["currency"].notna().any() else QUOTE[market]
    quote_cur = street.get("currency") or QUOTE[market]
    fx = yahoo.load_fx()
    rate = float(fx.get(report_cur, math.nan) / fx.get(quote_cur, math.nan)) if report_cur != quote_cur else 1.0
    daily = g["prices"]["daily"]
    px = sources.price_facts(daily, code, sources.INDEX[market][1])
    dps = dividends(market, g, a.iloc[-1]["period"][:4], today, quote_cur, report_cur)
    shares = st.dropna(subset=["shares"])["shares"].iloc[-1]
    if market == "us" and g["latest"].get("shares"):  # the latest filing's cover count
        shares = g["latest"]["shares"]
    if market == "hk" and "issued" in st and st["issued"].notna().any():  # issued, not the period's weighted average
        shares = st["issued"].dropna().iloc[-1]
    price, val_cn = px["close"], g.get("valuation")
    if market == "cn" and val_cn is not None and len(val_cn):
        price, shares = float(val_cn.iloc[-1]["close"]), float(val_cn.iloc[-1]["shares"])
    # every year's share count on today's basis, so dilution, payouts and per-share history aren't split or bonus effects
    if market == "cn":
        bonuses = [(d["ex_date"], d["bonus"]) for d in g["flows"].get("dividends") or [] if d["bonus"] and d["ex_date"]]
        a["shares"] = sheet.cn_shares(a, st.dropna(subset=["share_capital"]).iloc[-1], shares, bonuses).values
        a["div_paid"] = a["period"].str[:4].map(dps) * a["shares"]  # the cash flow lumps interest paid in
    else:
        a["shares"] = sheet.split_basis(a, g["prices"]["splits"]).values
    fin = kind in checks.FINANCIAL  # banks', insurers' and brokers' debt, cash and operating cash flow are their business
    check, a = sheet.crosscheck(a, None if g["single"] else g["second"], fin)  # a figure > 5% off is left out
    mcap = price * shares
    t12 = ({"revenue": g["latest"].get("revenue"), "ni": g["latest"].get("ni"), "ocf": g["latest"].get("ocf")} if market == "us"
           else {k: sheet.ttm(st, k) for k in ("revenue", "ni", "ocf")})
    for k in ("capex", "pretax", "interest", "da"):
        t12[k] = sheet.ttm(st, k) if market != "us" else g["latest"].get(k)
    bal = st.iloc[-1].copy()  # the latest balance sheet (US: the latest 10-Q's equity on the last 10-K's layout)
    if market == "us" and g["latest"].get("equity"):
        bal["equity"] = g["latest"]["equity"]
    ev = None if fin else mcap * rate + (checks.val(bal, "debt") or 0) - (checks.val(bal, "cash") or 0) + (checks.val(bal, "minority") or 0)
    ebit = None if t12["pretax"] is None else t12["pretax"] + (t12["interest"] or 0)
    common = None if checks.val(bal, "equity") is None else checks.val(bal, "equity") - (checks.val(bal, "pref") or 0)
    cons = consensus(market, g, int(a.iloc[-1]["period"][:4]))
    eps_years = sorted(cons["eps"])
    est_rate = float(fx.get(quote_cur, math.nan) / fx.get(cons["currency"], math.nan)) if cons["currency"] not in (None, quote_cur) else 1.0
    next_eps = cons["eps"][eps_years[0]] * est_rate if eps_years else None
    pe_fwd = checks.div(price, next_eps) if next_eps and next_eps > 0 else None  # a forecast loss: no forward P/E
    g_eps = checks.cagr(cons["eps"][eps_years[-1]], cons["eps"][eps_years[0]], len(eps_years) - 1) if len(eps_years) > 1 else None
    year_ago = (pd.Timestamp(today) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    if market == "cn":
        dps_12m = sum(d["dps"] for d in g["flows"].get("dividends") or [] if d["ex_date"] and d["ex_date"] > year_ago)
    else:
        divs = g["prices"]["dividends"]
        dps_12m = float(divs.loc[divs["ex_date"] > year_ago, "dps"].sum()) if len(divs) else 0.0
    balance = {k: None if fin and k in ("debt", "cash") else checks.val(bal, k) for k in ("debt", "cash", "minority")}
    valuation = {"price": price, "quote_currency": quote_cur, "report_currency": report_cur, "fx_quote_to_report": rate,
                 "balance": balance | {"period": bal["period"]},
                 "shares": shares, "market_cap": mcap, "market_cap_report": mcap * rate, "ev": ev, "ttm": t12,
                 "pe_ttm": checks.div(mcap * rate, t12["ni"]) if (t12["ni"] or 0) > 0 else None,
                 "book_common": common, "pb": checks.div(mcap * rate, common), "ps": checks.div(mcap * rate, t12["revenue"]),
                 "ev_ebit": checks.div(ev, ebit) if (ebit or 0) > 0 and ev is not None else None,
                 "fcf_yield": checks.div(t12["ocf"] - t12["capex"], mcap * rate) if None not in (t12["ocf"], t12["capex"]) and not fin else None,
                 "div_yield": checks.div(dps_12m, price), "dps_12m": dps_12m, "pe_fwd": pe_fwd, "eps_growth_consensus": g_eps,
                 "peg": checks.div(pe_fwd, g_eps * 100) if g_eps and g_eps > 0 and pe_fwd else None,
                 "pe_digest_years": (0.0 if pe_fwd and pe_fwd <= 30 else math.log(pe_fwd / 30) / math.log(1 + g_eps)
                                     if pe_fwd and g_eps and g_eps > 0 else None)}  # a-stock-data: years to 30x
    if market != "us" and check.get("left_out"):
        valuation["ttm_note"] = ("the latest fiscal year's figures more than 5% off the annual report's are left out "
                                 "(Eastmoney's restated comparatives); trailing figures may mix restated quarters with the year as filed")
    if market == "cn" and val_cn is not None:
        own = val_cn.assign(month=val_cn["date"].str[:7])
    else:
        own = sheet.own_multiples(g["prices"]["monthly"], a, quote_cur, report_cur, g["prices"]["splits"])  # a: today's basis
    own = own.tail(120)
    valuation["own_history"] = {k: sheet.stats(own[k], valuation[{"pe": "pe_ttm", "pb": "pb", "ps": "ps"}[k]]) for k in ("pe", "pb", "ps")}
    valuation["own_series"] = {"month": list(own["month"]), "pe": list(own["pe"]), "pb": list(own["pb"])}  # the report's band chart
    monthly = g["prices"]["monthly"]
    listed = monthly["listed"].iloc[0] if len(monthly) and "listed" in monthly else None
    listed_years = (today - date.fromisoformat(listed)).days / 365.25 if listed else None
    yields = {}
    if len(monthly):  # each year's dividends over its average price, both in the quote currency
        avg_px = monthly.groupby(monthly["month"].str[:4])["close"].mean()
        quoted = dps if market == "cn" else sources.dividend_years(g["prices"]["dividends"]) if len(g["prices"]["dividends"]) else {}
        yields = {y: quoted[y] / avg_px[y] for y in sorted(quoted) if y in avg_px and avg_px[y] > 0 and y < str(today.year)}
    acct = {"beneish": None if fin else checks.beneish(a), "piotroski": None if fin else checks.piotroski(a),
            "altman": None if fin else checks.altman(a, mcap * rate), "accruals": checks.accruals(a),
            "quality_screen": checks.quality_screen(a, kind, listed_years), "checklist": checks.checklist(a, kind),
            "income": checks.income(a, dps, price * rate, yields),
            "era_alpha": checks.era_alpha(a, sheet.quarters(st) if market != "us" else None),
            "earnings_signals": checks.earnings_signals(a)}
    if kind == "reit":  # its profit carries property revaluations: no payout on it (FFO isn't free)
        acct["income"]["payout"] = None
    if market == "cn":
        acct["cn_flags"] = checks.cn_flags(a, g["flows"])
    snap = sheet.snapshot(market, today)
    industry = (val_cn.iloc[-1]["industry"] if market == "cn" and val_cn is not None else
                snap.loc[snap["code"] == code, "industry"].iloc[0] if len(snap) and (snap["code"] == code).any() else street.get("industry"))
    titles = g["filings"] or []
    others = []  # the issuer's other listings (A+H): price and this listing's premium over it in one currency; none
    for _, o in lst[(lst["market"] != market) | (lst["code"] != code)].iterrows():  # with a US line (an ADR's ratio
        q = sources.tencent(o["market"], o["code"])                                 # or a share class isn't 1:1)
        per = float(fx.get(quote_cur, math.nan) / fx.get(QUOTE[o["market"]], math.nan))
        others.append({"market": o["market"], "code": o["code"], "price": q.get("price"), "currency": QUOTE[o["market"]],
                       "premium": price / (q["price"] * per) - 1 if q.get("price") and "us" not in (market, o["market"]) else None})
    facts = {
        "code": code, "market": market, "built": stamp(), "kind": kind, "listed": listed,
        "name": (me["name"].iloc[0] if len(me) and pd.notna(me["name"].iloc[0]) else None) or (me["name_en"].iloc[0] if len(me) else code),
        "listings": lst.replace({float("nan"): None}).to_dict("records"), "other_listings": others, "industry": industry,
        "damodaran": dam, "business": street.get("business"), "employees": street.get("employees"),
        "price": px, "valuation": valuation, "summary": sheet.summary(a, kind), "history": sheet.history(a, dps, kind),
        "latest": g["latest"] if market == "us" else sheet.latest_vs_prior(st),
        "audit_opinion": a.iloc[-1].get("opinion") if "opinion" in a else None,
        "checks": acct, "consensus": cons | ({"note": REIT_NOTE} if kind == "reit" else {}), "flows": g["flows"], "street": {k: street.get(k) for k in (
            "beta", "short_float", "short_ratio", "insiders", "institutions", "insider_buys_6m", "insider_sells_6m",
            "insider_net_shares_6m", "target_moves_6m", "ex_dividend")},
        "segments": g["segments"].replace({float("nan"): None}).to_dict("records") if market == "cn" and len(g["segments"]) else [],
        "peers": sheet.peers(snap, code, industry, mcap), "industry_history": sheet.industry_history(industry) if market == "cn" and industry else [],
        "screening": sheet.screening(market, code, snap, today, listed, kind),
        "filings_12m": {"count": len(titles), "management": [t for t in titles if re.search(MANAGEMENT, t["title"])][:10],
                        "auditor": [t for t in titles if re.search(AUDITOR, t["title"])][:5]},
        "crosscheck": {"single_source": g["single"]} | check | sheet.quote_check({"price": price, "mcap": mcap}, g["tencent"]),
        "as_of": {p.name: date.fromtimestamp(p.stat().st_mtime).isoformat() for p in folder(market, code).iterdir()
                  if p.name != "facts.json"}}  # each input's date: a failed refresh keeps an older cache
    save(folder(market, code) / "facts.json", facts)
    return facts


def pct(x) -> str:
    return "-" if x is None else f"{x:.1%}"


def show(f: dict) -> str:
    """A short console view of the fact sheet (the full sheet is the JSON)."""
    v, s, c, sc = f["valuation"], f["summary"], f["checks"], f["screening"]
    x = lambda d, k, fmt="{:.2f}": "-" if (d or {}).get(k) is None else fmt.format(d[k])
    lines = [f"{f['name']} {f['code']} ({f['market'].upper()}, {f['kind']}; {f['industry']}; Damodaran: {f['damodaran'].get('industry', '-')})",
             f"price {v['price']:.2f} {v['quote_currency']}  value {v['market_cap'] / 1e9:,.1f}bn  P/E {x(v, 'pe_ttm', '{:.1f}')}"
             f"  fwd P/E {x(v, 'pe_fwd', '{:.1f}')}  P/B {x(v, 'pb')}  P/S {x(v, 'ps')}  EV/EBIT {x(v, 'ev_ebit', '{:.1f}')}"
             f"  yield {pct(v['div_yield'])}  FCF yield {pct(v['fcf_yield'])}",
             f"{s['years']} years to {s['fy_latest']}: revenue CAGR 5y {pct(s.get('rev_cagr_5y'))}, profit {pct(s.get('ni_cagr_5y'))};"
             f" ROE 5y {pct(s['roe_avg_5y'])}; gross margin {pct(s['gross_margin_avg_5y'])}; net {pct(s['net_margin_avg_5y'])};"
             f" OCF/profit {x(s, 'ocf_to_profit_5y')}; net debt/EBITDA {x(s, 'net_debt_to_ebitda')}"]
    if c["beneish"]:
        lines.append(f"Beneish M {x(c['beneish'], 'm_score')}  Piotroski F {c['piotroski'].get('f_score')}"
                     f"/{c['piotroski'].get('signals_known')}  Altman Z'' {x(c['altman'], 'z2')} ({c['altman'].get('z2_zone', '-')})"
                     f"  accruals {pct(c['accruals']['accruals'])}")
    q = c["quality_screen"]
    lines.append(f"quality-screen: {q['result']} {q['failed'] or ''}; checklist {c['checklist']['stars']} stars;"
                 f" dividends raised {c['income']['raises']} / cut {c['income']['cuts']}")
    cs = f["consensus"]
    lines.append(f"consensus EPS {cs['eps']} ({cs['source']}, {cs['analysts']} analysts); target {cs['target_mean']}"
                 f" [{cs['target_low']}-{cs['target_high']}]")
    lines.append("screening: " + (f"{sc.get('rating', sc.get('fifth'))} (score rank {sc.get('score_rank')} of {sc.get('universe')};"
                                  f" value {sc.get('g_value')} quality {sc.get('g_quality')} growth {sc.get('g_growth')}"
                                  f" momentum {sc.get('g_momentum')})" if sc.get("in_universe") else sc["reason"]))
    cc = f["crosscheck"]
    lines.append("second source: " + ("single source; " if cc["single_source"] else "") + ", ".join(
        f"{k} {d['status']}" + (f" {d['gap']:.1%}" if d.get("gap") is not None and d["status"] != "agree" else "")
        for k, d in cc.items() if isinstance(d, dict)))
    for o in f["other_listings"]:
        lines.append(f"other listing {o['market'].upper()} {o['code']}: {o['price']} {o['currency']}, this one's premium {pct(o['premium'])}")
    return "\n".join(lines)
