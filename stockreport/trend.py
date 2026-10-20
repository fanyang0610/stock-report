"""Business trend (Phase 13, PLAN.md Method 16 "Trend first"): per stock, point-in-time votes of +1 / −1 outside
a dead band (config [trend]): revenue and core-profit growth acceleration, the ROE trend, 12-1 month momentum over
the market's median and the 4-week consensus revision (live only). The class (the votes config `evidence` counts
per market) drives the trend × valuation map and the outlier verdicts; CN adds speculative heat (limit-up days)."""

import numpy as np
import pandas as pd

from stockreport.config import CONFIG

CFG = CONFIG["trend"]
DEAD = CFG["dead"]
EVIDENCE = CFG["evidence"]  # per market: the votes the class counts
NEED = CFG["need"]  # per market: improving at a vote sum ≥ need, deteriorating at ≤ −need
BUSINESS = ("rev", "profit", "roe")
TEXT = {"rev": ("营收增速", "pt"), "profit": ("利润增速", "pt"), "roe": ("ROE", "pt"), "momentum": ("12-1 月动量", "%"),
        "revision": ("预期修正", "%")}
LABELS = {1: "改善", 0: "稳定", -1: "恶化"}


def accelerations(rev: np.ndarray, earn: np.ndarray, roe: np.ndarray) -> dict[str, np.ndarray]:
    """Revenue and profit growth acceleration and the ROE trend, from yearly columns latest first (k = 0..3)."""
    with np.errstate(all="ignore"):
        g = np.where((rev[:, :3] > 0) & (rev[:, 1:4] > 0), rev[:, :3] / rev[:, 1:4] - 1, np.nan)
        scale = (np.abs(earn[:, :3]) + np.abs(earn[:, 1:4])) / 2
        p = np.where(scale > 0, (earn[:, :3] - earn[:, 1:4]) / scale, np.nan)
        q = np.clip(roe, -0.5, 1.5)
        mean = lambda a: np.nansum(a, axis=1) / np.where(np.isfinite(a).any(axis=1), np.isfinite(a).sum(axis=1), np.nan)
        return {"rev": g[:, 0] - mean(g[:, 1:]), "profit": p[:, 0] - mean(p[:, 1:]), "roe": q[:, 0] - mean(q[:, 2:4])}


def vote(x, dead: float) -> np.ndarray:
    return np.select([np.asarray(x, float) > dead, np.asarray(x, float) < -dead], [1, -1], 0)


def evidence(years: pd.DataFrame, codes, today: str) -> pd.DataFrame:
    """Per stock (history.YEARS rows public by `today`): the three business accelerations from its latest four
    consecutive fiscal years (none when the latest is over two years old)."""
    y = years[(years["avail"] <= today) & years["code"].isin(set(codes))].drop_duplicates(["code", "year"], keep="last")
    last = y.groupby("code")["year"].transform("max")
    y = y[(y["year"] > last - 4) & (last >= int(today[:4]) - 2)].assign(k=last - y["year"])
    wide = {c: y.pivot(index="code", columns="k", values=c).reindex(columns=range(4)) for c in ("rev", "core", "roe")}
    acc = accelerations(*(wide[c].to_numpy(float) for c in ("rev", "core", "roe")))
    return pd.DataFrame(acc, index=wide["rev"].index).add_prefix("acc_").reindex(pd.Index(codes))


def classify(ev: pd.DataFrame, momentum: pd.Series, revision: pd.Series, market: str) -> pd.DataFrame:
    """Votes, the class (1 改善 / 0 稳定 / −1 恶化 from the votes config `evidence` counts) and its reason."""
    x = pd.DataFrame({k: ev.get(f"acc_{k}", pd.Series(np.nan, ev.index)) for k in BUSINESS}, index=ev.index).assign(
        momentum=momentum.reindex(ev.index) - momentum.median(), revision=np.nan if revision is None else revision.reindex(ev.index))
    votes, use, need = pd.DataFrame({k: vote(x[k], DEAD[k]) for k in x}, index=ev.index), EVIDENCE[market], NEED[market]
    score = votes[use].sum(axis=1)
    return votes.add_prefix("vote_").assign(trend=np.select([score >= need, score <= -need], [1, -1], 0), trend_score=score,
                                            trend_why=[describe(x.loc[c, use], votes.loc[c, use]) for c in ev.index])


def limit_ups(daily: pd.DataFrame, codes, day: str, days: int = 63) -> pd.Series:
    """CN speculative heat: limit-up days (close over the previous close ≥ 9.5%, 19.5% on ChiNext / STAR) in the
    last `days` trading days to `day`, from the daily price table (date, code, close, prev_close)."""
    d = daily[(daily["date"] <= day) & daily["code"].isin(set(codes))]
    d = d[d["date"] >= np.sort(d["date"].unique())[-days:][0]] if len(d) else d
    limit = np.where(d["code"].str[:3].isin(["300", "301", "688", "689"]), 0.195, 0.095)
    return (d["close"] / d["prev_close"] - 1 >= limit).groupby(d["code"]).sum().reindex(pd.Index(codes)).fillna(0)


def describe(x: pd.Series, v: pd.Series) -> str:
    """The votes cast, e.g. 营收增速 +12pt、ROE −3pt、12-1 月动量 +25%."""
    return "、".join(f"{TEXT[k][0]} {float(np.clip(x[k], -9.99, 9.99)) * 100:+.0f}{TEXT[k][1]}" for k in v.index[v != 0])
