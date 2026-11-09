"""Research stage 11, part 3: the report's words (PLAN.md "The analysis in words"; AGENTS.md rule 2). Four DeepSeek
calls in the shape of TradingAgents and FinRobot: (1) business, industry, moat and management, (2) the bull case and
(3) the bear case, written separately from the same facts and in parallel, so the report isn't one-sided; then (4) the
conclusion, investment points, risks, outlook, catalysts, what would change our view and the two explanations (against
the street, against the screening), given code's rating, target and drivers. The questions are the skills' (the
investment-research masters' questions, investment-checklist's judgment gates, investment-team's roles, industry-research,
management-deep-dive, earnings-review, income-investment, era-alpha, quality-screen's exemption C, news-pulse), ported
as the prompts below.
Every item cites its numbered source lines; a figure is a fact-sheet key ({rev_cagr_5y}) that code fills in. Code drops
an item with an unknown key, a quote (「…」) not verbatim in a source it cites, a rating word of its own, any other figure
not in a source it cites (a year may be any source's or key's), or no source and no key. Its words can't move a number
or the rating, so text injected into a filing or headline can't change a result."""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from dotenv import dotenv_values

from stockreport import quotes
from stockreport.config import CONFIG, ROOT
from stockreport.research import CUR, money, pct, price, times
from stockreport.research.compare import MARGIN_SOURCE

log = logging.getLogger(__name__)
CFG = CONFIG["research_words"]
KEY = re.compile(r"\{([a-z0-9_]+)\}")
QUOTE = re.compile(r"「([^」]+)」")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
N = "零〇一二两三四五六七八九十百千万亿"  # Chinese numerals: a run before a unit, a run of two or more with 十 / 百 / 千 / 万 / 亿, or a
CN_FIGURE = re.compile(rf"[{N}]*[{N[:-2]}][{N}]*(?:%|％|个?百分点|个点|点|成|倍|分之|万元|亿|元|美元|港元)|百分之[{N}]+|"  # fraction word
                       rf"(?=[{N}]{{2}})[{N}]*[十百千万亿][{N}]*|翻番|翻倍|一半|过半|半数")
UNIT_AFTER = re.compile(r"(\{[a-z0-9_]+\})\s*(?:万亿|亿|万)?(?:元|美元|港元)|(\{[a-z0-9_]+\})\s*(?:%|倍)")  # a unit after a key
DATE = re.compile(r"(?:19|20)\d\d-\d\d-\d\d|(?:(?:19|20)\d\d年)?\d{1,2}月\d{1,2}日|(?:19|20)\d\d年\d{1,2}月")
RATING_WORDS = re.compile(r"买入|卖出|增持|减持|强烈推荐|建议(买|卖|持有)")
MODELS = ("会员费", "平台佣金", "高周转薄利", "其他")  # quality-screen's exemption C: the business models it names
SOURCE_NAMES = {"年报": "年报", "业绩公告": "业绩公告", "公告": "公告标题", "新闻": "新闻标题", "研报": "研报标题", "评级变动": "评级变动"}

SHARED = """你是卖方研究员，为一份中文个股研究报告写文字部分。读者不是投资专家：用平实的中文、短句，先说结论，少用术语。
你只能依据下面的材料：「事实表」（程序算好的数字，每个有键名）和「来源」（编号的年报节选、业绩公告、公告标题、新闻标题、研报标题或评级变动）。不用你自己的知识，不推断材料里没有的事；英文来源要译成中文表述。
硬规则（违反的那一条会被程序删除）：
1. 数字只能写成事实表的键名 {键名}，程序会填入带单位的数值（键名后面不要再写单位）。不要自己写数字、百分比、倍数或金额，也不要把事实表里的数值抄出来，也不要自造键名。唯一例外：来源里原样出现的数字可以照写，但这一条的 src 必须包含那条来源的编号。年份可以写。
2. 每一条的 src 列出它依据的来源编号；只依据事实表时 src 写 []，但这一条必须至少用一个 {键名}。
3. 引用公司原话用「」括起，必须从 src 中某条来源逐字复制（至少 6 个字），不改写、不翻译、不拼接。
4. 评级和目标价由程序给出，你不能改变；不写买入、卖出、增持、减持之类的建议词，需要时写 {rating}、{target}。
5. 材料不足时写「材料不足以判断」，不要编造。每条 text 不超过 90 个字。
只输出 JSON。"""

