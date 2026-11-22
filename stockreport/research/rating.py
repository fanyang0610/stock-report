"""Research stage 10, part 2 (stage 15's rating): each method's value and 12-month target, the main method's fair value,
bear / base / bull, the rating (judge.py), what today's price assumes (reverse DCF, with base rates, and the return it
implies), the sensitivity grid and the comparison with the street; saved as data/research/<market>/<code>/valuation.json
(`research CODE --value`).
- Fair value a year from now: the type's main method (value.METHODS, the first that runs), an absolute method's value
  today rolled forward 12 months at the cost of equity less the dividend yield; the other methods are cross-checks
  (a multiple applied to the next 12 months' consensus: a normal trailing multiple a year from now).
- Rates (stage 15): the listing market's implied premium (market.py), so the market's members, priced like the market,
  come out at their price; Damodaran's published premium gives the absolute view, one line beside it.
- The 12-month target: the price a year on if it earns its cost of equity and closes a third of its (log) gap to the
  fair value, as the gap closes over about three years (CONVERGE); bear and bull the same way.
- Bear and bull: the first forecast year's analysts' low and high (Yahoo; CN: the brokers' reports) and the long-run
  margin (financials: ROE) one standard deviation of the company's own 10 years lower and higher, at most the margin's
  own size.
- 不评级 / 评级暂停: pre-revenue; a non-standard audit opinion or a hard red flag of the results review (investigation,
  going concern: no target); a pending takeover suspends the rating."""

import logging
from datetime import date

import numpy as np

from stockreport import review
from stockreport.fetch import yahoo
from stockreport.research import dcf, fade, folder, judge, load, save, sheet, stamp, texts, value
from stockreport.research import market as markets
from stockreport.research.checks import FINANCIAL, cagr

log = logging.getLogger(__name__)
ABSOLUTE = {"dcf", "dcf_normal", "excess_return", "pb_roe", "ddm"}  # the methods that read a discount rate
CONVERGE = 3  # years for the price to reach fair value: Morningstar's "generally within three years" (Equity Research
# Methodology, 2020); value-to-price predicts abnormal returns for up to three years (Ali, Hwang and Trombley 2003)
TABLE_CURRENCY = {"cn": "CNY", "us": "USD", "hk": "CNY"}  # Eastmoney's HK amounts are CNY (stage 9)
NAMES = {"dcf": "DCF (FCFF, 10 years)", "dcf_normal": "DCF, normalized on capital", "pe_own": "P/E against own history",
         "pe_peers": "P/E against peers", "pe_normal": "own P/E on normalized EPS", "pb_own": "P/B against own history",
         "pb_roe": "excess-return model on average ROE", "evs_peers": "EV/Sales against peers", "peg_peers": "PEG against peers",
         "ddm": "dividend discount (two-stage)", "yield_own": "yield against own 5-year average",
         "excess_return": "excess-return model on book equity"}


