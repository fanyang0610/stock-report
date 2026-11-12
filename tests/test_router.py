"""The WeChat router (research stage 12): ~50 messages routed with DeepSeek and Eastmoney's search box mocked, on a small
sample of the listings (research/listings.py's layout); the background queue; the research record's 12-month math."""

import json
from datetime import date

import pandas as pd
import pytest

from stockreport.research import jobs, record, router

ROWS = [  # market, code, name, name_en, org_code, cik, kind
    ("cn", "600519", "贵州茅台", None, "MT", None, "ordinary"), ("cn", "000858", "五粮液", None, "WLY", None, "ordinary"),
    ("cn", "601318", "中国平安", None, "PA", None, "ordinary"), ("hk", "02318", "中国平安", "PING AN", "PA", None, "ordinary"),
    ("cn", "000001", "平安银行", None, "PAB", None, "ordinary"),
    ("cn", "002594", "比亚迪", None, "BYD", None, "ordinary"), ("hk", "01211", "比亚迪股份", "BYD COMPANY", "BYD", None, "ordinary"),
    ("hk", "00285", "比亚迪电子", "BYD ELECTRONIC", "BYDE", None, "ordinary"),
    ("hk", "00700", "腾讯控股", "TENCENT", "TC", None, "ordinary"), ("hk", "01698", "腾讯音乐-SW", "TME-SW", "TME", None, "ordinary"),
    ("us", "TME", None, "Tencent Music Entertainment Group", "TME", 1744676, "listed"),
    ("cn", "300750", "宁德时代", None, "CATL", None, "ordinary"), ("hk", "03750", "宁德时代", "CATL", "CATL", None, "ordinary"),
    ("cn", "300751", "迈为股份", None, "MW", None, "ordinary"),
    ("cn", "600036", "招商银行", None, "CMB", None, "ordinary"), ("hk", "03968", "招商银行", "CM BANK", "CMB", None, "ordinary"),
    ("hk", "09988", "阿里巴巴-W", "BABA-W", "BABA", None, "ordinary"),
    ("us", "BABA", None, "Alibaba Group Holding Ltd", "BABA", 1577552, "listed"),
    ("hk", "00823", "领展房产基金", "LINK REIT", "LINK", None, "reit"),
    ("us", "AAPL", None, "Apple Inc.", "AAPL", 320193, "listed"), ("us", "NVDA", None, "NVIDIA CORP", "NVDA", 1045810, "listed"),
    ("us", "O", None, "REALTY INCOME CORP", "O", 726728, "listed"),
    ("us", "GOOGL", None, "Alphabet Inc.", "GOOG", 1652044, "listed"), ("us", "GOOG", None, "Alphabet Inc.", "GOOG", 1652044, "listed"),
    ("us", "BRK.B", None, "BERKSHIRE HATHAWAY INC", None, 1067983, "listed"),
    ("us", "BRK.A", None, "BERKSHIRE HATHAWAY INC", None, 1067983, "listed"),
    ("us", "TM", None, "TOYOTA MOTOR CORP", "TM", 1094517, "listed"),
    ("us", "SPY", None, "SPDR S&P 500 ETF TRUST", None, 884394, "listed"),  # an ETF: not in the screener
]
US = {"TME": "Tencent Music Entertainment Group", "BABA": "Alibaba Group Holding Limited", "AAPL": "Apple Inc",
      "NVDA": "NVIDIA Corporation", "O": "Realty Income Corporation", "GOOGL": "Alphabet Inc", "GOOG": "Alphabet Inc",
      "BRK.B": "Berkshire Hathaway Inc", "BRK.A": "Berkshire Hathaway Inc", "TM": "Toyota Motor Corporation"}
BOX = {  # Eastmoney's search box, as probed 2026-11-12 (only the hits in the sample)
    "平安": [("cn", "000001"), ("cn", "601318")], "茅台": [("cn", "600519")], "英伟达": [("us", "NVDA")],
    "腾讯控股": [("hk", "00700")], "阿里巴巴": [("us", "BABA"), ("hk", "09988")], "宁德时代": [("cn", "300750"), ("hk", "03750")],
}


