"""The valuation math (PLAN.md "Valuation and target price"), plain functions on numbers so pytest checks them against
published examples: the cost of capital (CAPM with a bottom-up beta relevered for the company's debt, debt cost from
the interest-cover rating table), Damodaran's 10-year FCFF model in the structure of his "simple Ginzu" spreadsheet,
its reverse (the growth today's price assumes), the excess-return model and justified P/B for financial firms, the
two-stage dividend discount model, and the sensitivity grid."""

import math

YEARS = 10


def relever(beta_u: float, debt_to_equity: float, tax: float) -> float:
    """Hamada: the levered beta of an unlevered (operating-asset) beta at a debt to equity ratio."""
    return beta_u * (1 + (1 - tax) * max(debt_to_equity, 0))


def capm(rf: float, beta: float, erp: float) -> float:
    return rf + beta * erp


def wacc(equity: float, debt: float, cost_equity: float, cost_debt: float, tax: float) -> float:
    total = equity + max(debt, 0)
    return (equity * cost_equity + max(debt, 0) * cost_debt * (1 - tax)) / total


def spread(cover: float | None, table: list[dict]) -> tuple[str, float]:
    """The synthetic rating and default spread for an interest cover (EBIT / interest expense), Damodaran's table
    (rows with low, high, rating, spread). No interest expense: the top row."""
    if cover is None:
        best = max(table, key=lambda r: r["high"])
        return best["rating"], best["spread"]
    below = [r for r in table if r["low"] <= cover]  # the bands' bounds leave gaps (4.249999 / 4.25): the band started
    row = max(below, key=lambda r: r["low"]) if below else min(table, key=lambda r: r["low"])
    return row["rating"], row["spread"]


def steps(start: float, end: float) -> list[float]:
    """Years 1-5 at start, then equal steps to end in year 10 (the simple Ginzu's path for growth after year 5, the
    tax rate and the cost of capital)."""
    return [start] * 5 + [start + (end - start) / 5 * k for k in range(1, 6)]


def fcff(revenue0: float, growth: list[float], margin: list[float], tax: list[float], sales_to_capital: list[float],
         cost: list[float], g_term: float, wacc_term: float, ronic: list[float], tax_term: float, nol: float = 0.0) -> dict:
    """Value of the operating assets: ten years of free cash flow to the firm, then the stable period growing at
    g_term (terminal). Reinvestment is next year's revenue change over the sales-to-capital ratio (one year's lag,
    Ginzu's default); in the stable period it is g / the return on new capital of NOPAT: `ronic` for the years excess
    returns last, then the cost of capital (growth adds no value). A tax loss carried forward shields operating income
    until used."""
    rev = [revenue0]
    for g in growth:
        rev.append(rev[-1] * (1 + g))
    rev_term = rev[YEARS] * (1 + g_term)
    ebit = [rev[t] * margin[t - 1] for t in range(1, YEARS + 1)]
    nopat, left = [], nol
    for e, t in zip(ebit, tax):
        nopat.append(e if e <= 0 or e < left else e - (e - left) * t)
        left = left - e if e < 0 else max(left - e, 0)
    nxt = rev[2:] + [rev_term]
    reinvest = [(nxt[t] - rev[t + 1]) / sales_to_capital[t] for t in range(YEARS)]
    flows = [n - r for n, r in zip(nopat, reinvest)]
    factor, disc = 1.0, []
    for c in cost:
        factor /= 1 + c
        disc.append(factor)
    tv = terminal(rev_term * margin[-1] * (1 - tax_term), g_term, wacc_term, ronic)
    pv = sum(f * d for f, d in zip(flows, disc))
    return {"revenue": rev[1:], "ebit": ebit, "nopat": nopat, "reinvestment": reinvest, "fcff": flows, "discount": disc,
            "terminal_value": tv, "pv_terminal": tv * disc[-1], "pv_flows": pv, "operating": pv + tv * disc[-1]}


def fcfe(book0: float, roe: list[float], growth: list[float], cost: float, g_term: float, ronic: list[float]) -> dict:
    """fcff's rules in equity terms (a market's aggregate, research/market.py): each year's profit is its ROE on the
    opening book, the book grows at `growth` (the reinvestment growth needs, as revenue over sales to capital in fcff) and
    the rest is paid out; then the stable period as in fcff: the year-10 ROE on the book in place, new capital earning
    `ronic`, then its cost (terminal). With ROE equal to the cost every year the value is the book."""
    book, factor, pv = book0, 1.0, 0.0
    for r, g in zip(roe, growth):
        factor /= 1 + cost
        pv += (r - g) * book * factor
        book *= 1 + g
    tv = terminal(roe[-1] * book, g_term, cost, ronic)
    return {"value": pv + tv * factor, "pv_flows": pv, "pv_terminal": tv * factor}


