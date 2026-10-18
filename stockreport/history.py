"""Company history for valuation v2 (docs/REVIEW.md A2.2, A2.7, A2.8), from data/history: yearly core
ROE, margins, cash flow and revenue summarised per stock, the stock's own P/B over the last 7 years,
the measured base rates of ROE regime breaks, CN pre-announcements and consensus revisions."""

import functools
from datetime import date, timedelta

import numpy as np
import pandas as pd

from stockreport.fetch import HISTORY

ROE_CLIP = (-0.5, 1.5)  # a yearly ROE on a tiny book can't dominate an average
SHARE_JUMP = np.log(1.6)  # share count change no split explains: the history before it is not comparable
LAG = timedelta(days=90)  # a report without a filing date is public this long after its period (HK, gaps)
STR = {c: str for c in ("code", "period", "fy_end", "filed", "date", "month", "notice_date", "snapshot", "e1_year",
                        "date_type", "trade_date", "item_code", "start")}


@functools.lru_cache(maxsize=32)
def _read(path, mtime: float) -> pd.DataFrame:
    return pd.read_csv(path, dtype=STR)


def read(name: str) -> pd.DataFrame:
    """A history table (cached while the file is unchanged; the backtest points HISTORY elsewhere)."""
    path = HISTORY / f"{name}.csv.gz"
    return _read(path, path.stat().st_mtime).copy()


def cn_years() -> pd.DataFrame:
    """CN fiscal years on 扣非 profit: ROE = weighted ROE × 扣非 EPS / EPS; public on the notice date."""
    a = read("cn_annual")
    a = a[a["period"].str.endswith("12-31")]
    core = (a["eps_deduct"] / a["eps"]).where(a["eps"] > 0).clip(-1, 1.5).fillna(1)
    shares = a["np"] / a["eps"].where(a["eps"].abs() > 0.005)
    return pd.DataFrame({"code": a["code"], "year": a["period"].str[:4].astype(int), "roe": a["roe"] / 100 * core,
                         "core": a["np"] * core, "ni": a["np"], "rev": a["revenue"], "ocf": a["ocfps"] * shares,
                         "gm": a["gross_margin"] / 100, "fcf": np.nan, "avail": a["notice_date"].fillna("")})


def us_annual(today: date | None = None) -> pd.DataFrame:
    """US annual reports, with the day each became public (filing date, else 90 days after the year end);
    only those public by `today` when given."""
    a = read("us_annual")
    a["year"] = a["fy_end"].str[:4].astype(int)
    a["avail"] = a["filed"].fillna((pd.to_datetime(a["fy_end"]) + LAG).dt.strftime("%Y-%m-%d"))
    if today is not None:
        a = a[a["avail"] <= today.isoformat()]
    return a.sort_values(["code", "fy_end"]).drop_duplicates(["code", "year"], keep="last").reset_index(drop=True)


def us_years() -> pd.DataFrame:
    """US fiscal years on continuing operations less preferred dividends, over book net of preferred
    equity (reporting currency; only ratios are used)."""
    a = us_annual()
    core = a["ni_cont"].fillna(a["ni"]) - (a["ni"] - a["ni_common"]).clip(lower=0).fillna(0)
    eq = a["equity"] - a["pref"].fillna(0)
    prev = eq.groupby(a["code"]).shift(1)
    roe = (core / ((eq + prev) / 2).where(prev > 0, eq)).where(eq > 0)
    return pd.DataFrame({"code": a["code"], "year": a["year"], "roe": roe, "core": core, "ni": a["ni"],
                         "rev": a["revenue"], "ocf": a["ocf"], "gm": a["gp"] / a["revenue"],
                         "fcf": a["ocf"] - a["capex"].fillna(0), "avail": a["avail"]})


def hk_results() -> pd.DataFrame:
    """HK main indicators; no filing dates, so a period is public 90 days after it ends (A4)."""
    h = read("hk_results")
    h["date_type"] = h["date_type"].str.zfill(3)
    h["avail"] = (pd.to_datetime(h["period"]) + LAG).dt.strftime("%Y-%m-%d")
    return h.sort_values(["code", "period"])


