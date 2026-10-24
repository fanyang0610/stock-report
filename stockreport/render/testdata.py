"""Fake report used only by `send --test`: a few made-up rows per market, all marked 测试数据."""

from datetime import date, timedelta

_MARKETS = [("CN", "A股 CN", "CNY", "元"), ("US", "美股 US", "USD", "美元"), ("HK", "港股 HK", "HKD", "港元")]
_NAMES = ["测试公司甲", "测试公司乙", "测试公司丙"]


def _card(code: str, i: int, data_date: str, unit: str, grades: str) -> dict:
    return {"rank": i + 1, "ticker": f"TEST-{code}-{i + 1}", "name": _NAMES[i], "sector": "测试行业", "price": 100.0 + i,
            "price_date": data_date, "score_rank": i + 1, "grades": dict(zip(["价值", "质量", "动量"], grades)),
            "lot_text": f"一手 100 股约 {10_000 + 100 * i:,} {unit}", "why": "测试数据：市盈率低（PE 8.0）；ROE 高（18%）",
            "weak": "测试数据：近一年股价走弱（-20%）", "risk": "测试数据：负债率 72%", "recheck": "2099-01-01",
            "weakest": "动量 E"}


def test_report(today: date | None = None) -> dict:
    today = today or date.today()
    data_date = (today - timedelta(days=1)).isoformat()
    markets = []
    for code, name, currency, unit in _MARKETS:
        buys = [_card(code, i, data_date, unit, "ABA") for i in range(3)]
        hold = _card(code, 0, data_date, unit, "BCB") | {"since": data_date, "status": "继续持有", "reason": "测试数据"}
        markets.append({"code": code, "name": name, "currency": currency, "data_date": data_date, "buys": buys,
                        "holdings": [hold], "avoid": [_card(code, 2, data_date, unit, "EDE")], "vetoes": [],
                        "expect": ["测试数据：模拟回测数字为虚构。"]})
    return {"title": "股票报告", "date": today.isoformat(), "test": True, "markets": markets,
            "method": "测试数据：价值、质量、动量三类打分。", "common": "测试数据。"}
