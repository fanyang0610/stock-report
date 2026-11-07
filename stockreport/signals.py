"""The score's ingredients (PLAN.md, "The score: four families"): each component per stock, and its percentile among
its sector's stocks on the date; and the distress probability the buys screen on. Inputs are point-in-time: the
universe's latest public reports, prices and consensus, the annual reports public by the date (history.YEARS), for CN
the quarterly 扣非 profit by notice date (fetch.eastmoney.CN_DEDUCT) and the research reports by publication date
(fetch.eastmoney.CN_REPORTS)."""

from datetime import date

import numpy as np
import pandas as pd

FAMILIES = {  # family -> market -> components
    "value": {m: ["ep", "fep", "bp", "sp", "ev", "dy"] for m in ("cn", "hk", "us")},
    "quality": {m: [prof, "cash", "debt", "prof8", "gm8", "vol"] for m, prof in (("cn", "roe"), ("hk", "roe"), ("us", "gpa"))},
    "growth": {m: ["rg", "pg", "roa5"] for m in ("cn", "hk", "us")},
    "momentum": {"cn": ["sue", "rev"], "hk": ["mom", "rev"], "us": ["mom", "rev"]},
}
LOWER_IS_BETTER = {"debt", "vol"}
LONG_YEARS, LONG_MIN, PROF_CLIP = 8, 5, (-0.5, 1.5)  # the last 8 fiscal years, at least 5; a yearly ratio on a tiny base
# Campbell, Hilscher and Szilagyi (2008), Table 4, failure within 12 months (Gray and Carlisle's distress screen). For a
# ranking the constant, the index's return in EXRETAVG and the market total in RSIZE drop out; PRICE (log price capped
# at $15) is left out, a US small-stock term.
CHS = {"nimta": -20.264, "tlmta": 1.416, "exret": -7.129, "sigma": 1.411, "rsize": -0.045, "cashmta": -2.132, "mb": 0.075}
SUE_QUARTERS, SUE_MIN = 8, 6  # the change's spread over the preceding 8 quarters, at least 6 of them known
MIN_ANALYSTS = 3  # forward E/P and the revisions need at least 3 estimates (both now and 91 days ago)
REV_LAG, REV_WINDOW = 91, 180  # CN: the consensus 91 days ago; a broker's estimate stands 180 days (two reports a year)
MIN_PEERS = 10  # a sector with fewer scored stocks is ranked with the whole market (too few peers for fifths)


