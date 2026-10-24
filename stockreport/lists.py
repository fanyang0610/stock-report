"""The lists (PLAN.md, "Lists"): the 20-name buy portfolio (equal amounts, at most 2 per sector), your holdings checked
by NAPS's 12-month rule, and the 10 avoid names. Your holdings are in data/holdings.csv (`hold`); without it the check
covers the names of the last 12 months' buy portfolios that aren't in today's."""

from datetime import date, timedelta

import pandas as pd

from stockreport import track, verdicts
from stockreport.config import CONFIG, DATA

HOLDINGS = DATA / "holdings.csv"
HOME = "United States"  # US buys only among home listings
LOT = {"cn": 100, "us": 1}  # HK: each stock's board lot (HKEX)
KEEP, REVIEW = 0.8, 0.5  # at the anniversary keep the top fifth; before it, review below the middle
COLUMNS = ["list", "rank", "code", "name", "sector", "price", "price_date", "lot", "lot_cost", "score", "score_rank",
           "f_value", "f_quality", "f_momentum", "g_value", "g_quality", "g_momentum", "why", "weak", "risk",
           "status", "reason", "since", "recheck"]


def capped(ranked: pd.DataFrame, n: int, cap: int) -> pd.DataFrame:
    """The first n rows in order, at most `cap` per sector."""
    per, keep = {}, []
    for code, sector in ranked["sector"].items():
        if per.get(sector, 0) < cap:
            per[sector] = per.get(sector, 0) + 1
            keep.append(code)
            if len(keep) == n:
                break
    return ranked.loc[keep]


def buy_field(df: pd.DataFrame, market: str) -> pd.Series:
    field = df["mcap_rank"] <= CONFIG["lists"]["buy_largest"][market]
    return field & (df["country"].fillna(HOME) == HOME) if market == "us" else field


def anniversary(d: date, years: int = 1) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 February
        return d.replace(year=d.year + years, day=28)


def held(market: str, today: date, buys: pd.Index) -> pd.DataFrame:
    """Code -> buy date and name: your holdings in the market, else the names in a buy portfolio of the last 12 months
    (logged with a score, so the old method's picks don't count) that aren't in today's."""
    if HOLDINGS.exists():
        h = pd.read_csv(HOLDINGS, dtype=str, keep_default_na=False)
        return h[h["market"] == market].set_index("code")[["since", "name"]]
    log = track.load()
    if "score" not in log:
        return pd.DataFrame(columns=["since", "name"])
    past = log[(log["market"] == market) & (log["bucket"] == "buy") & log["score"].notna()
               & (log["date"] >= (today - timedelta(days=365)).isoformat()) & (log["date"] < today.isoformat())]
    first = past.sort_values("date").groupby("ticker")[["date", "name"]].first().rename(columns={"date": "since"})
    return first[~first.index.isin(buys)]


def check(df: pd.DataFrame, market: str, today: date, buys: pd.DataFrame, dropped: dict[str, str]) -> pd.DataFrame:
    """继续持有 / 复核 / 卖出 per holding (PLAN.md, "Holding rule"); hard red flags come with stage 2's review."""
    scores = df.loc[buy_field(df, market), "score"]
    keep, review = scores.quantile(KEEP), scores.quantile(REVIEW)
    holdings = held(market, today, buys.index)
    swap = next((f"{c} {buys.at[c, 'name']}" for c in buys.index if c not in holdings.index), "")
    rows = []
    for code, h in holdings.iterrows():
        due = anniversary(date.fromisoformat(h["since"]))
        row = {"code": code, "name": h["name"], "since": h["since"]}
        if code not in df.index:
            rows.append(row | {"status": "复核", "recheck": today.isoformat(),
                               "reason": f"今日未评分（{dropped.get(code, '不在市值前列或数据不全')}）"})
            continue
        s, rank = df.at[code, "score"], df.at[code, "score_rank"]
        if today < due and s < review:
            status, reason, recheck = "复核", f"未满 12 个月，评分跌入后半（第 {rank} 名）", today
        elif today < due:
            status, reason, recheck = "继续持有", f"未满 12 个月，评分在前半（第 {rank} 名）", due
        elif s >= keep:
            status, reason, recheck = "继续持有", f"满 12 个月，仍在前五分之一（第 {rank} 名），再持有一年", anniversary(due)
        else:
            status, reason, recheck = "卖出", f"满 12 个月，已不在前五分之一（第 {rank} 名）", today
            reason += f"，可换入未持有的最高分 {swap}" if swap else ""
        rows.append(row | df.loc[code].to_dict() | {"status": status, "reason": reason, "recheck": recheck.isoformat()})
    return pd.DataFrame(rows).assign(list="holding")


def build(df: pd.DataFrame, market: str, today: date, dropped: dict[str, str]) -> pd.DataFrame:
    """The day's buys, avoid names, holdings check and your vetoes, one row each (COLUMNS)."""
    cfg = CONFIG["lists"]
    vetoes = {c: v for c, v in verdicts.active(market, today, df["period"].astype(str)).items() if v["verdict"] == "veto"}
    df = df.assign(lot=df["lot"] if "lot" in df else LOT[market])
    df["lot_cost"] = df["price"] * df["lot"]
    ranked = df.sort_values("score", ascending=False)
    field = buy_field(ranked, market) & ~ranked.index.isin(list(vetoes))
    buys = capped(ranked[field], cfg["buys"], cfg["per_sector"])
    avoid = capped(ranked[ranked["mcap_rank"] <= cfg["avoid_largest"]].iloc[::-1], cfg["avoid"], cfg["per_sector"])
    parts = [buys.assign(list="buy", rank=range(1, len(buys) + 1), recheck=anniversary(today).isoformat()),
             avoid.assign(list="avoid", rank=range(1, len(avoid) + 1)),
             check(df, market, today, buys, dropped),
             pd.DataFrame([{"list": "veto", "code": c, "name": df["name"].get(c, ""),
                            "reason": f"你的否决（至 {v['until']}）：{v['reason']}"} for c, v in vetoes.items()])]
    out = pd.concat([p.rename_axis("code").reset_index() if "code" not in p else p for p in parts if len(p)])
    return out.reindex(columns=COLUMNS)


def name_of(market: str, code: str) -> str:
    snaps = sorted((DATA / "snapshots").glob(f"*/{market}.csv.gz"))
    names = pd.read_csv(snaps[-1], usecols=["code", "name"], dtype=str).set_index("code")["name"] if snaps else {}
    return names.get(code, "")


def hold(code: str | None, day: str | None, sold: bool, today: date) -> str:
    """`hold CODE [--date D]` records a holding bought on D (default today); `hold CODE --sold` removes it; `hold`
    lists them."""
    h = pd.read_csv(HOLDINGS, dtype=str) if HOLDINGS.exists() else pd.DataFrame(columns=["market", "code", "name", "since"])
    if not code:
        return "\n".join(f"{r.market.upper()} {r.code} {r.name} since {r.since}" for r in h.itertuples()) or "No holdings."
    code = code.zfill(5) if code.isdigit() and len(code) <= 5 else code.upper()
    market = verdicts.market_of(code)
    h = h[h["code"] != code]
    if sold:
        msg = f"Removed {code}."
    else:
        since = date.fromisoformat(day) if day else today
        h = pd.concat([h, pd.DataFrame([{"market": market, "code": code, "name": name_of(market, code), "since": since.isoformat()}])])
        msg = f"Holding {market.upper()} {code} since {since}; the next `run` checks it."
    h.sort_values(["market", "code"]).to_csv(HOLDINGS, index=False)
    return msg
