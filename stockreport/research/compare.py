"""Research stage 11, part 2: the research rating against the daily screening and our target against the street's
(PLAN.md "Against the daily screening", "Valuation and target price"), and the forecast table against the consensus.
- Agreement, by code: 一致, 部分一致 (one step apart), 相反 (Buy against Sell or 偏空, or the reverse). The screening's
  view is its rating when the stock is on the day's lists, else its fifth of the market's score (偏多 / 中性 / 偏空).
- Drivers, named from how the two are built: momentum and revisions weigh in the screening and not in a valuation; the
  screening ranks within the sector and research against the whole market; a fast grower's 10 years of cash flows
  against trailing and next-year figures; a cyclical's normalized against current earnings; news or filings the numbers can't see (the review's findings).
- The street: what its target needs in our DCF (the cost of capital, 5-year revenue growth, long-run margin) or, for
  a financial, the ROE it implies, against ours; the adjusted (non-GAAP) basis.
Each driver is a sentence with fact keys ({wacc}); words.py fills them in and DeepSeek writes the paragraph from them.
- The rating's basis (stage 15; page 1 and the WeChat summary, by code): the return the price implies against the
  market's, the methods' state (unresolved: what the cross-check would need in the main method's terms), the checks
  that blocked a Buy or widened the band, the tail scenarios and the absolute view."""

from stockreport.research import CUR, pct, price, times
from stockreport.research.rating import ABSOLUTE

VIEW = {"买入": 1, "偏多": 1, "持有": 0, "中性": 0, "卖出": -1, "偏空": -1}
METHOD = {"dcf": "现金流折现", "dcf_normal": "正常化现金流折现", "pe_own": "自身历史市盈率", "pe_peers": "同行市盈率",
          "pe_normal": "正常化盈利的市盈率", "pb_own": "自身历史市净率", "pb_roe": "平均 ROE 的超额收益模型",
          "evs_peers": "同行企业价值/销售额", "peg_peers": "同行 PEG", "ddm": "股息折现", "yield_own": "自身 5 年平均股息率",
          "excess_return": "超额收益模型"}
CHECK = {"quality_screen": "去劣筛选", "checklist_veto": "买入前清单", "dividend_uncovered": "股息的现金覆盖",
         "beneish": "Beneish M 值", "earnings_signals": "财报异常信号"}
SIGNAL = {"receivables_faster": "应收快于营收", "inventory_faster": "存货快于营收", "cash_below_profit_widening": "现金流低于利润且差距扩大"}
QUALITY = {"roe_10y": "10 年平均 ROE", "fcf_5y": "5 年自由现金流", "interest_cover": "利息保障倍数", "gross_margin_avg": "长期毛利率",
           "ocf_to_profit_5y": "经营现金流 / 净利润", "net_margin_avg": "长期净利率", "share_growth_5y": "5 年股本扩张"}
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
            "scr_quality": ("筛选质量评级", sc.get("g_quality") or "-"),
            "scr_momentum": ("筛选动量评级", sc.get("g_momentum") or "-"),
            "scr_rank": ("筛选排名", f"第 {sc['score_rank']} 名（共 {sc['universe']} 只）" if sc.get("score_rank") else "-"),
            "ind_pe": ("同行市盈率中位数", times(peers.get("pe"))), "mkt_pe": ("全市场市盈率中位数", times(market_pe))}
    drivers = []
    if agreement and agreement != "一致":
        d, g = r - s, {k: sc.get(f"g_{k}") or "" for k in ("value", "quality", "momentum")}  # the screening's three
        if d < 0 and g["momentum"] in "AB" and g["momentum"] or d > 0 and g["momentum"] in ("D", "E"):
            drivers.append("动量：筛选的三项里动量（股价或业绩超预期、利润和营收增长、分析师上调）占三分之一，该股动量评级 {scr_momentum}；"
                           "研究的估值不看动量")
        expensive_sector = peers.get("pe") and market_pe and peers["pe"] > 1.2 * market_pe
        cheap_sector = peers.get("pe") and market_pe and peers["pe"] < 0.8 * market_pe
        if d < 0 and g["value"] in ("A", "B") or d > 0 and g["value"] in ("D", "E") or expensive_sector or cheap_sector:
            drivers.append("比较对象：筛选在同行业内排名（该股价值评级 {scr_value}），研究对比全市场和自身的现金流；"
                           "同行市盈率中位数 {ind_pe}，全市场 {mkt_pe}")
        if d < 0 and g["quality"] == "A":
            drivers.append("质量：筛选看重这一项（质量评级 {scr_quality}，含 5 年利润增长），研究看现价是否已经反映（合理价值的超额回报 {fair_excess}）")
        if d > 0 and g["quality"] in ("D", "E"):
            drivers.append("质量：筛选里这一项偏弱（质量评级 {scr_quality}），研究看现价相对价值（合理价值的超额回报 {fair_excess}）")
        if findings:
            drivers.append("公告和新闻：本报告的审核读到" + "、".join(dict.fromkeys(x["words"] for x in findings[:3])) +
                           "，这是筛选的数字看不到的")
        if kind == "fast_grower":
            drivers.append("快速成长：筛选看当前和明年的数字，研究看十年现金流，增长能持续多久决定价值")
        if kind == "cyclical":
            drivers.append("周期：研究用正常化利润（自身 10 年平均资本回报率乘现有资本，一致预期年份高出的部分另计），筛选用当前利润，周期高点时两者差得最远")
        if not drivers:
            drivers.append("估值：研究的合理价值超额回报 {fair_excess}，筛选的价值项只占三分之一（价值评级 {scr_value}）")
    return {"view": view, "agreement": agreement, "drivers": drivers, "keys": keys,
            "reason": None if sc.get("in_universe") else sc.get("reason")}


