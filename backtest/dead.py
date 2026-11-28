"""Stage 27: the names a survivor-only history leaves out (docs/PLAN.md "Stages" 27, docs/BACKTEST.md section 30).
Free sources that keep delisted names, as verified on 2026-11-23: Tencent's kline endpoints (raw and
back-adjusted monthly closes, CN and HK, delisted names included; Eastmoney's push2his has the same but drops a burst of
calls), Eastmoney's HK list and results (partly), Baostock (CN:
the delisted A-shares' daily prices and quarterly financials by publication date). Nothing here runs in the app; only
extracted tables are kept (data/backtest/), raw responses are parsed in memory.

  uv run python -m backtest.dead hk-prices      # monthly closes and total returns of the HK names with no Yahoo history
  uv run python -m backtest.dead us-filers      # the large SEC filers that stopped filing, and how they ended
  uv run --group backtest python -m backtest.dead cn-prices    # delisted A-shares' daily prices and valuation (Baostock)
  uv run --group backtest python -m backtest.dead cn-results   # and their quarterly results by publication date
  uv run --group backtest python -m backtest.dead cn-annual    # every delisted A-share's yearly revenue, profit and ROE
"""

import functools
import logging
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

from backtest.fetch import BT, write
from stockreport.fetch import HISTORY, Http, each, eastmoney, sec

log = logging.getLogger("backtest.dead")
RAW, ADJUSTED = ("https://web.ifzq.gtimg.cn/appstock/app/kline/kline", "https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get")
HK_DEAD = BT / "hk_dead_monthly.csv.gz"
HK_FROM = "2015-09"  # one month before Yahoo's table starts (a month's return needs the one before)


def kline(http: Http, symbol: str, adjusted: bool) -> pd.Series:
    """Monthly closes (index: month) of one Tencent symbol (hk03333, sz300104), as traded or back-adjusted. Empty when
    Tencent has none; the delisted names' history is kept."""
    if adjusted:
        resp = http.get(ADJUSTED, params={"param": f"{symbol},month,,,800,hfq"})
    else:
        resp = http.get(RAW, params={"param": f"{symbol},month,,,800"})
    data = resp.json().get("data") or {}
    rows = next((v for k, v in (data.get(symbol) or {}).items() if k.endswith("month")), [])
    return pd.Series({r[0][:7]: float(r[2]) for r in rows}, dtype=float)


RATIOS = {x for n in (2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 100) for x in (n, 1 / n)}  # splits and consolidations


def total_return(raw: pd.Series, adj: pd.Series) -> pd.Series:
    """Each month's total return from the as-traded close and the back-adjusted one, on the whole series from the
    listing. The adjustment adds each dividend, times the share scale so far, to the later closes and multiplies the
    later closes by a split's ratio (the scale), so a month's return is the adjusted move over (scale × the month
    before's close), whatever happened in it. The scale in force is the median of the last three months' adjusted move
    over the raw move (a month the raw close moved 3% or more; a dividend month is off, the median isn't); a month
    whose adjusted move is a round ratio (RATIOS) times the raw one is a split or consolidation and resets it."""
    out, seen = [float("nan")], [adj.iloc[0] / raw.iloc[0]]
    for i in range(1, len(raw)):
        r0, r1, a0, a1 = raw.iloc[i - 1], raw.iloc[i], adj.iloc[i - 1], adj.iloc[i]
        if not (r0 > 0 and r1 > 0):
            out.append(float("nan"))
            continue
        scale = float(np.median(seen[-3:]))
        ret = (a1 - a0) / (scale * r0) if scale > 0 else float("nan")
        out.append(ret if np.isfinite(ret) and ret > -1 else r1 / r0 - 1)  # a scale lost (penny prices): the price move
        q = (a1 / a0) / (r1 / r0) if a0 != 0 else 1.0
        n = round(q) if q > 1.5 else 1 / round(1 / q) if 0 < q < 0.67 else 1
        if n in RATIOS and abs(q / n - 1) < 0.04 and abs(a1 / a0 - 1) < 0.5:
            seen = [scale * n]
        elif abs(r1 - r0) >= 0.03 * r0 and (a1 - a0) / (r1 - r0) > 0:
            seen.append((a1 - a0) / (r1 - r0))
    return pd.Series(out, index=raw.index)


