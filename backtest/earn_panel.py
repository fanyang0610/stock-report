"""Stage 3 (docs/PLAN.md, the earnings engine): one annual panel per market for the forecast fits and the valuation
inputs, one row per company and fiscal year with revenue, core earnings, book, gross profit, operating cash flow,
the sector, the financial flag and the day the year became public.
- US fits: SEC frames (data.sec.gov/api/xbrl/frames, every us-gaap filer, dead ones included), one calendar year per
  row, re-read here with each fact's period end (public 120 days after it) and with gross profit (else revenue less
  the cost of revenue), operating income and operating cash flow added (data/backtest/us_frames_ext.csv.gz; the frame
  files are read in memory and never stored). US valuation inputs: us_annual (today's candidates, own fiscal years,
  filing dates, 20-F filers too).
- CN: 业绩报表 annual rows since 2009 (扣非 core earnings), public on the notice date; 申万 level 1 of the year end.
- HK: Eastmoney main indicators since 2015 (annual rows), public 90 days after the period; Eastmoney industry type.

  uv run python -m backtest.earn_panel fetch   # the US frames with period ends, gross profit, operating income and cash flow
"""

import sys

import numpy as np
import pandas as pd

from backtest import panel
from stockreport import history
from stockreport.fetch import frames
from stockreport.fetch.sec import WITH_NCI, make_http

EXT = panel.BT / "us_frames_ext.csv.gz"
US_LAG = 120  # days from a frame fact's period end to its 10-K (deadlines: 60-90 days)
# per field: concepts in order (revenue: the largest tagged, as fetch/frames.py; the rest: the first tagged)
CONCEPTS = frames.CONCEPTS | {"gp": ["GrossProfit"], "cost": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
                              "oi": ["OperatingIncomeLoss"],
                              "ocf": ["NetCashProvidedByUsedInOperatingActivities",
                                      "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]}
FIN_SIC = (6000, 6411)  # banks, credit institutions, brokers and exchanges, insurers and agents (not real estate, REITs, funds)


def fetch_year(http, year: int) -> pd.DataFrame:
    out = {}
    for field, names in CONCEPTS.items():
        for name in names:
            instant = "Q4I" if field == "equity" else ""
            resp = http.get(frames.FRAME.format(concept=name, year=year, instant=instant), ok=(200, 404))
            for d in resp.json().get("data", []) if resp.status_code == 200 else []:
                row = out.setdefault(d["cik"], {"cik": d["cik"], "name": d["entityName"], "year": year})
                if field == "revenue":
                    if d["val"] >= row.get("revenue", -np.inf):
                        row["revenue"], row["rev_end"] = d["val"], d["end"]
                elif field not in row:
                    row[field] = d["val"]
                    if field == "ni":
                        row["end"] = d["end"]
        print(f"CY{year} {field}: {len(out)} filers", flush=True)
    cols = ["cik", "name", "year", "end", "rev_end", "revenue", "ni", "equity", "gp", "cost", "oi", "ocf"]
    return pd.DataFrame(list(out.values())).reindex(columns=cols)


def fetch() -> None:
    http = make_http()
    rows = pd.concat([fetch_year(http, y) for y in range(frames.FIRST_YEAR, 2026)])
    rows.sort_values(["cik", "year"]).to_csv(EXT, index=False, compression="gzip")
    print(f"{EXT}: {len(rows)} rows")


if __name__ == "__main__":
    {"fetch": fetch}[sys.argv[1]]()
