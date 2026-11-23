"""Research stage 10, part 1: the company's type (its playbook), the discount rates, the forecast paths and each
valuation method's value per share, from the fact sheet and Damodaran's data (PLAN.md "The method"). rating.py weighs
them into the target, the scenarios and the rating. Every choice below is a published default, cited where it is made:
- Rates are in the reporting currency (the cash flows' currency, so r and g are in one currency): its government's
  10-year yield (ChinaBond, US Treasury, HK government bond, the OECD's series for the currencies FRED carries; a
  currency with none: the US yield, said).
- Cost of equity (stage 15): the reporting currency's yield plus the listing market's implied premium (research/
  market.py: the return at which the market's members are worth their price under this model's own cash-flow rules,
  less the yield) plus Damodaran's country risk premium for the company's country (his company list) over the listing
  market's, at a beta of 1: the stock's implied return is set against its market's (beta doesn't sort returns, Fama
  and French 1992, Frazzini and Pedersen 2014; implied costs of capital track expected returns best in the time
  series and characteristic proxies best in the cross-section, Lee, So and Wang 2021, so the rating's cross-sectional
  use is the weaker one, and page 1 says when the price has run ahead of the forecasts: judge.lag). The
  benchmark's expected return is the listing market's premium over the reporting currency's yield (the currency the
  target grows in). The absolute view keeps the pre-stage-15 rates: CAPM with Damodaran's published premium and his
  industry's unlevered beta corrected for cash (the US table for US companies, the global table for the rest; his
  China-region averages give the whole market a beta of 1.75), relevered at the company's market debt to equity with
  the statutory tax rate; banks, insurers and brokers the industry's levered beta (debt is their raw material).
- Debt cost: the yield plus the default spread of the synthetic rating from interest cover (his large-firm table above
  USD 5bn of market value, else the smaller-firm one).
- Stable period (the simple Ginzu's defaults, stage 14's three stages): the cost of capital at a beta of 1 (yield +
  the premium, its country risk kept: the market's aggregate is valued the same way); growth at the yield (Damodaran's cap), lower only where the terminal value
  fails the sensitivity test (dcf.tested_growth); the return on new capital above its cost for the years a graded
  moat gives (moat: how long and how far the return beat its cost, the market's measured fade, at most Morningstar's
  15-year stage II), then equal to it."""

import math
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

from stockreport.config import DATA
from stockreport.fetch import yahoo
from stockreport.research import damodaran, dcf, fade, sheet
from stockreport.research.checks import FINANCIAL

RATE_OF = {"CNY": "cn", "USD": "us", "HKD": "hk"}
COUNTRY = {"cn": "China", "hk": "Hong Kong", "us": "United States"}
MARGINAL_TAX = {"China": 0.25, "Hong Kong": 0.165, "United States": 0.25}  # CN EIT, HK profits tax, US federal + state
LARGE_USD = 5e9  # Damodaran's cut between his large-firm and smaller-firm rating tables
FAST = 0.20  # Lynch's fast growers grow 20-25% a year ("One Up on Wall Street", 1989)
MOAT_YEARS = 5  # the plan's minimum for a company's own history (as for its margin)
STAGE2 = 15  # Morningstar's longest stage II (excess returns fading to the cost of capital): 10-15 years for a wide moat
CONVERGENCE = 5  # the simple Ginzu's default year of margin convergence
CYCLICAL_SECTORS = {"Materials", "Energy"}  # with these industries: the plan's materials, energy, chemicals, shipping, memory
CYCLICAL_INDUSTRIES = {"Semiconductor", "Semiconductor Equip", "Shipbuilding & Marine", "Transportation"}
DDM_FIT = (0.8, 1.1)  # dividends 80-110% of FCFE over 5 years: the dividend model, else the FCFE model (Damodaran)
PRE_REVENUE = re.compile(r"-[A-Z]*[UB][A-Z]*$")  # HKEX "-B" (chapter 18A biotech), STAR "-U" where a name keeps it (CNINFO drops it)
METHODS = {  # PLAN.md's type table: the main method first (the fair value), then the cross-checks
    "ordinary": ["dcf", "pe_own", "pe_peers"],
    "fast_grower": ["dcf", "evs_peers", "peg_peers"],
    "loss_making": ["dcf", "evs_peers"],
    "cyclical": ["dcf_normal", "pe_normal", "pb_roe"],
    "income": ["ddm", "dcf", "yield_own"],
    "reit": ["ddm", "yield_own"],
    "bank": ["excess_return", "pb_own"],
    "insurer": ["excess_return", "pb_own"],
    "broker": ["pb_roe", "pb_own"],
    "holding": ["dcf", "pb_own"],
    "pre_revenue": [],
}


def labelled(f: dict) -> bool:
    """The exchange's pre-profit label (-B, -U) on the name. It types nothing: a company is pre-revenue by its figures
    (no revenue, or operating costs over twice the revenue); a labelled one with revenue is typed as any other, and
    page 1 says its pipeline isn't valued (compare.basis)."""
    return f.get("market") != "us" and f.get("kind") not in FINANCIAL | {"reit"} and bool(PRE_REVENUE.search(str(f.get("name")).upper()))


def rate(market: str) -> tuple[float, str]:
    r = pd.read_csv(DATA / "rates.csv").query("market == @market").dropna(subset=["y10"]).sort_values("date")
    return float(r["y10"].iloc[-1]) / 100, r["date"].iloc[-1]


