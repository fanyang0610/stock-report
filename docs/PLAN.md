# Plan

## Status
- Adopted 2026-10-24. It replaces the 2026-10-22 plan (stages 1 and 3 failed; docs/archive/PLAN-2026-10-22.md) and
  v1-v3 (Phases 1-13; docs/archive/PLAN-v1-v3.md). Both are reference only, not paths to follow. The fetchers, the
  cross-checks, the event feed, the deep-dive lane, the backtest data and the delivery stay as built.
- Stage 1 (the ranking and the new report): built 2026-10-24. signals.py, score.py, lists.py (`hold`), the new cards
  and report; v1, v3, signal.py and the stage-3 scripts removed; the history run is docs/BACKTEST.md section 21 (20
  names over the index fund a year: CN +2.9%, US −2.9%, HK +6.3%). Three fresh-context stage reviews; their fixes are
  in. A US index core (half in an S&P 500 fund) was added 2026-10-25 and removed in stage 3. US share counts fixed
  2026-10-25 (outside the stage; Data sources, US): Nasdaq's count
  stands when an SEC filing confirms it, else Yahoo's quote count a filing confirms is used, else a count 20% off every
  other is dropped; 14 of the top 800 set to Yahoo's count (Monster's P/E 42.5, was ~64; Carvana, TKO, Ferrari...), 4
  dropped (On, Aegon, JBS, Santander Brasil). The first version judged with Yahoo's statement count and set Martin
  Marietta, Public Storage and Somnigroup back to their July counts, before the shares they issued since. Not settled,
  Nasdaq's stands: Ares (an Up-C without an SEC count; avoid list, P/E 63 against ~43 on its class A) and Rio Tinto.
  Waiting for your OK (rule 9) to load the daily job, send a test, and turn the keyword reply back on.
- Stage 2 (the results review, AI notes and deep dives, on request): done 2026-10-26. review.py, fetch/news.py, the
  per-stock filing lists (fetch/filings.recent), notes.py and deepdive.py rewritten for it, the `review` command, the
  keyword reply and `send` reviewing first ("Results review", "How it is built"). Measured on 2026-10-26's full build
  (100 names; logs/2026-10-26.log): cold cache 100 reviews in 9 s, the reviewed report built in 9.6 s; warm 0.8 s;
  WeChat's two sends took 3 s in past replies, so ~13 s cold and ~4 s warm against the 30 s target (the review's budget
  caps a slow day at ~24 s). The day's review: no hard red flag, 42 soft concerns, no quote rejected, 96 of 100 AI notes
  shown. The deep dives' data check (18 reports read on 2026-10-25/26) compared 8: 7 agree within 0.3% (601225, 601600,
  601857, 00293, 00857, 00883, 01113) and 01919's row was read without its thousands unit (exactly 1,000× off: not
  counted, and such a unit line is now rejected when the report is read); 10 weren't compared: no verified profit row
  (7), US 10-Qs (2), a PDF without readable text (00966 中国太平, so the HK #1, an insurer with H1 profit +90%, has no
  deep dive yet). The keyword reply is still off (rule 9); nothing was sent.
  Two fresh-context stage reviews. The first found that one misread could remove a good buy with no override
  (confirm verdicts weren't read; loose subject checks; headlines about other companies; a 10-Q's legal wording read
  as an investigation; the data check didn't check its row), that bond defaults, overdue debts and auditor
  resignations were dropped as routine, that ~40% of CN headlines were daily data items, and that removed names weren't
  paired with replacements. The second found its fixes overreached: a fraud finding, an SEC subpoena and a live offer
  mentioning completion had become soft; the company-name check failed both ways (Micron's headlines say "Micron";
  中国太平 sits inside 中国太平洋); a denial in English made a false concern on 00857; notes named concerns code had
  dropped. All are fixed as "How it is built" describes: hard red flags now come only from filings, so no name check is
  needed. Left as follow-ups: 00966's unreadable report; the bench can't refill a removed buy's sector (closed in stage
  3: the bench is now per sector). The event
  feed's unused fetch and labels and the old title fetchers were removed on 2026-10-26 ("Kept from the old build").