def hk_years() -> pd.DataFrame:
    """HK fiscal years (Eastmoney amounts in CNY; only ratios are used): ROE_AVG, else profit / book."""
    fy = hk_results()
    fy = fy[fy["date_type"] == "001"].assign(year=lambda d: d["period"].str[:4].astype(int))
    fy = fy.drop_duplicates(["code", "year"], keep="last")
    roe = (fy["roe"] / 100).fillna(fy["np"] / (fy["bps"] * fy["shares"]).where(fy["bps"] > 0))
    return pd.DataFrame({"code": fy["code"], "year": fy["year"], "roe": roe, "core": fy["np"], "ni": fy["np"],
                         "rev": fy["revenue"], "ocf": fy["ocf"], "gm": fy["gross_margin"] / 100, "fcf": np.nan,
                         "avail": fy["avail"]})


YEARS = {"cn": cn_years, "us": us_years, "hk": hk_years}


def cagr(new: pd.Series, old: pd.Series, n) -> pd.Series:
    return ((new / old) ** (1 / n) - 1).where((new > 0) & (old > 0))


def features(years: pd.DataFrame, codes) -> pd.DataFrame:
    """Per stock, from its last 10 fiscal years: ROE level, volatility and 5-year trend; loss and revenue
    down years; margins; 5-year cash conversion and free cash flow; revenue growth; and the regime test's
    inputs (the last 3 years against the up to 7 before)."""
    y = years[years["code"].isin(set(codes))].sort_values(["code", "year"]).groupby("code").tail(10).copy()
    y["roe"] = y["roe"].clip(*ROE_CLIP)
    y["k"] = y.groupby("code").cumcount(ascending=False)  # 0 = latest fiscal year
    y["down"] = (y.groupby("code")["rev"].pct_change() < -0.02).astype(float)
    sums = lambda d, cols: d.groupby("code")[cols].sum(min_count=1)
    g, last5, last2 = y.groupby("code"), sums(y[y["k"] < 5], ["ocf", "ni", "fcf"]), sums(y[y["k"] < 2], ["core", "rev"])
    all10 = sums(y, ["core", "rev"])
    f = pd.DataFrame({
        "n_years": g["roe"].count(), "first_year": g["year"].min(), "roe_hist": g["roe"].mean(), "roe_vol": g["roe"].std(),
        "loss_years": (y["roe"] < 0).groupby(y["code"]).sum(), "rev_down_years": g["down"].sum(),
        "margin_hist": all10["core"] / all10["rev"].where(all10["rev"] > 0),
        "margin_2y": last2["core"] / last2["rev"].where(last2["rev"] > 0), "gm_hist": g["gm"].mean(),
        "ocf_ni_5y": last5["ocf"] / last5["ni"].where(last5["ni"] > 0), "fcf_5y": last5["fcf"],
        "ocf_2y_pos": y[y["k"] < 2].groupby("code")["ocf"].min() > 0,
    })
    early = y[y["k"] >= 3]
    five = y[y["k"] < 5]
    f["roe_5y"] = five.groupby("code")["roe"].mean().where(five.groupby("code")["roe"].count() >= 3)
    m5 = sums(five, ["core", "rev"])
    f["margin_5y"] = m5["core"] / m5["rev"].where(m5["rev"] > 0)
    recent = y[y["k"] < 3]
    f["early_losses_only"] = (early["roe"] < 0).groupby(early["code"]).any() & ~(recent["roe"] < 0).groupby(recent["code"]).any()
    rev = y.dropna(subset=["rev"]).set_index(["code", "k"])["rev"]
    at = lambda k: rev.xs(k, level="k") if k in rev.index.get_level_values("k") else pd.Series(dtype=float)
    f["rev_cagr_5y"], f["rev_g3"] = cagr(at(0), at(4), 4), cagr(at(0), at(3), 3)
    oldest = y.dropna(subset=["rev"]).groupby("code").agg(rev_old=("rev", "first"), k_old=("k", "first"))
    oldest = oldest[oldest["k_old"] >= 6]  # 3+ years before the last 3
    f["rev_g_before"] = cagr(at(3).reindex(oldest.index), oldest["rev_old"], oldest["k_old"] - 3)
    trend = y[(y["k"] < 5) & y["roe"].notna()]
    trend = trend[trend.groupby("code")["roe"].transform("count") >= 4]
    x, r = -trend["k"].astype(float), trend["roe"]
    cov = lambda a, b: (a * b).groupby(trend["code"]).mean() - a.groupby(trend["code"]).mean() * b.groupby(trend["code"]).mean()
    f["roe_slope"] = cov(x, x).pipe(lambda vx: cov(x, r) / vx)
    f["roe_r2"] = (cov(x, r) ** 2 / (cov(x, x) * cov(r, r))).where(cov(r, r) > 0)
    f.loc[f["n_years"] < 4, ["roe_hist", "roe_vol", "margin_hist"]] = np.nan
    return f