def quarters(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Code × quarter from year-to-date 扣非 profit (code, period, deduct): the trailing-12-month sum and the SUE, the
    quarter's profit minus the same quarter a year earlier over the standard deviation of that change in the preceding
    8 quarters (Chan, Jegadeesh and Lakonishok 1996). Amounts, not per-share figures, so bonus shares (送转) don't read
    as a fall."""
    ytd = table.pivot_table(index="code", columns="period", values="deduct", aggfunc="last")
    span = pd.period_range(ytd.columns.min(), ytd.columns.max(), freq="Q")
    ytd = ytd.reindex(columns=[p.end_time.strftime("%Y-%m-%d") for p in span])
    single = ytd - ytd.shift(1, axis=1)
    first = [c.endswith("-03-31") for c in ytd.columns]  # the fiscal year's first quarter is its year to date
    single.loc[:, first] = ytd.loc[:, first]
    change = single - single.shift(4, axis=1)
    sd = change.shift(1, axis=1).T.rolling(SUE_QUARTERS, min_periods=SUE_MIN).std().T
    return single.T.rolling(4, min_periods=4).sum().T, change / sd.where(sd > 0)


def cn_deduct(table: pd.DataFrame, day: str) -> pd.DataFrame:
    """Per stock, from the reports noticed on or before `day`: the latest quarter, its 扣非 TTM profit and SUE."""
    public = table[(table["notice_date"] <= day) & table["deduct"].notna()]
    ttm, sue = quarters(public)
    latest = public.groupby("code")["period"].max()
    rows, cols = ttm.index.get_indexer(latest.index), ttm.columns.get_indexer(latest.to_numpy())
    return pd.DataFrame({"deduct_period": latest, "deduct_ttm": ttm.to_numpy()[rows, cols],
                         "sue": sue.to_numpy()[rows, cols]}, index=latest.index)


def cn_revisions(reports: pd.DataFrame, bonus: pd.DataFrame, next_year: pd.Series, day: str) -> pd.DataFrame:
    """Per stock, next year's consensus EPS on `day` and REV_LAG days earlier from the research reports (code, publish,
    org, year, eps): each broker's latest estimate published in the REV_WINDOW days to the date, the median, with the
    brokers counted (est_n: the fewer of the two dates). Estimates published before a bonus-share ex-date (送转, code,
    ex_date, bonus per share) are divided by 1 + bonus, so they are per today's share like the newer ones."""
    rep = reports[(reports["year"] == reports["code"].map(next_year)) & (reports["publish"] <= day)].copy()
    first = (pd.Timestamp(day) - pd.Timedelta(days=REV_LAG + REV_WINDOW)).strftime("%Y-%m-%d")
    later = bonus[(bonus["bonus"] > 0) & (bonus["ex_date"] > first) & (bonus["ex_date"] <= day)]
    for code, ex, b in later[["code", "ex_date", "bonus"]].itertuples(index=False):
        rep.loc[(rep["code"] == code) & (rep["publish"] < ex), "eps"] /= 1 + b
    out = {}
    for tag, lag in (("now", 0), ("90", REV_LAG)):
        end = (pd.Timestamp(day) - pd.Timedelta(days=lag)).strftime("%Y-%m-%d")
        start = (pd.Timestamp(end) - pd.Timedelta(days=REV_WINDOW)).strftime("%Y-%m-%d")
        win = rep[(rep["publish"] > start) & (rep["publish"] <= end)].sort_values("publish")
        latest = win.drop_duplicates(["code", "org"], keep="last").groupby("code")["eps"]
        out[f"est_{tag}"], out[f"n_{tag}"] = latest.median(), latest.count()
    est = pd.DataFrame(out)
    return est.assign(est_n=est[["n_now", "n_90"]].min(axis=1).fillna(0))[["est_now", "est_90", "est_n"]]


def fy_end(e1_year: pd.Series) -> pd.Series:
    """The end of the first fiscal year without a report: e1_year is its year (CN, December year ends) or its last
    month (US, HK: '2027-08')."""
    parts = e1_year.astype(str).str.extract(r"^(\d{4})(?:-(\d{2}))?")
    first = pd.to_datetime(parts[0] + "-" + parts[1].fillna("12") + "-01", errors="coerce")
    return first + pd.offsets.MonthEnd(0)


def forward(df: pd.DataFrame, today: date) -> pd.DataFrame:
    """The consensus EPS for the next 12 months (eps_ntm), as I/B/E/S and FactSet build their 12-month forward EPS:
    this fiscal year's estimate (eps_e1) and next year's (eps_e2), each weighted by the share of the next 12 months its
    fiscal year covers; this year ending in t months (0-12) gives it t/12. Once it has ended (its report still to
    come), next year's alone, which ends within 12 months (HK's table has no third year). Next year's estimate alone
    put Micron's P/E in November 2026 on its fiscal year to August 2028, 21 months out, against 13 for a December year
    end. The analyst count is unchanged (PLAN.md, "Forward E/P"): next year's in the US and HK, which covers this year
    too; CN's consensus table counts rating institutions, not estimates per year."""
    left = ((fy_end(df["e1_year"]) - pd.Timestamp(today)).dt.days / 365.25 * 12).clip(0, 12) / 12
    this_year = (left * df["eps_e1"]).where(left > 0, 0.0)
    return df.assign(eps_ntm=(this_year + (1 - left) * df["eps_e2"]).where(left.notna()))