def yield_of(cur: str) -> tuple[float, str, str | None]:
    """The reporting currency's own 10-year government yield, its date and a note: ChinaBond, US Treasury and the HK
    government bond under their markets, the other currencies under their lowercase code (fetch/fred.py: the OECD's
    series). A currency with none takes the US yield, said (Damodaran's rule is the currency's own riskless rate: a
    TWD or DKK cash flow discounted at a dollar yield carries the dollar's inflation)."""
    key = RATE_OF.get(cur, cur.lower())
    if (pd.read_csv(DATA / "rates.csv")["market"] == key).any():
        return *rate(key), None
    return *rate("us"), f"{cur}：没有免费的本币 10 年国债收益率，用美国 10 年国债"


def industry(dam: dict, kind: str) -> dict:
    region = "US" if dam.get("region") == "US" else "Global"
    t = damodaran.load(f"industries_{region}")
    name = dam.get("industry") or ("Total Market" if kind in FINANCIAL else "Total Market (without financials)")
    return t[t["industry"] == name].iloc[0].to_dict() | {"region": region, "name": name}


def convert(fx, value, src: str | None, dst: str) -> float | None:
    if value is None or src in (None, dst):
        return value
    return value * float(fx.get(dst, math.nan)) / float(fx.get(src, math.nan))


def country_of(f: dict) -> str:
    """Damodaran's country for the company (his company list); without a match a 20-F or 40-F filer's home (Yahoo's
    profile: a foreign private issuer's business is abroad, and his list carries its home listing, not the ADR: TSMC
    is Taiwan's, Novo Nordisk Denmark's), else a CNY reporter is China-based, else the listing market's country."""
    dam = f.get("damodaran") or {}
    for name in (dam.get("country"), f.get("home")):
        if damodaran.country(name or ""):
            return name
    return "China" if f["valuation"]["report_currency"] == "CNY" else COUNTRY[f["market"]]


def priced_in(f: dict) -> str:
    """The market whose implied premium prices the stock: its listing market, but Hong Kong for a China-based issuer
    listed in the US (offshore Chinese equity is priced there: ADRs convert into their HK lines; the HK market's members
    are 81% mainland companies by value)."""
    return "hk" if f["market"] == "us" and country_of(f) in ("China", "Hong Kong") else f["market"]


def group_of(f: dict) -> tuple[bool, bool | None]:
    """The members a stock is set against (stage 18; market.implied): those of the market that prices it valued in its
    form (banks, insurers and brokers on book; the rest), and in Hong Kong those of its home (China-based or not), so
    Link isn't set against mainland issuers' premium nor 茅台 against banks priced at 0.8 times book. China-based:
    Damodaran's country is China or the cash flows are CNY (a red chip incorporated in Hong Kong), as for the members."""
    china = country_of(f) == "China" or f["valuation"]["report_currency"] == "CNY"
    return f["kind"] in FINANCIAL, china if priced_in(f) == "hk" else None


def inputs(f: dict, mkt: dict | None) -> dict:
    """The discount rates and the balance-sheet bridge, in the reporting currency. `mkt`: the implied return of the
    market that prices the stock (priced_in; market.implied); without it, Damodaran's published premium, said."""
    v, market, kind = f["valuation"], f["market"], f["kind"]
    dam, home_market = f["damodaran"] or {}, priced_in(f)
    cur, fin, t, b = v["report_currency"], kind in FINANCIAL, v["ttm"], v["balance"]
    rf, rf_date, rf_note = yield_of(cur)
    country = country_of(f)
    c, home = damodaran.country(country), damodaran.country(COUNTRY[home_market])
    ref = damodaran.country(mkt.get("country") or COUNTRY[home_market]) if mkt else home  # the group's home: China for
    erp_market = mkt["erp"] if mkt else home["erp"]  # HK's China-based members, whose premium already carries its risk
    erp = erp_market + c["crp"] - ref["crp"]  # the company's country risk over its group's (Damodaran's)
    ind, tax_m = industry(dam, kind), 0.0 if kind == "reit" else MARGINAL_TAX.get(country, 0.25)
    mcap, debt = v["market_cap_report"], 0.0 if fin else (b["debt"] or 0.0)
    beta = ind["beta"] if fin else dcf.relever(ind["unlevered_beta_cash"], debt / mcap, tax_m)
    coe = rf + erp  # the market's own return, its country risk apart: the return the price implies is set against it
    ebit = sheet.ebit(market, t)
    cover = ebit / t["interest"] if ebit is not None and (t["interest"] or 0) > 0 else None
    fx = yahoo.load_fx()
    table = "financial" if fin else "large" if convert(fx, mcap, cur, "USD") >= LARGE_USD else "smaller"
    rows = damodaran.load("ratings").query("table == @table").to_dict("records")
    rating, spread = dcf.spread(cover, rows)
    rf_list, _ = rate(home_market)
    tax_eff = (min(max(1 - t["ni"] / t["pretax"], 0.0), 0.5) if t["pretax"] and t["pretax"] > 0 and t["ni"] is not None
               else 0.0)
    if kind == "reit":  # its profit carries property revaluations: no interest cover, rating or debt cost from it
        rating, spread = None, None
    cost = lambda e: e if fin else None if spread is None else dcf.wacc(mcap, debt, e, rf + spread, tax_m)
    coe_pub = dcf.capm(rf, beta, c["erp"])
    return {"currency": cur, "rf": rf, "rf_date": rf_date, "rf_note": rf_note,
            "country": country, "priced_in": home_market, "erp": erp, "erp_market": erp_market, "crp": c["crp"] - ref["crp"], "industry": ind["name"],
            "market": dict(mkt) if mkt else {"r": None, "note": "the market's implied return couldn't be solved: Damodaran's published premium"},
            "region": ind["region"], "beta_source": "levered industry beta" if fin else "unlevered beta (cash-corrected), relevered",
            "beta": beta, "beta_note": "the absolute view's (published premium)", "debt_to_equity": debt / mcap, "cost_equity": coe, "rating": rating, "cost_debt": None if spread is None else rf + spread,
            "interest_cover": None if kind == "reit" else cover, "tax_effective": tax_eff, "tax_marginal": tax_m,
            "wacc": cost(coe), "stable_cost": coe,  # a beta of 1 from year 1, its country risk kept, as the market's aggregate
            "stable_wacc": cost(coe),  # so the DCF's cost of capital doesn't step: the WACC at it in every year
            "g": rf, "market_return": rf + erp_market, "market_return_listing": rf_list + erp_market,
            "published": {"erp": c["erp"], "cost_equity": coe_pub, "wacc": cost(coe_pub), "stable_cost": rf + c["erp"] - c["crp"], "stable_wacc": rf + c["erp"] - c["crp"],
                          "market_return": rf + home["erp"]},  # Damodaran's published premium: the absolute view
            "ind_margin": ind.get("op_margin"), "ind_sales_to_capital": ind.get("sales_to_capital"),
            "debt": debt, "cash": 0.0 if fin or b.get("float_in_business") else (b["cash"] or 0.0), "minority": b["minority"] or 0.0,
            "pref": 0.0 if fin else b.get("pref") or 0.0,  # ahead of common holders (facts: the statements' pref line)
            "nonop": 0.0 if fin or b.get("float_in_business") else (b.get("nonop") or 0.0),  # a float's in the business
            "shares": v["shares"], "fx": v["fx_quote_to_report"], "ebit": ebit}