def episodes(years: pd.DataFrame) -> pd.DataFrame:
    """Regime episodes in the whole panel: the first fiscal year of a run whose ROE moved 12+ points away
    from the mean of the (3 to) 5 years before (up: to 18% or more). kept = 3 years later ROE was still at least
    half the move away from that mean; cyclical = a loss or 2+ revenue down years in the 5 years before."""
    y = years.sort_values(["code", "year"]).reset_index(drop=True)
    y["roe"] = y["roe"].clip(-0.5, 1.0)
    g = y.groupby("code")
    y["prior"] = g["roe"].shift(1).groupby(y["code"]).rolling(5, min_periods=3).mean().reset_index(level=0, drop=True)
    bad = ((g["rev"].pct_change() < -0.02) | (y["roe"] < 0)).astype(float).groupby(y["code"]).shift(1)
    y["cyclical"] = bad.groupby(y["code"]).rolling(5, min_periods=3).sum().reset_index(level=0, drop=True) >= 2
    y["move"] = y["roe"] - y["prior"]
    y["dir"] = np.select([(y["move"] >= 0.12) & (y["roe"] >= 0.18), y["move"] <= -0.12], ["up", "down"], "")
    first = (y["dir"] != "") & (y["dir"] != y.groupby("code")["dir"].shift(1).fillna(""))
    later = g["roe"].shift(-3).where(g["year"].shift(-3) == y["year"] + 3)
    y["kept"] = ((later - y["prior"]) / y["move"] >= 0.5).where(later.notna())
    return y[first][["code", "year", "dir", "cyclical", "move", "kept"]]


def base_rates(eps: pd.DataFrame) -> pd.DataFrame:
    """Share of episodes that kept at least half of the move after 3 years, by direction and history."""
    done = eps[eps["kept"].notna()].assign(kept=lambda d: d["kept"].astype(float),
                                           history=lambda d: np.where(d["cyclical"], "cyclical", "steady"))
    both = done.assign(history="all")
    return pd.concat([done, both]).groupby(["dir", "history"])["kept"].agg(["mean", "count"])


def splits_after(splits: pd.DataFrame, codes: pd.Series, days: pd.Series) -> np.ndarray:
    """Product of each code's split ratios after each day (1 without splits)."""
    out, codes, days = np.ones(len(codes)), codes.to_numpy(), days.to_numpy()
    for code, s in splits[splits["code"].isin(set(codes))].groupby("code"):
        rows = np.flatnonzero(codes == code)
        for day, ratio in zip(s["date"], s["ratio"]):
            out[rows[days[rows] < day]] *= ratio
    return out


def closest(s: pd.DataFrame, day: str, want: float) -> float:
    """Among 1 and the products of the latest splits after `day`, the factor closest to `want` in logs."""
    later = s.loc[s["date"] > day].sort_values("date", ascending=False)["ratio"].to_numpy()
    options = np.concatenate([[1.0], np.cumprod(later)])
    return float(options[np.argmin(np.abs(np.log(options) - np.log(max(want, 1e-9))))])