def methods(f: dict, k: dict, kind: str, cons: dict, today: date, eps_factor: float = 1.0, shift: int = 0,
            only: set | None = None) -> dict:
    """Each method of the type's playbook (or `only` these): {name: {value (today), target (12 months), ...}} per
    share, quote currency."""
    v, t, own, w = f["valuation"], f["valuation"]["ttm"], f["valuation"]["own_history"], set(value.METHODS[kind]) & (only or set(value.METHODS[kind]))
    shares, fx, coe, g = k["shares"], k["fx"], k["cost_equity"], k["g"]
    dps = value.next_dividend(f, k, cons) * eps_factor
    roll = 1 + coe - dps / v["price"]
    eps = [e * eps_factor for e in cons["eps"]]
    eps_ntm = (cons["ntm_eps"] or (t["ni"] or 0) / shares) * eps_factor
    book, payout, out = v["book_common"], value.payout_5y(f) or f["checks"]["income"].get("payout") or 0.0, {}
    fwd_book = book + eps_ntm * shares * (1 - payout) if book else None
    per = lambda total: max(total, 0.0) / shares / fx
    window = "median" if kind == "cyclical" else "median_5y"  # a full cycle for a cyclical; else brokers' latest 5 years
    q = k.get("quantile")  # a scenario: the multiples' quartile in place of their median (stage 18)
    pick = lambda key, at: own[key].get(at.replace("median", f"q{round(q * 100)}") if q else at)
    multiple = lambda key: pick(key, window) or pick(key, "median")
    peers = value.peer_medians(f, today, q or 0.5) if w & {"pe_peers", "evs_peers", "peg_peers"} else {}
    case = lambda m: value.moat_case(m, k.get("moat_case"))  # a scenario: the moat off or on
    quartiles = lambda h: (h.quantile(0.75) - h.quantile(0.25)) / 2  # half the interquartile range: a quartile's move
    if {"dcf", "dcf_normal"} & set(w):
        roic = case(value.moat(value.history(f, "roic", 10), k["wacc"], k["stable_wacc"], k["excess_keep"]))
        g_dcf = dcf.tested_growth(lambda x: dcf.terminal(1.0, x, k["stable_wacc"], roic["ronic"]), k["g"])
        path = value.paths(f, k, kind, cons | {"eps": eps}, g_dcf)
        m = value.history(f, "ebit_margin", 10)
        peers_q = k.get("mature_quartiles") if path["margin_source"] == "profitable peers' median" else None
        if shift and (len(m) >= 3 or peers_q):  # a scenario: the long-run margin at its source's 25th / 75th percentile:
            # its own 10 years', or the mature peers' whose median it takes (a young firm's losses say how it got here,
            # not where its margin settles: Damodaran's target margin)
            d = min((peers_q[1] - peers_q[0]) / 2 if peers_q else quartiles(m), abs(path["target_margin"])) * shift
            path["margin"] = [x + d * min(i + 1, value.CONVERGENCE) / value.CONVERGENCE for i, x in enumerate(path["margin"])]
        s2c, s2c_source = (path["sales_to_capital"], "normal: new capital earns the cycle's average return") \
            if path.get("sales_to_capital") else value.sales_to_capital(f, k, path["margin_source"])
        x, res = value.dcf_value(f, k, path, s2c, roic["ronic"], g_term=g_dcf)
        x = max(x, 0.0)
        out["dcf_normal" if kind == "cyclical" else "dcf"] = {
            "value": x, "target": x * roll, "path": path, "sales_to_capital": s2c, "s2c_source": s2c_source,
            **year10_return(f, k, res),
            "moat": roic, "g": g_dcf, "terminal_multiple": dcf.terminal(1.0, g_dcf, k["stable_wacc"], roic["ronic"]),
            "years": {key: res[key] for key in ("revenue", "ebit", "nopat", "reinvestment", "fcff")},
            "pv_terminal_share": res["pv_terminal"] / res["operating"] if res["operating"] > 0 else None}
    if "pe_own" in w and multiple("pe") and eps_ntm > 0:
        out["pe_own"] = {"multiple": multiple("pe"), "target": multiple("pe") * eps_ntm / fx}
    if "pe_peers" in w and peers.get("pe") and not np.isnan(peers["pe"]) and eps_ntm > 0:
        out["pe_peers"] = {"multiple": peers["pe"], "group": peers["group"], "count": peers["count"],
                           "target": peers["pe"] * eps_ntm / fx}
    if "pb_own" in w and multiple("pb") and fwd_book:
        out["pb_own"] = {"multiple": multiple("pb"), "target": multiple("pb") * fwd_book / shares / fx}
    if "evs_peers" in w and peers.get("ev_sales") and not np.isnan(peers["ev_sales"]):
        rev = cons["ntm_revenue"] or t["revenue"] * (1 + (v.get("eps_growth_consensus") or 0))
        ev = peers["ev_sales"] * rev * eps_factor
        out["evs_peers"] = {"multiple": peers["ev_sales"], "target": per(ev - k["debt"] - k["minority"] + k["cash"])}
    growth = v.get("eps_growth_consensus")
    if "peg_peers" in w and peers.get("peg") and not np.isnan(peers["peg"]) and growth and growth > 0 and eps_ntm > 0:
        out["peg_peers"] = {"multiple": peers["peg"], "pe": peers["peg"] * growth * 100,
                            "target": peers["peg"] * growth * 100 * eps_ntm / fx}
    income = f["checks"]["income"]
    if "yield_own" in w and income.get("yield_avg_5y") and dps:
        out["yield_own"] = {"yield": income["yield_avg_5y"], "dividend": dps, "target": dps / income["yield_avg_5y"]}
    if "ddm" in w and dps:
        g1 = cagr(eps[-1], eps[0], len(eps) - 1) if len(eps) > 1 else income.get("dps_cagr_5y")
        g1 = g1 if g1 is not None else 0.0
        gt = min(dcf.tested_growth(lambda x: 1 / (coe - x), g), max(g1, 0.0))  # a fixed payout: r - g >= 5 points
        cover = None if kind == "reit" else judge.cover(f)  # income-investment: the dividend free cash flow pays
        paid = dps * min(max(cover, 0.0), 1.0) if cover is not None else dps
        x = dcf.ddm(paid * fx / (1 + g1), g1, 5, coe, gt) / fx  # next year's dividend, then growing at g1 to year 5
        out["ddm"] = {"value": x, "target": x * roll, "dividend": paid, "dividend_consensus": dps, "fcf_cover": cover,
                      "growth_5y": g1, "growth_stable": gt}
    roe_hist = value.history(f, "roe", 10)
    def book_growth(g_end: float) -> list[float]:
        """The book's growth: the market's aggregate's path (market.worth), the base rate of companies of this size to
        year 5, then in equal steps to stable growth by year 10; the profit it doesn't need is paid out."""
        b0 = k.get("base_growth") if k.get("base_growth") is not None else g_end
        return [b0] * value.CONVERGENCE + [b0 + (g_end - b0) * j / (dcf.YEARS - value.CONVERGENCE)
                                            for j in range(1, dcf.YEARS - value.CONVERGENCE + 1)]
    def on_book(roes: list[float], moat: dict, d: float, n: int) -> dict:
        """Book equity plus its excess returns: the ROE path to year 10, then the book in place at the year-10 ROE and
        new capital at the graded moat's return, then the cost. The bear / bull case moves the long-run ROE by d, from
        the last of the n given years (none: every year)."""
        roes = [r + d * min(max(i + 1 - n, 0) / (dcf.YEARS - n), 1.0) if n else r + d for i, r in enumerate(roes)]
        fade_ = [r + d for r in moat["ronic"]]
        g_er = dcf.tested_growth(lambda x: dcf.terminal(1.0, x, k["stable_cost"], fade_), g)
        growth = book_growth(g_er)
        res = dcf.excess_return(book, roes, growth, dcf.steps(coe, k["stable_cost"]), fade_, k["stable_cost"], g_er)
        x = per(res["value"])
        return {"value": x, "target": x * roll, "roe": roes, "roe_term": roes[-1], "fade": fade_, "moat": moat, "g": g_er,
                "growth": growth, "payout": [y["payout"] for y in res["years"]],
                "pv_terminal_share": res["pv_terminal"] / res["value"] if res["value"] else None}
    spread = lambda base: min(quartiles(roe_hist), abs(base)) * shift if shift and len(roe_hist) >= 3 else 0.0
    if "excess_return" in w and book and eps:
        moat = case(value.moat(roe_hist, coe, k["stable_cost"], k["excess_keep"]))  # graded, as the DCF's return on capital
        roes, b = [], book
        for e, gb in zip(eps, book_growth(g)):
            roes.append(e * shares / b)
            b *= 1 + gb
        n, own = len(roes), value.history(f, "roe", 8)  # then toward its own 8-year median at the market's measured
        target = float(own.median()) if len(own) >= value.MOAT_YEARS else roes[-1]  # keep, as the market's aggregate
        keep = k["margin_keep"]["above" if roes[-1] > target else "below"]  # (market.paths) and a margin (value.paths)
        roes += [target + (roes[-1] - target) * keep ** (i - n) for i in range(n + 1, dcf.YEARS + 1)]
        out["excess_return"] = on_book(roes, moat, spread(target), n)
    if "pb_roe" in w and book:  # the same model on the cycle's average ROE in place of the consensus (stage 15: it
        # capitalized the average for ever before; stage 20: the average is kept, as the DCF keeps a normal year's)
        hist = value.history(f, "roe", 10 if kind == "cyclical" else 8)
        if len(hist):
            roe, moat = float(hist.mean()), case(value.moat(hist, coe, k["stable_cost"], k["excess_keep"]))
            x = on_book([roe] * dcf.YEARS, moat, spread(roe), 0)  # the cycle's average, as a normal year's return
            extra = excess(eps, roe * book / shares, coe, 1)  # the consensus years' earnings above (below) the average
            x["value"] = max(x["value"] + extra / fx, 0.0)
            out["pb_roe"] = x | {"roe_avg": roe, "excess_earnings": extra / fx, "target": x["value"] * roll}
    if "pe_normal" in w and multiple("pe"):
        nm = value.history(f, "net_margin", 10).mean()
        year = value.normal(f, k)  # the normal year's revenue (stage 18; the trailing revenue carries the cycle)
        if not np.isnan(nm) and nm > 0:
            e = (year["revenue"] if year else t["revenue"]) * nm / shares * eps_factor
            extra = excess(eps, e, coe, 0)
            out["pe_normal"] = {"multiple": multiple("pe"), "eps": e, "net_margin": nm, "excess_earnings": extra / fx,
                                "target": max(multiple("pe") * e + extra, 0.0) / fx}
    return out


