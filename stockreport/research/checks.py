"""Accounting checks and the installed skills' numeric tests, from the fiscal years in the shared layout (research.KEYS),
oldest first. Each returns figures under keys and the published rule it applies; a test whose inputs are missing says
so (None) rather than passing. Financial companies (banks, insurers, brokers) skip the industrial tests.
- Beneish (1999) 8-variable M-score, > -1.78 flags likely earnings manipulation; Piotroski (2000) F-score, 9 signals;
  Altman Z (1968, manufacturers) and Z'' (1995, non-manufacturers and emerging markets) with their zones; Sloan (1996)
  accruals.
- quality-screen: its 7 elimination indicators and exemptions A and B (C needs a judgment of the business model);
  investment-checklist: gate 2's five numbers and the quick veto (3 years of negative free cash flow); income-investment:
  dividend record, cover and payout; era-alpha: growth quality, forward items; earnings-review: receivables, inventory
  and cash conversion against revenue and profit; CN 存贷双高."""

import math

import numpy as np
import pandas as pd

FINANCIAL = {"bank", "insurer", "broker"}


def div(a, b):
    return a / b if a is not None and b not in (None, 0) and pd.notna(a) and pd.notna(b) else None


def val(row, key):
    v = row.get(key) if row is not None else None
    return None if v is None or pd.isna(v) else float(v)


def cagr(new, old, years):
    return (new / old) ** (1 / years) - 1 if None not in (new, old) and new > 0 and old > 0 and years > 0 else None


def roe_series(a: pd.DataFrame) -> pd.Series:
    """Profit to shareholders over average common equity (preferred shares and perpetual securities left out; the
    year-end one for the first year)."""
    common = a["equity"] - (a["pref"].fillna(0) if "pref" in a else 0)
    avg = (common + common.shift(1)) / 2
    return a["ni"] / avg.fillna(common).where(lambda x: x > 0)


def beneish(a: pd.DataFrame) -> dict:
    if len(a) < 2:
        return {"m_score": None, "missing": ["two fiscal years"]}
    t, p = a.iloc[-1], a.iloc[-2]
    lev = "lt_debt" if pd.notna(t.get("lt_debt")) and pd.notna(p.get("lt_debt")) else "debt"
    gm = lambda r: div(val(r, "revenue") - val(r, "cogs"), val(r, "revenue")) if None not in (val(r, "revenue"), val(r, "cogs")) else None
    aq = lambda r: 1 - div(val(r, "cur_assets") + val(r, "ppe"), val(r, "assets")) if None not in (val(r, "cur_assets"), val(r, "ppe"), val(r, "assets")) else None
    dep = lambda r: div(val(r, "da"), val(r, "da") + val(r, "ppe")) if None not in (val(r, "da"), val(r, "ppe")) else None
    lv = lambda r: div(val(r, "cur_liab") + val(r, lev), val(r, "assets")) if None not in (val(r, "cur_liab"), val(r, lev)) else None
    ratio = lambda f, r1, r2: div(f(r1), f(r2))
    x = {"dsri": ratio(lambda r: div(val(r, "receivables"), val(r, "revenue")), t, p), "gmi": ratio(gm, p, t),
         "aqi": ratio(aq, t, p), "sgi": div(val(t, "revenue"), val(p, "revenue")), "depi": ratio(dep, p, t),
         "sgai": ratio(lambda r: div(val(r, "sga"), val(r, "revenue")), t, p), "lvgi": ratio(lv, t, p),
         "tata": div((val(t, "ni") or 0) - val(t, "ocf"), val(t, "assets")) if val(t, "ocf") is not None else None}
    missing = [k for k, v in x.items() if v is None]
    if missing:
        return {"m_score": None, "missing": missing} | x
    m = (-4.84 + 0.920 * x["dsri"] + 0.528 * x["gmi"] + 0.404 * x["aqi"] + 0.892 * x["sgi"] + 0.115 * x["depi"]
         - 0.172 * x["sgai"] + 4.679 * x["tata"] - 0.327 * x["lvgi"])
    return {"m_score": m, "flag": m > -1.78, "rule": "Beneish 1999: M > -1.78 likely manipulator; fast sales growth alone "
            "raises M (SGI), so a boom year can flag an honest grower"} | x