def c(name="", name_en="", ticker="", market=""):
    return {"name": name, "name_en": name_en, "ticker": ticker, "market": market}


def said(text, *candidates):
    return {"said": text, "candidates": list(candidates)}


DEEPSEEK = {  # what the fast model returns for each message (its reading is a hint; code confirms it)
    "茅台": {"intent": "research", "companies": [said("茅台", c("贵州茅台", "Kweichow Moutai", "600519", "cn"))]},
    "腾讯": {"intent": "research", "companies": [said("腾讯", c("腾讯控股", "Tencent", "0700", "hk"))]},
    "nvidia": {"intent": "research", "companies": [said("nvidia", c("英伟达", "NVIDIA", "NVDA", "us"))]},
    "how is tencent doing": {"intent": "research", "companies": [said("tencent", c("腾讯控股", "Tencent Holdings", "00700", "hk"))]},
    "テンセント": {"intent": "research", "companies": [said("テンセント", c("腾讯控股", "Tencent", "700", "hk"))]},
    "宁德": {"intent": "research", "companies": [said("宁德", c("宁德时代", "CATL", "300750", "cn"))]},
    "贵州矛台": {"intent": "research", "companies": [said("贵州矛台", c("贵州茅台", "", "600519", "cn"))]},
    "tencnet": {"intent": "research", "companies": [said("tencnet", c("腾讯控股", "Tencent", "", "hk"))]},
    "aapl": {"intent": "research", "companies": [said("aapl", c("苹果", "Apple", "AAPL", "us"))]},
    "AAPL": {"intent": "research", "companies": [said("AAPL", c("苹果", "Apple Inc.", "AAPL", "us"))]},
    "BRK.B": {"intent": "research", "companies": [said("BRK.B", c("伯克希尔", "Berkshire Hathaway", "BRK.B", "us"))]},
    "BYD": {"intent": "research", "companies": [said("BYD", c("比亚迪", "BYD Company", "002594", "cn"))]},
    "HELP": {"intent": "help", "companies": []},
    "某某科技": {"intent": "research", "companies": [said("某某科技", c("某某科技", "", "NVDA", "us"))]},  # a guessed ticker
    "alibaba": {"intent": "research", "companies": [said("alibaba", c("阿里巴巴", "Alibaba", "BABA", "us"))]},
    "平安": {"intent": "research", "companies": [said("平安", c("中国平安", "Ping An", "601318", "cn"),
                                                       c("平安银行", "Ping An Bank", "000001", "cn"))]},
    "茅台和五粮液": {"intent": "research", "companies": [said("茅台", c("贵州茅台", "", "600519", "cn")),
                                                     said("五粮液", c("五粮液", "", "000858", "cn"))]},
    "apple and nvidia": {"intent": "research", "companies": [said("apple", c("苹果", "Apple", "AAPL", "us")),
                                                             said("nvidia", c("英伟达", "NVIDIA", "NVDA", "us"))]},
    "沪深300怎么样": {"intent": "unsupported", "unsupported": "index", "companies": []},
    "比特币": {"intent": "unsupported", "unsupported": "crypto", "companies": []},
    "字节跳动": {"intent": "unsupported", "unsupported": "unlisted", "companies": []},
    "510300": {"intent": "unsupported", "unsupported": "fund", "companies": []},
    "你好": {"intent": "help", "companies": []},
    "今天的股票报告呢": {"intent": "screening", "companies": []},
    "宁德时代的前景": {"intent": "research", "companies": [said("宁德时代", c("宁德时代", "CATL", "300751", "cn"))]},  # wrong ticker
    "最近有什么好股票": {"intent": "research", "companies": [said("贵州茅台", c("贵州茅台", "", "600519", "cn"))]},  # not said
    "标普500ETF": {"intent": "research", "companies": [said("标普500ETF", c("", "SPDR S&P 500", "SPY", "us"))]},  # an ETF
    "Realty Income": {"intent": "research", "companies": [said("Realty Income", c("", "Realty Income", "O", "us"))]},
    "トヨタ": {"intent": "research", "companies": [said("トヨタ", c("丰田汽车", "Toyota Motor", "TM", "us"))]},
    "谷歌": {"intent": "research", "companies": [said("谷歌", c("谷歌", "Alphabet", "GOOGL", "us"))]},
    "tencent music": {"intent": "research", "companies": [said("tencent music", c("腾讯音乐", "Tencent Music", "TME", "us"))]},
    "3": {"intent": "unclear", "companies": []},
    "the insurance one": {"intent": "answer", "choice": 1, "companies": []},
    "随便": {"intent": "unclear", "companies": []},
}


