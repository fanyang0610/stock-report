"""Valuation v3 (Phase 13, PLAN.md Method 16) in shadow mode next to v1: its columns (v3_*) go into the snapshot
and the run prints the v3 lists, the common-sense checks and the hand-checked names. The report stays v1 until
Phase 10. Per stock: the value range, upside, what the price implies and how often similar companies did it,
the base-rate cell, what peers pay (a cross-check line, never blended), confidence and 需复核 flags. The lists
skip the AI swaps and the cross-market issuer dedupe."""

from datetime import date

import numpy as np
import pandas as pd

from stockreport import baserates as br, history, v3
from stockreport.config import CONFIG
from stockreport.pick import BUCKETS

C2 = CONFIG["shadow"]  # bucket rules kept from v2 (Phase 9 calibration): thresholds, momentum, size floor
HOME = "United States"  # US: foreign listings can't be bought (config buy_home_only)
HAND = {"us": ["TM", "GM", "F", "STLA", "TSLA", "RACE", "LLY", "JNJ", "NVDA", "MU", "ARM", "CRWD", "JPM"],
        "cn": ["601668", "601390", "600019", "600519", "300750", "002594", "300308"],
        "hk": ["00700", "03690", "00941", "02007", "01299"]}  # the Phase 13 hand-check list (PLAN item 13)
COLUMNS = ["e0", "book", "light", "t0", "g", "roe0", "roe_now", "level", "starts", "base", "s1", "s3", "s5", "s10", "d25", "d50", "d75",
           "r", "r_mkt", "roe_long", "irr", "v_low", "v_mid", "v_high", "upside", "d_implied", "implied_share", "implied_side",
           "implied_label", "roe_implied", "roe_reached", "implied", "v_peer", "screen_fails", "dilution", "flags", "conf_points",
           "confidence", "bucket", "rank", "tier", "conviction"]


def parents(df: pd.DataFrame, market: str) -> pd.Series:
    """The industry's parent sector (US Nasdaq sector, HK first level of the industry type, CN 申万 level 1)."""
    if market == "us":
        return df["sector"].fillna("")
    if market == "hk":
        return df["industry_type"].fillna("").str.split("-").str[0]
    return br.sectors("cn").reindex(df.index).fillna("")


def load(df: pd.DataFrame, market: str, today: date) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """History features, the base-rate starts (with the market's long-run ROE) and each stock's base-rate sector,
    from what was public on `today`."""
    day = today.isoformat()
    p = br.panel(market)
    st = br.starts(p, day, market)
    st.attrs["roe_long"] = v3.roe_long(p, day, market)
    sec = br.sectors(market)
    if market == "us":  # keyed by CIK
        from stockreport.fetch import sec as edgar
        cik = df["cik"] if "cik" in df else edgar.load_ciks().reindex(df.index)
        sector = cik.map(lambda c: sec.get(str(int(float(c))), "") if pd.notna(c) and str(c) != "" else "")
    else:
        sector = parents(df, market) if market == "hk" else sec.reindex(df.index)
    return history.load(market, df, today), st, sector.fillna("")


def value(df: pd.DataFrame, market: str, today: date, loaded: tuple | None = None) -> pd.DataFrame:
    """The v3 frame for one market's snapshot `df` (v1 columns)."""
    h, st, sector = loaded or load(df, market, today)
    v = v3.value(df, h, st, market, sector)
    v["base"] = [br.describe(lv, k, market) for lv, k in zip(v["level"], v["key"])]
    v["implied"] = sentences(v, df, v3.per_market(v3.FADE, market))
    v["v_peer"] = peer(df, v, parents(df, market))
    v = v.join(screen(df, h))
    v["dilution"] = h["dilution"] if "dilution" in h else np.nan  # US: 5-year share count change (deep-dive trigger)
    v["flags"] = flags(v, df, h)
    v = v.join(confidence(v, df))
    return v.join(buckets(v, df, market))


