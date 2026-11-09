"""Research stage 10, part 2: each method's value and 12-month target, the weighted target, bear / base / bull, the
valuation's uncertainty, the rating, what today's price assumes (reverse DCF, with base rates), the sensitivity grid
and the comparison with the street; saved as data/research/<market>/<code>/valuation.json (`research CODE --value`).
- Targets: an absolute method's value today rolled forward 12 months at the cost of equity less the dividend yield; a
  multiple applied to the next 12 months' consensus (a normal trailing multiple a year from now).
- Rating (PLAN.md "Rating"): expected 12-month excess return = (target - price + next year's dividend) / price
  - the listing market's expected return (Damodaran's premium for it over the yield of the currency the target grows
  in: the reporting currency's, so a CNY reporter listed in HK is compared in CNY terms, by interest parity). 买入 at +band or more, 卖出 at -band or
  worse, else 持有; the band is the valuation's uncertainty (the larger of the bear-to-bull half-range and the methods'
  half-range), rounded up to 5 points, at least the brokers' 10% and at most 25% (Morningstar's uncertainty-scaled
  star bands; the Securities Association of China's ratings against the index over 6-12 months).
- Bear and bull: the first forecast year's analysts' low and high (Yahoo; CN: the brokers' reports) and the long-run
  margin (financials: ROE) one standard deviation of the company's own 10 years lower and higher, at most the margin's
  own size.
- 不评级 / 评级暂停: pre-revenue; a non-standard audit opinion or a hard red flag of the results review (investigation,
  going concern: no target); a pending takeover suspends the rating."""

import math
from datetime import date
from functools import lru_cache

import numpy as np
import pandas as pd

from stockreport import review
from stockreport.config import DATA
from stockreport.fetch import yahoo
from stockreport.research import dcf, folder, load, save, stamp, value
from stockreport.research.checks import FINANCIAL, cagr

BAND = (0.10, 0.25)
TABLE_CURRENCY = {"cn": "CNY", "us": "USD", "hk": "CNY"}  # Eastmoney's HK amounts are CNY (stage 9)
NAMES = {"dcf": "DCF (FCFF, 10 years)", "dcf_normal": "DCF, margins normalized", "pe_own": "P/E against own history",
         "pe_peers": "P/E against peers", "pe_normal": "own P/E on normalized EPS", "pb_own": "P/B against own history",
         "pb_roe": "justified P/B on average ROE", "evs_peers": "EV/Sales against peers", "peg_peers": "PEG against peers",
         "ddm": "dividend discount (two-stage)", "yield_own": "yield against own 5-year average",
         "excess_return": "excess-return model on book equity"}


