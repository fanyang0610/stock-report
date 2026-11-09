"""Research stage 10, part 1: the company's type (its playbook), the discount rates, the forecast paths and each
valuation method's value per share, from the fact sheet and Damodaran's data (PLAN.md "The method"). rating.py weighs
them into the target, the scenarios and the rating. Every choice below is a published default, cited where it is made:
- Rates are in the reporting currency (the cash flows' currency, so r and g are in one currency): its government's
  10-year yield (ChinaBond, US Treasury, HK government bond; other currencies: the US yield, said).
- Equity risk premium: Damodaran's for the company's country (his company list); the benchmark's expected return is
  the listing market's premium over the reporting currency's yield (the currency the target grows in). Beta: his industry's unlevered beta corrected for cash, from the US table for
  US companies and the global table for the rest (his practice and the Ginzu's "Industry (Global)"; his China-region
  averages give the whole market a beta of 1.75), relevered at the company's market debt to equity with the statutory
  tax rate; banks, insurers and brokers use the industry's levered beta (debt is their raw material).
- Debt cost: the yield plus the default spread of the synthetic rating from interest cover (his large-firm table above
  USD 5bn of market value, else the smaller-firm one).
- Stable period (the simple Ginzu's defaults): the cost of capital of a mature company (yield + the mature-market
  premium), growth at the yield but at least 5 points below that cost (the investment-research skill's r - g rule),
  and a return on new capital equal to the cost of capital, except that a company whose return stayed above its cost
  of capital in each of at least 8 years keeps half of its median edge (Morningstar's moat idea, from data)."""

import math
import re
from datetime import date

import numpy as np
import pandas as pd

from stockreport.config import DATA
from stockreport.fetch import yahoo
from stockreport.research import damodaran, dcf, sheet
from stockreport.research.checks import FINANCIAL