def sentences(v: pd.DataFrame, df: pd.DataFrame, fade: int) -> pd.Series:
    """What the price implies, in one sentence, with how often similar companies did it."""
    out = pd.Series("", v.index)
    for code in v.index[v["valued"]]:
        x, side = v.loc[code], v.at[code, "implied_side"]
        g, d, cons = f"{x['g']:.0%}".replace("-0%", "0%"), x["d_implied"], x["t0"] == 3
        if not x["rising"] or side != "inside":
            head = ("价格隐含利润以年均 " + g + f" 增长超过 {br.DMAX} 年" if side == "above" and x["rising"] else
                    "价格低于利润增长随即停止的价值 " + f"{x['v_t0']:,.2f}" if side == "below" and x["rising"] else
                    f"ROE {x['roe_now']:.0%} 时增长不创造价值")
            text = f"{head}；价格隐含长期 ROE 约 {x['roe_implied']:.0%}（当前 {x['roe_now']:.0%}）"
            if pd.notna(x["roe_reached"]):
                text += f"；类似公司 3-5 年后 ROE 到这个水平的 {x['roe_reached']:.0%}"
        elif cons and d < 1:
            text = (f"价格隐含利润达不到分析师第 1 年的预测，停在近 12 个月的水平（ROE {x['roe_now']:.0%}）；"
                    f"历史上类似公司 {x['s1']:.0%} 至少保持了 1 年 {g} 的增长")
        elif cons and d < 3:
            text = f"价格隐含只兑现分析师预测的前 {d:.0f} 年；历史上类似公司 {x['implied_share']:.0%} 做到"
        else:
            lead = "（前 3 年按分析师预测）" if cons else ""
            text = (f"价格隐含利润以年均 {g} 增长约 {d:.0f} 年{lead}，之后 ROE 按类似公司的走势变化、{fade} 年后回到"
                    f"长期水平；历史上类似公司 {x['implied_share']:.0%} 做到")
        out[code] = text
    return out


def peer(df: pd.DataFrame, v: pd.DataFrame, parent: pd.Series, min_group: int = 8, min_own: int = 3) -> pd.Series:
    """What peers pay, a cross-check line (never blended): log P/E on core EPS fitted on the growth rate g within the
    industry (financials: log P/B on ROE) when it has 8+ valued members; a smaller industry takes its parent
    sector's slope at its own median level (3+ members, else the parent's), never the whole market. A slope of
    the wrong sign (more growth, a lower multiple) is dropped."""
    fin = df["financial"].astype(bool)
    base = v["book"].where(fin, v["e0"])
    y = np.log((df["price"] / base).where(base > 0))
    xv = v["roe0"].where(fin, v["g"])
    usable = v["valued"] & y.notna() & xv.notna()
    out = pd.Series(np.nan, df.index)
    for (_, is_fin), part in df.groupby([df["industry"], fin]):
        rows = part.index[usable[part.index]]
        sample, shift = rows, 0.0
        if len(rows) < min_group:
            sample = usable.index[usable & (parent == parent[part.index[0]]) & (fin == is_fin) & (parent != "")]
            if len(sample) < min_group:
                continue
        b = np.polyfit(xv[sample], y[sample], 1) if xv[sample].std() > 0 else np.array([0.0, y[sample].mean()])
        if b[0] < 0:
            b = np.array([0.0, y[sample].median()])
        if len(rows) < min_group and len(rows) >= min_own:
            shift = float(np.median(y[rows] - np.polyval(b, xv[rows])))
        target = part.index[v.loc[part.index, "valued"] & (base[part.index] > 0)]
        out[target] = np.exp(np.polyval(b, xv[target]) + shift) * base[target]
    return out