@pytest.fixture
def sample(monkeypatch):
    df = pd.DataFrame(ROWS, columns=["market", "code", "name", "name_en", "org_code", "cik", "kind"])
    table = router.prepare(df, pd.Series(US))
    monkeypatch.setattr(router, "companies", lambda: table)
    monkeypatch.setattr(router, "search", lambda text: list(dict.fromkeys(k for f in BOX.get(text, []) for k in router.at(f))))
    asked = []

    def read(text, pending):
        asked.append(text)
        return DEEPSEEK[text]
    monkeypatch.setattr(router, "read", read)
    return asked


def lead(d):
    assert d["action"] == "research", d
    return [x["code"] for x in d["issuer"]["lines"]]


@pytest.mark.parametrize("text, lines", [
    ("600519", ["600519"]), ("0700", ["00700"]), ("00700", ["00700"]), ("700.HK", ["00700"]), ("AAPL.US", ["AAPL"]),
    ("$nvda", ["NVDA"]), ("$BRK.B", ["BRK.B", "BRK.A"]), ("贵州茅台", ["600519"]), ("中国平安", ["601318", "02318"]),
    ("比亚迪", ["002594", "01211"]), ("01211", ["01211", "002594"]), ("腾讯控股", ["00700"]), ("Apple Inc.", ["AAPL"]),
    ("SH600036", ["600036", "03968"]), ("贵州茅台。", ["600519"]), ("TENCENT", ["00700"]),
    ("阿里巴巴", ["09988", "BABA"]), ("腾讯音乐", ["01698", "TME"]),  # HKEX's 阿里巴巴-W, 腾讯音乐-SW
])
def test_exact_codes_and_names_need_no_ai(sample, text, lines):
    d = router.route(text)
    assert lead(d) == lines and d["layer"] == 2 and not sample


@pytest.mark.parametrize("text, lines", [
    ("茅台", ["600519"]), ("腾讯", ["00700"]), ("nvidia", ["NVDA"]), ("how is tencent doing", ["00700"]),
    ("テンセント", ["00700"]), ("宁德", ["300750", "03750"]), ("贵州矛台", ["600519"]), ("tencnet", ["00700"]),
    ("aapl", ["AAPL"]), ("AAPL", ["AAPL"]), ("BRK.B", ["BRK.B", "BRK.A"]), ("BYD", ["002594", "01211"]),
    ("alibaba", ["09988", "BABA"]), ("Realty Income", ["O"]), ("トヨタ", ["TM"]),
    ("谷歌", ["GOOGL", "GOOG"]), ("tencent music", ["01698", "TME"]),
])
def test_deepseek_hints_confirmed_by_code(sample, text, lines):
    d = router.route(text)
    assert lead(d) == lines and d["layer"] == 3 and sample == [text]


def test_two_names_take_the_first(sample):
    d = router.route("茅台和五粮液")
    assert lead(d) == ["600519"] and d["rest"] == ["五粮液"]
    assert router.route("apple and nvidia")["rest"] == ["nvidia"]


@pytest.mark.parametrize("text, words", [
    ("沪深300怎么样", "指数"), ("比特币", "加密货币"), ("字节跳动", "还没有上市"), ("510300", "基金"), ("你好", "可以发"),
    ("?", "可以发"), ("HELP", "可以发"), ("最近有什么好股票", "可以发"), ("随便", "可以发"), ("标普500ETF", "没找到"),
])
def test_unsupported_vague_and_not_found(sample, text, words):
    d = router.route(text)
    assert d["action"] == "reply" and words in d["text"]


