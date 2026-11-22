"""The three ratings (PLAN.md, "Lists"), each market's top candidates, rated as a sell-side analyst rates stocks,
without anyone's portfolio: 买入 (Buy, expected to beat the market) the 20-name portfolio from the whole scored market
(each sector its places by its share of the market's free-float value, filled by its best scores, equal amounts;
Quantitative Value's screen first); 持有 (Hold, expected in line with it) the 10 steadiest prices among the largest
names at the middle of the score; 卖出 (Sell, expected to lag it) the 10 most expensive, lowest-quality and most
distressed among the largest, outside momentum's top fifth. A name rated in the newest earlier report keeps its rating until it falls well past
the cut (buffered: MSCI's and CSI's 20% buffer)."""

import math
from datetime import date

import numpy as np
import pandas as pd

from stockreport import verdicts
from stockreport.config import CONFIG, DATA
from stockreport.score import DIGITS, card_lines, grade, ranked
from stockreport.signals import FAMILIES, MIDDLE

LOT = {"cn": 100, "us": 1}  # HK: each stock's board lot (HKEX)
PARTNERSHIP = r"(?:\bL\.?P\.?|Limited Partnership)$"  # US master limited partnerships (K-1 units)
PICKS = DATA / "picks.csv"  # every report's ratings, each day's last build (written by track.log_picks)
NONE = {"buy": pd.Index([]), "hold": pd.Index([]), "sell": pd.Index([])}
COLUMNS = ["list", "rank", "code", "name", "sector", "weight", "price", "price_date", "lot", "lot_cost", "score",
           "score_rank", "f_value", "f_quality", "f_momentum", "g_value", "g_quality", "g_momentum", "vol_1y", "why", "weak", "risk", "status", "reason", "recheck", "period", "np_ytd", "np_ttm",
           "report_currency"]


def rated(market: str, today: date) -> dict[str, pd.Index]:
    """The ratings of the market's newest report before `today` (data/picks.csv: buy, hold, sell; a buy or Hold the
    review removed isn't rated, its replacement is): the names the buffer keeps. None yet: no name is kept."""
    if not PICKS.exists():
        return NONE
    log = pd.read_csv(PICKS, dtype={"ticker": str, "date": str}, usecols=["date", "market", "bucket", "ticker"])
    log = log[(log["market"] == market) & (log["date"] < today.isoformat()) & log["bucket"].isin(list(NONE))]
    if log.empty:
        return NONE
    last = log[log["date"] == log["date"].max()]
    return {k: pd.Index(last.loc[last["bucket"] == k, "ticker"].unique()) for k in NONE}


def buffered(order: pd.Index, current: pd.Index, n: int) -> pd.Index:
    """`order` (best first) with the buffer applied for n places, as MSCI's Quality Indexes (2025, section 3.1.1) and
    CSI's indexes (the CSI 300: new names in the top 240 first, current ones in the top 360 next) keep their
    constituents: the names within the first (1 - b) × n come first, then the current names within (1 + b) × n
    (b: `buffer`, 20%), then the rest in order. The first n of the result are the list. Rounded so that the buffer
    is at least one place (with one place, the current name stays while it is first or second)."""
    b = CONFIG["lists"]["buffer"]
    at = np.arange(len(order))
    first = at < math.floor((1 - b) * n + 1e-9)
    keep = order.isin(current) & (at < math.ceil((1 + b) * n - 1e-9)) & ~first
    return order[first].append(order[keep]).append(order[~first & ~keep])


def screened(df: pd.DataFrame) -> pd.Series:
    """Quantitative Value's first step (Gray and Carlisle 2012): the `screen` share of non-financials most likely to
    fail (Campbell-Hilscher-Szilagyi, signals.distress) or with the largest scaled total accruals (sta: the latest
    fiscal year's working-capital increase less depreciation over assets, Sloan 1996) can't be bought; they stay
    scored and can be rated Sell. A stock without the figure isn't screened."""
    share, fin = CONFIG["lists"]["screen"], df["financial"].astype(bool)
    worst = lambda x: x[~fin].rank(pct=True, ascending=False) <= share
    sta = df["sta"] if "sta" in df else pd.Series(np.nan, index=df.index)
    return (worst(df["distress"]) | worst(sta)).reindex(df.index, fill_value=False)


def by_value(df: pd.DataFrame) -> pd.Series:
    """Each name's place by free-float value (1: the largest; CN by the CSI float, HK the HK-listed value)."""
    value = df["float_value" if "float_value" in df else "mcap"].sort_values(ascending=False, kind="stable")
    return pd.Series(np.arange(1, len(value) + 1), index=value.index).reindex(df.index)


