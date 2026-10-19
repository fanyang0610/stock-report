"""Base rates, the outside view (Phase 13, PLAN.md Method 16). Of the companies that looked like this one in some
year (revenue growth band, ROE band, size band, sector), the share whose profit kept up a given growth rate for
1, 2, ... 10 years, which is the share that kept both their growth and their returns. Counted year by year over
the companies still reporting (Kaplan-Meier): a company that stops reporting (taken over, delisted, bankrupt, or
the panel's end) leaves the count without counting as a success or a failure, so dead companies count for the
years they lived. US from SEC's frames (every filer, dead ones included); CN and HK from today's listed
companies' history (CN delistings were rare; HK durations get a haircut, engine-side). Profit "keeps up" g in
year k while the profit summed over years 1..k is at least the sum of (1 + g)^j × the start's, less a tolerance;
the first year it falls short ends the run."""

import numpy as np
import pandas as pd

from stockreport import history
from stockreport.config import CONFIG

H = 10  # years measured; beyond, the hazard of the last 3 measured years continues (to DMAX)
DMAX = 30
MIN_RISK = 20  # a year is measured only while this many companies are still at risk
MIN_PAIRS = 50  # a cell's ROE change in a year counts only with this many companies reporting both years
GROWTH = [-np.inf, 0.0, 0.1, 0.2, 0.35, np.inf]  # revenue growth in the start year
ROE = [-np.inf, 0.08, 0.15, 0.25, np.inf]
G_GRID = np.round(np.arange(-0.10, 0.401, 0.025), 3)  # survival is measured at these rates and interpolated
MIN_STARTS = CONFIG["v3"]["min_starts"]
TOL = CONFIG["v3"]["tolerance"]  # per market
LEVELS = [("sector", "gb", "qb", "sb"), ("sector", "gb", "qb"), ("sector", "qb"), ("gb", "qb", "sb"), ("gb", "qb"), ("gb",)]
US_MIN_REVENUE = 5e7  # US frames: filers with $50m+ revenue in the start year (shells and funds out)
# Fama-French 12 industries by SIC code (US: SEC gives every filer, dead ones too, a SIC code, not a Nasdaq sector)
FF12 = [("耐用消费品", [(2500, 2519), (2590, 2599), (3630, 3659), (3710, 3711), (3714, 3714), (3716, 3716), (3750, 3751),
                    (3792, 3792), (3900, 3939), (3990, 3999)]),
        ("能源", [(1200, 1399), (2900, 2999)]), ("化工", [(2800, 2829), (2840, 2899)]),
        ("医疗", [(2830, 2839), (3693, 3693), (3840, 3859), (8000, 8099)]),
        ("科技设备与软件", [(3570, 3579), (3660, 3692), (3694, 3699), (3810, 3829), (7370, 7379)]),
        ("电信", [(4800, 4899)]), ("公用事业", [(4900, 4949)]), ("批发零售", [(5000, 5999), (7200, 7299), (7600, 7699)]),
        ("金融", [(6000, 6999)]),
        ("非耐用消费品", [(100, 999), (2000, 2399), (2700, 2749), (2770, 2799), (3100, 3199), (3940, 3989)]),
        ("制造", [(2520, 2589), (2600, 2699), (2750, 2769), (3000, 3099), (3200, 3569), (3580, 3629), (3700, 3709),
                (3712, 3713), (3715, 3715), (3717, 3749), (3752, 3791), (3793, 3799), (3830, 3839), (3860, 3899)])]


def ff12(sic) -> str:
    try:
        code = int(float(sic))
    except (TypeError, ValueError):
        return ""
    return next((name for name, ranges in FF12 if any(lo <= code <= hi for lo, hi in ranges)), "其他")


