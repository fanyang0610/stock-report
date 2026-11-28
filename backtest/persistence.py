"""Stage 14's check of the research DCF's long-run assumptions in the screening's history tables (PLAN.md "Forecast",
"Valuation and target price"). Published evidence sets the rules; this measures them in our three markets. It
prints, per market:
  1. margins: the share of a margin's gap to its own median kept h years on, margins above and below the median
     apart, the median over 5 or 8 years, with or without the current year, as measured and net of the market's drift
     (US operating margin; CN 扣非 net margin, the tables have no operating profit; HK net margin, likewise);
  2. growth: the share of a year's revenue growth above its size fifth's median kept in each of the next 5 years, for
     the past 1 year's and the past 3 years' excess;
  3. excess returns: of companies whose return on equity beat today's stable cost of equity in k of the last 5 years,
     the share that beats it h years on (Morningstar's moat: excess returns more likely than not for 10 / 20 years),
     and the share of a sustained excess kept h years on, net of the market's drift;
  4. the rates the research DCF uses (fade.margin_keep, lasting_keep, growth_shares, excess_keep);
  5. stage 26: whether a margin gap that has lasted 3 years keeps more than one that opened in the last year, 3 years
     on, by side (stage 14's gap: to the 5 years' median before, net of the drift), with a 90% interval on the
     difference (resampling companies), and the same against the 8-year median the forecast anchors on: a side
     changes when both intervals are above zero. The US also on
     SEC's frames (net margin, dead filers kept, the largest filers by revenue each year), the rates' source.
All on today's listings (survivors: a company whose margin or return collapsed and that left the market is missing,
so persistence above the median and recovery below it are overstated), except CN, whose tables hold the A-shares
delisted from 2012 since stage 27 (fade.cn_dead; their net margin stands in for 扣非). Complete fiscal years only.

  uv run python -m backtest.persistence [cn|us|hk]
"""

import sys

import numpy as np
import pandas as pd

from stockreport.research import fade

H = 5


def through_origin(x: pd.Series, y: pd.Series) -> float:
    """y's share of x across x's deciles (their medians, robust to the tails): sum(xy) / sum(x²)."""
    t = pd.DataFrame({"x": x, "y": y}).groupby(pd.qcut(x, 10, labels=False, duplicates="drop")).median()
    return float((t["x"] * t["y"]).sum() / (t["x"] ** 2).sum()) if len(t) > 2 else float("nan")


def excess_odds(t: pd.DataFrame, hurdle: float, years: int = 5, split: bool = False) -> dict:
    """Of company-years whose return beat `hurdle` in k of the last 5 years, the share beating it h years on:
    {k: {h: (share, observations)}}; `split`: the 5-of-5 group by its median excess above or below the group's median."""
    cols, rows = list(t.columns), []
    for i in range(4, len(cols) - 1):
        last = t[cols[i - 4:i + 1]]
        ok = last.notna().all(axis=1)
        d = pd.DataFrame({"k": (last[ok] > hurdle).sum(axis=1), "edge": last[ok].median(axis=1) - hurdle})
        for h in range(1, years + 1):
            if i + h < len(cols):
                d[h] = (t.loc[ok, cols[i + h]] > hurdle).where(t.loc[ok, cols[i + h]].notna())
        rows.append(d)
    d = pd.concat(rows)
    if split:
        d = d[d["k"] == 5]
        cut = d["edge"].median()
        groups = {f"under {cut:.0%}": d[d["edge"] < cut], f"over {cut:.0%}": d[d["edge"] >= cut]}
    else:
        groups = {str(k): d[d["k"] == k] for k in (5, 4, 3)} | {"0-2": d[d["k"] <= 2]}
    return {k: {h: (float(g[h].mean()), int(g[h].notna().sum())) for h in range(1, years + 1) if h in g} for k, g in groups.items()}


def margins(market: str) -> None:
    m = fade.margin_table(market)
    print(f"\n{market.upper()} margins ({fade.MARGIN_NAME[market]}), {m.shape[0]} companies, years {m.columns[0]}-{m.columns[-1]}; "
          f"gap of at least {fade.MIN_GAP:.0%}; median kept share (slope over the gap's deciles) [obs, start years]")
    for net in (False, True):
        print("  net of the market's drift" if net else "  as measured")
        for window in (5, 8):
            for current in (True, False):
                for side in ("above", "below"):
                    row = []
                    for h in range(1, H + 1):
                        d = fade.margin_gaps(m, window, current, h, side, net)
                        row.append("      -      " if len(d) < 30 else f"{(d['later'] / d['gap']).median():5.2f} "
                                   f"({through_origin(d['gap'], d['later']):4.2f}) [{len(d)},{d['start'].nunique()}]")
                    print(f"    w={window} {'with' if current else 'w/o '} now {side:<5} " + "  ".join(row))


