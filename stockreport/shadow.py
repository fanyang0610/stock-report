"""Valuation v2 in shadow mode (Phase 8, docs/REVIEW.md A2): the v2 engine runs next to v1 on the day's
snapshot, its columns (v2_*) are written into the snapshot, and the run prints the v2 lists, a v1/v2
comparison and v2's own answer on whether the profit of each name checks 1-2 excluded can last. The
report stays v1. The lists skip the AI swaps and the cross-market issuer dedupe."""

from datetime import date

import numpy as np
import pandas as pd

from stockreport import anchors, engine, history, regime
from stockreport.config import CONFIG
from stockreport.pick import BUCKETS

MOM_FLOOR = CONFIG["v2"]["momentum_floor"]  # buy floor on momentum z: "industry" (v1's z), "market" or "none"
MOM_WEIGHT = CONFIG["v2"]["momentum_weight"]  # weight of that momentum z next to the standardized buy key
# Phase 8 also asked buys for an expected return 2+ points above the required return (sells 2+ below). That
# favours short-duration stocks: the same 20-60% upside is ~2.4 points a year on a low P/B, ~1.1 on a high one,
# so MSFT (+37%) and META (+32%) failed it. Phase 9 review: off; the upside thresholds are the margin.
BUY_MIN_EXCESS, SELL_MAX_EXCESS = CONFIG["v2"].get("buy_min_excess"), CONFIG["v2"].get("sell_max_excess")
# Buys only among the largest companies (per market) and, in the US, among US listings: ranking by the largest
# estimated gaps picked noisy mid/small and foreign names (Phase 9 review: 13 of 15 buys outside the top 100).
BUY_LARGEST = CONFIG["v2"].get("buy_largest_n")  # {market: n} or None
BUY_HOME_ONLY = CONFIG["v2"].get("buy_home_only", False)

COLUMNS = ["archetype", "eps_core", "bps_c", "roe_cur", "roe_c3", "w_hist", "roe_norm", "structural_decline", "phi",
           "g0", "icc", "icc_final", "r_req", "r_mkt", "v_intrinsic", "v_used", "roe_implied", "v_peer", "v_own", "v_comb",
           "v_final", "upside", "dispersion", "n_anchors", "screen_fails", "dilution", "conf_points", "confidence",
           "theme", "break_dir", "break_keep", "break_confirmed", "roe_old", "roe_new", "p", "p_why", "v_new",
           "v_old", "v_regime", "p_market", "bucket", "rank", "tier", "conviction", "verdict"]


def themes(df: pd.DataFrame, market: str) -> pd.Series:
    """ai / ai_disrupted from the configured industry substrings (US: the Nasdaq industry before small
    industries were merged into '<sector> (other)')."""
    industry = df["industry"].fillna("")
    if market == "us":
        from stockreport.fetch import nasdaq
        listed = nasdaq.load_list().drop_duplicates("code").set_index("code")["industry"]
        industry = listed.reindex(df.index).fillna(industry)
    elif market == "hk":
        industry = industry + "-" + df["industry_type"].fillna("")
    tag = pd.Series("", df.index)
    for name, words in CONFIG["v2"]["themes"].items():
        tag[industry.str.contains("|".join(words), regex=True) & (tag == "")] = name
    return tag


def own_anchor(df: pd.DataFrame, h: pd.DataFrame, v: pd.DataFrame, market: str) -> pd.Series:
    """Median own P/B × today's book; the last 3 years only after a confirmed break. CN uses Eastmoney's
    P/B on both sides: price × median / today's P/B."""
    pb = h["own_pb_3y"].where(v["break_confirmed"] & h["own_pb_3y"].notna(), h["own_pb"])
    if market == "cn":
        return df["price"] * pb / df["pb_mrq_em"].where(df["pb_mrq_em"] > 0)
    return pb * v["bps_c"].where(v["bps_c"] > 0)