def excess(eps: list[float], normal: float, cost: float, start: int) -> float:
    """The consensus years' earnings per share above (or below) normal, discounted from `start` years: residual
    income that accrues to holders, so a normalized value of a cyclical at a peak (a trough) adds (subtracts) it."""
    return sum((e - normal) / (1 + cost) ** (i + start) for i, e in enumerate(eps))


def converge(fair: float, carry: float) -> float:
    """The price a year from now: `carry` (today's price earning its cost of equity, less the dividend) closing a third
    of its log gap to the fair value a year from now, as the gap closes over CONVERGE years. Fair values are never
    negative (each method's floor is 0), and a bear value of 0 stays 0, the limit of the log gap."""
    return carry * (fair / carry) ** (1 / CONVERGE) if fair > 0 and carry > 0 else fair


def flags(f: dict) -> tuple[str | None, str | None]:
    """(status, reason) when no rating can be given: 不评级 or 评级暂停."""
    if f["kind"] not in FINANCIAL and f["kind"] != "reit" and f["market"] != "us" and value.PRE_REVENUE.search(str(f["name"]).upper()):
        return "不评级", "pre-revenue: a pipeline can't be valued from free data"
    op = f.get("audit_opinion")
    if op and "标准无保留" not in op and "unqualified" not in op.lower():
        return "不评级", f"audit opinion: {op}"
    hard = {kind for kind, spec in review.KINDS.items() if spec[1]}
    for x in (review.cached(f["market"], f["code"]) or {}).get("findings") or []:
        if x.get("hard") and x.get("kind") == "takeover":
            return "评级暂停", f"pending takeover: {x.get('quote')}"
        if x.get("hard") and x.get("kind") in hard:
            return "不评级", f"{x.get('words')}: {x.get('quote')}"
    return None, None


