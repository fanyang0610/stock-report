"""Research stage 10, part 1: the company's type (its playbook), the discount rates, the forecast paths and each
valuation method's value per share, from the fact sheet and Damodaran's data (PLAN.md "The method"). rating.py weighs
them into the target, the scenarios and the rating. Every choice below is a published default, cited where it is made:
- Rates are in the reporting currency (the cash flows' currency, so r and g are in one currency): its government's
  10-year yield (ChinaBond, US Treasury, HK government bond; other currencies: the US yield, said).
- Cost of equity (stage 15): the reporting currency's yield plus the listing market's implied premium (research/
  market.py: the return at which the market's members are worth their price under this model's own cash-flow rules,
  less the yield) plus Damodaran's country risk premium for the company's country (his company list) over the listing
  market's, at a beta of 1: the stock's implied return is set against its market's (firm-level implied returns predict
  returns, Lee, So and Wang 2021; beta doesn't sort them, Fama and French 1992, Frazzini and Pedersen 2014). The
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
from stockreport.research import damodaran, dcf, sheet
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


def rate(market: str) -> tuple[float, str]:
    r = pd.read_csv(DATA / "rates.csv").query("market == @market").dropna(subset=["y10"]).sort_values("date")
    return float(r["y10"].iloc[-1]) / 100, r["date"].iloc[-1]


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
    """Damodaran's country for the company (his company list); without a match a CNY reporter is China-based, else
    the listing market's country."""
    dam = f.get("damodaran") or {}
    if damodaran.country(dam.get("country") or ""):
        return dam["country"]
    return "China" if f["valuation"]["report_currency"] == "CNY" else COUNTRY[f["market"]]


def priced_in(f: dict) -> str:
    """The market whose implied premium prices the stock: its listing market, but Hong Kong for a China-based issuer
    listed in the US (offshore Chinese equity is priced there: ADRs convert into their HK lines; the HK market's members
    are 81% mainland companies by value)."""
    return "hk" if f["market"] == "us" and country_of(f) in ("China", "Hong Kong") else f["market"]


def inputs(f: dict, mkt: dict | None) -> dict:
    """The discount rates and the balance-sheet bridge, in the reporting currency. `mkt`: the implied return of the
    market that prices the stock (priced_in; market.implied); without it, Damodaran's published premium, said."""
    v, market, kind = f["valuation"], f["market"], f["kind"]
    dam, home_market = f["damodaran"] or {}, priced_in(f)
    cur, fin, t, b = v["report_currency"], kind in FINANCIAL, v["ttm"], v["balance"]
    rf, rf_date = rate(RATE_OF.get(cur, "us"))
    country = country_of(f)
    c, home = damodaran.country(country), damodaran.country(COUNTRY[home_market])
    erp_market = mkt["erp"] if mkt else home["erp"]
    erp = erp_market + c["crp"] - home["crp"]  # the company's country risk over its market's (Damodaran's)
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
    return {"currency": cur, "rf": rf, "rf_date": rf_date, "rf_note": None if cur in RATE_OF else f"{cur}: the US yield used",
            "country": country, "priced_in": home_market, "erp": erp, "erp_market": erp_market, "crp": c["crp"] - home["crp"], "industry": ind["name"],
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
            "debt": debt, "cash": 0.0 if fin else (b["cash"] or 0.0), "minority": b["minority"] or 0.0,
            "nonop": 0.0 if fin else (b.get("nonop") or 0.0),
            "shares": v["shares"], "fx": v["fx_quote_to_report"], "ebit": ebit}


def history(f: dict, key: str, n: int) -> pd.Series:
    return pd.Series([h.get(key) for h in f["history"]][-n:], dtype=float).dropna()