def value(df: pd.DataFrame, market: str, today: date,
          loaded: tuple | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, float]:
    """The v2 frame for one market's snapshot `df` (v1 columns), with the history features, the base
    rates and the capex gauge it used (`loaded`: history.load's result, when the caller has it)."""
    h, rates = loaded or history.load(market, df, today)
    d = engine.value(df, h, market)
    b = regime.test(d, h, d["eps_core"] * df["shares"] / df["revenue_ttm"].where(df["revenue_ttm"] > 0))
    theme = themes(df, market)
    # no US annual table yet (the first build after Phase 7 values CN before the US backfill): no capex evidence
    us_table = history.HISTORY / "us_annual.csv.gz"
    gauge = regime.capex_gauge(history.us_annual(today)) if us_table.exists() else np.nan
    b["p"], b["p_why"] = regime.probability(b, d, h, rates, h.get("pre_type", pd.Series(dtype=object)),
                                            theme == "ai", gauge)
    v = d.join(b).join(regime.scenarios(b, d, h, df["price"], d["r_req"], engine.G_LONG[market], market))
    v["theme"], v["dilution"] = theme, h.get("dilution")
    v["v_own"] = own_anchor(df, h, v, market)
    if market == "us":
        parent = df["sector"]
    elif market == "hk":
        parent = df["industry_type"].fillna("").str.split("-").str[0]
    else:
        parent = pd.Series("全市场", df.index)  # CN: the data has no parent sector
    v["v_peer"] = anchors.peer(df, d, parent)
    v["v_used"] = v["v_regime"].where(v["break_confirmed"] & v["v_regime"].notna(), v["v_intrinsic"])
    v = v.join(anchors.combine(v.assign(v_intrinsic=v["v_used"]), df["price"], v["archetype"], v["w_hist"]))
    v["v_final"] = v["v_regime"].where(v["break_confirmed"] & v["v_regime"].notna(), v["v_comb"])  # A2.7: one value
    v["icc_final"] = v["icc_regime"].where(v["break_confirmed"], v["icc"])
    v["upside"] = v["v_final"] / df["price"] - 1
    v = v.join(anchors.screen(df, h))
    v = v.join(anchors.confidence(v, h, df["analysts"], df["price"]))
    return v.join(buckets(v, df, market)), h, rates, gauge


def buy_universe(df: pd.DataFrame, market: str) -> pd.Series:
    """Stocks a buy may come from: the market's largest (config buy_largest_n) and, in the US, home listings."""
    out = pd.Series(True, df.index)
    if BUY_LARGEST:
        out &= df["mcap_rank"] <= BUY_LARGEST[market]
    if BUY_HOME_ONLY and market == "us" and "country" in df:
        out &= df["country"].fillna(engine.HOME) == engine.HOME
    return out


def buckets(v: pd.DataFrame, df: pd.DataFrame, market: str = "cn") -> pd.DataFrame:
    """买入 / 持有 / 卖出 (A2.3), 5 each, strict rules first and relaxed fills marked 低信心; at most 2 per
    industry per bucket, each stock once; pre-profit names never get a call.
    Buy: among the largest companies (US: US listings), upside ≥ 20%, confidence 中/高, quality screen passed,
    momentum z ≥ −0.5; ranked by confidence-weighted upside plus momentum. Hold: quality in the top 30%,
    screen passed, |upside| ≤ 15%, confidence 中/高; ranked by quality. Sell: upside ≤ −25%, confidence
    中/高, among the 400 largest, and deterioration (momentum z ≤ −0.5, falling profit or a screen
    failure); ranked by confidence-weighted downside."""
    c, n, cap = CONFIG["v2"], CONFIG["buckets"]["per_bucket"], CONFIG["buckets"]["max_per_group"]
    ok = v["v_final"].notna() & (v["archetype"] != "pre-profit")
    can_buy = ok & buy_universe(df, market)
    up, good, passed = v["upside"], v["confidence"].isin(["高", "中"]), v["screen_ok"]
    mom = momentum(df)
    cw = np.log1p(up.clip(lower=-0.99)) * (1 - v["dispersion"].clip(upper=0.5))
    rank_key = cw / cw[ok].std() + MOM_WEIGHT * mom.fillna(0) if MOM_WEIGHT else cw  # buys only
    excess = (v["icc_final"] - v["r_req"]).fillna(0)
    ex_buy = excess >= BUY_MIN_EXCESS if BUY_MIN_EXCESS is not None else True
    ex_sell = excess <= SELL_MAX_EXCESS if SELL_MAX_EXCESS is not None else True
    largest = df["mcap_rank"] <= CONFIG["buckets"]["sell_largest_n"]
    weak = (df["z_momentum"] <= -0.5) | (df["np_growth"] < 0) | ~passed
    hold_band = c["hold_max_abs_upside"]
    rules = {
        "buy": [(can_buy & (up >= c["buy_min_upside"]) & ex_buy & good & passed
                 & ((mom >= -0.5) | (MOM_FLOOR == "none")), rank_key, False),
                (can_buy & (up >= 0.15) & passed, rank_key, False), (can_buy & (up > 0), rank_key, False)],
        "hold": [(ok & (df["quality_pct"] >= 0.7) & passed & (up.abs() <= hold_band) & good, df["z_quality"], False),
                 (ok & passed & (up.abs() <= hold_band + 0.05), df["z_quality"], False), (ok & (up.abs() < 0.25), df["z_quality"], False)],
        "sell": [(ok & (up <= c["sell_max_upside"]) & ex_sell & good & largest & weak, cw, True),
                 (ok & (up <= -0.15) & largest, cw, True), (ok & (up < 0) & largest, cw, True)],
    }
    chosen, taken = {k: [] for k in BUCKETS}, set()
    for strict in (True, False):  # strict rules for every bucket first, so fills never crowd out real picks
        for bucket, tiers in rules.items():
            for tier, (mask, key, ascending) in list(enumerate(tiers, start=1))[: 1 if strict else 3]:
                for code in key[mask].sort_values(ascending=ascending).index:
                    if len(chosen[bucket]) >= n:
                        break
                    same = sum(df.at[x, "industry"] == df.at[code, "industry"] for x, _ in chosen[bucket])
                    if code not in taken and same < cap:
                        chosen[bucket].append((code, tier))
                        taken.add(code)
    out = pd.DataFrame([{"code": code, "bucket": bucket, "rank": i, "tier": tier,
                         "conviction": "低信心" if tier > 1 or v.at[code, "confidence"] == "低" else "normal"}
                        for bucket, items in chosen.items() for i, (code, tier) in enumerate(items, start=1)],
                       columns=["code", "bucket", "rank", "tier", "conviction"])
    return out.set_index("code").reindex(v.index)