def methods(f: dict, k: dict, kind: str, cons: dict, today: date, eps_factor: float = 1.0, shift: int = 0) -> dict:
    """Each method of the type's playbook: {name: {value (today), target (12 months), ...}} per share, quote currency."""
    v, t, own, w = f["valuation"], f["valuation"]["ttm"], f["valuation"]["own_history"], value.WEIGHTS[kind]
    shares, fx, coe, g = k["shares"], k["fx"], k["cost_equity"], k["g"]
    dps = value.next_dividend(f, k, cons) * eps_factor
    roll = 1 + coe - dps / v["price"]
    eps = [e * eps_factor for e in cons["eps"]]
    eps_ntm = (cons["ntm_eps"] or (t["ni"] or 0) / shares) * eps_factor
    book, payout, out = v["book_common"], value.payout_5y(f) or f["checks"]["income"].get("payout") or 0.0, {}
    fwd_book = book + eps_ntm * shares * (1 - payout) if book else None
    per = lambda total: max(total, 0.0) / shares / fx
    window = "median" if kind == "cyclical" else "median_5y"  # a full cycle for a cyclical; else brokers' latest 5 years
    multiple = lambda key: own[key].get(window) or own[key].get("median")
    peers = value.peer_medians(f, today)
    if {"dcf", "dcf_normal"} & set(w):
        path = value.paths(f, k, kind, cons | {"eps": eps}, k["g"])
        m = value.history(f, "ebit_margin", 10)
        if shift and len(m) >= 3:  # bear / bull: the long-run margin one standard deviation lower / higher
            d = min(m.std(), abs(path["target_margin"])) * shift
            path["margin"] = [x + d * min(i + 1, value.CONVERGENCE) / value.CONVERGENCE for i, x in enumerate(path["margin"])]
        s2c, s2c_source = value.sales_to_capital(f, k)
        roic_term, moat = value.moat(value.history(f, "roic", 10), k["wacc"], k["stable_cost"])
        x, res = value.dcf_value(f, k, path, s2c, roic_term)
        x = max(x, 0.0)
        out["dcf_normal" if kind == "cyclical" else "dcf"] = {
            "value": x, "target": x * roll, "path": path, "sales_to_capital": s2c, "s2c_source": s2c_source,
            "roic_term": roic_term, "moat": moat, "terminal_multiple": (1 - k["g"] / max(roic_term, k["stable_cost"])) / (k["stable_cost"] - k["g"]),
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
        gt = min(g, max(g1, 0.0))
        x = dcf.ddm(dps * fx / (1 + g1), g1, 5, coe, gt) / fx  # next year's dividend, then growing at g1 to year 5
        out["ddm"] = {"value": x, "target": x * roll, "dividend": dps, "growth_5y": g1, "growth_stable": gt}
    roe_hist = value.history(f, "roe", 10)
    if "excess_return" in w and book and eps:
        roe_term, moat = value.moat(roe_hist, coe, k["stable_cost"])  # the moat clause, as for the DCF's return on capital
        if shift and len(roe_hist) >= 3:
            roe_term += min(roe_hist.std(), abs(roe_term)) * shift
        roes, b = [], book
        for e in eps:
            roes.append(e * shares / b)
            b += e * shares * (1 - payout)
        n = len(roes)
        roes += [roes[-1] + (roe_term - roes[-1]) * (i - n) / (dcf.YEARS - n) for i in range(n + 1, dcf.YEARS + 1)]
        res = dcf.excess_return(book, roes, [payout] * dcf.YEARS, dcf.steps(coe, k["stable_cost"]), roe_term, k["stable_cost"], g)
        x = per(res["value"])
        out["excess_return"] = {"value": x, "target": x * roll, "roe": roes, "roe_term": roe_term, "moat": moat,
                                "payout": payout, "pv_terminal_share": res["pv_terminal"] / res["value"] if res["value"] else None}
    if "pb_roe" in w and book:
        roe = value.history(f, "roe", 10 if kind == "cyclical" else 8).mean()
        if not np.isnan(roe) and roe > g:
            pb = dcf.justified_pb(roe + (min(roe_hist.std(), roe) * shift if shift else 0), coe, g)
            extra = excess(eps, roe * book / shares, coe, 1)
            x = max(pb * book / shares + extra, 0.0) / fx
            out["pb_roe"] = {"roe": roe, "pb": pb, "excess_earnings": extra / fx, "value": x, "target": x * roll}
    if "pe_normal" in w and multiple("pe"):
        nm = value.history(f, "net_margin", 10).mean()
        if not np.isnan(nm) and nm > 0:
            e = t["revenue"] * nm / shares * eps_factor
            extra = excess(eps, e, coe, 0)
            out["pe_normal"] = {"multiple": multiple("pe"), "eps": e, "net_margin": nm, "excess_earnings": extra / fx,
                                "target": max(multiple("pe") * e + extra, 0.0) / fx}
    return out


def excess(eps: list[float], normal: float, cost: float, start: int) -> float:
    """The consensus years' earnings per share above (or below) normal, discounted from `start` years: residual
    income that accrues to holders, so a normalized value of a cyclical at a peak (a trough) adds (subtracts) it."""
    return sum((e - normal) / (1 + cost) ** (i + start) for i, e in enumerate(eps))


def weigh(found: dict, kind: str) -> tuple[float | None, dict]:
    """The weighted target; a method that couldn't run gives its weight to the others in proportion."""
    w = {m: x for m, x in value.WEIGHTS[kind].items() if m in found and found[m]["target"] is not None}
    total = sum(w.values())
    if not total:
        return None, {}
    w = {m: x / total for m, x in w.items()}
    return sum(found[m]["target"] * x for m, x in w.items()), w


def rate(target: float, bear: float, bull: float, targets: list[float], price: float, dividend: float,
         market_return: float) -> dict:
    """The expected 12-month excess return over the market's and the rating at the valuation's uncertainty band."""
    spread = (max(bull, target, bear) - min(bull, target, bear)) / 2 / target if target > 0 else math.inf
    disagree = (max(targets) - min(targets)) / 2 / target if target > 0 else math.inf
    band = min(max(math.ceil(max(spread, disagree) * 20 - 1e-9) / 20, BAND[0]), BAND[1])
    expected = (target - price + dividend) / price
    excess = expected - market_return
    return {"rating": "买入" if excess >= band else "卖出" if excess <= -band else "持有", "expected_return": expected,
            "excess_return": excess, "uncertainty": {"scenario_half_range": spread, "methods_half_range": disagree, "band": band}}


@lru_cache(maxsize=3)
def base_table(market: str) -> pd.DataFrame:
    """Annual revenue per company and fiscal year from the screening's history tables (today's listings only)."""
    if market == "cn":
        t = pd.read_csv(DATA / "history" / "cn_annual.csv.gz", dtype={"code": str}, usecols=["code", "period", "revenue"])
        t = t.assign(year=t["period"].astype(str).str[:4])
    elif market == "us":
        t = pd.read_csv(DATA / "history" / "us_annual.csv.gz", dtype={"code": str}, usecols=["code", "fy_end", "revenue", "currency"])
        t = t[t["currency"] == "USD"].assign(year=lambda d: d["fy_end"].str[:4])
    else:
        t = pd.read_csv(DATA / "history" / "hk_results.csv.gz", dtype={"code": str}, usecols=["code", "period", "date_type", "revenue"])
        t = t[t["date_type"] == 1].assign(year=lambda d: d["period"].str[:4])
    return t.drop_duplicates(["code", "year"], keep="last").pivot(index="code", columns="year", values="revenue")


def base_rates(market: str, revenue_now: float, rates: dict[str, float | None], years: int = 5) -> dict:
    """Mauboussin and Callahan's base rates: of the companies in the same fifth by revenue (its rank in each start
    year), how many grew revenue at least as fast over `years`; and the median company's growth (the market's norm)."""
    p = base_table(market)
    cols, rows = sorted(p.columns), []
    for a, b in zip(cols, cols[years:]):
        start, end = p[a], p[b]
        ok = (start > 0) & (end > 0)
        rows.append(pd.DataFrame({"g": (end[ok] / start[ok]) ** (1 / years) - 1, "fifth": (start.rank(pct=True)[ok] * 5).clip(upper=4.999).astype(int)}))
    if not rows:
        return {}
    d, latest = pd.concat(rows), p[cols[-2]].dropna()  # the last full year's cross-section (the newest may be partial)
    fifth = min(int((latest < revenue_now).mean() * 5), 4)
    same = d[d["fifth"] == fifth]["g"]
    return {"years": f"{cols[0]}-{cols[-1]}", "fifth": fifth + 1, "count": len(same), "median": float(same.median()),
            "market_median": float(d["g"].median()), "recent_median": float(rows[-1]["g"].median()),
            "share_at_least": {name: float((same >= x).mean()) if x is not None else None for name, x in rates.items()}}


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


def reverse(f: dict, k: dict, kind: str, cons: dict, found: dict) -> dict:
    """What today's price assumes: the revenue growth in years 1-5 (then fading as in the base case) at which the DCF
    equals the price; for financials the ROE the price implies at our cost of equity, and the cost of equity it implies
    at the next year's ROE; for dividend payers the 5-year dividend growth."""
    v, price, out = f["valuation"], f["valuation"]["price"], {}
    d = found.get("dcf") or found.get("dcf_normal")
    if d:
        def at(g5):
            path = d["path"] | {"growth": dcf.steps(g5, k["g"])}
            return value.dcf_value(f, k, path, d["sales_to_capital"], d["roic_term"])[0]
        if at(-0.3) <= at(1.0):
            out["implied_growth_5y"] = dcf.solve(at, price, -0.3, 1.0)
        else:  # growth destroys value when the return on new capital is below its cost
            out["implied_growth_5y"] = dcf.solve(lambda g5: -at(g5), -price, -0.3, 1.0)
            out["note"] = "the return on new capital is below its cost: faster growth lowers the value"
        at_cost = lambda c: value.dcf_value(f, k, d["path"], d["sales_to_capital"], d["roic_term"], c)[0]
        shift = dcf.solve(lambda c: -at_cost(c), -price, -0.045, 0.25)  # the cost of capital the price implies
        out["implied_wacc"] = None if shift is None else k["wacc"] + shift
        if kind == "loss_making":  # the long-run margin the price assumes, the base case's growth
            def margin_at(m):
                p = d["path"]
                return value.dcf_value(f, k, p | {"margin": [x + (m - p["target_margin"]) * min(i + 1, value.CONVERGENCE)
                                                             / value.CONVERGENCE for i, x in enumerate(p["margin"])]},
                                       d["sales_to_capital"], d["roic_term"])[0]
            out["implied_margin"] = dcf.solve(margin_at, price, -0.5, 0.9)
    if kind in FINANCIAL and v["pb"]:
        roe = cons["eps"][0] * k["shares"] / v["book_common"] if cons["eps"] else f["summary"].get("roe_latest")
        if roe:
            out["implied_roe"] = k["g"] + v["pb"] * (k["cost_equity"] - k["g"])
            out["implied_cost_equity"] = (roe - k["g"]) / v["pb"] + k["g"]
            out["roe_next"] = roe
    if found.get("ddm"):
        gt, d1 = found["ddm"]["growth_stable"], found["ddm"]["dividend"] * k["fx"]
        out["implied_dividend_growth_5y"] = dcf.solve(lambda g1: dcf.ddm(d1 / (1 + g1), g1, 5, k["cost_equity"], gt) / k["fx"],
                                                      price, -0.5, 1.0)
    return out


def sensitivity(f: dict, k: dict, found: dict) -> dict:
    """The absolute method's value per share across the cost of capital (-1, 0, +1 point) and stable growth (-0.5, 0,
    +0.5 point)."""
    costs, growths = [-0.01, 0.0, 0.01], [k["g"] - 0.005, k["g"], k["g"] + 0.005]
    d = found.get("dcf") or found.get("dcf_normal")
    if d:
        fn = lambda c, g: value.dcf_value(f, k, d["path"], d["sales_to_capital"], d["roic_term"], c, g)[0]
        return {"method": "dcf", "cost_shift": costs, "growth": growths, "values": dcf.grid(fn, costs, growths)}
    if found.get("ddm"):
        x = found["ddm"]
        d0 = x["dividend"] * k["fx"] / (1 + x["growth_5y"])
        fn = lambda c, g: dcf.ddm(d0, x["growth_5y"], 5, k["cost_equity"] + c, g) / k["fx"]
        return {"method": "ddm", "cost_shift": costs, "growth": growths, "values": dcf.grid(fn, costs, growths)}
    return {}


def build(market: str, code: str, today: date | None = None) -> dict:
    from stockreport.research import facts as fact_sheet
    today = today or date.today()
    path = folder(market, fact_sheet.normal(market, code)) / "facts.json"
    f = load(path) if path.exists() and load(path)["built"][:10] == today.isoformat() else fact_sheet.build(market, code, today)
    k, v = value.implied_floor(f, value.inputs(f), today), f["valuation"]
    k["mature_margin"] = value.peer_medians(f, today).get("mature_margin")  # the young's target margin (value.paths)
    t = v["ttm"]
    cur_rev = value.convert(yahoo.load_fx(), t["revenue"], k["currency"], TABLE_CURRENCY[market]) if t["revenue"] else None
    norm = base_rates(market, cur_rev or 0, {})["recent_median"] if cur_rev else None  # the last 5-year window's median
    kind, why = value.kind_of(f, k, norm)
    cons = value.consensus_years(f, k, today)
    status, reason = flags(f) if kind != "pre_revenue" else ("不评级", why)
    out = {"code": f["code"], "market": market, "name": f["name"], "built": stamp(), "price": v["price"],
           "currency": v["quote_currency"], "type": kind, "type_reason": why, "inputs": k, "consensus": cons}
    found = {} if status == "不评级" else methods(f, k, kind, cons, today)
    target, weights = weigh(found, kind)
    if target is None or status:
        return finish(out | {"rating": status or "不评级", "reason": reason or "no method could value it", "methods": found})
    lo, hi = cons["range"] or (1.0, 1.0)
    bear = weigh(methods(f, k, kind, cons, today, lo, -1), kind)[0] or target  # a shifted case no method can value
    bull = weigh(methods(f, k, kind, cons, today, hi, +1), kind)[0] or target
    dividend = value.next_dividend(f, k, cons)
    r = rate(target, bear, bull, [found[m]["target"] for m in weights], v["price"], dividend, k["market_return"])
    d = found.get("dcf") or found.get("dcf_normal")
    ours = cagr(d["years"]["revenue"][4], t["revenue"], 5) if d else None
    rev = reverse(f, k, kind, cons, found)
    c = f["consensus"]
    street = c.get("target_mean") or c.get("target_yahoo")
    out |= r | {"target": target, "weights": weights, "methods": found, "bear": bear, "bull": bull,
            "market_return": k["market_return"], "dividend_next": dividend, "reverse": rev, "sensitivity": sensitivity(f, k, found),
            "base_rates": base_rates(market, cur_rev, {"forecast": ours, "implied": rev.get("implied_growth_5y")}) if cur_rev else {},
            "street": {"target": street, "upside": street / v["price"] - 1 if street else None, "ours_vs_street":
                       target / street - 1 if street else None, "ratings": c.get("ratings") or c.get("ratings_yahoo"),
                       "analysts": c.get("analysts")},
            "screening": {kk: f["screening"].get(kk) for kk in ("rating", "fifth", "score_rank", "universe", "in_universe", "reason")}}
    return finish(out)


def finish(out: dict) -> dict:
    save(folder(out["market"], out["code"]) / "valuation.json", out)
    return out


def show(r: dict) -> str:
    pct = lambda x: "-" if x is None else f"{x:+.1%}"
    k = r["inputs"]
    lines = [f"{r['name']} {r['code']}: {r['rating']}  price {r['price']:.2f} {r['currency']}  type {r['type']} ({r['type_reason']})",
             f"  rates ({k['currency']}): rf {k['rf']:.2%}  ERP {k['erp']:.2%} ({k['country']})  beta {k['beta']:.2f} ({k['industry']}, "
             f"{k['region']})  COE {k['cost_equity']:.2%}" + (f" (industry's implied; CAPM {k['floor']['cost_equity_capm']:.2%})"
             if (k.get("floor") or {}).get("applied") else "") + f"  WACC {'-' if k['wacc'] is None else f"{k['wacc']:.2%}"}  stable {k['stable_cost']:.2%}  g {k['g']:.2%}"]
    if r.get("target") is None:
        return "\n".join(lines + [f"  {r.get('reason')}"])
    for m, w in r["weights"].items():
        x = r["methods"][m]
        extra = f"  (x{x['multiple']:.2f})" if x.get("multiple") else ""
        lines.append(f"  {NAMES[m]:<36} {w:>4.0%}  target {x['target']:>9.2f}" + (f"  value {x['value']:.2f}" if x.get("value") is not None else "") + extra)
    s, u = r["street"], r["uncertainty"]
    lines.append(f"  target {r['target']:.2f} (bear {r['bear']:.2f} / bull {r['bull']:.2f}); expected {pct(r['expected_return'])} vs market "
                 f"{r['market_return']:.1%}: excess {pct(r['excess_return'])}, band ±{u['band']:.0%}")
    rv = r["reverse"]
    lines.append(f"  reverse: growth {pct(rv.get('implied_growth_5y'))}" + (f", WACC {rv['implied_wacc']:.1%}" if rv.get("implied_wacc") else "") + (f", margin {rv['implied_margin']:.1%}" if rv.get("implied_margin") is not None else "") + (f"; implied ROE {rv['implied_roe']:.1%}, implied COE "
                 f"{rv['implied_cost_equity']:.1%}" if rv.get("implied_roe") else "") + (f"; dividend growth {pct(rv['implied_dividend_growth_5y'])}"
                 if rv.get("implied_dividend_growth_5y") is not None else "") + f"; base rates {r['base_rates'].get('share_at_least')}")
    lines.append(f"  street: target {s['target']} ({pct(s['upside'])}), ours vs street {pct(s['ours_vs_street'])}, {s['ratings']};"
                 f" screening {r['screening'].get('rating') or r['screening'].get('fifth') or r['screening'].get('reason')}")
    return "\n".join(lines)
