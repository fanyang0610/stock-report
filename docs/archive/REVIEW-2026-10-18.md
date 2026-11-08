# Self-review and valuation v2 proposal (rev. 4, 2026-10-18)

Rev. 1 (2026-10-17) reviewed the project and proposed guardrails on the peer method. You answered the six decisions
and asked for a deeper valuation method. Part A is that proposal: method, evidence, deep-dive lane, backtest and plan.
Part B keeps the rev. 1 findings, which still describe the method in production today.

Rev. 3 adds three points from our discussion: regime-aware history for stocks whose economics changed, such as AI
winners and AI-disrupted businesses (A2.7); an event layer that judges whether news is noise or a value driver (A2.8);
and the bucket names 买入 / 持有 / 卖出 (Buy / Hold / Sell).

Rev. 4 replaces "show two values and the market's probability" with a committed estimate. The method estimates its own
probability that a new regime lasts, from measured base rates plus evidence. It values the stock at the
probability-weighted value, makes one call, and publishes its own track record (A2.7, A2.5).

The evidence in A2.6 comes from a working prototype run on the 2026-10-17 snapshots, plus free multi-year history it
downloaded: SEC 10-K history, Eastmoney CN annual results and valuation history, HK results since 2015, and 10 years of
Yahoo monthly prices. Everything went to my scratchpad; the project's data/, reports/ and launchd were not touched. The
scripts are in the shared notes folder (`review-sims/v2/`). The prototype is a demonstration, not a finished method:
its thresholds and weights are first guesses, which Phase 9 replaces with backtested values.

---

## A0. Your decisions and what they change

| | Your answer | Effect on this proposal |
|---|---|---|
| D1 | Line budget can grow; usefulness first | Proposed new soft target: ~6,000 app lines, files still under 400 lines (rule 6 text, A7) |
| D2 | No shrinking, no renaming; make the value itself useful | Fair value becomes an **intrinsic value from a cash-flow model**, not a peer residual. Next to it go the **expected annual return** at today's price, **what the price implies**, and later a **backtested 12-month expectation with its hit rate** (A2.5) |
| D3 | Deep research where the rules see something "unreal", balanced against cost | A **bounded deep-dive lane** (A3): rule-triggered, at most 3 stocks per market per day, evidence quoted from filings and checked by code, plus optional manual verdicts |
| D4 | Add free, good-quality sources as I see fit | Used in the prototype: SEC companyfacts history, Eastmoney 业绩报表 history with **扣非 EPS** (`DEDUCT_BASIC_EPS`, verified), Eastmoney valuation history (verified back to 2018-12), HK main indicators since 2015, Yahoo monthly prices and splits. Later: 申万 classification, Tencent quotes, the Eastmoney research-report archive (A4) |
| D5 | Backtest in scope | It calibrates every judgment parameter of v2 and decides whether v2 replaces v1 (Phase 9) |
| D6 | Build in a separate worktree, away from launchd, data/, reports/ | Phase 7 and later phases are built in a worktree. v2 runs in shadow mode next to v1 until the backtest says switch |

## A1. Summary

1. **Value each stock on its own earnings power, not only relative to peers.** Use a three-stage residual-income model
   (book value plus discounted excess profits): consensus EPS for years 1-3; a 10-year fade to a long-run ROE; a
   terminal value with r − g ≥ 3 points. Residual income suits a universe-wide method: it starts from book value,
   needs only ROE, growth and payout, and handles banks and insurers natively.
2. **Normalize earnings with data.** Each stock gets a weight on its own 10-year history versus today. The weight is set
   by how volatile its ROE has been and whether revenue has fallen in some years. Cyclicals at a peak are valued on
   through-cycle ROE. Fast growers whose early years lost money are valued on today and consensus. ROE reverts
   **upward** only with evidence of a cycle. A steady 5-year decline that analysts don't expect to reverse is treated
   as structural, not a trough.
3. **Regime breaks, such as AI, get a committed estimate, not a menu.** A data test compares the last 3 years with
   the 7 before and asks whether analysts confirm the new level. For a confirmed break the method estimates **its
   own** probability that the new regime lasts.
   - **Base rate:** measured in our 10-year panel. After an ROE jump, 47% of US companies and only 12% of A-shares kept
     at least half of it 3 years later.
   - **Adjusted by evidence:** the company's own past booms, how durable consensus is, inventory against sales,
     backlog, the capex of the largest AI spenders.
   - **Result:** the stock is valued at the probability-weighted value and gets one call like any other. The market's
     implied probability appears only as the reason for the call ("我们 40%，市场隐含 50% → 高估").
4. **News is judged by whether it moves a value driver.** An event layer reads market-wide announcement feeds daily.
   Events with numbers (pre-announcements, contracts, buybacks, placements) update the inputs. Risk events lower
   confidence or veto a pick. Stories without numbers leave the value unchanged. A big price move with no matching
   news is treated as probably noise.
5. **Growth must be paid for.** Book value grows at a sustainable rate that fades from consensus growth to long-run GDP
   growth; earnings above what that growth needs are paid out. Without this, high-ROE companies compound forever. The
   first prototype run valued NVDA at 5,466.
6. **Every stock gets three answers.** What it's worth (intrinsic value at its required return); what it returns at
   today's price (expected annual return); what the price assumes ("the price needs ROE X% for 10 years; its 10-year
   average is Y%; analysts expect Z%").
7. **Triangulate.** Intrinsic value is combined with a repaired peer value and the stock's own-history multiple, with
   weights by archetype. How far apart they are, together with data depth, analyst coverage, the quality gate and
   agreement with consensus, sets the confidence (高/中/低). The backtest turns that into a measured hit rate, and the
   report shows its own track record on page 1. Confidence says how often calls like this were right; it never
   replaces the call.
8. **Buckets by evidence, named 买入 / 持有 / 卖出 (Buy / Hold / Sell).** A buy needs upside, expected return above
   the required return, an agreeing confidence level and the quality-screen gate. A sell needs a large negative gap
   **and** deterioration (falling momentum or profits, or a quality failure), so the method doesn't short strong
   growth stocks on valuation alone. Pre-profit companies get no value and no buy or sell call.
9. **Prototype, today's problem names:** MU +251% → −39%, flagged low confidence. 天齐锂业 +304% → +80%. The P/S biotech
   sells (−82% to −97%) → no call. NVDA +34% and MSFT +48% with the anchors agreeing. Growth priced for perfection
   (PLTR, TSLA, 寒武纪) shows as expensive but low confidence, so no sell without deterioration.
10. **What v2 doesn't solve alone:** value traps that data and consensus can't see, where the market prices
    disruption or governance (Omnicom, Cognizant, 格力 at +90-125% in the prototype). The discount rate is the biggest
    lever behind those numbers. Answers: backtest calibration of the required return and of how much of a gap tends to
    close; a confidence penalty when the market disagrees strongly; a committed persistence probability where a
    regime break is detected; and the deep-dive lane.
11. **Deep-dive lane:** about 9 deep dives a day at most, in the 06:30 build, never in the 30 s keyword reply.
    DeepSeek pulls quoted facts from the latest filing; code checks each quote against the text and computes the
    numbers: one-off items, listed stakes for a sum-of-the-parts value, insurers' embedded value, landlords'
    underlying profit, deal terms, audit and going-concern vetoes. This needs rule 2 and 3 amendments and one
    dependency (pypdf); A7 has the text.
12. **Plan:** Phase 7 history data, bug fixes and the bucket rename (worktree) → 8 the v2 engine, including the regime
    test and the persistence probability, in shadow mode → 9 backtest and calibration, including the news test, plus live
    signal tracking → 10 switch the report to v2 with phone-first cards → 11 deep-dive lane and event layer → 12 data
    cross-checks.

---

## A2. Valuation v2: the method

### A2.1 Why the peer method can't be repaired into a value
Rev. 1 (B2) showed that today's fair value is the residual of a cross-sectional fit with median R² 0.43-0.59. Peer
comparison can't answer "is the whole group mispriced?" (US semiconductors at a median P/E of 45; Chinese insurers at
P/E 6). It also can't see cycle position. Its residual mixes real mispricing with everything the fit doesn't see. The
guardrails in rev. 1 would have made it safer, but every pick would have read "low conviction", which is your point. v2
keeps peers as one cross-check and builds the value from each company's own economics.

### A2.2 The engine, step by step (all rule-based, all stocks, seconds per market)

