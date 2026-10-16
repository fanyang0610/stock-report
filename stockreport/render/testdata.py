"""Fake report used only by `send --test`: 3 made-up rows per market, all marked 测试数据."""

from datetime import date, timedelta

_ROWS = [  # bucket, action, price, fair value low/mid/high
    ("buy", "买入", 100.0, 112.0, 125.0, 140.0),
    ("hold", "持有/不追高", 50.0, 45.0, 52.0, 58.0),
    ("sell", "卖出/回避", 80.0, 52.0, 60.0, 68.0),
]
_MARKETS = [("US", "美股 US", "USD"), ("HK", "港股 HK", "HKD"), ("CN", "A股 CN", "CNY")]
_NAMES = ["测试公司甲", "测试公司乙", "测试公司丙"]
_TRIGGERS = {
    "buy": "若股价跌破公允价下限或下季利润下滑，重新评估",
    "hold": "若空间升至 +15% 以上或质量分跌出前 30%，重新评估",
    "sell": "若空间回到 −10% 以内且利润转增，重新评估",
}


def test_report(today: date | None = None) -> dict:
    today = today or date.today()
    data_date = (today - timedelta(days=1)).isoformat()
    markets = []
    for code, name, currency in _MARKETS:
        picks = []
        for i, (bucket, action, price, low, mid, high) in enumerate(_ROWS):
            picks.append({
                "ticker": f"TEST-{code}-{i + 1}", "name": _NAMES[i], "bucket": bucket, "action": action,
                "price": price, "price_date": data_date,
                "fv_low": low, "fv_mid": mid, "fv_high": high, "upside": mid / price - 1,
                "drivers": ["测试数据：估值偏低", "测试数据：ROE 高于同行"],
                "risk": "测试数据：动量偏弱",
                "trigger": _TRIGGERS[bucket],
                "note": "测试数据，非真实点评。这一行用来检查中文长句在手机上的换行与排版效果。",
                "low_conviction": i == 2,
            })
        markets.append({"code": code, "name": name, "currency": currency, "data_date": data_date, "picks": picks})
    return {
        "title": "股票报告", "date": today.isoformat(), "test": True, "markets": markets,
        "method": "同行业估值（同业倍数回归 + 剩余收益交叉检验），综合价值/质量/成长/动量/风险打分分档。",
    }
