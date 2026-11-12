"""The fact sheet's computations from the gathered tables: trailing twelve months, the fiscal-year history with its
ratios, the stock's own valuation history, peers from the day's snapshot, the industry's valuation history (CN), the
screening's view of the stock and the two-source cross-check (financial-data: within 1% agree, 1-5% differ, above 5%
a large gap, left out of the calculations; config [crosscheck] agree / large)."""

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import yahoo
from stockreport.research.checks import cagr, div, fcf, roe_series, val

CHECK = ["revenue", "ni", "equity", "ocf", "assets"]
BALANCE = ["assets", "cur_assets", "cur_liab", "cash", "receivables", "inventory", "ppe", "goodwill", "intangibles",
           "liabilities", "debt", "lt_debt", "equity", "pref", "minority", "retained", "contract_liab", "cip"]
FIN_OFF = ["ocf", "capex", "fcf", "debt", "cash", "net_debt", "roic", "ocf_to_profit", "gp", "gross_margin", "ebit_margin"]
RATING = {"buy": "买入", "hold": "持有", "sell": "卖出"}


def ttm(st: pd.DataFrame, key: str) -> float | None:
    """Twelve months to the latest period: the fiscal year itself, or the year to date + the last fiscal year - the
    same months a year earlier (CN quarters, HK halves)."""
    st = st.dropna(subset=[key])
    if st.empty:
        return None
    last = st.iloc[-1]
    if last["months"] == 12:
        return float(last[key])
    prior_end = (pd.Timestamp(last["period"]) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    prior = st[(st["months"] == last["months"]) & (st["period"].str[:7] == prior_end[:7])]
    fy = st[(st["months"] == 12) & (st["period"] < last["period"])]
    if prior.empty or fy.empty:
        return None
    return float(last[key] + fy.iloc[-1][key] - prior.iloc[-1][key])


def latest_vs_prior(st: pd.DataFrame) -> dict:
    """earnings-review: the latest reported period against the same period a year earlier."""
    last = st.iloc[-1]
    prior = st[(st["months"] == last["months"]) &
               (st["period"].str[:7] == (pd.Timestamp(last["period"]) - pd.DateOffset(years=1)).strftime("%Y-%m"))]
    p = prior.iloc[-1] if len(prior) else None
    out = {"period": last["period"], "months": int(last["months"]), "basis": "year to date", "notice": last.get("notice")}
    for k in ("revenue", "ni", "gp", "ocf"):
        out[k], out[f"{k}_prior"] = val(last, k), val(p, k)
    return out


def quarters(st: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    """Single quarters from year-to-date reports (CN: 3, 6, 9, 12 months), with growth on the same quarter a year
    earlier: era-alpha's 4-8 quarter trend."""
    q = st[st["months"].isin([3, 6, 9, 12])].copy()
    q["year"] = q["period"].str[:4]
    q = q.sort_values("period")
    for k in ("revenue", "ni"):
        q[f"{k}_q"] = q[k] - q.groupby("year")[k].shift(1).where(q["months"] > 3, 0)
    q["key"] = q["period"].str[5:7]
    for k in ("revenue", "ni"):
        prev = q.groupby("key")[f"{k}_q"].shift(1)
        q[f"{k}_yoy"] = (q[f"{k}_q"] / prev - 1).where(prev > 0)
    return q[["period", "revenue_q", "ni_q", "revenue_yoy", "ni_yoy"]].tail(n)


def ebit(market: str, pretax, interest, op_income):
    """Operating profit, a figure or a column. US filers: the operating income they report, when filed: their pretax
    profit carries equity stakes' fair-value changes (US GAAP since 2018, ASU 2016-01: Amazon's Anthropic stake) and
    interest earned on cash the valuation adds as cash (Damodaran's EBIT is operating income). Elsewhere pretax profit
    plus interest expense: CN's 营业利润 itself counts investment income, and an HK associate's share stands for a
    stake the free data can't value apart (Tencent's)."""
    if isinstance(pretax, pd.Series):
        total = pretax + interest.fillna(0)
        return op_income.where(op_income.notna(), total) if market == "us" else total
    if market == "us" and op_income is not None and op_income == op_income:
        return op_income
    return None if pretax is None else pretax + (interest or 0)


def history(a: pd.DataFrame, dps: dict[str, float], kind: str, market: str = "cn") -> list[dict]:
    """Up to 10 fiscal years with margins, returns, cash conversion, free cash flow and leverage (not for banks, insurers
    and brokers, whose debt, cash and operating cash flow are their business; nor a REIT's cash conversion, its profit
    carrying property revaluations). EPS is profit over the year's shares on today's basis."""
    h = a.tail(10).copy()
    h["fcf"] = fcf(h) if fcf(h) is not None else np.nan
    h["gross_margin"], h["op_margin"], h["net_margin"] = h["gp"] / h["revenue"], h["op_income"] / h["revenue"], h["ni"] / h["revenue"]
    h["roe"], h["roa"], h["eps"] = roe_series(a).tail(10), h["ni"] / h["assets"], h["ni"] / h["shares"]
    tax_rate = (h["tax"] / h["pretax"]).clip(0, 0.5).fillna(0.25)
    invested = h["equity"] + h["debt"].fillna(0) - h["cash"].fillna(0)
    operating = ebit(market, h["pretax"], h["interest"], h["op_income"])
    h["roic"] = (operating * (1 - tax_rate) / invested).where(invested > 0)
    h["ebit_margin"] = operating / h["revenue"]
    h["ocf_to_profit"], h["net_debt"] = h["ocf"] / h["ni"].where(h["ni"] > 0), h["debt"] - h["cash"]
    h["dps"] = h["period"].str[:4].map(dps)
    h[{"bank": FIN_OFF, "insurer": FIN_OFF, "broker": FIN_OFF, "reit": ["ocf_to_profit"]}.get(kind, [])] = np.nan
    keep = ["period", "currency", "revenue", "gp", "op_income", "ni", "ni_core", "eps", "dps", "ocf", "capex", "fcf",
            "div_paid", "buyback", "assets", "equity", "debt", "cash", "net_debt", "goodwill", "shares", "gross_margin",
            "op_margin", "ebit_margin", "net_margin", "roe", "roa", "roic", "ocf_to_profit", "npl", "provision_cover", "car", "cet1", "nim",
            "solvency"]
    return h.reindex(columns=keep).dropna(axis=1, how="all").replace({np.nan: None}).to_dict("records")


def summary(a: pd.DataFrame, kind: str, market: str = "cn") -> dict:
    """The keyed figures the report's words cite most: growth, margins, returns, cash and leverage (not for banks,
    insurers and brokers, whose debt, cash and operating cash flow are their business; a REIT's profit carries property
    revaluations, so no profit-based cover or cash conversion)."""
    t, out = a.iloc[-1], {}
    for n in (3, 5, 10):
        if len(a) > n:
            old = a.iloc[-1 - n]
            out[f"rev_cagr_{n}y"], out[f"ni_cagr_{n}y"] = cagr(val(t, "revenue"), val(old, "revenue"), n), cagr(val(t, "ni"), val(old, "ni"), n)
    five, roe = a.tail(5), roe_series(a)
    operating = ebit(market, val(t, "pretax"), val(t, "interest"), val(t, "op_income"))
    ebitda = None if operating is None else operating + (val(t, "da") or 0)
    if kind in ("bank", "insurer", "broker"):
        a = a.assign(ocf=np.nan, capex=np.nan, debt=np.nan, cash=np.nan, gp=np.nan)
        t, five = a.iloc[-1], a.tail(5)
    reit = kind == "reit"
    return out | {
        "years": len(a), "fy_latest": t["period"], "roe_latest": float(roe.iloc[-1]) if pd.notna(roe.iloc[-1]) else None,
        "roe_avg_5y": float(roe.tail(5).mean()), "roe_avg_10y": float(roe.tail(10).mean()),
        "gross_margin_avg_5y": float((five["gp"] / five["revenue"]).mean()), "net_margin_avg_5y": float((five["ni"] / five["revenue"]).mean()),
        "fcf_5y": None if (f := fcf(five)) is None else float(f.sum()),
        "ocf_to_profit_5y": None if reit else div(five["ocf"].sum(min_count=1), five["ni"].sum()),
        "capex_to_ocf_5y": div(five["capex"].sum(min_count=1), five["ocf"].sum(min_count=1)), "loss_years_10y": int((a.tail(10)["ni"] < 0).sum()),
        "net_debt": None if val(t, "debt") is None else val(t, "debt") - (val(t, "cash") or 0),
        "net_debt_to_ebitda": None if reit else div(None if val(t, "debt") is None else val(t, "debt") - (val(t, "cash") or 0), ebitda),
        "interest_cover": div(operating, val(t, "interest")) if (val(t, "interest") or 0) > 0 and not reit else None,
        "debt_to_equity": div(val(t, "debt"), val(t, "equity")), "goodwill_to_equity": div(val(t, "goodwill"), val(t, "equity")),
        "sbc_to_revenue": div(val(t, "sbc"), val(t, "revenue"))}


def stats(series: pd.Series, now: float | None) -> dict:
    """The current multiple against its own history: mean, spread, range, percentile, and era-alpha's 3-sigma test."""
    s = series.dropna()
    s = s[s > 0]
    if len(s) < 12 or now is None or now <= 0:
        return {"now": now, "months": len(s)}
    mean, sd, recent = float(s.mean()), float(s.std()), series.tail(60).dropna()
    recent = recent[recent > 0]
    return {"now": now, "months": len(s), "mean": mean, "median": float(s.median()), "sd": sd, "min": float(s.min()), "max": float(s.max()),
            "median_5y": float(recent.median()) if len(recent) >= 12 else None,
            "pct": float((s < now).mean()), "above_3sd": now > mean + 3 * sd}


def split_basis(a: pd.DataFrame, splits: pd.DataFrame) -> pd.Series:
    """Each fiscal year's share count on today's split basis. Filings restate the years they repeat after a split and
    leave older ones (Apple's 4:1 of 2020: FY2019 17.8bn, FY2018 4.75bn), so a fall back in time by close to a later
    split's ratio (within 20%) marks the years before it as not yet adjusted."""
    s, ratios = a["shares"].astype(float).copy(), list(splits["ratio"]) if splits is not None and len(splits) else []
    for i in range(len(s) - 1, 0, -1):
        jump = s.iloc[i] / s.iloc[i - 1] if s.iloc[i - 1] else math.nan
        r = next((r for r in ratios if r >= 1.5 and abs(jump / r - 1) < 0.2), None)
        if r:
            s.iloc[:i] *= r
    return s


def cn_shares(a: pd.DataFrame, latest: pd.Series, today_shares: float, bonuses: list) -> pd.Series:
    """CN fiscal years' share counts on today's basis: Eastmoney's TOTAL_SHARE repeats today's count on every year
    (Hengrui: 6.64bn back to 2015), so each year's 股本 (share capital, par 1 for most) x the bonus shares (送转) that
    went ex after its end, scaled to today's count by the latest report's 股本 (shares issued since the last fiscal
    year, as China Shenhua's in 2026, stay out of the years before)."""
    cap = a["share_capital"].astype(float)
    later = lambda end: math.prod(1 + b for d, b in bonuses if d > end)
    if cap.isna().all() or not latest.get("share_capital"):
        return a["shares"].astype(float)
    scale = today_shares / (latest["share_capital"] * later(latest["period"]))
    return (cap * a["period"].map(later) * scale).fillna(a["shares"].astype(float))


def own_multiples(monthly: pd.DataFrame, a: pd.DataFrame, quote: str, report: str, splits: pd.DataFrame) -> pd.DataFrame:
    """Month-end P/E, P/B and P/S from the split-adjusted closes x the fiscal year's share count on today's split basis
    over its profit, equity and revenue, each year public from its filing date (else 90 days after its end), in the
    reporting currency at each month's rate (yahoo.cny_per; today's rate where that history has no such currency)."""
    later = lambda month: math.prod(r for d, r in zip(splits["date"], splits["ratio"]) if d[:7] > month) if len(splits) else 1
    m = monthly.assign(day=pd.to_datetime(monthly["month"]) + pd.offsets.MonthEnd(0),
                       close=monthly["close"] / monthly["month"].map(later)).sort_values("day")
    y = a.assign(shares=split_basis(a, splits).values,
                 avail=pd.to_datetime(a["notice"].where(a["notice"].notna() & (a["notice"] != ""),
                                                        (pd.to_datetime(a["period"]) + timedelta(days=90)).dt.strftime("%Y-%m-%d"))))
    y = y.dropna(subset=["shares"]).sort_values("avail")
    df = pd.merge_asof(m, y[["avail", "shares", "ni", "equity", "revenue"]], left_on="day", right_on="avail").dropna(subset=["shares"])
    rate = 1.0
    if quote != report:
        days = df["day"].dt.strftime("%Y-%m-%d")
        rate = (yahoo.cny_per(pd.Series(quote, index=df.index), days) / yahoo.cny_per(pd.Series(report, index=df.index), days))
        fx = yahoo.load_fx()
        rate = rate.fillna(fx.get(report, np.nan) / fx.get(quote, np.nan))
    cap = df["close"] * df["shares"] * rate
    return pd.DataFrame({"month": df["month"], "pe": cap / df["ni"].where(df["ni"] > 0), "pb": cap / df["equity"],
                         "ps": cap / df["revenue"]})


def snapshot(market: str, today: date) -> pd.DataFrame:
    days = sorted(p.name for p in (DATA / "snapshots").glob("????-??-??") if p.name <= today.isoformat()
                  and (p / f"{market}.csv.gz").exists())
    if not days:
        return pd.DataFrame()
    return pd.read_csv(DATA / "snapshots" / days[-1] / f"{market}.csv.gz", dtype={"code": str}).copy().assign(snap_date=days[-1])


def fifth(rank, n) -> str:
    return "偏多" if rank <= n / 5 else "偏空" if rank > 4 * n / 5 else "中性"


def peers(snap: pd.DataFrame, code: str, industry: str | None, mcap: float | None) -> dict:
    """The same industry in the day's snapshot (its sector when fewer than 3 share it), nearest in market value, with the
    group's medians: industry-research's peers table."""
    if snap.empty or not industry:
        return {}
    group = snap[snap["industry"] == industry]
    by = "industry"
    if len(group[group["code"] != code]) < 3 and "sector" in snap and len(snap.loc[snap["code"] == code, "sector"]):
        group, by = snap[snap["sector"] == snap.loc[snap["code"] == code, "sector"].iloc[0]], "sector"
    cols = ["code", "name", "mcap", "pe", "pb", "ps", "roe", "rev_growth", "np_growth", "gross_margin", "div_yield", "score_rank"]
    g = group.reindex(columns=cols)
    others = g[g["code"] != code]
    if mcap and others["mcap"].notna().any():
        others = others.assign(d=(np.log(others["mcap"]) - math.log(mcap)).abs()).sort_values("d").drop(columns="d")
    med = g[["pe", "pb", "ps", "roe", "rev_growth", "gross_margin", "div_yield"]].where(lambda x: x > 0).median()
    n = len(snap)
    rows = others.head(CONFIG["research"]["peers"]).assign(view=lambda d: [fifth(r, n) if pd.notna(r) else None for r in d["score_rank"]])
    return {"by": by, "group": industry if by == "industry" else group["sector"].iloc[0], "count": len(g),
            "median": med.replace({np.nan: None}).to_dict(), "peers": rows.replace({np.nan: None}).to_dict("records")}


def industry_history(industry: str) -> list[dict]:
    """CN: the industry's median PE-TTM (profitable members) and PB-MRQ at each half-year end since 2018-12, for today's
    members of its 申万 industry (Eastmoney's BOARD_NAME; today's listings only)."""
    quotes = pd.read_csv(DATA / "quotes" / "cn.csv.gz", dtype={"code": str})
    members = set(quotes.loc[quotes["industry"] == industry, "code"])
    v = pd.read_csv(DATA / "history" / "cn_valuation.csv.gz", dtype={"code": str, "period": str})
    v = v[v["code"].isin(members)]
    g = v.groupby("period")
    out = pd.DataFrame({"pe_median": g["pe_ttm"].apply(lambda s: s[s > 0].median()), "pb_median": g["pb_mrq"].median(),
                        "members": g.size()}).reset_index()
    return out.replace({np.nan: None}).to_dict("records")


def screening(market: str, code: str, snap: pd.DataFrame, today: date, listed: str | None, kind: str) -> dict:
    """The daily screening's view: its rating when on the market's newest lists; else its fifth of the market's score
    with the four family grades; else outside its universe, with the reason code can tell."""
    picks = pd.read_csv(DATA / "picks.csv", dtype=str)
    picks = picks[(picks["market"] == market) & picks["bucket"].isin(RATING)]
    newest = picks[picks["date"] == picks["date"].max()]
    hit = newest[newest["ticker"] == code]
    row = snap[snap["code"] == code] if len(snap) else snap
    view = {"lists_date": newest["date"].max() if len(newest) else None, "snapshot": snap["snap_date"].iloc[0] if len(snap) else None}
    if len(row):
        r = row.iloc[0]
        view |= {"in_universe": True, "score": r["score"], "score_rank": int(r["score_rank"]), "universe": len(snap),
                 "fifth": fifth(r["score_rank"], len(snap)), "why": r.get("why"), "weak": r.get("weak"), "risk": r.get("risk")}
        view |= {k: r.get(k) for k in ("g_value", "g_quality", "g_growth", "g_momentum", "f_value", "f_quality", "f_growth", "f_momentum")}
    else:
        reason = f"not among the market's {CONFIG['universe']['top_n']} largest liquid ordinary shares listed over a year"
        if listed and (today - date.fromisoformat(listed)).days < CONFIG["universe"]["min_listing_days"]:
            reason = f"listed on {listed}, under the screening's {CONFIG['universe']['min_listing_days']} days"
        elif market == "hk" and kind == "reit":
            reason = "HK REITs are trust units, not ordinary shares: outside the screening's universe"
        elif market == "cn" and code.startswith(("4", "8", "92")):
            reason = "北交所 listings are outside the screening's universe"
        view |= {"in_universe": False, "reason": reason}
    if len(hit):
        view |= {"rating": RATING[hit.iloc[0]["bucket"]], "list_rank": hit.iloc[0]["rank"]}
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in view.items()}


def compare(ours, other, agree: float, large: float) -> dict:
    if ours is None or other is None or pd.isna(ours) or pd.isna(other):
        return {"ours": ours, "other": other, "status": "single source"}
    g = abs(other - ours) / abs(ours) if ours else math.inf
    g = g if np.sign(ours) == np.sign(other) else math.inf
    return {"ours": ours, "other": other, "gap": g, "status": "agree" if g <= agree else "differ" if g <= large else "large gap"}


def crosscheck(a: pd.DataFrame, second: pd.DataFrame | None, financial: bool) -> tuple[dict, pd.DataFrame]:
    """The latest fiscal year both sources report (period ends within 10 days), figure by figure. financial-data: a
    figure more than 5% off isn't used, so that year's figure is left out of the calculations (a gap in equity or assets
    leaves out the year's whole balance sheet: Eastmoney keeps later reports' restated comparatives, China Shenhua's
    2025 assets CNY 904bn against the annual report's 628bn). A bank's or insurer's revenue is the exception: each
    source defines it its own way (crosscheck.py's known structural gap), so it is kept and labelled."""
    cfg, out, a = CONFIG["crosscheck"], {}, a.copy()
    if second is None or not len(second):
        return out, a
    s = second.assign(day=pd.to_datetime(second["period"]))
    for i in range(len(a) - 1, -1, -1):
        row = a.iloc[i]
        near = s[(s["day"] - pd.Timestamp(row["period"])).abs() <= pd.Timedelta(days=10)]
        if len(near):
            o = near.iloc[-1]
            out = {"fiscal_year": row["period"], "source2": "Yahoo"} | {
                k: compare(val(row, k), val(o, k), cfg["agree"], cfg["large"]) for k in CHECK}
            if financial and out["revenue"]["status"] == "large gap":
                out["revenue"]["status"] = "definition"
            gaps = [k for k in CHECK if out[k]["status"] == "large gap"]
            out["left_out"] = (BALANCE if {"equity", "assets"} & set(gaps) else []) + [k for k in gaps if k not in BALANCE]
            a.loc[a.index[i], out["left_out"]] = np.nan
            break
    return out, a


def quote_check(quote: dict, tencent: dict) -> dict:
    """Today's price and market value against Tencent's quote."""
    cfg = CONFIG["crosscheck"]
    return {k: compare(quote.get(q), tencent.get(q), cfg["agree"], cfg["large"])
            for k, q in (("price", "price"), ("market_cap", "mcap"))}