def capital(f: dict, x: dict) -> float:
    """Invested capital: equity + debt - cash - the stakes the bridge values apart (sheet.history's); a float's cash and
    investments stay in it (facts: an insurance carrier in an operating sector)."""
    apart = 0.0 if f["valuation"]["balance"].get("float_in_business") else (x.get("cash") or 0) + (x.get("nonop") or 0)
    return x["equity"] + (x.get("debt") or 0) - apart


def history(f: dict, key: str, n: int) -> pd.Series:
    return pd.Series([h.get(key) for h in f["history"]][-n:], dtype=float).dropna()


def line_rows(f: dict, k: dict, key: str, n: int) -> pd.Series:
    """The last `n` years of a history line as reported (NaN where missing): the issuer's other line's when this line
    has under 5 years of margins (k["long_line"], rating.long_line)."""
    line = k.get("long_line")
    return pd.Series(line[key][-n:] if line else [h.get(key) for h in f["history"]][-n:], dtype=float)


def lasted(rows: pd.Series, target: float, side: str) -> bool:
    """The margin was 3 points or more on this side of its long-run target in each of the last 3 reported years."""
    last = rows.tail(fade.LASTING_YEARS)
    return len(last) == fade.LASTING_YEARS and bool(((last - target) * (1 if side == "above" else -1) >= fade.MIN_GAP).all())


def kind_of(f: dict, k: dict, norm: float | None) -> tuple[str, str]:
    """The type and why (PLAN.md's type table; the tests' sources are cited at the constants)."""
    kind, s, t, dam = f["kind"], f["summary"], f["valuation"]["ttm"], f["damodaran"] or {}
    if kind in FINANCIAL or kind == "reit":
        return kind, f"listing type and industry: {kind}"
    rev, ebit = t["revenue"], k["ebit"]
    if not rev or rev <= 0 or (ebit is not None and -ebit > rev):
        return "pre_revenue", "no revenue, or operating costs over twice the revenue"
    m, growing = history(f, "ebit_margin", 10), ""
    commodity = dam.get("sector") in CYCLICAL_SECTORS
    cycle = (commodity or dam.get("industry") in CYCLICAL_INDUSTRIES) and len(m) >= 5 and m.min() < m.median() / 2 \
        and (commodity or downturn(f, norm or 0.0))
    if odd := one_off(f):  # one year's deal: its normal year is what the tests read
        if -odd["margin"] > 1:
            return "pre_revenue", "one year's deal after losses in every year on record; in a normal year operating costs are over twice the revenue"
        return "loss_making", "a trailing profit after losses in every year on record, on revenue that wasn't growing: one year's deal, not yet a business"
    if ebit is None or ebit <= 0:  # a cyclical at its trough: the normal year is the cycle's average margin, if positive
        if cycle and m.mean() > 0 and (commodity or (cycle_growth(f) or 0.0) < FAST):
            return "cyclical", (f"a cyclical industry and a margin that fell below half its median (low {m.min():.0%}, median "
                                f"{m.median():.0%}); the trailing year is a loss, its normal year the 10-year average margin")
        return "loss_making", "an operating loss over the last twelve months"
    if dam.get("industry") == "Diversified":
        return "holding", "Damodaran's industry: diversified holding"
    if cycle:
        g = cycle_growth(f)
        if commodity or g is None or g < FAST:
            return "cyclical", f"a cyclical industry and a margin that fell below half its median (low {m.min():.0%}, median {m.median():.0%})"
        growing = f"a cyclical industry, but revenue up {g:.0%} a year across the cycle (a growth firm, not a mature cyclical); "
    if (s.get("rev_cagr_3y") or 0) >= FAST:
        return "fast_grower", growing + f"revenue up {s['rev_cagr_3y']:.0%} a year over 3 years (Lynch's fast growers: 20-25%)"
    payout = payout_5y(f)
    if dam.get("sector") == "Utilities" or (payout and payout >= 0.6 and norm is not None and (s.get("rev_cagr_5y") or 0) < norm):
        return "income", (f"utility" if dam.get("sector") == "Utilities" else
                          f"5-year payout {payout:.0%} and revenue growth below the market's median ({norm:.1%})")
    return "ordinary", "a profitable business without a special type"


