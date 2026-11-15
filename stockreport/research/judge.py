"""Research stages 15 and 18: the rating from the main method's fair value (PLAN.md "Rating"), the way the investment-research
skill asks: one main method per type with the others as cross-checks, the skills' checks acting on the rating, and
discrete risks as a scenario, never in the discount rate.
- The gap: (fair value - price + next year's dividend) / price - the market's expected return, the market's being the
  implied return of the stock's group (market.py), so a stock priced like its group comes out at 0.
- The rating (stage 18): Morningstar's two-sided table on price over fair value (Uncertainty Rating Methodology Update
  FAQ, 2022): 5 stars at a 20 / 30 / 40 / 50 / 75% discount, 1 star at a 25 / 35 / 55 / 75 / 300% premium at low /
  medium / high / very high / extreme uncertainty. Price over fair value is today's price against the 12-month fair
  value plus its dividend brought back a year at the market's return, (1 + m) / (1 + m + gap): 买入 at or below 1 -
  the discount, 卖出 at or above 1 + the premium, else 持有. Until stage 18 a symmetric 10-75% band on the gap.
- The level: Morningstar's bear and bull are the outcomes with a 25% chance of worse and of better, and "the distance
  between the bull and bear cases in relation to the fair value estimate was used to assign an uncertainty rating".
  Each scenario input of the main method moves to its own quartile (rating.build: the analysts' range, the margin or
  ROE, growth beyond the consensus, the moat off or on, a stand-in multiple's quartiles), and their effects are
  combined as independent (the root of the sum of squares: moving every input to its quartile at once is a far rarer
  case than 1 in 4). The level is the lowest whose 5-star discount covers the bear-to-bull half-range (Morningstar
  publishes no cut-offs: code's reading); an earnings red flag moves it one level up.
- Cross-checks: each other method's gap the same way. When most of them (more than half, each on its own gap, nothing
  averaged) rate the opposite way (买入 against 卖出), the state is unresolved and the rating 持有, with what the cross-check would need in the main method's terms (the
  skill: explain the economic reason, never average it away, keep it unresolved rather than force a rating).
- Blocks: a failed quality screen (quality-screen's purpose is to drop the inferior before buying; Asness, Frazzini and
  Pedersen 2019: low-quality stocks earn less), the checklist's quick veto (3 straight years of negative free cash flow)
  or a recurring uncovered dividend (income-investment's blocking gate, for the income type: a REIT's free cash flow
  isn't measured) turns 买入 into 持有.
- The tail (investment-research's terminal-value tool: delisting or a VIE's failure is a yearly hazard, which a higher
  rate would misplace in time): a China-based issuer listed in the US or HK whose annual report describes a VIE /
  contractual-arrangement structure, and a China-based issuer listed in the US (the HFCAA). The value if it happens
  (0 for a void VIE: the accounts don't separate what isn't run through it; a delisted ADR with an HK line converts
  into it) and the chance of it over the year at which the rating would fall a step."""

import math
from collections import Counter

from stockreport.research import value
from stockreport.research.checks import FINANCIAL

LEVELS = [("low", 0.20, 0.25), ("medium", 0.30, 0.35), ("high", 0.40, 0.55), ("very high", 0.50, 0.75),
          ("extreme", 0.75, 3.00)]  # Morningstar's Uncertainty Ratings: the discount for 5 stars, the premium for 1 star
QUALITY_TYPES = {"ordinary", "fast_grower", "cyclical", "income", "holding"}  # established businesses: the screen's
# indicators apply (financials skip them; a REIT's profit carries revaluations and it grows on new equity; a loss-maker
# fails them by construction: quality-screen asks other measures of the immature)
UNCOVERED = 3  # dividends above free cash flow in most of the last 5 years: "recurring" (code's reading of the gate)
CHINA = {"China", "Hong Kong"}


def view(gap: float, u: dict, market_return: float) -> str:
    """买入 / 持有 / 卖出 from price over fair value (today's: the 12-month value and dividend a year back at the
    market's return) against the level's discount and premium."""
    worth = 1 + market_return + gap  # (fair value + dividend) / price
    ratio = (1 + market_return) / worth if worth > 0 else math.inf
    return "买入" if ratio <= 1 - u["discount"] + 1e-12 else "卖出" if ratio >= 1 + u["premium"] - 1e-12 else "持有"


def gap(value: float, price: float, dividend: float, market_return: float) -> float:
    return (value - price + dividend) / price - market_return