def piotroski(a: pd.DataFrame) -> dict:
    if len(a) < 3:
        return {"f_score": None, "missing": ["three fiscal years"]}
    t, p, q = a.iloc[-1], a.iloc[-2], a.iloc[-3]
    roa = lambda r, prev: div(val(r, "ni"), val(prev, "assets"))
    lev = lambda r, prev: div(val(r, "lt_debt") if val(r, "lt_debt") is not None else val(r, "debt"),
                              (val(r, "assets") + val(prev, "assets")) / 2 if None not in (val(r, "assets"), val(prev, "assets")) else None)
    cr = lambda r: div(val(r, "cur_assets"), val(r, "cur_liab"))
    gm = lambda r: div(val(r, "gp"), val(r, "revenue"))
    turn = lambda r, prev: div(val(r, "revenue"), val(prev, "assets"))
    gt = lambda x, y: None if x is None or y is None else x > y
    s = {"roa_positive": gt(roa(t, p), 0), "cfo_positive": gt(val(t, "ocf"), 0), "roa_up": gt(roa(t, p), roa(p, q)),
         "cfo_above_profit": gt(val(t, "ocf"), val(t, "ni")), "leverage_down": gt(lev(p, q), lev(t, p)),
         "current_ratio_up": gt(cr(t), cr(p)), "no_new_shares": gt(val(p, "shares") * 1.001, val(t, "shares")) if val(p, "shares") else None,
         "margin_up": gt(gm(t), gm(p)), "turnover_up": gt(turn(t, p), turn(p, q))}
    known = [v for v in s.values() if v is not None]
    return {"f_score": sum(known), "signals_known": len(known), "rule": "Piotroski 2000: 8-9 strong, 0-2 weak"} | s


def altman(a: pd.DataFrame, market_cap: float | None) -> dict:
    t = a.iloc[-1]
    ta, tl = val(t, "assets"), val(t, "liabilities")
    wc = None if None in (val(t, "cur_assets"), val(t, "cur_liab")) else val(t, "cur_assets") - val(t, "cur_liab")
    ebit = None if val(t, "pretax") is None else val(t, "pretax") + (val(t, "interest") or 0)
    x = {"wc_ta": div(wc, ta), "re_ta": div(val(t, "retained"), ta), "ebit_ta": div(ebit, ta),
         "mve_tl": div(market_cap, tl), "bve_tl": div(val(t, "equity"), tl), "sales_ta": div(val(t, "revenue"), ta)}
    out = {}
    if None not in (x["wc_ta"], x["re_ta"], x["ebit_ta"], x["mve_tl"], x["sales_ta"]):
        z = 1.2 * x["wc_ta"] + 1.4 * x["re_ta"] + 3.3 * x["ebit_ta"] + 0.6 * x["mve_tl"] + 1.0 * x["sales_ta"]
        out |= {"z": z, "z_zone": "safe" if z > 2.99 else "grey" if z >= 1.81 else "distress"}
    if None not in (x["wc_ta"], x["re_ta"], x["ebit_ta"], x["bve_tl"]):
        z2 = 6.56 * x["wc_ta"] + 3.26 * x["re_ta"] + 6.72 * x["ebit_ta"] + 1.05 * x["bve_tl"]
        out |= {"z2": z2, "z2_zone": "safe" if z2 > 2.6 else "grey" if z2 >= 1.1 else "distress"}
    return out | x | {"rule": "Altman Z (manufacturers): >2.99 safe, <1.81 distress; Z'': >2.6 safe, <1.1 distress"}