def reverse(f: dict, k: dict, kind: str, cons: dict, found: dict, price: float | None = None, margin: bool | None = None) -> dict:
    """What today's price (or another value per share today: the street's target discounted back 12 months) assumes:
    the revenue growth in years 1-5 (then fading as in the base case) at which the DCF equals it, and the cost of
    capital; a loss-maker's long-run margin (with `margin`, any DCF's); for financials the ROE it implies at our cost of
    equity, and the cost of equity it implies at the next year's ROE; for dividend payers the 5-year dividend growth."""
    v, out = f["valuation"], {}
    price, margin = price or v["price"], kind == "loss_making" if margin is None else margin
    d = found.get("dcf") or found.get("dcf_normal")
    if d:
        ronic, g = d["moat"]["ronic"], d["g"]
        def at(g5):
            path = d["path"] | {"growth": dcf.steps(g5, g)}
            return value.dcf_value(f, k, path, d["sales_to_capital"], ronic, g_term=g)[0]
        if at(-0.3) <= at(1.0):
            out["implied_growth_5y"] = dcf.solve(at, price, -0.3, 1.0)
        else:  # growth destroys value when the return on new capital is below its cost
            out["implied_growth_5y"] = dcf.solve(lambda g5: -at(g5), -price, -0.3, 1.0)
            out["note"] = "the return on new capital is below its cost: faster growth lowers the value"
        at_cost = lambda c: value.dcf_value(f, k, d["path"], d["sales_to_capital"], ronic, c, g)[0]
        shift = dcf.solve(lambda c: -at_cost(c), -price, -0.045, 0.25)  # the cost of capital the price implies
        out["implied_wacc"] = None if shift is None else k["wacc"] + shift
        if margin:  # the long-run margin the price assumes, the base case's growth
            def margin_at(m):
                p = d["path"]
                return value.dcf_value(f, k, p | {"margin": [x + (m - p["target_margin"]) * min(i + 1, value.CONVERGENCE)
                                                             / value.CONVERGENCE for i, x in enumerate(p["margin"])]},
                                       d["sales_to_capital"], ronic, g_term=g)[0]
            out["implied_margin"] = dcf.solve(margin_at, price, -0.5, 0.9)
    if kind in FINANCIAL and v["pb"]:
        roe = cons["eps"][0] * k["shares"] / v["book_common"] if cons["eps"] else f["summary"].get("roe_latest")
        pb = v["pb"] * price / v["price"]
        g = (found.get("excess_return") or found.get("pb_roe") or {}).get("g", k["g"])  # the method's stable growth
        if roe:
            out["implied_roe"] = g + pb * (k["cost_equity"] - g)
            out["implied_cost_equity"] = dcf.implied_cost_equity(roe, pb, g)
            out["roe_next"] = roe
    if found.get("ddm"):
        gt, d1 = found["ddm"]["growth_stable"], found["ddm"]["dividend"] * k["fx"]
        out["implied_dividend_growth_5y"] = dcf.solve(lambda g1: dcf.ddm(d1 / (1 + g1), g1, 5, k["cost_equity"], gt) / k["fx"],
                                                      price, -0.5, 1.0)
    return out