def scenarios(target: float, inputs: dict[str, tuple[float, float]]) -> tuple[float, float]:
    """Bear and bull from each input's value at its 25th and 75th percentile, combined as independent effects."""
    down = math.sqrt(sum(max(target - min(v), 0.0) ** 2 for v in inputs.values()))
    up = math.sqrt(sum(max(max(v) - target, 0.0) ** 2 for v in inputs.values()))
    return max(target - down, 0.0), target + up


def uncertainty(target: float, bear: float, bull: float, widen: bool, market_return: float) -> dict:
    """The level from the bear-to-bull half-range, a red flag one level up; with the gaps at which it is 买入 and 卖出
    at the market's return (for the report: +buy or more, -sell or worse)."""
    half = (max(bull, target, bear) - min(bull, target, bear)) / 2 / target if target > 0 else math.inf
    i = next((n for n, (_, d, _p) in enumerate(LEVELS) if half <= d + 1e-9), len(LEVELS) - 1)
    name, d, p = LEVELS[min(i + bool(widen), len(LEVELS) - 1)]
    m = 1 + market_return
    return {"level": name, "level_scenarios": LEVELS[i][0], "discount": d, "premium": p, "scenario_half_range": half,
            "buy": m / (1 - d) - m, "sell": m - m / (1 + p)}


def checks(f: dict, kind: str) -> dict:
    """The skills' checks that act: {block: [...], widen: [...]}, each {check, why}."""
    c, block, widen = f["checks"], [], []
    q = c.get("quality_screen") or {}
    if kind in QUALITY_TYPES and q.get("result") == "exclude":
        block.append({"check": "quality_screen", "why": "failed: " + ", ".join(q["failed"])})
    if (c.get("checklist") or {}).get("fcf_negative_3y"):
        block.append({"check": "checklist_veto", "why": "free cash flow negative 3 years running"})
    inc = c.get("income") or {}
    if kind == "income" and (inc.get("uncovered_years_5y") or 0) >= UNCOVERED:  # a REIT's free cash flow isn't measured
        block.append({"check": "dividend_uncovered", "why": f"dividends above free cash flow in {inc['uncovered_years_5y']} of 5 years"})
    m, e = (c.get("beneish") or {}).get("m_score"), c.get("earnings_signals") or {}
    signals = [k for k in ("receivables_faster", "inventory_faster", "cash_below_profit_widening") if e.get(k)]
    if kind not in FINANCIAL and m is not None and m > -1.78:
        widen.append({"check": "beneish", "why": f"M-score {m:.2f} above -1.78"})
    if kind not in FINANCIAL and len(signals) >= 2:
        widen.append({"check": "earnings_signals", "why": ", ".join(signals)})
    return {"block": block, "widen": widen}


def cover(f: dict) -> float | None:
    """Free cash flow over dividends paid across the last 5 fiscal years (income-investment's coverage); None when
    either isn't reported (a REIT's property purchases aren't capex)."""
    h = [x for x in f["history"][-5:] if x.get("fcf") is not None and x.get("div_paid")]
    paid = sum(abs(x["div_paid"]) for x in h)
    return sum(x["fcf"] for x in h) / paid if len(h) == 5 and paid > 0 else None


def fcfe_payout(f: dict) -> float | None:
    """Dividends paid over free cash flow to equity across the last 5 fiscal years (FCFE: operating cash flow less
    capex plus the debt raised over them, when the debt is reported at both ends); None when either isn't reported (a
    REIT's property purchases aren't capex), infinity when the FCFE isn't positive."""
    h = f["history"][-6:]
    five = [x for x in h[-5:] if x.get("fcf") is not None and x.get("div_paid")]
    if len(five) < 5:
        return None
    fcfe = sum(x["fcf"] for x in five)
    if len(h) == 6 and h[0].get("debt") is not None and h[-1].get("debt") is not None:
        fcfe += h[-1]["debt"] - h[0]["debt"]
    return sum(abs(x["div_paid"]) for x in five) / fcfe if fcfe > 0 else math.inf


def main_order(f: dict, kind: str) -> tuple[list[str], float | None]:
    """The type's methods, main first (value.METHODS), and for the income type the dividends' share of FCFE when it
    moves the main method: Damodaran's rule of thumb, "if dividends are less than 80% of FCFE or dividends are greater
    than 110% of FCFE over a 5-year period, use the FCFE model" (valuation lectures, "Given cash flows to equity,
    should I discount dividends or FCFE?"): the dividend model "understates the value because dividends are less than
    FCFE" (his S&P 500 example), the cash kept being the holders' too. The DCF stands in for the FCFE model: the same
    free cash flow, with the cash kept at book in the bridge (五粮液 paid 60% of its FCFE over 2021-25 and holds
    ¥28.8 a share of net cash the dividend model never pays out)."""
    order, ratio = value.METHODS[kind], fcfe_payout(f) if kind == "income" else None
    if ratio is None or value.DDM_FIT[0] <= ratio <= value.DDM_FIT[1]:
        return order, None
    return ["dcf"] + [m for m in order if m != "dcf"], ratio