def accruals(a: pd.DataFrame) -> dict:
    """Sloan's total accruals: profit less operating cash flow over average total assets, the latest year."""
    t, prev = a.iloc[-1], a.iloc[-2] if len(a) > 1 else None
    both = None not in (val(t, "assets"), val(prev, "assets"))
    avg = (val(t, "assets") + val(prev, "assets")) / 2 if both else val(t, "assets")
    return {"accruals": div(val(t, "ni") - val(t, "ocf"), avg) if None not in (val(t, "ni"), val(t, "ocf")) else None}


def window(a: pd.DataFrame, n: int) -> pd.DataFrame:
    return a.tail(n)


def fcf(a: pd.DataFrame) -> pd.Series | None:
    """Operating cash flow less capex; None when capex isn't reported at all (a REIT's property purchases aren't
    capex: missing is not zero). A year without capex counts none."""
    return None if a["capex"].isna().all() else a["ocf"] - a["capex"].fillna(0)


def quality_screen(a: pd.DataFrame, kind: str, listed_years: float | None) -> dict:
    """quality-screen's 7 indicators (exclude when: 10-year average ROE < 8%, 5-year free cash flow < 0, EBIT/interest
    < 2, long-run gross margin < 15%, 5-year operating cash flow / profit < 0.7 (as a ratio of sums: yearly ratios
    explode on small profits), long-run net margin < 5%, shares up > 20% in 5 years; the cause of dilution, M&A or not,
    isn't checked by code) and exemptions A (ROE: listed < 10 years, gross margin > 30%, 2 years of positive operating
    cash flow) and B (net margin: gross margin > 30%, net margin back above 5% or rising in the last 2 years). Banks and
    insurers skip the interest cover, financials the margins. Fewer years than the window: what there is, said."""
    ten, five, fin = window(a, 10), window(a, 5), kind in FINANCIAL
    t = a.iloc[-1]
    roe10 = roe_series(a).tail(10).mean()
    fcf5 = math.nan if fin or fcf(five) is None else fcf(five).sum(min_count=1)
    ebit = None if val(t, "pretax") is None else val(t, "pretax") + (val(t, "interest") or 0)
    cover = div(ebit, val(t, "interest")) if (val(t, "interest") or 0) > 0 else None
    gm = (ten["gp"] / ten["revenue"]).mean()
    nm = (ten["ni"] / ten["revenue"]).mean()
    conv = div(five["ocf"].sum(min_count=1), five["ni"].sum(min_count=1))
    dil = div(val(t, "shares"), val(five.iloc[0], "shares"))
    tests = {"roe_10y": (roe10, roe10 >= 0.08), "fcf_5y": (fcf5, None if pd.isna(fcf5) else fcf5 >= 0),
             "interest_cover": (cover, None if fin else cover is None or cover >= 2),
             "gross_margin_avg": (gm, None if fin or pd.isna(gm) else gm >= 0.15),
             "ocf_to_profit_5y": (conv, None if conv is None or fin else conv >= 0.7),
             "net_margin_avg": (nm, None if fin or pd.isna(nm) else nm >= 0.05),
             "share_growth_5y": (None if dil is None else dil - 1, None if dil is None else dil <= 1.2)}
    out = {k: {"value": None if v is None or pd.isna(v) else float(v), "pass": None if p is None or pd.isna(p) else bool(p)}
           for k, (v, p) in tests.items()}
    last2 = a.tail(2)
    margin_now = (last2["ni"] / last2["revenue"])
    if out["roe_10y"]["pass"] is False and (listed_years or 99) < 10 and gm > 0.3 and (last2["ocf"] > 0).all():
        out["roe_10y"]["exempt"] = "A"
    if out["net_margin_avg"]["pass"] is False and gm > 0.3 and (margin_now.iloc[-1] >= 0.05 or margin_now.is_monotonic_increasing):
        out["net_margin_avg"]["exempt"] = "B"
    failed = [k for k, v in out.items() if v["pass"] is False and not v.get("exempt")]
    return {"tests": out, "failed": failed, "years": len(ten), "result": "pass" if not failed else "exclude"}