def test_screening_asked_in_other_words(sample):
    assert router.route("今天的股票报告呢")["action"] == "screening"


def test_ambiguous_and_contradicting_hints_ask(sample):
    d = router.route("平安")
    assert d["action"] == "ask" and [o["lines"][0]["code"] for o in d["options"]] == ["601318", "000001"]
    assert "1 中国平安（601318 / 02318.HK）" in d["text"] and "2 平安银行（000001）" in d["text"]
    d = router.route("宁德时代的前景")  # its ticker names 迈为股份, its name 宁德时代: both, so you choose
    assert d["action"] == "ask" and {o["name"] for o in d["options"]} == {"迈为股份", "宁德时代"}
    d = router.route("某某科技")  # a listed ticker no name or search confirms: asked, not taken
    assert d["action"] == "ask" and d["text"].startswith("你是指 NVIDIA Corporation（NVDA）吗")


@pytest.mark.parametrize("text, code, layer", [
    ("1", "601318", 4), ("第二个", "000001", 4), ("银行", "000001", 4), ("平安银行", "000001", 4), ("２", "000001", 4),
    ("the insurance one", "601318", 3),
])
def test_answers_to_the_question(sample, text, code, layer):
    pending = {"text": "你指的是哪一家？", "options": router.route("平安")["options"]}
    sample.clear()
    d = router.route(text, pending)
    assert lead(d)[0] == code and d["layer"] == layer and (layer == 3) == bool(sample)


def test_out_of_range_answer_is_not_a_choice(sample):
    pending = {"text": "你指的是哪一家？", "options": router.route("平安")["options"]}
    assert router.route("3", pending)["action"] == "reply"


def test_deepseek_down(sample, monkeypatch):
    monkeypatch.setattr(router, "read", lambda text, pending: None)
    assert lead(router.route("600519")) == ["600519"]  # layer 2 still works
    d = router.route("茅台")  # the search box's suggestion, as a question
    assert d["action"] == "ask" and d["layer"] == 4 and d["text"] == "你是指 贵州茅台（600519）吗？是的话回复 1。"
    assert lead(router.route("1", {"text": d["text"], "options": d["options"]})) == ["600519"]
    assert router.route("aapl")["options"][0]["lines"][0]["code"] == "AAPL"
    assert router.route("AAPL")["options"][0]["lines"][0]["code"] == "AAPL"
    assert router.route("你好")["text"] == router.HELP


def test_queue_acknowledges_once_and_answers_in_order(sample, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "ROOT", tmp_path)
    monkeypatch.setattr(jobs, "QUEUE", tmp_path / "queue.json")
    monkeypatch.setattr(jobs, "QUEUE_LOCK", tmp_path / "queue.lock")
    monkeypatch.setattr(jobs, "WORKER_LOCK", tmp_path / "worker.lock")
    today = date(2026, 11, 12)
    byd = router.route("比亚迪")["issuer"]
    assert jobs.add(byd, [], today) == "收到：比亚迪（002594 / 01211.HK）。研究报告约 2 分钟后发出。"
    assert jobs.add(byd, [], today) == "比亚迪（002594 / 01211.HK）的报告已在生成中，稍后发出。"
    ack = jobs.add(router.route("贵州茅台")["issuer"], ["五粮液"], today)
    assert "约 3 分钟后发出（前面还有 1 份）" in ack and "「五粮液」请单独再发一条" in ack
    sent, built = [], []
    from stockreport import deliver
    from stockreport.research import report
    monkeypatch.setattr(deliver, "send_text", lambda text: sent.append(("text", text)))
    monkeypatch.setattr(deliver, "send_file", lambda path, title: sent.append(("file", title)))
    monkeypatch.setattr(report, "built_today", lambda m, code, day: None)

    def build(m, code, day):
        built.append(code)
        if code == "002594":
            raise RuntimeError("source down")  # the issuer's next line is tried
        return {"name": code, "code": code, "summary": f"summary {code}", "pdf": "x.pdf"}
    monkeypatch.setattr(report, "build", build)
    monkeypatch.setattr(jobs.time, "sleep", lambda s: None)
    assert jobs.work() == 0
    assert built == ["002594", "01211", "600519"]
    assert [x[0] for x in sent] == ["text", "file", "text", "file"] and sent[0][1] == "summary 01211"
    assert json.loads((tmp_path / "queue.json").read_text()) == {"jobs": [], "working": None}