def street(facts: dict, val: dict) -> list[str]:
    """Why our target differs from the street's: the drivers whose gap is material, most relevant first."""
    st, k = val.get("street") or {}, val.get("inputs") or {}
    if not st.get("target") or val.get("fair_value") is None:
        return []
    need, rev, kind = st.get("implied") or {}, val.get("reverse") or {}, val["type"]
    out = ["差距：我们的合理价值 {fair_value}，市场一致目标价 {street_target}，我们相对市场 {ours_vs_street}",
           "时间：卖方的 12 个月目标价默认一年内到达合理价值；我们按约 3 年靠拢，12 个月目标价 {target} 只计入三分之一的差距"]
    d = (val.get("methods") or {}).get("dcf") or (val.get("methods") or {}).get("dcf_normal")
    if kind in ("bank", "insurer", "broker") and need.get("implied_roe") is not None:
        out.append("回报率：市场的目标价对应长期 ROE {street_roe}（按我们的股权成本 {cost_equity}），我们假设长期 ROE {roe_term}；"
                   "现价隐含的股权成本是 {implied_coe}")
    margin = need.get("implied_margin")
    if d and margin is not None and abs(margin - d["path"]["target_margin"]) >= 0.03:
        out.append("利润率：我们的现金流折现要达到市场的目标价，长期营业利润率需要 {street_margin}，我们用 {target_margin}（{margin_source}）")
    if d and need.get("implied_growth_5y") is not None and val.get("forecast_growth_5y") is not None \
            and abs(need["implied_growth_5y"] - val["forecast_growth_5y"]) >= 0.03:
        out.append("增长：市场的目标价需要未来 5 年营收每年增长 {street_growth}（其余假设不变），我们预测 {forecast_growth}；"
                   "同等规模的公司里能做到的占 {base_street}")
    if d and need.get("implied_wacc") is not None and k.get("wacc") and abs(need["implied_wacc"] - k["wacc"]) >= 0.01:
        out.append("折现率：市场的目标价相当于资本成本 {street_wacc}，我们用 {wacc}（无风险利率 {rf} 加大盘现价隐含的股权风险溢价 {erp}，"
                   "按本模型的现金流规则求出）；现价隐含 {implied_wacc}")
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
        for g in er["growth"][:3]:
            book *= 1 + g
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