def checklist(a: pd.DataFrame, kind: str) -> dict:
    """investment-checklist gate 2 (ROE 5-year mean > 15%, gross margin > 40%, free cash flow positive every year and
    at least 80% of profit over 5 years, capex at most half of operating cash flow (light assets), interest-bearing
    debt under 3 years of profit), its stars by the count met (5 stars also needs ROE > 25%), and the quick veto of 3
    straight years of negative free cash flow. The 80% and the half are code's reading of "≈ profit" and "light"."""
    five, t = window(a, 5), a.iloc[-1]
    cash = fcf(five) if fcf(five) is not None else five["ocf"] * math.nan
    roe5 = roe_series(a).tail(5).mean()
    gm = div(val(t, "gp"), val(t, "revenue"))
    items = {"roe_5y": (roe5, roe5 > 0.15), "gross_margin": (gm, None if gm is None else gm > 0.40),
             "fcf_quality": (div(cash.sum(min_count=1), five["ni"].sum()), None if kind in FINANCIAL or cash.isna().all() else
                             bool((cash > 0).all() and cash.sum() >= 0.8 * five["ni"].sum())),
             "capex_to_ocf": (div(five["capex"].sum(), five["ocf"].sum()), None if kind in FINANCIAL else
                              bool(five["capex"].sum() <= 0.5 * five["ocf"].sum())),
             "debt_to_profit": (div(val(t, "debt"), val(t, "ni")), None if kind in FINANCIAL else
                                bool((val(t, "debt") or 0) < 3 * (val(t, "ni") or 0)))}
    met = sum(bool(p) for _, p in items.values() if p is not None)
    stars = None if kind in FINANCIAL else 5 if met == 5 and roe5 > 0.25 else max(min(met, 4), 1)
    veto = None if kind in FINANCIAL or cash.isna().all() else bool(len(cash) >= 3 and (cash.tail(3) < 0).all())
    return {"items": {k: {"value": None if v is None or pd.isna(v) else float(v), "pass": p} for k, (v, p) in items.items()},
            "stars": stars, "fcf_negative_3y": veto}


def income(a: pd.DataFrame, dps: dict[str, float], price: float | None, yields: dict[str, float]) -> dict:
    """income-investment: dividends per share by year, raises / holds / cuts, the 5-year dividend growth, profit and
    free-cash-flow payout, years the dividend wasn't covered by free cash flow (last 5), the yield against its own
    5-year average, and the free-cash-flow yield's inputs."""
    years = sorted(dps)[-11:]
    steps = [np.sign(round(dps[b] - dps[a_], 6)) for a_, b in zip(years, years[1:])]
    five, t = window(a, 5), a.iloc[-1]
    paid = five["div_paid"] if "div_paid" in five and five["div_paid"].notna().any() else None
    cover = None if paid is None or fcf(five) is None else int((fcf(five) < paid).sum())
    last = dps[years[-1]] if years else None
    return {"dps": {y: dps[y] for y in years}, "raises": steps.count(1), "holds": steps.count(0), "cuts": steps.count(-1),
            "dps_cagr_5y": cagr(dps.get(years[-1]), dps.get(years[-6]), 5) if len(years) >= 6 else None,
            "payout": div(last * val(t, "shares") if last and val(t, "shares") else val(t, "div_paid"), val(t, "ni")),
            "fcf_payout": div(val(t, "div_paid") or (last * val(t, "shares") if last and val(t, "shares") else None),
                              val(t, "ocf") - (val(t, "capex") or 0) if val(t, "ocf") is not None else None),
            "uncovered_years_5y": cover, "yield": div(last, price),
            "yield_avg_5y": float(np.mean(list(yields.values())[-5:])) if yields else None}