def own_pb(books: pd.DataFrame, monthly: pd.DataFrame, splits: pd.DataFrame, today: date) -> pd.DataFrame:
    """Median P/B per stock over the last 7 years (24+ months) and over the last 3 (12+ months: the
    window after a regime break). books: code, avail (the day the book is public), book_unit (book per
    listed unit in today's units, own currency); monthly: code, month, close (as traded), fx (own
    currency per quote-currency unit)."""
    m = monthly[monthly["month"].between(f"{today.year - 7}-{today.month:02d}", f"{today:%Y-%m}")].copy()
    m["day"] = pd.to_datetime(m["month"] + "-28")
    m["close"] = m["close"] / splits_after(splits, m["code"], m["month"] + "-28")  # today's units
    books = books.assign(day=pd.to_datetime(books["avail"])).drop(columns="avail").sort_values("day")
    m = pd.merge_asof(m.sort_values("day"), books, on="day", by="code")
    m["pb"] = (m["close"] * m["fx"] / m["book_unit"]).where((m["book_unit"] > 0) & (m["close"] > 0))
    m = m.dropna(subset=["pb"])
    recent = m[m["month"] >= f"{today.year - 3}-{today.month:02d}"].groupby("code")["pb"]
    out = pd.DataFrame({"own_pb": m.groupby("code")["pb"].median(), "own_pb_n": m.groupby("code")["pb"].count(),
                        "own_pb_3y": recent.median().where(recent.count() >= 12)})
    return out[out["own_pb_n"] >= 24]


def us_books(snap: pd.DataFrame, today: date) -> tuple[pd.DataFrame, set, pd.Series]:
    """US annual reports with book (net of preferred) > 0 and the share count in today's listed units.
    SEC restates share counts after a split in some years only, so each year's count goes to today's
    units by the later splits that bring it closest to the latest count; a change no split explains (an
    ADR ratio change, a merger) cuts the history there. The latest count per listed unit (ADRs, share
    classes; snap["shares"]) maps counts to listed units. Also the cut codes and 5-year dilution."""
    a = us_annual(today)
    a["book"] = a["equity"] - a["pref"].fillna(0)
    a = a[a["code"].isin(snap.index) & (a["book"] > 0) & (a["shares"] > 0)].reset_index(drop=True)
    splits = read("us_splits")
    a["f"], a["ref"] = 1.0, a.groupby("code")["shares"].transform("last")
    for code, s in splits[splits["code"].isin(set(a["code"]))].groupby("code"):
        rows = a.index[a["code"] == code]
        last = rows[-1]
        ref = a.at[last, "shares"] * closest(s, a.at[last, "fy_end"], snap.at[code, "shares"] / a.at[last, "shares"])
        a.loc[rows, "ref"] = ref
        a.loc[rows, "f"] = [closest(s, a.at[i, "fy_end"], ref / a.at[i, "shares"]) for i in rows]
    # a book that grew 40%+ beyond its profit (a stock-paid merger) or shrank 40%+ in a profitable year
    # (a spin-off) starts a new history too: the years before it belong to a different company
    prev = a.groupby("code")["book"].shift(1)
    book_jump = (a["book"] > prev * 1.4 + a["ni"].clip(lower=0)) | ((a["book"] < 0.6 * prev) & (a["ni"] > 0))
    adj = a["shares"] * a["f"]  # today's units
    five = adj.groupby(a["code"]).shift(5).where(a.groupby("code")["year"].shift(5) >= a["year"] - 6)
    dilution = (adj / five - 1).groupby(a["code"]).last()
    jump = ((np.log(a["shares"] * a["f"] / a["ref"]).abs() > SHARE_JUMP)
            | book_jump.groupby(a["code"]).shift(-1, fill_value=False)).astype(int)
    cut = jump[::-1].groupby(a["code"][::-1]).cummax()[::-1] > 0  # the jump and every year before it
    cut_codes = set(a.loc[cut, "code"])
    a = a[~cut].copy()
    a["units"] = a["shares"] * a["f"] * a["code"].map(snap["shares"]) / a["ref"]
    return a, cut_codes, dilution