def long_run(years: pd.DataFrame, day: str) -> pd.DataFrame:
    """Per stock, from its last LONG_YEARS fiscal years public by `day` (history.YEARS: code, year, core, assets, roa,
    gm, avail), at least LONG_MIN of them: the average ROA (prof8; Gray and Carlisle's franchise power), gross-margin
    stability (gm8: mean ÷ standard deviation) and the 5-year growth in profit over the assets 5 years before (roa5:
    the latest year's profit minus that year's, Asness, Frazzini and Pedersen's growth in ROA). On assets, not the
    book: a book shrunk or turned negative by buybacks, payouts or pre-listing preferred shares makes a return on it
    meaningless (Eastmoney's ROE put Wynn Macau's 2020 loss at +470%), and assets are what every market's tables give
    each year."""
    y = years[(years["avail"] != "") & (years["avail"] <= day)].sort_values(["code", "year"])
    y = y.groupby("code").tail(LONG_YEARS).copy()
    y["prof"] = y["roa"].clip(*PROF_CLIP)
    g, gm = y.groupby("code"), y.groupby("code")["gm"]
    last = y.drop_duplicates("code", keep="last").set_index("code")
    before = y.set_index(["code", "year"])[["core", "assets"]].reindex(
        pd.MultiIndex.from_arrays([last.index, last["year"] - 5])).set_axis(last.index)
    return pd.DataFrame({"prof8": g["prof"].mean().where(g["prof"].count() >= LONG_MIN),
                         "gm8": (gm.mean() / gm.std().where(gm.std() > 0)).where(gm.count() >= LONG_MIN),
                         "roa5": ((last["core"] - before["core"]) / before["assets"].where(before["assets"] > 0))})


def distress(df: pd.DataFrame) -> pd.Series:
    """Campbell-Hilscher-Szilagyi's failure logit without its constant (higher = more likely to fail), non-financials:
    trailing profit as a quarter's over market value + liabilities, liabilities and cash over it, the 12-month log
    return as a monthly average, 3-month volatility, log market value and market over book (book + a tenth of the
    gap, as CHS adjust it; still not positive: the highest). Each input winsorized at its 5th and 95th percentile
    among the market's non-financials, as CHS winsorize theirs. NaN where liabilities or cash are missing: not
    screened."""
    col = lambda c: df[c] if c in df else pd.Series(np.nan, index=df.index)
    fin = df["financial"].astype(bool)
    liab = col("liabilities").fillna(col("liab_y"))
    mta, book = df["mcap"] + liab, df["bps"] * col("shares")
    adj = book + 0.1 * (df["mcap"] - book)
    x = {"nimta": df["np_ttm"] / 4 / mta, "tlmta": liab / mta, "exret": np.log1p(col("ret_12m")) / 12,
         "sigma": col("vol_3m"), "rsize": np.log(df["mcap"]), "cashmta": col("cash") / mta,
         "mb": (df["mcap"] / adj).mask(adj <= 0, np.inf)}
    bounds = lambda v: v[~fin].replace(np.inf, np.nan).quantile([0.05, 0.95])
    return sum(CHS[k] * v.clip(*bounds(v)) for k, v in x.items()).where(~fin)