def growth(market: str) -> None:
    print(f"\n{market.upper()} revenue growth: excess over the size fifth's median kept in year t+h (slope over deciles) [obs]")
    for past in (1, 3):
        prof = fade.growth_profile(market, past)
        print(f"  past {past}y excess: " + "  ".join(f"h{h} {b:4.2f} [{n}]" for h, (b, n) in prof.items()))


def returns(market: str) -> None:
    hurdle = fade.hurdle(market)
    t = fade.return_table(market)
    print(f"\n{market.upper()} return on equity above today's stable cost of equity {hurdle:.1%}: share above h years on "
          f"(all firm-years: {np.nanmean((t > hurdle).where(t.notna())):.0%} above)")
    for k, row in excess_odds(t, hurdle).items():
        print(f"  {k} of 5 years above: " + "  ".join(f"h{h} {p:4.2f} [{n}]" for h, (p, n) in row.items()))
    for k, row in excess_odds(t, hurdle, split=True).items():
        print(f"  5 of 5, median excess {k}: " + "  ".join(f"h{h} {p:4.2f} [{n}]" for h, (p, n) in row.items()))
    kept = {h: fade.excess_kept(t, hurdle, h) for h in range(1, H + 1)}
    print("  5 of 5, share of the excess kept, net of drift: " + "  ".join(f"h{h} {k:4.2f} [{n}]" for h, (k, n) in kept.items()))


def spread(lasting: pd.Series, new: pd.Series, n: int = 500) -> tuple[float, float]:
    """A 90% interval on the difference of the two groups' median shares, resampling companies (a company's years are
    not independent)."""
    r, a, b = np.random.default_rng(0), lasting.groupby(level=0).apply(np.array), new.groupby(level=0).apply(np.array)
    x = [np.median(np.concatenate(a.iloc[r.integers(0, len(a), len(a))].values))
         - np.median(np.concatenate(b.iloc[r.integers(0, len(b), len(b))].values)) for _ in range(n)]
    return float(np.percentile(x, 5)), float(np.percentile(x, 95))


def spell_row(m: pd.DataFrame, window: int, current: bool, side: str, among: pd.DataFrame | None = None) -> str:
    d = fade.margin_gaps(m, window, current, fade.KEPT_YEARS, side, among=among)
    a, b = fade.gap_spells(d, side)
    if len(a) < 30 or len(b) < 30:
        return f"lasting [{len(a)}] new [{len(b)}]: too few"
    x, y = a["later"] / a["gap"], b["later"] / b["gap"]
    lo, hi = spread(x, y)
    return (f"lasting {x.median():.2f} [{len(a)}, {a['start'].nunique()}y]  new {y.median():.2f} [{len(b)}]  "
            f"difference {x.median() - y.median():+.2f} ({lo:+.2f}, {hi:+.2f})")


def lasting(market: str) -> None:
    m = fade.margin_table(market)
    print(f"\n{market.upper()} lasting margin gaps: share kept {fade.KEPT_YEARS} years on (lasting: 3 years on its side; new: opened in the last)")
    tables = [("own table", m, None)] + ([("SEC frames, largest filers", *fade.frames_margins())] if market == "us" else [])
    for name, t, among in tables:
        for side in ("above", "below"):
            print(f"  {name}, {side}, 5 years before: {spell_row(t, 5, False, side, among)}")
            print(f"  {name}, {side}, 8-year median:  {spell_row(t, 8, True, side, among)}")
    keep, old = fade.lasting_keep(market), fade.margin_keep(market)
    print(f"  kept a year: above {old['above']:.3f} -> {keep['above']:.3f}, below {old['below']:.3f} -> {keep['below']:.3f} (lasting gaps; "
          f"sides that change: {', '.join(fade.LASTING_SIDES[market])})")


def used(market: str) -> None:
    mk = fade.margin_keep(market)
    print(f"\n{market.upper()} used: margin gap kept a year above {mk['above']:.3f} below {mk['below']:.3f} (5 years: "
          f"{mk['above'] ** 5:.2f} / {mk['below'] ** 5:.2f}); growth shares after one year's excess "
          f"{[round(x, 3) for x in fade.growth_shares(market, 1)]}, after three years' {[round(x, 3) for x in fade.growth_shares(market, 3)]}; "
          f"excess return kept a year {fade.excess_keep(market):.3f} (year 11: {fade.excess_keep(market) ** 11:.2f}, year 25: {fade.excess_keep(market) ** 25:.2f})")


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    for mk in sys.argv[1:] or ["cn", "us", "hk"]:
        margins(mk)
        growth(mk)
        returns(mk)
        used(mk)
        lasting(mk)