BUSINESS = """任务：公司业务、行业、护城河和管理层（段永平、巴菲特、芒格、李录的追问）。
- business（2-4 条）：一句话说清这门生意的本质：客户是谁、为什么付钱、复购靠什么；主要产品或分部、地区（有分部数据就用）；10 年后大概率还在做什么。
- industry（2-3 条）：行业格局和竞争：主要对手、公司在产业链的位置、行业所处阶段（成长、成熟、调整、下行）；与同行比较用事实表的同行中位数。
- moat（2-3 条）：护城河的来源，只写有证据的（品牌和定价权：能否不掉销量提价；转换成本；网络效应；成本和规模；技术专利），过去几年变宽还是变窄，什么能摧毁它。
- management（1-3 条）：管理层和资本配置：分红、回购、并购、高管或审计师变动、大股东增减持；以前说的事有没有做到；只写来源里的事实。
- model：商业模式若属于「会员费」「平台佣金」「高周转薄利」之一就写这个词，否则写「其他」。
JSON：{"business":[{"text":"","src":[]}],"industry":[{"text":"","src":[]}],"moat":[{"text":"","src":[]}],"management":[{"text":"","src":[]}],"model":""}"""

BULL = """任务：多头观点。你只代表看多的一方（另一位研究员会单独写空头观点，不要替他写）。
写 3 条最有力的看多理由：基本面真实的变化、被低估或被忽视的地方、可能超预期的地方（参考财报前瞻科目、增长质量、同行对比、管理层的计划）。
每条：title 短标题（不超过 14 个字），text 1-3 句，最后一句说明这条理由要成立需要看到什么。
JSON：{"bull":[{"title":"","text":"","src":[]}]}"""

BEAR = """任务：空头观点。你只代表看空的一方（另一位研究员会单独写多头观点，不要替他写）。用芒格的反向思考：这家公司可能失败的路径，聪明人为什么不买。
写 3 条最有力的看空理由：需求或竞争、利润率、财务质量（应收或存货快于收入、现金流低于利润、商誉、股权激励）、治理、现价隐含的假设是否过高。
每条：title 短标题（不超过 14 个字），text 1-3 句，最后一句说明这条担忧落空需要看到什么。
JSON：{"bear":[{"title":"","text":"","src":[]}]}"""

THESIS = """任务：结论页和观点。程序已给出评级 {rating}、目标价 {target}（现价 {price}），预期 12 个月回报 {expected_return}，大盘 {market_return}。
下面附有已核对的业务、多头、空头三部分，以及程序列出的「与市场一致目标价不同的原因」和「与每日筛选的异同」。你的观点要和程序的评级一致，同时公平呈现两方。
- conclusion：一句话结论（不超过 50 个字），写出 {rating}，说清为什么是这个评级。
- points（3 条）：投资要点：你综合多空两方之后支持 {rating} 的理由，每条 title + 1-2 句；不要照抄多头或空头的条目。
- risks（3 条）：评级的风险：可能让 {rating} 出错的事（{rating} 为卖出时多是上行风险），每条 title + 1-2 句；不要照抄空头的条目。
- outlook（2-3 条）：未来 1-3 年的展望；管理层的计划用「」引用原话。
- catalysts（2-4 条）：接下来可能影响股价的事件和时间（财报、分红、解禁、产品、政策），只写材料里有的。
- change_view（2-3 条）：什么会让我们改变看法：可观察、可证伪的信号，每条写出要看的指标的键名（如 {latest_rev_growth}）和方向。
- vs_street：2-4 句，先写出差距（{target} 对 {street_target}，{ours_vs_street}），再解释为什么不同，只用列出的原因和它们的键名。
- vs_screening：1-3 句，解释研究评级和每日筛选为什么一致或不同，只用列出的原因和键名；没有列出原因时说明两者一致。
- moves：近 90 天有大涨大跌时 1-2 条，日期和涨幅写键名（news-pulse：价值事件、情绪波动、真因不明或混合），只用来源，找不到原因就写真因不明；没有异动时为空列表。
JSON：{"conclusion":{"text":"","src":[]},"points":[{"title":"","text":"","src":[]}],"risks":[{"title":"","text":"","src":[]}],"outlook":[{"text":"","src":[]}],"catalysts":[{"text":"","src":[]}],"change_view":[{"text":"","src":[]}],"vs_street":{"text":"","src":[]},"vs_screening":{"text":"","src":[]},"moves":[{"text":"","src":[]}]}"""


