"""Research stage 15: the rating from the main method's fair value (PLAN.md "Rating"), the way the investment-research
skill asks: one main method per type with the others as cross-checks, the skills' checks acting on the rating, and
discrete risks as a scenario, never in the discount rate.
- The gap: (fair value - price + next year's dividend) / price - the market's expected return, the market's being its
  implied return (market.py), so a stock priced like the market comes out at 0. 买入 at +band or more, 卖出 at -band
  or worse, else 持有.
- The band: the main method's bear-to-bull half-range, rounded up to 5 points, at least the brokers' 10% and at most
  Morningstar's 75%; an earnings red flag moves it to the next step of Morningstar's margins of safety (20, 30, 40, 50,
  75% at low to extreme uncertainty).
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

BAND = (0.10, 0.75)  # at least the brokers' 10%, at most Morningstar's margin of safety for extreme uncertainty
STEPS = [0.20, 0.30, 0.40, 0.50, 0.75]  # Morningstar's margins of safety for its top rating, low to extreme uncertainty
QUALITY_TYPES = {"ordinary", "fast_grower", "cyclical", "income", "holding"}  # established businesses: the screen's
# indicators apply (financials skip them; a REIT's profit carries revaluations and it grows on new equity; a loss-maker
# fails them by construction: quality-screen asks other measures of the immature)
UNCOVERED = 3  # dividends above free cash flow in most of the last 5 years: "recurring" (code's reading of the gate)
CHINA = {"China", "Hong Kong"}


def view(gap: float, band: float) -> str:
    return "买入" if gap >= band else "卖出" if gap <= -band else "持有"


def gap(value: float, price: float, dividend: float, market_return: float) -> float:
    return (value - price + dividend) / price - market_return


def band(target: float, bear: float, bull: float, widen: bool) -> dict:
    spread = (max(bull, target, bear) - min(bull, target, bear)) / 2 / target if target > 0 else math.inf
    b = min(max(math.ceil(spread * 20 - 1e-9) / 20, BAND[0]), BAND[1]) if math.isfinite(spread) else BAND[1]
    wide = next((s for s in STEPS if s > b + 1e-9), BAND[1]) if widen else b
    return {"scenario_half_range": spread, "band": wide, "band_scenarios": b}


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


def judge(main: str, found: dict, order: list[str], price: float, dividend: float, market_return: float, b: dict,
          acts: dict) -> dict:
    """The rating: the main method's view, the cross-checks against it, then the blocks."""
    g = gap(found[main]["target"], price, dividend, market_return)
    rows = [{"method": m, "target": found[m]["target"], "gap": gap(found[m]["target"], price, dividend, market_return)}
            for m in order if m != main and m in found and found[m].get("target") is not None]
    for r in rows:
        r["view"] = view(r["gap"], b["band"])
    first = view(g, b["band"])
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


def tail(f: dict, sections: dict | None, fair: float, price: float, dividend: float, market_return: float, b: float,
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
    floor = {"买入": b, "持有": -b}.get(rating)  # the gap at which it falls a step
    for x in out:
        x["breakeven"] = None
        if x["value"] is not None and floor is not None:
            # (1 - p) (fair + dividend) / price + p (value / price) - 1 - market = floor
            p = 1 - ((1 + market_return + floor) * price - x["value"]) / (fair + dividend - x["value"])
            x["breakeven"] = min(max(p, 0.0), 1.0)
    return out