def one_off(f: dict) -> dict | None:
    """A trailing year that isn't the business: an operating profit after a loss in every fiscal year on record (3 at
    least), revenue at 3 times or more its last 3 years' median, those years not growing, and no analyst forecasting a
    profit in the last year they cover (a licence fee booked at once: 加科思's 739m against 54-156m, its two analysts
    back to a loss in 2027). Damodaran normalizes a year that isn't normal ("Investment Valuation", ch. 22): its revenue
    and margin are the last 3 fiscal years' medians, and the forecast starts there. The 3 times is code's reading of a
    year out of line."""
    t, h = f["valuation"]["ttm"], [x for x in f["history"] if x.get("revenue") and x.get("ebit_margin") is not None]
    eps = (f.get("consensus") or {}).get("eps") or {}
    if len(h) < 3 or any(x["ebit_margin"] >= 0 for x in h) or (eps and (eps[max(eps)] or 0) > 0):
        return None
    ebit = sheet.ebit(f["market"], t)
    rev = float(np.median([x["revenue"] for x in h[-3:]]))
    if ebit is None or ebit <= 0 or not t["revenue"] or t["revenue"] < 3 * rev or (f["summary"].get("rev_cagr_3y") or 0) > 0:
        return None
    return {"revenue": rev, "margin": float(np.median([x["ebit_margin"] for x in h[-3:]]))}


def downturn(f: dict, norm: float) -> bool:
    """A margin that fell below half its 10-year median in a year whose revenue grew less than the market's median
    company's over 5 years (`norm`, the fast-grower test's): the downturn the cyclical test looks for. Damodaran's
    cyclical firms are those whose revenues and earnings move with the economy, falling in its downturns ("Investment
    Valuation", ch. 22); a halving in a year of fast-rising revenue is a merger's accounting or a young firm's ramp
    (Broadcom's -3% in FY2016, the Avago-Broadcom merger year, revenue +94%), not the cycle (NVIDIA's FY2023, revenue
    flat, and Micron's FY2023, -49%, are). For the economy-driven industries only: a commodity producer's margin also
    halves when its input's price rises (a refiner's squeeze), its cycle all the same."""
    h = [(x.get("revenue"), x.get("ebit_margin")) for x in f["history"]][-11:]
    half = history(f, "ebit_margin", 10).median() / 2
    return any(r is not None and p and e is not None and e < half and r / p - 1 < norm for (p, _), (r, e) in zip(h, h[1:]))


def cycle_growth(f: dict) -> float | None:
    """Revenue growth across a cycle: the last 5 fiscal years' average revenue over the 5 before's, a year (Damodaran:
    a cycle is "between 5 and 10 years"; averages, so one year's price spike doesn't set it: Micron's FY2026 revenue,
    4 times FY2025's, gives 15% a year, NVIDIA's 52%). Normalizing is "most appropriate for cyclical firms in mature
    businesses" ("Investment Valuation", ch. 22): a company in an economy-driven cyclical industry growing as fast as
    Lynch's fast growers across the cycle is typed by its growth (its own margin median then carries the cycle, as
    Damodaran values NVIDIA). A commodity producer's revenue is its price ("Ups and Downs", 2009: commodity companies
    are normalized on the price), so Materials and Energy stay cyclical whatever their revenue did (lithium's 2021-23
    price put 赣锋锂业 at 41% a year). With 6-9 years, the two halves of them (3 or 4 years each, a year apart from the
    centre of one to the other's per year counted: a young chip maker isn't a mature business either); None with
    fewer than 6."""
    r = history(f, "revenue", 10)
    half = len(r) // 2
    if half < 3 or not r.head(half).mean() > 0:
        return None
    return float((r.tail(half).mean() / r.head(half).mean()) ** (1 / (len(r) - half)) - 1)


def payout_5y(f: dict) -> float | None:
    """Dividends over profit across the last 5 fiscal years (dividends per share on today's basis x shares)."""
    h = f["history"][-5:]
    paid, ni = [x["dps"] * x["shares"] for x in h if x.get("dps") is not None and x.get("shares")], sum(x["ni"] or 0 for x in h)
    return sum(paid) / ni if len(paid) == 5 and ni > 0 else None


def next_dividend(f: dict, k: dict, cons: dict) -> float:
    """Next year's dividend per share in the quote currency: the next 12 months' consensus EPS x the 5-year payout
    (at most all of it; Damodaran's expected dividends), else the trailing year's. A REIT's: the trailing year's (its
    payout of GAAP profit is meaningless; its consensus is FFO)."""
    v, payout = f["valuation"], payout_5y(f)
    if f["kind"] == "reit" or not cons.get("ntm_eps") or payout is None:
        return v["dps_12m"] or 0.0
    return max(cons["ntm_eps"], 0.0) * min(payout, 1.0) / k["fx"]


def forward(by_year: dict, fy_month: int, today: date, offset: int) -> float | None:
    """The 12 months starting `offset` months from today, from fiscal-year figures weighted by their months in it."""
    s, total, months = today.year * 12 + today.month - 1 + offset, 0.0, 0
    for y, value in by_year.items():
        end = int(y) * 12 + fy_month - 1
        lo, hi = max(end - 11, s), min(end, s + 11)
        if value is not None and hi >= lo:
            total, months = total + value * (hi - lo + 1) / 12, months + hi - lo + 1
    return total if months == 12 else None


def month_end(label: str) -> date:
    """The last day of a "YYYY-MM" or "YYYY-MM-DD" quarter label's month."""
    y, m = int(label[:4]), int(label[5:7])
    return date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)


