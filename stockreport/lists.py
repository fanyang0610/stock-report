"""The lists (PLAN.md, "Lists"): the 20-name buy portfolio from the whole scored market (each sector its places by its
share of the market's free-float value, filled by its best scores, equal amounts; Quantitative Value's screen first),
the names held, checked by NAPS's 12-month rule (your holdings in data/holdings.csv, `hold`, if you keep them; else
a neutral hold rating of the names the published lists recommended), and the 10 avoid names."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from stockreport import track, verdicts
from stockreport.config import CONFIG, DATA
from stockreport.score import ranked

HOLDINGS = DATA / "holdings.csv"
LOT = {"cn": 100, "us": 1}  # HK: each stock's board lot (HKEX)
REVIEW = 0.5  # before the anniversary review below the middle of the sector; at it keep the top fifth (`top_share`)
WINDOW = 30  # days after an anniversary in which a holding is judged at it (the time to sell); then a new year starts
PARTNERSHIP = r"(?:\bL\.?P\.?|Limited Partnership)$"  # US master limited partnerships (K-1 units)
COLUMNS = ["list", "rank", "code", "name", "sector", "weight", "price", "price_date", "lot", "lot_cost", "score",
           "score_rank", "f_value", "f_quality", "f_growth", "f_momentum", "g_value", "g_quality", "g_growth",
           "g_momentum", "why", "weak", "risk", "status", "reason", "since", "recheck", "period", "np_ytd", "np_ttm",
           "report_currency"]


def screened(df: pd.DataFrame) -> pd.Series:
    """Quantitative Value's first step (Gray and Carlisle 2012): the `screen` share of non-financials most likely to
    fail (Campbell-Hilscher-Szilagyi, signals.distress) or with the largest scaled total accruals (sta: the latest
    fiscal year's working-capital increase less depreciation over assets, Sloan 1996) can't be bought; they stay
    scored and can be avoided. A stock without the figure isn't screened."""
    share, fin = CONFIG["lists"]["screen"], df["financial"].astype(bool)
    worst = lambda x: x[~fin].rank(pct=True, ascending=False) <= share
    sta = df["sta"] if "sta" in df else pd.Series(np.nan, index=df.index)
    return (worst(df["distress"]) | worst(sta)).reindex(df.index, fill_value=False)


def buyable(df: pd.DataFrame, market: str) -> pd.Series:
    """Can be bought: not screened; not a small cap (HK: the names making up the last `small_share` of the field's
    free-float value, Hang Seng's SmallCap band; the CN and US fields, the 800 largest, are large and mid caps already);
    not a partnership (a non-US holder pays 10% of a sale's gross proceeds and withholding on distributions; the S&P
    500 excludes them). The rest stay scored, avoidable and checked as holdings."""
    small = CONFIG["lists"]["small_share"].get(market, 0.0)
    value = df["float_value" if "float_value" in df else "mcap"].sort_values(ascending=False, kind="stable")
    large = (value.cumsum().shift(fill_value=0) / value.sum() < 1 - small).reindex(df.index)
    return ~screened(df) & large & ~df["name"].astype(str).str.contains(PARTNERSHIP)


def slots(weights: pd.Series, n: int, room: pd.Series) -> pd.Series:
    """n places split by weight, rounded by the largest remainders (Hamilton), no group given more than its `room`
    (members); a full group's share goes to the others."""
    out, room = pd.Series(0, index=weights.index), room.reindex(weights.index).fillna(0)
    while (left := n - out.sum()) > 0 and (open_ := weights[out < room]).sum() > 0:
        q = open_ / open_.sum() * left
        add = np.minimum(np.floor(q), room[q.index] - out[q.index]).astype(int)
        rest = (q - add).where(add < room[q.index] - out[q.index]).dropna().sort_values(ascending=False, kind="stable")
        add[rest.index[:max(left - add.sum(), 0)]] += 1
        out[add.index] += add
    return out


def positions(df: pd.DataFrame, n: int, market: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The n buys and the bench (the next one in each sector held), from the scored stocks that can be bought. Each
    sector gets places by its share of the scored market's free-float value (float_value, universe.py), filled by its
    best scores; equal amounts."""
    share = df.groupby("sector")["float_value" if "float_value" in df else "mcap"].sum()
    field = df[buyable(df, market)]
    k = slots(share, n, field["sector"].value_counts())
    buys, bench = [], []
    for sector, g in field[field["sector"].map(k) > 0].groupby("sector"):
        g = ranked(g)
        buys.append(g.iloc[:k[sector]])
        bench.append(g.iloc[k[sector]:k[sector] + 1])
    buys = ranked(pd.concat(buys))
    return buys.assign(weight=1 / len(buys)), pd.concat(bench)


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


def anniversary(d: date, years: int = 1) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 February
        return d.replace(year=d.year + years, day=28)


def cycle(since: date, today: date) -> tuple[int | None, date]:
    """The years held if an anniversary passed within WINDOW days (else None), and the next anniversary."""
    k = 1
    while anniversary(since, k) <= today:
        k += 1
    due, last = anniversary(since, k), anniversary(since, k - 1)
    return (k - 1 if k > 1 and (today - last).days <= WINDOW else None), due


def recorded() -> pd.DataFrame:
    """Your holdings (data/holdings.csv, `hold`); none when there's no file or it's empty."""
    return pd.read_csv(HOLDINGS, dtype=str, keep_default_na=False) if HOLDINGS.exists() \
        else pd.DataFrame(columns=["market", "code", "name", "since"])


def held(market: str, today: date, buys: pd.Index) -> pd.DataFrame:
    """Code -> the date it counts from and name: your holdings if you keep them; else a neutral hold rating, as an
    analyst rates the names he recommended without knowing your portfolio: each name of a buy list sent to you
    (data/sent.csv) that isn't in today's, from the date of the last list it was sent in (the day its card said 持有到
    a year on), until its 12-month review and the WINDOW days to act on it have passed."""
    if len(mine := recorded()):
        return mine[mine["market"] == market].set_index("code")[["since", "name"]]
    sent = track.load_sent()
    sent = sent[(sent["market"] == market) & (sent["listed"] <= today.isoformat())]
    last = sent.sort_values("listed").groupby("ticker")[["listed", "name"]].last().rename(columns={"listed": "since"})
    live = last["since"].map(lambda d: anniversary(date.fromisoformat(d)) + timedelta(days=WINDOW) >= today)
    return last[live.astype(bool) & ~last.index.isin(buys)]


def check(df: pd.DataFrame, market: str, today: date, buys: pd.DataFrame, dropped: dict[str, str]) -> pd.DataFrame:
    """继续持有 / 复核 / 卖出 per holding (PLAN.md, "Holding rule"), judged as the buys are picked: by the score's rank
    among its sector's scored names; the results review adds its findings (review.apply)."""
    holdings, neutral = held(market, today, buys.index), not len(recorded())
    swap = next((f"{c} {buys.at[c, 'name']}" for c in buys.index if c not in holdings.index), "")
    rows = []
    for code, h in holdings.iterrows():
        years, due = cycle(date.fromisoformat(h["since"]), today)
        row = {"code": code, "name": h["name"], "since": h["since"]}
        if code not in df.index:
            rows.append(row | {"status": "复核", "recheck": today.isoformat(),
                               "reason": "今日未评分：" + ("数据缺失或与第二来源对不上" if code in dropped else "不在市值前列或数据不全") +
                                         "，看不到它在同行业的排名"})
            continue
        others = df.loc[(df["sector"] == df.at[code, "sector"]) & (df.index != code), "score"]
        others = others if len(others) else df.loc[df.index != code, "score"]
        rank, n = int((others > df.at[code, "score"]).sum()) + 1, len(others) + 1
        place = f"同行业 {n} 只中第 {rank} 名"
        if years is None and rank > n * REVIEW:
            status, reason, recheck = "复核", f"未到满年（{due}），评分跌入同行业后半（{place}）", today
        elif years is None:
            status, reason, recheck = "继续持有", f"未到满年（{due}），评分在同行业前半（{place}）", due
        elif rank <= max(1, np.ceil(n * CONFIG["lists"]["top_share"])):
            status, reason, recheck = "继续持有", f"满 {years} 年，仍在同行业前五分之一（{place}），再持有一年", due
            if neutral:  # a rating ends with the year it was recommended for; a name picked again comes back
                reason, recheck = f"满 12 个月仍在同行业前五分之一（{place}）：可继续持有，此后不再列出（重新入选会再出现）", None
        else:
            status, reason, recheck = "卖出", f"满 {years} 年，已不在同行业前五分之一（{place}）", today
            reason += f"，可换入今天的最高分 {swap}" if swap else ""
        rows.append(row | df.loc[code].to_dict() | {"status": status, "reason": reason,
                                                     "recheck": recheck.isoformat() if recheck else ""})
    return pd.DataFrame(rows).assign(list="holding")


def build(df: pd.DataFrame, market: str, today: date, dropped: dict[str, str]) -> pd.DataFrame:
    """The day's buys, the next names (they replace buys the results review removes), avoid names, holdings check
    and your vetoes, one row each (COLUMNS)."""
    cfg = CONFIG["lists"]
    vetoes = {c: v for c, v in verdicts.active(market, today, df["period"].astype(str)).items() if v["verdict"] == "veto"}
    df = df.assign(lot=df["lot"] if "lot" in df else LOT[market])
    df["lot_cost"] = df["price"] * df["lot"]
    order = ranked(df)  # ties: score.ranked
    buys, bench = positions(order[~order.index.isin(list(vetoes))], cfg["buys"], market)
    bench = ranked(bench)  # each replaces a removed buy of its sector (review.apply)
    avoid = capped(order[order["mcap_rank"] <= cfg["avoid_largest"]].iloc[::-1], cfg["avoid"], cfg["per_sector"])
    parts = [buys.assign(list="buy", rank=range(1, len(buys) + 1), recheck=anniversary(today).isoformat()),
             bench.assign(list="next", rank=range(len(buys) + 1, len(buys) + len(bench) + 1),
                          recheck=anniversary(today).isoformat()),
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
