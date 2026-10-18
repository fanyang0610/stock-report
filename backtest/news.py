"""News test (A2.8, CN): do large one-day moves with a material announcement continue, and moves without
one reverse? Moves: a day's return over the CSI 300 beyond 2.5 standard deviations of the stock's last
120 days, for stocks in that month's top-800 universe, in the 通达信 period (2021-08 on). CNINFO's
market-wide feed stops after ~80 pages a day, so a random sample of moves is checked per stock (the
announcements of the day before and the day of the move). Outcome: the return over the CSI 300 in the
5, 20 and 60 trading days after the move.

  uv run python -m backtest.news sample   # → data/backtest/news_events.csv.gz (CNINFO, ~50 min)
"""

import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from backtest import panel, run
from stockreport.fetch import cninfo

N_SAMPLE = 2400
MATERIAL = re.compile(r"业绩预告|业绩快报|年度报告|半年度报告|季度报告|合同|中标|收购|出售|重组|重大资产|回购|增持|减持|"
                      r"定向增发|非公开发行|向特定对象发行|股权激励|立案|处罚|诉讼|仲裁|问询函|监管函|警示函|退市|"
                      r"控制权|实际控制人|利润分配|分红|对外投资|签署|战略合作|框架协议|获得.*(批|证|注册)|临床|"
                      r"药品|专利|项目|产能|涨价|价格调整|业绩说明|经营数据|产销|销售数据")
RESPONSE = re.compile(r"异常波动|严重异常|股价异动|交易风险提示")  # the company answering the move: no news


def moves(px: panel.CNPrices, data: dict) -> pd.DataFrame:
    """Every qualifying move in the 通达信 period: stock, day, abnormal return, z."""
    start = (panel.BT / "tdx_start.txt").read_text().strip()
    idx = px.index.reindex(pd.to_datetime(px.days)).ffill().to_numpy()
    mret = np.r_[np.nan, idx[1:] / idx[:-1] - 1]
    ab = np.where(px.traded, px.ret - 1 - mret[:, None], np.nan)
    sd = pd.DataFrame(ab).rolling(120, min_periods=60).std().shift(1).to_numpy()
    z = ab / sd
    universe = {m: set(d["snap"].index) for m, d in data.items()}
    month_end = sorted(universe)
    rows = []
    for t in np.flatnonzero(px.days >= start):
        prior = [m for m in month_end if m < px.days[t]]
        if not prior or t + 60 >= len(px.days):
            continue
        cols = [px.col[c] for c in universe[prior[-1]] if c in px.col]
        hit = [c for c in cols if np.isfinite(z[t, c]) and abs(z[t, c]) > 2.5]
        for c in hit:
            after = ab[t + 1: t + 61, c]
            rows.append({"day": str(px.days[t]), "code": str(px.codes[c]), "ab": ab[t, c], "z": z[t, c],
                         "car_5": np.nansum(after[:5]), "car_20": np.nansum(after[:20]), "car_60": np.nansum(after[:60])})
    ev = pd.DataFrame(rows).sort_values(["code", "day"])
    gap = pd.to_datetime(ev["day"]).groupby(ev["code"]).diff().dt.days
    return ev[gap.isna() | (gap > 28)]  # no second move of a stock within 4 weeks (overlapping outcomes)


def sample() -> None:
    run.panel.setup_history("cn")
    px, data = panel.CNPrices(), run.load("cn")
    ev = moves(px, data)
    ev = ev.groupby(np.sign(ev["ab"]), group_keys=False).apply(lambda g: g.sample(min(len(g), N_SAMPLE // 2), random_state=9))
    orgs = cninfo.org_ids()
    titles, material = [], []
    for code, day in zip(ev["code"], ev["day"]):
        if code not in orgs:
            titles.append(None), material.append(np.nan)
            continue
        before = (pd.Timestamp(day) - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
        payload = cninfo.http.post(cninfo.QUERY_URL, data={
            "stock": f"{code},{orgs[code]}", "tabName": "fulltext", "pageSize": 30, "pageNum": 1,
            "column": "sse" if code.startswith("6") else "szse", "category": "", "plate": "",
            "seDate": f"{before}~{day}", "searchkey": "", "secid": "", "trade": "", "sortName": "", "sortType": "",
            "isHLtitle": "false"}).json()
        ts = [re.sub(r"<[^>]+>", "", a.get("announcementTitle") or "") for a in payload.get("announcements") or []
              if datetime.fromtimestamp(a["announcementTime"] / 1000, cninfo.BEIJING).strftime("%Y-%m-%d") >= prior_day(px, day)]
        titles.append(" | ".join(ts)[:500])
        material.append(any(MATERIAL.search(t) and not RESPONSE.search(t) for t in ts))
    ev["titles"], ev["material"] = titles, material
    ev.to_csv(panel.BT / "news_events.csv.gz", index=False, compression="gzip")


def prior_day(px: panel.CNPrices, day: str) -> str:
    i = int(np.searchsorted(px.days, day))
    return px.days[max(i - 1, 0)]


def summary(ev: pd.DataFrame) -> pd.DataFrame:
    """Mean return over the CSI 300 after the move, signed by the move (positive = continuation), by move
    direction and whether a material announcement came with it; in- and out-of-sample."""
    ev = ev.dropna(subset=["material"]).copy()
    ev["sample"] = np.where(ev["day"] <= "2023-12-31", "in", "out")
    ev["dir"] = np.where(ev["ab"] > 0, "up", "down")
    ev["news"] = np.where(ev["material"].astype(bool), "with news", "no news")
    rows = []
    for (sample, d, news), g in ev.groupby(["sample", "dir", "news"]):
        sign = 1 if d == "up" else -1
        row = {"sample": sample, "move": d, "news": news, "n": len(g)}
        for k in (5, 20, 60):
            x = sign * g[f"car_{k}"]
            row[f"cont_{k}"], row[f"t_{k}"] = x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    if sys.argv[1] == "sample":
        sample()
