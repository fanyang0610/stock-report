"""Each market's implied return (stage 15; PLAN.md "Valuation and target price", "Rating"): the discount rate at which
the market's members in the day's snapshot, weighted by market value, are worth their price under the model's own
cash-flow rules. This is Damodaran's implied equity risk premium ("Equity Risk Premiums", his annual update: solve for
the rate that equates the index's level to its expected cash flows) with our cash flows instead of his (five years of
analysts' growth, then today's payout for ever), so a valuation's rate and its cash flows follow one set of rules (the
review of 2026-11-13, R1). In equity terms, so banks and insurers count with the rest (dcf.fcfe):
- the market per unit of its value: book (B/P), trailing earnings (E/P) and next year's (each member's trailing
  earnings grown by its consensus growth on the consensus's own basis, the screening's fwd_growth; none: trailing);
- ROE: next year's, then its gap to the market's own 8-year median shrinks by the market's measured margin keep each
  year (value.paths' margin rule; fade.margin_keep); the book grows at the largest fifth's base rate to year 5, then in
  equal steps to stable growth by year 10 (value.paths' growth rule without a consensus excess); what the book's
  growth doesn't need is paid out;
- after year 10 the DCF's stable period: the year-10 ROE on the book in place, new capital earning the graded moat's
  return (value.moat on the market's own ROE history, weighted by today's book, faded by fade.excess_keep), then its
  cost; stable growth at the yield unless the sensitivity test lowers it (dcf.tested_growth).
The yield is the members' reporting currencies' 10-year yields weighted by value (the cash flows' currency), so the
premium is the return less it. By construction the market is at its price at this return."""

from datetime import date
from functools import lru_cache

import pandas as pd

from stockreport.research import dcf, fade, sheet, value

HISTORY_YEARS, MEDIAN_YEARS = 10, 8  # the moat's record and the ROE's own median, as for a company (value.moat, paths)


def aggregate(snap: pd.DataFrame, market: str) -> dict | None:
    """The market as one firm per unit of its value: book, trailing and next year's earnings, the yield of its
    cash flows' currencies, and its book-weighted ROE history (each member's ROE in the history tables)."""
    s = snap[(snap["mcap"] > 0) & snap["ey"].notna() & snap["by"].notna()]
    if s.empty:
        return None
    w = s["mcap"] / s["mcap"].sum()
    growth = s["fwd_growth"].where(s["ey"] > 0).fillna(0.0)
    ccy = s["currency"] if "currency" in s else s["report_currency"] if "report_currency" in s else pd.Series("CNY", index=s.index)
    yields = {c: value.rate(value.RATE_OF.get(c, "us"))[0] for c in ccy.dropna().unique()}
    t = fade.return_table(market)
    years = list(t.columns)[-HISTORY_YEARS:]
    book = pd.Series((s["mcap"] * s["by"]).where(s["by"] > 0).values, index=s["code"].values)
    roes = t.reindex(book.index)[years]
    history = pd.Series({y: float((roes[y] * book).sum() / book[roes[y].notna()].sum()) for y in years})
    return {"members": len(s), "book": float((w * s["by"]).sum()), "earnings": float((w * s["ey"]).sum()),
            "earnings_next": float((w * s["ey"] * (1 + growth)).sum()), "rf": float((w * ccy.map(yields).fillna(yields.get("USD", 0.0))).sum()),
            "roe_history": history, "covered": float(min(book[roes[y].notna()].sum() / book.sum() for y in years))}


def paths(a: dict, base: float, keep: dict) -> dict:
    """Next year's ROE moving toward its own median at the measured keep; the book's growth at the base rate."""
    roe1, target = a["earnings_next"] / a["book"], float(a["roe_history"].tail(MEDIAN_YEARS).median())
    k = keep["above" if roe1 > target else "below"]
    return {"roe": [target + (roe1 - target) * k ** t for t in range(dcf.YEARS)], "roe_target": target, "base": base}


def worth(a: dict, p: dict, r: float, excess_keep: float) -> dict:
    """The market's value per unit of its price at return r."""
    moat = value.moat(a["roe_history"], r, r, excess_keep)
    g = dcf.tested_growth(lambda x: dcf.terminal(1.0, x, r, moat["ronic"]), a["rf"])
    growth = [p["base"]] * value.CONVERGENCE + [p["base"] + (g - p["base"]) * k / (dcf.YEARS - value.CONVERGENCE)
                                                 for k in range(1, dcf.YEARS - value.CONVERGENCE + 1)]
    return dcf.fcfe(a["book"], p["roe"], growth, r, g, moat["ronic"]) | {"g": g, "moat": moat}


@lru_cache(maxsize=6)
def implied(market: str, today: date) -> dict | None:
    """{r, rf, erp, ...}: the market's implied return and premium today; None without a snapshot or a solution (the
    caller falls back to Damodaran's published premium, said)."""
    a = aggregate(sheet.snapshot(market, today), market)
    if a is None:
        return None
    base = fade.base_rates(market, float("inf"), {}).get("fifth_recent")  # the largest fifth: the market is its largest
    p = paths(a, base if base is not None else a["rf"], fade.margin_keep(market))
    keep = fade.excess_keep(market)
    r = dcf.solve(lambda x: -worth(a, p, x, keep)["value"], -1.0, a["rf"] + 0.005, 0.40)
    if r is None:
        return None
    w = worth(a, p, r, keep)
    snap = sheet.snapshot(market, today)
    return {"r": r, "rf": a["rf"], "erp": r - a["rf"], "members": a["members"], "covered": a["covered"],
            "snapshot": snap["snap_date"].iloc[0], "pb": 1 / a["book"], "pe": 1 / a["earnings"] if a["earnings"] > 0 else None,
            "pe_next": 1 / a["earnings_next"] if a["earnings_next"] > 0 else None, "roe_next": p["roe"][0],
            "roe_median": p["roe_target"], "roe_history": {str(k): v for k, v in a["roe_history"].items()},
            "base_growth": p["base"], "g": w["g"], "moat_track": w["moat"]["track"], "moat_edge": w["moat"]["edge"],
            "pv_terminal_share": w["pv_terminal"] / w["value"], "value": w["value"]}
