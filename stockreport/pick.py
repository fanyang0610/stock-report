"""Buckets per market (PLAN.md Method section 6): always 5 BUY, 5 HOLD and 5 SELL, rank-based.
A bucket short of names that meet every rule is filled with the next-ranked ones, marked 低信心."""

import pandas as pd

from stockreport.config import CONFIG
from stockreport.score import explain

BUCKETS = {"buy": "买入", "hold": "持有/不追高", "sell": "卖出/回避"}


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
    """Picks plus runners-up. Each stock in one bucket only; at most N per industry per bucket."""
    c = CONFIG["buckets"]
    df = df[df["fv_mid"].notna()]
    rules = {b: list(enumerate(r, start=1)) for b, r in tiers(df).items()}
    taken: set[str] = set()
    chosen = {b: [] for b in BUCKETS}

    def scan(bucket: str, tier_rules: list, limit: int, role: str) -> None:
        for tier, (mask, key, ascending) in tier_rules:
            for code in df[mask].sort_values(key, ascending=ascending).index:
                if sum(x["role"] == role for x in chosen[bucket]) >= limit:
                    return
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
                             "code": item["code"], "drivers": drivers, "key_risk": risk})
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
    "quality_pct", "drivers", "key_risk",
]


def print_table(picks: pd.DataFrame) -> None:
    show = picks.assign(
        upside=lambda d: (d["upside"] * 100).round(1), price=lambda d: d["price"].round(2),
        fv_mid=lambda d: d["fv_mid"].round(2), q=lambda d: (d["quality_pct"] * 100).round(0),
        mom=lambda d: d["z_momentum"].round(2), score=lambda d: d["composite"].round(2))
    cols = ["rank", "code", "name", "industry", "price", "fv_mid", "upside", "q", "mom", "score", "conviction", "drivers"]
    for bucket, label in BUCKETS.items():
        for role, title in (("pick", label), ("runner_up", f"{label} — runners-up")):
            part = show[(show["bucket"] == bucket) & (show["role"] == role)]
            print(f"\n== {title} ({len(part)})")
            print(part[cols].to_string(index=False))
