"""Tracking (PLAN.md, "Checks": the live scorecard).

data/picks.csv: every report's three ratings (each day's last build; bucket buy / hold / sell with the price, the
review's removals beside their replacements; the old v3 method's lists of 2026-10-17..21 are bucketed v3 buy / v3 hold /
v3 sell). data/sent.csv: the buys of each report sent to you, for the report's "changes" line.

Cohorts: the first report of each month (from START) starts one per market, read from data/picks.csv (the record of
every report's three ratings; sent.csv holds only the buys, and only on the days you asked): its Buy, Hold and Sell
names in equal amounts within each rating, the index fund with dividends (FUND), and a neutral basket (the day's sector
places, as the buys get them, each sector's money spread equally over every name in it that can be bought; from the
day's snapshot). They go to data/cohorts.csv.gz once the report's day is over, and are held 12 months from the first
close after the lists' prices (on or after the report's day). At each month end and at 12 months each group's value is
written to data/cohort_marks.csv as observed and never recomputed, so the price files' rolling window can't erase it. A
name without a trade that day (suspended, delisted) is unresolved: left out of its group's value and counted, never
taken as flat. Both files are a few hundred KB a year, outside cleanup's folders."""

import logging
from datetime import date, timedelta

import pandas as pd

from stockreport import lists
from stockreport.config import CONFIG, DATA

log = logging.getLogger(__name__)
PICKS_LOG = DATA / "picks.csv"
SENT_LOG = DATA / "sent.csv"  # the buys of each report sent to you
SENT = ["date", "market", "ticker", "name", "listed"]  # sent on `date`, from the market's lists of `listed`
COLUMNS = ["date", "market", "bucket", "ticker", "name", "price", "price_date", "score", "rank"]
COHORTS = DATA / "cohorts.csv.gz"
MARKS = DATA / "cohort_marks.csv"
MEMBER = ["market", "cohort", "priced", "group", "code", "name", "weight"]  # cohort: the report's day
MARK = ["market", "cohort", "start", "mark", "months", "group", "value", "names", "unresolved", "missing", "recorded"]
WAIT = 5  # trading days a mark with unresolved names waits, so a failed fetch's gap is filled first (Yahoo refetches 10 days)
START = "2026-11-07"  # the first report of November built by the score as it stands (stage 6's inputs): PLAN, stage 8
FUND = {"cn": "510300", "us": "SPY", "hk": "02800"}  # 沪深300ETF, SPDR S&P 500, 盈富基金: prices with dividends
RATINGS = ["buy", "hold", "sell"]
GROUPS = RATINGS + ["basket", "fund"]


def load() -> pd.DataFrame:
    return pd.read_csv(PICKS_LOG, dtype={"ticker": str, "price_date": str}) if PICKS_LOG.exists() \
        else pd.DataFrame(columns=COLUMNS)


def load_sent() -> pd.DataFrame:
    if not SENT_LOG.exists():
        return pd.DataFrame(columns=SENT)
    sent = pd.read_csv(SENT_LOG, dtype={"ticker": str}).reindex(columns=SENT)
    return sent.assign(listed=sent["listed"].fillna(sent["date"]))


def log_sent(day: date, buys: pd.DataFrame) -> None:
    """Append the buys of a report sent to you on `day` (market, ticker, name, listed: as report.build returned them
    for that very text, not a file a later build may have rewritten): the record of what was sent, never rewritten
    (data/picks.csv keeps only each day's last build, sent or not)."""
    new = buys.assign(date=day.isoformat()).reindex(columns=SENT)
    new["listed"] = new["listed"].fillna(new["date"])
    pd.concat([load_sent(), new]).drop_duplicates(["date", "market", "ticker"]).to_csv(SENT_LOG, index=False)


def log_picks(today: date, final: dict[str, pd.DataFrame]) -> None:
    """Upsert the day's lists per market (frames with code, bucket, name, price, price_date, score and rank)."""
    new = pd.concat([f.assign(date=today.isoformat(), market=m, ticker=f["code"]) for m, f in final.items()])
    new = new.reindex(columns=list(dict.fromkeys([*new.columns, *COLUMNS])))
    old = load()
    old = old[(old["date"] != today.isoformat()) | ~old["market"].isin(final)]
    pd.concat([old, new[COLUMNS]]).to_csv(PICKS_LOG, index=False, float_format="%.6g")