RATE_OF = {"CNY": "cn", "USD": "us", "HKD": "hk"}
COUNTRY = {"cn": "China", "hk": "Hong Kong", "us": "United States"}
MARGINAL_TAX = {"China": 0.25, "Hong Kong": 0.165, "United States": 0.25}  # CN EIT, HK profits tax, US federal + state
GAP = 0.05  # investment-research: the stable cost of capital at least 5 points above growth
LARGE_USD = 5e9  # Damodaran's cut between his large-firm and smaller-firm rating tables
FAST = 0.20  # Lynch's fast growers grow 20-25% a year ("One Up on Wall Street", 1989)
MOAT_YEARS = 8
CONVERGENCE = 5  # the simple Ginzu's default year of margin convergence
CYCLICAL_SECTORS = {"Materials", "Energy"}  # with these industries: the plan's materials, energy, chemicals, shipping, memory
CYCLICAL_INDUSTRIES = {"Semiconductor", "Semiconductor Equip", "Shipbuilding & Marine", "Transportation"}
FLOOR = {"markets": {"cn", "hk"}, "kinds": {"bank", "insurer"}, "peers": 5}  # your decision of 2026-11-09
PRE_REVENUE = re.compile(r"-[A-Z]*[UB][A-Z]*$")  # HKEX "-B" (chapter 18A biotech), STAR "-U" where a name keeps it (CNINFO drops it)
WEIGHTS = {  # PLAN.md's type table
    "ordinary": {"dcf": .5, "pe_own": .25, "pe_peers": .25},
    "fast_grower": {"dcf": .6, "evs_peers": .2, "peg_peers": .2},
    "loss_making": {"dcf": .5, "evs_peers": .5},
    "cyclical": {"dcf_normal": 1 / 3, "pe_normal": 1 / 3, "pb_roe": 1 / 3},
    "income": {"ddm": .5, "dcf": .25, "yield_own": .25},
    "reit": {"ddm": .5, "yield_own": .5},
    "bank": {"excess_return": .5, "pb_own": .5},
    "insurer": {"excess_return": .5, "pb_own": .5},
    "broker": {"pb_roe": .5, "pb_own": .5},
    "holding": {"dcf": .5, "pb_own": .5},
    "pre_revenue": {},
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


def inputs(f: dict) -> dict:
    """The discount rates and the balance-sheet bridge, in the reporting currency."""
    v, dam, market, kind = f["valuation"], f["damodaran"] or {}, f["market"], f["kind"]
    cur, fin, t, b = v["report_currency"], kind in FINANCIAL, v["ttm"], v["balance"]
    rf, rf_date = rate(RATE_OF.get(cur, "us"))
    country = dam["country"] if damodaran.country(dam.get("country") or "") else COUNTRY[market]
    c = damodaran.country(country)
    ind, tax_m = industry(dam, kind), 0.0 if kind == "reit" else MARGINAL_TAX.get(country, 0.25)
    mcap, debt = v["market_cap_report"], 0.0 if fin else (b["debt"] or 0.0)
    beta = ind["beta"] if fin else dcf.relever(ind["unlevered_beta_cash"], debt / mcap, tax_m)
    coe = dcf.capm(rf, beta, c["erp"])
    ebit = None if t["pretax"] is None else t["pretax"] + (t["interest"] or 0)
    cover = ebit / t["interest"] if ebit is not None and (t["interest"] or 0) > 0 else None
    fx = yahoo.load_fx()
    table = "financial" if fin else "large" if convert(fx, mcap, cur, "USD") >= LARGE_USD else "smaller"
    rows = damodaran.load("ratings").query("table == @table").to_dict("records")
    rating, spread = dcf.spread(cover, rows)
    stable = rf + c["erp"] - c["crp"]  # a mature company's cost of capital: the yield + the mature-market premium
    rf_list, _ = rate(market)
    tax_eff = (min(max(1 - t["ni"] / t["pretax"], 0.0), 0.5) if t["pretax"] and t["pretax"] > 0 and t["ni"] is not None
               else 0.0)
    if kind == "reit":  # its profit carries property revaluations: no interest cover, rating or debt cost from it
        rating, spread = None, None
    return {"currency": cur, "rf": rf, "rf_date": rf_date, "rf_note": None if cur in RATE_OF else f"{cur}: the US yield used",
            "country": country, "erp": c["erp"], "mature_erp": c["erp"] - c["crp"], "industry": ind["name"],
            "region": ind["region"], "beta_source": "levered industry beta" if fin else "unlevered beta (cash-corrected), relevered",
            "beta": beta, "debt_to_equity": debt / mcap, "cost_equity": coe, "rating": rating, "cost_debt": None if spread is None else rf + spread,
            "interest_cover": None if kind == "reit" else cover, "tax_effective": tax_eff, "tax_marginal": tax_m,
            "wacc": coe if fin else None if spread is None else dcf.wacc(mcap, debt, coe, rf + spread, tax_m), "stable_cost": stable,
            "g": min(rf, stable - GAP), "market_return": rf + damodaran.country(COUNTRY[market])["erp"],
            "market_return_listing": rf_list + damodaran.country(COUNTRY[market])["erp"],
            "ind_margin": ind.get("op_margin"), "ind_sales_to_capital": ind.get("sales_to_capital"),
            "debt": debt, "cash": 0.0 if fin else (b["cash"] or 0.0), "minority": b["minority"] or 0.0,
            "shares": v["shares"], "fx": v["fx_quote_to_report"], "ebit": ebit}


def implied_floor(f: dict, k: dict, today: date) -> dict:
    """CN and HK banks and insurers: the cost of equity is at least their industry's implied one (Gebhardt, Lee and
    Swaminathan 2001's implied cost of capital, in its stable-growth form: each member's COE that makes the justified
    P/B equal its P/B on next year's consensus ROE, trailing where none; the median of the same industry in the day's
    snapshot, at least 5 members), so a discount the market has priced for years isn't assumed to close within the
    12 months; the stable cost too, and growth stays 5 points below it. The CAPM figure is kept beside it."""
    if f["market"] not in FLOOR["markets"] or f["kind"] not in FLOOR["kinds"]:
        return k
    snap, p = sheet.snapshot(f["market"], today), f.get("peers") or {}
    if snap.empty or not p:
        return k
    grp = snap[snap[p["by"]] == p["group"]]
    roe = (grp["eps_e1"] / grp["bps"]).where((grp["eps_e1"] > 0) & (grp["bps"] > 0)).fillna(grp["roe"])
    r = dcf.implied_cost_equity(roe, grp["pb"], k["g"]).where(grp["pb"] > 0).dropna()
    floor = {"implied_cost_equity": float(r.median()) if len(r) else None, "members": len(r), "group": p["group"],
             "cost_equity_capm": k["cost_equity"], "stable_cost_capm": k["stable_cost"]}
    if len(r) < FLOOR["peers"] or floor["implied_cost_equity"] <= k["cost_equity"]:
        return k | {"floor": floor | {"applied": False}}
    c = floor["implied_cost_equity"]
    stable = max(k["stable_cost"], c)
    return k | {"cost_equity": c, "wacc": c, "stable_cost": stable, "g": min(k["rf"], stable - GAP),
                "floor": floor | {"applied": True}}


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


def consensus_years(f: dict, k: dict, today: date) -> dict:
    """The consensus in the reporting currency: EPS and (Yahoo's) revenue over the two 12-month windows after the
    trailing figures end (PLAN.md: years 1-2; their growth is then a true 12 months'), the next 12 months from today
    (the multiples' base), and the analysts' low and high EPS for the first year (Yahoo; CN: the brokers' reports)."""
    c, fx, fy_month = f["consensus"], yahoo.load_fx(), int(f["summary"]["fy_latest"][5:7])
    eps = {y: convert(fx, e, c["currency"], k["currency"]) for y, e in c["eps"].items() if e is not None}
    yy = c.get("yahoo_years") or {}
    rev = {y: d["revenue"] for y, d in yy.items() if d.get("revenue")}
    end = date.fromisoformat(f["latest"]["period"])
    base = date(end.year + end.month // 12, end.month % 12 + 1, 1)
    out = {"eps": [], "revenue": [], "from": base.isoformat(), "ntm_eps": forward(eps, fy_month, today, 0),
           "ntm_revenue": forward(rev, fy_month, today, 0)}
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
    """Ten years of revenue growth and margins: the consensus years first (revenue from Yahoo's revenue consensus,
    else growing with the consensus profit; operating income moving with the consensus profit), then growth falling in
    equal steps to the stable rate by year 10 and the margin moving to its target by year 5 (the Ginzu's default).
    Targets: a cyclical's 10-year average (normalized earnings after the years the consensus sees); the industry's for
    the young (PLAN.md "Forecast"): a loss-maker, a fast grower, under 5 years of history or a negative 8-year median;
    the rest their own 8-year median. With no consensus: the
    3-year revenue trend, faded."""
    t, s = f["valuation"]["ttm"], f["summary"]
    rev0, ni0, ebit0, shares = t["revenue"], t["ni"], k["ebit"], k["shares"]
    m0 = ebit0 / rev0
    growth, margin, prev_r, prev_e = [], [], rev0, (ni0 / shares if ni0 else None)
    for e, r in zip(cons["eps"], cons["revenue"]):
        pg = e / prev_e - 1 if prev_e and prev_e > 0 and e > 0 else None
        rg = r / prev_r - 1 if r and prev_r > 0 else pg
        if rg is None:
            break
        growth.append(rg)
        level = rev0 * math.prod(1 + g for g in growth)
        margin.append(ebit0 * (e * shares / ni0) / level if ni0 and ni0 > 0 and e > 0 else m0)
        prev_r, prev_e = r or level, e
    if not growth:
        growth = [s.get("rev_cagr_3y") or s.get("rev_cagr_5y") or g_term]
        margin = [m0]
    own = history(f, "ebit_margin", 8)
    if kind == "cyclical":
        target = history(f, "ebit_margin", 10).mean()
    elif kind in ("loss_making", "fast_grower") or len(own) < 5 or own.median() <= 0:  # young: its industry's
        target = k["ind_margin"]
    else:
        target = own.median()
    n = len(growth)
    growth += [growth[-1] + (g_term - growth[-1]) * (t_ - n) / (dcf.YEARS - n) for t_ in range(n + 1, dcf.YEARS + 1)]
    last = margin[-1]
    margin += [target if t_ >= CONVERGENCE else last + (target - last) * (t_ - n) / (CONVERGENCE - n)
               for t_ in range(n + 1, dcf.YEARS + 1)]
    return {"growth": growth, "margin": margin, "target_margin": target, "consensus_years": n,
            "margin_source": "10-year average" if kind == "cyclical" else "industry" if target == k["ind_margin"] else "own 8-year median"}


def sales_to_capital(f: dict, k: dict) -> tuple[float, str]:
    """Revenue over invested capital (equity + debt - cash), its 5-year median when invested capital is positive in
    at least 3 of them; else the industry's."""
    h = f["history"][-5:]
    s2c = [x["revenue"] / ic for x in h if x.get("revenue") and x.get("equity") is not None
           and (ic := x["equity"] + (x.get("debt") or 0) - (x.get("cash") or 0)) > 0]
    return (float(np.median(s2c)), "own 5-year median") if len(s2c) >= 3 else (k["ind_sales_to_capital"], "industry")


def moat(series: pd.Series, cost: float, stable: float) -> tuple[float, bool]:
    """The stable return on new capital: the stable cost of capital, plus half the median edge when the return beat
    the company's cost of capital in each of at least 8 years."""
    if len(series) >= MOAT_YEARS and (series > cost).all() and series.median() > stable:
        return stable + (series.median() - stable) / 2, True
    return stable, False


def dcf_value(f: dict, k: dict, path: dict, s2c: float, roic_term: float, cost_shift=0.0, g_term=None) -> tuple[float, dict]:
    g = k["g"] if g_term is None else g_term
    cost = dcf.steps(k["wacc"] + cost_shift, k["stable_cost"] + cost_shift)
    res = dcf.fcff(f["valuation"]["ttm"]["revenue"], path["growth"], path["margin"],
                   dcf.steps(k["tax_effective"], k["tax_marginal"]), [s2c] * dcf.YEARS, cost, g,
                   k["stable_cost"] + cost_shift, max(roic_term + cost_shift, k["stable_cost"] + cost_shift), k["tax_marginal"])
    equity = dcf.equity_value(res["operating"], k["debt"], k["minority"], k["cash"])
    return equity / k["shares"] / k["fx"], res


def peer_medians(f: dict, today: date) -> dict:
    """The industry group's median EV/Sales and PEG in the day's snapshot (the fact sheet's peers group)."""
    snap, p = sheet.snapshot(f["market"], today), f.get("peers") or {}
    if snap.empty or not p:
        return {}
    g = snap[snap[p["by"]] == p["group"]]
    evs = (g["ev"] / g["revenue_ttm"]).where((g["ev"] > 0) & (g["revenue_ttm"] > 0))
    peg = (g["fwd_pe"] / (g["fwd_growth"] * 100)).where((g["fwd_growth"] > 0) & (g["fwd_pe"] > 0))
    return {"ev_sales": evs.median(), "peg": peg.median(), "count": len(g)}
