"""Research stage 12, part 3: the research record (PLAN.md "Track record"). Every report's rating, price and target go
to data/research/log.csv when it is built: one row per listing a day (the day's last build; an A+H report logs both
lines). Twelve months on, `track` settles each row once, as observed, never recomputed: the return with dividends from
the report day's close to the last close on or before its anniversary, the index fund's with dividends over the same
closes (track.FUND), and whether the target was reached at that close and at any close before it (the price's move
from the report day's close against the target's over the logged price, so a split in the year changes nothing). The words can't be
backtested (DeepSeek would know what happened next), so this forward record is the research's evidence; sell-side
targets are met at the 12-month mark about 4 times in 10 (Bradshaw, Brown and Huang 2013)."""

import logging
from datetime import date, timedelta

import pandas as pd

from stockreport.fetch import yahoo
from stockreport.lists import anniversary
from stockreport.research import ROOT, number, sources

log = logging.getLogger(__name__)
LOG = ROOT / "log.csv"
KEPT = ["date", "market", "code", "name", "rating", "price", "currency", "target", "expected_return", "market_return"]
SETTLED = ["end", "stock_return", "fund_return", "hit_end", "hit_any"]
FUND = {"cn": ("510300", "510300.SS"), "us": ("SPY", "SPY"), "hk": ("02800", "2800.HK")}  # track.FUND's Yahoo symbols
RATED = ["买入", "持有", "卖出"]


def load() -> pd.DataFrame:
    if not LOG.exists():
        return pd.DataFrame(columns=KEPT + SETTLED)
    df = pd.read_csv(LOG, dtype={"date": str, "code": str, "end": str}).reindex(columns=KEPT + SETTLED)
    return df.astype({k: object for k in SETTLED})


def save(df: pd.DataFrame) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG.with_suffix(".tmp")
    df.to_csv(tmp, index=False, float_format="%.6g")
    tmp.replace(LOG)


def add(v: dict, today: date) -> None:
    """Log one listing's valuation (valuation.json's fields) as of today, replacing an earlier build of the same day."""
    row = {k: v.get(k) for k in KEPT[1:]} | {"date": today.isoformat()}
    df = load()
    df = df[~((df["date"] == row["date"]) & (df["market"] == row["market"]) & (df["code"] == row["code"]))]
    new = pd.DataFrame([row]).reindex(columns=KEPT + SETTLED)
    save(pd.concat([df, new], ignore_index=True) if len(df) else new)


def recent(market: str, today: date, days: int) -> dict[str, dict]:
    """Each code's newest report in the last `days` days (the daily card's research line)."""
    df = load()
    df = df[(df["market"] == market) & (df["date"] >= (today - timedelta(days=days)).isoformat())]
    return {r["code"]: r for r in df.sort_values("date").to_dict("records")}


def held(daily: pd.DataFrame, start: str, end: str) -> pd.DataFrame | None:
    """The closes after the report's day through its anniversary, once a later close shows the stock still trades."""
    window = daily[(daily["date"] > start) & (daily["date"] <= end)]
    return window if len(window) and (daily["date"] > end).any() else None


def settle_one(r: dict, http) -> dict | None:
    """One row's 12-month result, or None while it isn't due or its prices are missing (a delisted name stays open)."""
    end, since = anniversary(date.fromisoformat(r["date"])).isoformat(), date.fromisoformat(r["date"]) - timedelta(days=7)
    stock = yahoo.chart(http, (r["code"], sources.symbol(r["market"], r["code"]), since))
    fund = yahoo.chart(http, (*FUND[r["market"]], since))
    s, f = (held(x[0], r["date"], end) if x else None for x in (stock, fund))
    base = stock[0].loc[stock[0]["date"] <= r["date"], "close"] if stock else None
    if s is None or f is None or not len(base):
        return None
    grow = lambda w: float((w["close"] / w["prev_close"]).prod() - 1)  # prev_close is dividend-adjusted (yahoo.py)
    out = {"end": s["date"].iloc[-1], "stock_return": grow(s), "fund_return": grow(f)}
    if number(r["target"]):  # Yahoo's closes are split-adjusted, the logged price and target as they were
        move, aim = s["close"] / base.iloc[-1], r["target"] / r["price"]
        reached = move >= aim if aim >= 1 else move <= aim
        out |= {"hit_end": bool(reached.iloc[-1]), "hit_any": bool(reached.any())}
    return out


def settle(today: date) -> pd.DataFrame:
    """Settle every row whose anniversary has passed (written once); returns the whole log."""
    df = load()
    due = df["end"].isna() & (df["date"] < (today - timedelta(days=366)).isoformat())
    if due.any():
        http = yahoo.make_http()
        for i in df.index[due]:
            try:
                got = settle_one(df.loc[i].to_dict(), http)
            except Exception as e:
                log.warning("research record %s %s: %s", df.at[i, "code"], df.at[i, "date"], e)
                got = None
            for k, x in (got or {}).items():
                df.loc[i, k] = x
        save(df)
    return df


def show(today: date) -> str:
    """`track`'s section: each rating's 12-month results against the index fund, and how often the target was reached."""
    df = settle(today)
    if df.empty:
        return "Research reports: none logged yet (data/research/log.csv)."
    counts = ", ".join(f"{k} {n}" for k, n in df["rating"].value_counts().items())
    first = anniversary(date.fromisoformat(df["date"].min())).isoformat()
    lines = [f"Research reports: {len(df)} logged since {df['date'].min()} ({counts}); each is settled 12 months after "
             f"its day against the index fund with dividends (510300 / SPY / 2800.HK); the first is due {first}."]
    done = df[df["rating"].isin(RATED) & df["end"].notna()]
    for rating, g in done.groupby("rating"):
        hits = g.dropna(subset=["hit_end"])
        lines.append(f"  {rating}: {len(g)} settled, return {g['stock_return'].mean():+.1%} against the fund's "
                     f"{g['fund_return'].mean():+.1%} ({(g['stock_return'] - g['fund_return']).mean():+.1%}); target reached "
                     f"at 12 months {hits['hit_end'].astype(bool).mean():.0%}, at any close {hits['hit_any'].astype(bool).mean():.0%}"
                     if len(hits) else f"  {rating}: {len(g)} settled, return {g['stock_return'].mean():+.1%} against the "
                     f"fund's {g['fund_return'].mean():+.1%}")
    open_ = int((df["end"].isna() & (df["date"] < (today - timedelta(days=366)).isoformat())).sum())
    if open_:
        lines.append(f"  {open_} due but without prices yet (delisted or a failed fetch): left open")
    return "\n".join(lines)