def load_cohorts() -> pd.DataFrame:
    return pd.read_csv(COHORTS, dtype=str).astype({"weight": float}) if COHORTS.exists() \
        else pd.DataFrame(columns=MEMBER)


def load_marks() -> pd.DataFrame:
    return pd.read_csv(MARKS, dtype={"cohort": str, "start": str, "mark": str, "missing": str}) if MARKS.exists() \
        else pd.DataFrame(columns=MARK)


def tracked(market: str, today: date, codes: list[str]) -> list[str]:
    """`codes` plus the fund and the names of the cohorts of the last 13 months, whose prices stay current."""
    c = load_cohorts()
    keep = c.loc[(c["market"] == market) & (c["cohort"] >= (today - timedelta(days=400)).isoformat()), "code"]
    return codes + sorted((set(keep) | {FUND[market]}) - set(codes))


def first_reports(picks: pd.DataFrame) -> pd.DataFrame:
    """Each market's first report of each month from START (columns market, month, date)."""
    p = picks[picks["bucket"].isin(RATINGS) & (picks["date"] >= START)]
    return p.assign(month=p["date"].str[:7]).groupby(["market", "month"])["date"].min().reset_index()


def basket(snap: pd.DataFrame, market: str) -> pd.Series:
    """The neutral basket (backtest/qvm.neutral on one day): code -> weight. The buys' sector places (lists.slots on
    the scored market's free-float value), each sector's money spread equally over its names that can be bought."""
    field = snap[lists.buyable(snap, market)]
    count = field["sector"].value_counts()
    k = lists.slots(snap.groupby("sector")["float_value" if "float_value" in snap else "mcap"].sum(),
                    CONFIG["lists"]["buys"], count)
    w = field["sector"].map(k / k.sum() / count)
    return w[w > 0]


def members(picks: pd.DataFrame, market: str, day: str, snap: pd.DataFrame | None) -> pd.DataFrame:
    """One cohort's rows (MEMBER): the day's Buy, Hold and Sell names, equal amounts within each; the fund; the basket
    (none without the day's snapshot)."""
    rows = picks[(picks["date"] == day) & (picks["market"] == market) & picks["bucket"].isin(RATINGS)]
    rows = rows.drop_duplicates(["bucket", "ticker"])
    parts = [pd.DataFrame({"group": rows["bucket"], "code": rows["ticker"], "name": rows["name"],
                           "weight": 1 / rows.groupby("bucket")["ticker"].transform("size")}),
             pd.DataFrame({"group": ["fund"], "code": [FUND[market]], "name": [""], "weight": [1.0]})]
    if snap is not None:
        w = basket(snap, market)
        parts.append(pd.DataFrame({"group": "basket", "code": w.index.astype(str), "name": "", "weight": w.to_numpy()}))
    return pd.concat(parts).assign(market=market, cohort=day, priced=rows["price_date"].max())[MEMBER]


def record(today: date) -> pd.DataFrame:
    """Add the cohorts of the month-first reports whose day is over; returns every cohort's rows."""
    have, picks = load_cohorts(), load()
    done, new = set(zip(have["market"], have["cohort"])), []
    for r in first_reports(picks).itertuples():
        if r.date >= today.isoformat() or (r.market, r.date) in done:
            continue
        path = DATA / "snapshots" / r.date / f"{r.market}.csv.gz"
        snap = pd.read_csv(path, dtype={"code": str}).set_index("code") if path.exists() else None
        if snap is None:
            log.warning("cohort %s %s: no snapshot of the day, so no neutral basket", r.market.upper(), r.date)
        new.append(members(picks, r.market, r.date, snap))
    if new:
        have = pd.concat([have, *new])
        save(have, COHORTS, compression="gzip", float_format="%.8g")
    return have


def save(df: pd.DataFrame, path, **kw) -> None:
    """Written whole and swapped in: the scorecard's files can't be rebuilt once the prices have moved on."""
    tmp = path.with_name(path.name + ".tmp")
    df.to_csv(tmp, index=False, **kw)
    tmp.replace(path)


def start(days: pd.Index, cohort: str, priced: str) -> str | None:
    """The cohort's first close: the first trading day after the report's day (the cohort is the day's last build, which
    an evening review may have changed after that day's close) and after the lists' prices."""
    after = days[days > max(cohort, priced)]
    return after[0] if len(after) else None


