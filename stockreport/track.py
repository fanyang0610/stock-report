"""Tracking (PLAN.md, the live scoreboard): every report's buys and avoid names go to data/picks.csv (bucket buy / avoid
with the score; the old method's buy / hold / sell rows stay as they were); `track` prints their average return by
market and bucket against the index at 1 week, 1 and 3 months (the buys are equal amounts), from the close each pick
was priced at, chained from close / prev_close (dividends and splits included; the indexes are price indexes)."""

from datetime import date, timedelta

import pandas as pd

from stockreport.config import DATA

PICKS_LOG = DATA / "picks.csv"
SENT_LOG = DATA / "sent.csv"  # the buys of each report sent to you
SENT = ["date", "market", "ticker", "name", "listed"]  # sent on `date`, from the market's lists of `listed`
COLUMNS = ["date", "market", "bucket", "ticker", "name", "price", "price_date", "score", "rank"]
INDEX = {"us": "SPX", "hk": "HSI", "cn": "CSI300"}
HORIZONS = {"1w": 7, "1m": 30, "3m": 91}  # calendar days after the price date


def load() -> pd.DataFrame:
    return pd.read_csv(PICKS_LOG, dtype={"ticker": str, "price_date": str}) if PICKS_LOG.exists() \
        else pd.DataFrame(columns=COLUMNS)


def load_sent() -> pd.DataFrame:
    if not SENT_LOG.exists():
        return pd.DataFrame(columns=SENT)
    sent = pd.read_csv(SENT_LOG, dtype={"ticker": str}).reindex(columns=SENT)
    return sent.assign(listed=sent["listed"].fillna(sent["date"]))


def log_sent(day: date, folder) -> None:
    """Append the buys of the report in `folder` (its buys.csv) as sent to you on `day`: the record of what was
    recommended, never rewritten (data/picks.csv keeps only each day's last build, sent or not)."""
    shown = folder / "buys.csv"
    if not shown.exists():
        return
    new = pd.read_csv(shown, dtype={"ticker": str}).assign(date=day.isoformat()).reindex(columns=SENT)
    new["listed"] = new["listed"].fillna(new["date"])
    pd.concat([load_sent(), new]).drop_duplicates(["date", "market", "ticker"]).to_csv(SENT_LOG, index=False)


def log_picks(today: date, final: dict[str, pd.DataFrame]) -> None:
    """Upsert the day's lists per market (frames with code, bucket, name, price, price_date, score and rank)."""
    new = pd.concat([f.assign(date=today.isoformat(), market=m, ticker=f["code"]) for m, f in final.items()])
    new = new.reindex(columns=list(dict.fromkeys([*new.columns, *COLUMNS])))
    old = load()
    old = old[(old["date"] != today.isoformat()) | ~old["market"].isin(final)]
    pd.concat([old, new[COLUMNS]]).to_csv(PICKS_LOG, index=False, float_format="%.6g")


def tracked(market: str, today: date, codes: list[str]) -> list[str]:
    """`codes` plus the tickers picked within the longest horizon, whose prices stay current for `track`."""
    picks, cutoff = load(), (today - timedelta(days=max(HORIZONS.values()) + 10)).isoformat()
    picked = picks.loc[(picks["market"] == market) & (picks["date"] >= cutoff), "ticker"]
    return codes + sorted(set(picked) - set(codes))


def growth(prices: pd.DataFrame, codes: set[str]) -> pd.DataFrame:
    """Growth of 1 by trading day (rows) and code (columns); a day without a row counts as flat."""
    p = prices[prices["code"].isin(codes)]
    daily = (p["close"] / p["prev_close"]).groupby([p["date"], p["code"]]).last().unstack()
    return daily.fillna(1.0).cumprod()


def returns(picks: pd.DataFrame, prices: pd.DataFrame, index: str) -> pd.DataFrame:
    """Per pick: return and excess return over the index for each horizon and to date (NaN until the horizon ends)."""
    g = growth(prices, set(picks["ticker"]) | {index})
    days, out = g.index, []
    for i, p in enumerate(picks.itertuples()):
        start = days[max(days.searchsorted(p.price_date, side="right") - 1, 0)]
        ends = {h: (date.fromisoformat(p.price_date) + timedelta(days=d)).isoformat() for h, d in HORIZONS.items()}
        for h, end in ({"to date": days[-1]} | ends).items():
            if end > days[-1] or end <= start or p.ticker not in g:
                continue
            end = days[days.searchsorted(end, side="right") - 1]
            ret, idx = (g.at[end, c] / g.at[start, c] - 1 for c in (p.ticker, index))
            out.append((i, h, ret, ret - idx))
    rows = pd.DataFrame(out, columns=["i", "horizon", "avg", "vs index"]).set_index(["i", "horizon"])
    return rows.reindex(pd.MultiIndex.from_product([range(len(picks)), ["to date", *HORIZONS]], names=["i", "horizon"]))


def table(picks: pd.DataFrame, loaders: dict) -> pd.DataFrame:
    """Rows market × bucket; columns horizon × (n, avg, vs index)."""
    parts = []
    for market in INDEX:
        part = picks[picks["market"] == market].reset_index(drop=True)
        if part.empty:
            continue
        r = returns(part, loaders[market](), INDEX[market]).reset_index(level=1)
        r["market"], r["bucket"] = market.upper(), part.loc[r.index, "bucket"].values
        parts.append(r)
    g = pd.concat(parts).groupby(["market", "bucket", "horizon"], sort=False)
    out = pd.DataFrame({"n": g["avg"].count(), "avg": g["avg"].mean(), "vs index": g["vs index"].mean()})
    return out.unstack("horizon").swaplevel(axis=1)[["to date", *HORIZONS]]


def scorecard() -> int:
    from stockreport.fetch import tdx, yahoo
    picks = load().drop_duplicates(["market", "bucket", "ticker", "price_date"], keep="last")
    if picks.empty:
        print(f"No picks yet: {PICKS_LOG.name} is written by every `run`.")
        return 1
    loaders = {"cn": tdx.load_prices, "us": lambda: yahoo.load_prices("us"), "hk": lambda: yahoo.load_prices("hk")}
    t = table(picks, loaders)
    show = t.copy()
    for col in t.columns:
        show[col] = t[col].map(lambda x: "" if pd.isna(x) else f"{x:.0f}" if col[1] == "n" else f"{x:+.1%}")
    print(f"Scorecard: {len(picks)} picks (one per stock, bucket and price date) from "
          f"{picks['price_date'].min()} to {picks['price_date'].max()}, against CSI 300 / Hang Seng / S&P 500.")
    print("Return from the close the pick was priced at; 1w / 1m / 3m = 7 / 30 / 91 days later (blank until then).")
    print("'vs index' = average of pick return minus the index over the same days; an avoid name worked if it is negative.\n")
    print(show.to_string())
    return 0