def momentum(df: pd.DataFrame) -> pd.Series:
    """Momentum z for the buy floor and ranking: v1's industry-relative z, or the 12-1 month return
    standardized across the whole market."""
    if MOM_FLOOR == "industry":
        return df["z_momentum"]
    m = df["mom_12_1"]
    return ((m - m.mean()) / m.std()).clip(-3, 3)


def verdict(v: pd.Series) -> str:
    """v2's own answer on whether a stock's recent profit can last: its normal EPS (normal ROE × book;
    for a confirmed break the probability-weighted normal ROE) against the trailing core EPS."""
    if v["archetype"] == "pre-profit" or pd.isna(v["eps_core"]):
        return "不可持续：无持续盈利史（v2 视为未盈利，不估值）"
    if pd.isna(v["v_final"]):
        return "v2 无法估值（账面为负或数据不足）"
    roe = v["p"] * v["roe_new"] + (1 - v["p"]) * v["roe_old"] if v["break_confirmed"] else v["roe_norm"]
    normal, eps = roe * v["bps_c"], v["eps_core"]
    share = normal / eps if eps > 0 else np.nan
    label = "可持续" if share >= 0.8 else "部分可持续" if share >= 0.5 else "不可持续"
    c3 = "无（不足 3 家分析师）" if pd.isna(v["roe_c3"]) else f"{v['roe_c3']:.0%}"
    text = (f"{label}：常态 EPS {normal:.2f} = 近 12 个月核心 EPS {eps:.2f} 的 {share:.0%}（历史权重 {v['w_hist']:.1f}，"
            f"常态 ROE {roe:.0%}，当前 {v['roe_cur']:.0%}，分析师第 3 年 {c3}）")
    if v["break_dir"]:
        side = "向上" if v["break_dir"] == "up" else "向下"
        text += f"；{side}断层{'已确认' if v['break_confirmed'] else '未获分析师确认'}"
    if v["break_confirmed"]:
        text += f"，新水平延续概率 {v['p']:.0%}（{v['p_why']}），市场隐含 {pct(v['p_market'])}"
    return text + f"；v2 价值 {v['v_final']:.2f}（{v['upside']:+.0%}，把握度 {v['confidence']}）"


def pct(x: float) -> str:
    return "—" if pd.isna(x) else "<0%" if x < 0 else ">100%" if x > 1 else f"{x:.0%}"


def run(df: pd.DataFrame, picks: pd.DataFrame, market: str, today: date) -> pd.DataFrame:
    """The snapshot with the v2 columns, after printing the v2 lists and the comparison."""
    v, h, rates, gauge = value(df, market, today)
    excluded = picks.loc[picks["role"] == "excluded", "code"].astype(str).tolist()
    v["verdict"] = pd.Series({c: verdict(v.loc[c]) for c in excluded if c in v.index}, dtype=object)
    report(df, picks, v, h, rates, gauge, market)
    return df.drop(columns=[c for c in df.columns if c.startswith("v2_")]).join(v[COLUMNS].add_prefix("v2_"))