def terminal(nopat: float, g: float, cost: float, ronic: list[float]) -> float:
    """The stable period's value a year before `nopat` (year 11's) is earned, in Morningstar's last two stages: the
    years excess returns last, each new unit of capital earning that year's `ronic` (growth g takes g / RONIC of
    NOPAT), then a return on new capital equal to the cost of capital, whose value is NOPAT / cost at any growth
    (Koller's value-driver formula, RONIC = WACC). With no excess years it is the Ginzu's NOPAT (1 - g / WACC) / (WACC -
    g) for g > 0."""
    pv, n, factor = 0.0, nopat, 1.0
    for r in ronic:
        factor /= 1 + cost
        pv += n * (1 - g / r if g > 0 else 1.0) * factor
        n *= 1 + g
    return pv + (n / cost if g > 0 else n / (cost - g)) * factor


STEP, LIMIT = 0.005, 1 / 9  # stable growth +0.5 point may raise the terminal value by at most 1/9: the investment-
# research skill's tools/terminal_value.py check ("g 只要再加 0.5pct", its 5-point r - g floor) for a perpetuity of
# a fixed payout, where 0.005 / (r - g - 0.005) <= 1/9 is r - g >= 5 points


def tested_growth(tv, g_max: float, g_min: float = 0.0) -> float:
    """The highest stable growth up to `g_max` (the riskless rate: Damodaran's cap) at which `tv(g)`, a terminal value
    as a function of growth, passes the sensitivity test; `g_min` when none does."""
    def ok(g):
        a, b = tv(g), tv(g + STEP)
        return a > 0 and b > 0 and b / a - 1 <= LIMIT
    if ok(g_max):
        return g_max
    if not ok(g_min):
        return g_min
    lo, hi = g_min, g_max
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo


def equity_value(operating: float, debt: float, minority: float, cash: float, nonop: float = 0.0, options: float = 0.0) -> float:
    return operating - debt - minority + cash + nonop - options


def solve(f, target: float, low: float, high: float, tol: float = 1e-7) -> float | None:
    """x in [low, high] with f(x) = target for an increasing f, by bisection; None when the target is outside."""
    if not f(low) <= target <= f(high):
        return None
    for _ in range(200):
        mid = (low + high) / 2
        if f(mid) < target:
            low = mid
        else:
            high = mid
        if high - low < tol:
            break
    return (low + high) / 2


def justified_pb(roe: float, cost_equity: float, g: float) -> float:
    """Gordon growth on book equity: P/B = (ROE - g) / (COE - g)."""
    return (roe - g) / (cost_equity - g)


def implied_cost_equity(roe, pb, g):
    """The cost of equity a price implies, the justified P/B solved for COE: g + (ROE - g) / (P/B) (works on numbers
    and pandas Series)."""
    return g + (roe - g) / pb


def excess_terminal(book: float, fade: list[float], cost: float, g: float) -> float:
    """The stable period's excess returns a year before they start: the ROE of each year excess returns last
    (`fade`) on a book growing at g, then ROE = the cost of equity (no excess: value = book)."""
    pv, factor = 0.0, 1.0
    for r in fade:
        factor /= 1 + cost
        pv += (r - cost) * book * factor
        book *= 1 + g
    return pv


def excess_return(book0: float, roe: list[float], payout: list[float], cost: list[float], fade: list[float],
                  cost_term: float, g_term: float) -> dict:
    """Equity value = book + the present value of each year's excess return (ROE - COE) x opening book, book growing
    by retained profit (Damodaran, "Investment Valuation", ch. 21); then the stable period: the years excess returns
    last at the ROEs `fade`, then none (excess_terminal)."""
    book, factor, pv, rows = book0, 1.0, 0.0, []
    for r, p, c in zip(roe, payout, cost):
        excess = (r - c) * book
        factor /= 1 + c
        pv += excess * factor
        rows.append({"book": book, "roe": r, "excess": excess})
        book *= 1 + r * (1 - p)
    term = excess_terminal(book, fade, cost_term, g_term)
    return {"value": book0 + pv + term * factor, "pv_excess": pv, "pv_terminal": term * factor, "book_end": book, "years": rows}


def ddm(dps0: float, g1: float, years: int, cost: float, g_term: float) -> float:
    """Two-stage dividend discount: dividends grow at g1 for `years`, then at g_term for ever."""
    pv, d, factor = 0.0, dps0, 1.0
    for _ in range(years):
        d *= 1 + g1
        factor /= 1 + cost
        pv += d * factor
    return pv + d * (1 + g_term) / (cost - g_term) * factor


def grid(value, costs: list[float], growths: list[float]) -> list[list[float | None]]:
    """value(cost shift, growth shift) over a grid; None where the cost doesn't exceed the growth."""
    out = []
    for c in costs:
        row = []
        for g in growths:
            try:
                v = value(c, g)
            except ZeroDivisionError:
                v = None
            row.append(v if v is not None and math.isfinite(v) else None)
        out.append(row)
    return out
