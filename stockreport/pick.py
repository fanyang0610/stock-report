"""Buckets per market (PLAN.md Method section 6): always 5 BUY, 5 HOLD and 5 SELL, rank-based.
A bucket short of names that meet every rule is filled with the next-ranked ones, marked 低信心.
Buy and hold candidates whose recent profit is a one-off by checks 1-2 (Method 8) never take a place;
the ones that would have are kept in the picks CSV as role "excluded", so the report can list them."""

import pandas as pd

from stockreport.config import CONFIG
from stockreport.score import explain

BUCKETS = {"buy": "买入", "hold": "持有", "sell": "卖出"}


def one_off(df: pd.DataFrame) -> pd.DataFrame:
    """The one_off_gain checks per stock (thresholds in config.toml [notes]; NaN = doesn't apply).
    1: profit jump without cash (not banks, brokers and insurers, whose investment income is core);
    2: analysts expect EPS to fall back; 3: profit outgrew revenue, which lets a one-off item in the
    announcement titles count (DeepSeek notes only)."""
    cfg, min_analysts = CONFIG["notes"], CONFIG["value"]["forward_min_analysts"]
    applies1 = (df["method"] != "P/B on ROE") & df["cash_conv"].notna() & (df["np_ttm"] > 0)
    applies2 = (df["analysts"] >= min_analysts) & (df["eps_ttm"] > 0) & df["eps_e2"].notna()
    ratio = (df["eps_e2"] / df["eps_ttm"]).where(applies2)
    c1 = (df["np_growth"] > cfg["spike_growth"]) & (df["cash_conv"] < cfg["spike_cash_conv"])
    c2 = ratio < cfg["eps_fall"]
    return pd.DataFrame({"c1": c1.astype(object).where(applies1), "c2": c2.astype(object).where(applies2),
                         "c3": df["np_growth"] - df["rev_growth"] >= cfg["title_gap"], "eps_ratio": ratio})


def exclusion(row: pd.Series, check: pd.Series) -> str:
    """Why checks 1-2 removed a candidate, in plain words."""
    if pd.notna(check["c2"]) and check["c2"]:
        return f"{row['analysts']:.0f} 家分析师预期明年 EPS 只有近 12 个月的 {check['eps_ratio']:.2f} 倍，近期利润难以持续。"
    return f"净利润同比 {row['np_growth']:+.0%}，但经营现金流/净利润只有 {row['cash_conv']:.2f}，利润缺少现金支撑。"


def tiers(df: pd.DataFrame) -> dict[str, list[tuple[pd.Series, str, bool]]]:
    """Per bucket: (candidates, sort column, ascending) from strict (tier 1) to relaxed (tiers 2-3)."""
    c = CONFIG["buckets"]
    upside, mom = df["upside"], df["z_momentum"]
    hold_range = upside.between(*c["hold_upside"])
    largest = df["mcap_rank"] <= c["sell_largest_n"]
    sell_weak = ((df["quality_pct"] <= c["sell_quality_bottom"]) | (mom <= c["sell_max_momentum_z"])
                 | (df["np_growth"] < 0))
    buy = upside >= c["buy_min_upside"]
    sell = upside <= c["sell_max_upside"]
    return {
        "buy": [(buy & (df["z_quality"] >= df["quality_group_median"]) & (mom >= c["buy_min_momentum_z"]),
                 "composite", False),
                (buy, "composite", False),
                (upside > 0, "composite", False)],
        "hold": [(hold_range & (df["quality_pct"] >= 1 - c["hold_quality_top"]), "z_quality", False),
                 (hold_range, "z_quality", False),
                 (upside.abs() < 0.25, "z_quality", False)],
        "sell": [(sell & sell_weak & largest, "composite", True),
                 (sell & largest, "composite", True),
                 (largest & (upside < 0), "composite", True)],
    }


