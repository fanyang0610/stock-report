"""Tracking (PLAN.md Method 10): every report's final picks go to data/picks.csv, and `track` prints
their average return by market and bucket against the market's index at 1 week, 1 month and 3 months.
Returns run from the close the pick was priced at, chained from close / prev_close (dividends and
splits included; the indexes are price indexes)."""

from datetime import date, timedelta

import pandas as pd

from stockreport.config import DATA

PICKS_LOG = DATA / "picks.csv"
COLUMNS = ["date", "market", "bucket", "ticker", "name", "price", "price_date", "fv_mid", "composite", "conviction"]
INDEX = {"us": "SPX", "hk": "HSI", "cn": "CSI300"}
HORIZONS = {"1w": 7, "1m": 30, "3m": 91}  # calendar days after the price date


def load() -> pd.DataFrame:
    return pd.read_csv(PICKS_LOG, dtype={"ticker": str, "price_date": str}) if PICKS_LOG.exists() \
        else pd.DataFrame(columns=COLUMNS)


def log_picks(today: date, final: dict[str, pd.DataFrame]) -> None:
    """Upsert the day's final picks per market (after AI swaps and the issuer dedupe)."""
    new = pd.concat([f.assign(date=today.isoformat(), market=m, ticker=f["code"]) for m, f in final.items()])
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
    r = pd.concat(parts)
    stats = r.groupby(["market", "bucket", "horizon"], sort=False)[["avg", "vs index"]].agg(["count", "mean"])
    out = pd.DataFrame({"n": stats[("avg", "count")], "avg": stats[("avg", "mean")], "vs index": stats[("vs index", "mean")]})
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
    print("'vs index' = average of pick return minus the index over the same days; a sell worked if it is negative.\n")
    print(show.to_string())
    return 0


def signals() -> int:
    """`track --signal`: the backtest's measures (stockreport/signal.py) on the live snapshots, v1 and v3."""
    from stockreport import signal
    from stockreport.fetch import tdx, yahoo
    loaders = {"cn": tdx.load_prices, "us": lambda: yahoo.load_prices("us"), "hk": lambda: yahoo.load_prices("hk")}
    print("Signal tracking on the saved snapshots: rank correlation of v1's and v3's upside with the returns since,\n"
          "and the buckets against the equal-weight snapshot universe (docs/BACKTEST.md has the backtest's numbers).")
    for market in INDEX:
        df = signal.live(market, loaders[market](), INDEX[market])
        if df.empty:
            print(f"\n== {market.upper()}: no snapshot with v3 columns yet")
            continue
        signal.report(market, df)
    return 0
