"""Stage 1 (docs/PLAN.md): the score from published signals, the funnel and the lists, tested once against the
registered ship bar. Definitions fixed before the run (committed first):
- Signals (sign: higher is better unless noted), each a percentile within the date among the stocks that have it:
  E/P on trailing core earnings (CN 扣非 EPS; US less preferred dividends, history.us_preferred) and B/P (US book net of
  preferred); profitability (US non-financials gross profit ÷ assets; CN and HK non-financials the mean percentile of
  ROE and gross margin; financials ROE, ranked among financials); accruals, net margin × (1 − cash conversion), lower
  is better (non-financials); 12-1-month and 6-month returns; 1-year volatility (lower); a loss over 12 months (binary,
  bad); CN 2+ limit-up days in 3 months (binary, bad); share issuance, market value growth over the price's 12-month
  total return (split-proof; dividends make payers look ~2% like buybacks), lower is better.
- The sub-period test: top fifth minus bottom fifth (binary signals: without the sign minus with it) on the mean
  6-month return, positive in at least 3 of 4 sub-periods (2019-20, 2021-22, 2023, 2024-26). The score: the equal-weight
  mean of the entering signals' percentiles (missing: the middle).
- The funnel: the largest 300 (CN, US) / 200 (HK); blow-up chance under twice the market's (backtest.funnel's in-sample
  fit); core earnings positive over the last 12 months and in each of the last 3 fiscal years. Data checks are live only.
- Buys: the 10 highest scores in the funnel, at most 2 per industry. Avoid: among the 400 largest, the 10 lowest scores
  with a warning sign (blow-up chance over the cut, a loss, the 6-month trend in the bottom fifth, CN 2+ limit-ups).
- The benchmark: each market's main index fund with dividends reinvested (Yahoo adjusted closes of SPY, 2800.HK Tracker
  Fund, 510300.SS CSI 300 ETF; data/backtest/index_etf.csv.gz), over the same days as the stocks' returns: your real
  alternative, net of its fees. The backtest snapshots carry no dividend yields, so "price index + dividend yield" (the
  plan's stopgap) can't be built. A round trip of costs comes off every list.
- The harness check: the all-stock 6-month beat and blow-up rates must match Method 17's (BACKTEST.md section 18) within
  1 point (the v3-list numbers need the v3 frames, which the new plan retires).

  uv run python -m backtest.stage1 frame cn|us|hk   # one row per month-end and stock: data/backtest/s1_<market>.pkl
  uv run python -m backtest.stage1 bar cn|us|hk     # the registered test, run once
"""

import sys
import warnings

import numpy as np
import pandas as pd

from backtest import funnel, panel, run
from stockreport import history

N_BUY, CAP, DRAWS = 10, 2, 1000
BUY_N = {"us": 300, "cn": 300, "hk": 200}
COST, PERIODS, BLOW = funnel.COST, funnel.PERIODS, funnel.BLOW
SIGNALS = {"E/P": ("ep", 1), "B/P": ("bp", 1), "profitability": ("prof", 1), "accruals": ("accruals", -1),
           "12-1 momentum": ("mom_12_1", 1), "6m trend": ("mom_6", 1), "volatility": ("vol_1y", -1),
           "loss": ("loss", -1), "CN heat": ("heat", -1), "issuance": ("issuance", -1)}
BINARY = {"loss", "heat"}
SINGLE = {"plain E/P": "ep", "plain B/P": "bp", "12-1 momentum": "mom_12_1"}  # the simpler versions


# ---------------------------------------------------------------- the frame

