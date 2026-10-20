"""Business trend (Phase 13, PLAN.md Method 16 "Trend first"): per stock, from what was public that day, votes of
+1 / −1 outside a dead band (config [trend]): revenue and core-profit growth acceleration (the latest fiscal
year's growth over the mean of the two before; profit growth as the change over the mean absolute level), the
ROE trend (latest over the mean of 2 and 3 years before), 12-1 month momentum over the market's median, and the
4-week consensus revision (live only). The business band (the first three) can split base-rate cells; the class
(the votes config `evidence` counts per market) drives the shadow lists' trend × valuation map."""

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


def band(rev: np.ndarray, earn: np.ndarray, roe: np.ndarray) -> np.ndarray:
    """Business band per row: 2 improving (business votes sum ≥ 2), 0 deteriorating (≤ −2), else 1."""
    acc = accelerations(rev, earn, roe)
    s = sum(vote(acc[k], DEAD[k]) for k in BUSINESS)
    return np.select([s >= 2, s <= -2], [2, 0], 1)


def evidence(years: pd.DataFrame, codes, today: str) -> pd.DataFrame:
    """Per stock (history.YEARS rows public by `today`): the three business accelerations from its latest four
    consecutive fiscal years (none when the latest is over two years old) and its business band."""
    y = years[(years["avail"] <= today) & years["code"].isin(set(codes))].drop_duplicates(["code", "year"], keep="last")
    last = y.groupby("code")["year"].transform("max")
    y = y[(y["year"] > last - 4) & (last >= int(today[:4]) - 2)].assign(k=last - y["year"])
    wide = {c: y.pivot(index="code", columns="k", values=c).reindex(columns=range(4)) for c in ("rev", "core", "roe")}
    acc = accelerations(*(wide[c].to_numpy(float) for c in ("rev", "core", "roe")))
    out = pd.DataFrame(acc, index=wide["rev"].index).add_prefix("acc_")
    out["tb"] = band(*(wide[c].to_numpy(float) for c in ("rev", "core", "roe")))
    return out.reindex(pd.Index(codes))


def classify(ev: pd.DataFrame, momentum: pd.Series, revision: pd.Series, market: str) -> pd.DataFrame:
    """Votes, the class (1 改善 / 0 稳定 / −1 恶化 from the votes config `evidence` counts) and its reason."""
    x = pd.DataFrame({k: ev.get(f"acc_{k}", pd.Series(np.nan, ev.index)) for k in BUSINESS}, index=ev.index)
    x["momentum"] = momentum.reindex(ev.index) - momentum.median()
    x["revision"] = revision.reindex(ev.index) if revision is not None else np.nan
    votes = pd.DataFrame({k: vote(x[k], DEAD[k]) for k in x}, index=ev.index)
    use, need = EVIDENCE[market], NEED[market]
    score = votes[use].sum(axis=1)
    cls = np.select([score >= need, score <= -need], [1, -1], 0)
    why = [describe(x.loc[c, use], votes.loc[c, use]) for c in ev.index]
    return votes.add_prefix("vote_").assign(trend=cls, trend_score=score, trend_why=why)


def describe(x: pd.Series, v: pd.Series) -> str:
    """The votes cast, e.g. 营收增速 +12pt、ROE −3pt、12-1 月动量 +25%."""
    return "、".join(f"{TEXT[k][0]} {float(np.clip(x[k], -9.99, 9.99)) * 100:+.0f}{TEXT[k][1]}" for k in v.index[v != 0])