**1. Earnings base.** Core earnings, meaning one-offs are stripped wherever the data allows: CN TTM on 扣非 EPS; US on
continuing operations, with book value net of preferred equity. Current ROE = the median of TTM ROE and the two
consensus years on today's book, which is robust to one-offs (HON's spin-off gain drops out).

**2. History and archetype.**
- 10-year history per company: ROE, margins, OCF/NI, free cash flow, share count, revenue down-years, and the 5-year
  ROE trend.
- Weight on history: w = f(ROE volatility relative to its level) × cycle factor. The cycle factor is 1.0 if revenue
  fell in 2+ of 10 years or no growth is expected; 0.3 for a grower with at most one down year and ≥15% expected
  growth; 0.6 otherwise.
- Normal ROE = w × history + (1 − w) × today. Below its history, ROE reverts upward only with past dips, no steady
  5-year decline and analysts' year-3 ROE at least halfway back; otherwise today's level or consensus stands.
- Regime test (A2.7): where the last 3 years broke from the 7 before and analysts confirm the new level, the history
  window shrinks to the post-break years, and the stock gets a persistence probability and a probability-weighted
  value.
- Archetype labels (financial / cyclical / growth / steady / pre-profit) are for display and for anchor weights.

**3. Three-stage residual income.**
- Years 1-3: consensus EPS when 3+ analysts cover the stock. For volatile earners it is haircut toward the normal path,
  by 10%, 25% and 50% for years 1, 2 and 3 at full weight. Otherwise the ROE path runs from today toward normal.
- Years 4-13: ROE fades to a long-run level, r + φ × (normal ROE − r). φ, the persistence of excess returns, comes from
  ROE stability and gross margin; Phase 9 estimates it from the history panel instead.
- Book value grows at a sustainable rate that fades from consensus growth (capped at 15%) to long-run nominal growth:
  US 4%, CN and HK 3%.
- Terminal value: the excess return as a growing perpetuity, with r − g of at least 3 points (the terminal_value.py
  discipline).

**4. Required return.** r = the market's implied return plus λ × the industry's implied premium. The market's implied
return is the median expected return of well-covered stocks. Phase 9 calibrates λ (prior 0.5). With λ = 0 every sector
is held to the market's return, which is the justified-P/B problem behind insurers at +200-316%; with λ = 1 the method
is relative within sectors again.
- Today the implied market return is US 6.9% (config 10.1%), HK 10.0% (10.0%), CN 6.4% (7.65%).
- Whether to use the implied or the configured return is a real choice (A7). Implied means the median stock is fairly
  valued and no market-wide call is made; configured means whole markets can look cheap or dear.

**5. Outputs per stock.** Intrinsic value at r; expected annual return at today's price (the implied cost of capital,
as in Gebhardt-Lee-Swaminathan 2001, whose model this engine resembles); and implied ROE, the constant ROE over 10
years that justifies today's price.

**6. Anchors.**
- Peer value: the current regression, repaired with normal ROE, expected growth, at least 15 members, parent-sector
  merges and bounded regressors.
- Own history: the stock's 7-year median P/B × today's book. This matters most for cyclicals: MU's own median P/B is
  2.1 against 7.2 today.
- Weights in log space: steady 0.6 / 0.3 / 0.1 (intrinsic / peer / own); cyclical 0.5 / 0.1 / 0.4; financial 0.55 /
  0.3 / 0.15. Phase 9 calibrates them.

**7. Confidence.** The confidence score counts: anchor agreement (dispersion of the three in log terms); history depth;
analyst coverage; archetype; the quality gate; whether the model's normal ROE agrees with analysts' year-3 ROE; and
whether the market disagrees by more than 2×. Phase 9 replaces the points with measured hit rates.

**8. Quality gate** (quality-screen rules, market-wide, buy and hold only):
- 10-year ROE < 8%, with exemption A (young company, gross margin > 30%, positive OCF)
- 5-year OCF/NI < 0.7
- 5-year free cash flow < 0
- long-run net margin < 5%, with exemptions B and C
- share count +20% in 5 years: a flag only
- banks, insurers and brokers are judged on ROE only

### A2.3 Buckets v2: 买入 / 持有 / 卖出 (always 5 per cell, rule 4)
- **买入 Buy:** combined upside ≥ 20%, expected return ≥ required + 2 points, confidence 中 or 高, quality gate
  passed, momentum z ≥ −0.5. Ranked by confidence-weighted upside.
- **持有 Hold:** quality in the top 30% and gate passed, |upside| ≤ 15%, confidence 中 or 高. Ranked by
  quality.
- **卖出 Sell:** upside ≤ −25%, expected return ≤ required − 2 points, confidence 中 or 高, among the 400
  largest, **and** deterioration (momentum z ≤ −0.5, falling profits, or a quality failure). Ranked by
  confidence-weighted downside.
- **Regime-break stocks (A2.7):** valued at the probability-weighted value and run through the same rules. There is
  no "no call" zone.
- **Fills:** relaxed tiers fill short cells as today, marked 低信心. Peer-group limit 2. Pre-profit names never enter
  buy or sell.
- **Names:** the Chinese labels drop their qualifiers (持有/不追高 → 持有, 卖出/回避 → 卖出). Phase 7 renames them in the
  current report too.

### A2.4 The card, v2 (prototype numbers)
> **格力电器 000651 · 买入候选 · 把握度 中**
> 现价 39.49 → 内在价值 105；三个锚：内在 105 · 同业 74 · 自身历史 54 → 综合 88（+124%）
> 预期年化回报 14.0%（要求回报 6.8%）
> 股价隐含：未来 10 年 ROE 12%；过去 10 年平均 25%；分析师第 3 年 22%
> 类型：稳定型（ROE 五年下行，按分析师 22% 估值，不假设回到 25%）
> 回测（Phase 9 之后）：同类信号 12 个月平均兑现差距 x%，跑赢概率 y%

> **MU · 无动作 · 把握度 低**
> 现价 878.84 → 内在价值 709；三个锚：内在 709 · 同业 2,197 · 自身历史 261 → 综合 532（−39%），分歧很大
> 预期年化回报 4.1%（要求 7.0%）
> 股价隐含：未来 10 年 ROE 82%；过去 10 年平均 21%；分析师预计 FY28 见顶
> 类型：周期股（按周期平均 ROE 估值，第 3 年共识打 5 折）
> AI 景气延续概率：本模型 40%（同类历史 45%；MU 上一轮 FY2018 ROE 44% 两年后降到 7%；分析师预计 FY28 见顶）对比市场隐含约 50%
> 加权价值 约 830（−6%）：现价不买；跌到约 690 以下转为买入；库存相对销售回升、或大客户资本开支放缓会继续下调概率（数值为示意，Phase 8 计算）
> 近期事件（格式示例）：日期 · 事件类型 · 是否进入估值，例如“业绩预告：扣非净利 +x%，已纳入估值”或“股价 +y%，无对应公告，视为噪音”

MU gets one committed answer: about 6% overvalued, so not a buy, together with the price and the evidence that would
change the call. The second card also shows a known prototype gap: its score still rated MU 中. Dispersion above 0.5 should cap confidence
at 低; fixed in Phase 8.

### A2.5 Making the number useful without shrinking it (your D2)
The intrinsic value stays exactly what the model computes. What makes it actionable is two numbers measured from the
model's own record, not chosen:
- **12-month expectation:** E[price in 12 months] = price × (V/price)^β × (1 + dividend yield). β is the share of the
  log gap that has historically closed within 12 months, estimated in the backtest per archetype and confidence band.
- **Hit rate:** the share of past signals in the same band that beat the market over 12 months.

If β turns out near zero, the model has no predictive power and we'll know before it ships. Rev. 1's shrink was a
display choice; β is a test result.

**Accountability.** Every call is logged with its value, probability and confidence. Page 1 of the report shows the
track record: hit rate and average excess return of past buys and sells per market, and whether our stated
probabilities came true at the stated rates. The reader judges the method by its record, not the other way around.

### A2.6 What the prototype shows (2026-10-17 snapshots)

| | US | HK | CN |
|---|---|---|---|
| Valued (non-pre-profit with a value) | 744 / 796 | 366 / 407 | 784 / 798 |
| 5+ years of history (Phase 7 target ≥ 90%) | 66% | 92% | 100% |
| Own P/B history | 72% | 99% | 98% |
| Archetypes: steady / cyclical / growth / financial / pre-profit | 455 / 131 / 103 / 92 / 15 | 182 / 97 / 52 / 37 / 39 | 348 / 216 / 147 / 73 / 14 |
| Anchors agree (dispersion ≤ 0.3) | 71% | 66% | 55% |
| Confidence 高 / 中 / 低 | 45 / 26 / 29% | 53 / 19 / 28% | 45 / 23 / 31% |
| Median combined upside: steady / cyclical / growth / financial | +4 / −35 / −31 / +14% | +9 / −20 / −23 / +16% | +8 / −38 / −24 / +27% |
| Structural-decline flags | 133 | 147 | 223 |