def pick(df: pd.DataFrame) -> pd.DataFrame:
    """Picks plus runners-up, and the excluded names. Each stock in one bucket only; at most N per
    industry per bucket. The sell bucket ignores checks 1-2: a one-off gain only adds to overvaluation."""
    c = CONFIG["buckets"]
    df = df[df["fv_mid"].notna()]
    checks = one_off(df)
    spiked = set(df.index[checks["c1"].eq(True) | checks["c2"].eq(True)])
    rules = {b: list(enumerate(r, start=1)) for b, r in tiers(df).items()}
    taken: set[str] = set()
    chosen = {b: [] for b in BUCKETS}
    excluded: dict[str, tuple[str, int]] = {}  # code -> (bucket, tier) where it would have been picked

    def scan(bucket: str, tier_rules: list, limit: int, role: str) -> None:
        for tier, (mask, key, ascending) in tier_rules:
            for code in df[mask].sort_values(key, ascending=ascending).index:
                if sum(x["role"] == role for x in chosen[bucket]) >= limit:
                    return
                if bucket != "sell" and code in spiked:
                    if role == "pick" and code not in excluded:
                        excluded[code] = (bucket, tier)
                    continue
                industry = df.at[code, "industry"]
                if code in taken or sum(df.at[x["code"], "industry"] == industry
                                        for x in chosen[bucket]) >= c["max_per_group"]:
                    continue
                chosen[bucket].append({"code": code, "role": role, "tier": tier})
                taken.add(code)

    for bucket in BUCKETS:  # strict rules for every bucket first, so fills never crowd out real picks
        scan(bucket, rules[bucket][:1], c["per_bucket"], "pick")
    for bucket in BUCKETS:
        scan(bucket, rules[bucket], c["per_bucket"], "pick")
    for bucket in BUCKETS:
        scan(bucket, rules[bucket], c["runners_up"], "runner_up")

    rows = []
    for bucket, items in chosen.items():
        for role in ("pick", "runner_up"):
            for rank, item in enumerate((x for x in items if x["role"] == role), start=1):
                row = df.loc[item["code"]]
                drivers, risk = explain(row, bucket)
                low = item["tier"] > 1 or not row["lenses_agree"]  # the RI check is kept for reference only
                rows.append({"bucket": bucket, "action": BUCKETS[bucket], "role": role, "rank": rank,
                             "tier": item["tier"], "conviction": "低信心" if low else "normal",
                             "code": item["code"], "drivers": drivers, "key_risk": risk, "exclusion": None})
    for code, (bucket, tier) in excluded.items():
        drivers, risk = explain(df.loc[code], bucket)
        rank = sum(r["role"] == "excluded" and r["bucket"] == bucket for r in rows) + 1
        rows.append({"bucket": bucket, "action": BUCKETS[bucket], "role": "excluded", "rank": rank, "tier": tier,
                     "conviction": "", "code": code, "drivers": drivers, "key_risk": risk,
                     "exclusion": exclusion(df.loc[code], checks.loc[code])})
    out = pd.DataFrame(rows).set_index("code")
    return out.join(df).reset_index()


CSV_COLUMNS = [
    "bucket", "action", "role", "rank", "tier", "conviction", "code", "name", "industry", "peer_group",
    "price", "price_date", "fv_low", "fv_mid", "fv_high", "upside", "method", "fit_group", "fit_n",
    "fv_trailing", "fv_forward", "lenses_agree", "analysts", "eps_e2", "fwd_pe", "fwd_growth",
    "ri_value", "ri_gap", "cross_check_ok", "r", "mcap", "mcap_rank", "turnover_20d",
    "pe", "pb", "ps", "ey", "by", "roe", "rev_growth", "np_growth", "gross_margin", "debt_ratio",
    "cash_conv", "div_yield", "mom_12_1", "vol_1y", "period", "notice_date", "np_ttm", "revenue_ttm",
    "eps_ttm", "bps", "z_value", "z_quality", "z_growth", "z_momentum", "z_risk", "composite",
    "quality_pct", "drivers", "key_risk", "exclusion",
]


def print_table(picks: pd.DataFrame) -> None:
    show = picks.assign(
        upside=lambda d: (d["upside"] * 100).round(1), price=lambda d: d["price"].round(2),
        fv_mid=lambda d: d["fv_mid"].round(2), q=lambda d: (d["quality_pct"] * 100).round(0),
        mom=lambda d: d["z_momentum"].round(2), score=lambda d: d["composite"].round(2))
    cols = ["rank", "code", "name", "industry", "price", "fv_mid", "upside", "q", "mom", "score", "conviction", "drivers"]
    for bucket, label in BUCKETS.items():
        for role, title in (("pick", label), ("runner_up", f"{label} — runners-up"),
                            ("excluded", f"{label} — excluded by one-off checks 1-2")):
            part = show[(show["bucket"] == bucket) & (show["role"] == role)]
            if role != "excluded" or len(part):
                print(f"\n== {title} ({len(part)})")
                print(part[cols + (["exclusion"] if role == "excluded" else [])].to_string(index=False))
