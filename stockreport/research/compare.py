"""Research stage 11, part 2: the research rating against the daily screening and our target against the street's
(PLAN.md "Against the daily screening", "Valuation and target price"), and the forecast table against the consensus.
- Agreement, by code: 一致, 部分一致 (one step apart), 相反 (Buy against Sell or 偏空, or the reverse). The screening's
  view is its rating when the stock is on the day's lists, else its fifth of the market's score (偏多 / 中性 / 偏空).
- Drivers, named from how the two are built: momentum and revisions weigh in the screening and not in a valuation; the
  screening ranks within the sector and research against the whole market; a fast grower's 10 years of cash flows
  against trailing and next-year figures; a cyclical's normalized against current earnings; a floored cost of equity;
  news or filings the numbers can't see (the review's findings).
- The street: what its target needs in our DCF (the cost of capital, 5-year revenue growth, long-run margin) or, for
  a financial, the ROE it implies, against ours; the adjusted (non-GAAP) basis; the floor.
Each driver is a sentence with fact keys ({wacc}); words.py fills them in and DeepSeek writes the paragraph from them."""

from stockreport.research import CUR, pct, times

VIEW = {"买入": 1, "偏多": 1, "持有": 0, "中性": 0, "卖出": -1, "偏空": -1}
MARGIN_SOURCE = {"10-year average": "自身 10 年平均", "profitable peers' median": "盈利同行的中位数", "industry": "行业平均",
                 "own 8-year median": "自身 8 年中位数"}


def screening(facts: dict, val: dict, market_pe: float | None, findings: list[dict] | None = None) -> dict:
    """{view, agreement, drivers, keys}: the screening's view, the agreement and the drivers of a difference (findings:
    the report's own review's, which the screening's numbers can't see)."""
    sc, rating, kind = facts["screening"], val["rating"], val.get("type")
    view = sc.get("rating") or (sc.get("fifth") if sc.get("in_universe") else None)
    r, s = VIEW.get(rating) if rating in ("买入", "持有", "卖出") else None, VIEW.get(view)
    agreement = None if r is None or s is None else ("一致", "部分一致", "相反")[abs(r - s)]
    peers = (facts.get("peers") or {}).get("median") or {}
    keys = {"scr_view": ("筛选的看法", view or "不在筛选范围"), "scr_value": ("筛选价值评级", sc.get("g_value") or "-"),
            "scr_quality": ("筛选质量评级", sc.get("g_quality") or "-"), "scr_growth": ("筛选成长评级", sc.get("g_growth") or "-"),
            "scr_momentum": ("筛选动量评级", sc.get("g_momentum") or "-"),
            "scr_rank": ("筛选排名", f"第 {sc['score_rank']} 名（共 {sc['universe']} 只）" if sc.get("score_rank") else "-"),
            "ind_pe": ("同行市盈率中位数", times(peers.get("pe"))), "mkt_pe": ("全市场市盈率中位数", times(market_pe))}
    drivers = []
    if agreement and agreement != "一致":
        d, g = r - s, {k: sc.get(f"g_{k}") or "" for k in ("value", "quality", "growth", "momentum")}
        if d < 0 and g["momentum"] in "AB" and g["momentum"] or d > 0 and g["momentum"] in ("D", "E"):
            drivers.append("动量：筛选的四项里动量（近期涨跌和分析师上调）占四分之一，该股动量评级 {scr_momentum}；研究的估值不看动量")
        expensive_sector = peers.get("pe") and market_pe and peers["pe"] > 1.2 * market_pe
        cheap_sector = peers.get("pe") and market_pe and peers["pe"] < 0.8 * market_pe
        if d < 0 and g["value"] in ("A", "B") or d > 0 and g["value"] in ("D", "E") or expensive_sector or cheap_sector:
            drivers.append("比较对象：筛选在同行业内排名（该股价值评级 {scr_value}），研究对比全市场和自身的现金流；"
                           "同行市盈率中位数 {ind_pe}，全市场 {mkt_pe}")
        if d < 0 and "A" in (g["quality"], g["growth"]):
            drivers.append("质量和成长：筛选看重这两项（质量 {scr_quality}、成长 {scr_growth}），研究看现价是否已经反映（预期超额回报 {excess_return}）")
        if d > 0 and {"D", "E"} & {g["quality"], g["growth"]}:
            drivers.append("质量和成长：筛选里这两项偏弱（质量 {scr_quality}、成长 {scr_growth}），研究看现价相对价值（预期超额回报 {excess_return}）")
        if findings:
            drivers.append("公告和新闻：本报告的审核读到" + "、".join(dict.fromkeys(x["words"] for x in findings[:3])) +
                           "，这是筛选的数字看不到的")
        if kind == "fast_grower":
            drivers.append("快速成长：筛选看当前和明年的数字，研究看十年现金流，增长能持续多久决定价值")
        if kind == "cyclical":
            drivers.append("周期：研究用正常化利润（{target_margin} 的长期利润率），筛选用当前利润，周期高点时两者差得最远")
        if ((val.get("inputs") or {}).get("floor") or {}).get("applied"):
            drivers.append("资本成本：研究用行业隐含的股权成本 {cost_equity}（CAPM 为 {capm_cost_equity}），市场多年来按这个水平定价")
        if not drivers:
            drivers.append("估值：研究的预期超额回报 {excess_return}，筛选的价值项只占四分之一（价值评级 {scr_value}）")
    return {"view": view, "agreement": agreement, "drivers": drivers, "keys": keys,
            "reason": None if sc.get("in_universe") else sc.get("reason")}