**Before / after for today's 45 picks** (full table: `review-sims/v2/before_after.csv`):

| Pick (old call, old upside) | v2 | Why |
|---|---|---|
| MU (buy, +251%) | −39%, low confidence | through-cycle ROE 21%; the price needs 82% for 10 years |
| 天齐锂业 (buy, +304%) | +80% | consensus recovery, priced below its 12% through-cycle ROE; Phase 9 decides whether lithium history counts |
| TIGO (buy, +130%) | −14%, low confidence | normal ROE 11% ≈ required return |
| WDC, 江波龙 (AI-swapped, +177%/+113%) | −75% / −29%, low confidence | peak cycle; WDC's history is broken by its spin-off (a deep-dive trigger) |
| P/S biotech sells (−82% to −97%) | no value, no call | pre-profit |
| 牧原股份 (sell, −54%) | −17%, no sell | hog cycle; consensus recovery |
| MSTR (sell, −94%) | −48%, low confidence | bitcoin holder; needs a NAV deep dive |
| Brilliance (buy, +173%) | +105%, fails the gate (OCF/NI) | equity-method income without cash: a holdco deep dive |
| CN holds (成都银行, 柏楚, 药明康德, 中国人寿) | +14% to +50% | banks and insurers still look cheap at λ = 0.5: calibration |

**v2 prototype lists** (before AI swaps and the issuer dedupe):
- US buy: VALE, OMC, CTSH, VTRS, SYF. Hold: TRV, PGR, JPM, NTRS, INCY. Sell: INTC, WELL, CL, SPOT, WMB.
- HK buy: 康哲药业, 碧桂园服务, 复星医药, 玖龙纸业, 中信股份. Sell: 国泰君安国际, 中芯国际, 华虹宏力, 渣打, 中广核矿业.
- CN buy: 华东医药, 华鲁恒升, 格力电器, 丽珠集团, 赛轮轮胎. Sell: 华大九天, 远东股份, 东材科技, 长川科技, 中微公司.

These lists are a strong value tilt. That is defensible (in CN, high-ROE low-P/E names beat the market in 2022-2025,
which the backtest will confirm or refute). They also show where v2 still needs work:

| Open problem | Evidence | Fix |
|---|---|---|
| Value traps the data can't see | OMC +125%, CTSH +90%, 格力 +124%: history and consensus both say "cheap", the market says disruption or governance | Market-disagreement penalty; β calibration; deep dive on triggers |
| Discount rate drives value-stock upsides | Implied US 6.9% vs config 10.1%; CN 6.4% vs 7.65% | Phase 9 compares implied, configured and λ variants out of sample (A7) |
| Sector discounts | Median financial +14-27% | λ calibration, or each sector's own historical implied return (A4) |
| Growth optionality underweighted | PLTR −75%, TSLA −88%, but low confidence | Sells need deterioration; backtest checks the growth bucket |
| US history coverage 66% | SEC 10-K extraction misses some concepts; foreign filers have only 4 Yahoo years | Phase 7: concept fallbacks and quarterly sums |
| Confidence points uncalibrated | MU rated 中 despite dispersion 0.67 | Phase 8 caps; Phase 9 hit rates |
| AI regime breaks, both directions | 新易盛 treated as cyclical (−36%); AMD, 寒武纪, 海光 dragged by pre-AI history (−52% to −67%); Omnicom, Cognizant read as cheap (+125%, +90%) | Regime test and a committed persistence probability (A2.7) |
| News not used beyond titles in the notes | 7 of 66 candidates flagged from announcements today; nothing judges price-moving news | Event layer (A2.8) |

### A2.7 Regime breaks (AI and others): regime-aware history and a committed probability
A 10-year average assumes the last decade is a fair sample of the next one. Where AI, or anything else, changed a
business's economics, that is false in both directions. The prototype handled clear AI winners mostly by accident and
misfired on three groups ("weight on history" = how much the 10-year average counts versus today and consensus):

| Group | Examples (weight on history → v2 upside) | Verdict |
|---|---|---|
| AI winners with steady high returns | NVDA 0.03 → +34%; TSMC 0 → +50%; Broadcom 0 → +20%; MSFT 0 → +48% | History barely used; fine |
| Memory, storage, optical modules | MU 1.0 → −39%; WDC 1.0 → −75%; 江波龙 1.0 → −29%; 新易盛 0.67 → −36% | Fully history-driven; debatable, since AI demand may have changed cyclical industries |
| Fast growers whose early years lost money | AMD, 寒武纪, 海光, Palantir 0.3 → −52% to −75% | Even 30% weight on a pre-AI history drags the value down; probably wrong |
| AI-disrupted businesses | Omnicom 0.13 → +125%; Cognizant 0 → +90%; Accenture 0 → +27% | Stable history read as "cheap" while the market prices disruption; history likely overstates their future |

**1. Detect a regime break with data.**
- **Signals:** revenue growth over the last 3 years far from the trend of the 7 before (acceleration or decline); a
  step change in ROE or margin.
- **Confirmation:** whether analysts' year-2 and year-3 forecasts stay at the new level or fall back toward history.
- **Confirmed break:** history shrinks to the post-break years plus consensus. NVDA's 2026 isn't averaged with its
  2017. The same test catches negative breaks (China property, AI-disrupted services) alongside the structural-decline
  rule.
- **Unconfirmed:** a break analysts expect to revert keeps the long window, as for a cyclical.

**2. Value both outcomes, then commit to our own probability.**
- **New regime persists:** consensus earnings, then a slow fade with high persistence (V_new).
- **Old pattern returns:** the 10-year normal ROE and a faster fade; for the disrupted, shrinking revenue (V_old).
- **Base rate (outside view), measured in our history panel:** company-years where ROE jumped 12+ points above its
  5-year average to 18% or more, and what happened next:

  | Market | Episodes | Kept ≥ half of the jump after 2 years | after 3 years | 3 years, cyclical history |
  |---|---|---|---|---|
  | US (SEC, 2016-2026) | 259 / 209 | 54% | 47% | 45% |
  | CN (业绩报表, 2015-2025) | 736 / 665 | 22% | 12% | 15% |

  - **What it says:** in A-shares, betting that a profit spike lasts 3 years loses about 9 times in 10. In the US it
    is close to a coin flip.
  - **Bias:** the US panel holds today's listings only, so it overstates persistence; the CN point-in-time backtest
    (Phase 9) is the unbiased check.
- **Evidence (inside view)** moves the base rate up or down:
  - the company's own past booms (MU: ROE 44% in FY2018, 7% two years later)
  - how durable consensus is (year 3 vs year 1)
  - inventory growth against sales growth, a classic sign a cycle is turning
  - backlog and contract liabilities (CN 合同负债; US remaining performance obligations)
  - gross-margin direction
  - for AI: a capex gauge, the combined capex growth of the 10 largest spenders in our US universe, computed from SEC
    data with no hand-picked names
  - events from A2.8
- **Calibration:** a small model (logistic regression) of "kept the gain" on these signals, fitted on the panel. Only
  signals that predict out of sample keep a weight. A stated 40% has to come true about 40% of the time in the
  backtest's calibration curve, or the model is refitted.

**3. One value, one call.**
- **Value** = p × V_new + (1 − p) × V_old, run through the normal 买入 / 持有 / 卖出 rules. No "no call" zone.
- **The market's implied probability** (where today's price sits between V_old and V_new) appears on the card as the
  reason for the call: "我们估计 40%，市场隐含 50% → 高估约 6%". The disagreement is the thesis, stated plainly.
- **The re-check trigger** names the evidence that would move p and the price that would change the call.

**4. Which stocks get it.**
- First, the data break test.
- Then theme tags where free: Eastmoney concept boards in CN (CPO, 算力, 人工智能; a-stock-data §3.3).
- For US/HK: a configured industry list (semiconductors, optical, networking, data-centre power, IT services,
  advertising, outsourcing) or a DeepSeek category label, never a number.
- Tags only decide who gets the regime treatment and explain the card. They never set a value.