def keys(f: dict, v: dict, extra: dict) -> dict[str, tuple[str, str]]:
    """The fact sheet as DeepSeek reads it: key -> (label, the value as shown), from facts.json and valuation.json;
    keys without a value are left out."""
    val, s, c, ck, k = f["valuation"], f["summary"], f["consensus"], f["checks"], v.get("inputs") or {}
    q, r = v["currency"], k.get("currency") or val["report_currency"]
    st, rev = v.get("street") or {}, v.get("reverse") or {}
    need, br = st.get("implied") or {}, (v.get("base_rates") or {}).get("share_at_least") or {}
    m = v.get("methods") or {}
    d, er, own = m.get("dcf") or m.get("dcf_normal") or {}, m.get("excess_return") or {}, val.get("own_history") or {}
    lt, px, inc = f.get("latest") or {}, f["price"], ck.get("income") or {}
    ratio = lambda a, b: a / b - 1 if a is not None and b else None
    ratings = st.get("ratings") or {}
    n_rated = sum(x or 0 for x in ratings.values())
    bullish = sum(ratings.get(x) or 0 for x in ("buy", "add", "strongBuy"))
    seg = [x for x in f.get("segments") or [] if x["by"] == "product" and x["period"] == max(y["period"] for y in f["segments"])]
    top = max(seg, key=lambda x: x.get("share") or 0, default=None)
    out = {
        "name": ("公司", f["name"]), "industry": ("行业", f.get("industry")),
        "rating": ("我们的评级", v["rating"]), "target": ("12 个月目标价", price(v.get("target"), q)),
        "price": ("现价", price(v["price"], q)),
        "upside": ("目标价相对现价", pct(ratio(v.get("target"), v["price"]), True)),
        "expected_return": ("预期 12 个月回报（含股息）", pct(v.get("expected_return"), True)),
        "market_return": ("大盘预期 12 个月回报", pct(v.get("market_return"))),
        "excess_return": ("预期超额回报", pct(v.get("excess_return"), True)),
        "band": ("评级门槛（估值不确定性）", "±" + pct((v.get("uncertainty") or {}).get("band"), digits=0) if v.get("uncertainty") else None),
        "bear": ("悲观情景价值", price(v.get("bear"), q)), "bull": ("乐观情景价值", price(v.get("bull"), q)),
        "street_target": ("市场一致目标价", price(st.get("target"), q)),
        "street_upside": ("市场目标价相对现价", pct(st.get("upside"), True)),
        "ours_vs_street": ("我们的目标价相对市场目标价", pct(st.get("ours_vs_street"), True)),
        "street_rated": ("给出评级的卖方机构数", f"{n_rated:g}" if n_rated else None),
        "street_bullish": ("其中看多（买入或增持）的机构数", f"{bullish:g}" if n_rated else None),
        "analysts": ("覆盖的分析师人数", f"{c['analysts']:g}" if c.get("analysts") else None),
        "wacc": ("我们用的资本成本", pct(k.get("wacc"))), "cost_equity": ("股权成本", pct(k.get("cost_equity"))),
        "capm_cost_equity": ("CAPM 算出的股权成本", pct((k.get("floor") or {}).get("cost_equity_capm"))),
        "rf": ("无风险利率", pct(k.get("rf"), digits=2)), "erp": ("股权风险溢价", pct(k.get("erp"), digits=2)),
        "beta": ("贝塔", f"{k['beta']:.2f}" if k.get("beta") is not None else None), "g": ("永续增长率", pct(k.get("g"))),
        "implied_wacc": ("现价隐含的资本成本", pct(rev.get("implied_wacc"))),
        "implied_growth": ("现价隐含的未来 5 年营收年增长", pct(rev.get("implied_growth_5y"), True)),
        "implied_margin": ("现价隐含的长期营业利润率", pct(rev.get("implied_margin"))),
        "implied_roe": ("现价隐含的长期 ROE", pct(rev.get("implied_roe"))),
        "implied_coe": ("现价隐含的股权成本", pct(rev.get("implied_cost_equity"))),
        "implied_div_growth": ("现价隐含的未来 5 年股息年增长", pct(rev.get("implied_dividend_growth_5y"), True)),
        "street_wacc": ("市场目标价相当于的资本成本", pct(need.get("implied_wacc"))),
        "street_growth": ("市场目标价需要的 5 年营收年增长", pct(need.get("implied_growth_5y"), True)),
        "street_margin": ("市场目标价需要的长期营业利润率", pct(need.get("implied_margin"))),
        "street_roe": ("市场目标价对应的长期 ROE", pct(need.get("implied_roe"))),
        "forecast_growth": ("我们预测的未来 5 年营收年增长", pct(v.get("forecast_growth_5y"), True)),
        "base_forecast": ("同等规模公司中 5 年做到我们预测增长的比例（越低越难）", pct(br.get("forecast"), digits=0)),
        "base_implied": ("同等规模公司中 5 年做到现价隐含增长的比例（越低越难）", pct(br.get("implied"), digits=0)),
        "base_street": ("同等规模公司中 5 年做到市场目标价所需增长的比例（越低越难）", pct(br.get("street"), digits=0)),
        "target_margin": ("我们假设的长期营业利润率", pct((d.get("path") or {}).get("target_margin"))),
        "margin_source": ("长期利润率的依据", MARGIN_SOURCE.get((d.get("path") or {}).get("margin_source"))),
        "roe_term": ("我们假设的长期 ROE", pct(er.get("roe_term"))),
        "market_cap": ("市值", money(val["market_cap"], q)), "pe_ttm": ("市盈率（过去 12 个月）", times(val.get("pe_ttm"))),
        "pe_fwd": ("市盈率（未来 12 个月一致预期）", times(val.get("pe_fwd"))), "pb": ("市净率", times(val.get("pb"))),
        "ps": ("市销率", times(val.get("ps"))), "ev_ebit": ("企业价值 / 息税前利润", times(val.get("ev_ebit"))),
        "div_yield": ("股息率（过去 12 个月）", pct(val.get("div_yield"))), "fcf_yield": ("自由现金流收益率", pct(val.get("fcf_yield"))),
        "pe_own": ("自身近 5 年市盈率中位数", times((own.get("pe") or {}).get("median_5y"))),
        "pb_own": ("自身近 5 年市净率中位数", times((own.get("pb") or {}).get("median_5y"))),
        "high_52w": ("52 周最高", price(px.get("high_52w"), q)), "low_52w": ("52 周最低", price(px.get("low_52w"), q)),
        "ret_12m": ("近 12 个月股价涨跌", pct(px.get("ret_12m"), True)), "rel_12m": ("近 12 个月相对大盘", pct(px.get("rel_12m"), True)),
        "ret_3m": ("近 3 个月股价涨跌", pct(px.get("ret_3m"), True)), "vol_1y": ("年化波动率", pct(px.get("vol_1y"), digits=0)),
        "fy_latest": ("最新财年", s["fy_latest"][:4] + " 年"),
        "rev_cagr_3y": ("近 3 年营收年均增长", pct(s.get("rev_cagr_3y"), True)), "rev_cagr_5y": ("近 5 年营收年均增长", pct(s.get("rev_cagr_5y"), True)),
        "rev_cagr_10y": ("近 10 年营收年均增长", pct(s.get("rev_cagr_10y"), True)), "ni_cagr_5y": ("近 5 年净利润年均增长", pct(s.get("ni_cagr_5y"), True)),
        "roe_latest": ("最新财年 ROE", pct(s.get("roe_latest"))), "roe_5y": ("近 5 年平均 ROE", pct(s.get("roe_avg_5y"))),
        "gross_margin_5y": ("近 5 年平均毛利率", pct(s.get("gross_margin_avg_5y"))), "net_margin_5y": ("近 5 年平均净利率", pct(s.get("net_margin_avg_5y"))),
        "cash_conversion": ("近 5 年经营现金流 / 净利润", pct(s.get("ocf_to_profit_5y"), digits=0)),
        "net_debt_ebitda": ("净负债 / EBITDA", times(s.get("net_debt_to_ebitda"))),
        "sbc_to_revenue": ("股权激励占营收", pct(s.get("sbc_to_revenue"))),
        "revenue_ttm": ("过去 12 个月营收", money(val["ttm"].get("revenue"), r)), "ni_ttm": ("过去 12 个月净利润", money(val["ttm"].get("ni"), r)),
        "latest_period": ("最新一期报告", f"{lt['period']}（{ {'year to date': '年初至今', 'TTM': '过去 12 个月'}.get(lt.get('basis'), lt.get('basis') or '')}）" if lt.get("period") else None),
        "latest_rev_growth": ("最新一期营收同比", pct(ratio(lt.get("revenue"), lt.get("revenue_prior")), True)),
        "latest_ni_growth": ("最新一期净利润同比", pct(ratio(lt.get("ni"), lt.get("ni_prior")), True)),
        "m_score": ("Beneish M 值", f"{ck['beneish']['m_score']:.2f}" if (ck.get("beneish") or {}).get("m_score") is not None else None),
        "f_score": ("Piotroski F 值", f"{ck['piotroski']['f_score']}/{ck['piotroski']['signals_known']}" if ck.get("piotroski") else None),
        "z2": ("Altman Z'' 值", f"{ck['altman']['z2']:.1f}" if (ck.get("altman") or {}).get("z2") is not None else None),
        "quality_screen": ("去劣筛选", {"pass": "通过", "fail": "未通过"}.get((ck.get("quality_screen") or {}).get("result"))),
        "checklist_stars": ("好生意五项的星数（满分 5）", f"{ck['checklist']['stars']}" if (ck.get("checklist") or {}).get("stars") is not None else None),
        "dps_cagr_5y": ("近 5 年每股股息年均增长", pct(inc.get("dps_cagr_5y"), True)), "payout": ("派息率", pct(inc.get("payout"), digits=0)),
        "div_raises": ("提高股息的年数", f"{inc['raises']}" if inc.get("raises") is not None else None),
        "div_cuts": ("削减股息的年数", f"{inc['cuts']}" if inc.get("cuts") is not None else None),
        "yield_avg_5y": ("近 5 年平均股息率", pct(inc.get("yield_avg_5y"))),
        "eps_growth_consensus": ("一致预期的每股收益年增长", pct(val.get("eps_growth_consensus"), True)),
        "top_segment": ("最大的产品分部", top["item"] if top and top.get("share") else None),
        "top_segment_share": ("最大产品分部的收入占比", pct(top.get("share"), digits=0) if top else None),
        "next_earnings": ("下次财报日", (c.get("next_earnings") or [None])[0]),
        "upgrades_6m": ("近 6 个月上调评级的次数", f"{c['upgrades_6m']}" if c.get("upgrades_6m") is not None else None),
        "downgrades_6m": ("近 6 个月下调评级的次数", f"{c['downgrades_6m']}" if c.get("downgrades_6m") is not None else None),
        "target_hit_rate": ("卖方目标价 12 个月内达到的比例", "约四成"),
    }
    out |= extra
    return {key: x for key, x in out.items() if x[1] not in (None, "-", "", "±-")}