def own_pb_us(snap: pd.DataFrame, today: date) -> pd.DataFrame:
    """US: market value / book (net of preferred) at each month end, in today's listed units (us_books)."""
    a, cut_codes, dilution = us_books(snap, today)
    splits = read("us_splits")
    books = pd.DataFrame({"code": a["code"], "avail": a["avail"], "book_unit": a["book"] / a["units"]})
    currency = a.groupby("code")["currency"].last()
    monthly = read("us_monthly")
    fx = monthly[monthly["code"].str.endswith("=X")].assign(currency=lambda d: d["code"].str[:3])
    fx = fx.set_index(["currency", "month"])["close"]
    m = monthly[monthly["code"].isin(currency.index)].copy()
    cur = m["code"].map(currency)
    m["fx"] = np.where(cur == "USD", 1.0, fx.reindex(pd.MultiIndex.from_arrays([cur, m["month"]])).to_numpy())
    start = a.groupby("code")["year"].min()  # the year a comparable history starts, after a cut
    out = own_pb(books, m, splits, today).join(start[start.index.isin(cut_codes)].rename("history_from"), how="outer")
    return out.join(dilution.rename("dilution"), how="outer")  # share count change over 5 years (a flag)


def us_preferred(snap: pd.DataFrame, today: date) -> pd.DataFrame:
    """Share of book that is preferred equity and of profit that goes to preferred dividends, from each
    company's latest annual report (at most 18 months old), for book and earnings net of preferred."""
    a = us_annual(today).groupby("code").last()
    a = a[a.index.isin(snap.index) & (a["fy_end"] >= (today - timedelta(days=548)).isoformat())]
    return pd.DataFrame({"pref_share": (a["pref"] / a["equity"]).where(a["equity"] > 0).clip(0, 0.5).fillna(0),
                         "pref_div_share": ((a["ni"] - a["ni_common"]) / a["ni"]).where(a["ni"] > 0).clip(0, 0.5).fillna(0)})


def own_pb_hk(snap: pd.DataFrame, today: date) -> pd.DataFrame:
    """HK: Eastmoney's book per share (CNY, restated in today's units like its EPS) against month-end
    closes in today's units at that month's HKDCNY=X; a book is public ~90 days after its period."""
    h = hk_results()
    h = h[h["code"].isin(snap.index) & (h["bps"] > 0)]
    books = pd.DataFrame({"code": h["code"], "avail": h["avail"], "book_unit": h["bps"]})
    monthly = read("hk_monthly")
    fx = monthly[monthly["code"] == "HKDCNY=X"].set_index("month")["close"]
    m = monthly[monthly["code"].isin(snap.index)].assign(fx=lambda d: d["month"].map(fx))
    return own_pb(books, m, read("hk_splits"), today)


def own_pb_cn(snap: pd.DataFrame, today: date) -> pd.DataFrame:
    """CN: Eastmoney's P/B (MRQ) on the last trading day of each half-year (6+ in 7 years); the anchor
    is then price × median / today's Eastmoney P/B, one definition on both sides."""
    v = read("cn_valuation")
    v = v[v["code"].isin(snap.index) & (v["pb_mrq"] > 0) & (v["period"] >= f"{today.year - 7}-{today.month:02d}")
          & (v["trade_date"] <= today.isoformat())]
    recent = v[v["period"] >= f"{today.year - 3}-{today.month:02d}"].groupby("code")["pb_mrq"]
    out = pd.DataFrame({"own_pb": v.groupby("code")["pb_mrq"].median(), "own_pb_n": v.groupby("code")["pb_mrq"].count(),
                        "own_pb_3y": recent.median().where(recent.count() >= 4)})
    return out[out["own_pb_n"] >= 6]