def sensitivity(f: dict, k: dict, found: dict) -> dict:
    """The absolute method's value per share across the cost of capital (-1, 0, +1 point) and its stable growth (-0.5,
    0, +0.5 point)."""
    costs, around = [-0.01, 0.0, 0.01], lambda g: [g - 0.005, g, g + 0.005]
    d = found.get("dcf") or found.get("dcf_normal")
    if d:
        fn = lambda c, g: value.dcf_value(f, k, d["path"], d["sales_to_capital"], d["moat"]["ronic"], c, g)[0]
        return {"method": "dcf", "cost_shift": costs, "growth": around(d["g"]), "values": dcf.grid(fn, costs, around(d["g"]))}
    if found.get("ddm"):
        x = found["ddm"]
        growths = around(x["growth_stable"])
        d0 = x["dividend"] * k["fx"] / (1 + x["growth_5y"])
        fn = lambda c, g: dcf.ddm(d0, x["growth_5y"], 5, k["cost_equity"] + c, g) / k["fx"]
        return {"method": "ddm", "cost_shift": costs, "growth": growths, "values": dcf.grid(fn, costs, growths)}
    return {}


def main_of(found: dict, order: list[str]) -> str | None:
    """The type's first method with a value: a DCF whose equity value is negative (counted as 0: limited liability)
    can't give a fair value, so the next method stands in (the report names the one skipped)."""
    return next((m for m in order if ((found.get(m) or {}).get("target") or 0) > 0), None)


def at_cost(k: dict, r: float) -> dict:
    """The rates at an equity return r (a beta of 1, as the rating's): the stable cost too, the WACC on the same debt in
    every year."""
    de, kd = k["debt_to_equity"], k["cost_debt"]
    wacc = r if k["wacc"] == k["cost_equity"] or kd is None else (r + de * kd * (1 - k["tax_marginal"])) / (1 + de)
    wacc = None if k["wacc"] is None else wacc
    return k | {"cost_equity": r, "stable_cost": r, "wacc": wacc, "stable_wacc": wacc}


def implied(f: dict, k: dict, kind: str, cons: dict, today: date, main: str) -> float | None:
    """The return today's price implies under the main method: the equity return at which its value today equals the
    price, every rule that reads the cost (the moat's hurdle, the tested growth, the WACC) at that return, as the
    market's own implied return is solved (market.py). None when the price is above the value even at 1%, or when a
    multiple stands in as the main method (it reads no rate)."""
    if main not in ABSOLUTE:
        return None
    worth = lambda r: (methods(f, at_cost(k, r), kind, cons, today, only={main}).get(main) or {}).get("value") or 0.0
    r = dcf.solve(lambda x: -worth(x), -f["valuation"]["price"], 0.01, 0.40, tol=1e-5)
    return r


def typed(f: dict) -> tuple[str, str, dict, float | None]:
    """The type (value.kind_of) on the fact sheet's figures and its market's norm, the last 5-year window's median
    growth, with the base rates of companies of its size and its revenue in the history tables' currency."""
    market, t = f["market"], f["valuation"]["ttm"]
    rev = value.convert(yahoo.load_fx(), t["revenue"], f["valuation"]["report_currency"], TABLE_CURRENCY[market]) if t["revenue"] else None
    rates = fade.base_rates(market, rev, {}) if rev else {}
    return *value.kind_of(f, {"ebit": sheet.ebit(market, t)}, rates.get("recent_median")), rates, rev


def years(f: dict) -> int:
    """The fact sheet's history in years: its latest unbroken run of fiscal years with revenue (a row a year after the
    last, from the latest back), so a gap (中国移动's A line: 2010-11, then 2018-25) or a year whose revenue reads 0 (百济神州
    A's 2025, 中国石油 H's 2017) doesn't count as history the type's tests can read."""
    n, last = 0, None
    for x in reversed(f["history"]):
        y = int(x["period"][:4])
        if not (x.get("revenue") or 0) > 0 or (last is not None and y != last - 1):
            break
        n, last = n + 1, y
    return n


def one_type(f: dict, today: date) -> tuple[str, str] | None:
    """An A+H issuer's type from the line whose fact sheet has the longer history (years()), typed as that line is:
    one company with one set of accounts is one type (Damodaran's playbook types the business, not the listing).
    中国海油's A line, listed in 2022, has 8 years from 2018 and was ordinary; its H line's 10 years carry 2016's loss
    year, the cycle's low, and type it cyclical: its two fair values were 2.4 times apart. At equal length the A line's:
    the type's tests read the operating margin, and the A line's statements (Eastmoney's CN template) give each line the
    operating profit leaves out its own row (investment income, fair-value changes: "Valuation and target price"),
    where the HK template has no row for fair-value changes, so its profit keeps them; its consensus and dividends
    stand for both lines since stage 19. None
    when no other line's history is longer (or the line is the A line at equal length), or its fact sheet is of another
    kind (a financial, a REIT) or can't be built."""
    from stockreport.research import facts as fact_sheet
    if f["market"] not in ("cn", "hk"):
        return None
    for o in f.get("other_listings") or []:
        if o["market"] not in ("cn", "hk"):
            continue
        try:
            path = folder(o["market"], fact_sheet.normal(o["market"], o["code"])) / "facts.json"
            of = load(path) if path.exists() and load(path)["built"][:10] == today.isoformat() else \
                fact_sheet.build(o["market"], o["code"], today)
        except Exception as e:
            log.warning("%s: its %s line %s couldn't be typed: %s", f["code"], o["market"].upper(), o["code"], e)
            continue
        n, mine = years(of), years(f)
        if of["kind"] == f["kind"] and (n > mine or n == mine and o["market"] == "cn"):
            kind, why, _, _ = typed(of)
            return kind, (f"its {o['market'].upper()} line's " + ("longer history" if n > mine else "type at equal history") +
                          f" ({n} years): {why}")
    return None