- Stage 3 (analyst revisions, and a list built like its index): done 2026-10-31. Revisions in every momentum family,
  forward E/P in value, all families ranked within sectors (signals.py, score.py); the buys from the index fund's own
  index sector by sector, sized like S&P DJI's QVM index within UCITS 5/10/40 (lists.py; the review's replacement now
  comes from the removed buy's sector, which closes stage 2's follow-up); holdings judged within their sector as buys
  are; fetch/index.py (CSI 300 and SPY weight files), the report archive, Yahoo's US estimate trend and HK-listed
  shares; `track` weighs buys by their share; the US index core and the 可做空 plan removed. 99 tests pass. The
  2026-10-31 build (reports/2026-10-31; 271 s on a warm cache, 41 min when the weekly US refresh is due; all three
  markets, no index-core text):
  - coverage of the scored stocks: forward E/P CN 85%, US 93%, HK 70%; revisions CN 30% (the archive has fewer brokers
    than the consensus table counts: 44% of the largest 300), US 93%, HK 70%;
  - each list's sector weights within about 4 points of its index's (CN 4.1, US 3.9, HK 3.1; MSCI allows 5); the
    index's 10 largest held: CN 中际旭创, 贵州茅台, 药明康德 (25% of the money; 23% of the CSI 300), US NVIDIA,
    Amazon, Meta, Micron (40%; 39% of the S&P 500), HK 中国移动, 网易 (18%; 45% of the parent);
  - but only 20 names: the money that overlaps the index's own weights is 18% (CN, US) and 13% (HK), an active share
    of 82-87%, and a sector's weight held in leaders the list doesn't buy flows to the qualifiers it does (US memory
    makers Micron, SanDisk, Western Digital ~20% against ~2% of the index; HK mainland insurers). Capping each name
    near its index weight (MSCI's ±2 points) can't be done with 20 names while keeping the sectors; the report says
    plainly that the names, not the sectors, differ from the index and that results will swing away from it;
  - your spot checks (examples, not targets): Micron is the US #2 score and a 10% buy; AMD (279th of 794, value E) and
    Eli Lilly (625th: value E, quality D on its 76% liabilities and cash backing weak for its sector) are neither
    bought nor avoided; Stellantis ranks 725th (next year's estimates cut by 11% of its price in 3 months, momentum E;
    too small for the avoid list's 400 largest); GM ranks 216th, not a buy. Microsoft is 21st of 75 in technology,
    Apple 71st;
  - history (docs/BACKTEST.md section 22, without analyst data): 20 names over the fund a year CN +7.2% (67% of
    windows; about 14 of 2024-26's 22 points from 中际旭创 alone), US −1.3% (32%), HK +3.3% (58%); largest falls CN
    −37% (fund −37%), US −24% (−24%), HK −38% (−47%).
  The fresh-context stage review confirmed the parsers, the revisions' point-in-time handling, the issuer-summed SPY
  weights, the same-sector replacement, no index-core text left, no choice made on a history result (the method was
  written before the stage-3 history run) and no rule for a named stock, and reproduced every figure. Its findings and
  the answers: (1) the holding rule still used the whole index while buys are picked within sectors, so 16-24% of each
  list would have been sold at its anniversary while the buy rule picked it again: fixed (holdings by their rank in
  their sector, "Holding rule"); (2) "the list's size mix is close to the index" overstated it: the report now says
  the sectors follow the index and the names don't (overlap above); (3) Yahoo's 0 for a missing 90-day-old estimate
  read as an estimate (ASMPT had a +5.6% revision): now missing, also in tables saved before; Yum China's HK-listed
  count was 3× its total shares: a listed count can't exceed all shares; reasons and risks read backwards (中国移动's
  reason was two falls, Micron's risk a strength): a reason is now a figure that reads well, a weakness one that reads
  badly; grades are now fifths among the peers exactly; stale plan lines fixed. Answered, not changed: 13 of 236
  covered CN stocks show a zero revision, brokers keeping their forecasts (维持盈利预测), a real "no change"; the US
  history stand-in admits a few names the S&P 500 can't hold (an MLP), noted in section 22.
- Nothing runs on a schedule (your call, 2026-10-24: a fresh start). The 06:30 job (com.stockreport.daily) is unloaded
  and disabled; the keyword listener (com.stockreport.listen) was already off. launchd/com.stockreport.daily.plist is
  rewritten for `run` (no DeepSeek); the copy in ~/Library/LaunchAgents is still the old one until it's loaded. While
  it's off, no daily snapshots or weekly consensus snapshots are collected.

## Why this plan
- **What went wrong.** Thirteen phases and two stages built engines that no successful stock-ranking product builds (a
  fair value per stock, an earnings forecast, an implied return), and judged them on ship bars I proposed that no
  realistic edge could pass: a 10-name list beating 90% of random lists over about 8 years needs an edge of 4-5% a year
  over random picks (a track record's t-statistic is about its information ratio × √years). Signals were also chosen on
  our own 8 years: CN's score took the price trend, which 20 years of A-share research says doesn't pay, and it reversed
  in 2024-26. So nothing shipped.
- **What others do.** Stockopedia's StockRanks, Seeking Alpha's quant grades, Alpha Architect's and Greenblatt's
  published rules and AAII's real-money portfolios rank stocks on a few published factor families and hold a diversified
  list. None forecasts a value for each stock. Their evidence is decades of research in many countries (most published
  factors replicate across 93 countries: Jensen-Kelly-Pedersen 2023) plus a live record, not one backtest.
- **This plan borrows a complete method.** Stockopedia's ranking (quality, value and momentum, equal weights) and its
  NAPS holding rule (hold a year, then repeat), with each market's ingredients taken from published research on that
  market. Stage 3 replaced NAPS's portfolio rules (2 names per sector, equal amounts) with S&P DJI's QVM index
  construction, sector-neutral ("Lists").

## Goal
- On the WeChat keyword (股票报告 / 股票简报 / stock report / stock brief), within 30 s, two messages (a text summary and
  a PDF), in Chinese. Per market (CN → US → HK):
  - **买入组合 (buy portfolio):** 20 names from the index the market's fund tracks, each with its share of the money,
    the sectors weighted as in the index ("Lists");
  - **持仓检查 (your holdings):** 继续持有 / 复核 / 卖出 for each name you hold;
  - **回避 (avoid):** 10 names;
  - **预期 (what to expect):** how this method did in our history and in published research.
- **Moderate.** The aim is to beat the market's index fund over the year you hold the names, at about the market's level
  of risk. Not a defensive tilt (low volatility, dividends) and not an aggressive one (small caps, a few concentrated
  bets, chasing the hottest stocks).
- **Honest expectations.** Published factor portfolios have beaten their index by a few percent a year on average, have
  lost to it in roughly 4 years out of 10 (AAII's real-money portfolio: beat the index in 55% of rolling years), and
  their edge shrank after publication (McLean-Pontiff: about −58%). No list is a guarantee; the report says so.

## The method

### Universe
- Scored: the 800 largest after the filters (liquidity floors as built). Buys: the index fund's own index (stage 3; "Lists"):
  the CSI 300 (510300) and the S&P 500 (SPY) from their weight files, HK the largest 200 by HK-listed value. Avoid names:
  the largest 400.
- Out only on facts: figures that fail the cross-checks, ST / *ST, suspended, under 12 months of prices, and (from stage
  2) a hard red flag. Everything else is left to the score, so a troubled company ranks low rather than vanishing.

### The score: three families, equal weights
Each component is a percentile among the stock's peers on the date, point-in-time; a family is the percentile rank among
the peers of the mean of its components' percentiles (a missing component is skipped; a missing family counts as 50);
the score is the mean of the three families. Ranking each family before combining is Stockopedia's way and makes the
weights equal in effect: a plain mean of three percentiles spreads much less than one percentile, which let
one-component momentum drive the score (fixed in stage 1 after the stage review).
- **Peers (stage 3):** the stock's sector, financials apart from the rest (their components differ: no S/P, cash
  backing or debt, which made a bank's one or two components outrank everyone's three-component means in stage 1). Why
  within sectors: MSCI's Diversified Multiple-Factor indexes score value and quality relative to the sector, and
  Asness, Porter and Stevens (2000) find industry-relative value and momentum predict returns better than the raw
  figures; with the buys chosen sector by sector ("Lists") a family ranked market-wide would also weigh differently in
  each sector. Momentum is ranked within sectors too (MSCI keeps it market-wide, but its optimizer then sets the
  weights; ours are rank-based). A sector with fewer than 10 scored stocks is too small for fifths: its stocks are
  ranked against the whole market of their kind (financials or the rest). Sectors: CN 申万 level 1, US the Nasdaq
  sector, HK Eastmoney's first-level industry type.

| Family | CN | HK | US |
|---|---|---|---|
| 价值 Value | E/P on 扣非 TTM, forward E/P, B/P, S/P | E/P, forward E/P, B/P, S/P | E/P, forward E/P, B/P, S/P |
| 质量 Quality | ROE, cash backing, debt ÷ assets | ROE, cash backing, debt ÷ assets | gross profit ÷ assets, cash backing, liabilities ÷ assets |
| 动量 Momentum | earnings momentum (SUE), revisions | 12-1-month price return, revisions | 12-1-month price return, revisions |

- **Value:** a composite of three ratios, as Stockopedia's value rank uses several, so no single ratio decides. E/P is
  CN's strongest value measure (Liu-Stambaugh-Yuan 2019). B/P only where book > 0 (negative book from buybacks is
  undefined, not cheap or dear). S/P not for banks, insurers and brokers.
- **Quality:** profitability (Novy-Marx 2013; Asness-Frazzini-Pedersen's quality-minus-junk, which holds in 23 of 24
  countries), cash backing = −(net profit − operating cash flow) ÷ revenue (Sloan 1996), and balance-sheet strength
  (lower debt is better; not for financials, whose leverage is their business).
- **Momentum:** the 12-1-month price return in the US and HK. In CN the price trend hasn't paid over 20 years (Jansen,
  Swinkels and Zhou 2021: past-return anomalies weak in A-shares), while earnings surprises are followed by drift
  (A-share studies, 2000-2020). So CN uses SUE: the latest quarter's 扣非 EPS minus the same quarter a year earlier,
  divided by the standard deviation of that change over the preceding 8 quarters, from the notice date. Stockopedia's own
  momentum rank mixes price and earnings momentum, so this stays within the method. HK's evidence on price momentum is
  mixed rather than negative, so it keeps the standard definition.
- **Forward E/P (stage 3):** next fiscal year's consensus EPS over the price, at least 3 analysts (CN Eastmoney's
  研报一致预期, US Nasdaq's consensus, HK Yahoo's). The predicted E/P is the largest part of the earnings yield in MSCI's
  Barra equity models, whose value factor MSCI's multi-factor indexes use; it judges a fast-growing company on the
  profit analysts expect next year, not only the last 12 months (on 2026-10-26 NVIDIA's trailing P/E was 26, next year's 13).
- **Revisions (stage 3):** next fiscal year's consensus EPS now minus 91 days ago, over the price: the price-scaled
  change in the consensus of Chan, Jegadeesh and Lakonishok (1996), who find revisions predict returns apart from price
  momentum, over the 3-month window of S&P DJI's Asian study (7 markets including China and Hong Kong, 2005-2016: in
  most of them prices moved with the revisions) and of Stockopedia's momentum rank. The price, not the old estimate,
  divides, so an estimate near zero doesn't explode. At least 3 estimates; missing: skipped, like any component.
  US and HK from Yahoo's earningsTrend (the +1y estimate now and its value 90 days ago, kept by Yahoo for the same
  fiscal year: MU's FY2028 162.9 → 206.9; weekly). CN from Eastmoney's research-report archive: each broker's latest
  estimate published in the 180 days to the date (A-share brokers report on a company at least at the annual and
  interim results), the median, now and 91 days earlier, at least 3 brokers at both dates; an estimate published
  before a bonus-share ex-date (送转, common in June) is divided by 1 + the bonus ratio, so a 10-for-10 doesn't read
  as a halving. Next year: the year after the first fiscal year without an annual report. Coverage on 2026-10-26: see
  Status. The up-minus-down ratio (S&P DJI's second measure) needs each analyst's revisions over 3 months, which
  Yahoo gives only for 30 days; one definition in all three markets instead.
- No weights are fitted and nothing is chosen on our backtest.
- **How each ingredient is built** (stage 1; stockreport/signals.py):
  - Percentiles are taken over the whole scored universe (the 800 largest after the filters), so a holding outside the
    buy universe still has a score; the buy and avoid lists then take their own size cuts.
  - CN 扣非 comes from 主要财务指标 (year-to-date 扣非 net profit as an amount, each quarter since 2015, by its first
    notice date), because 业绩报表 has 扣非 EPS only in half-year and annual reports. E/P = 扣非 TTM profit ÷ market value
    (reported profit for the ~1% without it). The SUE uses amounts, not per-share figures, so bonus shares (送转) don't
    read as a fall, and needs at least 6 of the last 8 year-on-year changes (the usual minimum in the SUE literature).
  - The score's financials are banks, insurers, brokers and other lenders, whose balance sheet is the product: CN 申万
    银行 and 非银金融 (多元金融 is leasing, trusts and financial holdings); HK the bank, insurer and broker sub-industries
    plus 消费信贷 and 特殊金融服务 (consumer lenders, lessors); US Nasdaq's bank, broker and insurer industries plus SEC SIC
    6000-6199 (credit institutions: AmEx, Synchrony, SoFi, NU sit in Nasdaq's "Finance: Consumer Services" with Moody's
    and Equifax) and 6300-6399 (insurance carriers, health insurers and Berkshire included). Exchanges, rating agencies,
    data firms and asset managers are fee businesses, scored like other companies, except in the US, where Nasdaq's
    broker industry also holds the exchanges (CME, ICE, Nasdaq, Cboe, Tradeweb) and BlackRock, so they count as
    financials there. SIC 6199 also holds Coinbase (a
    retail broker, like Robinhood, which Nasdaq lists among brokers), Circle and BitMine (balance sheets that are their
    product), so they count as financials. Known gaps, left without name rules: Equitable (a life insurer under SIC
    6411), Ares Capital (no SIC), Annaly (a mortgage REIT) and HK 中国信达 (filed with asset managers).
  - "Debt ÷ assets" is total liabilities ÷ assets (资产负债率) in every market: the free tables have no interest-bearing
    debt line. It counts client funds and settlement obligations (ADP, Mastercard) and buyback-shrunk equity as
    leverage, so such companies grade low on quality; the card's 负债率 is the reported ratio.
  - Cash backing is left out for banks, insurers and brokers (their operating cash flow moves with deposits and loans;
    Sloan's sample excludes financials). CN and HK use the latest report's year to date (CN: operating cash flow per
    share × shares; HK in the reporting currency), the US the trailing 12 months.
  - US financials have no gross profit: their profitability is ROE ranked among financials (Novy-Marx's gross
    profitability excludes them). US E/P and B/P are to common shareholders (preferred dividends and equity taken
    out, history.us_preferred). US gross profit comes from SEC, else Yahoo's standardized figure (a quarter of SEC
    filers tag neither gross profit nor a cost of revenue).
  - Figures are kept as reported (no winsorizing): the score uses percentiles, and the cards show the numbers. A
    missing growth figure no longer drops a stock: growth isn't scored (out only on facts).
  - An issuer listed in two markets can appear in both lists: each market's portfolio is measured on its own.

### Lists
- **Buys (stage 3):** 20 names from the index the market's fund tracks, built like S&P DJI's S&P 500 Quality, Value &
  Momentum Multi-Factor Index (it holds the top fifth by the averaged score, weighted by market value × score), made
  sector-neutral (S&P DJI's own study of multi-factor construction on the S&P 500, Innes, Jain and Ponnala 2021, finds
  sector-neutral selection more efficient; MSCI's multi-factor indexes keep each sector within 5 points of the parent):
  - the parent: the CSI 300 (CSI's month-end weight file) and the S&P 500 (SPY's daily holdings, an issuer's share
    classes summed); HK has no free current Hang Seng Index file (the Tracker Fund's holdings file stopped in 2022), so
    its parent is the 200 largest by HK-listed value (Yahoo's listed-class share count × price: an A+H bank's H shares
    only; total value would put 38% in financials against 30% listed), weighted by it. A market whose file is missing
    falls back to the same rule on market value (US home listings);
  - places: each sector gets 20 × its index weight, rounded by the largest remainders (a sector can't get more places
    than it has names);
  - picks: in each sector its top fifth by score qualify (at least its places), and the places go to the largest index
    weight × score: the largest positions such an index would hold. Past the qualifiers, by score. The next one is the
    sector's bench, which replaces a buy the review removes;
  - money: each sector its index weight (over the sectors held), inside it index weight × score, within UCITS 5/10/40
    (the EU's rule for funds sold to the public: at most 10% in a name and 40% in names above 5%; here the four largest
    up to 10%, the rest up to 5%), a capped name's excess going to its sector's other names. The report shows each
    name's share and its index weight; the text summary shows the 10 largest.
  - Why this replaces "the 20 highest scores, at most 2 per sector, equal amounts" (Stockopedia's NAPS rules) and the
    US index core: a name had to be good on value, quality and momentum at once, so the expensive leaders that make up
    much of each index never qualified (on 2026-10-25 NVIDIA, Microsoft and Apple ranked 327, 441 and 522 of 791), two
    places a sector gave every sector a tenth whatever its size (US technology is ~45% of the S&P 500), and equal
    amounts put a mid-size company's weight on every name. So the list's sector and size mix drifted from the index:
    the US 20 names trailed SPY by 2.9 points a year in 2018-2026 (ahead in 24% of 12-month windows), about what the
    equal-weighted S&P 500 lost to the cap-weighted one then. The half-in-an-index-fund advice (2026-10-25 to 26) only
    diluted that list, and how you split your money between the list, funds or bonds is your business, not the
    report's. The published multi-factor indexes (S&P's, MSCI's, FTSE Russell's) all start from the parent's weights
    and tilt them, none from equal amounts; this is the smallest version of that a 20-name list allows. The same
    construction in all three markets: each market's fund is cap-weighted and the aim (beat it at about its risk) is
    the same everywhere; the score's ingredients stay each market's own.
  - Spot checks on 2026-10-26 (examples, not targets): see Status.
- **Holding rule (NAPS):** hold each name 12 months from the day you bought it.
  - 继续持有: no hard red flag, and either before its anniversary or still in its sector's top fifth at it;
  - 复核: before the anniversary it has fallen into its sector's bottom half, or the review (stage 2) found a soft
    concern;
  - 卖出: a hard red flag at any time, or at the anniversary outside its sector's top fifth (replace it with the largest
    buy you don't hold).
  - Every anniversary repeats this: for 30 days after it (the time to act) the top-fifth test applies; after that a new
    year has started, judged by the in-year rule until the next anniversary.
  - Your holdings live in data/holdings.csv (code, buy date), set with `hold CODE [--date D]` and `hold CODE --sold`.
    Without the file, the check covers the names of the last 12 months' buy portfolios (data/picks.csv) that aren't
    in today's, each from the first day it was listed.
  - "Top fifth" and "bottom half" are the score's rank among the holding's sector's names in the index (stage 3: the
    line a buy qualifies by; the stage review found the rule still used the whole index, which would have sold 16-24% of
    each list at its anniversary while the buy rule picked it again), so a holding that left the index is still judged
    against the same names. A holding the build couldn't score (dropped on facts, or no longer among the 800 largest)
    gets 复核 with the reason.
- **Avoid:** the 10 lowest scores among the 400 largest, at most 2 per sector, each with its weakest family named.
### Cards
- The price; the rank; the three grades A-E (fifths of each family); one line on why it's there (its two strongest
  components in words, with the figure); the key risk (a loss, heavy debt (70%+ of assets, the SASAC warning line; not
  financials) or a 30%+ fall in 6 months, else its weakest component); the cost of one board lot (CN 100 shares, US 1
  share, HK the board lot from HKEX's List of Securities, verified 2026-10-24: Tencent 100, HSBC 400, China Mobile 500,
  AIA 200); the re-check date (the anniversary, or sooner if the rank falls into the bottom half); a buy's share of the money and
  its index weight (stage 3). A ratio is worded by its side of the peers' median (同行中市盈率低 / 高), cash backing,
  momentum, the SUE and the revisions by their sign (the revisions as the estimate's 3-month change).
- From stage 2: the review's line (审核：… for a hard red flag, 数据存疑：…, 市场可能在担心 … with its quoted source, or
  审核未见重大风险 / 审核进行中 / 审核暂不可用) and the AI note (one sentence, words only).
- Each market section opens with its 预期 line: from the history run, the 20-name portfolio's average 12-month return
  over the index fund, the share of 12-month windows it beat the fund, its worst 12 months and its largest fall against
  the fund's, marked 模拟回测 (simulated, after costs), plus one line on the published evidence.

### The history run (stage 1, once)
- On the existing month-end frames (CN 2019-01.., US 2018-01.., HK 2016-10..): each month's 20-name portfolio at its
  weights, held 12 months with a round trip of costs (0.2% US, 0.3% CN, 0.6% HK), against the index fund with dividends
  (SPY, 2800.HK, 510300.SS). Also its 10 and 5 largest positions, to show how much fewer names widen the range.
- Each family's top fifth against its bottom fifth over the whole sample, per market.
- Stage 3: no free index history exists, so the parent is a stand-in: each stock's market value then × today's float
  factor (its index weight today over its share of market value; HK: HK-listed over all shares), the largest 300 (CN),
  500 (US) and 200 (HK). The snapshots have no consensus estimates, so the history's score has no forward E/P or
  revisions; the report says both.
- The CN frames are point-in-time by report date but hold only companies still listed (Eastmoney drops delisted ones),
  with restated 扣非 figures; US and HK hold today's listings. So every market's numbers are flattered, and the report
  says so (corrected in stage 1: this line said CN had delisted names).

### Results review (stage 2; only when you ask for a report)
The numbers can't see a fraud investigation, a going-concern doubt, a takeover at a fixed price, or a story the market is
worried about. DeepSeek reads the stock's non-routine filings of the last 90 days (CNINFO, HKEXnews, SEC) and free
headlines, at temperature 0 with a fixed checklist and JSON out; every finding quotes its source and code checks the
quote (quotes.py). It never changes a number (rule 2). It reviews the 20 buys, the bench (the next name of each sector
held), your holdings and the 10 avoid names, buys first, up to 10 calls at a time, within a 20-second budget; each review is cached per stock and redone only
for a name new to a list, a new filing or headline, or a review over 7 days old. A name not reviewed in time shows
审核进行中 and is finished in the background; if DeepSeek is down, the report goes out marked 审核暂不可用. The 06:30
build makes no DeepSeek calls.
- **Hard red flags** remove a buy (the next-ranked name takes its place, listed under 审核剔除 with the reason and
  source), turn a holding into 卖出, and are noted on an avoid name: a regulator's investigation, a fraud finding or a
  Wells notice; a non-standard audit opinion or the auditor resigning; a going-concern doubt or a debt default; delisting
  or ST risk, or a suspension; a takeover or privatisation at a fixed price; sanctions or a ban naming the company.
- **Soft concerns only annotate** (an industry downturn, a lost customer, a guidance cut, management leaving,
  litigation, a one-off gain): the card says 市场可能在担心 … and a holding gets 复核. Cheap stocks carry bad news by
  nature, and that is where value pays off on average.
- **Data check:** a latest filing that contradicts a card's figure by 20%+ drops the name as data_suspect, and the next
  one takes its place (rule 5).
- The review can't be backtested (an LLM reading old news knows what happened next), so its powers stay this narrow; the
  scoreboard follows each removed name against the name that replaced it.
- **How it is built** (stage 2; review.py, deepdive.py):
  - Sources, gathered by the build with no DeepSeek (~30 s a market; reports/<date>/<market>_sources.json): each name's
    filings of the last 90 days from a per-stock query (CNINFO, HKEXnews' title search, SEC's filing list), routine ones
    dropped by the filing rules (events.classify), the newest 20; and headlines of the last 30 days, the newest 15.
    Per-stock queries rather than the old market-wide event feed, which only held the days the build ran (10 back;
    removed 2026-10-26). The routine rules drop bond, guarantee and auditor titles; a default, an overdue debt or an
    auditor resigning is checked first and kept as a risk filing (events.ALARM; found by the stage review).
  - Headline sources, verified 2026-10-25: CN and HK Eastmoney's per-stock news list (np-listapi getListInfo, biz
    web_stock_news, market 1 / 0 / 116: the 资讯 tab of its quote pages; 0.1-0.5 s a call, at most ~2 a second); US
    Yahoo Finance's RSS feed per ticker (feeds.finance.yahoo.com/rss/2.0/headline; 429 to a full browser User-Agent,
    fine with "Mozilla/5.0"). Titles only. Eastmoney's list is ~40% daily data items (margin balances, fund and Stock
    Connect flows, block trades, market roundups); they say nothing about the
    company and are new every day, so they'd redo every cached review, and are left out (news.DATA_ITEMS; 206 of
    525 CN headlines and 19 of 372 HK on 2026-10-25).
  - One DeepSeek call per name (deepseek-flash, thinking off, temperature 0, JSON): the card's own lines and the numbered
    source lines in, findings (kind, source line, quote) and the note out. A finding counts only if its quote is in a
    source line (6+ characters, or a short title quoted whole: HKEX's 「盈利警告」). Then code checks each kind (KINDS):
    - a hard kind has to name its subject in the quote: an investigation names 立案, 调查 or the like; an audit flag a
      non-standard opinion or the auditor resigning (not any director); a takeover 要约, 私有化, a tender offer... Else it
      is a soft concern;
    - hard red flags come only from the company's own filings; from a headline the same finding is a soft concern
      (市场可能在担心). Issuers in all three markets must disclose these events themselves (立案告知书, 退市风险警示,
      要约收购报告书, 违约公告; HKEX inside information; 8-K items), while headlines are often about another company
      or the whole market, and no name match tells them apart reliably (Micron's headlines say "Micron"; 中国太平 sits
      inside 中国太平洋; tickers like ALL are words: a name check tried in the first fix failed both ways);
    - dropped, no finding at all: a denial (不存在…, "none of … was subject to any investigation"); a suspension or
      delisting of another security (preferred shares, bonds, convertibles); a report on an offer already done (a
      sponsor's 持续督导 report, 过户, 收购结果, 已完成; a live offer that mentions its expected completion stays hard);
      a management change that isn't the chair, CEO or CFO (or an executive under investigation): ordinary directors,
      board secretaries, 副总经理, a Vice Chair and a subsidiary's or branch's executives are routine. Bare SEC 25-NSE /
      15-12B forms, which don't say which security (Comcast's and ONEOK's were their notes), are left out of the sources.
  - The bench is the next name of each sector held (stage 3); a removed buy's place goes to its sector's bench name if
    not blocked, else to the best other one, and the money is split again (lists.weigh). With none left the list is
    shorter.
    The scoreboard logs each removed name (bucket removed) and the name that took its place (bucket replacement), so
    `track` shows the two side by side.
  - Your confirm verdict (`verdict CODE confirm --until D --reason "..."`) overrides the review for that name until its
    date or the next report period: a buy stays, a holding keeps its status, and the card says 你已确认 with your reason.
  - Cached per stock (data/review/<market>/<code>.json); the keyword reply waits `budget` (20 s), then sends what is
    done, and a background `review` finishes the rest and the day's deep dives. `review` runs it all without a limit.
    The AI note is dropped if it holds a figure (a digit, or one in characters like 三成), so every number on a card
    comes from code, and when code rejected, dropped or changed any finding the note was written with, so it never
    names a concern the card doesn't show.
  - Deep dives (the lane of rule 3): the latest periodic report of the buys, the bench and your scored holdings, read once
    per filing, at most 3 new filings per market a day, after the review. The data check compares the report's net
    profit to shareholders for the card's period (the period end quoted in the report, '30 June' or '30th June'; CN:
    else its standard title) with the card's figure: CN and HK year to date (HK in the reporting currency), US the year's
    profit from a 10-K (10-Qs are year to date, the card's figure trailing 12 months, so they aren't compared). It reads
    only a row that says it is the shareholders' profit (归属于…股东 or 所有者, 權益持有人應佔, attributable to,
    shareholders of...), not a consolidated row, the minorities' or the profit after deducting non-recurring items (扣非).
    So the US check runs only on a 10-K's attributable row, which is rare; US figures come from the same XBRL filings,
    so it matters least there. A table row's unit line must state the scale or the base unit (单位：元, in millions,
    RMB'000; 'RMB' alone could be RMB'000). Any figure of the row within 20% passes (a row holds the quarter and the year
    to date, or this year and last); a gap that is a power of ten is a unit misread of the row, not our data (a fault
    that size fails the second-source cross-checks). The same reading gives the hard flags of a non-standard audit
    opinion, a going-concern doubt, an investigation opened or a fraud finding (立案, a Wells notice, an SEC subpoena or
    the Division of Enforcement, 欺诈, 虚假记载, 造假; legal-proceedings boilerplate such as "in the ordinary course" and
    denials are not) and an offer price, and the soft concern of non-recurring items at 30%+ of the period's profit (a
    quote naming the profit after deducting them is that profit, and is skipped).