def preannounced(snap: pd.DataFrame, today: date, max_days: int = 120) -> pd.DataFrame:
    """CN 业绩预告 for a period after the latest report (A2.8): the midpoint of the 扣非 profit range (else
    net profit) gives the trailing-12-month core EPS: year-to-date forecast + last fiscal year − the same
    period a year earlier (the notice's own comparison figure)."""
    f = read("cn_forecasts")
    f["item_code"] = f["item_code"].str.zfill(3)
    f = f[f["item_code"].isin(["004", "005"]) & (f["notice_date"] <= today.isoformat())
          & (f["notice_date"] >= (today - timedelta(days=max_days)).isoformat())]
    f = f[f["code"].isin(snap.index) & (f["period"] > f["code"].map(snap["period"]).fillna(""))]
    f = f.sort_values(["code", "period", "item_code", "notice_date"]).groupby("code").tail(1)  # newest period, 扣非 first
    mid = f[["amount_low", "amount_high"]].mean(axis=1)
    fy = cn_years().drop_duplicates(["code", "year"]).set_index(["code", "year"])
    last = fy.reindex(pd.MultiIndex.from_arrays([f["code"], f["period"].str[:4].astype(int) - 1]))
    last_fy = np.where(f["item_code"] == "005", last["core"], last["ni"])
    ttm = np.where(f["period"].str.endswith("12-31"), mid, mid + last_fy - f["prior_year"])
    out = pd.DataFrame({"pre_period": f["period"].to_numpy(), "pre_notice": f["notice_date"].to_numpy(),
                        "pre_type": f["type"].to_numpy(), "pre_ttm": ttm}, index=f["code"].to_numpy())
    out["pre_eps_ttm"] = out["pre_ttm"] / snap["shares"].reindex(out.index)
    return out.dropna(subset=["pre_eps_ttm"])


def revisions(market: str, today: date, weeks: int = 4) -> pd.Series:
    """Change of next year's consensus EPS since the newest weekly snapshot at least `weeks` old, for the
    same fiscal year (after a year roll: this year's estimate against the old next year's). Empty until
    the snapshots span that long."""
    path = HISTORY / f"{market}_consensus.csv.gz"
    if not path.exists():
        return pd.Series(dtype=float)
    s = read(f"{market}_consensus")
    s = s[s["snapshot"] <= today.isoformat()]
    old_day = s.loc[s["snapshot"] <= (today - timedelta(weeks=weeks)).isoformat(), "snapshot"].max()
    if pd.isna(old_day):
        return pd.Series(dtype=float)
    new, old = (s[s["snapshot"] == d].set_index("code") for d in (s["snapshot"].max(), old_day))
    old = old.reindex(new.index)
    rolled = new["e1_year"].str[:4] > old["e1_year"].str[:4]
    before = old["eps_e2"].where(~rolled, old["eps_e3"] if "eps_e3" in old else np.nan)
    now = new["eps_e1"].where(rolled, new["eps_e2"])
    return ((now - before) / before.abs()).where(before.abs() > 0.01).dropna()


def load(market: str, snap: pd.DataFrame, today: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """History features, own P/B, consensus revisions and (CN) pre-announcements per stock, and the
    market's measured base rates, from what was public on `today` (the backtest runs it on past days)."""
    years = YEARS[market]()
    years = years[years["avail"] <= today.isoformat()]
    out = features(years, snap.index).reindex(snap.index)
    out = out.join({"cn": own_pb_cn, "us": own_pb_us, "hk": own_pb_hk}[market](snap, today))
    if market == "cn":
        out = out.join(preannounced(snap, today))
    if market == "us":
        out = out.join(us_preferred(snap, today))
    out["revision"] = revisions(market, today)
    eps = episodes(years)
    past = eps[(eps["dir"] == "up") & eps["kept"].notna()].sort_values("year").groupby("code").last()  # own last boom
    out["past_boom_year"], out["past_boom_kept"] = past["year"], past["kept"]
    return out, base_rates(eps)