def numbered(lines: list[dict]) -> str:
    return "\n".join(f"[{i}] {x['date'] or ''} {SOURCE_NAMES[x['type']]}" + (f"（{x['part']}）" if x.get("part") else "") + f"：{x['text']}"
                     for i, x in enumerate(lines, 1))


def fact_block(k: dict) -> str:
    return "\n".join(f"{{{key}}} {label}：{value}" for key, (label, value) in k.items())


def check(text: str, cites, k: dict, lines: list[dict], years: set) -> str | None:
    """Why an item can't be shown (None when it can): rule 2's checks on its text and its cited sources."""
    text = " ".join(str(text or "").split()).replace("{{", "{").replace("}}", "}")
    if not text:
        return "empty"
    if unknown := [x for x in KEY.findall(text) if x not in k]:
        return f"unknown key {unknown[0]}"
    src = [lines[i - 1]["text"] for i in cites or [] if isinstance(i, int) and 1 <= i <= len(lines)]
    full = quotes.norm(" ".join(src)).replace(",", "")
    for q in quoted(text):  # verbatim in a source line (code adds the line to the item's sources)
        if not any(quotes.norm(q) in quotes.norm(x["text"]) for x in lines):
            return f"quote not in a source: {q[:30]}"
    bare = KEY.sub(" ", QUOTE.sub(lambda m: " " if m.group(1) in quoted(text) else m.group(0),
                                  UNIT_AFTER.sub(lambda m: m.group(1) or m.group(2), text)))
    bare = DATE.sub(lambda m: " " if quotes.norm(m.group(0)) in years else m.group(0), bare)  # a date the material has
    if RATING_WORDS.search(bare.replace(k["rating"][1], "") if "rating" in k else bare):  # code's own rating may be named
        return "rating word"
    spans = [(m.group(0), bare[m.end():m.end() + 3]) for m in NUMBER.finditer(bare)] + [(x, "") for x in CN_FIGURE.findall(bare)]
    for n, after in spans:
        token = quotes.norm(n).replace(",", "")
        if re.fullmatch(r"(19|20)\d\d", token) and token in years:
            continue
        if re.match(r"\s*(年|个月)", after) and token in horizons(k):  # 近 5 年, 12 个月: the keys' own horizons
            continue
        if not re.search(rf"(?<![\d.]){re.escape(token)}(?!\.?\d)", full):
            return f"figure not in a cited source: {n}"
    if not src and not KEY.search(text) and not quoted(text):
        return "no source and no key"
    return contradicts(text, k)