**5. Where the probability comes from for something as new as AI.** The AI regime is only about 3 years old, so its
own history can't calibrate how long it lasts. The base rate therefore comes from earlier booms in the same panel
(memory, solar, lithium, 5G, the 2021 commodity spike), adjusted by AI-specific evidence (the capex gauge, backlog,
consensus durability). A disciplined analyst would do the same; the difference is that every step is measured and the
result is checked against what happens. The event layer (A2.8) feeds the evidence: a large AI contract, capex
guidance, a pre-announcement.

### A2.8 Event layer: is a piece of news noise or a value driver?
Today news reaches the method only as up to 10 announcement titles in each pick's DeepSeek note, which can flag a
swap. That matters (7 of today's 66 candidates were flagged: 长和's Panama ports sale, 中金公司's merger, 09969's
Lilly licence), but nothing judges price-moving news. The rule: news changes the value only if it moves one of the
model's inputs (the earnings path, how long high returns last, the required return, the share count or book value).
Everything else may move the price, not the value.

| Event type | How it reaches the value | What the code does |
|---|---|---|
| Earnings pre-announcement or guidance (业绩预告 is market-wide, with numbers) | Earnings path | Updates the inputs from the published numbers, re-runs the value |
| Large contract, acquisition, disposal | Earnings path or deal price | Materiality = size ÷ revenue or market value, from the filing. Small → noise; large → deep-dive lane for the hard numbers |
| Buyback, placement, convertible | Share count, book value, payout | Adjusts per-share numbers |
| Investigation, penalty, litigation, audit issue, policy hit | Risk | Lowers confidence; severe → veto (swap) |
| Theme or story with no amounts (AI, low-altitude economy, a "partnership") | None measurable | Value unchanged; the card states what the price now assumes (e.g. "股价隐含 ROE 60%") |

- **The market's own reaction.** Research on news and returns finds that large moves *with* matching news tend to
  continue, while large moves *without* news tend to reverse. For every abnormal move (beyond about 2.5 standard
  deviations against its market over 1-5 days):
  - **With a material event:** information. The value waits for the inputs and consensus to catch up.
  - **Without one:** probably noise. The value stays put, and the wider gap strengthens the signal.
  - **The test:** the Phase 9 backtest checks whether this holds in A-shares before it enters the score.
- **Analysts as the slow news reader.** Weekly consensus snapshots (stored from Phase 7) show revisions. Rising
  revisions after news mean a value driver; none mean noise. Yahoo's HK data already carries 7-, 30-, 60- and 90-day
  revision fields. Revisions feed confidence and are tested as a signal.
- **Cost and rules.**
  - **Sources:** market-wide daily feeds (CNINFO latest announcements, HKEXnews latest filings, the SEC 8-K daily
    feed), not per-stock calls.
  - **Classification:** keywords, filing types and 8-K item numbers first; DeepSeek only to pick a category for an
    ambiguous title, never a number.
  - **Numbers:** taken from filings, quoted and checked as in the deep-dive lane.
- **Optional intraday check:** a light hourly check of the 45 picks only. A material event since 06:30 adds one line
  to the keyword reply ("10-18 盘中：××公告立案调查"). It needs a launchd job, so I'd ask first (rule 9).

---

## A3. The deep-dive lane (your D3)

**Why:** market-wide rules decide quickly and consistently, but they can't read the filings. A small number of picks
each day are exactly the cases where reading changes the answer: holding companies, insurers, landlords, spin-offs,
pending deals, "too cheap to be true". The lane spends depth only there.

**Four tiers of effort:**

| Tier | Scope | Cost | What it does |
|---|---|---|---|
| 1 | Whole universe (~2,000) | seconds | v2 engine, quality gate, confidence |
| 2 | ~45 picks + runners-up | ~60 DeepSeek calls/day (today) | Notes and flags, as now, plus the v2 facts |
| 3 | ≤ 3 per market per day | ~9 long-context calls; cached until the next filing | Evidence extraction from the latest filing; code recomputes |
| 4 | Your choice | your time in Claude Code | Run ai-berkshire skills (investment-checklist, earnings-review...) on a pick; record a verdict |

**Tier 3 triggers** (rule-based; among picks and the first runners-up):
- the model's value is more than 2× or less than 0.5× the price and confidence is not 高
- the quality gate fails while the value signal is strong ("looks unreal")
- detected archetype gaps: equity-method income above 40% of profit (holdco), an insurer, a property investor with
  revaluation swings, a broken history (spin-off, large acquisition: share count or book changed more than 40%)
- an AI flag of pending_deal
- a material event from the event layer on a pick (A2.8), e.g. a contract above 10% of revenue, or a large move whose
  cause the titles don't explain

**What it extracts** (a fixed questionnaire built from the skills; every item comes with the quoted sentence):

| Item | From (skill idea) | Code then |
|---|---|---|
| Non-recurring items: amount, period | earnings-review (附注); CN 非经常性损益明细表 | Adjusts core earnings, recomputes the value |
| Listed stakes: ticker, % held | for holdcos | Sum-of-the-parts at our own market prices, minus holdco net debt |
| Embedded value per share (insurers) | income-investment (sector measures) | P/EV anchor for insurers |
| Underlying profit excluding revaluation (landlords) | | Replaces reported profit |
| Deal terms: offer price, swap ratio | | Becomes the anchor; the pick is swapped as today |
| Audit opinion, going concern, investigations, related-party sales share | investment-checklist quick veto | Veto (swap) or 低信心 |
| Commodity or price driver | era-alpha (verification) | Archetype correction |

**Verification:** code looks up the quoted sentence in the filing text (whitespace-normalized) and parses the number
from the quote itself, not from the model's answer. Anything unverified is dropped. Numbers still come from data; the
LLM only finds where they are. Sources: CNINFO and HKEXnews PDFs (text via pypdf, a new dependency) and SEC
10-K/10-Q HTML. Cost: about 9 calls of ~30k tokens a day on DeepSeek, roughly cents a day. It runs in the 06:30
build, never in the keyword reply.

**Tier 4, manual verdicts (optional):** `stockreport verdict <code> veto|confirm --until <date> --reason "..."`
writes data/verdicts.csv. A veto swaps the pick; a confirm can raise 低 to 中. A verdict never changes a number and
expires at the date or the next filing.

## A4. Backtest and calibration (your D5)

- **CN, point-in-time, 2019-2026, the main test:**
  - Results with notice dates (Eastmoney 业绩报表, verified back to 2015).
  - Prices from 通达信 daily packages (2021+, about 3 GB downloaded, extracted and discarded) and Eastmoney valuation
    history (2018+) for the early years.
  - Industries from the 申万 change history (no look-ahead).
  - Consensus rebuilt point-in-time from the Eastmoney research-report archive: each report carries its publish date
    and this-year / next-year / year-after EPS. Median of the reports in the trailing 120 days.
  - Universe: top 800 at each rebalance, using the same turnover rule. Delisted stocks stay in (packages hold
    everything), so there's no survivorship bias.
- **US, 2016-2026, secondary:** SEC facts carry filing dates (point-in-time) and Yahoo monthly prices. Current
  constituents only, so survivorship bias is stated, not fixed. No free consensus history, so the test uses the ROE
  path.
- **HK:** no filing dates; assume 3 months after period end.
- **Calibrated, in-sample 2019-2023, checked out-of-sample 2024-2026:**
  - λ; the history-weight and cycle rules; the consensus haircut; φ (from the ROE persistence panel); anchor weights;
    confidence → hit rate; β by archetype and band.
  - Implied vs configured discount rate.
  - Sector premium from each sector's own historical implied return, compared with λ.
- **News test (CN):** announcement history (CNINFO by date range) aligned with abnormal moves. Do moves with a
  material event continue and moves without one reverse? Do consensus revisions predict returns? This decides whether
  attribution and revisions enter the score.
- **Regime-persistence model (A2.7):** base rates and signals fitted on the panel; a calibration curve of stated vs
  realized probabilities; the CN point-in-time data corrects the US survivorship bias. AI itself has about 3 years of
  history, so its probability rests on earlier booms plus AI-specific evidence.
- **Reported in docs/BACKTEST.md:**
  - Buckets vs index and the equal-weight universe.
  - Rank correlation of upside and expected return with 1-, 3- and 12-month returns.
  - Calibration curves (predicted vs realized).
  - v1 vs v2 compared directly.
- **The same code scores live snapshots (`track --signal`),** so evidence keeps building after the switch.

**Switch rule (proposed):** v2 replaces v1 in the report only if, out of sample, its buy-minus-sell spread and its
rank correlation beat v1's in at least two of three markets, and its 高 picks beat the market more often than its 低
picks.