def era_alpha(a: pd.DataFrame, quarters: pd.DataFrame) -> dict:
    """era-alpha's numeric tests: revenue and profit growth over the last quarters (CN) and years, the gross margin's
    direction over 3 years, growth with cash (operating cash flow up with revenue), and the forward items (contract
    liabilities, inventory, construction in progress) against revenue."""
    t, p = a.iloc[-1], a.iloc[-2] if len(a) > 1 else None
    growth = lambda k: div(val(t, k), val(p, k)) - 1 if div(val(t, k), val(p, k)) is not None else None
    gm = (a["gp"] / a["revenue"]).tail(4).dropna()
    return {"revenue_growth": growth("revenue"), "profit_growth": growth("ni"), "ocf_growth": growth("ocf"),
            "growth_with_cash": None if growth("revenue") is None or growth("ocf") is None else growth("revenue") > 0 and growth("ocf") > 0,
            "gross_margin_trend": None if len(gm) < 3 else float(gm.iloc[-1] - gm.iloc[0]),
            "contract_liab_growth": growth("contract_liab"), "inventory_growth": growth("inventory"), "cip_growth": growth("cip"),
            "quarters": quarters.to_dict("records") if quarters is not None else []}


def earnings_signals(a: pd.DataFrame) -> dict:
    """earnings-review's anomaly signals on the latest fiscal year: receivables or inventory growing faster than revenue
    (where they are at least 5% of revenue), operating cash flow below profit and the gap widening, capex intensity
    against its 3-year average, and (CN) the share of profit from non-recurring items."""
    if len(a) < 2:
        return {}
    t, p = a.iloc[-1], a.iloc[-2]
    g = lambda r, k: div(val(r, k), val(p, k)) - 1 if div(val(r, k), val(p, k)) is not None else None
    rev = g(t, "revenue")
    faster = lambda k: None if None in (g(t, k), rev) or (div(val(t, k), val(t, "revenue")) or 0) < 0.05 else g(t, k) > rev
    conv = lambda r: div(val(r, "ocf"), val(r, "ni"))
    intensity = (a["capex"] / a["revenue"]).dropna()
    return {"receivables_faster": faster("receivables"), "inventory_faster": faster("inventory"),
            "cash_below_profit_widening": None if None in (conv(t), conv(p)) else conv(t) < 1 and conv(t) < conv(p),
            "capex_intensity": float(intensity.iloc[-1]) if len(intensity) else None,
            "capex_intensity_3y": float(intensity.iloc[-4:-1].mean()) if len(intensity) > 3 else None,
            "non_recurring_share": div(val(t, "ni") - val(t, "ni_core"), val(t, "ni")) if val(t, "ni_core") is not None else None}


def cn_flags(a: pd.DataFrame, flows: dict) -> dict:
    """CN market flags: 存贷双高 (cash and interest-bearing debt each over 20% of total assets, the common screening
    rule), goodwill against equity, the pledge ratio, lock-ups ahead (next 12 months) and holders' net selling."""
    t = a.iloc[-1]
    cash, debt = div(val(t, "cash"), val(t, "assets")), div(val(t, "debt"), val(t, "assets"))
    trades = flows.get("holder_trades") or []
    ahead = [x for x in flows.get("lockups") or [] if x["date"] >= pd.Timestamp.today().strftime("%Y-%m-%d")]
    return {"cash_to_assets": cash, "debt_to_assets": debt,
            "cash_and_debt_high": None if None in (cash, debt) else cash > 0.2 and debt > 0.2,
            "goodwill_to_equity": div(val(t, "goodwill"), val(t, "equity")),
            "pledge_ratio": (flows.get("pledge") or {}).get("ratio"),
            "lockups_ahead": ahead, "holder_net_shares_1y": sum(x["shares"] or 0 for x in trades),
            "holder_sells_1y": sum(x["direction"] == "减持" for x in trades)}
