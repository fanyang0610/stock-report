"""Each market's implied return (stage 15; PLAN.md "Valuation and target price", "Rating"): the discount rate at which
the market's members in the day's snapshot, weighted by market value, are worth their price under the model's own
cash-flow rules. This is Damodaran's implied equity risk premium ("Equity Risk Premiums", his annual update: solve for
the rate that equates the index's level to its expected cash flows) with our cash flows instead of his (five years of
analysts' growth, then today's payout for ever), so a valuation's rate and its cash flows follow one set of rules (the
review of 2026-11-13, R1). In equity terms, so banks and insurers count with the rest (dcf.fcfe):
- the market per unit of its value: book (B/P), trailing earnings (E/P) and next year's (each member's trailing
  earnings grown by its consensus growth on the consensus's own basis, the screening's fwd_growth; none: trailing);
- ROE: next year's, then its gap to the market's own 8-year median shrinks by the market's measured margin keep each
  year (value.paths' margin rule; fade.margin_keep); the book grows at the largest fifth's base rate plus the measured
  share of its excess revenue growth over it kept each year (the book-weighted trailing revenue growth of the members
  valued by a DCF, on their share of the book; fade.growth_shares, the members' DCFs carry theirs: stage 20) to year 5, then in equal steps to stable growth by
  year 10 (value.paths' growth rule); what the book's growth doesn't need is paid out;
- after year 10 the DCF's stable period: the year-10 ROE on the book in place, new capital earning the graded moat's
  return (value.moat on the market's own ROE history, weighted by today's book, faded by fade.excess_keep), then its
  cost; stable growth at the yield unless the sensitivity test lowers it (dcf.tested_growth).
The yield is the members' reporting currencies' 10-year yields weighted by value (the cash flows' currency), so the
premium is the return less it. By construction the market is at its price at this return. Since stage 18 a stock is
set against its group's (select: financials or not, and in Hong Kong China-based or not), each at its own price."""

from datetime import date
from functools import lru_cache

import pandas as pd

from stockreport.research import damodaran, dcf, fade, sheet, value

HISTORY_YEARS, MEDIAN_YEARS = 10, 8  # the moat's record and the ROE's own median, as for a company (value.moat, paths)


def aggregate(snap: pd.DataFrame, market: str) -> dict | None:
    """The market as one firm per unit of its value: book, trailing and next year's earnings, the yield of its
    cash flows' currencies, and its book-weighted ROE history (each member's ROE in the history tables)."""
    s = snap[(snap["mcap"] > 0) & snap["ey"].notna() & snap["by"].notna()]
    if s.empty:
        return None
    w = s["mcap"] / s["mcap"].sum()
    growth = s["fwd_growth"].where(s["ey"] > 0).fillna(0.0)
    bw = (s["mcap"] * s["by"]).where(s["by"] > 0)  # book weights: the aggregate's revenue analog is its book
    rg = s["rev_growth"].clip(-0.5, 2.0) if "rev_growth" in s else pd.Series(float("nan"), index=s.index)
    dcf_form = ~s["financial"].astype(bool) if "financial" in s else pd.Series(True, index=s.index)  # banks, insurers
    ok = rg.notna() & bw.notna() & dcf_form  # and brokers carry no excess growth (their book grows at the base rate)
    ccy = s["currency"] if "currency" in s else s["report_currency"] if "report_currency" in s else pd.Series("CNY", index=s.index)
    yields = {c: value.yield_of(c)[0] for c in ccy.dropna().unique()}
    t = fade.return_table(market)
    years = list(t.columns)[-HISTORY_YEARS:]
    book = pd.Series((s["mcap"] * s["by"]).where(s["by"] > 0).values, index=s["code"].values)
    roes = t.reindex(book.index)[years]
    history = pd.Series({y: float((roes[y] * book).sum() / book[roes[y].notna()].sum()) for y in years})
    return {"members": len(s), "book": float((w * s["by"]).sum()), "earnings": float((w * s["ey"]).sum()),
            "earnings_next": float((w * s["ey"] * (1 + growth)).sum()), "rf": float((w * ccy.map(yields).fillna(yields.get("USD", 0.0))).sum()),
            "roe_history": history, "covered": float(min(book[roes[y].notna()].sum() / book.sum() for y in years)),
            "revenue_growth": float((rg[ok] * bw[ok]).sum() / bw[ok].sum()) if ok.any() else None,
            "growth_share": float(bw[ok].sum() / bw.sum()) if ok.any() else 0.0}