def frame(market: str) -> pd.DataFrame:
    warnings.simplefilter("ignore")
    panel.setup_history(market)
    snaps, rows = run.load(market), []
    country = panel.today_snapshot("us")["country"] if market == "us" else None
    years = history.YEARS[market]()
    px = panel.CNPrices() if market == "cn" else None
    for m, d in snaps.items():
        s, day = d["snap"], run.day_of(market, m)
        x = s.reindex(columns=["name", "industry", "financial", "mcap", "mcap_rank", "price", "np_ttm", "revenue_ttm", "roe",
                               "gross_margin", "cash_conv", "mom_12_1", "vol_1y", "div_yield", "debt_ratio", "bps", "eps_ttm"])
        if market == "cn":
            e0 = s["eps_deduct_ttm"].fillna(s["eps_ttm"])
            x["bp"] = s["bps"] / s["price"]
        elif market == "us":
            pref = history.us_preferred(s, day)
            e0 = s["eps_ttm"] * (1 - pref["pref_div_share"].reindex(s.index).fillna(0))
            x["bp"] = s["bps"] * (1 - pref["pref_share"].reindex(s.index).fillna(0)) / s["price"]
            x["country"] = s["country"] if "country" in s else country.reindex(s.index)
            x["gpa"] = (s["gp_ttm"] / s["assets"]).where(s["assets"] > 0)
        else:
            e0 = s["eps_ttm"]
            x["bp"] = s["bps"] / s["price"]
        x["ep"] = e0 / s["price"]
        x["core_pos"] = (e0 > 0) & no_recent_loss(years, s.index, day.isoformat())
        x["loss"] = (s["np_ttm"] <= 0).astype(float)
        x["accruals"] = (s["np_ttm"] / s["revenue_ttm"] * (1 - s["cash_conv"])).where(~s["financial"].astype(bool))
        if px is not None:
            from backtest.v3 import cn_limit_ups
            x["limit_ups"] = cn_limit_ups(px, s.index, day.isoformat())
            x["heat"] = (x["limit_ups"] >= 2).astype(float)
        rows.append(x.join(d["fwd"]).assign(date=m))
    f = pd.concat(rows).rename_axis("code").reset_index()
    f = f.merge(funnel.past_6m(market, f), on=["date", "code"], how="left")
    f["issuance"] = issuance(f, market)
    f = f[f["date"] >= run.START.get(market, "")]
    f["sample"] = np.where(f["date"] <= run.IN_SAMPLE_END[: 7 if market != "cn" else 10], "in", "out")
    f["period"] = np.select([f["date"].between(*p) for p in PERIODS.values()], list(PERIODS), "")
    f.to_pickle(panel.BT / f"s1_{market}.pkl")
    print(f"{market}: {f['date'].nunique()} dates, {len(f)} rows; columns {list(f.columns)}")
    return f


def no_recent_loss(years: pd.DataFrame, codes, day: str) -> pd.Series:
    """Core earnings positive in each of the last 3 fiscal years public by `day` (fewer years count as they are)."""
    y = years[(years["avail"] <= day) & years["code"].isin(codes)].sort_values(["code", "year"])
    last3 = y.groupby("code").tail(3)
    return (last3.groupby("code")["core"].min() > 0).reindex(codes).fillna(False)


def issuance(f: pd.DataFrame, market: str) -> pd.Series:
    """Market value growth over the price's total return in the 12 months before each date, minus 1 (share growth)."""
    dates = sorted(f["date"].unique())
    back = dict(zip(dates[12:], dates[:-12]))
    mc = f.set_index(["date", "code"])["mcap"]
    prev = pd.Series([mc.get((back.get(d), c), np.nan) for d, c in zip(f["date"], f["code"])], f.index)
    ret = trailing_return(f, market, 12)
    return (f["mcap"] / prev) / (1 + ret) - 1


def trailing_return(f: pd.DataFrame, market: str, months: int) -> pd.Series:
    out = pd.Series(np.nan, f.index)
    if market == "cn":
        px = panel.CNPrices()
        for d, g in f.groupby("date"):
            cols = g["code"].map(px.col)
            t, t0 = px.at(d), px.at(d, round(months * 30.4))
            ok = cols.notna().to_numpy()
            idx = np.nan_to_num(cols.to_numpy(float), nan=0).astype(int)
            out[g.index] = np.where(ok, px.level[t, idx] / px.level[t0, idx] - 1, np.nan)
    else:
        mon = panel.Monthly(market)
        for d, g in f.groupby("date"):
            i = mon.ret.index.get_loc(d)
            if i < months - 1:
                continue
            r = (1 + mon.ret.iloc[i - months + 1: i + 1].reindex(columns=list(g["code"]))).prod(min_count=months) - 1
            out[g.index] = r.to_numpy()
    return out


# ---------------------------------------------------------------- signals, score, funnel, lists