## Checks, and what each one decides
- **pytest** on the score math (peer percentiles, families, SUE, revisions, the list's places, picks and weights, the
  holding rule) and the parsers, on small saved samples: catches calculation and parsing bugs.
- **The data cross-checks** (built): a stock whose figures disagree with the second source is dropped (rule 5).
- **The history run's family check:** a family running strongly against its published direction over the whole sample
  in a market sends me looking for a data or definition bug. If none is found, the family stays (the published evidence
  is far longer than ours), and the report says so.
- **The history run's portfolio numbers:** they fill the report's 预期 line. They don't decide whether the report ships.
- **The fresh-eyes review** at the end of each stage (.claude/agents/stage-reviewer.md): catches what I missed, and
  spot-checks a few buys and avoid names against their filings and news for common sense.
- **The live scoreboard** (`track`): each month's portfolio against the index fund (buys weighted by their share of
  the money from stage 3), shown in the report once a month;
  it catches live data faults and builds the method's own record. It never holds anything up.

## How decisions are made
- Investment-method choices are mine to make from published evidence, each with its reason written here. You are asked
  only for approvals: starting a stage, any WeChat send, a new dependency, GitHub, launchd, or a paid service (rule 9).
- The method changes only to fix a bug or to follow new published evidence; never because a backtest number, a
  sub-period or one stock looked wrong, and no rule is written for a named stock.