def sectors(market: str) -> pd.Series:
    """code -> base-rate sector: CN 申万 level 1, HK the first level of Eastmoney's industry type, US the
    Fama-French 12 industry of the SEC SIC code (keyed by CIK)."""
    if market == "cn":
        from stockreport.fetch import swclass
        return swclass.level1()
    if market == "hk":
        from stockreport.fetch import eastmoney
        hk = eastmoney.load_hk_list().drop_duplicates("code").set_index("code")["industry_type"]
        return hk.fillna("").str.split("-").str[0].replace("", np.nan).dropna()
    from stockreport.fetch import frames
    sic = pd.read_csv(frames.SIC, dtype=str).set_index("code")["sic"] if frames.SIC.exists() else pd.Series(dtype=str)
    return sic.map(ff12)


def panel(market: str) -> pd.DataFrame:
    """One row per company and fiscal year: code, year, sector, rev, earn (CN 扣非, US net income, HK profit),
    roe and the day the year became public (US frames: 31 March of the next year)."""
    if market == "us":
        from stockreport.fetch import frames
        f = frames.load().sort_values(["cik", "year"])
        g = f.groupby("cik")
        prev = g["equity"].shift(1).where(g["year"].shift(1) == f["year"] - 1)
        eq = ((f["equity"] + prev) / 2).where(prev > 0, f["equity"])
        out = pd.DataFrame({"code": f["cik"].astype(str), "year": f["year"], "rev": f["revenue"], "earn": f["ni"],
                            "roe": (f["ni"] / eq).where(eq > 0), "avail": (f["year"] + 1).astype(str) + "-03-31"})
    else:
        y = history.YEARS[market]()
        out = pd.DataFrame({"code": y["code"], "year": y["year"], "rev": y["rev"], "earn": y["core"], "roe": y["roe"],
                            "avail": y["avail"]})
    return out.assign(sector=out["code"].map(sectors(market)).fillna("")).drop_duplicates(["code", "year"], keep="last")


def bands(growth, roe, size_rank) -> pd.DataFrame:
    """Growth, ROE and size band labels (size: revenue tercile of the start year, 0-2)."""
    gb = pd.cut(pd.Series(growth, dtype=float), GROWTH, labels=False, right=False)
    qb = pd.cut(pd.Series(roe, dtype=float), ROE, labels=False, right=False)
    return pd.DataFrame({"gb": gb.to_numpy(), "qb": qb.to_numpy(), "sb": np.asarray(size_rank, dtype=float)})


def starts(p: pd.DataFrame, today: str, market: str) -> pd.DataFrame:
    """Every profitable company-year public by `today` (a start; US: $50m+ revenue), with its bands, its profit
    k = 1..H years later over the start's (e1..e10) and its ROE then (q1..q10); NaN once the company stops
    reporting or the year isn't public yet. The latest year's revenue terciles are in .attrs["size_cuts"]."""
    p = p[p["avail"] <= today]
    years = list(range(int(p["year"].min()), int(p["year"].max()) + 1))
    wide = {c: p.pivot(index="code", columns="year", values=c).reindex(columns=years) for c in ("earn", "rev", "roe")}
    e, rev, roe = wide["earn"].to_numpy(float), wide["rev"].to_numpy(float), wide["roe"].to_numpy(float).clip(*history.ROE_CLIP)
    sector = p.groupby("code")["sector"].last().reindex(wide["earn"].index).to_numpy()
    rows, cuts = [], {}
    for j, year in enumerate(years[1:], start=1):
        ok = (e[:, j] > 0) & (rev[:, j] > (US_MIN_REVENUE if market == "us" else 0))
        if ok.sum() < 3:
            continue
        cuts[year] = np.quantile(rev[ok, j], [1 / 3, 2 / 3])
        ahead = lambda m, k: m[ok, j + k] if j + k < len(years) else np.full(ok.sum(), np.nan)
        cols = {f"e{k}": ahead(e, k) / e[ok, j] for k in range(1, H + 1)} | {f"q{k}": ahead(roe, k) for k in range(0, H + 1)}
        with np.errstate(divide="ignore", invalid="ignore"):
            growth = rev[ok, j] / rev[ok, j - 1] - 1
        b = bands(growth, roe[ok, j], np.searchsorted(cuts[year], rev[ok, j]))
        rows.append(pd.DataFrame(cols).assign(year=year, sector=sector[ok], **b))
    out = pd.concat(rows, ignore_index=True)
    out.attrs["size_cuts"] = cuts[max(cuts)]
    return out