def trailing_eps(f: dict, k: dict) -> tuple[float | None, str]:
    """The last twelve months' EPS on the consensus's own basis, in the reporting currency, so the consensus years
    grow from the figure they are forecast against. Nasdaq's (Zacks's) and Yahoo's consensus are mostly the companies'
    adjusted figures (Lilly's leave out acquired research and amortization, NVIDIA's and Amazon's their stakes' gains):
    the source's own four quarters that end with the trailing figures (within 20 days: 52-53-week years; a source run
    a quarter past the fact sheet, NVIDIA's Nasdaq actuals after its release, keeps the four that match).
    Eastmoney's 研报一致预期 forecasts reported profit to shareholders (归母净利润) per share: the trailing profit.
    Without either, the trailing reported profit, said."""
    c, v = f["consensus"], f["valuation"]
    reported = v["ttm"]["ni"] / k["shares"] if v["ttm"].get("ni") is not None else None
    if c["source"].startswith("Eastmoney"):
        return reported, "reported (归母净利润 per share, the consensus's own basis)"
    rows = ([(r["quarter"], r["eps"]) for r in c.get("actuals") or []] if c["source"] == "Nasdaq" else
            [(r["quarter"], r.get("actual")) for r in c.get("surprises") or [] if r.get("quarter")])
    end = date.fromisoformat(f["latest"]["period"])
    rows = sorted(r for r in rows if (month_end(r[0]) - end).days <= 20)[-4:]
    if len(rows) == 4 and all(e is not None for _, e in rows) and abs((month_end(rows[-1][0]) - end).days) <= 20 \
            and 250 <= (month_end(rows[-1][0]) - month_end(rows[0][0])).days <= 290:
        return convert(yahoo.load_fx(), sum(e for _, e in rows), c["currency"], k["currency"]), f"{c['source']}'s last four quarters"
    return reported, "reported (no trailing figures on the consensus's own basis)"


def reported_so_far(f: dict, fy_month: int) -> dict[str, float]:
    """Revenue the company has already reported for its current fiscal year (the fact sheet's year-to-date figures:
    CN and HK; a US fact sheet carries the trailing twelve months, not the year to date)."""
    x = f.get("latest") or {}
    if x.get("basis") != "year to date" or not 0 < (x.get("months") or 0) < 12 or not x.get("revenue"):
        return {}
    end = date.fromisoformat(x["period"])
    return {str(end.year if end.month <= fy_month else end.year + 1): x["revenue"]}


def revenue_years(f: dict, k: dict, fy_month: int) -> tuple[dict, dict, list[dict]]:
    """Revenue by fiscal year in the reporting currency: the EPS consensus's own brokers' where they publish it (CN:
    Eastmoney's, the panel whose EPS the margin divides; cn.revenue_consensus), else Yahoo's; an estimate below what
    the company has already reported for that fiscal year is rejected (a stale forecast: 摩尔线程's Yahoo 2026 at
    3.60bn after 3.29bn in nine months, Q3 alone +319%), the other source's taken if it isn't, and said."""
    c, fx = f["consensus"], yahoo.load_fx()
    sources = [("Eastmoney", c.get("revenue") or {}, c["currency"]),
               ("Yahoo", {y: d.get("revenue") for y, d in (c.get("yahoo_years") or {}).items()},
                c.get("revenue_currency") or k["currency"])]
    done, rev, src, rejected = reported_so_far(f, fy_month), {}, {}, []
    for y in sorted({y for _, t, _ in sources for y, v in t.items() if v}):
        for name, table, cur in sources:
            if not table.get(y):
                continue
            x = convert(fx, table[y], cur, k["currency"])
            if y in done and x < done[y]:
                rejected.append({"year": y, "source": name, "revenue": x, "reported": done[y]})
                continue
            rev[y], src[y] = x, name
            break
    return rev, src, rejected