def street(facts: dict, val: dict) -> list[str]:
    """Why our target differs from the street's: the drivers whose gap is material, most relevant first."""
    st, k = val.get("street") or {}, val.get("inputs") or {}
    if not st.get("target") or val.get("target") is None:
        return []
    need, rev, kind = st.get("implied") or {}, val.get("reverse") or {}, val["type"]
    out = ["差距：我们的目标价 {target}，市场一致目标价 {street_target}，我们相对市场 {ours_vs_street}"]
    d = (val.get("methods") or {}).get("dcf") or (val.get("methods") or {}).get("dcf_normal")
    if kind in ("bank", "insurer", "broker") and need.get("implied_roe") is not None:
        out.append("回报率：市场的目标价对应长期 ROE {street_roe}（按我们的股权成本 {cost_equity}），我们假设长期 ROE {roe_term}；"
                   "现价隐含的股权成本是 {implied_coe}")
    if k.get("floor", {}).get("applied"):
        out.append("资本成本：中资银行和保险用行业隐含的股权成本 {cost_equity}，不用 CAPM 的 {capm_cost_equity}")
    margin = need.get("implied_margin")
    if d and margin is not None and abs(margin - d["path"]["target_margin"]) >= 0.03:
        out.append("利润率：我们的现金流折现要达到市场的目标价，长期营业利润率需要 {street_margin}，我们用 {target_margin}（{margin_source}）")
    if d and need.get("implied_growth_5y") is not None and val.get("forecast_growth_5y") is not None \
            and abs(need["implied_growth_5y"] - val["forecast_growth_5y"]) >= 0.03:
        out.append("增长：市场的目标价需要未来 5 年营收每年增长 {street_growth}（其余假设不变），我们预测 {forecast_growth}；"
                   "同等规模的公司里能做到的占 {base_street}")
    if d and need.get("implied_wacc") is not None and k.get("wacc") and abs(need["implied_wacc"] - k["wacc"]) >= 0.01:
        out.append("折现率：市场的目标价相当于资本成本 {street_wacc}，我们用 {wacc}（无风险利率 {rf} 加股权风险溢价 {erp} 乘贝塔 {beta}）；"
                   "现价隐含 {implied_wacc}")
    c = facts["consensus"]
    if facts["market"] == "us" and kind != "reit" and (  # a REIT's consensus is FFO by convention (stage 9's note)
            (c.get("basis_gap_yahoo") or 0) > 0.2 or (facts["summary"].get("sbc_to_revenue") or 0) > 0.1):
        out.append("口径：市场常用经调整（非 GAAP）利润，不计股权激励（占营收 {sbc_to_revenue}），我们把它算作成本")
    if rev.get("implied_dividend_growth_5y") is not None and kind in ("income", "reit"):
        out.append("股息：现价对应未来 5 年股息每年增长 {implied_div_growth}，我们按一致预期的盈利和 5 年派息率")
    out.append("市场一致目标价普遍偏乐观：12 个月到期时，卖方目标价能达到的只有{target_hit_rate}（Bradshaw、Brown 和 Huang，2013）")
    return out


def forecast(facts: dict, val: dict) -> dict:
    """Three forward years (12-month windows from where the trailing figures end): ours from the valuation's own
    paths, and the consensus by fiscal year beside it. Amounts in the reporting currency."""
    cons, m, k = val.get("consensus") or {}, val.get("methods") or {}, val.get("inputs") or {}
    start = cons.get("from")
    if not start or val.get("target") is None:
        return {}
    y, mo = int(start[:4]), int(start[5:7])
    cols = [f"{y + i}-{mo:02d} 至 {y + i + (mo + 10) // 12}-{(mo + 10) % 12 + 1:02d}" for i in range(3)]
    eps, rows, shares = list(cons.get("eps") or []), [], k.get("shares")
    d = m.get("dcf") or m.get("dcf_normal")
    if d:
        yr = d["years"]
        rows += [("营业收入", yr["revenue"][:3], "money"), ("营业利润（EBIT）", yr["ebit"][:3], "money"),
                 ("税后经营利润", yr["nopat"][:3], "money"), ("公司自由现金流", yr["fcff"][:3], "money")]
        if len(eps) >= 2 and yr["nopat"][1] > 0:
            eps = eps[:2] + [eps[1] * yr["nopat"][2] / yr["nopat"][1]]
    er = m.get("excess_return")
    if er and shares:
        book, bvps = facts["valuation"]["book_common"], []
        for i, roe in enumerate(er["roe"][:3]):
            book += roe * book * (1 - er["payout"])
            bvps.append(book / shares)
        rows += [("ROE", er["roe"][:3], "pct"), ("每股净资产", bvps, "per")]
        if len(eps) >= 2:
            eps = eps[:2] + [er["roe"][2] * bvps[1]]
    if eps:
        rows.append(("每股收益（第 1-2 年为一致预期）", eps[:3], "per"))
    dd = m.get("ddm")
    if dd:
        rows.append(("每股股息", [dd["dividend"] * k.get("fx", 1) * (1 + dd["growth_5y"]) ** i for i in range(3)], "per"))
    c = facts["consensus"]
    fy = [{"year": yy, "eps": c["eps"][yy], "revenue": ((c.get("yahoo_years") or {}).get(yy) or {}).get("revenue")} for yy in sorted(c["eps"])]
    return {"columns": cols, "rows": rows, "currency": k.get("currency"), "unit": CUR.get(k.get("currency"), ""),
            "consensus": fy, "consensus_currency": c.get("currency"), "source": c.get("source"), "analysts": c.get("analysts"),
            "margin_source": MARGIN_SOURCE.get((d or {}).get("path", {}).get("margin_source"))}
