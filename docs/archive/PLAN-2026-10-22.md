# Plan

## Status
- Adopted 2026-10-22 (your call), replacing the v1-v3 plan (Phases 1-13), which is kept in docs/archive/PLAN-v1-v3.md as reference only. The universe build and metrics, the data cross-checks, the event layer and the deep-dive lane stay as built; their details are in the archive (Methods 1-3, 13, 14, 15).
- Stage 1 (data fixes, the score and the new report): **closed 2026-10-22 as a fail**, after the corrected test (your OK; Evaluation, "Corrections"): CN and HK fail only item 2 (their portfolios beat 79% and 86% of random portfolios from the same funnel, under the 90% line; CN +2.9% a year over the CSI 300 fund with half its drawdown, HK +5.6% over the Tracker Fund), the US fails four items, so no buy list ships; CN's avoid list passed its own check in all four sub-periods, but the stage review found that largely in-sample by construction, so it isn't standalone evidence. The review's reading: CN's edge sat in the trend signals and reversed in 2024-26 (short of edge), HK looks under-powered, and a 10-name portfolio can't confirm an edge under about 4-5% a year over random picks. No further variant runs on this data (docs/BACKTEST.md section 19). Earlier on the same day: the ship bar fails in every market, in both the first run (fresh monthly lists) and the registered holding-rule run (docs/BACKTEST.md section 19), so the report doesn't switch and the keyword reply stays off. CN: the portfolio beat the CSI 300 index fund by +6.7% a year after costs (4/4 sub-periods) but only 78% of random portfolios from the same funnel, and its names fell 25%+ as often as random ones; HK: +5.6% a year over the Tracker Fund with a third of the random falls, but 81% of random portfolios and momentum alone returned more; US: nothing beat SPY. Done: the preferred-dividend fix (deductions above zero 178 → 116, at the cap 41 → 3), backtest/stage1.py and stage1_hold.py, the index-fund benchmark, the stage-reviewer agent. Not done, by rule 12 (they change nothing the stage-1 score uses), for your OK: consensus fiscal years on the calendar (moves to stage 5) and raw inputs (the score is rank-based; winsorizing ties 1-2 names a date at the extremes). Housekeeping (your OK, 2026-10-22): the 06:30 job fetches the data only (no report, no v1 or v3, no DeepSeek) until a report ships; the 10 worktrees of Phases 7-13 removed (4.2 GB; their branches stay in git); data/backtest (382 MB) in main.
- Stage 3 (the earnings engine, your call 2026-10-22: it runs now, stage 2 waits until some market's list passes): **closed 2026-10-22 as a fail** after its registered test (Evaluation, "Stage 3's test") ran once (docs/BACKTEST.md section 20). (a) The forecast loses to "margin persists" at 1 year in every market (CN +22% error, US +5.5%, HK +88%) and is lower at 3 years only pooled (CN −2.5%, US −2.2%) in 5 of 11 years, under the half the bar needs; (b) the implied return is a value signal distinct from trend (rank correlation with 12-1 momentum −0.22 in CN) but positive in only 2 of 4 sub-periods in CN and HK, and in the US it doesn't beat B/P; (c) it enters the score only in the US, where it helps in 2 of 4 sub-periods. So the score stays stage 1's, no buy list ships, and the report doesn't switch. The stage review found the levels wrong (non-financials fade to sector medians that include small loss-makers; HK's flat loss flag), so the fail says more about this specification than about forecasting earnings. "What the price implies" wasn't built (no card ships). No variant runs on this data.
- Stages 2, 4 and 5: not started.
- Until stage 1 ships, the 06:30 job only fetches the data and cleans up (launchd/com.stockreport.daily.plist), and the keyword reply stays off.

## Why a new plan

v1 to v3 tried to compute a fair value per stock that looks sensible. Thirteen phases in five days added rules after specific names looked wrong, and the registered bars mostly failed. Measured on the 2026-10-20/21 snapshots and in docs/BACKTEST.md:
- **The fair value isn't a forecast.** A valuation gap has closed 0-5% of itself within a year (BACKTEST.md section 17), so "+117% upside" on Microsoft has historically meant about +1-2% over the market in a year.
- **v3's levels are plugged.** Its discount rate is solved from its own values: 46 of the 100 largest US stocks sit at 5.5%, against a 5.15% 10-year yield. Its ranking is close to plain book-to-price (rank correlation 0.81 in CN, 0.80 in HK).
- **The live model isn't the backtested one.** The live engine uses analysts for 93% / 88% / 74% (US / CN / HK) of valued stocks, the backtest for none. Their rankings correlate 0.71, and single names flip (Micron −5% vs +225%).
- **Wrong earnings go in.** A preferred-dividend bug halves earnings for 38 US companies (89 affected), and forecast fiscal years aren't placed on the calendar.
- **What held up was simple:** cheapness, the 6-12-month price trend, and the warning signs before 25%+ falls. Volatility, a loss, a falling price and CN limit-up days ran at 1.2-2.1× the market's blow-up rate in every market and both samples. The confidence labels didn't predict accuracy.

## Goal and how you use it

- You buy a handful of names per market and hold them for months. "Sell" means avoid, or sell if you own it. Shorting, where it's possible, is a bonus.
- Success: the names you'd buy beat their market's total-return index over 6 and 12 months, on average, with fewer 25%+ falls than the market.
- Realistic size of an edge: a few percent a year, with losing stretches. No single list is a guarantee.
- Delivery as today: a WeChat keyword gets a text summary and a PDF, for US, HK and CN, in Chinese.
- A new report as soon as the evidence supports one: stage 1 ships it; later stages only improve it.

## The report, per market

- **买入候选 (buy shortlist):** 10 names, ranked, at most 2 per industry. You pick a handful. Why 10 rather than 5:
  - a 10-name list is steadier (the 5-name lists' 6-month beat rates ranged 41-71%);
  - you can add what you know (industries you understand, what you already hold);
  - ranks 6-10 are slightly weaker on average, and each card shows its own expected return.

  The length doesn't remove extreme picks. Ranking on several signals at once does: the top names look good on most signals rather than extreme on one, and no single signal can carry a name.
- **持仓检查 (your holdings):** every name in data/holdings.csv (a small `hold CODE` / `hold CODE --sold` command), marked 继续持有 / 复核 / 卖出 by the holding rule. Without the file, it checks the buy-list names of the last 6 months.
- **回避 (avoid):** 10 names among the market's 400 largest, at most 2 per industry. Each is marked 可做空 where shorting is possible:
  - US: shortable through brokers;
  - HK: HKEX's list of designated securities (endpoint to verify);
  - CN: not offered, since securities lending for individuals was largely halted in 2024 (to verify).
- **The 持有 bucket goes.** "Good companies priced about right" isn't an action for a buy-and-hold investor; the holdings check replaces it.
- **Each card shows:**
  - the price;
  - the expected excess return over the index for 6 and 12 months, with the range history gave stocks with that score, e.g. "+3%（历史区间 −12%~+16%）";
  - the 2-3 signals behind it, in plain words;
  - what the price implies: the margin and growth the price needs, against our forecast (from stage 3);
  - the key risk (the largest warning sign) and the re-check trigger;
  - the reviewer's line: 市场可能在担心 … (with its quoted source), or 审核未见重大风险;
  - the AI note (words only), and the 近期事件 and 深度核查 lines as today.
- **审核剔除 (removed by the review):** the names the review took out, each with its reason and quoted source, and the name that replaced it.
- **Text summary:** at most 4,000 bytes. Today's 45 lines take 3,015 bytes. 60+ names need compact lines (short names, no repeated action word); if they still don't fit, the avoid names go in the PDF only.

## Method

### Signals

Each signal is defined from published evidence before any test and isn't tuned. Each is computed within each market, point-in-time.
1. **Cheapness:** earnings yield on trailing core earnings (CN 扣非) and book yield. From stage 3, the expected return implied by our own earnings forecast replaces both, if it does better.
2. **Profitability and cash backing:** gross profit ÷ assets where assets exist (US; CN from the balance-sheet table, to verify), else ROE and gross margin; plus accruals, i.e. (net profit − operating cash flow) ÷ revenue (Novy-Marx 2013; Sloan 1996).
3. **Price trend:** the 12-1-month return and the 6-month return.
4. **Risk:** 1-year volatility, a loss over the last 12 months, and CN limit-up days in 3 months.
5. **Share issuance:** the 1-year change in the diluted share count (US; CN and HK where the share history exists).
6. **Analysts (stage 5):** the 4-week revision of next year's EPS, and the gap between consensus and our own forecast (So 2013: stocks where analysts are more optimistic than a fundamentals model tend to lag). Analysts never enter the valuation itself, so the valuation is the same model live and in the backtest.

### Combining

- Each signal becomes a percentile within its market on each date.
- A signal enters a market's score only if its top fifth beat its bottom fifth, with the expected sign, in at least 3 of 4 sub-periods (2019-20, 2021-22, 2023, 2024-26) in that market.
- Equal weights among the signals that enter; no weight fitting. Because nothing is tuned to the backtest, the backtest can decide whether to ship, without waiting for a live record.
- Expected excess return, per market: the line of realized 6- and 12-month excess return on the score percentile over all dates, shown with the realized 25th-75th percentile for the stock's score tenth.

### Lists

- **The funnel:**
  - the data cross-checks pass;
  - investable: the largest 300 (CN, US) / 200 (HK) for buys, with the liquidity floors as today;
  - blow-up chance under twice the market's (Method 17's fit on volatility, a loss, the 6-month trend and CN limit-up days);
  - profitable on core earnings over 3 years, or (from stage 4) a forecast recovery.
- **Buys:** the 10 highest scores among the funnel's survivors.
- **Holding rule:**
  - 继续持有 while the name stays in the top 30% of the score and passes the funnel;
  - 复核 when it falls into the middle, or on a new warning sign (analysts cutting 10%+, an abnormal move without a filing, a review note, a deep-dive veto);
  - 卖出 below the median, when it fails the funnel, or on a review veto.
- **Avoid:** among the 400 largest, the highest blow-up chances, and the bottom scores that carry a warning sign.
- **Shorts (stage 5):** the avoid names count as a short list only if, in the backtest, they fell in absolute terms over 6 months net of a borrow cost; otherwise they stay "avoid".

### Results review (only when you ask for a report)

The numbers can't see a fraud investigation, a going-concern doubt, a takeover at a fixed price, or a story the market is worried about. A reviewer reads what the numbers can't, before you see the lists.
- **Who reviews:** DeepSeek, already used for the notes. Temperature 0, a fixed checklist, JSON out. Every finding must quote a filing or headline, and code checks the quote (quotes.py, as the deep-dive lane does). It never changes a number (rule 2).
- **What it reviews:** per market, the 10 buys, the next 5 runners-up, the 10 avoid names and your holdings.
- **When it runs:** only when you send the keyword. The 06:30 build makes no DeepSeek calls at all; it fetches the data and builds the lists and cards with code. The AI notes and the deep dives move to the keyword too.
  - Each review is cached per stock with what it read. A name is reviewed again only when it is new to a list, a new filing or headline has appeared since its last review, or the review is more than 7 days old. Lists change slowly (at most a few names a day), so most requests need a handful of calls.
  - Order and time budget: buys first, then holdings, then the avoid names, with up to 10 calls at a time and a 20-second budget. A name not reviewed in time shows 审核进行中 on its card and is finished in the background for your next request. Then the PDF is rendered and both messages go out.
  - Expected time (estimates, measured in stage 2): a request on a warm cache adds about 2-5 seconds; the first request after a week away is about 20-25 seconds of review, plus a few seconds to render. Deep dives read whole filings (2-15 s each), so they finish in the background when the budget runs out and show on the next request. If DeepSeek is down or slow, the report goes out without the review, marked 审核暂不可用.
- **What it reads:** the stock's non-routine filings of the last 90 days from the event feed (CNINFO, HKEXnews, SEC), plus headlines from a free news source (CN: Eastmoney or 财联社, as the a-stock-data skill documents; HK and US: to verify), plus the card's numbers.
- **Hard red flags remove a buy** (the next-ranked name takes its place, listed under 审核剔除), turn a holding into 卖出, and are noted on an avoid name:
  - a regulator's investigation, a fraud finding, or a Wells notice;
  - a non-standard audit opinion, or the auditor resigning;
  - a going-concern doubt, or a default on debt;
  - delisting or ST risk, or a trading suspension;
  - a takeover or privatisation at a fixed price (the upside is capped);
  - sanctions or a ban naming the company.

  These are discrete facts with a quoted source, and the old checks 1-3 and the deep-dive vetoes fold into this list.
- **Soft concerns only annotate:** an industry downturn, a lost customer, a guidance cut, management leaving, litigation, a one-off gain. The card says 市场可能在担心 … with the source, and a holding gets 复核. They don't remove a name. Cheap stocks carry bad news by nature, and that is where cheapness pays off on average. The score's trend, risk and (from stage 3) earnings-forecast signals already price the systematic part of "troubled".
- **Data check:** if the latest filing contradicts a card's figure by 20%+, the name is dropped as data_suspect, and the next one takes its place (rule 5).
- **Limits:** the review can't be backtested. An LLM reading old news knows what happened next, and there's no free point-in-time news archive. So its powers stay narrow. The scoreboard follows each removed name against the name that replaced it.
- **Cost:** nothing on days you don't ask. On a day you do, a few calls for what changed, and about 120-130 calls (cents) after a long gap.

### Earnings engine (stages 3-4; from the two reviews)

- **Correct inputs first (stage 1):** net income, common-share income and book from the same fiscal-year row; consensus fiscal years placed on the calendar; raw, not winsorized, inputs.
- **Earning power:** a sales forecast times a lasting-margin forecast, refit each year on each market's panel from what was public then.
  - The margin's level persists and its unusual changes partly reverse; profit that cash doesn't back counts for less (Nissim–Penman; Hou–van Dijk–Zhang 2012).
  - Banks, insurers and brokers are forecast on ROE's level and change instead.
- **Implied expected return:** the rate at which book plus discounted residual income on that forecast equals the price. After year 5, margin and growth fade to the sector's long-run levels over 10 years. No discount rate is chosen: the rate is the answer.
- **What the price implies:** the margin, or growth, at which the implied return equals the market's median, shown against our forecast, with the share of similar company-years that reached it.
- **Reinvestment and financing (US first):** growth needs capital (capital intensity × the revenue added); it is financed by retained earnings, then debt, then new shares at today's price, which dilutes each share.
- **Losses and recoveries:** loss years are part of the margin fit, so the way back is estimated, not assumed. A funding gap is raised in new shares. Labels: 可恢复 / 需融资 / 持续亏损.
- **Deep-dive facts:** a one-off item quoted from the filing and verified by code may be removed from the earnings base, as CN's 扣非 already does for every A-share. Live only, at most 3 a day per market.

## Evaluation (registered before anything is built)

A benchmark is in the bar only if losing to it would change what we do. v1 isn't: we wouldn't go back to it if it won. Its buys beat the index over 6 months only a few points more often than the average stock in the US and HK, and less often in CN (out of sample: US 50.4%, CN 37.8%, HK 50.4%, against 46.1% / 41.7% / 44.1% for all stocks), so beating it proves nothing. v1 and v3 leave the bar; their numbers may be shown for reference.

- **The test portfolio is what you'd do:**
  - each month-end, per market, buy the 10 buys equal-weight (and a top-5 variant), then hold or sell by the holding rule;
  - returns include dividends; after costs of a round trip of 0.2% (US), 0.3% (CN) and 0.6% (HK), as in Method 17.
- **The benchmarks, each with the decision it drives:**
  - **The total-return index** (US ^SP500TR; CN and HK: the price index plus its dividend yield until a free total-return series is verified). This is your real alternative, an index fund. Losing to it: don't use the list; buy the index.
  - **Random lists from the same pool:** each month, 1,000 random 10-name lists drawn from the funnel's survivors (at most 2 per industry), held the same way. Losing to them: the score has no skill, whatever the market did. It answers "is this luck?" in plain terms: our list beat X% of the random lists.
  - **The funnel alone:** random lists from the funnel against random lists from the whole investable universe. Losing: the filters (blow-up chance, profitability) don't cut falls; drop them.
  - **Simpler versions:** stage 1 against single-signal lists (plain E/P, plain B/P, 12-1 momentum) under the same funnel; each later stage against the stage before it. Losing: ship the simpler version (a tie goes to the simpler one).
- **Measures:** 6- and 12-month excess return over the index (mean and median); the share of months beating the index; the share of random lists beaten; 25%+ falls; the worst drawdown; turnover. Ranges come from a date-block bootstrap. For each signal and for the score: top fifth minus bottom fifth.
- **Samples:** about 8 years of month-ends per market (CN from 2019, US from 2018, HK from 2016), reported by sub-period. CN is point-in-time, with nearly all delisted names, so it is the main test. The US and HK backtests hold today's listings only, so they are secondary. All of it was looked at in Phases 9-13; that's why nothing is tuned to it.
- **Ship bar (stage 1).** In CN and at least one other market, after costs, every item must hold:
  1. the mean 6-month excess return over the index is above zero, and positive in at least 3 of 4 sub-periods;
  2. the list beats at least 90% of the random lists over the whole sample, and the random median in at least 3 of 4 sub-periods;
  3. it is at least as good as the best single-signal list (otherwise that signal ships instead);
  4. its 25%+ falls are no more frequent than the random lists';
  5. the expected-return line slopes the right way in at least 3 of 4 sub-periods.
- **Corrections after the first stage-1 test (your OK, 2026-10-22; registered before the corrected run).** The first runs
  (docs/BACKTEST.md section 19) failed, and the diagnosis found three items that measured the wrong thing. The pass levels
  above stay as they are; what each item measures changes, each for its reason:
  1. *Signals are judged on what they are for.* Return signals (E/P, B/P, profitability, accruals, the two trends,
     issuance) enter on the mean 6-month return as before. Risk signals (volatility, a loss, CN heat) enter if their safe
     side had fewer 25%+ falls than their risky side (lowest-volatility fifth against the highest; without a loss against
     with one; without 2+ limit-ups against with) in at least 3 of 4 sub-periods. Reason: their job in your goal is to cut
     big falls; judging them on return left CN's score all trend, and its picks fell as often as random ones.
  2. *Random portfolios use no score.* They buy at random from the funnel and sell at random: names that leave the funnel
     are sold, and each month a random number of the rest (binomial, at the score portfolio's average monthly turnover)
     too. Reason: in the first holding-rule run they sold by our score, so they shared its skill and item 2 compared the
     score with itself. Their turnover is at least the score portfolio's, so they pay at least as much in costs.
  3. *Simpler versions are compared on your whole goal.* A single signal beats the score only if its portfolio has the
     higher return and no more 25%+ falls; then it ships instead. Reason: HK's momentum had the higher return with
     falls 22.7% of the time against the score's 3.4%.
  The portfolio is the registered holding-rule one (backtest/stage1_hold.py's rules). The avoid list ships in a market
  that passes if its names trailed the 400 largest on the mean 6-month return and fell 25%+ more often, in at least 3 of
  4 sub-periods. A market that fails shows no buys: its section says no list beat its index fund and names the fund
  (SPY, the 2800.HK Tracker Fund, the 510300 CSI 300 ETF). The report still switches only if CN and one other market
  pass. These runs are on data looked at before, so a pass here is weaker evidence than a first run; the report says so.
- **Adding a part (stages 3-5).** It must:
  - (a) forecast what it claims to better than the simple alternative. For the earnings engine, that's earnings 1 and 3 years ahead against "this year's margin persists": this is how the valuation approach itself is judged;
  - (b) raise the list's 6-month excess return, or cut its falls, against the same score without the part, without worsening the other, in CN and one other market, in 3 of 4 sub-periods.
- **Stage 3's test (registered 2026-10-22, committed before anything that produces results was built).** Each part runs
  once; no variant after seeing results. Code in backtest/ (outside the app's line budget): earn_panel.py (the panels),
  earnings.py (the forecast and part a), implied.py (the implied return), stage3.py (parts b-d). No analyst data anywhere.
  The open definitions, fixed here with their reasons:
  - *Panels*, one row per company and fiscal year, each public from: CN 业绩报表 since 2009 (core earnings = 扣非, as
    history.cn_years; book = BPS × profit ÷ EPS), the notice date. US: the SEC frames 2009-2025, every us-gaap filer
    with the dead ones (net income, equity at the calendar year end, revenue as fetch/frames.py, gross profit else revenue
    less the cost of revenue, operating cash flow), each fact's period end + 120 days (10-K deadlines are 60-90 days),
    filers with $50m+ revenue in the base year (the base rates' floor: shells and funds out). HK: Eastmoney's annual rows
    since 2015, 90 days after the period. The US stocks' own inputs come from us_annual (their fiscal years and filing
    dates, continuing operations less preferred dividends, book net of preferred, 20-F filers too), with the coefficients
    fit on the frames (dead filers in the fit, not survivors only). Operating income is fetched but unused: CN and HK
    have none, and one model serves every market.
  - *Financials* (banks, brokers, insurers) are forecast on ROE: CN 申万 48, 4901, 4902 and HK the industry types of
    config `financial_industries_hk` (both as the snapshots); US SIC 6000-6411 (the frames carry no Nasdaq industry; real
    estate, REITs and funds aren't financials). *Sectors:* CN 申万 level 1 at the year end, US the Fama-French 12
    industry of the SIC code, HK the first level of Eastmoney's industry type (as baserates.py). Sector medians are taken
    within the group (financials or not); on a date, over the rows public by then, for the stock's base year (10+
    companies, else the year before, else the market's).
  - *Non-financials:* earnings = revenue × margin (core earnings ÷ revenue). For each horizon h = 1..5 years one direct
    OLS fit of margin(t+h) on margin(t), its change from t−1, accruals ((earnings − operating cash flow) ÷ revenue), the
    gross-margin change, a loss flag (earnings < 0) and the sector median margin; and one of revenue's log growth t→t+h
    on its log growth t−1→t and the sector median log growth. A missing change, accrual or gross margin counts as 0, in
    the fits and the forecasts alike. *Financials:* ROE(t+h) (earnings ÷ the previous year-end book) on ROE(t), its
    change from t−1, the loss flag and the sector median ROE.
  - *Fits:* every 30 June, on every pair (base year t, outcome t+h) whose outcome was public by then (an expanding
    window, Hou-van Dijk-Zhang style); at least 300 pairs, else that horizon has no fit yet. Training values are
    winsorized at the fit sample's 1st and 99th percentiles, for stable coefficients; forecasts take each company's raw
    inputs (the plan's "raw, not winsorized").
  - *Book path:* book grows by earnings less a net payout, paid on positive earnings only (clean surplus). Net payout =
    1 − book growth ÷ earnings over the last 3 years, within 0-1; without 3 years of book or with 3-year earnings ≤ 0,
    the sector median. Reason: CN and HK have no free dividend history; this also counts buybacks and share issues.
  - *Implied expected return,* per stock and month end: the rate r at which P/B (stage 1's B/P, from the snapshot)
    equals 1 + Σ (earnings_k − r × book_k−1) ÷ (1+r)^k over years 1..T, plus year T's residual income held flat for ever
    (÷ r; Gebhardt-Lee-Swaminathan's convention, since a growing perpetuity needs a chosen growth rate). Years 1..H come
    from the fits (H = the longest horizon fit by then, at most 5); margin and revenue growth (financials: ROE) then fade
    in a straight line over 10 years to the sector's long-run level (the median company-year of the last 10 fiscal years
    public by then, 30+ company-years, else the market's), so T = H + 10. Inputs: the latest fiscal year public on the
    date, at most 18 months old; the forecast, in units of that year's book, is applied to the snapshot's latest book.
    r is read on a grid from 0.5% to 50% in 0.25-point steps, linear in between: the first rate at which the value falls
    to the price (below 0.5%: 0.5%; never: 50%; ties at the ends). No r when book ≤ 0 or the inputs are missing; in the
    score a missing signal counts as the middle, as in stage 1.
  - **(a) Forecast accuracy, in every market** (the engine's own test). Forecasts made on 30 June of t+1 from base year t
    with that day's fit, for every base year with a fit and an outcome (at most CN and US 2010-2024 at 1 year, 2012-2022
    at 3 years; HK 2016-2024 and 2018-2022); the US on the frames (dead filers included). Evaluated per base year: the 800
    companies with the largest book among those public by the forecast day with revenue > 0, book > 0 (financials: the
    previous book too) and an outcome. Error: |forecast earnings(t+h) − actual| ÷ book(t), each capped at 1 (else a few
    tiny books decide the mean); financials' earnings = ROE × the forecast book path, the same payout on both sides.
    Against "this year's margin persists, revenue at the sector median growth" (financials: ROE persists). Pass: at 3
    years the mean error is lower, pooled over the base years and in at least half of them; at 1 year it is at most 2%
    above the benchmark's (relative; a near-tie counts as not worse). The median error is shown, not deciding.
  - **(b) The signal across all stocks, CN and one other market.** On each month end, the stocks of the stage-1 frame
    with the implied return, plain E/P and plain B/P (stage 1's) and a 6-month return, each signal a percentile within
    that set. Its top fifth minus bottom fifth on the mean 6-month return (pooled over the sub-period's dates, as stage
    1's test) and its mean monthly rank correlation with the 6-month return are both positive in at least 3 of 4
    sub-periods (2019-20, 2021-22, 2023, 2024-26), and both higher than plain E/P's and than plain B/P's in at least 3
    of 4 ("on the same measure"). Shown, not deciding: its mean rank correlation with 12-1 momentum and the 6-month trend
    per sub-period, since CN needs an edge that isn't trend.
  - **(c) In the score, CN and one other market.** Stage 1's corrected score with the implied return in place of E/P and
    B/P (a return signal under the corrected inclusion rule: top fifth minus bottom fifth positive in 3 of 4 sub-periods)
    against stage 1's corrected score as it ran (E/P and B/P where they entered); the same funnel, holding-rule portfolio,
    costs and index fund. Per sub-period: the mean 6-month return over the fund from its start months, and 25%+ falls per
    entry for the names entered in it. A sub-period counts when one is better and the other no worse (return higher and
    falls not higher, or falls lower and return not lower); pass in at least 3 of 4. Where the implied return doesn't
    enter, the score is unchanged and (c) fails.
  - **(d) The shipping check, unchanged:** stage1_fix.py's items 1-5 with the new score (random portfolios with no score
    at its turnover; plain E/P, plain B/P and 12-1 momentum as the simpler versions), CN and one other market.
  - *Decision.* The engine enters the score only if (a) passes in every market and (b) and (c) pass in CN and one other
    market. A buy list ships only if the engine enters and (d) passes in CN and one other market. Every part's numbers are
    reported whatever the outcome; the runs reuse data looked at in Phases 9-13 and stage 1, so a pass is weaker evidence
    than a first look, and the report says so.
- **Bug fixes** are adopted because they are correct; their effect is reported, not tested.
- **The results review (stage 2)** is adopted on its narrow mandate, because it can't be backtested; the scoreboard follows what it removes.
- **Scoreboard:** `track` keeps scoring every list (and every removed name against its replacement) against the index and the random lists, and the report shows it once a month. It never holds up a stage or a decision: it is there so you can see how the picks are doing, and to catch a fault in the live data that a backtest can't show.

## Keeping the project on course

The old plan drifted: rules added after single names looked wrong, and targets that made results look plausible (median upsides, outlier labels) rather than more useful. Two guards, both cheap:
- **Usefulness first (a rule in AGENTS.md).** A change is worth doing only if it changes what you'd buy, hold or avoid, or the expected return shown, and it passes its registered test. Work whose only effect is that results look more plausible or better explained is not done: normalizing medians, outlier labels, plausibility targets, or a rule added because one name looked wrong.
- **A fresh-eyes review at the end of every stage.** A reviewer agent with fresh context (defined in .claude/agents/stage-reviewer.md, written in stage 1) reads the plan, the stage's diff, its test results and the scoreboard, and answers a fixed checklist. Its answers go into the stage report to you:
  1. Did the stage change what's bought, held or avoided, or the expected return shown? If not, why was it done?
  2. Did it pass its registered test, run once? Was any threshold chosen after seeing results?
  3. Was any rule written in response to specific names?
  4. Complexity before and after: config values, special-case rules, app lines.
  5. Does every number on a card come from code and data (rule 2)?
  6. Are the live lists within the backtest's range, and is there any sign of a data fault?
  7. What would a sceptical investor ask about today's lists? Spot-check 3 buys and 3 avoid names against their latest filings.

  For the larger stages, a second model (e.g. Codex) reviewing the same diff is worth it: in this review, the two models caught different things (Codex found the preferred-dividend bug).
- **No self-modifying loop.** The reviewers propose; you decide; any change passes its registered test. Retuning automatically on live results would chase noise, and it repeats the old pattern of reacting to the latest names.

## Stages (one per session; each done when its test has run once)

1. **Data fixes, the score and the new report** (ships in this stage if it clears the bar).
   - The preferred-dividend bug, consensus fiscal years on the calendar, and raw inputs (pytest on saved samples).
   - data/backtest rebuilt in main (today it exists only in old worktrees); total-return benchmarks verified.
   - The portfolio test: monthly buys, the holding rule, costs, random lists. Checked against Method 17's numbers for today's v3 lists within 1 point (a check that the test code is right, not a benchmark).
   - Signals 1-5 (no new valuation engine yet), the funnel, buys / holdings check / avoid, and cards with the expected return; then the ship bar, run once.
   - The daily build stops calling DeepSeek. Until stage 2 (the next session), the cards carry the code's lines only (signals, key risk, 近期事件 with recent filings), with no AI note.
   - The stage-reviewer agent definition, used for this stage's own review.
   - If it passes: the report switches; v1 and v3 leave the daily build, and their code is deleted as the line budget needs; the keyword reply comes back after a test send with your OK (rule 9).
   - If it fails: I report which item failed and in which market; the report doesn't switch, and the keyword reply stays off.
2. **The results review, on request:** the red-flag checklist on buys, runners-up, avoid names and holdings; the AI notes and deep dives back, all run from the keyword with the cache and the 20-second budget; a free news source per market verified; quote checks; 审核剔除 and the reviewer's card line.
   - Done when its tests pass on saved filings and headlines (a quote not in the source is rejected; a hard flag removes a buy; a soft concern only annotates).
   - Also: the keyword reply is measured at under 30 seconds both on a warm cache and on a cold one (every review missing).
3. **The earnings engine:** the sales × lasting-margin forecast, the implied expected return, and "what the price implies". Done when its test (a) + (b) has run once; if it passes, the report uses it.
4. **Reinvestment, financing, losses and recoveries:** US first; CN and HK need a statement fetch (capex, cash, debt), with your OK first. Done when its tests have run once.
5. **Analysts and shorts:** revisions and the analyst-vs-model gap, measured on CN's 2026 consensus window and the weekly snapshots collected since 2026-10-19; shortable flags; the short test. Done when its tests have run once.

## Decisions taken in this plan (override any)

- 10 buys, a holdings check and 10 avoid names per market; no 持有 bucket.
- The card shows an expected excess return, not a fair-value price, so there's no discount rate to choose.
- Analysts are separate signals, never blended into the valuation.
- Verified one-off items may leave the earnings base, like 扣非.
- Equal weights among the signals that pass the sign test; no weight fitting.
- The results review removes names only on hard red flags with a quoted source; soft concerns annotate.
- DeepSeek runs only when you ask for a report (the review, the notes and the deep dives), cached, within a 20-second budget.
- A fresh-eyes review closes every stage; nothing changes the method automatically.
- Success is judged on the backtest against the index, random lists from the same pool and simpler versions of the method, never against v1 or v3; v1 and v3 keep running until stage 1 ships. No stage waits for a live record.

## Kept from the old build

- The fetchers and cross-checks; the history tables; the SEC frames with dead companies; the point-in-time CN panel.
- The backtest snapshots, with 6-month returns and worst month-ends.
- The event feed; the deep-dive lane with its quote checks; the verdicts.
- The DeepSeek notes and flags (folded into the results review).
- WeChat and PDF delivery.
- The habit of registering a test before running it.
- Method 17's blow-up fit, reused in the funnel.

## Decisions kept from the old plan
- Python 3.12 + uv. The old Swift project is archived read-only at ~/Developer/EquitySignalsClawbot-legacy.
- Delivery is 2 messages per keyword: a text summary (at most 4,000 bytes) + a PDF.
- WeChat bot limits seen in practice:
  - It can only reply after I've messaged it recently; sends failed 9–12 h after my last message.
  - A burst of more than about 3–4 messages fails.
  - So never send more than 3 messages per keyword.
- Order: CN → US → HK.
- AI notes come from the DeepSeek API (OpenAI-compatible) in v1.
- Universe: top 800 per market by market value, after filters.
- Report language: Chinese, with tickers as-is.
- Each market is valued in its own quote currency. There is no cross-market ranking.

## Storage and cleanup (disk must not grow without limit)
- Fetch only what changed:
  - Prices and quotes: daily.
  - Fundamentals: weekly (Sundays), or when a company has newly reported. They change quarterly, not daily.
- Raw responses: data/raw/<date>/. Extract the needed fields right away and keep only the extracted table.
  - Large per-company files (e.g. SEC companyfacts JSON, several MB each) are deleted at the end of the run that fetched them.
  - Everything else under data/raw/ is deleted after 7 days.
- Price history: one compressed file per market (data/prices/<market>.csv.gz), updated incrementally with the latest day. No daily full re-download, and raw kline responses aren't kept.
- Daily snapshot: data/snapshots/<date>/<market>.csv.gz with the computed metrics and scores per stock (a few hundred KB). Kept 400 days, for tracking and later method checks.
- Reports: reports/<date>/ (PDF, summary, picks CSV) kept 90 days. data/picks.csv is tiny and kept forever.
- Logs: kept 30 days.
- All retention periods are config values.
- `cleanup` runs automatically at the end of every `run`. `cleanup --dry-run` lists what would be deleted and the space it would free.
- After each run, log the total size of data/ + reports/. If it exceeds 2 GB, add a warning line to the report footer.
- Cleanup only ever deletes inside this project's data/, reports/ and logs/ folders.
- Phase 6 estimate (2026-10-17): price files ~33 MB (rolling 385 days), snapshots ~1 MB a day × 400 = ~400 MB, reports ~1.7 MB a day × 90 = ~150 MB, raw ~3 MB a day × 7 = ~20 MB; steady state ~0.6 GB of the 2 GB limit.
- Phase 11: data/events/<market>.csv.gz keeps 120 days of classified filings (the update drops older rows; ~0.2 MB for the first 10 days, so ~2-3 MB at steady state); data/deepdive/<market>/ keeps the verified facts per filing read (a few KB each, at most 9 a day, deleted after 400 days); filing documents are read in memory and never stored; data/verdicts.csv is tiny.
- History tables (Phase 7, data/history/, kept; cleanup doesn't touch them), for valuations v2/v3 and the backtest:
  - Phase 13: us_frames (SEC frames, every filer's revenue, net income and equity per calendar year 2009-2025, 2.1 MB; new years once, the last two again every 30 days), us_sic (SEC SIC code per filer with $100m+ revenue and per candidate, from the submissions files, once each), cn_sw (申万 classification change history, weekly), cn_annual back to 2009 (was 2015). Backtest only: data/backtest/us_quarterly.csv.gz (every US 10-Q/10-K period by filing date, 878 companies, 1.3 MB; companyfacts read once each and not stored); us_annual also carries R&D from that read (not refreshed).
  - us_annual: one row per company and fiscal year since 2015: revenue, gross and operating profit, net income (also to common and from continuing operations), operating cash flow, capex, dividends paid, diluted shares, equity, preferred, assets, liabilities, shares, in the reporting currency, with the first filing date. From the companyfacts files the weekly SEC fetch reads anyway; Yahoo for the companies SEC has none for (Sundays, every 90 days).
  - cn_annual: 业绩报表 for every fiscal year since 2015 with 扣非 EPS and weighted ROE (each year once; the latest weekly while its reports come in). cn_valuation: close, market value, shares, PE-TTM, PB-MRQ, PS-TTM on the last trading day of every half-year since 2018-12 (one fetch per half-year).
  - hk_results: Eastmoney main indicators since 2015 (amounts in CNY, as in the weekly table), fetched once and topped up from the weekly table.
  - us_monthly / hk_monthly and us_splits / hk_splits: ~11 years of month-end closes as traded and monthly total returns for the candidates, the index and the FX rates own-history P/B needs (HKDCNY=X; the US reporting currencies as <CUR>=X); new months on Sundays.
  - cn_forecasts: the market-wide 业绩预告 table, daily from a week before the newest notice (started with the last 400 days).
  - cn/us/hk_consensus: the consensus table appended once a week with its snapshot date, so revisions have a record.
  - Backtest tables (Phase 9, data/backtest, ~0.73 GB, not touched by cleanup and rebuildable with the commands in docs/BACKTEST.md): CN daily returns, closes and turnover 2018-01..2026-10 (one compressed matrix), Eastmoney valuation rows, 业绩报表 since 2009, balance sheets, 业绩预告 since 2017-10, 申万 history, report-archive EPS since 2025-06, the per-market month-end snapshots and v2 inputs, results. The ~2.8 GB of 通达信 packages were parsed in memory and never stored.
  - Measured 2026-10-18: 13.8 MB in all (hk_results 4.8, cn_annual 3.4, cn_valuation 2.6, us_monthly 1.2, hk_monthly 0.9, us_annual 0.6, cn_forecasts 0.4, consensus snapshots 0.06), plus 0.3 MB for 扣非 EPS and ROE in the weekly results tables; growth ~6 MB a year, mostly consensus snapshots and monthly prices. The first build with Phase 7 backfills them once (CN ~10 min; US ~13 min, SEC companyfacts read again for every company plus 1,100 monthly series; HK ~11 min). After that a weekday build adds under 1 s (业绩预告) and a Sunday ~15 s (new months, and re-asking Yahoo for the ~40 HK symbols it has no data for).

## Data sources (free; verify each endpoint while building)
- CN (changed in Phase 2, see below):
  - Universe and quotes: Eastmoney datacenter daily valuation table RPT_VALUEANALYSIS_DET (close, total market value, total shares, PE-TTM, PB-MRQ, industry BOARD_NAME = the same industry field as clist f100).
  - Quarterly results for all A-shares: Eastmoney datacenter 业绩报表 RPT_LICO_FN_CPD; debt/assets from RPT_DMSK_FN_BALANCE; cash dividends from RPT_SHAREBONUS_DET.
  - Analyst consensus EPS for the next three fiscal years: Eastmoney datacenter 研报一致预期 RPT_WEB_RESPREDICT (one market-wide table, refreshed weekly).
  - History (verified in Phase 7, 2026-10-18): RPT_LICO_FN_CPD has DEDUCT_BASIC_EPS (扣非 EPS) and WEIGHTAVG_ROE for every report period back to 2015 (4,329 rows for 2015-12-31, ~5,580 recently); both are also in the weekly quarterly tables, which give the TTM 扣非 EPS (eps_deduct_ttm in the snapshot; there is no 扣非 profit amount). RPT_VALUEANALYSIS_DET filtered by TRADE_DATE has the whole market from 2018-12-28 (3,354 rows) and nothing for 2016-06-30; non-trading days return no rows. 业绩预告 RPT_PUBLIC_OP_NEWPREDICT filtered by NOTICE_DATE or REPORT_DATE: one row per stock, period and indicator (PREDICT_FINANCE_CODE 004 net profit, 005 扣非 net profit, ...), with the amount and year-on-year ranges, PREDICT_TYPE (预增, 扭亏, 略减, ...) and last year's figure; ~14,300 rows in 13 months.
  - Price history and turnover: 通达信 official daily packages, www.tdx.com.cn/products/data/data/g4day/<YYYYMMDD>.zip (whole market in one ~2.7 MB file per day). Returns are chained as close ÷ exchange prev-close, which is ex-rights adjusted (checked on ex-dividend days).
  - A/H pairs: the Eastmoney AH list.
  - 10-year yield: the ChinaBond 10-year yield as republished in Eastmoney datacenter RPTA_WEB_TREASURYYIELD (EMM00166466).
  - Not used (2026-10-17): the push2 list API (clist) and push2delay dropped every connection after ~25 requests; Eastmoney kline is the same push2 family; Tencent's adjusted kline adds dividends instead of compounding them (understates momentum); yield.chinabond.com.cn timed out.
  - Announcements: CNINFO. Phase 11: the same query without a stock gives the whole market per day (Method 14); periodic reports by category (category_ndbg_szsh, _bndbg_, _yjdbg_, _sjdbg_); PDFs at static.cninfo.com.cn, text by pypdf (most read; some A+H issuers' PDFs have fonts without a Unicode map).
  - Second source for the quotes (Phase 12, verified 2026-10-19): Tencent qt.gtimg.cn, 60 codes per call, GBK, fields split by ~: 3 price, 4 previous close, 30 time (YYYYMMDDhhmmss), 39 PE-TTM, 45 total market value (100m CNY; 44 is the float value), 46 P/B, 73 total shares. Daily for the 1,200 largest A-shares (20 calls, ~1 s); 1,197 answered. Price, market value and shares matched Eastmoney's quote table exactly for all 800 of the universe.
  - 申万 industries for daily use (Phase 13, verified 2026-10-19): swsresearch.com's change-history file (codes only; the 31 level-1 names of the 2021 scheme are fixed), weekly with curl (its certificate chain isn't in Python's trust store); every one of the 791 CN stocks matched, and Eastmoney's BOARD_NAME (the 申万 level 2 name) maps to one level 1 for all but 5 names.
  - Backup: the Tushare token in .env.
  - The a-stock-data skill documents many CN endpoints.
  - Backtest (verified in Phase 9, 2026-10-18): 通达信 packages exist from 2021-08-13; RPT_VALUEANALYSIS_DET has every trading day from 2018-01-02 (pageSize 5000: one request a day; CHANGE_RATE = close ÷ ex-rights prev-close, identical to the packages), but only for companies still listed (delisted ones are dropped from it and from 业绩报表); 业绩报表 back to 2009; the 申万 change history (swsresearch.com xls; Python's TLS client is refused, curl works); the research-report archive (reportapi report/list) pages to the end, but its predict*Eps fields are relative to today (2019-2023 reports have none, 2024 reports only FY2026); RPT_RES_PROFITPREDICT and RPT_WEB_RESPREDICT hold the current years only; CNINFO's market-wide query stops after ~80 pages a day; the Tushare token has no API access.
- US (verified in Phase 4, 2026-10-17):
  - Universe: the Nasdaq screener, api.nasdaq.com/api/screener/stocks?tableonly=true&download=true (every NASDAQ/NYSE/AMEX listing in one call: price, market value, sector, industry). Its market value is company-wide on every share class and ADR, so shares = market value / price; its price can lag Yahoo by a day, so market value is rescaled to Yahoo's close and a stock whose screener price matches none of Yahoo's last 3 closes within 1% is dropped. The Eastmoney list (push2 clist) is blocked, as for CN. The 1,100 largest ordinary shares are kept up to date (config `us_candidates`).
  - Trailing-12-month fundamentals: SEC companyfacts (data.sec.gov/api/xbrl/companyfacts), 4 at a time, at most ~8 requests/s, User-Agent = SEC_USER_AGENT from .env; refreshed weekly per company (~5 min for 1,100). Files are 1-8 MB: they are parsed in memory and never written to disk. TTM = year-to-date + last fiscal year - same YTD a year earlier (the CN formula), or, after an annual report for less than a year (a fiscal-year change's transition period, a merger's successor stub), the fewest reported periods added and subtracted end to end that span the 12 months (not otherwise: L3Harris tags its fiscal-year revenue with Q4's dates); growth = TTM vs the TTM a year earlier. Concepts are merged per period in a preference order because companies switch tags between filings, with three rules from the Phase 12 cross-checks (2026-10-19), also in the annual history: revenue is chosen per period, because companies also tag parts of it with its concepts (ASC 606 fee revenue at M&T, AmEx and SoFi, Blue Owl's "Revenues", Zions' non-interest revenue subtotal) and totals before intersegment eliminations (Williams' ASC 606 total, Hasbro's "Revenues"): the concept within 5% of what the income statement implies (gross profit + cost of revenue, else operating income + total costs and expenses), else the largest concept (REITs' rent: OperatingLeaseLeaseIncome), and for banks net interest + noninterest income when larger; a 12-month figure comes only from a 10-K (Comfort Systems' Q1 2026 10-Q tagged Q1 2025 revenue as the 2025 year); equity and net income are the parent's: the total including minorities less MinorityInterest when only the total is tagged (AT&T, Carlyle, TPG, Royalty Pharma), ProfitLoss less the minorities' share when NetIncomeLoss is missing (Invesco).
  - Gaps (changed in the Phase 4 review; freshness: 200 days, 300 for half-year reporters): Yahoo fundamentals-timeseries (ws/fundamentals-timeseries/v1/finance/timeseries), one call per company, weekly, for companies SEC can't cover: no recent us-gaap 10-Q/10-K (foreign filers), no CIK, or a missing field (e.g. MLPs report partners' capital). It gives TTM revenue / profit / gross profit / operating cash flow and the balance sheet in the reporting currency; growth is TTM vs the TTM a year earlier, else the fiscal year a year earlier, else the same quarter a year earlier, else the last two fiscal years (semiannual reporters). 259 of 262 gap companies covered on 2026-10-17 (~80 s); 796 of the top 800 have complete data. Changed in Phase 12: fetched weekly for all 1,100 candidates (gap companies first), as the second source of the cross-checks, with NetIncome (before preferred dividends) and OrdinarySharesNumber added; ~5 min the first time.
  - Not used: FMP's free key. It served 7 of 184 gap companies (402 "premium" for ASML, NVO, SAP, AZN, SHEL, HSBC, TM, RY...) and stops at ~250 calls a day, which dropped 168 of the top 800.
  - Annual history (Phase 7): the same companyfacts files, forms 10-K, 20-F and 40-F, in us-gaap or ifrs-full: 20-F filers such as TSM and NVO report in ifrs-full (NVO has no ProfitLossAttributableToOwnersOfParent: ProfitLoss and Equity instead), ASML and BABA in us-gaap. One currency per company, the one with the most annual figures (TSM: TWD; its USD convenience figures cover the same years but appear only once each). Companies SEC has no annual history for: Yahoo fundamentals-timeseries annual types (4-5 years).
  - Monthly prices (Phase 7): the Yahoo chart API with interval=1mo and events=div,split over 11 years, for the candidates, ^GSPC and FX (<CUR>=X). Yahoo's closes are split-adjusted (NVDA Nov 2015: 0.79); they are stored as traded (× later split ratios: 31.72) to match the book value per share reported then, and monthly returns come from adjclose. Bars start at local midnight, and the current month appears twice (month start and last trade): only complete months are kept.
  - Analyst consensus EPS (added in Phase 4, for the forward lens and check 2): Nasdaq api/analyst/<symbol>/earnings-forecast, the first three fiscal years not yet reported; analysts = estimates behind next year's EPS. 2-4 s per call, so 4 at a time, weekly (~13 min for 1,100).
  - Price history and dividends: the Yahoo chart API (v8/finance/chart), one call per stock, incremental. It answers 429 to a full browser User-Agent but works with "Mozilla/5.0". Returns come from the adjusted close inside each response (splits and dividends included), stored as close + implied prev_close like the CN table. Index: ^GSPC (stored as SPX). The fetch updates every stock behind the newer of the index's and the largest candidate's latest day; the trading days (the screen's last day, momentum and volatility) are the days with prices for at least half as many stocks as the busiest day, in every market (2026-10-21 fix: Yahoo's ^HSI skipped 2026-10-20).
  - 10-year yield: FRED DGS10 (FRED_API_KEY).
  - FX for gap companies reporting in another currency: Yahoo "<CUR>=X" (21 currencies on 2026-10-17; ECB rates via frankfurter have no TWD, CLP, COP, PEN or KZT).
  - Headlines: the SEC filing list (data.sec.gov/submissions), see Method 8.
  - Base-rate panel (Phase 13, verified 2026-10-19): SEC frames data.sec.gov/api/xbrl/frames/us-gaap/<concept>/USD/CY<year>[Q4I].json, one concept's figure for one calendar year from every filer, dead companies included (CY2016 net income: 6,779 filers); ~1 MB each, 9 concepts a year (revenue concepts, NetIncomeLoss / ProfitLoss, StockholdersEquity at the year end, which 10-Q balance sheets fill for other fiscal years). SIC codes from data.sec.gov/submissions (0.1-1 MB each, read once per filer). Foreign filers report in IFRS and aren't in the us-gaap frames; their SIC code still comes from submissions.
  - Market-wide filings (Phase 11): SEC full-text search efts.sec.gov/LATEST/search-index?forms=...&startdt=&enddt=&from= (100 a page, `items` per 8-K, the document path in `_id`); filing documents at www.sec.gov/Archives/edgar/data/<cik>/<accession>/<document>.
- HK (verified in Phase 5, 2026-10-17):
  - Company list: Eastmoney datacenter RPT_HKF10_INFO_ORGPROFILE (every HK profile: name, ORG_CODE, industry, GICS-style industry type, organisation type, listing date; ~7,000 rows incl. delisted names, weekly). The Eastmoney list (push2 clist, fs = m:128+t:3,m:128+t:4,m:128+t:1) is blocked, as for CN and US.
  - Results: Eastmoney datacenter RPT_HKF10_FN_MAININDICATOR, one market-wide table filtered by report date (periods ending in the last ~2.2 years, ~12,500 rows; weekly, daily in March, April and August): year-to-date revenue and profit, growth (in the reporting currency, like Eastmoney's CN 业绩报表), BPS, gross margin, operating cash flow, debt/assets, issued shares, and Eastmoney's market value, PE-TTM and PB for the candidate list and the consistency checks. The 1,200 largest ordinary shares by that market value are kept up to date (config `hk_candidates`). TTM = year-to-date + last fiscal year - same period a year earlier, on each company's own fiscal year (the row's start date: March, June... year ends).
  - History (Phase 7): the same table since 2015-01-01, ~70,000 rows (140 pages), also ROE_AVG and BASIC_EPS (added to the weekly fetch too). Its TOTAL_MARKET_CAP, PE_TTM and PB_TTM are today's values on every row, not history, so the history table leaves them out. Monthly prices as for US (0700.HK, ^HSI), plus HKDCNY=X, since book values are in CNY.
  - Its amounts are all in CNY, converted at each period-end rate (HSBC and AIA at 7.0288 CNY per USD for FY2025), and no field names the reporting currency. About 30% of HK companies report in HKD or USD; with the 2026 RMB move, reading their amounts as CNY at today's rate would overstate profit and book by 2-6%. So each row goes back to the reporting currency (Yahoo's, below) at that period end's rate (Yahoo '<CUR>CNY=X' close, ~0.5% from Eastmoney's rates), the TTM is summed there, and converted to HKD at today's rate.
  - Not Yahoo fundamentals-timeseries: its HK trailing series stops at December 2025 for 563 of 1,154 candidates (half-year interims are missing), so the TTM would be six months stale.
  - Consensus EPS and the reporting currency: Yahoo quoteSummary earningsTrend + earnings (this and next fiscal year, last year's actual, analyst count, estimate currency; financialCurrency), one call per stock, weekly (~8 min for 1,200); it needs Yahoo's A3 cookie (from fc.yahoo.com) and the crumb for it. Eastmoney's RPT_WEB_RESPREDICT has no HK rows. 384 of the 1,200 candidates have 3+ analysts (2026-10-17). Phase 12: the same call also asks for defaultKeyStatistics and summaryDetail (book value and trailing EPS per share in HKD, impliedSharesOutstanding, mostRecentQuarter) for the cross-checks; a table without them is fetched again for every stock once (~8 min).
  - Price history and dividends: the Yahoo chart API (symbol 0700.HK), as for US, with the same trading-day rule; index ^HSI (stored as HSI). ~9 min for the first 385 days of 1,200 stocks.
  - 10-year yield: hkgb.gov.hk daily closing reference pricings workbook (HKD_DailyClosingReferencePricings_IBPandGSBP.xls, benchmark 10-year), read with xlrd. The HKMA API (api.hkma.gov.hk, IBP/GSBP) stops at June 2026 (monthly bulletin) and answered 405 after ~7 quick calls.
  - Issuer ids for the dedupe: ORG_CODE from the HK profiles above, the CN quotes (RPT_VALUEANALYSIS_DET) and Eastmoney RPT_USF10_INFO_ORGPROFILE (every US ticker, weekly).
  - Headlines: HKEXnews titleSearchServlet.do with the stockId from activestock_sehk_c.json. Phase 11: stockId -1 with a one-day range returns all of a day's filings in one call (rowRange 5000); t1code 40000 (lang en) lists a stock's annual and interim reports.
  - FX: Yahoo "<CUR>=X" for HKD and the reporting and estimate currencies (CNY, USD, SGD, JPY, EUR...), and ~900 days of daily "<CUR>CNY=X" closes for the period-end rates.
- FX, only needed when a company reports in a different currency from the one it trades in: ECB rates via api.frankfurter.dev.
- Legacy references (read only), all under ~/Developer/EquitySignalsClawbot-legacy/:
  - Sources/EquitySignalsClawbotCore/PublicUniverse.swift (around line 1310, the Eastmoney list call)
  - Sources/EquitySignalsClawbotCore/MacroPanel.swift (rate sources)
  - Sources/EquitySignalsClawbotCore/EastmoneyHKFinancialStatements.swift
  - script/a_stock_snapshot_sidecar.py (Tencent/Sina A-share calls)
