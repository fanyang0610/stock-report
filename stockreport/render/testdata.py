"""Fake report used by `send --test` and the summary's size test: a full-size made-up report (per market 20 buys, 10
avoid names, holdings to sell, re-check and keep, a name the review removed; US names long and in English, the worst
case for the summary's size), all marked 测试数据."""

from datetime import date, timedelta

from stockreport.report import COMMON, GUIDE, METHOD

_MARKETS = [("CN", "A股 CN", "CNY", "元"), ("US", "美股 US", "USD", "美元"), ("HK", "港股 HK", "HKD", "港元")]
_CN = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"


def _card(code: str, i: int, data_date: str, unit: str, grades: str, **more) -> dict:
    if code == "US":
        ticker, name = f"TS{chr(65 + i)}", f"Testing Manufacturing Group {i + 1:02d} Inc"
        short = f"{ticker} Testing Manufacturing Group {i + 1:02d}"
    else:
        ticker, name = f"{'9' if code == 'CN' else ''}{i + 1:05d}", f"测试{_CN[i % len(_CN)]}{'科技' if i < len(_CN) else '集团'}"
        short = name
    return {"rank": i + 1, "ticker": ticker, "name": name, "name_en": "", "short": short, "sector": "测试行业",
            "business": "测试数据：一家虚构的公司，生产和销售测试用的产品。", "price": 100.0 + i, "price_date": data_date,
            "score_rank": i + 1, "grades": dict(zip(["价值", "质量", "成长", "动量"], grades)),
            "lot_text": f"一手 100 股约 {10_000 + 100 * i:,} {unit}", "why": "测试数据：同行中市盈率低（PE 8.0）；同行中 ROE 高（18%）",
            "weak": "测试数据：近一年股价走弱（-20%）", "risk": "测试数据：负债率 72%", "recheck": "2099-01-01",
            "weakest": "动量 E", "weight": 0.05, "risk_label": "风险", "risk_text": "测试数据：负债率 72%",
            "avoid_why": "测试数据：近一年股价走弱（-20%）；负债率 72%", "review": "审核未见重大风险", "review_kind": "ok",
            "review_shown": "审核未见重大风险", "note": "测试数据：虚构的点评，只用文字。"} | more


def test_report(today: date | None = None) -> dict:
    today = today or date.today()
    data_date = (today - timedelta(days=1)).isoformat()
    markets = []
    for code, name, currency, unit in _MARKETS:
        buys = [_card(code, i, data_date, unit, "ABBA") for i in range(20)]
        held = [_card(code, i, data_date, unit, "BCCB", since=data_date, status=s, reason=f"测试数据：{s}的原因")
                for i, s in zip(range(10, 24), ["卖出"] + ["复核"] * 6 + ["继续持有"] * 7)]
        soft = {"review": "市场可能在担心：测试数据（新闻：「虚构的标题」）", "review_kind": "soft",
                "review_shown": "市场可能在担心：测试数据（新闻：「虚构的标题」）"}
        removed = _card(code, 21, data_date, unit, "AAAA", reason="测试数据：被收购（虚构）", status=f"由 {buys[-1]['short']} 替换")
        markets.append({
            "code": code, "name": name, "short": name.split()[0], "currency": currency, "unit": unit, "field": "测试市场",
            "data_date": data_date, "recheck": "2099-01-01", "share": "5%", "stale": "", "review": "",
            "expect": {"line": "测试数据：模拟回测数字为虚构。", "short": "测试数据：历史模拟平均每年比基金多赚 9.9%，99% 的时候跑赢。",
                       "detail": ["测试数据。"]},
            "buys": buys, "holdings": held, "sell": held[:1], "check": [h | soft for h in held[1:7]], "keep": held[7:],
            "avoid": [_card(code, i, data_date, unit, "EDDE") for i in range(10)], "vetoes": [], "removed": [removed],
            "changes": {"since": data_date, "new": buys[:3], "gone": [h["short"] for h in held[:3]]}})
    return {"title": "股票报告", "date": today.isoformat(), "test": True, "markets": markets, "guide": GUIDE,
            "method": METHOD, "common": COMMON, "recorded": True, "storage_warning": ""}