def needs(x: dict, main: str, shares: dict) -> str:
    """What the main method would need to reach a cross-check's value, in its own terms (with the base rate: the share
    of companies of the same size that grew that fast)."""
    n, share = x.get("needs") or {}, shares.get(x["method"])
    if main in ("dcf", "dcf_normal"):
        parts = ([f"未来 5 年营收每年增长 {pct(n['implied_growth_5y'], True)}" + (f"（同等规模公司中做到的占 {pct(share, digits=0)}）"
                  if share is not None else "")] if n.get("implied_growth_5y") is not None else []) + \
                ([f"长期营业利润率 {pct(n['implied_margin'])}"] if n.get("implied_margin") is not None else [])
        return "或".join(parts)
    if main in ("excess_return", "pb_roe") and n.get("implied_roe") is not None:
        return f"长期 ROE {pct(n['implied_roe'])}"
    if main == "ddm" and n.get("implied_dividend_growth_5y") is not None:
        return f"未来 5 年股息每年增长 {pct(n['implied_dividend_growth_5y'], True)}"
    return ""


LEVEL = {"low": "低", "medium": "中", "high": "高", "very high": "很高", "extreme": "极高"}  # Morningstar's levels
MARKET = {"cn": "A股", "hk": "港股", "us": "美股"}  # the market whose members a stock's group is drawn from


def threshold(v: dict) -> str:
    """Price over fair value against the level's two sides (stage 18: Morningstar's table)."""
    u, r = v["uncertainty"], v.get("price_to_fair")
    return (f"现价相当于合理价值的 {r:.2f} 倍" if r is not None else "合理价值为零") + \
        f"；不确定性{LEVEL[u['level']]}，{1 - u['discount']:.2f} 倍以下买入、{1 + u['premium']:.2f} 倍以上卖出"


