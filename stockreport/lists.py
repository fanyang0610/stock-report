"""The three ratings (PLAN.md, "Lists"), each market's top candidates, rated as a sell-side analyst rates stocks,
without anyone's portfolio: 买入 (Buy, expected to beat the market) the 20-name portfolio from the whole scored market
(each sector its places by its share of the market's free-float value, filled by its best scores, equal amounts;
Quantitative Value's screen first); 持有 (Hold, expected in line with it) the 10 steadiest prices among the largest
names at the middle of the score; 卖出 (Sell, expected to lag it) the 10 lowest scores among the largest."""

from datetime import date

import numpy as np
import pandas as pd

from stockreport import verdicts
from stockreport.config import CONFIG
from stockreport.score import ranked

LOT = {"cn": 100, "us": 1}  # HK: each stock's board lot (HKEX)
PARTNERSHIP = r"(?:\bL\.?P\.?|Limited Partnership)$"  # US master limited partnerships (K-1 units)
COLUMNS = ["list", "rank", "code", "name", "sector", "weight", "price", "price_date", "lot", "lot_cost", "score",
           "score_rank", "f_value", "f_quality", "f_growth", "f_momentum", "g_value", "g_quality", "g_growth",
           "g_momentum", "vol_1y", "why", "weak", "risk", "status", "reason", "recheck", "period", "np_ytd", "np_ttm",
           "report_currency"]


def screened(df: pd.DataFrame) -> pd.Series:
    """Quantitative Value's first step (Gray and Carlisle 2012): the `screen` share of non-financials most likely to
    fail (Campbell-Hilscher-Szilagyi, signals.distress) or with the largest scaled total accruals (sta: the latest
    fiscal year's working-capital increase less depreciation over assets, Sloan 1996) can't be bought; they stay
    scored and can be rated Sell. A stock without the figure isn't screened."""
    share, fin = CONFIG["lists"]["screen"], df["financial"].astype(bool)
    worst = lambda x: x[~fin].rank(pct=True, ascending=False) <= share
    sta = df["sta"] if "sta" in df else pd.Series(np.nan, index=df.index)
    return (worst(df["distress"]) | worst(sta)).reindex(df.index, fill_value=False)


def buyable(df: pd.DataFrame, market: str) -> pd.Series:
    """Can be bought: not screened; not a small cap (HK: the names making up the last `small_share` of the field's
    free-float value, Hang Seng's SmallCap band; the CN and US fields, the 800 largest, are large and mid caps already);
    not a partnership (a non-US holder pays 10% of a sale's gross proceeds and withholding on distributions; the S&P
    500 excludes them). The rest stay scored and can be rated Hold or Sell."""
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


def holds(df: pd.DataFrame, n: int, out: pd.Index) -> pd.DataFrame:
    """The Hold candidates in order (PLAN.md, "Lists"): among the `largest` names, those in the middle fifth of the
    market's score (`middle`: leaning neither to the top nor to the bottom), not screened (screened()) nor `out` (the
    buys and their bench, your vetoes), the steadiest prices first (1-year volatility of daily returns, the lowest first; then the code), at most
    `per_sector` a sector; the first n are the list, the next ones its bench."""
    cfg, order = CONFIG["lists"], ranked(df)
    at = pd.Series(np.arange(len(order)) / max(len(order), 1), index=order.index).reindex(df.index)
    lo, hi = cfg["middle"]
    field = df[(at >= lo) & (at < hi) & (df["mcap_rank"] <= cfg["largest"]) & ~screened(df) & ~df.index.isin(out)
               & df["vol_1y"].notna()]
    field = field.iloc[np.lexsort([field.index.astype(str), field["vol_1y"].to_numpy()])]
    return capped(field, n, cfg["per_sector"]).assign(
        reason=lambda h: [f"评分居中（全市场 {len(df)} 只中第 {r} 名）；股价波动小（近一年年化 {v:.0%}）"
                          for r, v in zip(order.index.get_indexer(h.index) + 1, h["vol_1y"])])


def sells(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """The Sell list: the n lowest scores among the `largest` names, at most `per_sector` a sector (ties: score.ranked
    reversed, so of tied names the smaller)."""
    cfg, order = CONFIG["lists"], ranked(df)
    return capped(order[order["mcap_rank"] <= cfg["largest"]].iloc[::-1], n, cfg["per_sector"])


def build(df: pd.DataFrame, market: str, today: date) -> pd.DataFrame:
    """The day's three ratings, one row each (COLUMNS): the buys, their bench (it replaces buys the results review
    removes), the Hold names and theirs, the Sell names, and your vetoes (kept out of Buy and Hold); each rating's
    re-check date is 12 months on, its horizon."""
    cfg = CONFIG["lists"]
    vetoes = {c: v for c, v in verdicts.active(market, today, df["period"].astype(str)).items() if v["verdict"] == "veto"}
    df = df.assign(lot=df["lot"] if "lot" in df else LOT[market])
    df["lot_cost"] = df["price"] * df["lot"]
    order = ranked(df)  # ties: score.ranked
    buys, bench = positions(order[~order.index.isin(list(vetoes))], cfg["buys"], market)
    bench = ranked(bench)  # each replaces a removed buy of its sector (review.apply)
    held = holds(order, cfg["holds"] + cfg["bench"], buys.index.union(bench.index).union(list(vetoes)))
    sell = sells(order, cfg["sells"])
    k, due = cfg["holds"], anniversary(today).isoformat()
    parts = [buys.assign(list="buy", rank=range(1, len(buys) + 1)),
             bench.assign(list="next", rank=range(len(buys) + 1, len(buys) + len(bench) + 1)),
             held.iloc[:k].assign(list="hold", rank=range(1, min(k, len(held)) + 1)),
             held.iloc[k:].assign(list="hold_next", rank=range(k + 1, len(held) + 1)),
             sell.assign(list="sell", rank=range(1, len(sell) + 1)),
             pd.DataFrame([{"list": "veto", "code": c, "name": df["name"].get(c, ""),
                            "reason": f"你的否决（至 {v['until']}）：{v['reason']}"} for c, v in vetoes.items()])]
    out = pd.concat([p.rename_axis("code").reset_index() if "code" not in p else p for p in parts if len(p)])
    out.loc[out["list"] != "veto", "recheck"] = due
    return out.reindex(columns=COLUMNS)