def large(df: pd.DataFrame, market: str) -> pd.Series:
    """Not a small cap: HK the names making up the first 1 - `small_share` of the field's free-float value (Hang Seng's
    LargeCap and MidCap bands; its SmallCap band is the last 5%); the CN and US fields, the 800 largest, are large and
    mid caps already."""
    small = CONFIG["lists"]["small_share"].get(market, 0.0)
    value = df["float_value" if "float_value" in df else "mcap"].sort_values(ascending=False, kind="stable")
    return (value.cumsum().shift(fill_value=0) / value.sum() < 1 - small).reindex(df.index)


def biggest(df: pd.DataFrame, market: str, current: pd.Index) -> pd.Series:
    """Hold's and Sell's field: the names an investor is likely to know or hold. CN and the US the `largest` by market
    value (400 of the 800 scored); HK, where the count would cut nothing (~400 scored), Buy's band (large(): the top
    95% of HK-listed value, ~210 names). A `current` name stays while within the field's count × (1 + `buffer`)."""
    cfg = CONFIG["lists"]
    if market in cfg["small_share"]:
        place, n = by_value(df), int(large(df, market).sum())
    else:
        place, n = df["mcap_rank"], cfg["largest"]
    return (place <= n) | (df.index.isin(current) & (place <= math.ceil(n * (1 + cfg["buffer"]) - 1e-9)))


def big_words(market: str) -> str:
    """biggest() in words, for the headings and the review's card."""
    cfg = CONFIG["lists"]
    return "港股大中盘股" if market in cfg["small_share"] else f"市值前 {cfg['largest']} 只"


def buyable(df: pd.DataFrame, market: str) -> pd.Series:
    """Can be bought: not screened; not a small cap (large()); not a partnership (a non-US holder pays 10% of a sale's
    gross proceeds and withholding on distributions; the S&P 500 excludes them). The rest stay scored and can be rated
    Hold or Sell."""
    return ~screened(df) & large(df, market) & ~df["name"].astype(str).str.contains(PARTNERSHIP)


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


