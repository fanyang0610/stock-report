"""Tables for docs/BACKTEST.md from the saved backtest results (data/backtest): v1 vs v2, the switch rule,
the calibration grids, β and hit rates by band, the review tests, checks 1-2, the regime and panel
studies, the news test and the 2026 consensus window. Writes data/backtest/results.md.

  uv run python -m backtest.report
"""

import pickle

import numpy as np
import pandas as pd

from backtest import calibrate, checks, news, panel, run
from stockreport import signal

MARKETS = calibrate.MARKETS
BT = panel.BT


def pct(x, d=1) -> str:
    return "" if pd.isna(x) else f"{x * 100:+.{d}f}%"


def num(x, d=3) -> str:
    return "" if pd.isna(x) else f"{x:+.{d}f}"


def md(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join([df.index.name or ""] + cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for i, row in df.iterrows():
        lines.append("| " + " | ".join([str(i)] + [str(v) for v in row]) + " |")
    return "\n".join(lines)


def frames(label: str) -> dict[str, pd.DataFrame]:
    return {m: pd.read_pickle(BT / "compare" / f"{m}_{label}.pkl") for m in MARKETS}


def method_table(f: pd.DataFrame, sample: str) -> pd.DataFrame:
    """v1 and v2 side by side for one market and sample."""
    part = f[f["sample"] == sample]
    rows = {}
    for who, up, bucket in (("v1", "upside", "v1_bucket"), ("v2", "v2_upside", "v2_bucket")):
        r = {}
        for h in ("1m", "3m", "12m"):
            s = signal.summarize(signal.rank_ic(part, up, f"ret_{h}"), signal.HORIZONS[h])
            r[f"IC {h}"] = f"{s['mean']:+.3f} ({s['t']:+.1f})"
        for h in ("3m", "12m"):
            t = signal.bucket_table(part, bucket, h)
            for b in ("buy", "hold", "sell"):
                r[f"{b} {h}"] = pct(t.at[b, "vs_universe"]) if b in t.index else ""
            r[f"buy−sell {h}"] = (f"{pct(t.at['buy-sell', 'vs_universe'])} ({t.at['buy-sell', 't']:+.1f})"
                                  if "buy-sell" in t.index else "")
        if who == "v2":  # the expected return over the required return, the engine's other answer
            s = signal.summarize(signal.rank_ic(part.assign(exret=part["v2_icc_final"] - part["v2_r_req"]), "exret", "ret_12m"), 12)
            r["IC 12m, exp. return − r"] = f"{s['mean']:+.3f} ({s['t']:+.1f})"
        tb = signal.bucket_table(part, bucket, "12m")
        r["buy hit 12m"] = f"{tb.at['buy', 'hit']:.0%}" if "buy" in tb.index else ""
        r["buy vs index 12m"] = pct(tb.at["buy", "vs_index"]) if "buy" in tb.index else ""
        rows[who] = r
    return pd.DataFrame(rows).T.rename_axis(f"{sample}-sample")


def switch_rule(cal: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, str]:
    """A4: v2 replaces v1 only if, out of sample, its buy − sell spread and its rank correlation beat
    v1's in at least two of three markets, and its 高 picks beat the market more often than its 低 picks."""
    rows, wins = {}, 0
    for m, f in cal.items():
        part = f[f["sample"] == "out"]
        ic1 = signal.summarize(signal.rank_ic(part, "upside", "ret_12m"), 12)["mean"]
        ic2 = signal.summarize(signal.rank_ic(part, "v2_upside", "ret_12m"), 12)["mean"]
        s1 = signal.bucket_table(part, "v1_bucket", "12m").at["buy-sell", "vs_universe"]
        s2 = signal.bucket_table(part, "v2_bucket", "12m").at["buy-sell", "vs_universe"]
        ok = ic2 > ic1 and s2 > s1
        wins += ok
        rows[m.upper()] = {"IC 12m v1": num(ic1), "IC 12m v2": num(ic2), "buy−sell 12m v1": pct(s1),
                           "buy−sell 12m v2": pct(s2), "v2 beats v1 on both": "yes" if ok else "no"}
    hits = confidence_hits(cal, "out")
    hi, lo = hits.get("高", np.nan), hits.get("低", np.nan)
    verdict = (f"v2 beats v1 on both measures in {wins} of 3 markets (needs 2); its 高 picks beat the market "
               f"{hi:.0%} of the time, its 低 picks {lo:.0%} (needs 高 > 低). "
               + ("The rule says switch." if wins >= 2 and hi > lo else "The rule says don't switch."))
    return pd.DataFrame(rows).T.rename_axis("market (out of sample)"), verdict


def confidence_hits(cal: dict[str, pd.DataFrame], sample: str) -> pd.Series:
    """Share of v2 buy and sell picks that beat the universe over 12 months (a sell: did worse), by band."""
    parts = []
    for f in cal.values():
        p = f[(f["sample"] == sample) & f["v2_bucket"].isin(["buy", "sell"])].dropna(subset=["ex_12m"])
        parts.append(pd.DataFrame({"band": p["v2_confidence"], "hit": np.where(p["v2_bucket"] == "buy", p["ex_12m"] > 0,
                                                                                p["ex_12m"] < 0)}))
    d = pd.concat(parts)
    return d.groupby("band")["hit"].mean()


def band_table(cal: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Confidence → hit rate (every valued stock: did the sign of the upside match its 12-month return
    over the universe?) and β by band, out of sample, per market."""
    rows = []
    for m, f in cal.items():
        for sample in ("in", "out"):
            p = f[(f["sample"] == sample)].dropna(subset=["ex_12m", "v2_upside"])
            p = p[p["v2_confidence"].isin(["高", "中", "低"])]
            for band, g in p.groupby("v2_confidence"):
                b = signal.beta(g, "v2_gap", "12m")
                rows.append({"market": m.upper(), "sample": sample, "band": band, "stocks": len(g),
                             "sign right": f"{(np.sign(g['v2_upside']) == np.sign(g['ex_12m'])).mean():.0%}",
                             "β": num(b["beta"].iloc[0], 2) if len(b) else ""})
    return pd.DataFrame(rows).set_index(["market", "sample", "band"])


def beta_table(cal: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for m, f in cal.items():
        for sample in ("in", "out"):
            p = f[f["sample"] == sample]
            for arch, g in p.groupby("v2_archetype"):
                b = signal.beta(g, "v2_gap", "12m")
                if len(b):
                    rows.append({"market": m.upper(), "sample": sample, "archetype": arch, "n": int(b["n"].iloc[0]),
                                 "β 12m": num(b["beta"].iloc[0], 2)})
    return pd.DataFrame(rows).pivot_table(index=["market", "archetype"], columns="sample", values="β 12m", aggfunc="first")


def grid_table() -> pd.DataFrame:
    g = pd.concat([pd.read_csv(BT / f"grid_{m}.csv") for m in MARKETS])
    keys = ["in ic 12m", "out ic 12m", "in buy-sell 12m", "out buy-sell 12m", "in buy 12m", "out buy 12m"]
    avg = g.groupby(["param", "value"], sort=False)[keys].mean()
    per = g.pivot_table(index=["param", "value"], columns="market", values=["in ic 12m", "out ic 12m"], sort=False)
    per.columns = [f"{a.split()[0]} IC {b.upper()}" for a, b in per.columns]
    out = avg.join(per)
    for c in out.columns:
        out[c] = out[c].map(lambda x: num(x) if "ic" in c.lower() else pct(x))
    return out


def checks_table() -> pd.DataFrame:
    ev, data = [], {}
    for m in MARKETS:
        data[m] = run.load(m)
        ev.append(checks.events(m, data[m]))
    s = checks.summary(pd.concat(ev), data)
    s["cell"] = s.apply(lambda r: f"{pct(r['vs_universe'])} ({r['n']})", axis=1)
    return s.pivot_table(index=["market", "check", "role"], columns="h", values="cell", aggfunc="first")[["1m", "3m", "12m"]]


def window_tables(cal: dict[str, pd.DataFrame]) -> list[str]:
    """CN 2026-01..09 with point-in-time consensus: v1 (forward lens, check 2) and v2 (consensus years 1-3)
    rank correlations at 1 and 3 months, and the revision signal (FY2027 consensus change over the month)."""
    f = cal["cn"]
    w = f[f["date"] >= "2026-01-01"]
    rows = {}
    for who, up in (("v1 upside", "upside"), ("v2 upside", "v2_upside")):
        rows[who] = {h: "{mean:+.3f} (t {t:+.1f}, {n} dates)".format(**signal.summarize(signal.rank_ic(w, up, f"ret_{h}"), signal.HORIZONS[h]))
                     for h in ("1m", "3m")}
    rep = pd.read_csv(BT / "cn_reports.csv.gz", dtype={"code": str})
    revs = []
    for m in sorted(w["date"].unique()):
        def cons(day):
            win = rep[(rep["publish"] <= day) & (rep["publish"] > (pd.Timestamp(day) - pd.Timedelta(days=120)).strftime("%Y-%m-%d"))]
            win = win.sort_values("publish").drop_duplicates(["code", "org"], keep="last")
            g = win.groupby("code")["eps_2027"]
            return g.median().where(g.count() >= 3)
        prev = (pd.Timestamp(m) - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
        now, before = cons(m), cons(prev)
        r = ((now - before) / before.abs()).where(before.abs() > 0.01).dropna()
        part = w[w["date"] == m].set_index("code")
        revs.append(part.join(r.rename("revision"), how="inner").reset_index().assign(date=m))
    rv = pd.concat(revs)
    rows["FY2027 consensus revision (1 month)"] = {
        h: "{mean:+.3f} (t {t:+.1f}, {n} dates)".format(**signal.summarize(signal.rank_ic(rv.assign(date=rv["date"]), "revision", f"ret_{h}"), signal.HORIZONS[h]))
        for h in ("1m", "3m")}
    out = [md(pd.DataFrame(rows).T.rename_axis("rank IC, CN 2026 window")),
           f"\nStocks with a revision: {rv.groupby('date').size().median():.0f} per month (3+ brokers in both months)."]
    return out


def main() -> None:
    cal, default = frames("calibrated"), frames("default")
    parts = ["# Backtest results (generated by backtest/report.py)\n"]
    for m in MARKETS:
        for sample in ("out", "in"):
            parts.append(f"\n## {m.upper()} {sample}-of-sample: v1 vs v2 (calibrated)\n")
            parts.append(md(method_table(cal[m], sample)))
            parts.append(f"\nv2 with today's defaults, {m.upper()} {sample}-of-sample:\n")
            parts.append(md(method_table(default[m], sample).loc[["v2"]]))
    t, verdict = switch_rule(cal)
    parts += ["\n## Switch rule\n", md(t), "\n" + verdict]
    parts += ["\n## Grids (average of the three markets; per-market IC)\n", md(grid_table())]
    parts += ["\n## Confidence bands\n", md(band_table(cal))]
    parts += ["\n## β by archetype (12 months)\n", md(beta_table(cal))]
    parts += ["\n## Checks 1-2\n", md(checks_table())]
    parts += ["\n## CN 2026 consensus window\n"] + window_tables(cal)
    ne = BT / "news_events.csv.gz"
    if ne.exists():
        parts += ["\n## News test\n", md(news.summary(pd.read_csv(ne, dtype={"code": str})).round(4).set_index("sample"))]
    for m in MARKETS:
        p = BT / f"studies_{m}.pkl"
        if p.exists():
            s = pickle.load(open(p, "rb"))
            parts += [f"\n## Regime base rates {m.upper()} (up-breaks)\n", md(s["groupings"].round(3)),
                      "\n", md(s["evidence"][0].round(3)), "\n", md(s["evidence"][1].round(2)), "\n", md(s["evidence"][2].round(2)),
                      "\n", md(s["current_p"][0].round(3)), "\n", md(s["current_p"][1].round(2)),
                      f"\n## Persistence {m.upper()}\n", md(s["persistence"].round(3).T),
                      "\n", md(s["break_persistence"].round(2)),
                      "\n", md(pd.DataFrame(s["errors"]).round(4))]
    (BT / "results.md").write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {BT / 'results.md'}")


if __name__ == "__main__":
    import warnings
    warnings.simplefilter("ignore")
    panel.setup_history("us")
    main()
