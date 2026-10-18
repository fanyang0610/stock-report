"""Run the panel studies for one market and save their tables (data/backtest/studies_<market>.pkl).

  uv run python -m backtest.panels_run cn
"""

import pickle
import sys
import warnings

from backtest import panel, studies

FIRST = {"cn": 2013, "us": 2019, "hk": 2019}  # the first fiscal year with 5 years of history before it

if __name__ == "__main__":
    warnings.simplefilter("ignore")
    market = sys.argv[1]
    panel.setup_history(market)
    y = studies.years(market)
    e = studies.episode_table(y)
    up = e[e["dir"] == "up"]
    out = {"episodes": e, "groupings": studies.grouping_test(up), "groupings_down": studies.grouping_test(e[e["dir"] == "down"]),
           "evidence": studies.evidence_test(up), "current_p": studies.current_p(up),
           "evidence_each": studies.evidence_one_by_one(up),
           "break_persistence": studies.episode_persistence(y, e)}
    p = studies.asof_panel(y, FIRST[market], 2024)
    out["asof"] = p
    out["errors"] = {"in": studies.forecast_errors(p[p["year"] <= 2020]), "out": studies.forecast_errors(p[p["year"].between(2021, 2022)])}
    out["persistence"] = studies.persistence(p)
    out["persistence_by"] = {k: studies.persistence(g) for k, g in p.groupby(
        [p["phi"].round(1).clip(0.2, 0.7)])}
    out["normal_grid"] = studies.normal_grid(y, FIRST[market], 2020, 2022)
    with open(panel.BT / f"studies_{market}.pkl", "wb") as f:
        pickle.dump(out, f)
    print("done", market)
