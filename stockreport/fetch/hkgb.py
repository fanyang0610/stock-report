"""Hong Kong Government Bonds (www.hkgb.gov.hk): the HK 10-year yield, from the daily closing
reference pricings workbook (benchmark issues, the last ~10 business days). It is a legacy .xls."""

import pandas as pd
import xlrd

from stockreport.fetch import Http, save_rates

URL = "https://www.hkgb.gov.hk/en/others/documents/HKD_DailyClosingReferencePricings_IBPandGSBP.xls"
http = Http(min_interval=0.5, headers={"User-Agent": "Mozilla/5.0"})


def parse_closings(content: bytes) -> pd.DataFrame:
    """The benchmark sheet: a 'Tenor' row names the columns ('10-year' over its price; the yield is
    the next column), then one row per day with an Excel date in the first column."""
    book = xlrd.open_workbook(file_contents=content)
    sheet = book.sheet_by_index(0)
    rows = [sheet.row_values(i) for i in range(sheet.nrows)]
    col = next(r.index("10-year") for r in rows if r[0] == "Tenor") + 1
    return pd.DataFrame([{"date": xlrd.xldate_as_datetime(r[0], book.datemode).date().isoformat(), "market": "hk",
                          "y10": r[col]} for r in rows if isinstance(r[0], float) and isinstance(r[col], float)])


def update_yield() -> None:
    save_rates(parse_closings(http.get(URL).content), "hk")
