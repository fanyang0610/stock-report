"""Checks 1-2 (PLAN Method 8): how the buy and hold names the one-off checks excluded did against the names
that took their places. v1 picks are built with both checks (production), with none, and with each one
alone (backtest.run.build); per date and bucket, the excluded = picked without the checks but not with
them, the replacements = picked with them but not without. Check 1 is split by whether 3+ analysts
expected next year's EPS at or above the last 12 months (only where consensus exists: the CN 2026
window)."""

import numpy as np
import pandas as pd

from backtest import run
from stockreport import pick, signal


def events(market: str, data: dict) -> pd.DataFrame:
    rows = []
    for m, d in data.items():
        s, fwd, picks = d["snap"], d["fwd"], d["picks"]
        checks = pick.one_off(s[s["fv_mid"].notna()])
        for variant, label in (("both", "both"), ("c1", "check 1"), ("c2", "check 2")):
            with_, without = picks[variant], picks["none"]
            for bucket in ("buy", "hold"):
                a = set(with_.loc[(with_["role"] == "pick") & (with_["bucket"] == bucket), "code"])
                b = set(without.loc[(without["role"] == "pick") & (without["bucket"] == bucket), "code"])
                for code, role in [(c, "excluded") for c in b - a] + [(c, "replacement") for c in a - b]:
                    ratio = s.at[code, "eps_e2"] / s.at[code, "eps_ttm"] if s.at[code, "eps_ttm"] > 0 else np.nan
                    rows.append({"market": market, "date": m, "check": label, "bucket": bucket, "role": role, "code": code,
                                 "c1": checks.at[code, "c1"] if code in checks.index else np.nan,
                                 "c2": checks.at[code, "c2"] if code in checks.index else np.nan,
                                 "analysts_up": (s.at[code, "analysts"] >= 3) and ratio >= 1 if pd.notna(ratio) else np.nan}
                                | fwd.loc[code].to_dict())
    out = pd.DataFrame(rows)
    if len(out):
        out["sample"] = np.where(out["date"] <= run.IN_SAMPLE_END[: 7 if market != "cn" else 10], "in", "out")
    return out


def summary(ev: pd.DataFrame, data_by_market: dict) -> pd.DataFrame:
    """Excluded vs replacement: number of names and average return against the market's equal-weight
    universe at 1, 3 and 12 months (the replacement's minus the excluded's is what the check earned)."""
    rows = []
    for (market, check), part in ev.groupby(["market", "check"]):
        univ = {m: d["fwd"].mean() for m, d in data_by_market[market].items()}
        for h in signal.HORIZONS:
            col = f"ret_{h}"
            if col not in part:
                continue
            ex = part[col] - part["date"].map(lambda m: univ[m].get(col, np.nan))
            for role in ("excluded", "replacement"):
                sel = (part["role"] == role) & ex.notna()
                rows.append({"market": market, "check": check, "h": h, "role": role, "n": int(sel.sum()),
                             "vs_universe": ex[sel].mean()})
            if check == "check 1":
                sel = (part["role"] == "excluded") & ex.notna()
                for flag, lab in ((True, "excluded, analysts ≥ trailing"), (False, "excluded, analysts below or none")):
                    s2 = sel & (part["analysts_up"].eq(True) if flag else ~part["analysts_up"].eq(True))
                    rows.append({"market": market, "check": check, "h": h, "role": lab, "n": int(s2.sum()),
                                 "vs_universe": ex[s2].mean()})
    return pd.DataFrame(rows)