ECOLS, QCOLS = [f"e{k}" for k in range(1, H + 1)], [f"q{k}" for k in range(0, H + 1)]


def roe_path(q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """How a cell's ROE moved after a start: ROE k years on ≈ A[k] + B[k] × ROE at the start (k = 1..H). The cell's
    level is chained year by year from its mean start ROE with the median change over the starts reporting both
    years k − 1 and k (the drift: an industry whose returns kept falling); B[k] is the share of a company's
    distance from the cell's mean still there after k years (slope of ROE k years on over the start's, among those
    reporting then, within [0, 1]). A year with under MIN_PAIRS companies (a short panel) adds no change and keeps
    the last slope."""
    A, B = np.zeros(H), np.ones(H)
    start = q[np.isfinite(q[:, 0]), 0]
    level, slope = start.mean(), 1.0
    for k in range(1, H + 1):
        both = np.isfinite(q[:, k]) & np.isfinite(q[:, k - 1])
        step = float(np.median(q[both, k] - q[both, k - 1])) if both.sum() >= MIN_PAIRS else 0.0
        seen = np.isfinite(q[:, k]) & np.isfinite(q[:, 0])
        if seen.sum() >= MIN_PAIRS and q[seen, 0].std() > 0:
            slope = float(np.clip(np.polyfit(q[seen, 0], q[seen, k], 1)[0], 0, 1))
        level += step
        A[k - 1], B[k - 1] = level - slope * start.mean(), slope
    return A, B


def km(values: np.ndarray, path: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Kaplan-Meier share still at or above `path` (per year 1..H, or per start × year) after 0..H years, and
    how many were at risk each year. A start is at risk in year k while it stayed on the path through k − 1 and
    still reports in year k; the first missing year ends its record."""
    seen = np.cumprod(~np.isnan(values), axis=1).astype(bool)
    kept = np.where(seen, values >= path, False)
    through = np.cumprod(np.where(seen, kept, True), axis=1).astype(bool)
    before = np.column_stack([np.ones(len(values), bool), through[:, :-1]])
    risk = (before & seen).sum(axis=0)
    ended = (before & seen & ~kept).sum(axis=0)
    return np.concatenate([[1.0], np.cumprod(1 - ended / np.maximum(risk, 1))]), risk


def track(g: float, tol: float | None = None) -> np.ndarray:
    """Cumulative profit that counts as keeping up g after k = 1..H years: the sum of (1 + g)^j × the start's
    profit over j ≤ k, less the tolerance. Cumulative, because value depends on the profit summed over the
    years: one weak year (profit is noisy) doesn't end a run whose trend holds."""
    return np.cumsum((1 + g) ** np.arange(1, H + 1)) * (1 - (TOL["cn"] if tol is None else tol))


def extend(s: np.ndarray, risk: np.ndarray) -> np.ndarray:
    """Survival to DMAX: measured while MIN_RISK companies are at risk, then the hazard of the last 3 measured
    years continues."""
    k = int(np.argmax(risk < MIN_RISK)) if (risk < MIN_RISK).any() else H  # years measured
    k = max(k, 1)
    base = s[max(k - 3, 0)]
    hazard = 1 - (s[k] / base) ** (1 / min(k, 3)) if base > 0 and s[k] > 0 else 1.0
    tail = s[k] * (1 - hazard) ** np.arange(1, DMAX - k + 1)
    return np.concatenate([s[: k + 1], tail])


def cell_of(st: pd.DataFrame, want: pd.DataFrame) -> pd.DataFrame:
    """Per stock (rows of `want`: sector, gb, qb, sb), the finest LEVELS cell with MIN_STARTS starts: its level
    number and key."""
    out = pd.DataFrame({"level": np.nan, "key": None}, index=want.index)
    for i, cols in enumerate(LEVELS):
        counts = st.groupby(list(cols)).size()
        keys = pd.MultiIndex.from_frame(want[list(cols)]) if len(cols) > 1 else pd.Index(want[cols[0]])
        n = pd.Series(counts.reindex(keys).to_numpy(), index=want.index)
        take = out["level"].isna() & (n >= MIN_STARTS)
        out.loc[take, "level"] = i
        out.loc[take, "key"] = pd.Series(list(zip(*[want[c] for c in cols])), index=want.index)[take]
    return out


def members(st: pd.DataFrame, level, key) -> np.ndarray:
    cols = list(LEVELS[int(level)])
    return np.logical_and.reduce([st[c].to_numpy() == v for c, v in zip(cols, key)])


def survival(st: pd.DataFrame, want: pd.DataFrame, g: pd.Series, tol: float) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """Per stock (rows in `want` order): the share of its cell whose profit kept up the stock's own growth rate
    g for 0..DMAX years (measured on G_GRID and interpolated); its cell's ROE path (A and B stacked, 2 × H);
    and the cell (level, key, starts)."""
    cells = cell_of(st, want)
    surv, path = np.full((len(want), DMAX + 1), np.nan), np.full((len(want), 2, H), np.nan)
    cells["starts"] = 0
    for (level, key), part in cells.dropna(subset=["level"]).groupby(["level", "key"]):
        mask = members(st, level, key)
        ratio = np.cumsum(st.loc[mask, ECOLS].to_numpy(float), axis=1)
        grid = np.array([extend(*km(ratio, track(x, tol))) for x in G_GRID])  # (rates, years)
        rows = want.index.get_indexer(part.index)
        x = np.clip(g.loc[part.index].to_numpy(float), G_GRID[0], G_GRID[-1])
        pos = np.interp(x, G_GRID, np.arange(len(G_GRID)))
        lo, frac = np.floor(pos).astype(int), (pos % 1)[:, None]
        surv[rows] = grid[lo] * (1 - frac) + grid[np.minimum(lo + 1, len(G_GRID) - 1)] * frac
        path[rows] = np.stack(roe_path(st.loc[mask, QCOLS].to_numpy(float)))
        cells.loc[part.index, "starts"] = int(mask.sum())
    return surv, path, cells


def roe_reached(st: pd.DataFrame, cells: pd.DataFrame, level: pd.Series, now: pd.Series) -> pd.Series:
    """Per stock with a `level`: the share of its cell whose average ROE in years 3-5 after a start was at or
    below that level when it lies under the stock's ROE `now` (a fall), at or above it otherwise (a rise);
    companies reporting at least two of those years."""
    out = pd.Series(np.nan, level.index)
    todo = cells.loc[level.dropna().index].dropna(subset=["level"])
    for (lv, key), part in todo.groupby(["level", "key"]):
        q = st.loc[members(st, lv, key), ["q0", "q3", "q4", "q5"]].to_numpy(float)
        late = np.where(np.isfinite(q[:, 1:]).sum(axis=1) >= 2, np.nanmean(q[:, 1:], axis=1), np.nan)
        late = late[np.isfinite(late)]
        for code in part.index:
            fall = level[code] < now[code]
            out[code] = np.mean(late <= level[code]) if fall else np.mean(late >= level[code])
    return out


def describe(level, key, market: str) -> str:
    """The cell in words, e.g. 申万一级 银行 · 营收增速 0-10% · ROE 8-15% · 大."""
    if pd.isna(level):
        return ""
    names = {"gb": lambda b: f"营收增速 {band(GROWTH, b)}", "qb": lambda b: f"ROE {band(ROE, b)}",
             "sb": lambda b: ["小", "中", "大"][int(b)] + "规模", "sector": lambda s: s}
    return " · ".join(names[c](v) for c, v in zip(LEVELS[int(level)], key))


def band(edges: list, b) -> str:
    lo, hi = edges[int(b)], edges[int(b) + 1]
    return f"<{hi:.0%}" if lo == -np.inf else f"≥{lo:.0%}" if hi == np.inf else f"{lo:.0%}-{hi:.0%}"
