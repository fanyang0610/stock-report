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


COLS = ["code", "year", "fy_end", "avail", "rev", "earn", "book", "gp", "ocf", "sector", "fin"]
US_FLOOR = 5e7  # US frames: filers with $50m+ revenue in the base year (baserates.US_MIN_REVENUE)
SW_2014 = "2014-02-21"  # the first 申万 change of the scheme the history uses; earlier year ends take it


def us_fin(sic: pd.Series) -> pd.Series:
    s = pd.to_numeric(sic, errors="coerce")
    return s.between(*FIN_SIC)


def us_frames() -> pd.DataFrame:
    """The fit panel for the US: SEC frames per filer (cik) and calendar year, public 120 days after the period end."""
    from stockreport import baserates
    f = pd.read_csv(EXT)
    end = pd.to_datetime(f["end"].fillna(f["rev_end"]).fillna(f["year"].astype(str) + "-12-31"))
    sic = pd.read_csv(frames.SIC, dtype=str).drop_duplicates("code").set_index("code")["sic"]
    code = f["cik"].astype(int).astype(str)
    out = pd.DataFrame({"code": code, "year": f["year"], "fy_end": end.dt.strftime("%Y-%m-%d"),
                        "avail": (end + pd.Timedelta(days=US_LAG)).dt.strftime("%Y-%m-%d"), "rev": f["revenue"],
                        "earn": f["ni"], "book": f["equity"], "gp": f["gp"].fillna(f["revenue"] - f["cost"]), "ocf": f["ocf"],
                        "sector": code.map(sic).map(baserates.ff12).replace("", np.nan), "fin": us_fin(code.map(sic))})
    return out[COLS]


def us_own() -> pd.DataFrame:
    """The US stocks' own fiscal years (us_annual, by ticker): continuing operations less preferred dividends, book
    net of preferred, public on the filing date; sector and financial flag from the SEC SIC code."""
    from stockreport import baserates
    from stockreport.fetch import sec
    a = history.us_annual()
    core = a["ni_cont"].fillna(a["ni"]) - (a["ni"] - a["ni_common"]).clip(lower=0).fillna(0)
    sic = pd.read_csv(frames.SIC, dtype=str).drop_duplicates("code").set_index("code")["sic"]
    cik = a["code"].map(sec.load_ciks()).map(lambda c: str(int(c)) if pd.notna(c) else None).map(sic)
    out = pd.DataFrame({"code": a["code"], "year": a["year"], "fy_end": a["fy_end"], "avail": a["avail"],
                        "rev": a["revenue"], "earn": core, "book": a["equity"] - a["pref"].fillna(0), "gp": a["gp"],
                        "ocf": a["ocf"], "sector": cik.map(baserates.ff12).replace("", np.nan), "fin": us_fin(cik)})
    return out[COLS]


def cn() -> pd.DataFrame:
    """CN fiscal years (业绩报表 annual rows since 2009): 扣非 core earnings, book = BPS × profit ÷ EPS, public on the
    notice date; 申万 level 1 at the year end (the 2014 scheme's first class for earlier year ends)."""
    a = pd.read_csv(panel.HIST / "cn_annual.csv.gz", dtype={"code": str, "period": str, "notice_date": str})
    a = a[a["period"].str.endswith("12-31") & a["code"].str.match(panel.A_SHARE)]
    a = a.sort_values("notice_date").drop_duplicates(["code", "period"], keep="last")
    core = (a["eps_deduct"] / a["eps"]).where(a["eps"] > 0).clip(-1, 1.5).fillna(1)
    shares = a["np"] / a["eps"].where(a["eps"].abs() > 0.005)
    out = pd.DataFrame({"code": a["code"], "year": a["period"].str[:4].astype(int), "fy_end": a["period"],
                        "avail": a["notice_date"], "rev": a["revenue"], "earn": a["np"] * core, "book": a["bps"] * shares,
                        "gp": a["gross_margin"] / 100 * a["revenue"], "ocf": a["ocfps"] * shares})
    sw = pd.read_csv(panel.BT / "sw_history.csv.gz", dtype=str).sort_values("start")
    day = np.maximum(out["fy_end"], SW_2014)
    m = pd.merge_asof(pd.DataFrame({"day": pd.to_datetime(day), "code": out["code"], "i": out.index}).sort_values("day"),
                      sw.assign(day=pd.to_datetime(sw["start"]))[["day", "code", "sw"]], on="day", by="code")
    code_sw = m.set_index("i")["sw"].reindex(out.index).fillna(out["code"].map(sw.groupby("code")["sw"].first()))
    out["sector"], out["fin"] = code_sw.str[:2], code_sw.fillna("").str.startswith(panel.FIN_SW)
    return out[COLS].reset_index(drop=True)


def hk() -> pd.DataFrame:
    """HK fiscal years (Eastmoney annual rows since 2015, CNY; only ratios are used), public 90 days after the period;
    sector = the first level of the industry type, financials as config `financial_industries_hk`."""
    from stockreport.config import CONFIG
    from stockreport.fetch import eastmoney
    h = history.hk_results()
    h = h[h["date_type"] == "001"].assign(year=lambda d: d["period"].str[:4].astype(int))
    h = h.drop_duplicates(["code", "year"], keep="last")
    t = eastmoney.load_hk_list().drop_duplicates("code").set_index("code")["industry_type"].fillna("")
    kind = h["code"].map(t).fillna("")
    out = pd.DataFrame({"code": h["code"], "year": h["year"], "fy_end": h["period"], "avail": h["avail"],
                        "rev": h["revenue"], "earn": h["np"], "book": h["bps"] * h["shares"],
                        "gp": h["gross_margin"] / 100 * h["revenue"], "ocf": h["ocf"],
                        "sector": kind.str.split("-").str[0].replace("", np.nan),
                        "fin": kind.str.split("-").str[-1].isin(CONFIG["peers"]["financial_industries_hk"])})
    return out[COLS].reset_index(drop=True)


def panels(market: str) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """(the fit panel, the stocks' own panel, the base year's revenue floor): the US fits on the frames, the rest on
    one panel."""
    if market == "us":
        return us_frames(), us_own(), US_FLOOR
    p = cn() if market == "cn" else hk()
    return p, p, 0.0


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