HIGHER = re.compile(r"(远|明显|显著)?(高于|超过|大于|高出)")
LOWER = re.compile(r"(远|明显|显著)?(低于|小于|不及|落后于)")


def value_of(shown: str) -> float | None:
    """The number in a key's shown value (+11.9% -> 11.9, 22.1倍 -> 22.1, 1,453.00元 -> 1453), None for text."""
    m = re.fullmatch(r"\s*([+-]?[\d,]+(?:\.\d+)?)\s*(%|倍|万亿|亿)?.*", shown or "")
    if not m:
        return None
    return float(m.group(1).replace(",", "")) * {"万亿": 1e12, "亿": 1e8}.get(m.group(2), 1)


def contradicts(text: str, k: dict) -> str | None:
    """A comparison between two keys that their values contradict ({a} 高于 {b} while a < b): the words can't be
    checked for meaning, but a direction between two of code's figures can."""
    for clause in re.split(r"[。；;！？]", text):
        found = [(m.start(), m.group(1)) for m in KEY.finditer(clause)]
        for (i, a), (j, b) in zip(found, found[1:]):
            between = clause[i:j]
            x, y = value_of(k[a][1]), value_of(k[b][1])
            if x is None or y is None or not (HIGHER.search(between) or LOWER.search(between)):
                continue
            ma, mb = (re.search(r"市盈率|市净率|市销率|股息率|ROE|利润率|增长|资本成本|股权成本", k[key][0]) for key in (a, b))
            if ma and mb and ma.group(0) != mb.group(0):
                return f"compares different measures: {k[a][0]} vs {k[b][0]}"
            if HIGHER.search(between) and x <= y or LOWER.search(between) and x >= y:
                return f"comparison contradicts the figures: {a} {k[a][1]} vs {b} {k[b][1]}"
    return None