def paths(a: dict, base: float, keep: dict, shares: list[float] | None = None) -> dict:
    """Next year's ROE moving toward its own median at the measured keep; the book's growth at the base rate plus the
    measured share of the members' excess revenue growth over it kept in each of the next 5 years (stage 20: the
    members' DCFs carry theirs, value.paths; `shares`: fade.growth_shares, on one year's excess), for the part of the
    book in members valued by a DCF (a bank's model carries none: rating.book_growth). The members' DCFs start from
    the consensus's revenue growth, which the snapshot doesn't carry: their trailing growth here, the basis the shares
    were measured on."""
    roe1, target = a["earnings_next"] / a["book"], float(a["roe_history"].tail(MEDIAN_YEARS).median())
    k = keep["above" if roe1 > target else "below"]
    excess = (a["revenue_growth"] - base) * a["growth_share"] if a.get("revenue_growth") is not None and shares else 0.0
    return {"roe": [target + (roe1 - target) * k ** t for t in range(dcf.YEARS)], "roe_target": target, "base": base,
            "early": [base + x * excess for x in (shares or [0.0] * value.CONVERGENCE)], "excess": excess}


def worth(a: dict, p: dict, r: float, excess_keep: float) -> dict:
    """The market's value per unit of its price at return r."""
    moat = value.moat(a["roe_history"], r, r, excess_keep)
    g = dcf.tested_growth(lambda x: dcf.terminal(1.0, x, r, moat["ronic"]), a["rf"])
    g5 = p["early"][-1]
    growth = p["early"] + [g5 + (g - g5) * k / (dcf.YEARS - value.CONVERGENCE) for k in range(1, dcf.YEARS - value.CONVERGENCE + 1)]
    return dcf.fcfe(a["book"], p["roe"], growth, r, g, moat["ronic"]) | {"g": g, "moat": moat}


def china(snap: pd.DataFrame, market: str) -> pd.Series:
    """China-based members (value.group_of's test on each): Damodaran's country (his company list) is China, or
    they report in CNY: red chips such as CNOOC, CITIC and China Resources Land are incorporated in Hong Kong, where
    he lists them, but their business and cash flows are the mainland's."""
    co = damodaran.load("companies").query("market == @market").drop_duplicates("code").set_index("code")["country"]
    ccy = snap["report_currency"] if "report_currency" in snap else snap["currency"] if "currency" in snap else None
    cny = ccy.eq("CNY") if ccy is not None else pd.Series(market == "cn", index=snap.index)
    return snap["code"].map(co).eq("China") | cny


def select(snap: pd.DataFrame, market: str, financial: bool | None, home: bool | None) -> pd.DataFrame:
    """The members of a stock's group (stage 18): those valued in its form (the screening's financials, whose balance
    sheet is the product, against the rest) and, in Hong Kong, of its home (China-based or not); None: all."""
    keep = pd.Series(True, index=snap.index)
    if financial is not None:
        keep &= snap["financial"].astype(bool) == financial
    if home is not None:
        keep &= china(snap, market) == home
    return snap[keep]


@lru_cache(maxsize=24)
def implied(market: str, today: date, financial: bool | None = None, home: bool | None = None) -> dict | None:
    """{r, rf, erp, ...}: the implied return and premium today of the market's members in a stock's group (select; all
    by default), so a stock is set against the companies valued in its form and priced with its home's risk: on
    2026-11-14 CN's financials implied 12.8% and the rest 6.3%, HK's China-based members 11.5% and the rest 7.7%
    (the review of stage 15; Gebhardt, Lee and Swaminathan 2001: industry membership is one of the four things a
    firm's implied cost of capital depends on). A group under Damodaran's floor for an average (10 members) takes its
    form's across homes, then the market's. None without a snapshot or a solution (the caller falls back to Damodaran's
    published premium, said)."""
    snap = sheet.snapshot(market, today)
    s = select(snap, market, financial, home) if len(snap) else snap
    if (financial, home) != (None, None) and (len(s) < damodaran.MIN_FIRMS):
        return implied(market, today, financial, None) if home is not None else implied(market, today)
    a = aggregate(s, market)
    if a is None:
        return None
    base = fade.base_rates(market, float("inf"), {}).get("fifth_recent")  # the largest fifth: the market is its largest
    shares = fade.growth_shares(market, 1) if a["revenue_growth"] is not None else None
    p = paths(a, base if base is not None else a["rf"], fade.margin_keep(market), shares)
    keep = fade.excess_keep(market)
    r = dcf.solve(lambda x: -worth(a, p, x, keep)["value"], -1.0, a["rf"] + 0.005, 0.40)
    if r is None:
        return None
    w = worth(a, p, r, keep)
    return {"r": r, "rf": a["rf"], "erp": r - a["rf"], "members": a["members"], "covered": a["covered"],
            "financial": financial, "china": home, "country": "China" if home else value.COUNTRY[market],
            "snapshot": snap["snap_date"].iloc[0], "pb": 1 / a["book"], "pe": 1 / a["earnings"] if a["earnings"] > 0 else None,
            "pe_next": 1 / a["earnings_next"] if a["earnings_next"] > 0 else None, "roe_next": p["roe"][0],
            "roe_median": p["roe_target"], "roe_history": {str(k): v for k, v in a["roe_history"].items()},
            "base_growth": p["base"], "excess_growth": p["excess"], "g": w["g"], "moat_track": w["moat"]["track"], "moat_edge": w["moat"]["edge"],
            "pv_terminal_share": w["pv_terminal"] / w["value"], "value": w["value"]}