- No pass/fail gates on shipping, and no test whose result would change nothing.
- The reviewers propose; nothing changes the method automatically.

## Stages (one per session)
1. **The ranking and the new report.**
   - signals.py (the families per market, point-in-time; stage 1's signal code reused where it matches these
     definitions; CN SUE from the quarterly 扣非 EPS), score.py, lists.py (buys, the holding rule with `hold`, avoid).
   - Cards with the grades, the key risk, the board-lot cost, the re-check date and the 预期 line; the text summary
     under 4,000 bytes.
   - The history run (backtest/), its numbers in docs/BACKTEST.md section 21.
   - Removed: v1 (value.py, pick.py), v3 (baserates.py, v3.py, shadow.py, trend.py, outliers.py), signal.py and their
     commands; the stage-3 engine scripts in backtest/.
   - The daily build makes the report, with no DeepSeek calls (cards carry the code's lines only until stage 2); the
     job file is rewritten for the new commands.
   - Done when: pytest passes; a full build renders all three markets; the history numbers are recorded; the
     fresh-eyes review is done; then, with your OK, the daily job is loaded again, a test send goes out, and the
     keyword reply comes back on.
2. **The results review, AI notes and deep dives, on request** (above): a free news source per market verified, the
   quote checks, 审核剔除 and the card's review line. Done when its tests pass on saved filings and headlines (a quote not
   in the source is rejected; a hard flag removes a buy; a soft concern only annotates) and the keyword reply takes
   under 30 s on a warm cache and on a cold one. Done 2026-10-26 (tests/test_review.py, tests/test_deepdive.py; the
   timings are in Status).
