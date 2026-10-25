"""CNINFO (www.cninfo.com.cn): the A-share list with CNINFO's orgIds and the announcement query that
fetch/filings.py reads a stock's filings with."""

from datetime import timedelta, timezone

from stockreport.fetch import Http

STOCKS_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"  # every A-share with its CNINFO orgId
QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
BEIJING = timezone(timedelta(hours=8))
http = Http(min_interval=0.5)


def org_ids() -> dict[str, str]:
    """A-share code -> CNINFO orgId (needed by the announcement query)."""
    return {s["code"]: s["orgId"] for s in http.get(STOCKS_URL).json()["stockList"]}