def consensus_years(f: dict, k: dict, today: date) -> dict:
    """The consensus in the reporting currency: EPS and revenue (revenue_years) over the two 12-month windows after
    the trailing figures end (PLAN.md: years 1-2; their growth is then a true 12 months'), the next 12 months from
    today (the multiples' base), and the analysts' low and high EPS for the first year (Yahoo; CN: the brokers'
    reports). `basis_gap`: the trailing year's profit on the consensus's basis less the reported (adjusted EPS: stock
    pay, amortization), held at its amount so the consensus profit is taken back to reported terms (paths)."""
    c, fx, fy_month = f["consensus"], yahoo.load_fx(), int(f["summary"]["fy_latest"][5:7])
    eps = {y: convert(fx, e, c["currency"], k["currency"]) for y, e in c["eps"].items() if e is not None}
    yy = c.get("yahoo_years") or {}
    rev, rev_source, rejected = revenue_years(f, k, fy_month)
    end = date.fromisoformat(f["latest"]["period"])
    base = date(end.year + end.month // 12, end.month % 12 + 1, 1)
    eps0, basis = trailing_eps(f, k)
    ni0 = f["valuation"]["ttm"].get("ni")
    gap = eps0 * k["shares"] - ni0 if eps0 is not None and ni0 is not None and not basis.startswith("reported") else 0.0
    out = {"eps": [], "revenue": [], "from": base.isoformat(), "ntm_eps": forward(eps, fy_month, today, 0),
           "ntm_revenue": forward(rev, fy_month, today, 0), "eps0": eps0, "eps0_basis": basis, "basis_gap": gap,
           "revenue_source": rev_source, "revenue_rejected": rejected}
    for i in range(2):
        e = forward(eps, fy_month, base, 12 * i)
        if e is None:
            break
        out["eps"].append(e)
        out["revenue"].append(forward(rev, fy_month, base, 12 * i))
    out["range"] = None  # the first forecast year's low and high over its mean, within one source
    first = min(eps, default=None)
    reports = [r["eps"][first] for r in c.get("reports") or [] if first and (r.get("eps") or {}).get(first) is not None]
    mean_y, d = (c.get("eps_yahoo") or {}).get(first), yy.get(first) or {}
    if len(reports) >= 3 and c["eps"][first] > 0:  # CN: the brokers' own forecasts of the last six months
        out["range"] = (min(reports) / c["eps"][first], max(reports) / c["eps"][first])
    elif mean_y and mean_y > 0 and d.get("eps_low") is not None and d.get("eps_high") is not None:
        out["range"] = (d["eps_low"] / mean_y, d["eps_high"] / mean_y)
    return out


def normal(f: dict, k: dict) -> dict | None:
    """A cyclical's normal year (stage 18), Damodaran's normalization by scaled averages ("Investment Valuation", ch.
    22): "average the firm's return on investment or profit margins over prior periods ... a firm with an average
    return on capital of 12 percent over prior periods and a current capital invested of $1,000 million would have
    normalized operating income of $120 million". The margin variant applies it to today's revenue, which for a firm
    whose revenue moves with its price (his commodity companies, normalized on the price first; memory makers) is
    itself the cycle: Micron's FY2027 consensus revenue is 7 times FY2025's. So capital, which a price spike doesn't
    inflate: the 10-year average pre-tax return on operating capital (equity + debt - cash - the non-operating assets
    the bridge values apart, sheet.history's capital) x that capital today. Its revenue is that profit at the 10-year
    average margin, so new capital earns the normal return (sales to capital = normal revenue / capital: "we also have
    to normalize return on capital, reinvestment", Damodaran, "Ups and Downs", 2009). Without 5 years' returns or with
    no capital today, the margin variant on the trailing revenue. None when the cycle's average margin is a loss."""
    margin, rev0 = history(f, "ebit_margin", 10).mean(), f["valuation"]["ttm"]["revenue"]
    if not margin > 0:
        return None
    roc = [x["ebit_margin"] * x["revenue"] / c for x in f["history"][-10:] if x.get("ebit_margin") is not None
           and x.get("revenue") and x.get("equity") is not None and (c := capital(f, x)) > 0]
    now = capital_now(f, k)
    if len(roc) < MOAT_YEARS or now <= 0 or float(np.mean(roc)) <= 0:
        return {"source": "10-year average margin x trailing revenue", "margin": float(margin), "revenue": rev0,
                "ebit": rev0 * margin, "roc": None, "capital": None, "years": len(roc)}
    ebit = float(np.mean(roc)) * now
    return {"source": "10-year average return on capital x today's capital", "margin": float(margin),
            "revenue": ebit / margin, "ebit": ebit, "roc": float(np.mean(roc)), "capital": now, "years": len(roc)}


def paths(f: dict, k: dict, kind: str, cons: dict, g_term: float) -> dict:
    """Ten years of revenue growth and margins: the consensus years first, each a 12-month window both the revenue
    consensus (revenue_years) and the profit consensus cover (a margin needs both: a window past the revenue forecasts
    ends them, where NVIDIA's second year put 50% more profit on base-rate revenue, a 79% margin), its operating income
    from the consensus profit (consensus_ebit). Then (stage 14, PLAN.md "Forecast"):
    - Growth: the base rate (k["base_growth"]: the median 5-year revenue growth of companies of the same size,
      Mauboussin's base rates) plus the share of the last consensus year's excess over it that the market's history
      keeps in each following year (k["growth_shares"], measured on one year's excess; k["trend_shares"] on three
      years' for the 3-year trend a company without a consensus starts from), to year 5, then in equal steps to the
      stable rate by year 10 (the Ginzu's two stages). Without a base rate, growth falls from the last consensus year's
      to the stable rate.
    - Margin: an own 8-year median target is approached as the market's history says a margin's gap to its median
      shrinks, the same share each year, above and below the median apart (k["margin_keep"]; Fama and French 2000's
      partial adjustment), a gap that has lasted 3 reported years at its own measured rate (k["lasting_keep"], stage
      26: part of a lasting gap is a moved level, not noise); a cyclical's 10-year average (normalized earnings after the years the consensus sees) and
      the young's mature-peer margin are reached by year 5 (the Ginzu's default). The young (PLAN.md "Forecast"): a
      loss-maker, a fast grower with a loss year (else its margin is established), under 5 years of history or a
      negative 8-year median. With no consensus: the 3-year revenue trend."""
    t, s = f["valuation"]["ttm"], f["summary"]
    rev0, ebit0, eps0 = t["revenue"], k["ebit"], cons.get("eps0")
    m0, base, odd = ebit0 / rev0, k.get("base_growth"), one_off(f) if kind == "loss_making" else None
    if odd:  # the trailing year was a one-off: the forecast starts from the normal year's revenue and margin
        rev0, m0 = odd["revenue"], odd["margin"]
    growth, margin, check, prev_r = [], [], [], rev0
    for e, r in [] if odd else zip(cons["eps"], cons["revenue"]):
        if not r or prev_r <= 0:  # a margin needs the revenue and the profit of the same 12 months
            break
        growth.append(r / prev_r - 1)
        margin.append(consensus_ebit(f, k, cons, e) / r)
        check.append(ebit0 * e / eps0 / r if eps0 and eps0 > 0 and e > 0 else None)  # the EPS-growth figure: a check
        prev_r = r
    n = len(growth)
    nm = normal(f, k) if kind == "cyclical" else None
    if nm:  # the consensus years as earned, then the normal year growing at the base rate: no consensus excess
        # carried on ("double counting growth, once by normalizing earnings and again by using a higher growth rate",
        # "Ups and Downs"; the measured shares are every company's, and a cyclical's consensus year is its cycle)
        earned, r = [], rev0
        for g_, m_ in zip(growth, margin):
            r *= 1 + g_
            earned.append((r, r * m_))
        g0 = base if base is not None else g_term
        return {"growth": [g0] * CONVERGENCE + [g0 + (g_term - g0) * t_ / (dcf.YEARS - CONVERGENCE) for t_ in range(1, 6)],
                "margin": [nm["margin"]] * dcf.YEARS, "target_margin": nm["margin"], "consensus_years": n,
                "revenue0": nm["revenue"], "earned": earned, "normal": nm, "margin_source": "10-year average", "eps_check": check,
                "sales_to_capital": nm["revenue"] / nm["capital"] if nm["capital"] else None}
    shares, fixed = k.get("growth_shares") or [0.0] * CONVERGENCE, len(growth)  # the years the consensus fixes
    if not growth:
        growth = [s.get("rev_cagr_3y") or s.get("rev_cagr_5y") or g_term]
        margin, shares = [m0], k.get("trend_shares") or [0.0] * CONVERGENCE
    rows = line_rows(f, k, "ebit_margin", 8)
    own = rows.dropna()
    young = kind == "loss_making" or kind == "fast_grower" and (own <= 0).any() or len(own) < 5 or own.median() <= 0
    if kind == "cyclical":
        target = history(f, "ebit_margin", 10).mean()
    elif young:  # mature firms' margin
        target = k.get("mature_margin") or k["ind_margin"]
    else:
        target = own.median()
    n = len(growth)
    if base is None:
        growth += [growth[-1] + (g_term - growth[-1]) * (t_ - n) / (dcf.YEARS - n) for t_ in range(n + 1, dcf.YEARS + 1)]
    else:
        growth += [base + shares[t_ - n - 1] * (growth[n - 1] - base) for t_ in range(n + 1, CONVERGENCE + 1)]
        g5 = growth[-1]
        growth += [g5 + (g_term - g5) * (t_ - CONVERGENCE) / (dcf.YEARS - CONVERGENCE) for t_ in range(CONVERGENCE + 1, dcf.YEARS + 1)]
    last, lasting = margin[-1], False
    if kind == "cyclical" or young:
        margin += [target if t_ >= CONVERGENCE else last + (target - last) * (t_ - n) / (CONVERGENCE - n)
                   for t_ in range(n + 1, dcf.YEARS + 1)]
    else:
        side = "above" if last > target else "below"
        keep = k["margin_keep"][side]
        if lasted(rows, target, side):  # the rate differs only where the measurement found lasting gaps keep more
            keep, lasting = (k.get("lasting_keep") or {}).get(side, keep), (k.get("lasting_keep") or {}).get(side, keep) != keep
        margin += [target + (last - target) * keep ** (t_ - n) for t_ in range(n + 1, dcf.YEARS + 1)]
    return {"growth": growth, "margin": margin, "target_margin": target, "margin_lasting": lasting, "consensus_years": n,
            "fixed_years": fixed, "eps_check": check,
            **({"revenue0": rev0, "one_off": True} if odd else {}),
            "margin_source": "10-year average" if kind == "cyclical" else "profitable peers' median" if young and target == k.get("mature_margin")
            else "industry" if young else "other line's 8-year median" if k.get("long_line") else "own 8-year median"}


def consensus_ebit(f: dict, k: dict, cons: dict, eps: float) -> float:
    """A consensus window's operating income from its profit (stage 23; Damodaran: operating growth from revenue and
    margin, not from EPS, which buybacks, interest and investment gains move): net income = the consensus EPS x
    today's shares, less the basis gap (an adjusted consensus back to reported terms, consensus_years), taken back to
    operating income through the trailing year's own bridge: grossed up at its effective tax rate (as the DCF's first
    years tax it; a loss isn't grossed up) and its net interest and non-operating income (EBIT less pretax profit)
    held at their amounts. A turn to profit is kept whatever the trailing EPS (摩尔线程: trailing -0.51, the first
    window's 1.05)."""
    t = f["valuation"]["ttm"]
    ni = eps * k["shares"] - (cons.get("basis_gap") or 0.0)
    bridge = k["ebit"] - t["pretax"] if t.get("pretax") is not None else 0.0
    return (ni / (1 - (k.get("tax_effective") or 0.0)) if ni > 0 else ni) + bridge


def capital_now(f: dict, k: dict) -> float:
    """Today's invested capital on one balance sheet: a US filer's equity is its latest 10-Q's, its cash, debt and
    stakes its 10-K's, whose year end then gives the equity too (NVIDIA's cash earned since counted as capital). The
    equity is the parent's, with its preferred stock and perpetuals, as each history year's is (book_common leaves them
    out)."""
    v = f["valuation"]
    equity = (v["book_common"] or 0.0) + k.get("pref", 0.0)  # the preferred stock and perpetuals fund the assets too
    if (f.get("latest") or {}).get("period") != v["balance"].get("period"):
        equity = next((x["equity"] for x in f["history"] if x["period"] == v["balance"]["period"] and x.get("equity")), equity)
    return capital(f, {"equity": equity, "debt": k["debt"], "cash": k["cash"], "nonop": k["nonop"]})


YOUNG_SOURCES = ("profitable peers' median", "industry")  # paths' margin sources for a young company


def sales_to_capital(f: dict, k: dict, margin_source: str | None = None) -> tuple[float, str]:
    """Revenue over invested capital (equity + debt - cash - the stakes valued apart, as sheet.history's return on
    capital: their revenue isn't in revenue), its 5-year median when invested capital is positive in at least 3 of
    them; else the industry's. A company whose long-run margin is mature peers' (a young one, paths) takes its
    industry's, as its margin (stage 23: Damodaran's young-firm default, the Ginzu's and "Valuing Young, Start-up and
    Growth Companies", 2009): capital built while revenue was small doesn't set a mature firm's needs, and own capital
    beside peers' margin made growth destroy value (摩尔线程: own 0.32 x 18.1% x 75% = 4.3% on new capital against a
    6.8% cost)."""
    if margin_source in YOUNG_SOURCES and k.get("ind_sales_to_capital"):
        return k["ind_sales_to_capital"], "industry (its long-run margin is mature peers')"
    if (k.get("long_line") or {}).get("s2c"):
        return k["long_line"]["s2c"], f"its {k['long_line']['market'].upper()} line's 5-year median"
    own = own_s2c(f)
    return (own, "own 5-year median") if own else (k["ind_sales_to_capital"], "industry")


def own_s2c(f: dict) -> float | None:
    """The 5-year median of revenue over invested capital, with at least 3 years of positive capital."""
    s2c = [x["revenue"] / ic for x in f["history"][-5:] if x.get("revenue") and x.get("equity") is not None
           and (ic := capital(f, x)) > 0]
    return float(np.median(s2c)) if len(s2c) >= 3 else None


def moat(series: pd.Series, cost: float, stable: float, keep: float) -> dict:
    """The graded moat (Morningstar's excess-return period, measured): how long the return (on capital; financials:
    on equity) beat the company's cost (`track`: the share of its last 10 years, at least 5 needed) and how far (`edge`:
    its median over the stable cost) give the expected excess today, track x edge (a track is the frequency of excess
    years, the odds they go on); it fades by the market's measured annual share kept (`keep`, fade.excess_keep), so the
    return on new capital in stable year j (year 10 + j) is stable + track x edge x keep^(10 + j), for at most
    Morningstar's 15-year stage II, then the cost of capital (its stage III). `start`: the return in year 10, where the
    explicit years end."""
    if len(series) < MOAT_YEARS or series.median() <= stable or not (series > cost).any():
        return {"track": float((series > cost).mean()) if len(series) else None, "edge": None, "keep": keep,
                "start": stable, "ronic": [], "years": 0, "moat": False}
    track, edge = float((series > cost).mean()), float(series.median() - stable)
    return faded(track, edge, keep, stable)


def faded(track: float, edge: float, keep: float, stable: float) -> dict:
    ronic = [stable + track * edge * keep ** (dcf.YEARS + j) for j in range(1, STAGE2 + 1)]
    return {"track": track, "edge": edge, "keep": keep, "start": stable + track * edge * keep ** dcf.YEARS,
            "ronic": ronic, "years": STAGE2, "moat": True, "stable": stable}


def moat_case(m: dict, case: str | None) -> dict:
    """The moat in a scenario (stage 18): "off", the excess returns end with the explicit years (Morningstar's no-moat
    stage II of about a year); "on", they last as long as the edge allows (a track of 1: the odds that they go on
    come true); else as graded."""
    if case == "off" and m["moat"]:
        return m | {"start": m["stable"], "ronic": [], "years": 0, "moat": False}
    if case == "on" and m["moat"]:
        return faded(1.0, m["edge"], m["keep"], m["stable"])
    return m


def dcf_value(f: dict, k: dict, path: dict, s2c: float, ronic: list[float], cost_shift=0.0, g_term=None) -> tuple[float, dict]:
    g = k["g"] if g_term is None else g_term
    cost = dcf.steps(k["wacc"] + cost_shift, k["stable_wacc"] + cost_shift)
    res = dcf.fcff(path.get("revenue0") or f["valuation"]["ttm"]["revenue"], path["growth"], path["margin"],
                   dcf.steps(k["tax_effective"], k["tax_marginal"]), [s2c] * dcf.YEARS, cost, g,
                   k["stable_wacc"] + cost_shift, [r + cost_shift for r in ronic], k["tax_marginal"], earned=path.get("earned"))
    equity = dcf.equity_value(res["operating"], k["debt"], k["minority"], k["cash"], k["nonop"], pref=k["pref"])
    return equity / k["shares"] / k["fx"], res


def peer_medians(f: dict, today: date, q: float = 0.5) -> dict:
    """The peers' medians in the day's snapshot, the company left out: P/E, EV/Sales, PEG (forward P/E over consensus
    growth) and the profitable members' operating margin (the mature firms' margin a young company's target takes,
    Damodaran's advice). The group is the fact sheet's industry when it has at least 10 members (Damodaran's floor for
    an industry average, damodaran.MIN_FIRMS; Apple's industry is IBM, Dell, HP and Super Micro), else its sector.
    `q`: another quantile of the multiples (a stand-in multiple's scenarios take the peers' quartiles, stage 18)."""
    snap, p = sheet.snapshot(f["market"], today), f.get("peers") or {}
    if snap.empty or not p:
        return {}
    g, by, group = snap[snap[p["by"]] == p["group"]], p["by"], p["group"]
    me = snap[snap["code"] == f["code"]]
    if len(g) < damodaran.MIN_FIRMS and len(me):
        by, group = "sector", me["sector"].iloc[0]
        g = snap[snap["sector"] == group]
    g = g[g["code"] != f["code"]]
    evs = (g["ev"] / g["revenue_ttm"]).where((g["ev"] > 0) & (g["revenue_ttm"] > 0))
    peg = (g["fwd_pe"] / (g["fwd_growth"] * 100)).where((g["fwd_growth"] > 0) & (g["fwd_pe"] > 0))
    margin = (g["ebit"] / g["revenue_ttm"]).where(g["revenue_ttm"] > 0)
    profitable = margin[margin > 0]
    return {"by": by, "group": group, "count": len(g), "pe": g["pe"].where(g["pe"] > 0).quantile(q), "ev_sales": evs.quantile(q),
            "peg": peg.quantile(q), "profitable": len(profitable),
            "mature_margin": float(profitable.median()) if len(profitable) >= damodaran.MIN_FIRMS else None,
            "mature_quartiles": [float(profitable.quantile(0.25)), float(profitable.quantile(0.75))]
            if len(profitable) >= damodaran.MIN_FIRMS else None}