def basis(f: dict, v: dict, index: str) -> list[str]:
    """The rating's basis on page 1, each line by code with its figures."""
    if v.get("target") is None:
        return []
    k, rv, q = v.get("inputs") or {}, v.get("reverse") or {}, v["currency"]
    out = [provisional(v["provisional"])] if v.get("provisional") else []
    mk, u, main = k.get("market") or {}, v["uncertainty"], v["main"]
    shares = (v.get("base_rates") or {}).get("share_at_least") or {}
    r = rv.get("implied_return")
    implied = (f"现价隐含年回报 {pct(r) if r is not None else '低于 1%'}，" if main in ABSOLUTE else "")
    home = {True: "内地", False: "非内地"}.get(mk.get("china"), "")
    place = MARKET.get(k.get("priced_in"), index) + "中"
    group = home + {True: "金融股", False: "非金融公司"}.get(mk.get("financial"), "成分")
    out += [implied + f"要求回报 {pct(k['cost_equity'])}（{place}{group}现价隐含的股权风险溢价 "
           f"{pct(k['erp_market'])}" + (f"，国别风险差 {pct(k['crp'], True)}" if abs(k.get("crp") or 0) >= 0.0005 else "") +
           f"，加无风险利率 {pct(k['rf'], digits=2)}）；按{METHOD[main]}，合理价值的超额回报 {pct(v['fair_excess'], True)}，{threshold(v)}"
           if mk.get("r") is not None else f"大盘的隐含回报未能求出，用 Damodaran 公布的股权风险溢价 {pct(k['erp'])}"]
    gp = k.get("groups") or {}
    if mk.get("r") is not None and mk.get("financial") is not None and gp.get("financial") and gp.get("other"):
        out.append(f"分组比较：{place}{home}金融股现价隐含年回报 {pct(gp['financial'])}，{home}其他公司 {pct(gp['other'])}。两组的差距是"
                   f"市场对行业的定价（金融股按账面估值），本股只和{group}比，不替市场判断哪一组更便宜")
    if v.get("fcfe_payout") is not None:  # the income type valued on its free cash flow (Damodaran's 80-110% rule)
        out.append(f"近 5 年股息为股权自由现金流的 {pct(v['fcfe_payout'], digits=0) if v['fcfe_payout'] != float('inf') else '无穷倍'}"
                   f"（Damodaran：低于 80% 或高于 110% 时不用股息折现，留存的现金也属于股东），合理价值由{METHOD[main]}给出")
    for m in v.get("main_skipped") or []:
        out.append(f"{METHOD[m]}给不出正的价值（股权价值为负按 0 计），合理价值由{METHOD[main]}给出")
    if v["state"] == "unresolved":
        x = max(v["cross"], key=lambda c: abs(c["gap"] - v["fair_excess"]))
        need = needs(x, main, shares)
        out.append(f"方法分歧未决：{METHOD[main]}看{v['main_view']}，交叉检验看{v['checks_view']}（{METHOD[x['method']]} "
                   f"{price(x['target'], q)}）" + (f"；{METHOD[main]}要达到它，需要{need}" if need else "") +
                   "。分歧不靠平均消除，评级持有，等待能分出对错的数据")
    else:
        far = [c for c in v.get("cross") or [] if c["view"] != v["main_view"]]
        for x in far[:1]:
            need = needs(x, main, shares)
            out.append(f"交叉检验：{METHOD[x['method']]} {price(x['target'], q)}（看{x['view']}）" +
                       (f"；{METHOD[main]}要达到它，需要{need}" if need else ""))
    for a in (v.get("acts") or {}).get("block") or []:
        if v["state"] == "blocked":
            out.append(f"{CHECK[a['check']]}：{explain(a, f)}，不给买入（{METHOD[main]}看买入）")
    for a in (v.get("acts") or {}).get("widen") or []:
        out.append(f"{CHECK[a['check']]}：{explain(a, f)}，不确定性上调一档至{LEVEL[u['level']]}")
    lag = v.get("forecast_lag")
    if lag:  # sluggish forecasts (Guay, Kothari and Shu 2011): the implied return leans on a consensus not yet revised
        out.append(f"近 3 个月股价 {pct(lag['price_3m'], True)}，{lag['year']} 年一致预期同期 {pct(lag['revision_3m'], True)}，"
                   f"两者背离 {pct(abs(lag['gap']), digits=0)}：分析师预测调整慢于股价，现价隐含回报可能"
                   + ("因预测尚未下调而偏高" if lag["gap"] < 0 else "因预测尚未上调而偏低") + "（Guay、Kothari 和 Shu 2011），评级可能随预测修正而变动")
    for t in v.get("tail") or []:
        line = {"vie": "VIE（协议控制）结构失效", "delisting": "美国退市"}[t["risk"]]
        if t["value"] is None:
            out.append(f"尾部情景：{line}——美国存托股可转换为港股 {t['line']}，不按价值损失计")
        elif t.get("breakeven") is not None:
            out.append(f"尾部情景：{line}，以价值归零为界；一年内发生的概率超过 {pct(t['breakeven'], digits=0)} 时，评级会降一档")
        else:
            out.append(f"尾部情景：{line}，以价值归零为界（已是卖出）")
    a = v.get("absolute") or {}
    if a.get("fair_value") is not None:
        out.append(f"绝对视角（Damodaran 公布的股权风险溢价 {pct(a['erp'])}、行业贝塔 {k['beta']:.2f}，股权成本 {pct(a['cost_equity'])}）："
                   f"合理价值 {price(a['fair_value'], q)}，超额回报 {pct(a['gap'], True)}，看{a['view']}")
    return out


def provisional(p: dict) -> str:
    """Results released after the fact sheet's figures (judge.release): the rating is provisional (暂定)."""
    what = f"{p['date']} 发布了新的业绩（{p['title']}）" if p.get("title") else f"下次财报日 {p['date']} 已过"
    return f"评级暂定：{what}，本报告的财务数据截至 {p['period']}，早于这次发布；新的定期报告读入后评级会更新"


def explain(a: dict, f: dict) -> str:
    """A check's finding in words."""
    c = f["checks"]
    if a["check"] == "quality_screen":
        return "未通过：" + "、".join(QUALITY.get(x, x) for x in c["quality_screen"]["failed"])
    if a["check"] == "earnings_signals":
        e = c.get("earnings_signals") or {}
        return "、".join(SIGNAL[x] for x in SIGNAL if e.get(x))
    if a["check"] == "beneish":
        return f"{c['beneish']['m_score']:.2f}，高于 -1.78（快速增长也会抬高它）"
    if a["check"] == "checklist_veto":
        return "自由现金流连续 3 年为负"
    return f"近 5 年有 {c['income']['uncovered_years_5y']} 年股息高于自由现金流"