def pct(f: pd.DataFrame, col: str, sign: int, within: pd.Series | None = None) -> pd.Series:
    keys = [f["date"]] if within is None else [f["date"], within]
    return f.groupby(keys)[col].rank(pct=True, ascending=sign > 0)


def percentiles(f: pd.DataFrame, market: str) -> pd.DataFrame:
    """Every signal as a percentile within the date, higher = better (profitability among financials apart)."""
    fin = f["financial"].astype(bool)
    p = pd.DataFrame(index=f.index)
    for name, (col, sign) in SIGNALS.items():
        if col == "prof":
            nonfin = pct(f, "gpa", 1, fin) if market == "us" else (pct(f, "roe", 1, fin) + pct(f, "gross_margin", 1, fin)) / 2
            p[name] = nonfin.where(~fin, pct(f, "roe", 1, fin))
        elif col in f:
            p[name] = pct(f, col, sign)
    return p


def subperiod_test(f: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    """Per signal and sub-period: mean 6-month return of the top fifth minus the bottom fifth (binary: without − with)."""
    rows = {}
    for name, (col, _) in SIGNALS.items():
        if name not in p or p[name].notna().sum() == 0:
            continue
        if col in BINARY:
            top, bot = f[col] == 0, f[col] == 1
        else:
            top, bot = p[name] >= 0.8, p[name] <= 0.2
        r = {}
        for per in PERIODS:
            part = (f["period"] == per) & f["ret_6m"].notna()
            r[per] = f.loc[part & top, "ret_6m"].mean() - f.loc[part & bot, "ret_6m"].mean()
        r["has data"] = p[name].notna().mean()
        rows[name] = r
    t = pd.DataFrame(rows).T
    t["positive"] = (t[list(PERIODS)] > 0).sum(axis=1)
    t["enters"] = t["positive"] >= 3
    return t


def lists(f: pd.DataFrame, key: pd.Series, mask: pd.Series, ascending: bool = False, n: int = N_BUY) -> pd.Series:
    """Per date, the n best by `key` within `mask`, at most CAP per industry."""
    out = pd.Series(False, f.index)
    for _, g in f[mask & key.notna()].groupby("date"):
        per = {}
        for i in key[g.index].sort_values(ascending=ascending).index:
            ind = f.at[i, "industry"]
            if per.get(ind, 0) < CAP:
                out[i], per[ind] = True, per.get(ind, 0) + 1
                if sum(per.values()) == n:
                    break
    return out


ETF = {"us": "SPY", "hk": "2800.HK", "cn": "510300.SS"}


def benchmark(f: pd.DataFrame, market: str, h: str = "6m") -> pd.Series:
    """The index fund's total return over the horizon from each date: CN from the month-end trading day to the last close
    on or before the same number of calendar days later (panel.HORIZONS), US and HK month end to month end."""
    e = pd.read_csv(panel.BT / "index_etf.csv.gz")
    e = e[e["symbol"] == ETF[market]].set_index("date")["adjclose"].sort_index()
    days = e.index.to_numpy()

    def level(day: str) -> float:
        i = np.searchsorted(days, day, side="right") - 1
        return e.iloc[i] if i >= 0 else np.nan

    out = {}
    for d in f["date"].unique():
        if market == "cn":
            end = (pd.Timestamp(d) + pd.Timedelta(days=panel.HORIZONS[h])).strftime("%Y-%m-%d")
            start = d
        else:
            k = {"1m": 1, "3m": 3, "6m": 6, "12m": 12}[h]
            start = pd.Period(d, "M").end_time.strftime("%Y-%m-%d")
            end = (pd.Period(d, "M") + k).end_time.strftime("%Y-%m-%d")
        out[d] = level(end) / level(start) - 1 if end <= days[-1] else np.nan
    return f["date"].map(out)


# ---------------------------------------------------------------- random lists

def random_lists(f: pd.DataFrame, mask: pd.Series, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per date, DRAWS random lists of N_BUY from `mask` (at most CAP per industry): each draw's mean excess and blow-up
    share (rows: dates, columns: draws)."""
    rng, ex_out, bl_out = np.random.default_rng(seed), {}, {}
    for d, g in f[mask & f["ex6"].notna()].groupby("date"):
        k = len(g)
        ex, bl = g["ex6"].to_numpy(float), g["blow"].to_numpy(float)
        ind = pd.factorize(g["industry"].fillna(""))[0]
        order = np.argsort(rng.random((DRAWS, k)), axis=1)
        counts, taken = np.zeros((DRAWS, ind.max() + 1), int), np.zeros(DRAWS, int)
        s_ex, s_bl, rows = np.zeros(DRAWS), np.zeros(DRAWS), np.arange(DRAWS)
        for j in range(k):
            i = order[:, j]
            ok = (counts[rows, ind[i]] < CAP) & (taken < N_BUY)
            s_ex += np.where(ok, ex[i], 0)
            s_bl += np.where(ok, bl[i], 0)
            counts[rows, ind[i]] += ok
            taken += ok
            if (taken == N_BUY).all():
                break
        ex_out[d], bl_out[d] = s_ex / np.maximum(taken, 1), s_bl / np.maximum(taken, 1)
    return pd.DataFrame(ex_out).T, pd.DataFrame(bl_out).T


# ---------------------------------------------------------------- the holding-rule portfolio (reported)

def holding_portfolio(f: pd.DataFrame, score_pct: pd.Series, field: pd.Series, market: str, n: int = N_BUY) -> dict:
    """Each month: keep the names still at or above the median score and in the funnel, fill to n from the top of the
    funnel (at most CAP per industry); equal weight; costs on what changes."""
    held, months, turn = [], [], []
    bench = benchmark(f, market, "1m")
    for d, g in f.groupby("date", sort=True):
        if g["ret_1m"].notna().sum() == 0:
            break
        idx = g.set_index("code")
        keep = [c for c in held if c in idx.index and score_pct.get(idx.at[c, "_row"], 0) >= 0.5 and field.get(idx.at[c, "_row"], False)]
        per = idx.loc[keep, "industry"].value_counts().to_dict() if keep else {}
        cand = g[field[g.index]].assign(s=score_pct[g.index]).sort_values("s", ascending=False)
        new = []
        for _, r in cand.iterrows():
            if len(keep) + len(new) >= n:
                break
            if r["code"] in keep or per.get(r["industry"], 0) >= CAP:
                continue
            new.append(r["code"])
            per[r["industry"]] = per.get(r["industry"], 0) + 1
        held = keep + new
        if not held:
            continue
        ret = idx.loc[held, "ret_1m"].fillna(0).mean() - COST[market] * len(new) / n
        months.append((d, ret, bench[idx.loc[held[0], "_row"]], idx.loc[held, "date"].size))
        turn.append(len(new) / n)
    m = pd.DataFrame(months, columns=["date", "ret", "bench", "n"]).set_index("date")
    ex = m["ret"] - m["bench"]
    curve = (1 + m["ret"]).cumprod()
    return {"months": len(m), "annual excess": ex.mean() * 12, "share of months ahead": (ex > 0).mean(),
            "max drawdown": (curve / curve.cummax() - 1).min(), "bench max drawdown": ((1 + m["bench"]).cumprod() / (1 + m["bench"]).cumprod().cummax() - 1).min(),
            "monthly turnover": np.mean(turn[1:]) if len(turn) > 1 else np.nan}


# ---------------------------------------------------------------- the registered test

def bar(market: str) -> None:
    warnings.simplefilter("ignore")
    f = pd.read_pickle(panel.BT / f"s1_{market}.pkl").reset_index(drop=True)
    f["_row"] = f.index
    f["blow"] = (f["worst_6m"] <= BLOW).astype(float).where(f["worst_6m"].notna())
    f["beat"] = (f["ret_6m"] > f["idx_6m"]).astype(float).where(f["ret_6m"].notna())
    f["bench6"] = benchmark(f, market)
    f["ex6"] = f["ret_6m"] - COST[market] - f["bench6"]
    f["debt_nf"] = f["debt_ratio"].where(~f["financial"].astype(bool))
    print(f"\n==== {market.upper()} stage 1: {f['date'].nunique()} dates ({f['date'].min()}..{f['date'].max()}), "
          f"{f.loc[f['ret_6m'].notna(), 'date'].nunique()} with 6-month returns")

    # harness check against Method 17's all-stock numbers (from v3's first valued month)
    first = {"us": "2019-02", "cn": "2019-01", "hk": "2019-06"}[market]
    chk = f[(f["date"] >= first) & f["ret_6m"].notna()]
    print("harness check, all stocks beat the index / blow-ups: " + "; ".join(
        f"{s} {chk.loc[chk['sample'] == s, 'beat'].mean():.1%} / {chk.loc[chk['sample'] == s, 'blow'].mean():.1%}" for s in ("in", "out"))
          + "  (Method 17: US 49.2/10.4 in, 46.1/7.8 out; CN 45.1/18.6, 41.7/11.3; HK 52.0/24.3, 44.1/13.3)")

    p = percentiles(f, market)
    t = subperiod_test(f, p)
    print("\n-- the sub-period test (mean 6-month return, top fifth − bottom fifth)\n" + t.round(3).to_string())
    entered = list(t.index[t["enters"]])
    score = p[entered].fillna(0.5).mean(axis=1) if entered else pd.Series(0.5, f.index)
    score_pct = score.groupby(f["date"]).rank(pct=True)
    print(f"score = equal-weight mean of: {entered}")

    known = f[f["blow"].notna()]
    b, _, base = funnel.blowup_model(known, market)  # Method 17's fit: in-sample rows with an outcome
    x = funnel.features(f, market)
    use = [c for c in b.index if c != "const"]
    chance = 1 / (1 + np.exp(-(b["const"] + x[use].to_numpy(float) @ b[use].to_numpy(float))))
    chance = pd.Series(chance, f.index)
    cut = chance > 2 * base
    field = (f["mcap_rank"] <= BUY_N[market]) & ~cut & f["core_pos"].astype(bool)
    print(f"funnel: {field.groupby(f['date']).sum().mean():.0f} stocks a date (blow-up cut {cut.mean():.1%} of rows; "
          f"in-sample market blow-up rate {base:.1%})")
    buys = lists(f, score, field)
    sixm = f["ex6"].notna()

    def per_date(sel: pd.Series) -> pd.Series:
        return f[sel & sixm].groupby("date")["ex6"].mean()

    ours = per_date(buys)
    rnd_ex, rnd_bl = random_lists(f, field)
    rnd_mean = rnd_ex.mean(axis=0)
    share_beaten = (rnd_mean < ours.mean()).mean()
    inv = f["mcap_rank"] <= BUY_N[market]
    inv_ex, inv_bl = random_lists(f, inv, seed=1)
    singles = {k: per_date(lists(f, f[c], field)) for k, c in SINGLE.items()}
    per = f.drop_duplicates("date").set_index("date")["period"]

    rows = {"score buys": ours, **{f"single: {k}": v for k, v in singles.items()}}
    tab = {}
    for name, s in rows.items():
        r = {"all": s.mean()}
        r |= {pp: s[per.reindex(s.index) == pp].mean() for pp in PERIODS}
        tab[name] = r
    rm = rnd_ex.mean(axis=1)
    tab["random lists (median of draws)"] = {"all": rnd_mean.median()} | {pp: rnd_ex[per.reindex(rnd_ex.index) == pp].mean(axis=0).median() for pp in PERIODS}
    tab["random, whole investable"] = {"all": inv_ex.mean(axis=0).median()} | {pp: inv_ex[per.reindex(inv_ex.index) == pp].mean(axis=0).median() for pp in PERIODS}
    print("\n-- mean 6-month return over the total-return index, after a round trip of costs\n" + pd.DataFrame(tab).T.round(3).to_string())

    blow_ours = f.loc[buys & sixm, "blow"].mean()
    blow_rnd, blow_inv = rnd_bl.mean(axis=0).mean(), inv_bl.mean(axis=0).mean()
    beat_ours = (f.loc[buys & sixm, "ret_6m"] - COST[market] > f.loc[buys & sixm, "bench6"]).mean()
    print(f"buys: beat the total-return index {beat_ours:.1%} of the time; 25%+ falls {blow_ours:.1%} (random lists from the funnel "
          f"{blow_rnd:.1%}, from the whole investable top {blow_inv:.1%}); the list beat {share_beaten:.1%} of {DRAWS} random lists")

    # expected-return line: realized 6-month return over the benchmark on the score percentile, per sub-period
    slopes, line = {}, {}
    ok = sixm & score_pct.notna()
    for pp in ["all"] + list(PERIODS):
        part = ok & ((f["period"] == pp) if pp != "all" else True)
        b = np.polyfit(score_pct[part], (f["ret_6m"] - f["bench6"])[part], 1)
        slopes[pp] = b[0]
        if pp == "all":
            line = {"intercept": b[1], "slope": b[0]}
    print(f"expected-return line (all stocks, 6 months): {line['intercept']:+.3f} + {line['slope']:+.3f} × score percentile; "
          f"slopes by sub-period " + ", ".join(f"{k} {v:+.3f}" for k, v in slopes.items() if k != "all"))
    tenth = np.ceil(score_pct * 10).clip(1, 10)
    dec = (f["ret_6m"] - f["bench6"])[ok].groupby(tenth[ok]).describe(percentiles=[0.25, 0.5, 0.75])[["mean", "25%", "50%", "75%", "count"]]
    print("by score tenth (10 = top)\n" + dec.round(3).to_string())

    sub_pos = sum((ours[per.reindex(ours.index) == pp].mean() > 0) for pp in PERIODS)
    sub_rnd = sum(ours[per.reindex(ours.index) == pp].mean() > rnd_ex[per.reindex(rnd_ex.index) == pp].mean(axis=0).median() for pp in PERIODS)
    best_single = max(s.mean() for s in singles.values())
    items = {"1. mean over the index > 0, positive in 3 of 4 sub-periods": (ours.mean() > 0) and sub_pos >= 3,
             "2. beats 90% of random lists, and their median in 3 of 4 sub-periods": (share_beaten >= 0.9) and sub_rnd >= 3,
             "3. at least as good as the best single signal": ours.mean() >= best_single,
             "4. 25%+ falls no more frequent than random lists'": blow_ours <= blow_rnd,
             "5. expected-return line slopes up in 3 of 4 sub-periods": sum(v > 0 for k, v in slopes.items() if k != "all") >= 3}
    print(f"\n-- ship bar ({market.upper()}): sub-periods positive {sub_pos}/4, above the random median {sub_rnd}/4, best single "
          f"signal {best_single:+.3f} vs {ours.mean():+.3f}")
    for k, v in items.items():
        print(f"   {k}: {'pass' if v else 'FAIL'}")
    print(f"   {market.upper()} passes: {all(items.values())}")

    port = holding_portfolio(f, score_pct, field, market)
    port5 = holding_portfolio(f, score_pct, field, market, n=5)
    print("\n-- the holding-rule portfolio (reported, not deciding): 10 names " + ", ".join(f"{k} {v:.3f}" for k, v in port.items())
          + "\n   5 names " + ", ".join(f"{k} {v:.3f}" for k, v in port5.items()))

    largest = f["mcap_rank"] <= 400
    warn = cut | (f["loss"] == 1) | (pct(f, "mom_6", 1) <= 0.2) | (f.get("heat", 0) == 1)
    avoid = lists(f, score, largest & warn, ascending=True)
    print(f"avoid list: beat the index {f.loc[avoid & sixm, 'beat'].mean():.1%}, 25%+ falls {f.loc[avoid & sixm, 'blow'].mean():.1%}, "
          f"mean over the total-return index {f.loc[avoid & sixm, 'ex6'].mean():+.3f} (all of the 400 largest: "
          f"{f.loc[largest & sixm, 'beat'].mean():.1%}, {f.loc[largest & sixm, 'blow'].mean():.1%}, {f.loc[largest & sixm, 'ex6'].mean():+.3f})")

    last = f["date"].max()
    show = f[(f["date"] == last)].assign(score=score_pct, buy=buys, avoid=avoid)
    print(f"\n-- lists on {last} (shown, not used)\nbuys: " + ", ".join(f"{r['code']} {str(r['name'])[:12]}" for _, r in show[show["buy"]].sort_values("score", ascending=False).iterrows())
          + "\navoid: " + ", ".join(f"{r['code']} {str(r['name'])[:12]}" for _, r in show[show["avoid"]].sort_values("score").iterrows()))
    f.assign(s1_score=score_pct, s1_buy=buys, s1_avoid=avoid, s1_field=field, s1_chance=chance).to_pickle(panel.BT / f"s1_{market}_result.pkl")


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    {"frame": frame, "bar": bar}[sys.argv[1]](sys.argv[2])