def report(df: pd.DataFrame, picks: pd.DataFrame, v: pd.DataFrame, h: pd.DataFrame, rates: pd.DataFrame, gauge: float,
           market: str) -> None:
    valued = v["v_final"].notna()
    conf = v.loc[valued, "confidence"].value_counts(normalize=True)
    print(f"\n==== {market.upper()} valuation v2 (shadow; the report stays v1) ====")
    pre = v["archetype"] == "pre-profit"
    unvalued = (~valued & ~pre & (v["bps_c"] > 0)).sum()
    over = ((v["v_final"] > 3 * df["price"]) & (v["confidence"] != "低")).sum()
    print(f"required return: market-implied {v['r_mkt'].iloc[0]:.2%} (v1 configured {df['r'].iloc[0]:.2%}), λ = "
          f"{engine.LAMBDA}; valued {valued.sum()} of {len(v)} (pre-profit {pre.sum()}, negative book "
          f"{(v['bps_c'] <= 0).sum()}, no positive value {unvalued}); confidence 高 {conf.get('高', 0):.0%} "
          f"中 {conf.get('中', 0):.0%} 低 {conf.get('低', 0):.0%}; above 3× price without 低: {over}")
    if "pre_eps_ttm" in h:
        print(f"业绩预告 newer than the latest report moved the earnings base of {h['pre_eps_ttm'].notna().sum()} stocks")
    med = v.groupby("archetype")["upside"].median()
    print("archetypes " + ", ".join(f"{a} {k}" + (f" (median upside {med[a]:+.0%})" if pd.notna(med.get(a)) else " (no value)")
                                    for a, k in v["archetype"].value_counts().items()))
    up = rates.xs("up")
    print(f"base rates (kept ≥ half of an ROE jump 3 years later): {up.loc['all', 'mean']:.0%} of {up.loc['all', 'count']:.0f}; "
          f"cyclical history {up.loc['cyclical', 'mean']:.0%}; US top-10 capex growth {gauge:+.0%}")
    show = v.join(df[["name", "price"]])
    cols = {"name": "name", "archetype": "type", "price": "price", "v_used": "intrinsic", "v_peer": "peer",
            "v_own": "own", "v_final": "v2", "upside": "up", "icc_final": "exp_ret", "r_req": "r", "roe_implied": "impl_roe",
            "roe_norm": "norm_roe", "confidence": "conf",
            "conviction": "conviction", "screen_fails": "screen"}
    for bucket, label in BUCKETS.items():
        part = show[show["bucket"] == bucket].sort_values("rank")
        print(f"\n-- v2 {label} ({len(part)})")
        print(fmt(part, cols).to_string())
    breaks = show[show["break_confirmed"]].sort_values("upside")
    print(f"\n-- confirmed regime breaks ({len(breaks)}): our probability the new level lasts vs the market's")
    bcols = {"name": "name", "break_dir": "dir", "price": "price", "v_old": "V_old", "v_new": "V_new", "p": "p_ours",
             "p_market": "p_market", "v_regime": "V_weighted", "v2_up": "up", "p_why": "evidence"}
    print(fmt(breaks.assign(v2_up=breaks["upside"]), bcols).to_string())
    v1 = picks[picks["role"] == "pick"].set_index("code")
    cmp = v1[["bucket", "upside"]].rename(columns={"bucket": "v1", "upside": "v1_up"}).join(show, how="left")
    print("\n-- v1 picks in v2 (v2 bucket blank = not in the v2 lists)")
    print(fmt(cmp.assign(v2b=cmp["bucket"].fillna("")), {"name": "name", "v1": "v1", "v1_up": "v1_up", "archetype": "type",
          "v_final": "v2", "upside": "v2_up", "confidence": "conf", "v2b": "v2_bucket"}).to_string())
    same = {b: len(set(v1.index[v1["bucket"] == b]) & set(v.index[v["bucket"] == b])) for b in BUCKETS}
    print("same name in v1 and v2: " + ", ".join(f"{BUCKETS[b]} {k}/5" for b, k in same.items()))
    excl = picks[picks["role"] == "excluded"]
    if len(excl):
        print("\n-- excluded by one-off checks 1-2 (v1) and v2's answer on whether the profit can last")
        for _, row in excl.iterrows():
            code = str(row["code"])
            print(f"{code} {row['name']} ({BUCKETS[row['bucket']]} candidate)\n  v1: {row['exclusion']}\n"
                  f"  v2: {v['verdict'].get(code, '无 v2 数据')}")


def fmt(part: pd.DataFrame, cols: dict) -> pd.DataFrame:
    out = part.reindex(columns=list(cols)).rename(columns=cols)
    for c in out.columns:
        if c in ("up", "v1_up", "v2_up", "exp_ret", "r", "p_ours", "p_market", "impl_roe", "norm_roe"):
            out[c] = out[c].map(lambda x: "" if pd.isna(x) else pct(x) if c.startswith("p_") else f"{x:+.0%}" if "up" in c else f"{x:.1%}")
        elif c in ("price", "intrinsic", "peer", "own", "v2", "V_old", "V_new", "V_weighted"):
            out[c] = out[c].map(lambda x: "" if pd.isna(x) else f"{x:,.2f}")
        elif c == "name":
            out[c] = out[c].astype(str).str[:16]
    return out
