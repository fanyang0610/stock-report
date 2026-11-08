"""The official listings stage 12's name resolution confirms a company against, stored as data/research/listings.csv.gz
(weekly): CNINFO's A-share and HK lists (Chinese short names, pinyin initials), HKEX's List of Securities (English
names; ordinary shares and REITs on the HKD counter, no warrants, CBBCs, ETFs or debt), SEC's ticker file (US names
and CIKs, no OTC lines), and Eastmoney's ORG_CODE, one per issuer across its A, H and US lines (as the screening's
issuer dedupe), so 比亚迪 finds 002594 and 01211 as one company."""

import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import date

import pandas as pd

from stockreport.config import DATA
from stockreport.fetch import Http, hkex, sec
from stockreport.research import ROOT, cached, days

PATH = ROOT / "listings.csv.gz"
CNINFO = "http://www.cninfo.com.cn/new/data/{}_stock.json"
HK_KINDS = {"Equity Securities (Main Board)": "ordinary", "Equity Securities (GEM)": "ordinary"}
US_EXCHANGES = {"Nasdaq", "NYSE", "CBOE"}


def parse_cninfo(payload: dict, category: str) -> pd.DataFrame:
    rows = [{"code": s["code"], "name": s["zwjc"], "pinyin": s.get("pinyin")} for s in payload.get("stockList", [])
            if s.get("category") == category]
    return pd.DataFrame(rows, columns=["code", "name", "pinyin"])


def parse_hkex(xlsx: bytes) -> pd.DataFrame:
    """Code, English name and kind of the HKD-counter ordinary shares and REITs in HKEX's List of Securities."""
    rows = []
    sheet = zipfile.ZipFile(io.BytesIO(xlsx)).read("xl/worksheets/sheet1.xml")
    for row in ET.fromstring(sheet).iterfind(".//x:row", hkex.SHEET):
        c = {"".join(ch for ch in cell.get("r") if ch.isalpha()): "".join(cell.itertext()) for cell in row.iterfind("x:c", hkex.SHEET)}
        kind = "reit" if c.get("C") == "Real Estate Investment Trusts" else HK_KINDS.get(c.get("D")) if c.get("C") == "Equity" else None
        if kind and c.get("Q") == "HKD":
            rows.append({"code": c["A"], "name_en": c.get("B"), "kind": kind})
    return pd.DataFrame(rows, columns=["code", "name_en", "kind"])


def build() -> pd.DataFrame:
    http = Http(min_interval=0.5, headers={"User-Agent": "Mozilla/5.0"})
    cn = parse_cninfo(http.get(CNINFO.format("szse")).json(), "A股").assign(market="cn", kind="ordinary")
    quotes = pd.read_csv(DATA / "quotes" / "cn.csv.gz", dtype={"code": str, "org_code": str})
    cn = cn.merge(quotes[["code", "org_code"]], on="code", how="left")
    hk = parse_hkex(http.get(hkex.LOTS_URL).content).merge(
        parse_cninfo(http.get(CNINFO.format("hke")).json(), "港股"), on="code", how="left")
    hk_list = pd.read_csv(DATA / "quotes" / "hk_list.csv.gz", dtype={"code": str, "org_code": str})
    hk = hk.merge(hk_list[["code", "org_code"]], on="code", how="left").assign(market="hk")
    us = sec.update_ciks(date.today())
    us = us[us["exchange"].isin(US_EXCHANGES)].rename(columns={"name": "name_en"}).assign(market="us", kind="listed")
    orgs = pd.read_csv(DATA / "fundamentals" / "us_org.csv.gz", dtype={"code": str, "org_code": str})
    us = us.merge(orgs.drop_duplicates("code"), on="code", how="left")
    cols = ["market", "code", "name", "name_en", "pinyin", "kind", "org_code", "cik"]
    return pd.concat([cn, hk, us]).reindex(columns=cols).drop_duplicates(["market", "code"])


def load() -> pd.DataFrame:
    return cached(PATH, days("statements"), build)


def issuer(market: str, code: str) -> pd.DataFrame:
    """Every listing of the same issuer (its ORG_CODE), this one included."""
    df = load()
    org = df.loc[(df["market"] == market) & (df["code"] == code), "org_code"].dropna()
    return df[df["org_code"] == org.iloc[0]] if len(org) else df[(df["market"] == market) & (df["code"] == code)]
