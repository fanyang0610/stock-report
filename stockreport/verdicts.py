"""Your verdicts (AGENTS.md rule 3): `verdict <code> veto|confirm --until D --reason "..."` appends to data/verdicts.csv.
A veto keeps a name out of the Buy and Hold lists (lists.build); a confirm keeps a name as the lists have it when the
results review would remove a Buy or Hold name on a hard red flag (review.apply), and its card says so;
never a number. It ends at its date or when the stock reports a period newer than the snapshot's it was given on."""

import re
from datetime import date

import pandas as pd

from stockreport.config import DATA

PATH = DATA / "verdicts.csv"
COLUMNS = ["date", "market", "code", "verdict", "until", "reason", "period"]


def market_of(code: str) -> str:
    return "cn" if re.fullmatch(r"\d{6}", code) else "hk" if re.fullmatch(r"\d{1,5}", code) else "us"


def periods(market: str) -> pd.Series:
    """Code -> latest report period in the newest snapshot of the market."""
    snaps = sorted((DATA / "snapshots").glob(f"*/{market}.csv.gz"))
    if not snaps:
        return pd.Series(dtype=str)
    return pd.read_csv(snaps[-1], usecols=["code", "period"], dtype=str).set_index("code")["period"]


def load() -> pd.DataFrame:
    return pd.read_csv(PATH, dtype=str, keep_default_na=False) if PATH.exists() else pd.DataFrame(columns=COLUMNS)


def add(code: str, verdict: str, until: str, reason: str, today: date) -> dict:
    code = code.zfill(5) if re.fullmatch(r"\d{1,5}", code) else code.upper()
    market = market_of(code)
    row = {"date": today.isoformat(), "market": market, "code": code, "verdict": verdict,
           "until": date.fromisoformat(until).isoformat(), "reason": reason, "period": periods(market).get(code, "")}
    pd.concat([load(), pd.DataFrame([row])]).to_csv(PATH, index=False)
    return row


def active(market: str, today: date, period: pd.Series) -> dict[str, dict]:
    """Code -> the newest verdict still in force (before its date and with no newer report period)."""
    df = load()
    df = df[(df["market"] == market) & (df["until"] >= today.isoformat())]
    out = {}
    for row in df.to_dict("records"):
        now = period.get(row["code"])
        if not row["period"] or not isinstance(now, str) or now <= row["period"]:
            out[row["code"]] = row
    return out


def show(today: date) -> int:
    for market in ("cn", "us", "hk"):
        for code, v in active(market, today, periods(market)).items():
            print(f"{market.upper()} {code} {v['verdict']} until {v['until']} (given {v['date']}): {v['reason']}")
    return 0