def hk_prices() -> None:
    """Monthly (code, month, close, ret) for the HK ordinary shares Yahoo has no history for (today's top candidates
    only), whether alive or delisted: the names a candidate list taken from today leaves out."""
    have = set(pd.read_csv(HISTORY / "hk_monthly.csv.gz", dtype={"code": str})["code"])
    lst = eastmoney.load_hk_list()
    lst = lst[lst["org_type"].notna() & (lst["code"] < "10000")]
    res = pd.read_csv(HISTORY / "hk_results.csv.gz", dtype={"code": str})
    todo = sorted((set(lst["code"]) & set(res["code"])) - have)
    log.info("hk dead prices: %d codes", len(todo))

    def one(http, code):
        raw, adj = kline(http, f"hk{code}", False), kline(http, f"hk{code}", True)
        if len(raw) < 2:
            return None
        raw = raw[raw.index < pd.Timestamp.today().strftime("%Y-%m")]
        adj = adj.reindex(raw.index)
        ok = raw.notna() & adj.notna()
        ret = total_return(raw[ok], adj[ok])  # on the whole series: the scale is 1 at the listing
        keep = ret.index >= HK_FROM
        return pd.DataFrame({"code": code, "month": ret.index[keep], "close": raw[ok][keep].to_numpy(), "ret": ret[keep].to_numpy()})

    frames = [f for f in each(lambda: Http(min_interval=0.4), one, todo, 3) if f is not None]
    out = pd.concat(frames)
    write(out.round({"close": 4, "ret": 6}), HK_DEAD)
    log.info("hk dead prices: %d of %d codes with prices, %d rows", out["code"].nunique(), len(todo), len(out))


US_DEAD = BT / "us_dead.csv.gz"
TAKEOVER_FORMS = {"SC TO-T", "SC 14D9", "SC 14D1", "DEFM14A", "425", "S-4"}
MIN_REVENUE = 1e9  # a filer's largest yearly revenue: the size of the history's smaller top-800 names (BACKTEST.md section 30)