def build(market: str, code: str, today: date | None = None) -> dict:
    from stockreport.research import facts as fact_sheet
    today = today or date.today()
    path = folder(market, fact_sheet.normal(market, code)) / "facts.json"
    f = load(path) if path.exists() and load(path)["built"][:10] == today.isoformat() else fact_sheet.build(market, code, today)
    priced, (fin, home) = value.priced_in(f), value.group_of(f)
    k, v = value.inputs(f, markets.implied(priced, today, fin, home)), f["valuation"]
    k["groups"] = {key: (markets.implied(priced, today, key == "financial", home) or {}).get("r")  # page 1: the gap between
                   for key in ("financial", "other")}  # the forms, so the sector view is said, not hidden in every rating
    pm = value.peer_medians(f, today)  # the young's target margin (value.paths) and its quartiles (the scenarios)
    k["mature_margin"], k["mature_quartiles"] = pm.get("mature_margin"), pm.get("mature_quartiles")
    kind, why, rates, cur_rev = typed(f)
    kind, why = one_type(f, today) or (kind, why)
    k["base_growth"] = rates.get("fifth_recent")  # companies of this size now: growth beyond the consensus (value.paths)
    k |= {"growth_shares": fade.growth_shares(market, 1), "trend_shares": fade.growth_shares(market, 3),
          "margin_keep": fade.margin_keep(market), "excess_keep": fade.excess_keep(market)}  # stage 14's measured rates
    cons = value.consensus_years(f, k, today)
    status, reason = flags(f) if kind != "pre_revenue" else ("不评级", why)
    out = {"code": f["code"], "market": market, "name": f["name"], "built": stamp(), "price": v["price"],
           "currency": v["quote_currency"], "type": kind, "type_reason": why, "inputs": k, "consensus": cons}
    found = {} if status == "不评级" else methods(f, k, kind, cons, today)
    order, fcfe_payout = judge.main_order(f, kind)  # an income stock paying far from its FCFE: the FCFE model
    main = main_of(found, order)
    if main is None or status:
        return finish(out | {"rating": status or "不评级", "reason": reason or "no method could value it", "methods": found})
    target, price = found[main]["target"], v["price"]
    def at(e: float = 1.0, s: int = 0, **scenario) -> float:  # the main method with one input moved; a case it can't
        x = (methods(f, k | scenario, kind, cons, today, e, s, only={main}).get(main) or {}).get("target")  # value: the
        return target if x is None else x  # base (a value of 0 stands)
    lo, hi = cons["range"] or (1.0, 1.0)
    q = rates.get("fifth_recent_quartiles") if k.get("base_growth") is not None else None
    cases = {"analysts": (at(lo), at(hi)), "margin": (at(s=-1), at(s=+1)), "moat": (at(moat_case="off"), at(moat_case="on")),
             "growth": (at(base_growth=q[0]), at(base_growth=q[1])) if q else (target, target),
             "multiple": (at(quantile=0.25), at(quantile=0.75)) if main not in ABSOLUTE else (target, target)}
    bear, bull = judge.scenarios(target, cases)
    dividend = value.next_dividend(f, k, cons)
    acts = judge.checks(f, kind)
    u = judge.uncertainty(target, bear, bull, bool(acts["widen"]), k["market_return"])
    j = judge.judge(main, found, order, price, dividend, k["market_return"], u, acts)
    carry = price * (1 + k["cost_equity"]) - dividend  # the price a year on, earning its cost of equity
    move = lambda x: converge(x, carry)
    target12 = move(target)
    expected = (target12 - price + dividend) / price
    d = found.get("dcf") or found.get("dcf_normal")
    ours = cagr(d["years"]["revenue"][4], v["ttm"]["revenue"], 5) if d else None
    rev = reverse(f, k, kind, cons, found) | {"implied_return": implied(f, k, kind, cons, today, main)}
    roll = 1 + k["cost_equity"] - dividend / price  # as the absolute methods' targets roll forward
    for x in j["cross"]:  # what the main method would need to reach a cross-check that rates it differently
        if x["view"] != j["main_view"]:
            x["needs"] = reverse(f, k, kind, cons, found, x["target"] / roll, margin=True)
    c = f["consensus"]
    street = c.get("target_mean") or c.get("target_yahoo")
    needs = reverse(f, k, kind, cons, found, street / roll, margin=True) if street else {}  # what the street's target assumes
    pub = k | k["published"]  # the absolute view: Damodaran's published premium
    absolute = (methods(f, pub, kind, cons, today).get(main) or {}).get("target")
    sections = None
    if judge.exposed(f):  # China-based and listed abroad: the annual report says whether it runs through a VIE
        try:
            sections = texts.sections(market, f["code"], today)
        except Exception as e:
            log.warning("%s sections for the tail scenario: %s", code, e)
    skipped = [m for m in order[:order.index(main)] if m in found]
    filings = folder(market, f["code"]) / "filings.json"
    out |= {"provisional": judge.release(f, load(filings) if filings.exists() else [], today),  # 暂定: results since
            "rating": j["rating"], "state": j["state"], "main": main, "main_skipped": skipped, "fcfe_payout": fcfe_payout, "main_view": j["main_view"], "checks_view": j["checks_view"],
            "cross": j["cross"], "acts": acts, "uncertainty": u, "scenarios": cases, "target": target12, "fair_value": target,
            "price_to_fair": (1 + k["market_return"]) / (1 + k["market_return"] + j["fair_excess"]) if 1 + k["market_return"] + j["fair_excess"] > 0 else None,
            "fair_excess": j["fair_excess"], "expected_return": expected, "excess_return": expected - k["market_return"],
            "methods": found, "bear": move(bear), "bull": move(bull), "fair_bear": bear, "fair_bull": bull,
            "market_return": k["market_return"], "dividend_next": dividend, "reverse": rev, "sensitivity": sensitivity(f, k, found),
            "absolute": {"fair_value": absolute, "cost_equity": pub["cost_equity"], "erp": pub["erp"],
                         "market_return": pub["market_return"],
                         "gap": None if absolute is None else judge.gap(absolute, price, dividend, pub["market_return"]),
                         "view": None if absolute is None else judge.view(judge.gap(absolute, price, dividend, pub["market_return"]), u, pub["market_return"])},
            "tail": judge.tail(f, sections, target, price, dividend, k["market_return"], u, j["rating"]),
            "forecast_lag": judge.lag(f),  # the price far from where the consensus moved: page 1 says the implied
            # return may move with the forecasts (sluggish forecasts)
            "base_rates": fade.base_rates(market, cur_rev, {"forecast": ours, "implied": rev.get("implied_growth_5y"),
                                                       "street": needs.get("implied_growth_5y")} |
                                          {x["method"]: (x.get("needs") or {}).get("implied_growth_5y") for x in j["cross"]}) if cur_rev else {},
            "forecast_growth_5y": ours,
            "street": {"target": street, "upside": street / price - 1 if street else None, "ours_vs_street":
                       target / street - 1 if street else None, "target_vs_street": target12 / street - 1 if street else None, "ratings": c.get("ratings") or c.get("ratings_yahoo"),
                       "analysts": c.get("analysts"), "implied": needs},
            "screening": {kk: f["screening"].get(kk) for kk in ("rating", "fifth", "score_rank", "universe", "in_universe", "reason")}}
    return finish(out)


