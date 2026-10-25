"""Filing rules (PLAN.md, "Results review"): each filing classified by kind from its title (CN, HK: and HKEX's
category) or its form and 8-K items (US); routine ones are dropped from the review's sources (fetch/filings.recent)."""

import re

KINDS = {"earnings": "业绩", "deal": "交易", "risk": "风险", "capital": "股本", "holders": "增减持", "business": "经营",
         "other": "其他"}
# Title (CN; HK: title and HKEX's headline category) patterns, tried in this order after the routine ones.
# The exchange-mandated 股票交易异常波动 notice says nothing new about the company: routine.
RULES = {
    "cn": [("routine", r"法律意见|核查意见|股东会决议|股东大会决议|召开.*股东|股东.*通知|董事会.*决议|监事会|独立董事|工作细则|"
                       r"制度|章程|鉴证报告|保荐|路演|翌日披露|异常波动|专门委员会|职工代表|选举|聘任|授信|担保|套期保值|"
                       r"募集资金|摘要|英文|更正|工商变更|证券事务代表|会计师事务所|内部控制|社会责任|ESG|转股|赎回|融资券|公司债|"
                       r"会议资料|H股公告|已回购股份|通知债权人|资本债|永续债|中期票据|短期融资|债券.*(发行结果|付息|兑付|评级)"),
           ("deal", r"重大资产重组|重组|收购|出售|吸收合并|换股|要约|股权转让|资产置换|购买资产|控制权|分拆|私有化|筹划"),
           ("risk", r"立案|调查|处罚|警示|监管函|问询函|关注函|诉讼|仲裁|退市|终止上市|停牌|停业|\*?ST|无法表示|保留意见|否定意见|持续经营|冻结|"
                    r"违规|逾期|失信|破产|重整|减值"),
           ("earnings", r"业绩|预增|预减|预亏|扭亏|季度报告|年度报告|半年度报告|利润"),
           ("capital", r"回购|增发|向特定对象发行|定向发行|配股|可转换|可转债|股权激励|限制性股票|股票期权|员工持股|权益分派|"
                       r"利润分配|分红|送转|注销|解除限售|上市流通|发行.*股票"),
           ("holders", r"减持|增持|质押|权益变动|持股.*变动"),
           ("business", r"合同|中标|订单|协议|合作|批准|注册证|一致性评价|临床|投产|项目|专利|产品")],
    "hk": [("routine", r"通知信函|回條|董事名單|董事會召開日期|股東周年大會|股東特別大會|股東大會|投票結果|更換董事|"
                       r"董事委任|董事辭任|董事委員會|決議|環境、社會及管治|股份計劃|股份獎勵|購股權|章程|職權範圍|英文版面|"
                       r"法律意見|債券|理財|擔保|致.*股東|函件|任職資格|註冊辦事處|營業地點|聘任.*核數師|續聘|投資者關係|說明會|"
                       r"票據|^海外監管公告$"),
           ("earnings", r"盈利警告|盈利預告|業績"),
           ("deal", r"須予披露|主要交易|非常重大|關連交易|收購|出售|要約|私有化|合併|分拆|反收購|收購守則|協議安排|重組"),
           ("risk", r"停牌|暫停買賣|清盤|訴訟|調查|立案|處罰|處分|批評|紀律|除牌|更換核數師|核數師辭任|延遲|監管者|呈請|違約"),
           ("earnings", r"業績|盈利|虧損|年報|中期報告|季度報告|財務報表"),
           ("capital", r"購回|回購|配售|供股|發行股份|可換股|股息|派息|紅股|以股代息|股本"),
           ("holders", r"增持|減持|質押|抵押股份"),
           ("business", r"業務|合約|協議|合作|批准|項目|產品|營運|投資"),
           ("other", r"內幕消息")],
}
# Checked before the routine rules (which drop bond, guarantee and auditor titles): a default, overdue debt or an
# auditor resigning is a risk filing however it is titled
ALARM = r"违约|違約|逾期|未能按期|无法兑付|無法兌付|(会计师事务所|會計師事務所|核數師|核数师|审计机构).{0,6}(辞任|辭任|辞职|辭職)"
# HK document types (HKEX's top-level category) that are never news
HK_ROUTINE = r"翌日披露報表|月報表|交易所買賣基金|債券及結構性產品|委任代表表格|展示文件|槓桿及反向|公司資料報表"
# US: 8-K items, then forms (an 8-K whose items are all routine, e.g. 7.01 Reg FD or 9.01 exhibits, is routine)
US_ITEMS = {"2.02": "earnings", "1.01": "deal", "1.02": "deal", "2.01": "deal", "5.01": "deal", "1.03": "risk",
            "1.05": "risk", "2.04": "risk", "2.05": "risk", "2.06": "risk", "3.01": "risk", "4.01": "risk",
            "4.02": "risk", "2.03": "capital", "3.02": "capital", "3.03": "capital", "5.02": "other"}
US_FORMS = {"10-K": "earnings", "10-Q": "earnings", "20-F": "earnings", "40-F": "earnings", "6-K": "other",
            "SC TO-T": "deal", "SC TO-I": "capital", "SC 14D9": "deal", "PREM14A": "deal", "DEFM14A": "deal",
            "S-4": "deal", "NT 10-K": "risk", "NT 10-Q": "risk", "15-12B": "risk", "25-NSE": "risk"}


def classify(market: str, row: dict) -> str:
    """One kind per filing, by rules (KINDS or 'routine'); unmatched non-routine filings are 'other'."""
    if market == "us":
        form = (row.get("form") or "").removesuffix("/A")
        if form == "8-K":
            kinds = [US_ITEMS[i] for i in str(row.get("items") or "").split(",") if i in US_ITEMS]
            return min(kinds, key=list(KINDS).index) if kinds else "routine"
        return US_FORMS.get(form, "routine")
    if re.search(ALARM, row["title"]):
        return "risk"
    if market == "cn":
        return match("cn", row["title"])
    # HK: the title first (A+H issuers' reposts of their A-share filings without the prefix), else HKEX's category
    category = row.get("category") or ""
    if re.search(HK_ROUTINE, category.split(" - ")[0]):
        return "routine"
    kind = match("hk", re.sub(r"^海外監管公告\s*-?\s*", "", row["title"]))
    return match("hk", category) if kind == "other" else kind


def match(market: str, text: str) -> str:
    for kind, pattern in RULES[market]:
        if re.search(pattern, text):
            return kind
    return "other"