def due(days: pd.Index, first: str) -> list[str]:
    """The marks that have closed: each month's last trading day after the first close, then the 12-month close (the
    last trading day on or before its anniversary). A mark is due once a later close is in."""
    end = lists.anniversary(date.fromisoformat(first)).isoformat()
    held = list(days[(days > first) & (days <= end)])
    ends = [d for d, nxt in zip(held, held[1:] + [None]) if nxt is None or nxt[:7] != d[:7]]
    return [d for d in ends if (days > d).any()]


def growth(prices: pd.DataFrame, codes: set[str], days: pd.Index) -> pd.DataFrame:
    """Growth of 1 by trading day and code, chained from close / prev_close (dividends included); a day without a row
    adds nothing, so a resumed name's first return runs from its last close."""
    p = prices[prices["code"].isin(codes)]
    daily = (p["close"] / p["prev_close"]).groupby([p["date"], p["code"]]).last().unstack()
    return daily.reindex(days).fillna(1.0).cumprod()


def traded(prices: pd.DataFrame, day: str) -> set[str]:
    """The codes with a price on `day`, less those with neither a trade nor a price change (suspended: 通达信 and Yahoo
    show the last close with volume 0). Volume alone won't do: Yahoo gives every HK row volume 0 on half days."""
    p = prices[prices["date"] == day]
    return set(p.loc[(p["volume"] > 0) | (p["close"] != p["prev_close"]), "code"])


def value(g: pd.DataFrame, live: set[str], group: pd.DataFrame, first: str, day: str) -> tuple[float, int, list[str]]:
    """(value of 1 put in at the first close, names counted, the unresolved names) on `day`: the weighted growth of the
    names that traded that day, their weights scaled to sum to 1. Each unresolved name is kept as code=its growth to its
    last close (code alone if never priced), for the record; it isn't in the value."""
    w = group.set_index("code")["weight"]
    ok = [c for c in w.index if c in live and c in g.columns]
    missing = [f"{c}={g.at[day, c] / g.at[first, c]:.4f}" if c in g.columns else c for c in w.index if c not in ok]
    if not ok:
        return float("nan"), 0, missing
    grown = g.loc[day, ok] / g.loc[first, ok]
    return float((grown * w[ok]).sum() / w[ok].sum()), len(ok), missing


def marks_for(cohort: pd.DataFrame, prices: pd.DataFrame, days: pd.Index, first: str, at: list[str]) -> list[dict]:
    """Each group's value at the given closes from the first close (MARK rows without `recorded`)."""
    g, out = growth(prices, set(cohort["code"]), days), []
    for day in at:
        live = traded(prices, day)
        for name, group in cohort.groupby("group"):
            v, n, missing = value(g, live, group, first, day)
            out.append({"market": cohort["market"].iloc[0], "cohort": cohort["cohort"].iloc[0], "start": first,
                        "mark": day, "months": round((date.fromisoformat(day) - date.fromisoformat(first)).days / 30.44, 1),
                        "group": name, "value": v, "names": n, "unresolved": len(missing), "missing": " ".join(missing)})
    return out


def first_close(marks: pd.DataFrame, days: pd.Index, market: str, cohort: pd.DataFrame) -> str | None:
    """The cohort's first close: as its marks recorded it, else from the price file."""
    key, known = cohort["cohort"].iloc[0], marks.loc[(marks["market"] == market), ["cohort", "start"]]
    known = known.loc[known["cohort"] == key, "start"]
    return known.iloc[0] if len(known) else start(days, key, cohort["priced"].iloc[0])