def components(df: pd.DataFrame, market: str, cn: pd.DataFrame | None = None) -> pd.DataFrame:
    """Each component's raw value (NaN where it doesn't apply). E/P on 扣非 TTM in CN (reported profit where 扣非 is
    missing), and on profit to common shareholders in the US (B/P and ROE on common book, history.us_preferred); B/P only on
    a positive book; S/P, cash backing and debt not for banks, insurers and brokers. Forward E/P is the next 12 months'
    consensus EPS over the price (forward), the revisions next year's consensus now minus 91 days ago over the price,
    the same fiscal year at both dates (Chan, Jegadeesh and Lakonishok 1996), both with at least 3 estimates. EBIT/EV
    and margin stability not for financials either; growth is the latest report's against a year earlier (CN and HK
    year to date, US trailing 12 months); the long-run columns come from long_run."""
    fin = df["financial"].astype(bool)
    col = lambda c: df[c] if c in df else pd.Series(np.nan, index=df.index)
    pref = df.get("pref_share", 0.0)
    earnings = df["np_ttm"] * (1 - df.get("pref_div_share", 0.0))
    if market == "cn" and cn is not None:
        earnings = cn["deduct_ttm"].reindex(df.index).fillna(df["np_ttm"])
    ocf, npf, rev = (["ocf_ttm", "np_ttm", "revenue_ttm"] if market == "us" else ["ocf_ytd", "np_ytd", "revenue_ytd"])
    book = df["bps"] * (1 - pref)
    out = pd.DataFrame({
        "ep": earnings / df["mcap"],
        "bp": (book / df["price"]).where(book > 0),
        "sp": (df["revenue_ttm"] / df["mcap"]).where(~fin & (df["revenue_ttm"] > 0)),
        "roe": (earnings / (book * df["shares"])).where(book > 0) if market == "us" else df["roe"],
        "cash": ((df[ocf] - df[npf]) / df[rev]).where(~fin & (df[rev] > 0)),
        "debt": df["debt_ratio"].where(~fin),
        "mom": df["mom_12_1"],
        "fep": (col("eps_ntm") / df["price"]).where(col("analysts") >= MIN_ANALYSTS),
        "rev": ((col("est_now") - col("est_90")) / df["price"]).where(col("est_n") >= MIN_ANALYSTS),
        "ev": (col("ebit") / col("ev")).where(~fin & (col("ev") > 0)),
        "dy": col("div_yield"),
        "prof8": col("prof8"), "gm8": col("gm8").where(~fin), "vol": col("vol_1y"),
        "rg": col("rev_growth"), "pg": col("np_growth"), "roa5": col("roa5"),
    }, index=df.index)
    if market == "us":
        out["gpa"] = (df["gp_ttm"] / df["assets"]).where(~fin & (df["assets"] > 0))
    if market == "cn":
        out["sue"] = cn["sue"].reindex(df.index) if cn is not None else np.nan
    return out


def peers(df: pd.DataFrame) -> pd.Series:
    """Each stock's peer group: its sector, financials apart from the rest (their components differ), as MSCI's
    multi-factor indexes rank value and quality within sectors and Asness, Porter and Stevens (2000) find industry-
    relative value and momentum the better predictors. A group under MIN_PEERS stocks joins the whole market's
    financials or the rest ("" + the flag)."""
    fin = df["financial"].astype(bool).map({True: "|金融", False: ""})
    group = df["sector"].astype(str) + fin
    return group.where(group.map(group.value_counts()) >= MIN_PEERS, "全市场" + fin)


def peer_rank(x: pd.Series, group: pd.Series) -> pd.Series:
    """Percentile ranks within each peer group; a small sector's stocks ("全市场") against all stocks of their kind."""
    kind = group.str.endswith("|金融")
    return x.groupby(group).rank(pct=True).where(~group.str.startswith("全市场"), x.groupby(kind).rank(pct=True))


def percentiles(comp: pd.DataFrame, df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Each component as a percentile among its peers (1 = best). US financials have no gross profit: their
    profitability is ROE (Novy-Marx's gross profitability excludes them)."""
    used, group = sorted({c for fam in FAMILIES.values() for c in fam[market]}), peers(df)
    pct = pd.DataFrame({c: peer_rank(-comp[c] if c in LOWER_IS_BETTER else comp[c], group) for c in used},
                       index=comp.index)
    if market == "us":
        fin = df["financial"].astype(bool)
        pct.loc[fin, "gpa"] = peer_rank(comp.loc[fin, "roe"], group[fin])
    return pct