def quoted(text: str) -> list[str]:
    """The quotes to check verbatim: 「…」 of at least MIN_QUOTE characters (a shorter one is a term, read as words)."""
    return [q for q in QUOTE.findall(text) if len(quotes.norm(q)) >= quotes.MIN_QUOTE]


def material_dates(lines: list[dict], k: dict) -> set[str]:
    """The years and dates the material has (sources and keys): written, they aren't figures to check."""
    text = " ".join(f"{x['text']} {x['date'] or ''}" for x in lines) + " " + " ".join(x[1] for x in k.values())
    out = set(re.findall(r"(?:19|20)\d\d", text)) | {quotes.norm(d) for d in DATE.findall(text)}
    for d in re.findall(r"(?:19|20)\d\d-(\d\d)-(\d\d)", text):  # 2026-11-05 is also 11月5日
        out.add(f"{int(d[0])}月{int(d[1])}日")
    return out


def horizons(k: dict) -> set[str]:
    return {x for label, _ in k.values() for x in re.findall(r"(\d+)\s*(?:年|个月)", label)}


def fill(text: str, k: dict) -> str:
    """The keys' values in place (each carries its unit, so a unit written after a key is dropped)."""
    text = " ".join(str(text).split()).replace("{{", "{").replace("}}", "}")
    text = UNIT_AFTER.sub(lambda m: m.group(1) or m.group(2), text)
    out, at = "", 0
    for m in KEY.finditer(text):  # a word the value ends with isn't written twice (42 家中 39 家看多 + 看多)
        value = k[m.group(1)][1]
        tails = [value[-n:] for n in range(min(4, len(value)), 1, -1)] + ([value[-1]] if value[-1:] in "元倍%位家年次星个" else [])
        tail = next((t for t in tails if not re.search(r"\d", t) and text.startswith(t, m.end())), "")
        out += text[at:m.start()] + value
        at = m.end() + len(tail)
    return out + text[at:]