def screen(df: pd.DataFrame, h: pd.DataFrame) -> pd.DataFrame:
    """Quality screen (buy and hold only): 10-year ROE < 8% (exempt: under 10 years of history, gross margin > 30%,
    operating cash flow positive in the last 2 years); 5-year OCF/NI < 0.7; 5-year free cash flow < 0 (US: the CN
    and HK tables have no capex); long-run net margin < 5% (exempt: gross margin > 30% and the last 2 years at 5%+
    or rising; or 10-year ROE > 20% and OCF/NI > 1). Banks, insurers and brokers on ROE alone."""
    fin, gm = df["financial"].astype(bool), df["gross_margin"]
    young = (h["n_years"] < 10) & (gm > 0.3) & h["ocf_2y_pos"].eq(True)
    exempt = ((gm > 0.3) & ((h["margin_2y"] >= 0.05) | (h["margin_2y"] > h["margin_hist"]))) | (
        (h["roe_hist"] > 0.2) & (h["ocf_ni_5y"] > 1))
    fails = pd.DataFrame({"ROE<8%": (h["roe_hist"] < 0.08) & ~young, "OCF/NI<0.7": ~fin & (h["ocf_ni_5y"] < 0.7),
                          "FCF<0": ~fin & (h["fcf_5y"] < 0), "净利率<5%": ~fin & (h["margin_hist"] < 0.05) & ~exempt},
                         index=df.index).fillna(False)
    text = fails.apply(lambda r: ",".join(c for c in fails.columns if r[c]), axis=1)
    return pd.DataFrame({"screen_fails": text, "screen_ok": text == ""}, index=df.index)


def flags(v: pd.DataFrame, df: pd.DataFrame, h: pd.DataFrame) -> pd.Series:
    """Common-sense checks (需复核), each with its reason: value and price an order apart (beyond ±100%) without
    an implied-expectations label; the stock's industry as a whole far off (median beyond ±30%, 5+ valued); a
    value implying a P/B outside the stock's own 7-year range by half again; peers paying more than 2× or under
    ½ of the value."""
    ok, up = v["valued"], v["upside"]
    out = pd.Series([[] for _ in v.index], v.index)
    ind = up[ok].groupby(df["industry"][ok]).agg(["median", "count"])
    far = ind[(ind["count"] >= 5) & (ind["median"].abs() > 0.3)]["median"]
    implied_pb = v["v_mid"] / (df["price"] / df["pb_mrq_em"] if "pb_mrq_em" in df else v["book"])
    pb_lo, pb_hi = h.get("own_pb_lo"), h.get("own_pb_hi")
    for code in v.index[ok]:
        if abs(up[code]) > 1 and not v.at[code, "implied_label"]:
            out[code].append(f"估值与价格相差 {up[code]:+.0%}")
        if df.at[code, "industry"] in far.index:
            out[code].append(f"行业整体偏离 {far[df.at[code, 'industry']]:+.0%}")
        if pb_lo is not None and pd.notna(pb_lo.get(code)) and v.at[code, "book"] > 0 and not v.at[code, "light"]:
            if implied_pb[code] > 1.5 * pb_hi[code] or implied_pb[code] < pb_lo[code] / 1.5:
                out[code].append(f"估值隐含 P/B {implied_pb[code]:.1f}，自身 7 年 {pb_lo[code]:.1f}-{pb_hi[code]:.1f}")
        ratio = v.at[code, "v_peer"] / v.at[code, "v_mid"]
        if pd.notna(ratio) and (ratio > 2 or ratio < 0.5):
            out[code].append(f"同行定价是估值的 {ratio:.1f} 倍")
    return out.map("；".join)