LAG = 0.20  # a divergence this large could move a rating by itself (the low level's 20% discount): page 1 says so


def lag(f: dict) -> dict | None:
    """The price's move over 3 months against the revision of next year's consensus over the same 90 days (Yahoo's
    trend, the one free revision history in every market), when the price moved by LAG or more and the consensus
    didn't follow (they diverge by LAG or more the price's way: a price held while forecasts fell isn't this case). An implied return
    reads today's price against forecasts that adjust slowly: analysts' forecasts lag the information in past
    returns, a predictable error in implied costs of capital (Guay, Kothari and Shu 2011, as their abstract states
    it), so after a fall the implied return rises before the consensus moves (NVIDIA -28% in 3 months while its next
    year's consensus rose 24%). Lee, So and Wang find implied-cost-of-capital proxies best in the time series and
    characteristic proxies best in the cross-section, the use the rating makes of them."""
    c, ret = f["consensus"], (f.get("price") or {}).get("ret_3m")
    years = [y for y, d in (c.get("yahoo_years") or {}).items() if d.get("eps_90d") and (c.get("eps_yahoo") or {}).get(y)]
    if ret is None or not years:
        return None
    y = max(years)
    before, now = c["yahoo_years"][y]["eps_90d"], c["eps_yahoo"][y]
    if before <= 0 or now <= 0:
        return None
    gap = (1 + ret) / (now / before) - 1
    far = abs(ret) >= LAG and abs(gap) >= LAG and (gap < 0) == (ret < 0)
    return {"year": y, "price_3m": ret, "revision_3m": now / before - 1, "gap": gap} if far else None


def judge(main: str, found: dict, order: list[str], price: float, dividend: float, market_return: float, b: dict,
          acts: dict) -> dict:
    """The rating: the main method's view, the cross-checks against it, then the blocks."""
    g = gap(found[main]["target"], price, dividend, market_return)
    rows = [{"method": m, "target": found[m]["target"], "gap": gap(found[m]["target"], price, dividend, market_return)}
            for m in order if m != main and m in found and found[m].get("target") is not None]
    for r in rows:
        r["view"] = view(r["gap"], b, market_return)
    first = view(g, b, market_return)
    opposite = {"买入": "卖出", "卖出": "买入"}.get(first)
    votes = Counter(r["view"] for r in rows)
    others = max(votes, key=lambda v: (votes[v], v == "持有")) if rows else None  # the view most of them give (ties: 持有)
    state, rating = "resolved", first
    if opposite and votes[opposite] * 2 > len(rows):  # most cross-checks rate it the opposite way, each on its own gap
        state, rating, others = "unresolved", "持有", opposite
    if rating == "买入" and acts["block"]:
        state, rating = "blocked", "持有"
    return {"rating": rating, "state": state, "main_view": first, "checks_view": others, "fair_excess": g, "cross": rows}


def exposed(f: dict) -> bool:
    """A China-based issuer (value.country_of) listed in the US or HK."""
    return value.country_of(f) in CHINA and f["market"] != "cn"


def tail(f: dict, sections: dict | None, fair: float, price: float, dividend: float, market_return: float, b: dict,
         rating: str) -> list[dict]:
    """The discrete risks that apply, each with its value if it happens and the yearly chance at which the rating
    would fall a step (the fair value's gap with that chance of the tail's value, against the band)."""
    if not exposed(f):
        return []
    out, hk = [], [o for o in f.get("other_listings") or [] if o["market"] == "hk"]
    if (sections or {}).get("vie"):
        out.append({"risk": "vie", "value": 0.0})
    if f["market"] == "us":
        out.append({"risk": "delisting", "value": None if hk else 0.0, "line": hk[0]["code"] if hk else None})
    floor = {"买入": b["buy"], "持有": -b["sell"]}.get(rating)  # the gap at which it falls a step
    for x in out:
        x["breakeven"] = None
        if x["value"] is not None and floor is not None:
            # (1 - p) (fair + dividend) / price + p (value / price) - 1 - market = floor
            p = 1 - ((1 + market_return + floor) * price - x["value"]) / (fair + dividend - x["value"])
            x["breakeven"] = min(max(p, 0.0), 1.0)
    return out