def verify(answer: dict, k: dict, lines: list[dict], years: set, log_to: list) -> dict:
    """The answer's items that pass check(), each {title?, text (filled), raw (with keys), src}; dropped ones logged."""
    out = {}
    for field, items in answer.items():
        if isinstance(items, str):  # only the business model's word is a bare string; any other string is dropped
            if field == "model" and items in MODELS:
                out[field] = items
            elif items:
                log_to.append({"field": field, "why": "not an item", "text": items})
            continue
        single = isinstance(items, dict)
        kept = []
        for it in [items] if single else items or []:
            if not isinstance(it, dict):
                continue
            joined = f"{it.get('title') or ''} {it.get('text') or ''}".strip()
            why = check(joined, it.get("src"), k, lines, years)
            if why:
                log_to.append({"field": field, "why": why, "text": joined})
                continue
            src = [i for i in it.get("src") or [] if isinstance(i, int) and 1 <= i <= len(lines)]
            for q in quoted(joined):  # a quote's own line
                at = next(i for i, x in enumerate(lines, 1) if quotes.norm(q) in quotes.norm(x["text"]))
                src += [at] if at not in src else []
            kept.append({"title": fill(it.get("title") or "", k), "text": fill(it.get("text") or "", k), "src": src,
                         "raw": joined})
        out[field] = (kept[0] if kept else None) if single else kept
    return out


REPAIR = """下面这些条目被程序删除了，原因附后（figure：写了来源里没有的数字，改用键名，或在 src 里引用含这个数字的来源；no source and no key：
没有来源也没有键名，补上 src 或用键名；quote：引文不是来源原文；rating word：写了建议词；comparison / measures：比较的方向和数字不符，或比较了不同的指标）。
按同样的规则重写这些条目（站不住的内容可以删掉），只输出这些字段，JSON 结构不变。
被删除的条目：
{items}"""


def ask_checked(client, task: str, material: str, k: dict, lines: list[dict], years: set, dropped: list) -> dict:
    """One call, checked; the items code drops go back once with their reasons, and the rewrites are checked again."""
    first, out = [], None
    out = verify(client.ask(SHARED, task + "\n\n" + material), k, lines, years, first)
    if not first:
        return out
    items = "\n".join(f"- {d['field']}：{d['text']}（原因：{d['why']}）" for d in first)
    again = verify(client.ask(SHARED, task + "\n\n" + material + "\n\n" + REPAIR.format(items=items)), k, lines, years, dropped)
    for field in {d["field"] for d in first}:
        got, have = again.get(field), out.get(field)
        if isinstance(have, list) and isinstance(got, list):  # up to the count asked for, no repeated title or text
            seen = {x["raw"] for x in have} | {x["title"] for x in have if x["title"]}
            more = [x for x in got if x["raw"] not in seen and not (x["title"] and x["title"] in seen)]
            out[field] = (have + more)[:3 if field in ("points", "risks", "bull", "bear") else 4]
        elif have is None and isinstance(got, dict):
            out[field] = got
    return out