def confidence(v: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Points: the 25-75% range within ±15% of the value +1, wider than ±40% −1; 7+ years of history +1, under 5
    −1; 5+ analysts +1, under 3 −1; a base-rate cell with the stock's sector and bands +1, market-wide −1; peers
    within 30% of the value +1, 2× apart −1; an implied-expectations label −1; each 需复核 flag −1 (at most −2).
    3+ = 高, 1-2 = 中, else 低."""
    width = (v["v_high"] - v["v_low"]) / v["v_mid"] / 2
    peer_gap = (v["v_peer"] / v["v_mid"] - 1).abs()
    s = pd.Series(np.select([width <= 0.15, width > 0.4], [1, -1], 0), v.index)
    s += np.select([v["n_years"] >= 7, ~(v["n_years"] >= 5)], [1, -1], 0)
    s += np.select([df["analysts"] >= 5, df["analysts"] < 3], [1, -1], 0)
    s += np.select([v["level"] <= 1, v["level"] >= 3], [1, -1], 0)
    s += np.select([peer_gap <= 0.3, peer_gap > 1], [1, -1], 0)
    s -= (v["implied_label"] != "").astype(int)
    s -= np.minimum(v["flags"].str.count("；") + (v["flags"] != ""), 2)
    label = np.select([s >= 3, s >= 1], ["高", "中"], "低")
    return pd.DataFrame({"conf_points": s, "confidence": np.where(v["valued"], label, "")}, index=v.index)


def buy_universe(df: pd.DataFrame, market: str) -> pd.Series:
    """Stocks a buy may come from: the market's largest (config buy_largest_n) and, in the US, home listings."""
    out = pd.Series(True, df.index)
    if C2.get("buy_largest_n"):
        out &= df["mcap_rank"] <= C2["buy_largest_n"][market]
    if C2.get("buy_home_only") and market == "us" and "country" in df:
        out &= df["country"].fillna(HOME) == HOME
    return out


def buckets(v: pd.DataFrame, df: pd.DataFrame, market: str = "cn") -> pd.DataFrame:
    """买入 / 持有 / 卖出, 5 each, strict rules first and relaxed fills marked 低信心; at most 2 per industry per
    bucket, each stock once (v2's rules, Phase 9 calibration). Buy: among the largest (US: home listings), upside
    ≥ 20%, confidence 中/高, quality screen passed, momentum z ≥ −0.5; ranked by range-weighted upside + 0.5 ×
    momentum. Hold: quality top 30%, screen passed, |upside| ≤ 15%, 中/高; by quality. Sell: upside ≤ −25%, 中/高,
    among the 400 largest, and momentum z ≤ −0.5, falling profit or a screen failure."""
    n, cap = CONFIG["buckets"]["per_bucket"], CONFIG["buckets"]["max_per_group"]
    ok = v["valued"]
    can_buy = ok & buy_universe(df, market)
    up, good, passed, mom = v["upside"], v["confidence"].isin(["高", "中"]), v["screen_ok"], df["z_momentum"]
    width = (np.log(v["v_high"] / v["v_low"]) / 2).clip(upper=0.5).fillna(0.5)
    cw = np.log1p(up.clip(lower=-0.99)) * (1 - width)
    rank_key = cw / cw[ok].std() + C2["momentum_weight"] * mom.fillna(0)
    largest = df["mcap_rank"] <= CONFIG["buckets"]["sell_largest_n"]
    weak = (mom <= -0.5) | (df["np_growth"] < 0) | ~passed
    band = C2["hold_max_abs_upside"]
    rules = {
        "buy": [(can_buy & (up >= C2["buy_min_upside"]) & good & passed & (mom >= -0.5), rank_key, False),
                (can_buy & (up >= 0.15) & passed, rank_key, False), (can_buy & (up > 0), rank_key, False)],
        "hold": [(ok & (df["quality_pct"] >= 0.7) & passed & (up.abs() <= band) & good, df["z_quality"], False),
                 (ok & passed & (up.abs() <= band + 0.05), df["z_quality"], False), (ok & (up.abs() < 0.25), df["z_quality"], False)],
        "sell": [(ok & (up <= C2["sell_max_upside"]) & good & largest & weak, cw, True),
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


def run(df: pd.DataFrame, picks: pd.DataFrame, market: str, today: date) -> pd.DataFrame:
    """The snapshot with the v3 columns, after printing the v3 lists and checks."""
    v = value(df, market, today)
    report(df, picks, v, market)
    old = [c for c in df.columns if c.startswith(("v2_", "v3_"))]
    return df.drop(columns=old).join(v[COLUMNS].add_prefix("v3_"))


def report(df: pd.DataFrame, picks: pd.DataFrame, v: pd.DataFrame, market: str) -> None:
    ok, up = v["valued"], v["upside"]
    shown = ok & (v["implied_label"] == "")
    conf = v.loc[ok, "confidence"].value_counts(normalize=True)
    print(f"\n==== {market.upper()} valuation v3 (Phase 13, shadow; the report stays v1) ====")
    lam = v3.per_market(v3.LAMBDA, market)
    print(f"discount rate {v['r_mkt'].iloc[0]:.2%} (market-implied) + {lam:g} × the industry's premium (stocks' rates "
          f"{v.loc[ok, 'r'].quantile(0.05):.1%}-{v.loc[ok, 'r'].quantile(0.95):.1%}), long-run ROE {v['roe_long'].iloc[0]:.1%}; valued "
          f"{ok.sum()} of {len(v)} (no profit and no analyst-expected profit within 3 years: {(~v['ok']).sum()}); "
          f"book-light {(v['light'] & ok).sum()}; confidence 高 {conf.get('高', 0):.0%} 中 {conf.get('中', 0):.0%} 低 {conf.get('低', 0):.0%}")
    print(f"common-sense checks: median upside {up[ok].median():+.0%} (shown without a label {up[shown].median():+.0%}); "
          f"beyond ±100%: {(up[ok].abs() > 1).mean():.1%} of valued, {(up[shown].abs() > 1).sum()} shown; labels "
          + ", ".join(f"{k} {n}" for k, n in v.loc[ok, "implied_label"].replace("", "无").value_counts().items())
          + f"; 需复核 {(v['flags'] != '').sum()}")
    ind = up[ok].groupby(df["industry"][ok])
    t = pd.DataFrame({"median": ind.median(), "n": ind.count(), "high": (v.loc[ok, "implied_label"] == "价格隐含过高").groupby(df["industry"][ok]).sum(),
                      "low": (v.loc[ok, "implied_label"] == "价格隐含过低").groupby(df["industry"][ok]).sum(),
                      "d_implied": v.loc[ok, "d_implied"].groupby(df["industry"][ok]).median(),
                      "d50": v.loc[ok, "d50"].groupby(df["industry"][ok]).median()})
    far = t[(t["n"] >= 5) & (t["median"].abs() > 0.3)].sort_values("median")
    print(f"industries (5+ valued) beyond ±30%: {len(far)} of {(t['n'] >= 5).sum()}; why: labels and median implied vs "
          f"base-rate durations (years)")
    if len(far):
        print(far.assign(median=far["median"].map("{:+.0%}".format)).round(1).to_string())
    show = v.join(df[["name", "price"]])
    cols = ["name", "price", "v_low", "v_mid", "v_high", "upside", "confidence", "implied_label", "conviction", "flags"]
    for bucket, label in BUCKETS.items():
        part = show[show["bucket"] == bucket].sort_values("rank")
        print(f"\n-- v3 {label} ({len(part)})")
        print(fmt(part[cols]).to_string())
    hand = [c for c in HAND[market] if c in show.index]
    print("\n-- hand-checked names (PLAN item 13)")
    for code in hand:
        x = show.loc[code]
        val = "无估值（无盈利，也无 3 位以上分析师预期 3 年内盈利）" if not x["valued"] else (
            f"{x['v_low']:,.2f} / {x['v_mid']:,.2f} / {x['v_high']:,.2f}（{x['upside']:+.0%}，{x['confidence']}）{x['implied_label']}")
        print(f"{code} {x['name']}: 价格 {x['price']:,.2f}；估值 {val}\n  {x['implied']}\n  基础比率：{x['base']}，"
              f"{x['starts']:.0f} 例；利润以年均 {x['g']:.0%} 增长 3/5/10 年的比例 {x['s3']:.0%}/{x['s5']:.0%}/{x['s10']:.0%}"
              + (f"\n  同行定价 {x['v_peer']:,.2f}" if pd.notna(x["v_peer"]) else "") + (f"\n  需复核：{x['flags']}" if x["flags"] else ""))
    v1 = picks[picks["role"] == "pick"].set_index("code")
    same = {b: len(set(v1.index[v1["bucket"] == b]) & set(v.index[v["bucket"] == b])) for b in BUCKETS}
    print("same name in v1 and v3: " + ", ".join(f"{BUCKETS[b]} {k}/5" for b, k in same.items()))


def fmt(part: pd.DataFrame) -> pd.DataFrame:
    out = part.copy()
    out["upside"] = out["upside"].map(lambda x: "" if pd.isna(x) else f"{x:+.0%}")
    for c in ("price", "v_low", "v_mid", "v_high"):
        out[c] = out[c].map(lambda x: "" if pd.isna(x) else f"{x:,.2f}")
    out["name"] = out["name"].astype(str).str[:16]
    return out