3. **Analyst revisions, and a list built like the index it is measured against** (your words, 2026-10-26: the US
   index core is a patch that sheds half the job; how you split your money is your business; fix the biased selection
   and the missing index leaders in how the list itself is built).
   - Revisions join each market's momentum family: the 3-month change in the next fiscal year's consensus EPS, divided
     by the price. US and HK from Yahoo's earningsTrend (the +1y estimate now and 90 days ago, at least 3 analysts),
     CN from Eastmoney's research-report archive (each broker's latest estimate, bonus shares adjusted). No waiting
     for our own snapshots: the old "26 weekly snapshots" condition was wrong, since both sources keep the past
     estimates. Adopted on the published evidence (no free history exists to test it).
   - Value adds forward E/P (next year's consensus EPS ÷ price); value, quality and momentum are ranked within
     sectors; the 20 names come from the index fund's own index, sector by sector, sized like it (S&P DJI's QVM
     multi-factor index, MSCI's multi-factor indexes; "The method").
   - Removed: the US index core (config, report, template, expect.json, this plan, AGENTS.md's goal line). Dropped: the
     old stage 3's 可做空 label, useful only to someone who shorts; you didn't ask for it.
   - The history run again (docs/BACKTEST.md section 22) for the 预期 line; it fills the report and decides nothing.
   - Done when: pytest passes, with the new parsers on saved samples (Yahoo's earningsTrend, the report archive, the
     CSI 300 and SPY weight files, Yahoo's HK share counts) and the list construction; a full `run` renders all three
     markets without any index-core text; the history numbers are in BACKTEST.md section 22 and the 预期 lines; the
     fresh-context stage review has run and its findings are fixed or answered; this plan's status is updated and the
     work is committed on main.

## Kept from the old build
- The fetchers and cross-checks; the history tables; the SEC frames with dead companies; the point-in-time CN panel.
- The backtest snapshots and the stage-1 harness (index funds, costs, month-end frames).
- The event feed's filing rules (events.py), which classify the review's filings. Removed on 2026-10-26, unused since
  stage 2: the feed's market-wide fetch (every build read the latest days' filings of all three markets into
  data/events/, and nothing read the rows), its abnormal-move labels and the old per-stock title fetchers in cninfo.py,
  hkex.py and sec.py. The deep-dive lane with its quote checks; the verdicts (veto or confirm with an expiry).
- The DeepSeek notes (folded into the results review); WeChat and PDF delivery; the scoreboard.

## Sources for the method
Stockopedia StockRanks and NAPS (stockopedia.com/academy, "What are the StockRanks", "Strategies for systematic
investors"); AAII Shadow Stock Portfolio (aaii.com/model-portfolios/shadowstockinvesting); Jensen, Kelly and Pedersen,
"Is there a replication crisis in finance?" (JF 2023); McLean and Pontiff (JF 2016); Liu, Stambaugh and Yuan, "Size and
value in China" (JFE 2019); Jansen, Swinkels and Zhou, "Anomalies in the China A-share market" (PBFJ 2021); Asness,
Frazzini and Pedersen, "Quality minus junk" (RAST 2019); Novy-Marx (JFE 2013); Sloan (TAR 1996); S&P DJI, "How smart
beta strategies work in the Hong Kong market". Stage 3: Chan, Jegadeesh and Lakonishok, "Momentum strategies" (JF 1996);
S&P DJI, "Do earnings revisions matter in Asia?" (2017); Asness, Porter and Stevens, "Predicting stock returns using
industry-relative firm characteristics" (2000); S&P DJI's S&P Quality, Value & Momentum Multi-Factor Indices (top 20%
by score, weighted by market value × score; Indexology, 2026-05-28) and "Harnessing multi-factor strategies close to the
core" (2021: the QVM Top 90% indices keep the benchmark's sector weights); Innes, Jain and Ponnala, "Exploring
techniques in multi-factor index construction" (S&P DJI 2021: sector-neutral selection and score-based weighting are
more efficient); MSCI Diversified Multiple-Factor Indexes Methodology (May 2022: value and quality sector-relative,
sectors within ±5% of the parent, each stock within ±2% of its parent weight); the UCITS Directive's 5/10/40 rule.

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
- Phase 11: data/deepdive/<market>/ keeps the verified facts per filing read (a few KB each, at most 9 a day, deleted after 400 days); filing documents are read in memory and never stored; data/verdicts.csv is tiny.
- History tables (Phase 7, data/history/, kept; cleanup doesn't touch them), for valuations v2/v3 and the backtest:
  - Phase 13: us_frames (SEC frames, every filer's revenue, net income and equity per calendar year 2009-2025, 2.1 MB; new years once, the last two again every 30 days), us_sic (SEC SIC code per filer with $100m+ revenue and per candidate, from the submissions files, once each), cn_sw (申万 classification change history, weekly), cn_annual back to 2009 (was 2015). Backtest only: data/backtest/us_quarterly.csv.gz (every US 10-Q/10-K period by filing date, 878 companies, 1.3 MB; companyfacts read once each and not stored); us_annual also carries R&D from that read (not refreshed).
  - us_annual: one row per company and fiscal year since 2015: revenue, gross and operating profit, net income (also to common and from continuing operations), operating cash flow, capex, dividends paid, diluted shares, equity, preferred, assets, liabilities, shares, in the reporting currency, with the first filing date. From the companyfacts files the weekly SEC fetch reads anyway; Yahoo for the companies SEC has none for (Sundays, every 90 days).
  - cn_annual: 业绩报表 for every fiscal year since 2015 with 扣非 EPS and weighted ROE (each year once; the latest weekly while its reports come in). cn_valuation: close, market value, shares, PE-TTM, PB-MRQ, PS-TTM on the last trading day of every half-year since 2018-12 (one fetch per half-year).
  - hk_results: Eastmoney main indicators since 2015 (amounts in CNY, as in the weekly table), fetched once and topped up from the weekly table.
  - us_monthly / hk_monthly and us_splits / hk_splits: ~11 years of month-end closes as traded and monthly total returns for the candidates, the index and the FX rates own-history P/B needs (HKDCNY=X; the US reporting currencies as <CUR>=X); new months on Sundays.
  - cn_forecasts: the market-wide 业绩预告 table, daily from a week before the newest notice (started with the last 400 days).
  - cn/us/hk_consensus: the consensus table appended once a week with its snapshot date (no longer needed for the
    revisions: stage 3 reads the past estimates from Yahoo and the report archive).
  - Stage 3: cn_reports (every company research report's EPS estimates, one row per report and fiscal year, the last 300
    days, ~0.14 MB, daily top-up); fundamentals/us_trend (next year's US consensus now and 90 days ago, weekly),
    cn_index / us_index (the CSI 300's and S&P 500's weights, daily), quotes/hk_yahoo_shares (HK-listed shares, daily);
    a few tens of KB each.
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
  - 扣非 net profit per quarter (stage 1, verified 2026-10-24): Eastmoney datacenter 主要财务指标
    RPT_F10_FINANCE_MAINFINADATA filtered by REPORT_DATE and the A-share types: KCFJCXSYJLR (year-to-date 扣非 net
    profit, CNY) with the first NOTICE_DATE, ~6,500 rows a quarter back to 2015 (99.4% filled for 2026-06-30), ~22 s a
    quarter. data/history/cn_deduct.csv.gz (2.6 MB, 2015-03..), each quarter once, the open one daily.
  - Announcements: CNINFO. Phase 11: the same query without a stock gives the whole market per day (Method 14); periodic reports by category (category_ndbg_szsh, _bndbg_, _yjdbg_, _sjdbg_); PDFs at static.cninfo.com.cn, text by pypdf (most read; some A+H issuers' PDFs have fonts without a Unicode map).
  - Second source for the quotes (Phase 12, verified 2026-10-19): Tencent qt.gtimg.cn, 60 codes per call, GBK, fields split by ~: 3 price, 4 previous close, 30 time (YYYYMMDDhhmmss), 39 PE-TTM, 45 total market value (100m CNY; 44 is the float value), 46 P/B, 73 total shares. Daily for the 1,200 largest A-shares (20 calls, ~1 s); 1,197 answered. Price, market value and shares matched Eastmoney's quote table exactly for all 800 of the universe.
  - 申万 industries for daily use (Phase 13, verified 2026-10-19): swsresearch.com's change-history file (codes only; the 31 level-1 names of the 2021 scheme are fixed), weekly with curl (its certificate chain isn't in Python's trust store); every one of the 791 CN stocks matched, and Eastmoney's BOARD_NAME (the 申万 level 2 name) maps to one level 1 for all but 5 names.
  - Research reports for the revisions (stage 3, verified 2026-10-26): reportapi.eastmoney.com/report/list, qType 0,
    100 a page at most one call per 2 s (Referer data.eastmoney.com): stock code, broker, publish date and
    predictThisYearEps / NextYear / NextTwoYear, labelled by the year the page is read in (a 2025-06 report read in 2026
    shows its 2026 and 2027 estimates; earlier years are blank), so the year is fixed when read. ~90 reports a day;
    the first read of 300 days took 88 pages. Its broker counts are a third to a half of 研报一致预期's analyst counts
    (which count analysts over a longer window), so 3+ brokers at both dates covers ~30% of the 800 (44% of the
    largest 300). Bonus shares: RPT_SHAREBONUS_DET's BONUS_IT_RATIO (送转 per 10 shares), with the dividends.
  - CSI 300 weights (stage 3, verified 2026-10-26): CSI's month-end file
    oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/closeweight/000300closeweight.xls (300 rows,
    weights in %, the date first), read with xlrd. Banks are 12% of the CSI 300 against 24% of the largest 300's total
    market value (state holdings aren't free float), 石油石化 1.7% against 7.4%.
  - Backup: the Tushare token in .env.
  - The a-stock-data skill documents many CN endpoints.
  - Backtest (verified in Phase 9, 2026-10-18): 通达信 packages exist from 2021-08-13; RPT_VALUEANALYSIS_DET has every trading day from 2018-01-02 (pageSize 5000: one request a day; CHANGE_RATE = close ÷ ex-rights prev-close, identical to the packages), but only for companies still listed (delisted ones are dropped from it and from 业绩报表); 业绩报表 back to 2009; the 申万 change history (swsresearch.com xls; Python's TLS client is refused, curl works); the research-report archive (reportapi report/list) pages to the end, but its predict*Eps fields are relative to today (2019-2023 reports have none, 2024 reports only FY2026); RPT_RES_PROFITPREDICT and RPT_WEB_RESPREDICT hold the current years only; CNINFO's market-wide query stops after ~80 pages a day; the Tushare token has no API access.
- US (verified in Phase 4, 2026-10-17):
  - Universe: the Nasdaq screener, api.nasdaq.com/api/screener/stocks?tableonly=true&download=true (every NASDAQ/NYSE/AMEX listing in one call: price, market value, sector, industry). Its market value is company-wide on every share class and ADR, so shares = market value / price; its price can lag Yahoo by a day, so market value is rescaled to Yahoo's close and a stock whose screener price matches none of Yahoo's last 3 closes within 1% is dropped. Share counts (2026-10-25, crosscheck.us_shares): the screener's count is wrong at times (Monster's 2:1 split of 2026-08-11 counted 3:1, Cboe 7% high) and adds Up-C units and voting-only classes that the parent's profit and book leave out (Carvana, TKO, Symbotic, Blue Owl: 30-370%; Ferrari's special voting shares, On's class B). So before the universe is cut, three counts in the listed security's units (an ADR's depositary shares) are judged by the filings: the screener's and Yahoo's two quote counts (v7 quote, 11 calls a day: impliedSharesOutstanding, every class, as Alphabet's three and Berkshire's in B shares; sharesOutstanding, the listed class, as an Up-C's class A). The judges, in the filer's units, × Yahoo's splits since: SEC's basic weighted-average shares of the latest quarter (the EPS denominator) and the latest 10-Q/10-K cover count; for filers with neither (20-F filers), the last annual EPS denominator, only where Yahoo's two counts agree (Itau's 20-F tags one class's count: half the company). The screener's count stands when a judge is within 5% of it (often it is the cover's, newer than the quarter: Gartner's buyback, the shares Martin Marietta and Public Storage issued in acquisitions since); else the first Yahoo count a judge is within 5% of is used; else, more than 20% off every other count, the stock is dropped (rule 5). Yahoo's statement count (OrdinarySharesNumber) is no judge: it leaves out AB InBev's restricted shares, sums Blue Owl's Up-C classes, puts Berkshire in A shares and CME in thousands, and a version that used it set Martin Marietta and Public Storage back to July. Why the parent's count: the published value research's market equity is CRSP's shares of the listed classes (summed across classes, as for Alphabet and Berkshire) against Compustat's parent earnings and common equity, with S/P on consolidated revenue over that market value; an Up-C's unlisted units aren't in it. Not settled, the screener's count stands: an Up-C without an SEC count (Ares: its filings tag the counts per class only, which companyfacts leaves out, and its two Yahoo counts look like Berkshire's; the per-class counts are only in the 10-Q's XBRL instance) and a dual-listed company (Rio Tinto: the screener's is the plc's, the profit the group's). The Eastmoney list (push2 clist) is blocked, as for CN. The 1,100 largest ordinary shares are kept up to date (config `us_candidates`).
  - Trailing-12-month fundamentals: SEC companyfacts (data.sec.gov/api/xbrl/companyfacts), 4 at a time, at most ~8 requests/s, User-Agent = SEC_USER_AGENT from .env; refreshed weekly per company (~5 min for 1,100). Files are 1-8 MB: they are parsed in memory and never written to disk. TTM = year-to-date + last fiscal year - same YTD a year earlier (the CN formula), or, after an annual report for less than a year (a fiscal-year change's transition period, a merger's successor stub), the fewest reported periods added and subtracted end to end that span the 12 months (not otherwise: L3Harris tags its fiscal-year revenue with Q4's dates); growth = TTM vs the TTM a year earlier. Concepts are merged per period in a preference order because companies switch tags between filings, with three rules from the Phase 12 cross-checks (2026-10-19), also in the annual history: revenue is chosen per period, because companies also tag parts of it with its concepts (ASC 606 fee revenue at M&T, AmEx and SoFi, Blue Owl's "Revenues", Zions' non-interest revenue subtotal) and totals before intersegment eliminations (Williams' ASC 606 total, Hasbro's "Revenues"): the concept within 5% of what the income statement implies (gross profit + cost of revenue, else operating income + total costs and expenses), else the largest concept (REITs' rent: OperatingLeaseLeaseIncome), and for banks net interest + noninterest income when larger; a 12-month figure comes only from a 10-K (Comfort Systems' Q1 2026 10-Q tagged Q1 2025 revenue as the 2025 year); equity and net income are the parent's: the total including minorities less MinorityInterest when only the total is tagged (AT&T, Carlyle, TPG, Royalty Pharma), ProfitLoss less the minorities' share when NetIncomeLoss is missing (Invesco).
  - Gaps (changed in the Phase 4 review; freshness: 200 days, 300 for half-year reporters): Yahoo fundamentals-timeseries (ws/fundamentals-timeseries/v1/finance/timeseries), one call per company, weekly, for companies SEC can't cover: no recent us-gaap 10-Q/10-K (foreign filers), no CIK, or a missing field (e.g. MLPs report partners' capital). It gives TTM revenue / profit / gross profit / operating cash flow and the balance sheet in the reporting currency; growth is TTM vs the TTM a year earlier, else the fiscal year a year earlier, else the same quarter a year earlier, else the last two fiscal years (semiannual reporters). 259 of 262 gap companies covered on 2026-10-17 (~80 s); 796 of the top 800 have complete data. Changed in Phase 12: fetched weekly for all 1,100 candidates (gap companies first), as the second source of the cross-checks, with NetIncome (before preferred dividends) and OrdinarySharesNumber added; ~5 min the first time.
  - Not used: FMP's free key. It served 7 of 184 gap companies (402 "premium" for ASML, NVO, SAP, AZN, SHEL, HSBC, TM, RY...) and stops at ~250 calls a day, which dropped 168 of the top 800.
  - Annual history (Phase 7): the same companyfacts files, forms 10-K, 20-F and 40-F, in us-gaap or ifrs-full: 20-F filers such as TSM and NVO report in ifrs-full (NVO has no ProfitLossAttributableToOwnersOfParent: ProfitLoss and Equity instead), ASML and BABA in us-gaap. One currency per company, the one with the most annual figures (TSM: TWD; its USD convenience figures cover the same years but appear only once each). Companies SEC has no annual history for: Yahoo fundamentals-timeseries annual types (4-5 years).
  - Monthly prices (Phase 7): the Yahoo chart API with interval=1mo and events=div,split over 11 years, for the candidates, ^GSPC and FX (<CUR>=X). Yahoo's closes are split-adjusted (NVDA Nov 2015: 0.79); they are stored as traded (× later split ratios: 31.72) to match the book value per share reported then, and monthly returns come from adjclose. Bars start at local midnight, and the current month appears twice (month start and last trade): only complete months are kept.
  - Analyst consensus EPS (added in Phase 4, for the forward lens and check 2): Nasdaq api/analyst/<symbol>/earnings-forecast, the first three fiscal years not yet reported; analysts = estimates behind next year's EPS. 2-4 s per call, so 4 at a time, weekly (~13 min for 1,100).
  - Revisions (stage 3, verified 2026-10-26): Yahoo quoteSummary modules=earningsTrend for the 1,100 candidates, weekly
    (~7 min): the +1y period's avg, numberOfAnalysts, earningsCurrency and epsTrend's 90daysAgo (the same fiscal year:
    MU's +1y is FY2028, 162.9 then and 206.9 now, while its 0y FY2027 was 153.9 then). epsRevisions counts up and down
    revisions for 7 and 30 days only (90 days is blank).
  - S&P 500 weights (stage 3, verified 2026-10-26): SPY's daily holdings file,
    www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx (the old intermediary path
    redirects there): Name, Ticker, ..., Weight (%), an "As of" line; 503 lines, cash lines without a ticker left out;
    read with zipfile and ElementTree. Share classes are summed per issuer by SEC CIK (GOOGL + GOOG).
  - Price history and dividends: the Yahoo chart API (v8/finance/chart), one call per stock, incremental. It answers 429 to a full browser User-Agent but works with "Mozilla/5.0". Returns come from the adjusted close inside each response (splits and dividends included), stored as close + implied prev_close like the CN table. Index: ^GSPC (stored as SPX). The fetch updates every stock behind the newer of the index's and the largest candidate's latest day; the trading days (the screen's last day, momentum and volatility) are the days with prices for at least half as many stocks as the busiest day, in every market (2026-10-21 fix: Yahoo's ^HSI skipped 2026-10-20).
  - 10-year yield: FRED DGS10 (FRED_API_KEY).
  - FX for gap companies reporting in another currency: Yahoo "<CUR>=X" (21 currencies on 2026-10-17; ECB rates via frankfurter have no TWD, CLP, COP, PEN or KZT).
  - Headlines: the SEC filing list (data.sec.gov/submissions), see Method 8.
  - Base-rate panel (Phase 13, verified 2026-10-19): SEC frames data.sec.gov/api/xbrl/frames/us-gaap/<concept>/USD/CY<year>[Q4I].json, one concept's figure for one calendar year from every filer, dead companies included (CY2016 net income: 6,779 filers); ~1 MB each, 9 concepts a year (revenue concepts, NetIncomeLoss / ProfitLoss, StockholdersEquity at the year end, which 10-Q balance sheets fill for other fiscal years). SIC codes from data.sec.gov/submissions (0.1-1 MB each, read once per filer). Foreign filers report in IFRS and aren't in the us-gaap frames; their SIC code still comes from submissions.
  - Market-wide filings (Phase 11; unused since the market-wide feed was removed on 2026-10-26): SEC full-text search efts.sec.gov/LATEST/search-index?forms=...&startdt=&enddt=&from= (100 a page, `items` per 8-K, the document path in `_id`); filing documents at www.sec.gov/Archives/edgar/data/<cik>/<accession>/<document>.
- HK (verified in Phase 5, 2026-10-17):
  - Company list: Eastmoney datacenter RPT_HKF10_INFO_ORGPROFILE (every HK profile: name, ORG_CODE, industry, GICS-style industry type, organisation type, listing date; ~7,000 rows incl. delisted names, weekly). The Eastmoney list (push2 clist, fs = m:128+t:3,m:128+t:4,m:128+t:1) is blocked, as for CN and US.
  - Results: Eastmoney datacenter RPT_HKF10_FN_MAININDICATOR, one market-wide table filtered by report date (periods ending in the last ~2.2 years, ~12,500 rows; weekly, daily in March, April and August): year-to-date revenue and profit, growth (in the reporting currency, like Eastmoney's CN 业绩报表), BPS, gross margin, operating cash flow, debt/assets, issued shares, and Eastmoney's market value, PE-TTM and PB for the candidate list and the consistency checks. The 1,200 largest ordinary shares by that market value are kept up to date (config `hk_candidates`). TTM = year-to-date + last fiscal year - same period a year earlier, on each company's own fiscal year (the row's start date: March, June... year ends).
  - History (Phase 7): the same table since 2015-01-01, ~70,000 rows (140 pages), also ROE_AVG and BASIC_EPS (added to the weekly fetch too). Its TOTAL_MARKET_CAP, PE_TTM and PB_TTM are today's values on every row, not history, so the history table leaves them out. Monthly prices as for US (0700.HK, ^HSI), plus HKDCNY=X, since book values are in CNY.
  - Its amounts are all in CNY, converted at each period-end rate (HSBC and AIA at 7.0288 CNY per USD for FY2025), and no field names the reporting currency. About 30% of HK companies report in HKD or USD; with the 2026 RMB move, reading their amounts as CNY at today's rate would overstate profit and book by 2-6%. So each row goes back to the reporting currency (Yahoo's, below) at that period end's rate (Yahoo '<CUR>CNY=X' close, ~0.5% from Eastmoney's rates), the TTM is summed there, and converted to HKD at today's rate.
  - Not Yahoo fundamentals-timeseries: its HK trailing series stops at December 2025 for 563 of 1,154 candidates (half-year interims are missing), so the TTM would be six months stale.
  - HK-listed shares (stage 3, verified 2026-10-26): Yahoo's v7 quote sharesOutstanding is the listed class (ABC's 30.7bn
    H shares of 350bn, ICBC's 86.8bn of 356bn; Tencent's one class), daily, 12 calls; the parent's weights are these
    shares × price.
  - Consensus EPS and the reporting currency: Yahoo quoteSummary earningsTrend + earnings (this and next fiscal year, last year's actual, analyst count, estimate currency; financialCurrency), one call per stock, weekly (~8 min for 1,200); it needs Yahoo's A3 cookie (from fc.yahoo.com) and the crumb for it. Eastmoney's RPT_WEB_RESPREDICT has no HK rows. 384 of the 1,200 candidates have 3+ analysts (2026-10-17). Phase 12: the same call also asks for defaultKeyStatistics and summaryDetail (book value and trailing EPS per share in HKD, impliedSharesOutstanding, mostRecentQuarter) for the cross-checks; a table without them is fetched again for every stock once (~8 min). Stage 3: also the +1y
    estimate 90 days ago (epsTrend), for the revisions; fetched again for every stock once on 2026-10-26 (~16 min).
  - Price history and dividends: the Yahoo chart API (symbol 0700.HK), as for US, with the same trading-day rule; index ^HSI (stored as HSI). ~9 min for the first 385 days of 1,200 stocks.
  - 10-year yield: hkgb.gov.hk daily closing reference pricings workbook (HKD_DailyClosingReferencePricings_IBPandGSBP.xls, benchmark 10-year), read with xlrd. The HKMA API (api.hkma.gov.hk, IBP/GSBP) stops at June 2026 (monthly bulletin) and answered 405 after ~7 quick calls.
  - Issuer ids for the dedupe: ORG_CODE from the HK profiles above, the CN quotes (RPT_VALUEANALYSIS_DET) and Eastmoney RPT_USF10_INFO_ORGPROFILE (every US ticker, weekly).
  - Board lots (stage 1, verified 2026-10-24): HKEX's List of Securities,
    www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx (one sheet, inline strings,
    read with zipfile and ElementTree; no Excel package): stock code, category, board lot (it also lists short-sell eligibility,
    unused: the old stage 3's 可做空 label was dropped). 2,817 equities; weekly into data/fundamentals/hk_lots.csv.gz.
  - Headlines: HKEXnews titleSearchServlet.do with the stockId from activestock_sehk_c.json. Phase 11: stockId -1 with a one-day range returns all of a day's filings in one call (rowRange 5000); t1code 40000 (lang en) lists a stock's annual and interim reports.
  - FX: Yahoo "<CUR>=X" for HKD and the reporting and estimate currencies (CNY, USD, SGD, JPY, EUR...), and ~900 days of daily "<CUR>CNY=X" closes for the period-end rates.
- FX, only needed when a company reports in a different currency from the one it trades in: ECB rates via api.frankfurter.dev.
- Legacy references (read only), all under ~/Developer/EquitySignalsClawbot-legacy/:
  - Sources/EquitySignalsClawbotCore/PublicUniverse.swift (around line 1310, the Eastmoney list call)
  - Sources/EquitySignalsClawbotCore/MacroPanel.swift (rate sources)
  - Sources/EquitySignalsClawbotCore/EastmoneyHKFinancialStatements.swift
  - script/a_stock_snapshot_sidecar.py (Tencent/Sina A-share calls)