def ending(http: Http, cik: int) -> dict | None:
    """How a filer that stopped filing ended, from its filing list: bankrupt (an 8-K Item 1.03 in the year before its
    last periodic report or after it), taken over (a tender offer, merger proxy or merger registration then), else
    other (a deregistration, going private, a new CIK after a holding-company reorganisation, a foreign filer's
    change of form). The EDGAR list ('recent', up to 1000 filings) reaches back past the end for a company that
    stopped filing."""
    r = http.get(sec.SUBMISSIONS.format(cik=cik)).json()["filings"]["recent"]
    f = pd.DataFrame({"date": r["filingDate"], "form": r["form"], "items": r["items"]})
    periodic = f[f["form"].isin(["10-K", "10-K405", "10-KSB", "10-Q", "20-F", "40-F"])]
    if periodic.empty:
        return None
    last = periodic["date"].max()
    window = f[f["date"] >= (pd.Timestamp(last) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")]
    bankrupt = window["items"].str.split(",").map(lambda x: "1.03" in x).any()
    taken = window["form"].isin(TAKEOVER_FORMS).any()
    return {"cik": cik, "last_filed": last, "cause": "bankrupt" if bankrupt else "taken over" if taken else "other"}


def us_filers() -> None:
    """The SEC frames' large filers that are no longer listed and stopped filing (the dead filers of docs/PLAN.md stage
    27), one row each with its last figures and how it ended."""
    f = pd.read_csv(HISTORY / "us_frames.csv.gz")
    f["cik"] = f["cik"].astype(int)
    live = set(sec.load_ciks().dropna().astype(int))
    big, last = f.groupby("cik")["revenue"].max(), f.groupby("cik")["year"].max()
    todo = [c for c in big.index if big[c] >= MIN_REVENUE and c not in live and last[c] <= 2024]
    log.info("us dead filers: %d", len(todo))
    got = [g for g in each(sec.make_http, ending, todo, 4) if g]
    out = pd.DataFrame(got).merge(f.sort_values("year").groupby("cik").last().reset_index(), on="cik")
    out = out.rename(columns={"year": "last_year", "revenue": "revenue_last", "ni": "ni_last", "equity": "equity_last"})
    out["revenue_max"] = out["cik"].map(big)
    write(out, US_DEAD)
    log.info("us dead filers: %d classified: %s", len(out), out["cause"].value_counts().to_dict())


def us_rates(months: list[str]) -> pd.DataFrame:
    """The yearly rate at which large SEC filers (revenue of $1bn or more) that were public on a month end went
    bankrupt, and were taken over, in the 12 months after it (a periodic report filed in that window was the last), by
    the filer's last published year: a loss or negative equity, or neither. Pooled over `months`; the frames' last year
    is 2025, so a filer that stopped filing after 2024 is missing and later months aren't asked."""
    f = pd.read_csv(HISTORY / "us_frames.csv.gz")
    f["cik"] = f["cik"].astype(int)
    f = f[f["revenue"] >= MIN_REVENUE]
    f["loss"] = (f["ni"] < 0) | (f["equity"] < 0)
    dead = pd.read_csv(US_DEAD).set_index("cik")
    live = set(sec.load_ciks().dropna().astype(int))
    out = {}
    for m in months:
        day = pd.Period(m, "M").end_time.strftime("%Y-%m-%d")
        end = (pd.Period(m, "M") + 12).end_time.strftime("%Y-%m-%d")
        year = int(m[:4]) - (1 if m[5:] >= "04" else 2)  # the latest year published by then
        g = f[f["year"] == year].copy()
        g["last_filed"] = g["cik"].map(dead["last_filed"]).fillna("9999")
        g["cause"] = g["cik"].map(dead["cause"])
        g = g[g["last_filed"] > day]  # still filing on the month end
        for loss, h in g.groupby("loss"):
            out[(m, bool(loss))] = {"n": len(h), "bankrupt": int(((h["cause"] == "bankrupt") & (h["last_filed"] <= end)).sum()),
                                    "taken": int(((h["cause"] == "taken over") & (h["last_filed"] <= end)).sum())}
    t = pd.DataFrame(out).T.rename_axis(["month", "loss"]).groupby("loss").sum()
    t["bankrupt_rate"], t["taken_rate"] = t["bankrupt"] / t["n"], t["taken"] / t["n"]
    return t


def us_haircut(rates: pd.DataFrame, snaps: dict, picks: dict[str, pd.Series], windows: pd.DataFrame, dead_return: float) -> pd.Series:
    """Each cohort's 12-month return with the bankruptcies a survivor-only list leaves out put back: the share of the list's
    names with a loss or negative equity (the snapshot's) times the loss group's bankruptcy rate, plus the rest times the
    other's, of the money earns `dead_return` (Shumway 1997: -30% in the delisting month for a NYSE or AMEX name; Shumway
    and Warther 1999: -55% for a Nasdaq one) instead of the list's return."""
    out = {}
    for d, w in windows["ret"].items():
        s = snaps[d]["snap"].reindex(picks[d].index)
        loss = ((s["np_ttm"] < 0) | (s["bps"] < 0)).mean()
        p = loss * rates.at[True, "bankrupt_rate"] + (1 - loss) * rates.at[False, "bankrupt_rate"]
        out[d] = (1 - p) * w + p * dead_return
    return pd.Series(out)


SHUMWAY = {"NYSE or AMEX": -0.30, "Nasdaq": -0.55, "total loss": -1.0}  # a performance delisting's return in its month (1997; 1999), and the bound


def us_correction(picks: dict[str, dict[str, pd.Series]], windows: dict[str, pd.DataFrame]) -> dict:
    """The US lists' 12-month results with the bankruptcies put back (us_haircut), per list and per delisting return:
    the mean return over the fund and the share of windows ahead of it, with the survivor-only figures beside them, and
    the rates used. A bound, not a rebuild: the SEC's frames have the dead filers' figures but no prices, so a dead
    filer can't be ranked into a list."""
    from backtest import run
    snaps = run.load("us")
    months = sorted(set().union(*(w.index for w in windows.values())))
    rates = us_rates([m for m in months if m <= "2023-12"])
    out = {"rates": rates.reset_index().to_dict("records")}
    for kind, w in windows.items():
        row = {"survivors": {"excess": float((w["ret"] - w["fund"]).mean()), "beat": float((w["ret"] > w["fund"]).mean())}}
        for label, r in SHUMWAY.items():
            c = us_haircut(rates, snaps, picks[kind], w, r)
            row[label] = {"excess": float((c - w["fund"]).mean()), "beat": float((c > w["fund"]).mean())}
        out[kind] = row
    return out


# ---------------------------------------------------------------- CN delisted A-shares (Baostock)

CN_DAILY, CN_RESULTS, CN_NAMES = (BT / f"cn_dead_{x}.csv.gz" for x in ("daily", "results", "names"))
CN_FIRST_OUT = "2018-12-01"  # delisted before the first month end of the history (2019-01) can't be in it
WORKERS, PAUSE = 2, 0.3  # Baostock blocked the IP for days after 6 sessions at full speed (2026-11-23)
DAILY_FIELDS = "date,code,close,preclose,volume,amount,tradestatus,pctChg,peTTM,pbMRQ,isST"
FUNDAMENTALS = {"profit": "query_profit_data", "balance": "query_balance_data", "cash": "query_cash_flow_data"}


def _login() -> None:
    import baostock as bs
    r = bs.login()
    if r.error_code != "0":  # 10001011: the IP is blocked for calling too fast (2026-11-23: 6 sessions at once)
        raise RuntimeError(f"baostock login: {r.error_code} {r.error_msg}")


def _rows(rs) -> pd.DataFrame:
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    return pd.DataFrame(rows, columns=rs.fields)


def _query(name: str, **kw) -> pd.DataFrame:
    """One Baostock query, paced (PAUSE) and retried after logging in again when the socket drops."""
    import baostock as bs
    for attempt in range(3):
        time.sleep(PAUSE)
        try:
            return _rows(getattr(bs, name)(**kw))
        except Exception as e:
            log.warning("%s %s: %s", name, kw, e)
            time.sleep(5 * (attempt + 1))
            _login()
    raise RuntimeError(f"baostock {name} {kw}: giving up")


def _daily(code: str) -> pd.DataFrame:
    return _query("query_history_k_data_plus", code=code, fields=DAILY_FIELDS, start_date="2017-12-01",
                  end_date="2026-11-20", frequency="d", adjustflag="3")


def _baostock(code: str) -> str:
    return ("sh." if code[0] == "6" else "sz.") + code


def _collect(jobs: list[tuple], fn, part) -> list[dict]:
    """fn(job) for every job on WORKERS sessions, saved to `part` every 200 so a stopped run resumes where it was; the
    part file is removed by the caller once the table is written."""
    done = pd.read_pickle(part) if part.exists() else []
    seen = {tuple(r["job"]) for r in done}
    todo = [j for j in jobs if tuple(j) not in seen]
    log.info("baostock: %d jobs, %d done before", len(jobs), len(jobs) - len(todo))
    with Pool(WORKERS, initializer=_login) as pool:
        for i, row in enumerate(pool.imap_unordered(fn, todo, chunksize=4), 1):
            done.append(row)
            if i % 200 == 0 or i == len(todo):
                pd.to_pickle(done, part)
                log.info("baostock: %d of %d", i, len(todo))
    return done


def cn_list(since: str = "2018-12-01") -> pd.DataFrame:
    """Delisted A-shares (Baostock's stock list: status 0 is delisted, outDate the day) that left on or after `since`."""
    from backtest.panel import A_SHARE
    _login()
    lst = _query("query_stock_basic")
    lst = lst[(lst["type"] == "1") & (lst["status"] == "0") & (lst["outDate"] >= since)].copy()
    lst["code6"] = lst["code"].str[3:]
    return lst[lst["code6"].str.match(A_SHARE)]


def cn_prices() -> None:
    """Daily close, price move (the exchange's: ex-rights prices, no dividends, as the 通达信 packages), turnover,
    P/E and P/B of every delisted A-share that left from CN_FIRST_OUT, from 2017-12 to its last trading day."""
    lst = cn_list(CN_FIRST_OUT)
    log.info("cn dead A-shares: %d", len(lst))
    with Pool(WORKERS, initializer=_login) as pool:
        parts = pool.map(_daily, list(lst["code"]), chunksize=4)
    daily = pd.concat([p for p in parts if len(p)])
    daily["code"] = daily["code"].str[3:]
    for c in ("close", "preclose", "volume", "amount", "pctChg", "peTTM", "pbMRQ"):
        daily[c] = pd.to_numeric(daily[c], errors="coerce")
    write(daily.rename(columns={"peTTM": "pe", "pbMRQ": "pb", "pctChg": "chg"}), CN_DAILY)
    write(lst[["code6", "code_name", "ipoDate", "outDate"]].rename(columns={"code6": "code", "code_name": "name"}), CN_NAMES)
    log.info("cn dead A-shares: %d with prices, %d rows", daily["code"].nunique(), len(daily))


def _report(job: tuple[str, int, int, tuple[str, ...]]) -> dict:
    """One company-quarter of the named Baostock tables (publication date, YTD figures): the job and each table's row."""
    code, year, quarter, tables = job
    out = {"job": job, "code": code}
    for name in tables:
        df = _query(FUNDAMENTALS[name], code=code, year=year, quarter=quarter)
        if len(df):
            out |= df.iloc[0].to_dict()
    return out


CN_ANNUAL = HISTORY / "cn_dead_annual.csv.gz"  # read by research/fade.py (stage 25's failure share, stage 26's persistence)
ANNUAL_FROM = "2012-01-01"  # a company that left earlier has no window in the revenue tables (2009 on, 3 years behind)


def cn_annual() -> None:
    """The yearly revenue, net profit, return on equity and share count of every delisted A-share that left in 2012 or
    later, 2009 to its last annual report: the revenue paths a survivors-only table leaves out (and the share counts
    cn_results sizes the names by)."""
    lst = cn_list(ANNUAL_FROM)
    jobs = [(c, y, 4, ("profit",)) for c, out in zip(lst["code"], lst["outDate"]) for y in range(2009, min(int(out[:4]), 2025) + 1)]
    part = BT / "cn_dead_annual.part.pkl"
    t = pd.DataFrame([r for r in _collect(jobs, _report, part) if r.get("statDate")])
    num = lambda c: pd.to_numeric(t[c], errors="coerce")
    out = pd.DataFrame({"code": t["code"].str[3:], "period": t["statDate"], "notice_date": t["pubDate"], "revenue": num("MBRevenue"),
                        "np": num("netProfit"), "roe": num("roeAvg") * 100, "shares": num("totalShare")})
    write(out.dropna(subset=["revenue"]).sort_values(["code", "period"]), CN_ANNUAL)
    part.unlink()
    log.info("cn dead A-shares: %d annual rows for %d names", len(out), out["code"].nunique())


def cn_size(daily: pd.DataFrame) -> list[str]:
    """The delisted names that could have been among the 800 largest on a month end of the history: market value
    (close × the latest annual report's share count; the earliest one before it) within 80% of that month end's
    smallest member of the snapshots' 800."""
    from backtest import run
    cut = pd.Series({m[:7]: d["snap"]["mcap"].min() for m, d in run.load("cn").items()})  # keyed by month
    sh = pd.read_csv(CN_ANNUAL, dtype={"code": str}).dropna(subset=["shares", "notice_date"]).sort_values("notice_date")
    d = daily.assign(month=daily["date"].str[:7])
    d = d[d["date"] >= "2019-01-01"].sort_values("date").groupby(["code", "month"]).last().reset_index()
    d = pd.merge_asof(d.assign(t=pd.to_datetime(d["date"])).sort_values("t"),
                      sh[["code", "shares"]].assign(t=pd.to_datetime(sh["notice_date"])), on="t", by="code")
    d["shares"] = d["shares"].fillna(d["code"].map(sh.groupby("code")["shares"].first()))
    big = d["close"] * d["shares"] >= 0.8 * d["month"].map(cut)
    keep = sorted(d.loc[big, "code"].unique())
    log.info("cn dead A-shares: %d of %d can reach the 800 largest", len(keep), d["code"].nunique())
    return keep


def cn_results() -> None:
    """Quarterly results (YTD revenue, profit, margins, cash conversion, debt ratio, share count) of the delisted
    A-shares that could be among the 800 largest, 2016 to their last report, with each report's publication date."""
    daily = pd.read_csv(CN_DAILY, dtype={"code": str})
    out_date = pd.read_csv(CN_NAMES, dtype={"code": str}).set_index("code")["outDate"]
    jobs = [(_baostock(c), y, q, tuple(FUNDAMENTALS)) for c in cn_size(daily) for y in range(2016, 2026) for q in (1, 2, 3, 4)
            if f"{y}-{3 * q:02d}" <= out_date[c][:7]]
    part = BT / "cn_dead_results.part.pkl"
    out = pd.DataFrame([r for r in _collect(jobs, _report, part) if r.get("statDate")])
    out["code"] = out["code"].str[3:]
    write(out.drop(columns="job"), CN_RESULTS)
    part.unlink()
    log.info("cn dead A-shares: %d reports for %d names", len(out), out["code"].nunique())


# ---------------------------------------------------------------- the tables the history reads (backtest/panel.py)

def survivors_only() -> bool:
    """SURVIVORS_ONLY=1 builds the history as before stage 27 (to rerun a "before")."""
    return os.environ.get("SURVIVORS_ONLY") == "1"


def hk_prices_table(last_month: str) -> pd.DataFrame:
    """The HK names that stopped trading (or whose last month is before the Yahoo table's), as Yahoo's monthly rows."""
    if survivors_only() or not HK_DEAD.exists():
        return pd.DataFrame(columns=["code", "month", "close", "ret"])
    d = pd.read_csv(HK_DEAD, dtype={"code": str})
    gone = d.groupby("code")["month"].max() < last_month
    return d[d["code"].isin(gone[gone].index)]


@functools.cache
def cn_tables() -> dict[str, pd.DataFrame] | None:
    """The delisted A-shares in the shapes of data/backtest's CN tables: results (业绩报表: YTD figures by notice date),
    balance (debt ratio), and the daily rows (close, the exchange's price move, turnover, whether it traded, the share
    count of the latest report). None when the tables aren't there or SURVIVORS_ONLY=1."""
    if survivors_only() or not (CN_DAILY.exists() and CN_RESULTS.exists()):
        return None
    daily = pd.read_csv(CN_DAILY, dtype={"code": str})
    r = pd.read_csv(CN_RESULTS, dtype={"code": str})
    num = lambda c: pd.to_numeric(r[c], errors="coerce")
    shares = num("totalShare")
    margin = num("npMargin").where(num("npMargin").abs() > 0.001)  # Q1 and Q3 reports carry no 主营收入: profit over margin
    res = pd.DataFrame({"code": r["code"], "notice_date": r["pubDate"], "period": r["statDate"],
                        "revenue": num("MBRevenue").fillna(num("netProfit") / margin),
                        "np": num("netProfit"), "gross_margin": num("gpMargin") * 100, "shares": shares})
    res["eps"] = res["np"] / shares
    res["ocfps"] = num("CFOToNP") * res["np"] / shares
    res = res.dropna(subset=["period", "notice_date"]).drop_duplicates(["code", "period"])
    prior = res.assign(period=(res["period"].str[:4].astype(int) + 1).astype(str) + res["period"].str[4:]).set_index(["code", "period"])
    key = pd.MultiIndex.from_arrays([res["code"], res["period"]])
    for new, col in (("rev_yoy", "revenue"), ("np_yoy", "np")):
        before = prior[col].reindex(key).to_numpy()
        res[new] = (res[col] - before) / np.abs(before) * 100
    daily = daily.sort_values(["code", "date"])
    # the book value per share on the first trading day after the notice date: price over P/B (a negative book stays negative)
    first = daily[daily["pb"].notna() & (daily["pb"] != 0)]
    bps = []
    for c, g in res.groupby("code"):
        d = first[first["code"] == c]
        i = d["date"].searchsorted(g["notice_date"].to_numpy())
        ok = i < len(d)
        v = np.full(len(g), np.nan)
        v[ok] = d["close"].to_numpy()[i[ok]] / d["pb"].to_numpy()[i[ok]]
        bps.append(pd.Series(v, index=g.index))
    res["bps"] = pd.concat(bps)
    res["eps_deduct"], res["roe"] = np.nan, np.nan
    bal = pd.DataFrame({"code": r["code"], "notice_date": r["pubDate"], "period": r["statDate"],
                        "debt_ratio": num("liabilityToAsset") * 100}).dropna(subset=["period"]).drop_duplicates(["code", "period"])
    return {"results": res.drop(columns="shares"), "balance": bal, "daily": daily, "shares": res[["code", "notice_date", "shares"]]}


def entered(market: str, codes: pd.Series) -> int:
    """How many of the delisted names this module adds are in the history's frame (CN and HK; 0 under SURVIVORS_ONLY)."""
    if survivors_only() or market == "us":
        return 0
    if market == "cn":
        gone = set(pd.read_csv(CN_NAMES, dtype={"code": str})["code"]) if CN_NAMES.exists() and cn_tables() else set()
    else:
        gone = set(hk_prices_table(pd.read_csv(HISTORY / "hk_monthly.csv.gz", usecols=["month"])["month"].max())["code"])
    return int(codes[codes.isin(gone)].nunique())


def cn_valuations(ends: set[str], tables: dict) -> pd.DataFrame:
    """The delisted names' rows for the month ends in Eastmoney's valuation table's shape: close, the day's move, market
    value (close × the share count of the latest report published by then), shares. P/E and P/B are left out
    (Baostock's differ in their definitions; the snapshot's check against the source needs Eastmoney's)."""
    d = tables["daily"]
    d = d[d["date"].isin(ends) & d["close"].notna()].copy()
    sh = tables["shares"].dropna().sort_values("notice_date")
    d = pd.merge_asof(d.assign(t=pd.to_datetime(d["date"])).sort_values("t"),
                      sh.assign(t=pd.to_datetime(sh["notice_date"])).drop(columns="notice_date"), on="t", by="code").drop(columns="t")
    d["mcap"] = d["close"] * d["shares"]
    names = pd.read_csv(CN_NAMES, dtype={"code": str}).set_index("code")["name"]
    return d.assign(name=d["code"].map(names), board=np.nan, pe=np.nan, pb=np.nan)[
        ["code", "name", "board", "close", "chg", "mcap", "shares", "pe", "pb", "date"]].dropna(subset=["mcap"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    {"hk-prices": hk_prices, "us-filers": us_filers, "cn-prices": cn_prices, "cn-results": cn_results, "cn-annual": cn_annual}[sys.argv[1]]()