def test_record_twelve_months(monkeypatch, tmp_path):
    monkeypatch.setattr(record, "LOG", tmp_path / "log.csv")
    days = pd.date_range("2025-11-03", "2026-11-20", freq="B").strftime("%Y-%m-%d")
    stock = pd.DataFrame({"date": days, "close": 100.0, "prev_close": 100.0})
    stock.loc[stock["date"] == "2026-03-02", "close"] = 130.0  # touches the target once
    stock["prev_close"] = stock["close"].shift(1).fillna(100.0)
    stock.loc[stock["date"] == "2026-06-01", "prev_close"] = 98.0  # a 2% dividend
    fund = pd.DataFrame({"date": days, "close": 1.0, "prev_close": 1.0 / 1.0001})
    charts = {"600519": (stock, None), "510300": (fund, None)}
    monkeypatch.setattr(record.yahoo, "chart", lambda http, job: charts[job[0]])
    record.add({"market": "cn", "code": "600519", "name": "贵州茅台", "rating": "买入", "price": 100.0, "currency": "CNY",
                "target": 125.0, "expected_return": 0.27, "market_return": 0.07}, date(2025, 11, 10))
    record.add({"market": "cn", "code": "600519", "name": "贵州茅台", "rating": "买入", "price": 100.0, "currency": "CNY",
                "target": 120.0, "expected_return": 0.22, "market_return": 0.07}, date(2025, 11, 10))  # the day's last build
    df = record.settle(date(2026, 11, 20))
    r = df.iloc[0]
    assert len(df) == 1 and r["target"] == 120.0 and r["end"] == "2026-11-10"
    assert r["stock_return"] == pytest.approx(130 / 100 * 100 / 130 * 100 / 98 - 1)  # back to 100, plus the dividend
    assert bool(r["hit_any"]) and not bool(r["hit_end"])
    assert record.recent("cn", date(2025, 11, 20), 30)["600519"]["rating"] == "买入"
    assert "买入: 1 settled" in record.show(date(2026, 11, 20))


def test_listener_routes_messages(sample, tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from stockreport import deliver, listener
    now = datetime.now(timezone.utc).isoformat()
    polls = [[{"id": "1", "text": "股票报告", "receivedAt": now}, {"id": "2", "text": "平安", "receivedAt": now},
              {"id": "3", "text": "1", "receivedAt": now}, {"id": "4", "text": "今天的股票报告呢", "receivedAt": now}]]

    def poll(ms):
        if not polls:
            raise deliver.DeliveryError("done")
        return polls.pop(0)
    sent, events = [], []
    monkeypatch.setattr(listener, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(listener, "LOCK", tmp_path / "listen.lock")
    monkeypatch.setattr(listener.time, "sleep", lambda s: None)
    monkeypatch.setattr(deliver, "poll", poll)
    monkeypatch.setattr(deliver, "send_text", sent.append)
    monkeypatch.setattr(listener, "reply", lambda today: events.append("screening"))
    monkeypatch.setattr(jobs, "add", lambda o, rest, today: f"收到：{router.label(o)}")
    monkeypatch.setattr(jobs, "start", lambda: events.append("worker"))
    listener.listen(60)
    assert events == ["screening", "worker"]  # the second screening request in the same poll isn't sent twice
    assert sent[0].startswith("你指的是哪一家？") and sent[1] == "收到：中国平安（601318 / 02318.HK）"
    assert sample == ["平安", "今天的股票报告呢"]  # the keyword and the answer "1" use no AI
    assert "pending" not in json.loads((tmp_path / "state.json").read_text())
