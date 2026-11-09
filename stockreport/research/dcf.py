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
         cost: list[float], g_term: float, wacc_term: float, roic_term: float, tax_term: float, nol: float = 0.0) -> dict:
    """Value of the operating assets: ten years of free cash flow to the firm, then a stable year growing at g_term.
    Reinvestment is next year's revenue change over the sales-to-capital ratio (one year's lag, Ginzu's default); in
    the stable period it is g / return on capital of NOPAT (a return equal to the cost of capital adds no value). A tax
    loss carried forward shields operating income until used."""
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
    term_nopat = rev_term * margin[-1] * (1 - tax_term)
    term_flow = term_nopat - (g_term / roic_term * term_nopat if g_term > 0 else 0)
    tv = term_flow / (wacc_term - g_term)
    pv = sum(f * d for f, d in zip(flows, disc))
    return {"revenue": rev[1:], "ebit": ebit, "nopat": nopat, "reinvestment": reinvest, "fcff": flows, "discount": disc,
            "terminal_value": tv, "pv_terminal": tv * disc[-1], "pv_flows": pv, "operating": pv + tv * disc[-1]}


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


def excess_return(book0: float, roe: list[float], payout: list[float], cost: list[float], roe_term: float,
                  cost_term: float, g_term: float) -> dict:
    """Equity value = book + the present value of each year's excess return (ROE - COE) x opening book, book growing
    by retained profit; after the last year a stable period at roe_term, cost_term and g_term, whose value over book is
    the justified P/B's (Damodaran, "Investment Valuation", ch. 21)."""
    book, factor, pv, rows = book0, 1.0, 0.0, []
    for r, p, c in zip(roe, payout, cost):
        excess = (r - c) * book
        factor /= 1 + c
        pv += excess * factor
        rows.append({"book": book, "roe": r, "excess": excess})
        book *= 1 + r * (1 - p)
    term = (justified_pb(roe_term, cost_term, g_term) - 1) * book
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