def positions(df: pd.DataFrame, n: int, market: str, current: pd.Index = NONE["buy"]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The n buys and the bench (the next one in each sector held), from the scored stocks that can be bought. Each
    sector gets places by its share of the scored market's free-float value (float_value, universe.py), filled by its
    best scores, the `current` buys kept within the buffer (buffered: with k places, while within the sector's best
    ceil(1.2 k)); equal amounts."""
    share = df.groupby("sector")["float_value" if "float_value" in df else "mcap"].sum()
    field = df[buyable(df, market)]
    k = slots(share, n, field["sector"].value_counts())
    buys, bench = [], []
    for sector, g in field[field["sector"].map(k) > 0].groupby("sector"):
        g = g.loc[buffered(ranked(g).index, current, k[sector])]
        buys.append(g.iloc[:k[sector]])
        bench.append(g.iloc[k[sector]:k[sector] + 1])
    buys = ranked(pd.concat(buys))
    return buys.assign(weight=1 / len(buys)), pd.concat(bench)


def capped(ranked: pd.DataFrame, n: int, cap: int) -> pd.DataFrame:
    """The first n rows in order, at most `cap` per sector (n = len(ranked): the whole order with the cap applied)."""
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


def holds(df: pd.DataFrame, n: int, out: pd.Index, current: pd.Index = NONE["hold"], market: str = "") -> pd.DataFrame:
    """The Hold candidates in order (PLAN.md, "Lists"): in Hold's and Sell's field (biggest()), those in the middle fifth
    of the market's score (`middle`: leaning neither to the top nor to the bottom), not screened (screened()) nor `out`
    (the buys and their bench, the Sell names, your vetoes), the steadiest prices first (1-year volatility of daily
    returns, the lowest first; then the code), at most `per_sector` a sector; the first n are the list, the next `bench`
    its bench. A `current` Hold stays within the buffer: the band and the field widened by `buffer` (the middle fifth's
    20%: 36% to 64%; the field's count × 1.2), and its place among the capped order (buffered)."""
    cfg, order = CONFIG["lists"], ranked(df)
    at = pd.Series(np.arange(len(order)) / max(len(order), 1), index=order.index).reindex(df.index)
    (lo, hi), b, cur = cfg["middle"], cfg["buffer"], df.index.isin(current)
    pad = b * (hi - lo)
    band = ((at >= lo) & (at < hi)) | (cur & (at >= lo - pad) & (at < hi + pad))
    field = df[band & biggest(df, market, current) & ~screened(df) & ~df.index.isin(out) & df["vol_1y"].notna()]
    field = field.iloc[np.lexsort([field.index.astype(str), field["vol_1y"].to_numpy()])]
    field = capped(field, len(field), cfg["per_sector"])
    return field.loc[buffered(field.index, current, n)].iloc[:n + cfg["bench"]].assign(
        reason=lambda h: [f"评分居中（全市场 {len(df)} 只中第 {r} 名）；股价波动小（近一年年化 {v:.0%}）"
                          for r, v in zip(order.index.get_indexer(h.index) + 1, h["vol_1y"])])


def junk(df: pd.DataFrame) -> pd.Series:
    """Sell's measure, the lower the more expensive, lower-quality and distressed: the mean of the value family, the
    quality family and safety (1 - the percentile of Campbell-Hilscher-Szilagyi's failure logit, signals.distress,
    outside the financial sector; missing, as for the financial sector, at the middle). The short side of Novy-Marx's
    (2013) profitable value and of Asness, Frazzini and Pedersen's quality minus junk (2019), whose safety includes
    the failure scores; Campbell, Hilscher and Szilagyi (2008) found the likeliest to fail earn the least. Weak
    momentum doesn't count towards Sell: losers rebound when markets turn (Daniel and Moskowitz 2016); strong momentum
    keeps a name off the list (sells())."""
    risk = df["distress"].rank(pct=True)
    return ((df["f_value"] + df["f_quality"] + (1 - risk).fillna(MIDDLE)) / 3).round(DIGITS)


def sells(df: pd.DataFrame, n: int, out: pd.Index = NONE["sell"], current: pd.Index = NONE["sell"],
          market: str = "") -> pd.DataFrame:
    """The Sell list: in Hold's and Sell's field (biggest()), not `out` (the buys and their bench), not in momentum's
    top fifth (grade A: among the year's strongest winners value and the failure risk don't predict lagging, Asness
    1997; a protection like the buys' screen, so not buffered), the lowest of junk() (ties: the smaller free float,
    then the code), at most `per_sector` a sector, the `current` ones kept within the buffer on that capped order
    (buffered: the first 8, then current names within the first 12). With the score's card lines, `weak` names the
    two weakest value and quality components and `reason` the failure logit's place when in the riskiest `risky`
    share, in words that say what it weighs."""
    cfg, key = CONFIG["lists"], junk(df)
    field = df[biggest(df, market, current) & ~df.index.isin(out) & (grade(df["f_momentum"]) != "A")]
    value = field["float_value" if "float_value" in field else "mcap"]
    order = pd.DataFrame({"k": key[field.index], "v": value, "c": field.index.astype(str)}).sort_values(["k", "v", "c"])
    order = capped(field.loc[order.index], len(order), cfg["per_sector"]).index
    sell = field.loc[buffered(order, current, n)[:n]]
    if "why" not in sell or not market:  # the history's frames carry no card lines
        return sell
    used = sorted({c for f in ("value", "quality") for c in FAMILIES[f][market]})
    risk = df["distress"].rank(pct=True, ascending=False)
    lines = {code: card_lines(row, used, market)[1] for code, row in sell.iterrows()}
    reason = {code: f"综合风险（亏损、负债、股价波动和下跌）在全市场非金融股中排前 {math.ceil(risk[code] * 100)}%"
              if risk.get(code, 1) <= cfg["risky"] else "" for code in sell.index}  # the grades are on the card
    return sell.assign(weak=pd.Series(lines), reason=pd.Series(reason))


def build(df: pd.DataFrame, market: str, today: date, current: dict[str, pd.Index] = NONE) -> pd.DataFrame:
    """The day's three ratings, one row each (COLUMNS): the buys, their bench (it replaces buys the results review
    removes), the Sell names, the Hold names and theirs, and your vetoes (kept out of Buy and Hold); `current`: the
    ratings of the newest earlier report (rated()), which the buffer keeps. A name has one rating: Sell leaves out the
    buys and their bench, Hold also the Sell names. Each rating's re-check date is 12 months on, its horizon."""
    cfg = CONFIG["lists"]
    vetoes = {c: v for c, v in verdicts.active(market, today, df["period"].astype(str)).items() if v["verdict"] == "veto"}
    df = df.assign(lot=df["lot"] if "lot" in df else LOT[market])
    df["lot_cost"] = df["price"] * df["lot"]
    order = ranked(df)  # ties: score.ranked
    buys, bench = positions(order[~order.index.isin(list(vetoes))], cfg["buys"], market, current["buy"])
    bench = ranked(bench)  # each replaces a removed buy of its sector (review.apply)
    taken = buys.index.union(bench.index)
    sell = sells(order, cfg["sells"], taken, current["sell"], market)
    held = holds(order, cfg["holds"], taken.union(sell.index).union(list(vetoes)), current["hold"], market)
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