def year10_return(f: dict, k: dict, res: dict) -> dict:
    """The DCF's return on capital in year 10 (its NOPAT over today's invested capital plus the reinvestment of years
    1-9), beside the industry's (Damodaran's pre-tax operating margin x sales to capital, after the marginal tax): the
    Ginzu's check that the forecast's growth and margin are consistent with the capital it takes (stage 23)."""
    ic = value.capital_now(f, k) + sum(res["reinvestment"][:dcf.YEARS - 1])
    m, s2c = k.get("ind_margin"), k.get("ind_sales_to_capital")
    return {"roic10": res["nopat"][-1] / ic if ic > 0 else None,
            "roic_industry": m * s2c * (1 - k["tax_marginal"]) if m is not None and s2c else None}


def finish(out: dict) -> dict:
    save(folder(out["market"], out["code"]) / "valuation.json", out)
    return out


def show(r: dict) -> str:
    pct = lambda x: "-" if x is None else f"{x:+.1%}"
    k, mk = r["inputs"], r["inputs"].get("market") or {}
    lines = [f"{r['name']} {r['code']}: {r['rating']}  price {r['price']:.2f} {r['currency']}  type {r['type']} ({r['type_reason']})",
             f"  rates ({k['currency']}): rf {k['rf']:.2%}  ERP {k['erp']:.2%} (market implied {k['erp_market']:.2%}, published "
             f"{k['published']['erp']:.2%}; {k['country']})  beta {k['beta']:.2f} ({k['industry']}, {k['region']})  COE {k['cost_equity']:.2%}"
             f"  WACC {'-' if k['wacc'] is None else f"{k['wacc']:.2%}"}  stable {k['stable_cost']:.2%}  g {k['g']:.2%}"]
    if mk.get("r") is not None:
        lines.append(f"  market: implied return {mk['r']:.2%} (yield {mk['rf']:.2%}, premium {mk['erp']:.2%}; {mk['members']} members, "
                     f"P/E {mk['pe']:.1f}, P/B {mk['pb']:.2f}, snapshot {mk['snapshot']})")
    if r.get("target") is None:
        return "\n".join(lines + [f"  {r.get('reason')}"])
    for m in [r["main"]] + [x["method"] for x in r["cross"]]:
        x = r["methods"][m]
        extra = f"  (x{x['multiple']:.2f})" if x.get("multiple") else ""
        lines.append(f"  {NAMES[m]:<36} {'main' if m == r['main'] else 'check':>5}  target {x['target']:>9.2f}" +
                     (f"  value {x['value']:.2f}" if x.get("value") is not None else "") + extra)
    s, u, a = r["street"], r["uncertainty"], r["absolute"]
    lines.append(f"  fair value {r['fair_value']:.2f} (bear {r['fair_bear']:.2f} / bull {r['fair_bull']:.2f}): excess {pct(r['fair_excess'])}"
                 f", price/fair {r['price_to_fair'] or 0:.2f} against {1 - u['discount']:.2f} / {1 + u['premium']:.2f} ({u['level']}; {r['state']}; main {r['main_view']}, checks {r['checks_view']}); 12-month target "
                 f"{r['target']:.2f}, expected {pct(r['expected_return'])} vs market {r['market_return']:.1%}")
    rv = r["reverse"]
    lines.append(f"  implied return {'-' if rv.get('implied_return') is None else f"{rv['implied_return']:.2%}"} against a required "
                 f"{k['cost_equity']:.2%}; absolute view (published premium): fair value "
                 f"{'-' if a['fair_value'] is None else f"{a['fair_value']:.2f}"}, excess {pct(a['gap'])} ({a['view']})")
    d, c = r["methods"].get("dcf") or r["methods"].get("dcf_normal"), r["consensus"]
    if d:
        p, f2 = d["path"], lambda xs: "/".join("-" if x is None else f"{x:.1%}" for x in xs)
        lines.append(f"  forecast: {p['consensus_years']} consensus years (revenue {c.get('revenue_source')}), margins "
                     f"{f2(p['margin'][:p['consensus_years']])} (EPS-growth check {f2(p.get('eps_check') or [])}); long-run "
                     f"{p['target_margin']:.1%} ({p['margin_source']}); sales to capital {d['sales_to_capital']:.2f} ({d['s2c_source']});"
                     f" year-10 ROIC {'-' if d.get('roic10') is None else f'{d['roic10']:.1%}'} (industry "
                     f"{'-' if d.get('roic_industry') is None else f'{d['roic_industry']:.1%}'})")
    for x in c.get("revenue_rejected") or []:
        lines.append(f"  rejected: {x['source']}'s FY{x['year']} revenue {x['revenue']:,.0f} below the {x['reported']:,.0f} already reported")
    if r.get("provisional"):
        lines.append(f"  provisional (暂定): results {r['provisional']['date']} ({r['provisional']['title'] or 'next earnings date'}) after the figures of {r['provisional']['period']}")
    for x in r["acts"]["block"] + r["acts"]["widen"]:
        lines.append(f"  check: {x['check']}: {x['why']}")
    for x in r["tail"]:
        lines.append(f"  tail: {x['risk']} value {x['value']} breakeven {x['breakeven']}")
    lines.append(f"  reverse: growth {pct(rv.get('implied_growth_5y'))}" + (f", WACC {rv['implied_wacc']:.1%}" if rv.get("implied_wacc") else "") + (f", margin {rv['implied_margin']:.1%}" if rv.get("implied_margin") is not None else "") + (f"; implied ROE {rv['implied_roe']:.1%}, implied COE "
                 f"{rv['implied_cost_equity']:.1%}" if rv.get("implied_roe") else "") + (f"; dividend growth {pct(rv['implied_dividend_growth_5y'])}"
                 if rv.get("implied_dividend_growth_5y") is not None else "") + f"; base rates {r['base_rates'].get('share_at_least')}")
    lines.append(f"  street: target {s['target']} ({pct(s['upside'])}), ours vs street {pct(s['ours_vs_street'])}, {s['ratings']};"
                 f" screening {r['screening'].get('rating') or r['screening'].get('fifth') or r['screening'].get('reason')}")
    return "\n".join(lines)