class Client:
    """DeepSeek's chat API with the usage of every call counted (tokens, seconds)."""

    def __init__(self, model: str):
        key = dotenv_values(ROOT / ".env").get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("DEEPSEEK_API_KEY is missing from .env")
        self.model, self.calls = model, []
        self.http = httpx.Client(base_url=CONFIG["notes"]["base_url"], timeout=CFG["timeout"],
                                 headers={"Authorization": f"Bearer {key}"})

    def ask(self, system: str, user: str) -> dict:
        err = None
        for _ in (1, 2):
            started = time.monotonic()
            try:
                resp = self.http.post("/chat/completions", json={
                    "model": self.model, "temperature": CFG["temperature"], "thinking": {"type": "disabled"},
                    "response_format": {"type": "json_object"}, "max_tokens": CFG["max_tokens"],
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                resp.raise_for_status()
                body = resp.json()
                u = body.get("usage") or {}
                self.calls.append({"seconds": time.monotonic() - started, "hit": u.get("prompt_cache_hit_tokens", 0),
                                   "miss": u.get("prompt_cache_miss_tokens", u.get("prompt_tokens", 0)),
                                   "out": u.get("completion_tokens", 0)})
                text = body["choices"][0]["message"]["content"].strip().removeprefix("```json").removesuffix("```")
                if isinstance(answer := json.loads(text), dict):
                    return answer
                err = ValueError("not a JSON object")
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
                err = e
        raise RuntimeError(f"DeepSeek failed: {type(err).__name__}: {err}")

    def cost(self) -> dict:
        """Tokens and the cost in USD at the peak price (off-peak is half)."""
        p = CFG["prices"][self.model]
        hit, miss, out = (sum(c[x] for c in self.calls) for x in ("hit", "miss", "out"))
        return {"model": self.model, "calls": len(self.calls), "input_tokens": hit + miss, "output_tokens": out,
                "usd": (hit * p[0] + miss * p[1] + out * p[2]) / 1e6, "seconds": [round(c["seconds"], 1) for c in self.calls]}


def write(f: dict, v: dict, lines: list[dict], extra: dict, street: list[str], screen: dict, model: str | None = None) -> dict:
    """The four calls, checked: {business, industry, moat, management, model, bull, bear, conclusion, points, risks,
    outlook, catalysts, change_view, vs_street, vs_screening, moves, dropped, usage}; status 'unavailable' when
    DeepSeek can't be reached (the report then goes out with its numbers and these sections marked 暂不可用)."""
    k = keys(f, v, extra)
    moves = {f"move{i}": ("近 90 天的异动", f"{m['date']} 单日 {pct(m['move'], True)}（大盘 {pct(m['index'], True)}）")
             for i, m in enumerate(f["price"].get("moves_90d") or [], 1)}
    k |= moves
    years = material_dates(lines, k)
    material = f"事实表：\n{fact_block(k)}\n\n来源：\n{numbered(lines) or '（无）'}"
    dropped, out = [], {"status": "done"}
    try:
        client = Client(model or CFG["model"])
        with ThreadPoolExecutor(3) as pool:
            for got in pool.map(lambda task: ask_checked(client, task, material, k, lines, years, dropped), (BUSINESS, BULL, BEAR)):
                out |= got
        done = lambda field: "\n".join(f"- {x['raw']}" for x in out.get(field) or []) or "（无）"
        drivers = lambda items: "\n".join(f"- {x}" for x in items if all(y in k for y in KEY.findall(x))) or "（无）"
        moves = "、".join(f"{{{x}}}" for x in moves)
        context = (f"已核对的业务：\n{done('business')}\n{done('industry')}\n{done('moat')}\n多头：\n{done('bull')}\n空头：\n{done('bear')}\n\n"
                   f"与市场一致目标价不同的原因：\n{drivers(street)}\n\n与每日筛选：{screen.get('agreement') or '无法比较'}"
                   f"（筛选的看法 {{scr_view}}）\n{drivers(screen.get('drivers') or [])}\n\n近 90 天异动：{moves or '无'}")
        out |= ask_checked(client, THESIS, context + "\n\n" + material, k, lines, years, dropped)
        out["usage"] = client.cost()
    except Exception as e:
        log.warning("%s words: %s", f["code"], e)
        out = {"status": "unavailable", "error": str(e)}
    out["dropped"] = dropped
    if dropped:
        log.info("%s words: %d items dropped after the repair round: %s", f["code"], len(dropped),
                 "; ".join(f"{d['field']}: {d['why']}" for d in dropped))
    out["drivers_street"] = [fill(x, k) for x in street if all(y in k for y in KEY.findall(x))]
    out["drivers_screen"] = [fill(x, k) for x in screen.get("drivers") or [] if all(y in k for y in KEY.findall(x))]
    return out