def update(today: date, loaders: dict) -> pd.DataFrame:
    """Record new cohorts and every mark that has closed since (`loaders`: market -> its price table). A mark with an
    unresolved name waits until WAIT later closes are in, so a name a failed fetch missed is filled in first; one still
    without a price then is suspended or gone. A mark taken after the cohort's first close has left the price file's
    window (385 days) can't be valued: logged, left out."""
    cohorts, marks = record(today), load_marks()
    done, rows = set(zip(marks["market"], marks["cohort"], marks["mark"])), []
    for market, part in cohorts.groupby("market"):
        prices = loaders[market]()
        days = pd.Index(sorted(prices["date"].unique()))
        for key, cohort in part.groupby("cohort"):
            first = first_close(marks, days, market, cohort)
            todo = [d for d in (due(days, first) if first else []) if (market, key, d) not in done]
            if todo and first not in days:
                log.warning("cohort %s %s: its first close %s is no longer in the prices", market.upper(), key, first)
            elif todo:
                for day in todo:
                    new = marks_for(cohort, prices, days, first, [day])
                    if (days > day).sum() >= WAIT or not any(r["unresolved"] for r in new):
                        rows += new
    if rows:
        marks = pd.concat([marks, pd.DataFrame(rows).assign(recorded=today.isoformat())])[MARK]
        save(marks, MARKS, float_format="%.6g")
    return marks


def standing(marks: pd.DataFrame, market: str) -> tuple[pd.DataFrame, int]:
    """Each cohort's newest mark (one row per cohort with start, mark, months and the groups' returns), and how many
    different names of the three ratings are unresolved in them."""
    m = marks[marks["market"] == market]
    if m.empty:
        return pd.DataFrame(), 0
    m = m[m["mark"] == m.groupby("cohort")["mark"].transform("max")]
    wide = m.pivot_table(index=["cohort", "start", "mark", "months"], columns="group", values="value")
    gone = {x.split("=")[0] for x in " ".join(m.loc[m["group"].isin(RATINGS), "missing"].fillna("")).split()}
    return wide.sub(1).reset_index().reindex(columns=["cohort", "start", "mark", "months", *GROUPS]), len(gone)


def loaders() -> dict:
    from stockreport.fetch import tdx, yahoo
    return {"cn": tdx.load_prices, "us": lambda: yahoo.load_prices("us"), "hk": lambda: yahoo.load_prices("hk")}


def scorecard() -> int:
    """Each cohort against the fund and the basket: its month-end marks, and its value at the newest close."""
    today, load_prices = date.today(), loaders()
    marks, cohorts = update(today, load_prices), load_cohorts()
    if cohorts.empty:
        print(f"No cohort yet: the first report of each month from {START} starts one (data/picks.csv).")
        return 1
    pct = lambda x: "" if pd.isna(x) else f"{x:+.1%}"
    print("Scorecard: the first report of each month, held 12 months from the first close after it; equal amounts "
          "within each rating;\nfund = the index fund with dividends (510300 / SPY / 2800.HK); basket = the same sector "
          "places, every name that can be bought.\nValues at month-end closes since the first close; unresolved = names "
          "with no trade that day (suspended, delisted), left out.\n")
    for market in [m for m in FUND if m in set(cohorts["market"])]:
        part = cohorts[cohorts["market"] == market]
        prices = load_prices[market]()
        days = pd.Index(sorted(prices["date"].unique()))
        for key, cohort in part.groupby("cohort"):
            rows = marks[(marks["market"] == market) & (marks["cohort"] == key)]
            first = first_close(marks, days, market, cohort)
            sizes = cohort.groupby("group").size().reindex(GROUPS, fill_value=0)
            print(f"{market.upper()} cohort {key} (lists priced {cohort['priced'].iloc[0]}; "
                  + ", ".join(f"{g} {n}" for g, n in sizes.items()) + f"): first close {first or 'after ' + max(key, cohort['priced'].iloc[0]) + ', not in yet'}")
            if first in days and days[-1] > first:  # the newest close, shown but not kept
                now = marks_for(cohort, prices, days, first, [days[-1]])
                rows = pd.concat([rows, pd.DataFrame(now).assign(recorded="now")])
            if rows.empty:
                print("  no close since the first one yet\n")
                continue
            t = rows.pivot_table(index=["mark", "months", "recorded"], columns="group", values="value").reindex(
                columns=GROUPS).sub(1)
            u = rows[rows["group"] != "fund"].groupby("mark")["unresolved"].sum()
            show = pd.DataFrame({g: t[g].map(pct) for g in GROUPS})
            show["buy-fund"], show["buy-basket"] = (t["buy"] - t["fund"]).map(pct), (t["buy"] - t["basket"]).map(pct)
            show["unresolved"] = u.reindex(t.index.get_level_values("mark")).to_numpy()
            print(show.reset_index().drop(columns="recorded").to_string(index=False) + "\n")
    return 0