---

## A5. Plan (each phase one session; built in a worktree; v1 keeps running until the Phase 10 switch)

### Phase 7: History data, production bug fixes and bucket names
- **History tables, weekly or yearly, small:**
  - US: 10-K history from the companyfacts files already downloaded weekly (no new calls): net income, continuing
    operations, equity, preferred, OCF, capex, dividends, shares, revenue. Concept fallbacks plus quarterly sums to
    lift coverage from 66% to at least 90%.
  - US foreign filers: Yahoo annual.
  - CN: annual 业绩报表 2015+ with 扣非 EPS, plus TTM 扣非; valuation history 2018+ (semiannual, monthly later).
  - HK: main indicators 2015+.
  - Yahoo monthly prices, splits and HKDCNY for US/HK own-history P/B.
  - Start keeping weekly consensus snapshots (CN, US, HK) and the market-wide 业绩预告 table, so revisions and
    pre-announcements have history by the time Phase 8 uses them.
- **Bucket names:** 买入 / 持有 / 卖出 everywhere. Files: pick.py, render/, report.py (re-check triggers), the DeepSeek
  prompt in notes.py, the text summary, tests; plus the AGENTS.md goal paragraph and PLAN.md Method 6.
- **Production fixes from rev. 1:** checks 1-2 enforced in code at pick time (they're skipped today without DeepSeek);
  quality scores standardized within financials and non-financials; cash conversion clipped.
- **Done when:** history covers ≥ 90% of each universe; the tables add < 50 MB; the daily build grows < 30 s; tests on
  saved samples pass; a `--no-notes` run in the worktree shows checks 1-2 applied and the report and summary read
  买入 / 持有 / 卖出. Effort ~380 lines. Risk: SEC
  concept gaps; Eastmoney rate limits (1 request/s, as now).

### Phase 8: v2 engine in shadow mode
- Earnings base, history weights, archetypes, the three-stage residual-income model, expected return, implied ROE,
  repaired peer anchor, own-history anchor, combination, confidence v0 (with the dispersion cap), quality gate, v2
  buckets.
- Regime test; V_new and V_old; a first persistence probability from the measured base rates by market and
  cyclical history, adjusted by the company's own past booms and consensus durability; the probability-weighted
  value (A2.7). Theme tags from Eastmoney concept boards (CN) and the configured industry list (US/HK).
- Pre-announcement numbers as inputs; consensus revisions as a confidence input (A2.8, data only).
- Written to the snapshots next to v1. The report is unchanged; the run prints the v2 lists and a v1/v2 comparison.
- **Done when:**
  - all three markets run in < 60 s
  - pre-profit names get no value
  - no value above 3× price without 低
  - every stock with a confirmed break shows our probability with its evidence, the market's implied probability and
    one probability-weighted value; MU-, NVDA- and Omnicom-type cases are checked by hand
  - tests cover the residual-income math (a hand-checked case), the history-weight rules and the gate
  - you review one day of v2 lists
- Effort ~550 lines. Risk: first-guess parameters until Phase 9; the break test's thresholds.

### Phase 9: Backtest, calibration, signal tracking
- A4 in full: CN point-in-time data, consensus from the report archive, US secondary, HK with a lag.
- Calibrate the parameters; `track --signal` on live snapshots; docs/BACKTEST.md.
- The news test: abnormal moves with and without material events; the revision signal (A4).
- The persistence model: fit the signals (inventory against sales, backlog and contract liabilities, the capex gauge,
  margin direction, consensus durability) and check its calibration.
- **Done when:** out-of-sample tables exist for v1 and v2; the parameters come from in-sample and hold out of sample;
  the switch rule is evaluated and reported to you.
- Effort ~550 lines plus a script. Risk: the consensus rebuild (archive paging limits; verify first); about 3 GB of
  transient downloads.

### Phase 10: Switch the report to v2 (only if Phase 9 says so) and phone-first cards
- Cards as in A2.4 with the backtested 12-month expectation and hit rate, the regime line (our probability vs the
  market's) where it applies, and "近期事件" lines once the event layer runs. Page 1 shows the track record. The summary text line becomes
  "代码 名称 动作 现价→内在价值 空间 预期回报 把握度".
- DeepSeek gets the v2 facts (implied ROE vs history and consensus) so notes say why.
- Phone-sized PDF pages.
- **Done when:** the keyword reply works in < 30 s with the v2 report; you review the 45 picks; the PDF reads without
  zoom.
- Effort ~250 lines. Risk: low.

### Phase 11: Deep-dive lane and event layer (needs the A7 amendments)
- A3 tiers 3 and 4: triggers; filing fetch for CNINFO, HKEXnews and SEC; pypdf text; DeepSeek questionnaire; quote
  verification; code adjustments (one-offs, sum-of-the-parts, insurer EV, landlord underlying profit, deal anchors,
  vetoes); verdicts.
- Event layer (A2.8): daily market-wide feeds (CNINFO, HKEXnews, SEC 8-K); classification by rules, with DeepSeek
  only picking a category; materiality from filing numbers; attribution of abnormal moves (with or without news);
  event lines on cards; events as deep-dive triggers. The hourly pick check is optional and needs your OK for a
  launchd job.
- **Done when:** at most 3 deep dives per market per day; cached per filing; every used number has a verified quote
  (tested on saved filings); every abnormal move on a pick is labelled with or without a matching event; cards show
  "深度核查" and "近期事件" lines; the 06:30 build grows < 5 min.
- Effort ~600 lines. Risk: PDF text quality on scanned filings (those are skipped); questionnaire drift (fixed JSON
  schema, as for notes).

### Phase 12: Data cross-checks and drift alarms
- Rev. 1's Phase 11, unchanged: Tencent quotes, Yahoo vs SEC, Yahoo key statistics for HK, a day-over-day drift
  alarm, consensus sanity checks, market-cap checks.
- **Done when:** disagreement counts are printed every run and tests use saved samples.
- Effort ~150 lines.

Total ≈ 2,500 lines over six phases, so app code goes to ~5,300.

## A6. What stays as it is
- Free data only; numbers from code and data; rank-based buckets (5 per cell); issuer dedupe; 06:30 build;
  30 s keyword reply; storage under 2 GB (history and event tables add well under 100 MB).
- v1 keeps producing the report until Phase 10. The only change you'll see before the backtest has spoken is the
  bucket names (Phase 7).

## A7. Decisions for you now

1. **Approve the v2 direction and Phase 7** (history data, the production bug fixes and the bucket names), built in
   a worktree.
2. **Rule text** (AGENTS.md), proposed wording:
   - Rule 2, add: "In the deep-dive lane DeepSeek may extract facts from primary filings, each with the quoted
     sentence; code checks the quote against the filing text and takes the number from the quote."
   - Rule 3, replace with: "Value every stock with one rule-based engine (intrinsic residual-income value, peer and
     own-history anchors), calibrated by backtest. No hand-typed per-company assumptions. Per-company research only
     through the bounded deep-dive lane (rule-triggered, at most 3 per market per day, cached per filing) and user
     verdicts (veto or confirm with an expiry, never numbers)."
   - Rule 6: target ~6,000 app lines, files under 400.
   - Goal paragraph: the buckets are buy 买入 / hold 持有 / sell 卖出, and the card shows intrinsic value, expected
     return, confidence and (for regime breaks) our persistence probability, instead of "fair-value range".
3. **pypdf** (pure Python, free) as a dependency for Phase 11. Needed only then.
4. **Hourly event check for the 45 picks** (Phase 11, optional): a small launchd job. I'll ask again before
   installing it.
5. **Discount rate:** let Phase 9 choose between the market-implied rate (no market-wide calls) and the configured
   rate (whole markets can look cheap or dear), or decide now. My recommendation: let the backtest decide, and default
   to implied.

---

# Part B: rev. 1 findings (2026-10-17)

These still describe the method in production (v1). Phase numbers in Part B point to the plan in A5.

## B1. Blind spots

| Area | Finding | Evidence |
|---|---|---|
| **Cyclicals at peak** | A one-year spike in ROE or revenue growth is read as quality and growth, and the method has no through-cycle view. Memory makers, lithium, fertilizer and bull-market brokers get growth-stock multiples on peak earnings. | MU, WDC, SQM, CF, 天齐锂业, 盐湖股份, 江波龙, 德明利, 招商证券, 广发证券 are all buy picks or AI-swapped picks today. Among the 30 best-ranked buy candidates: US 18 with profit ≥+100%, 8 where analysts expect EPS to fall within 2 years, 11 above +100% upside. CN: 20, 4 and 16. |
| **Cyclicals at trough** | Loss-making cyclicals go to P/S. When next year's consensus is positive but this year's is negative there is no forward lens, because forward growth needs e1 > 0. | 牧原股份 is a sell at −54% on P/S (hog-cycle trough). Analysts expect FY27 EPS of 4.47, a forward P/E of 9.2. |
| **One-off profits** | CN uses 归母净利润, not 扣非. US uses `NetIncomeLoss`, which includes discontinued operations. Checks 1-3 catch some cases, but only at the notes stage (see the robustness bug). | HON: TTM EPS 25.91 against FY26E 8.27, so P/E 8.2 and +79% upside (trailing lens 553). Profit growth sits at the winsor cap for 江波龙, 德明利 and 天齐 (+1,216%). 天齐's cash conversion is 0.514, just over check 1's 0.5 threshold. |
| **Consensus quirks** | US consensus is adjusted (non-GAAP) EPS while trailing EPS is GAAP. A depressed current-year estimate inflates forward growth (e1 → e3). | INCY: TTM 7.06, FY26E 2.28, FY27E 7.61, so forward growth hits the +78% cap; INCY is a final buy at +38%. GM: TTM 2.22 against FY26E 13.53. The ratio eps_e1/eps_ttm is otherwise sane (median 1.09-1.20); the outliers come from GAAP vs adjusted EPS and low bases, not unit errors. |
| **Peer groups too small** | A 3-parameter fit on 8 stocks leaves 5 degrees of freedom. | 210 US, 142 HK and 200 CN valued names come from fits with fewer than 15 members. WDC (+177%) and P/Everpure (−56%) sit in the same 8-member group. |
| **Peer groups too broad** | Industries with fewer than 8 members are fitted against the whole market. Tech and semiconductors dominate that pool, so the traditional sectors in it all look cheap. | CN: 244 of 798 names (31%) are on the pooled fit (R² 0.24, residual sd 0.76), with median upside +41% against +2% within their own groups. 50 of the 80 CN names above +100% are pooled. HK: 48 names, median +23%. US avoids this by merging small groups into "<sector> (other)": 7% pooled. |
| **Peer groups wrong** | Exchange industry labels misplace companies. | FSLR and NXT (solar) sit in Nasdaq "Semiconductors"; FSLR shows +260%. TIGO (a LatAm telecom operator) sits in "Telecommunications Equipment" (n=13); its revenue growth of +59% comes from acquisitions, so it shows +130%. GM is on the market-wide pool. |
| **Wrong-signed fits accepted** | The Phase 2 problem (a negative ROE coefficient) recurs in some P/B fits. | ROE coefficient: HK 建筑 −14.2 (n=8; one name at +508%); US Telecom Equipment −0.53 (TIGO); CN IT服务Ⅱ −1.9, 电池 −1.2, 自动化设备 −0.9, 消费电子 −0.8. |
| **Financials** | CN insurers have fewer than 8 members, so they are pooled with banks and brokers (R² 0.01). The CN broker fit explains nothing (R² 0.00), so fair P/B is about the group average. US book value includes preferred equity. | 中国人寿 A is valued on the pooled financial fit. Brokers with +75-108% revenue growth in a bull market reach the buy list. For US banks with preferreds, BVPS is overstated by up to ~10%, since `StockholdersEquity` includes them. |
| **Tiny book** | Negative book goes to the forward lens. Positive but tiny book (after buybacks or spin-offs) gives an extreme ROE and an extreme fitted P/B. | WDC: ROE 106%, P/B 14, trailing lens 659 against a price of 332. |
| **Holding companies, JVs, landlords** | P/B against operating peers misses structural holdco discounts. A property revaluation loss sends a landlord to P/S. | HK buys: BRILLIANCE CHI +173% (its value is a JV stake; the autos fit has R² 0.06); 第一太平 +141% (1 analyst; cash conversion 18.5 because consolidated OCF is divided by attributable profit); 九龙仓置业 on P/S. MSTR (a bitcoin holder) gets −94% on software P/S, although its P/B of 1.87 points to roughly −45% to book. |
| **Pre-revenue biotech** | P/S on licensing revenue is meaningless. | Sells: 映恩生物 −89%, 劲方医药 −97%, 百利天恒 −82%. The P/S fit for HK biotechs has R² 0.09. |
| **Quality metric artifacts** | Cash conversion (OCF/NI) explodes when profit is tiny, and mixes consolidated cash flow with attributable profit. HK gross margin isn't comparable across reporting formats. | Cash conversion above 3: 91 US, 86 HK, 124 CN names. 兖煤澳大利亚 is a "top-30% quality" hold with ROE 3.3%, profit −90%, cash conversion 31.6 and gross margin 75%. 金沙中国 has cash conversion 15.4. |
| **Score bias (financials)** | `score()` z-scores the financial and non-financial component means together, but financial quality is one metric (ROE) against four for the rest. | Spread of the quality score: US 1.55 vs 0.84, HK 1.29 vs 0.92, CN 1.35 vs 0.94. Financials' share of the top 5% by quality: US 42% (12% of the universe), CN 28% (9%). US holds today: SEIC, BSAC, ITUB, GL, BAP. |
| **低信心 logic** | Only tier > 1 or opposite-pointing lenses (more than 50% apart) set 低信心. Two lenses saying +100% and +250% "agree". Fit size, R², pooling, P/S, a missing lens, winsor caps and the size of the upside are all ignored. | 2 of 45 final picks are marked 低信心. MU (+251%), 天齐 (+304%) and 劲方医药 (−97%) are "normal". |
| **Robustness: spike checks** | `Notes.fetch` returns the template note before checks 1-2 are enforced when there is no client (`--no-notes`, missing key) or the API fails. | Today, checks 1-2 swapped ALL, WDC, 09995, 00966, 03888, 301308, 001309, 688331 and 688336. A 06:30 run with DeepSeek down would ship them and log them in data/picks.csv. |
| **Data cross-checks** | CN and HK compare P/E and P/B with Eastmoney's own numbers, the same source family, at a loose 50% tolerance. US has no second source for fundamentals. | universe.py checks; financial-data asks for two independent sources and treats more than 5% as unusable. |
| **Staleness** | OK today: the newest report periods are at most 199 days old in every market (median 108). | One weak spot: HK's "no report in the last 300 days" check would accept a Dec-FY company that missed its interim report. 200-220 days is enough. |
| **Look-ahead and survivorship** | None in live mode. In tracking, returns start at the price-date close, while the report arrives the next morning, so the opening gap is credited. A delisted pick counts as flat. HK has no filing dates, so a future HK backtest would need an assumed lag. | track.py `returns()`, `growth()`. |
| **Currency and units** | Handled carefully (undoing Eastmoney's CNY conversion for HK, FX for US gap companies). No unit errors found in the EPS consistency check. Remaining issues are the GAAP-vs-adjusted EPS and preferred-equity points above. | |
| **Share classes, dual listings** | Fine. Dedupe by ORG_CODE worked today (中国人寿 H was swapped out). Note that the same issuer gets very different upsides at the A and H prices (中国人寿 A +8%, H +4%; H trades about 37% below A). | |
| **Liquidity** | Thresholds are fine. HK has only ~407 names, so many groups are small. A sell can be a thinly covered name. | 01196 伟禄科技股份-新: 0 analysts, P/S, −96%. |
| **Line budget** | App 2,839 lines; tests 591; total 3,430. Rule 6 says "under 3,000 lines of Python in total". | If tests count, the project is already 430 lines over. You raised the budget (D1); A7 proposes ~6,000 app lines. |

## B2. The valuation method

### B2.1 What's sound
Cross-sectional regressions of log multiples on fundamentals (the "value map", P/B on ROE) are a standard way to rank
cheap against expensive within groups of similar companies. The method works where groups are homogeneous and the fit
explains a lot: US major banks (R² 0.70), HK banks (0.73), CN railways and roads (0.93), 白酒 (0.97), shipping (0.81),
US integrated oil (0.90). The design choices behind it are right: the LLM never makes numbers, consensus EPS is used
and target prices are not, financials are valued within their own peers, and negative book goes to the forward lens.

### B2.2 How upsides are distributed (valued stocks, 2026-10-17)

| Market | Method | n | median | 5th pct | 95th pct | max |
|---|---|---|---|---|---|---|
| US | P/B (ROE + growth) | 612 | −0% | −50% | +106% | +553% |
| US | P/B on ROE (financials) | 92 | +4% | −28% | +53% | +76% |
| US | P/S (loss-makers) | 47 | −4% | −88% | +251% | +546% |
| US | forward P/E only | 37 | −2% | −45% | +71% | +138% |
| HK | P/B | 302 | +5% | −52% | +121% | +508% |
| HK | P/B on ROE | 37 | +9% | −41% | +53% | +85% |
| HK | P/S | 64 | −31% | −93% | +147% | +640% |
| CN | P/B | 652 | +11% | −51% | +142% | +362% |
| CN | P/B on ROE | 73 | +9% | −47% | +43% | +59% |
| CN | P/S | 73 | −9% | −87% | +250% | +420% |

Share of valued stocks with |upside| > 50%: US 20%, HK 29%, CN 31%. Above +100%: 6%, 7%, 10%. The CN median of +9%
has two causes: the pooled fit (2.4) and the arithmetic 50/50 blend of two log-normal-ish values, which biases upward.
The trailing and forward lenses correlate only 0.45-0.60 in log terms.

### B2.3 Why the magnitudes aren't credible
- **Low explanatory power.** Median R² of the P/B fits: US 0.59, HK 0.50, CN 0.43. Many groups are near zero: CN
  证券Ⅱ 0.00, 小金属 0.01, 自动化设备 0.01, 汽车零部件 0.03, 电池 0.04, 半导体 0.12; HK 保险 0.03, 汽车 0.06; US
  Investment Bankers 0.09, Life Insurance 0.10, Semiconductors 0.29. A residual spread of 0.5 log points means ±65%.
  The residual is mostly omitted fundamentals, not mispricing.
- **Exponential extrapolation.** log(P/B) = a + b·ROE + c·growth means a stock at the tail of ROE or growth gets
  exp(b·x) times the group's multiple. Winsorizing at the 2nd/98th percentile doesn't help, because the caps
  themselves are extreme: US revenue growth +99%, CN profit growth +1,216%, US ROE 120%.
- **One-year trailing growth** is noisy and mean-reverting. Cyclical rebounds and acquisitions look like structural
  growth.
- **Relative-only.** When the whole group is expensive, "fair" is expensive. Today the US semiconductor median is P/E 45
  and P/B 10.8.
- **The blend and the agreement test are lenient** (see 低信心 in B1).

### B2.4 Case study: MU at 3,087 against 879 (+251%)

| | Value | How |
|---|---|---|
| Inputs | P/E 11.7, P/B 7.19, ROE 61.4%, revenue growth +98.8% (the US winsor cap), profit growth +895% | SEC TTM to 2026-09-03 |
| Consensus (9 analysts) | FY27E 177.0, FY28E 207.3, FY29E 183.1 | analysts see a peak in FY28; 2-year CAGR e1→e3 +1.7% |
| Trailing lens | 2,630 | semiconductor fit (n=26, R² 0.29): log P/B = 1.64 + 0.36·ROE + 1.22·growth, so 21.5× book. Intercept 5.2×, ROE term 1.25×, **growth term 3.3×** |
| Forward lens | 3,543 | 17.1× (fitted at +1.7% growth) × FY28E EPS 207 |
| Group medians | P/B 10.8× → 1,319; forward P/E 22.4× → 4,645; P/E 45× → 3,411 | the group medians call MU cheap too |
| Market's own signal | 4.2× FY28E EPS | stored as 6.6× because forward P/E is winsorized at the US 2nd percentile |
| Own history (public data, not in our cache) | P/B roughly 1-4× over 2012-2025, highest near cycle tops | 7.2× today is already above that range; 3,087 would be about 25× book |
| Mid-cycle sketch | book 122/share × ROE 15-20% ≈ EPS 18-25 | even at 20× that is 370-490; the price already assumes several years of elevated earnings |

**Not believable.** Both lenses multiply peak-cycle earnings (ROE 61%, FY28E EPS 207) by multiples fitted on
structural growers in the same Nasdaq industry (NVDA, AVGO, AMD). One-year revenue growth of +99% is read as growth
quality worth a 3.3× multiplier. A sector-median check doesn't help, because the group is priced for AI growth while MU
is a memory producer at the top of its cycle. Only two checks see it: MU's own multiple history, and the market's 4×
forward P/E, which for a cyclical means "peak". The honest output is "this method can't value MU": 低信心, out of tier-1
buys, upside not printed as a fair value.

## B3. Confidence in today's 45 picks

Verdicts: **yes** = I'd stand behind the call; **partly** = direction defensible, number or reason not; **no** = model
artifact.

| Market · bucket | Overall | Picks |
|---|---|---|
| US · buy | **Low** | MU no (peak cycle, +251%); TIGO no (wrong peer group, acquisition-driven growth, profit −84%, 2 analysts); CF partly (cheap on P/E 8.7, but analysts expect EPS −25%); INCY partly (FY26E 2.28 vs TTM 7.06 vs FY27E 7.61 is inconsistent data); SQM no (lithium rebound, profit +647%, revenue growth at the cap) |
| US · hold | Medium for each name, low as a bucket | SEIC partly (broker fit R² 0.09); BSAC yes; ITUB yes; GL partly (n=9, R² 0.10); BAP yes. Five financials is the scoring bug, not a finding |
| US · sell | Low-medium | MSTR partly (direction yes, since it trades at a premium to its bitcoin; −94% on software P/S is meaningless); HLT partly (asset-light franchisor against hotel and cruise peers; −49% too strong); P partly (P/E 163, but an 8-member group); MRNA partly (P/S, n=8); INTC partly (loss-making TTM, forward P/E 62: fine as 回避, not as a −41% value) |
| HK · buy | **Low** | 01114 Brilliance no (JV holdco, R² 0.06); 00696 TravelSky partly (n=14, lenses 19.4 vs 10.6); 00142 First Pacific no (holdco, cash conversion 18.5, 1 analyst); 01997 Wharf REIC partly (already 低信心; revaluation loss sent it to P/S; P/B 0.51); 00590 Lukfook partly (market-wide pooled fit) |
| HK · hold | Medium | 09961 Trip.com yes; 03668 Yancoal no (profit −90%, "quality" from cash conversion 31.6); 01308 SITC partly (低信心; analysts expect EPS to fall); 01928 Sands China partly (cash conversion 15.4); 01651 Tsugami yes |
| HK · sell | **Low** | 01918 Sunac partly (distressed, direction OK); 09606 Duality, 02595 劲方, 02577 Innoscience no (P/S on pre-profit biotech and semis: −89% to −97%); 01196 伟禄 no (0 analysts, P/S) |
| CN · buy | **Low** | 600999 招商证券 partly (broker fit R² 0.00, bull-market profit +105%, analysts see EPS falling); 000792 盐湖股份 no (pooled fit, potash/lithium cycle, +103%); 605117 德业股份 partly-yes (n=9, but both lenses positive); 000776 广发证券 partly (same broker issues); 002466 天齐锂业 no (+304%, pooled fit, profit growth at the cap) |
| CN · hold | Medium-high | 601628 中国人寿 partly (pooled financial fit, R² 0.01); 603605 珀莱雅 yes (pooled fit, but both lenses near the price); 688188 柏楚电子 yes; 601838 成都银行 yes (bank fit R² 0.60); 603259 药明康德 partly (pooled fit) |
| CN · sell | Low-medium | 688126 沪硅产业, 688172 燕东微 partly (loss-making national-champion semis: direction maybe, values no); 688506 百利天恒 no (ADC biotech with large licensing deals); 600879 航天电子 partly (P/E 449, theme stock; defensible as 回避); 002714 牧原股份 no (selling at the hog-cycle trough, forward P/E 9.2) |

Tally: 8 yes, 23 partly, 14 no. The holds are the most trustworthy bucket (fairly priced quality, where a small
upside is harmless). The buys and sells are least trustworthy, because they select the largest residuals, which are
where the model is most wrong.

## B4. Skills

**What's installed.** "ai-berkshire" is not a Claude Code plugin; installed_plugins.json has only claude-mem. It is a
git clone at `~/ai-berkshire` (latest commit ab56abc, 2026-10-15) whose 21 skill files were installed as user commands
in `~/.claude/commands/*.md` (and as Codex skills). That's where quality-screen, financial-data and the others come
from. `a-stock-data` is a separate skill in `~/.claude/skills/`. The project uses a-stock-data only as an endpoint
reference (the 通达信 package layout); it uses no ai-berkshire skill, which is what rule 3 intends.

| Skill | Idea that works universe-wide, by rule | Data / endpoint | Fits rule 3? |
|---|---|---|---|
| **quality-screen** | 7 exclusion rules with 3 exemptions: 10y avg ROE < 8%, 5y cumulative FCF < 0, EBIT/interest < 2, long-run gross margin < 15%, 5y OCF/NI < 0.7, long-run net margin < 5%, shares +20% in 5y. "Cyclicals: use a full-cycle average, not one year." Apply as a gate for buy and hold (not sell), banks and insurers on ROE only. | SEC companyfacts (already downloaded weekly; extract annual history); CN 业绩报表 annual periods + RPT_DMSK_FN_CASHFLOW/INCOME (verify fields); HK main indicator over a longer window | Yes, as code on market-wide data. Its WebSearch per-company workflow is not used |
| **financial-data** | Two independent sources per key figure: ≤1% OK, 1-5% flag, >5% don't use. GAAP vs non-GAAP, consolidated vs attributable, and FX as known causes. | US: Yahoo timeseries (code exists) for all 800 vs SEC; CN: Tencent batch quotes (qt.gtimg.cn, from a-stock-data) vs Eastmoney; HK: Yahoo quoteSummary `defaultKeyStatistics` (book value, trailing EPS) added to the weekly call we already make | Yes. Its sources (macrotrends, stockanalysis, aastocks) are per-company web pages; use APIs instead |
| **industry-funnel** | Hard metrics: P/E against history and peers (PEG < 1.5 for growth), ROE > 15% or improving, OCF/NI > 70%, debt/assets < 60% (70% for utilities). Every dropped stock keeps a reason. | Same data as quality-screen | Partly. The moat rating is qualitative and is skipped |
| **investment-checklist** | 第二关 business metrics (5y ROE, gross margin, FCF ≈ NI, capex intensity, debt/NI < 3); 第五关 margin of safety as the **historical percentile** of P/E, P/B, yield and FCF yield; quick veto: 3 years of negative FCF | Own-history multiples (CN: RPT_VALUEANALYSIS_DET by trade date, which we already call daily; US/HK: annual history × Yahoo monthly prices) | The numeric parts yes; management, moat and the mirror test no |
| **era-alpha** | Don't buy when P/E is more than 3σ above its own historical mean. Growth quality: revenue growth backed by cash flow growth. | Own-history multiples; OCF growth vs revenue growth | The numeric rules yes; industry maps and expert calls no |
| **income-investment** | Dividend traps: net-income payout and FCF payout above 100%; sector-specific measures (REIT FFO, bank capital); resources on mid-cycle cash flow | dps_ttm (have it), FCF (Phase 7) | The payout rule yes, as a 低信心 flag for high-yield holds |
| **earnings-review** | Per-company reading of filings | none | No (per company) |
| **thesis-tracker** | A mechanical version: check every pick's re-check trigger daily (price below fv_low, profit turning negative) and list fired triggers | picks.csv + prices | Yes, rule-based (Phase 9) |
| **thesis-drift** | Separate fact changes from wording changes. Analogue: alert when a stock's fair value moves more than 30% day-on-day with a flat price, which means a data change | snapshots | Yes (Phase 12) |
| **dyp-ask** | A Duan Yongping Q&A persona | none | Not applicable |
| **portfolio-review** | Concentration: today lithium appears in both US and CN buys (SQM, 天齐, 盐湖) | needs a cross-market sector map | Possible, low priority |
| news-pulse, management-deep-dive, deep-company-series, investment-research/team, earnings-team, industry-research, bottleneck-hunter, private-company-research, wechat-article, investment-memo-craft | Per-company or narrative research | | No (rule 3) |
| **ai-berkshire tools** | `financial_rigor.py verify-market-cap` (price × shares vs reported market value, more than 5% off → check the share count): do this market-wide (HK price × shares vs Eastmoney's market value). `terminal_value.py`: justified P/E = (1 − g/ROIC)/(r − g) with r − g ≥ 5 points | | The market-cap check yes. The justified P/E as a flag only (the Phase 2/5 experience: an absolute anchor with one r per market flags too many stocks) |
| **a-stock-data**, endpoints worth adopting | ① 申万 classification file (swsresearch `StockClassifyUse_stock.xls`, readable with xlrd, already a dependency): L1/L2 codes for CN peer-group merging. ② 业绩预告 RPT_PUBLIC_OP_NEWPREDICT, market-wide by report date: flag buy/hold candidates whose pre-announced (扣非) profit drops, ahead of the report. ③ Tencent batch quotes as CN's second source. ④ Eastmoney valuation history by date for own-history P/E and P/B (no new dependency; baostock would need approval). ⑤ Lockup expiries RPT_LIFT_STAGE and share pledges RPT_CSDC_LIST as 低信心 flags (low priority). ⑥ 扣非 profit: not documented in the skill; RPT_LICO_FN_CPD may have `DEDUCT_BASIC_EPS`, and RPT_F10_FINANCE_MAINFINADATA (used per stock in ai-berkshire's ashare_data.py) has 扣非 fields. Verify while building | | Yes (endpoint reference) |

**Where your request conflicts with rule 3 (you answered in D3; the deep-dive lane in A3 is my proposal):**
- Running investment-checklist, earnings-review, news-pulse or investment-research on each day's picks, as a deeper AI
  note or a pick filter, is per-company deep research. Rule 3 forbids it, and it breaks the ~60-calls-a-day and 30 s
  reply budget. My recommendation: keep them outside the pipeline, as tools you run by hand on a pick you're
  considering.
- Moat, management and "can I explain the business" judgments can't be made by rule. Making them with DeepSeek per
  company would also stretch rule 2 (the LLM may flag swaps only for data and event reasons).
- `~/ai-berkshire/data/morningstar_fair_value_20260519.csv` holds analyst fair values. PLAN Method 4 says target
  prices are never used. At most a one-off calibration check, and it is 5 months old.
- quality-screen's 10-year ROE needs multi-year data. That is a new data path, not a new dependency (Phase 7).

## B5. Other things to improve

**Robustness**
- The spike-check bypass described in B1 (fixed in Phase 7).
- `run --market X --no-notes` replaces today's report.pdf for all markets with template notes, and the listener sends
  that. Write it to a separate file (`report_nonotes.pdf`), or never replace a report that has AI notes.
- No day-over-day drift alarm (Phase 12).
- Show the age of the cache, not just "fetch failed today", so a weekly source that breaks silently becomes visible.
- `--no-notes` and API-failure runs log unflagged picks to data/picks.csv; after the Phase 7 fix this goes away.

**Tests** (rule 7: math, parsers, one end-to-end run)
- The value and score tests use only the CN sample. Add small US and HK samples for value() and score().
- Missing tests: a no-notes run still applies checks 1-2; the quality-score spread is similar for financials and
  non-financials; no fit with a non-positive ROE coefficient is used; displayed upside respects the cap.

**Report readability on the phone**
- A4 at 9.5 pt is 11 pages and needs pinching on a phone. Use a phone-sized page (e.g. 110 × 200 mm, 11-12 pt), the
  overview first, one card per screen.
- False precision ("3,086.52"): use 3 significant figures and cap the printed upside ("> +100%" or after shrinking).
- Say why a pick is 低信心 ("周期高点 / 同业组过小 / 仅一种估值视角"), and which lens priced it.
- The DeepSeek note repeats the model's claim ("估值明显低于同行" for MU). Pass the red flags into the prompt so the note
  states the uncertainty. Numbers still come from code.
- The text summary is 3,277 of 4,000 bytes; one line per market about low conviction fits.

**Tracking**
- The 15-picks-per-market scorecard needs about a year to say anything. The snapshots already hold every valued stock
  daily: rank correlation (IC) and decile spreads of upside, composite and each z-score against 1w/1m/3m forward returns
  give evidence within weeks (Phase 9).
- Add an equal-weight universe benchmark next to the cap-weighted index (CN picks are mid-caps, compared with CSI 300).
- Split the results by method, tier and conviction. Add fv_low, fv_high, upside, method, tier and flags to
  data/picks.csv, which is kept forever while snapshots expire after 400 days.
- Measure from the next close (or open) after the report, not the price-date close.

**Smaller items**
- The residual-income cross-check is computed but unused. Removing it saves about 40 lines toward the budget.
- Cross-market theme concentration (lithium in US and CN).
- HK gross margin isn't comparable across reporting formats: use it in the quality score only within groups, or drop it
  for HK.