def kind_of(f: dict, k: dict, norm: float | None) -> tuple[str, str]:
    """The type and why (PLAN.md's type table; the tests' sources are cited at the constants)."""
    kind, s, t, dam = f["kind"], f["summary"], f["valuation"]["ttm"], f["damodaran"] or {}
    if kind in FINANCIAL or kind == "reit":
        return kind, f"listing type and industry: {kind}"
    rev, ebit = t["revenue"], k["ebit"]
    label = f["market"] != "us" and PRE_REVENUE.search(str(f["name"]).upper())
    if label or not rev or rev <= 0 or (ebit is not None and -ebit > rev):
        return "pre_revenue", "the exchange's pre-profit label, or costs over twice the revenue"
    if ebit is None or ebit <= 0:
        return "loss_making", "an operating loss over the last twelve months"
    if dam.get("industry") == "Diversified":
        return "holding", "Damodaran's industry: diversified holding"
    m = history(f, "ebit_margin", 10)
    if (dam.get("sector") in CYCLICAL_SECTORS or dam.get("industry") in CYCLICAL_INDUSTRIES) and len(m) >= 5 \
            and m.min() < m.median() / 2:
        return "cyclical", f"a cyclical industry and a margin that fell below half its median (low {m.min():.0%}, median {m.median():.0%})"
    if (s.get("rev_cagr_3y") or 0) >= FAST:
        return "fast_grower", f"revenue up {s['rev_cagr_3y']:.0%} a year over 3 years (Lynch's fast growers: 20-25%)"
    payout = payout_5y(f)
    if dam.get("sector") == "Utilities" or (payout and payout >= 0.6 and norm is not None and (s.get("rev_cagr_5y") or 0) < norm):
        return "income", (f"utility" if dam.get("sector") == "Utilities" else
                          f"5-year payout {payout:.0%} and revenue growth below the market's median ({norm:.1%})")
    return "ordinary", "a profitable business without a special type"


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
    the source's own four latest quarters, when they end with the trailing figures (within 20 days: 52-53-week years).
    Eastmoney's 研报一致预期 forecasts reported profit to shareholders (归母净利润) per share: the trailing profit.
    Without either, the trailing reported profit, said."""
    c, v = f["consensus"], f["valuation"]
    reported = v["ttm"]["ni"] / k["shares"] if v["ttm"].get("ni") is not None else None
    if c["source"].startswith("Eastmoney"):
        return reported, "reported (归母净利润 per share, the consensus's own basis)"
    rows = ([(r["quarter"], r["eps"]) for r in c.get("actuals") or []] if c["source"] == "Nasdaq" else
            [(r["quarter"], r.get("actual")) for r in c.get("surprises") or [] if r.get("quarter")])
    rows = sorted(rows)[-4:]
    end = date.fromisoformat(f["latest"]["period"])
    if len(rows) == 4 and all(e is not None for _, e in rows) and abs((month_end(rows[-1][0]) - end).days) <= 20 \
            and 250 <= (month_end(rows[-1][0]) - month_end(rows[0][0])).days <= 290:
        return convert(yahoo.load_fx(), sum(e for _, e in rows), c["currency"], k["currency"]), f"{c['source']}'s last four quarters"
    return reported, "reported (no trailing figures on the consensus's own basis)"


def consensus_years(f: dict, k: dict, today: date) -> dict:
    """The consensus in the reporting currency: EPS and (Yahoo's) revenue over the two 12-month windows after the
    trailing figures end (PLAN.md: years 1-2; their growth is then a true 12 months'), the next 12 months from today
    (the multiples' base), and the analysts' low and high EPS for the first year (Yahoo; CN: the brokers' reports)."""
    c, fx, fy_month = f["consensus"], yahoo.load_fx(), int(f["summary"]["fy_latest"][5:7])
    eps = {y: convert(fx, e, c["currency"], k["currency"]) for y, e in c["eps"].items() if e is not None}
    yy = c.get("yahoo_years") or {}
    rev = {y: convert(fx, d["revenue"], c.get("revenue_currency") or k["currency"], k["currency"])
           for y, d in yy.items() if d.get("revenue")}
    end = date.fromisoformat(f["latest"]["period"])
    base = date(end.year + end.month // 12, end.month % 12 + 1, 1)
    eps0, basis = trailing_eps(f, k)
    out = {"eps": [], "revenue": [], "from": base.isoformat(), "ntm_eps": forward(eps, fy_month, today, 0),
           "ntm_revenue": forward(rev, fy_month, today, 0), "eps0": eps0, "eps0_basis": basis}
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


def paths(f: dict, k: dict, kind: str, cons: dict, g_term: float) -> dict:
    """Ten years of revenue growth and margins: the consensus years first, each a 12-month window both the revenue
    consensus (Yahoo's) and the profit consensus cover (a margin needs both: a window past the revenue forecasts ends
    them, where NVIDIA's second year put 50% more profit on base-rate revenue, a 79% margin), its operating income the
    trailing one (stock-based pay a cost) grown as the consensus EPS grows from the trailing EPS on its own basis
    (trailing_eps). Then (stage 14, PLAN.md "Forecast"):
    - Growth: the base rate (k["base_growth"]: the median 5-year revenue growth of companies of the same size,
      Mauboussin's base rates) plus the share of the last consensus year's excess over it that the market's history
      keeps in each following year (k["growth_shares"], measured on one year's excess; k["trend_shares"] on three
      years' for the 3-year trend a company without a consensus starts from), to year 5, then in equal steps to the
      stable rate by year 10 (the Ginzu's two stages). Without a base rate, growth falls from the last consensus year's
      to the stable rate.
    - Margin: an own 8-year median target is approached as the market's history says a margin's gap to its median
      shrinks, the same share each year, above and below the median apart (k["margin_keep"]; Fama and French 2000's
      partial adjustment); a cyclical's 10-year average (normalized earnings after the years the consensus sees) and
      the young's mature-peer margin are reached by year 5 (the Ginzu's default). The young (PLAN.md "Forecast"): a
      loss-maker, a fast grower with a loss year (else its margin is established), under 5 years of history or a
      negative 8-year median. With no consensus: the 3-year revenue trend."""
    t, s = f["valuation"]["ttm"], f["summary"]
    rev0, ebit0, eps0 = t["revenue"], k["ebit"], cons.get("eps0")
    m0, base = ebit0 / rev0, k.get("base_growth")
    growth, margin, prev_r = [], [], rev0
    for e, r in zip(cons["eps"], cons["revenue"]):
        if not r or prev_r <= 0:  # a margin needs the revenue and the profit of the same 12 months
            break
        growth.append(r / prev_r - 1)
        margin.append(ebit0 * e / eps0 / r if eps0 and eps0 > 0 and e > 0 else m0)
        prev_r = r
    shares = k.get("growth_shares") or [0.0] * CONVERGENCE
    if not growth:
        growth = [s.get("rev_cagr_3y") or s.get("rev_cagr_5y") or g_term]
        margin, shares = [m0], k.get("trend_shares") or [0.0] * CONVERGENCE
    own = history(f, "ebit_margin", 8)
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
    last = margin[-1]
    if kind == "cyclical" or young:
        margin += [target if t_ >= CONVERGENCE else last + (target - last) * (t_ - n) / (CONVERGENCE - n)
                   for t_ in range(n + 1, dcf.YEARS + 1)]
    else:
        keep = k["margin_keep"]["above" if last > target else "below"]
        margin += [target + (last - target) * keep ** (t_ - n) for t_ in range(n + 1, dcf.YEARS + 1)]
    return {"growth": growth, "margin": margin, "target_margin": target, "consensus_years": n,
            "margin_source": "10-year average" if kind == "cyclical" else "profitable peers' median" if young and target == k.get("mature_margin")
            else "industry" if young else "own 8-year median"}


def sales_to_capital(f: dict, k: dict) -> tuple[float, str]:
    """Revenue over invested capital (equity + debt - cash), its 5-year median when invested capital is positive in
    at least 3 of them; else the industry's."""
    h = f["history"][-5:]
    s2c = [x["revenue"] / ic for x in h if x.get("revenue") and x.get("equity") is not None
           and (ic := x["equity"] + (x.get("debt") or 0) - (x.get("cash") or 0)) > 0]
    return (float(np.median(s2c)), "own 5-year median") if len(s2c) >= 3 else (k["ind_sales_to_capital"], "industry")


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
    ronic = [stable + track * edge * keep ** (dcf.YEARS + j) for j in range(1, STAGE2 + 1)]
    return {"track": track, "edge": edge, "keep": keep, "start": stable + track * edge * keep ** dcf.YEARS,
            "ronic": ronic, "years": STAGE2, "moat": True}


def dcf_value(f: dict, k: dict, path: dict, s2c: float, ronic: list[float], cost_shift=0.0, g_term=None) -> tuple[float, dict]:
    g = k["g"] if g_term is None else g_term
    cost = dcf.steps(k["wacc"] + cost_shift, k["stable_wacc"] + cost_shift)
    res = dcf.fcff(f["valuation"]["ttm"]["revenue"], path["growth"], path["margin"],
                   dcf.steps(k["tax_effective"], k["tax_marginal"]), [s2c] * dcf.YEARS, cost, g,
                   k["stable_wacc"] + cost_shift, [r + cost_shift for r in ronic], k["tax_marginal"])
    equity = dcf.equity_value(res["operating"], k["debt"], k["minority"], k["cash"], k["nonop"])
    return equity / k["shares"] / k["fx"], res


def peer_medians(f: dict, today: date) -> dict:
    """The peers' medians in the day's snapshot, the company left out: P/E, EV/Sales, PEG (forward P/E over consensus
    growth) and the profitable members' operating margin (the mature firms' margin a young company's target takes,
    Damodaran's advice). The group is the fact sheet's industry when it has at least 10 members (Damodaran's floor for
    an industry average, damodaran.MIN_FIRMS; Apple's industry is IBM, Dell, HP and Super Micro), else its sector."""
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
    return {"by": by, "group": group, "count": len(g), "pe": g["pe"].where(g["pe"] > 0).median(), "ev_sales": evs.median(),
            "peg": peg.median(), "profitable": len(profitable),
            "mature_margin": float(profitable.median()) if len(profitable) >= damodaran.MIN_FIRMS else None}
