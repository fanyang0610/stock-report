# Plan

## Status (update at the end of each phase)
- Phase 1 Foundation + delivery test: done 2026-10-17 (TEST text + PDF arrived on the phone, PDF opens)
- Phase 2 CN data + valuation: done 2026-10-17 (CN picks reviewed; data sources and the valuation method were changed in the review, see Method 4 and Data sources)
- Phase 3 CN notes + report + keyword: done 2026-10-17 (DeepSeek notes in the CN PDF; texting 股票报告 returned the CN summary + PDF in ~4 s; listener cadence changed, see Method 9)
- Phase 4 US: done 2026-10-17 (US picks reviewed; texting 股票报告 returned CN + US; US build from cache 24 s. Review fixes: foreign filers from Yahoo fundamentals instead of FMP, negative-book companies on the forward lens; see Method 4 and Data sources)
- Phase 5 HK + full 45-stock report: done 2026-10-17 (HK picks reviewed; texting 股票报告 returned the full US + HK + CN report; HK build from cache 44 s; issuer dedupe by Eastmoney ORG_CODE. Review fix: financials valued on peer P/B and the forward lens, no justified P/B (insurers were at +200-316%), see Method 4; HK amounts undo Eastmoney's CNY conversion, see Data sources)
- Phase 6 Daily schedule + tracking: code done 2026-10-17, waiting on the 06:30 builds of 2026-10-18 and 2026-10-19 (all three markets in 96 s from cache; the launchd job is installed and a test run exited cleanly in 86 s; `track` prints the scorecard, blank until the first week has passed; data/ + reports/ 42 MB)
- Phase 7 History data, production fixes, bucket names: done 2026-10-18 on the worktree branch claude/phase-7-history-data-f7fece, not merged (Phase 6 still waits on the main checkout's 06:30 builds). 5+ annual years of history: US 770/796 (96.7%; of the other 26, 17 listed under 5 years, 9 are new holding-company CIKs or foreign filers with only Yahoo's 4 years: XOM, BLK, SW, VNOM, PNFP, FER, IBN, CNI, CIB), HK 394/407 (96.8%; all 13 others listed under 5 years), CN 798/798. Tables 13.8 MB. `run --no-notes` from cache took 73 s against 57 s before, on a Sunday (the new steps take 0.6 s on a weekday, ~15 s on Sundays); it excluded 2 US, 4 HK and 3 CN buy/hold candidates by checks 1-2 (WDC, Allstate, 中国人寿 H, 江波龙...) and the report and summary read 买入 / 持有 / 卖出. 59 tests pass. At the merge: remove the untracked docs/REVIEW.md in the main checkout first (this branch commits the same file); the first build afterwards backfills the history once (~35 min).
- Delivery format that works on the phone (PDF or image): PDF (A4, headless Chrome 155 with --no-pdf-header-footer, ~460 KB; opens in WeChat on the phone)

## Decisions
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

## Method

### 1. Universe (per market)
- Exclude:
  - CN: ST/*ST, delisting-period and suspended stocks, and stocks listed under 1 year.
  - HK/US: non-ordinary securities (ETFs, funds, warrants, preferreds, SPACs, OTC) and stocks listed under 1 year.
  - US (Phase 4): preferreds, notes, units and fractional depositary shares are dropped by listing name (ADRs, MLP common units and names that say ordinary/common shares stay); only the most traded share class per issuer (SEC CIK) is kept, e.g. GOOGL not GOOG.
  - HK (Phase 5): ordinary shares are Eastmoney company profiles with an organisation type (REITs, ETFs and other funds have none), without the RMB counters (8xxxx). Market value = all issued shares (H + A + unlisted domestic shares) × the HK price, as Eastmoney counts it. Privatised and merged names still in Eastmoney's list (Hang Seng Bank, Haitong, Dongfeng, ESR...) have no Yahoo prices and fall out at "traded on the last day".
- Liquidity: 20-day average daily turnover of at least ¥50m (CN), HK$20m (HK) or US$10m (US). These are config values.
- Keep the top 800 by total market value.
  - HK (Phase 5): only 413 of the 941 HK stocks listed a year or more pass HK$20m (2026-10-17), so the HK universe is ~410 names, not 800; 407 have complete data (dropped: 1 without a reporting currency from Yahoo, 3 with missing results, 2 with short price history).

### 2. Peer groups
Use the industry from the data source (the Eastmoney industry field in v1). Merge groups with fewer than 8 members into the nearest broader group, or compare them market-wide.
- HK (Phase 5): the Eastmoney HK industry (BELONG_INDUSTRY, ~30 Hang Seng-style groups); groups under 8 are compared market-wide. Banks, insurers and brokers are an exact list of sub-industries, the last level of Eastmoney's GICS-style HK industry type (config `financial_industries_hk`). HKEX, asset managers, lessors and consumer lenders are valued like other companies, as in CN and US.
- US (Phase 4): the Nasdaq screener industry; a non-financial industry with fewer than 8 members in the universe becomes "<Nasdaq sector> (other)". Banks, brokers and insurers are an exact list of Nasdaq industries (config `financial_industries_us`). "Specialty Insurers" is left out: in the US universe it holds the insurance brokers (Marsh, Aon, Gallagher, WTW, Brown & Brown), which the insurer method valued on goodwill-heavy books (Gallagher at -67%).

### 3. Metrics
Use the latest data, trailing 12 months where possible:
- price, market value, P/E, P/B, ROE
- revenue growth, net profit growth, gross margin
- debt/assets, operating cash flow ÷ net profit, dividend yield
- 12-month price return excluding the last month
- 1-year volatility

Winsorize each metric at the 2nd and 98th percentile within the market.
- Phase 7: cash conversion (operating cash flow ÷ net profit) is clipped to [−1, 3] and left out when the net margin is under 2% (config `[universe]`). It exploded on tiny profits and mixes consolidated cash flow with attributable profit: 91 US, 86 HK and 124 CN names were above 3 (兖煤澳大利亚 31.6 made a "top-30% quality" hold).

### 4. Fair value (per stock, in its quote currency)
- Banks, insurers and brokers: the P/B the peer group pays for that ROE (a cross-sectional fit of log P/B on ROE), plus the forward lens like other companies. Loss-making financials have no trailing value.
  - Changed in the Phase 5 review: until then this was blended 50/50 with the justified P/B = (ROE − g) / (r − g), and financials had no forward lens. That put Chinese insurers at +200-316% (中国人寿 H +238%, 中国太平 +316%, 中国人寿 A +192%), for two reasons. (1) It is an absolute anchor with one market-wide r, while each market prices its financials at its own implied cost of equity (Chinese banks ~13%, Chinese insurers ~20%, US banks ~8%), so whole-sector discounts became stock "upside": the median financial showed +42% in CN and +37% in HK, -12% in the US (peer-only: +9%, +10%, +3%). (2) It is a perpetuity on one year's ROE, and insurers' 32-37% TTM ROE is 2026 investment gains; analysts expect 16-28% next year. Now the largest insurer upsides are +44% (CN, 中国太保), +47% (HK, 中国人保), +56% (US, Everest), and 中国人寿 is +8% (A) / +4% (H).
- Other profitable companies: the P/B the peer group pays for similar ROE and growth (a fit of log P/B on ROE and growth within the group). Changed from P/E in the Phase 2 review: in A-shares the P/E fit gets a negative ROE coefficient in every group (low ROE usually means depressed earnings and a high P/E), which made cheap low-ROE stocks look undervalued.
- Loss-making companies: P/S fitted on gross margin and growth. If no fit is possible, the stock has no fair value and is excluded.
- Negative book value (added in the Phase 4 review): P/B means nothing, so a profitable company with negative equity (mostly US buyback stocks: ABBV, MCD, BKNG, HLT, LOW, PM...) is valued on the forward lens alone, at normal conviction, and has no ROE (quality comes from margin, cash conversion and leverage). Without 3 analysts it has no fair value. Before, these were dropped: 35 of the US top 800. No CN stock is affected today.
- Forward lens (added in the Phase 2 review, because trailing numbers make one-off profit spikes look cheap and early fast growth look expensive): for non-financials with at least 3 analysts, also fit log forward P/E (price ÷ next year's consensus EPS) on expected EPS growth (2-year consensus CAGR) within the peer group. Fair value mid = 50/50 trailing and forward value (trailing only when there is no forward lens); the range always covers both. If the two lenses point opposite ways versus the price and differ by more than 50%, mark 低信心. Consensus EPS only; analysts' target prices and ratings are never used.
- HK forward lens (Phase 5): Yahoo has consensus EPS for this and next fiscal year only, so expected EPS growth is the 2-year CAGR from last year's actual EPS (Yahoo's own, often adjusted) to next year's consensus; forward P/E is on next year's consensus, as in CN and US.
- Fair value mid = fitted multiple × the company's own metric.
- Fair value low/high = from the 25th/75th percentile of the group's fit residuals.
- r = 10-year government bond yield + equity premium (CN 6%, HK 6%, US 5%), a config value. It is only used by the residual-income cross-check.
- Absolute cross-check: a simple residual-income value at the same r (excess ROE fades linearly to r over 10 years), kept in the picks CSV for reference. It does not set 低信心 (Phase 2 review: at r ≈ 7.7% the RI value is typically ~1/2.7 of what peers pay, so it flagged 44–79% of the market, including real growth stocks; the forward-lens disagreement is the 低信心 signal instead).
- Upside = fair value mid / price − 1.

### 5. Scores (sector-neutral z-scores within each market)
- Value: upside, earnings yield, book yield (for financials)
- Quality: ROE, gross margin, cash conversion, low leverage
- Growth: revenue and profit growth
- Momentum: 12-month return excluding the last month
- Risk: low volatility

Composite = 0.35 value + 0.25 quality + 0.15 growth + 0.15 momentum + 0.10 risk. The weights live in config.toml.
- Phase 7: each component is standardized within financials and within the rest before the market-wide z-score. Financial quality is ROE alone and the others average four metrics, so financials' quality scores spread wider and crowded the top (spread financials vs rest: US 1.55 vs 0.84, HK 1.29 vs 0.92, CN 1.35 vs 0.94; now ~1.0 on both sides).

### 6. Buckets (per market, always 5 each)
- 买入 BUY: upside ≥ 15%, quality ≥ peer-group median and momentum z ≥ −0.5. Take the top 5 by composite score.
- 持有 HOLD: quality in the market's top 30% and upside between −10% and +15%. Take the top 5 by quality score. These are good companies priced about right.
- 卖出 SELL: upside ≤ −15%, plus at least one of: quality in the bottom 40%, momentum z ≤ −0.5, or falling profits. The stock must be among the market's 400 largest. Take the 5 with the lowest composite score.
- Phase 7: the labels were 持有/不追高 and 卖出/回避 until then (valuation v2 drops the qualifiers). The report takes the label from the bucket, so older picks CSVs show the new names too.
- Phase 7: buy and hold candidates that fail one-off check 1 or 2 (Method 8) take no place; see Method 8.
- At most 2 stocks per peer group per bucket, and each stock in only one bucket.
- One issuer appears only once in the whole report. A/H pairs come from Eastmoney's AH list; US ADR ↔ HK pairs come from a small CSV in data/ref/.
  - Changed in Phase 5: both come from Eastmoney's company id (ORG_CODE), which is the same for every listing of one issuer (601939 and 00939; BABA and 09988; HSBC and 00005), so no hand-made CSV is needed. The AH list is the blocked push2 API.
  - Which listing stays: CN, then US, then HK. When an issuer is picked in two markets, the A-share (the primary listing of an A/H issuer) or the US listing (the China ADRs listed in New York first; most of their HK lines are secondary listings) stays, and the HK pick is swapped for the next HK runner-up the same way as an AI flag, listed in the report as 其他市场已入选.
- If a bucket has fewer than 5 qualifying names, fill it with the next-ranked ones and mark them 低信心.

### 7. Stock cards
Each card shows:
- ticker, name and action
- price with its date
- fair value low/mid/high and upside
- the 2 drivers (largest score contributions, in plain words)
- key risk (the weakest score)
- re-check trigger, rule-based. Example for a buy: "re-check if the price falls below the fair-value low or profits decline next quarter".
- the DeepSeek note
- conviction (normal or 低信心)

### 8. AI notes (DeepSeek)
- Use the OpenAI-compatible API with base URL https://api.deepseek.com. Check their docs for the current chat model name. The key is DEEPSEEK_API_KEY in .env.
- Input per pick: the card's numbers plus up to 10 announcement/news titles from the last 60 days (CN: CNINFO; US: SEC filing list; HK: HKEXnews).
  - HK (Phase 5): HKEXnews title search in Chinese (traditional characters). Routine filings are skipped: next-day disclosures, monthly returns, share-award grants, board lists, letters and forms to holders, and the governance rules A+H issuers repost from their A-share filings ("海外監管公告").
  - US (Phase 4): the SEC list has no headlines, only form types and 8-K item numbers, so a title is "date form: description" (e.g. "8-K: Results of operations", "DEFM14A: Merger proxy"). Routine forms (insider trades, 13G, prospectuses) are skipped, and so are the bare 8-K labels 7.01 "Reg FD disclosure" and 8.01 "Other events": DeepSeek cited "Other events" as one-off-gain evidence for Incyte. Revenue and profit are shown to DeepSeek in 亿美元.
- Output JSON:
  - note: at most 60 Chinese characters
  - risk: at most 30 characters
  - flag: none | one_off_gain | pending_deal | delisting_or_st | data_suspect
  - reason
- Use a low temperature and validate the JSON.
- Any flag other than none swaps the pick for the next-ranked candidate; log the swap. Numbers are never changed.
  - Phase 3: the model is deepseek-flash (GET /models, 2026-10-17), with thinking off, JSON output and temperature 0.
  - one_off_gain rules (Phase 3 fix). The first version flagged 8 names inconsistently: it flagged 江波龙 but not 中际旭创, and it flagged 中国人寿 for investment income. Prompt rules alone stayed flaky, so code computes three checks for buy/hold candidates, shows them to DeepSeek and enforces them. Thresholds are in config `[notes]`.
    - Check 1: profit growth > 100% and operating cash flow / net profit < 0.5. Not used for banks, brokers and insurers, whose investment and trading income is core business.
    - Check 2: at least 3 analysts and next year's consensus EPS < 60% of trailing EPS.
    - Checks 1 and 2 always set one_off_gain, in code, even if DeepSeek says none.
    - Changed in Phase 7: checks 1 and 2 run in pick.py, for every buy and hold candidate, before the buckets are filled. Until then they were enforced only in the DeepSeek path, so `--no-notes`, a missing key or an API failure shipped the names (on 2026-10-17: ALL, WDC, 09995, 00966, 03888, 301308, 001309, 688331, 688336). A candidate that fails either takes no place; the ones that would have been picked stay in the picks CSV as role `excluded` with the reason, and the report and summary list them as 利润异常已剔除. DeepSeek still sees all three checks; check 3 with a quoted title can still flag a pick.
    - Check 3: profit growth at least 30 points above revenue growth. Only then can a one-off item in the titles (an asset or stake sale, investment or fair-value gains, a licence upfront payment, a subsidy) flag a stock.
    - Title-based flags (one_off_gain via check 3, and pending_deal) must quote a title we sent in the reply's `evidence` field; code clears them otherwise.
    - The sell bucket never uses one_off_gain, enforced in code: a one-off gain only adds to overvaluation.
    - Measured on 45 CN candidates, 3 fresh runs: every candidate got the same flag in all runs. Today's CN report swaps 4 picks: 江波龙 and 德明利 (check 1), 荣昌生物 and 三生国健 (check 2). 天齐锂业 is not flagged: cash conversion 0.51, and analysts expect EPS at 1.76× trailing.
  - Note length: 60 / 30 Chinese characters, with digits, letters and ASCII symbols counted as half. A reply that is still too long after one request to shorten is cut at the last clause break, never mid-phrase (no notes cut in 135 test notes).
  - The bench is 10 runners-up per bucket (config `runners_up`), so a flagged pick always has a next-ranked name. If the bench runs out, the flagged pick stays, marked 低信心.
  - The report and the text summary list every swapped-out name.
- Cache notes per day and ticker. If the API fails, use template text and still ship the report. Expect up to about 60 calls per daily run.

### 9. Report and delivery
- PDF: Jinja2 HTML → PDF via headless Chrome, in the order overview, US, HK, CN. The footer gives the data date per market, a one-line description of the method and "not investment advice".
- Text summary: 45 lines of "代码 名称 动作 现价→公允价 空间%", grouped by market and bucket, at most 4,000 bytes.
- Listener: a launchd job (StartInterval 10) runs `listen`. It polls, matches the keyword (trailing punctuation trimmed, case-insensitive) and sends the newest report: text first, then the PDF.
  - Each run polls for ~55 s. The bot server holds an idle poll ~18 s; polls are never cut short by the client.
  - launchd counts StartInterval from the previous run's exit (measured 2026-10-17), so the next run starts 10 s after one ends and a keyword waits at most ~15 s. Changed in Phase 3: the planned "every 60 s" left a ~60 s gap after each run (a reply took 62 s).
  - Keywords older than 30 minutes (e.g. sent while the Mac slept) are logged, not answered.
  - It always replies. If today's report isn't ready, it sends the newest one with its date in the title.
  - If a send fails, it retries once and logs the failure.
  - It dedupes by message id, stored in data/state.json.
- Only one process may poll the bot. The old listener is stopped.

### 10. Schedule and tracking
- A launchd job runs `run` daily at 06:30 Beijing time: after the US close, and CN/HK use the previous close.
  - Phase 6: `run` without `--market` builds CN, US and HK, then the report once (`launchd/com.stockreport.daily.plist`, output in logs/<date>-daily.log). It never polls the bot. `run --market X` builds one market and the report. The PDF and summary are written to temporary files and renamed, so the listener never sends a half-written report.
  - Measured 2026-10-17: 96 s for all three markets from cache, with cached notes. Sundays (weekly fundamentals and consensus) take ~30 min. A run missed while the Mac sleeps starts when it wakes.
- If a market's fetch fails, reuse its last good data and say so in the report.
  - Phase 6: failed fetch steps keep their cache and are saved in reports/<date>/fetch_failed.json; the market header, the footer and the text summary say 今日部分数据获取失败（steps），沿用上次的缓存数据. A market whose build fails (or that wasn't run today) shows its newest earlier picks with that day's notes, marked 今日未能更新，沿用 <date> 的选股. The report never fails because of one market.
- Every run appends its picks to data/picks.csv: date, market, bucket, ticker, price, fair value mid, composite score, conviction.
  - Phase 6: the final picks after AI swaps and the issuer dedupe, plus name and price_date (the close the pick was priced at). A second run on the same day replaces that day's rows for the market; markets showing earlier picks are not logged again.
- `track` reports the average return by market and bucket against each market's index (CSI 300, Hang Seng, S&P 500) at 1 week, 1 month and 3 months.
  - Phase 6: return from the price_date close to the last close on or before 7, 30 and 91 days later (blank until then), plus to date; chained from close / prev_close like momentum, so dividends count; the indexes are price indexes. "vs index" = average of pick return minus index return over the same days (a sell worked if it is negative). Each stock counts once per bucket and price date (weekend runs repeat Friday's picks). US/HK prices of stocks picked in the last 101 days stay updated even if they leave the candidates; CN packages cover the whole market. Prices are kept 385 days, so the scorecard covers picks from about the last year.

### 11. Storage and cleanup (disk must not grow without limit)
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
- History tables (Phase 7, data/history/, kept; cleanup doesn't touch them), for valuation v2 and its backtest:
  - us_annual: one row per company and fiscal year since 2015: revenue, gross and operating profit, net income (also to common and from continuing operations), operating cash flow, capex, dividends paid, diluted shares, equity, preferred, assets, liabilities, shares, in the reporting currency, with the first filing date. From the companyfacts files the weekly SEC fetch reads anyway; Yahoo for the companies SEC has none for (Sundays, every 90 days).
  - cn_annual: 业绩报表 for every fiscal year since 2015 with 扣非 EPS and weighted ROE (each year once; the latest weekly while its reports come in). cn_valuation: close, market value, shares, PE-TTM, PB-MRQ, PS-TTM on the last trading day of every half-year since 2018-12 (one fetch per half-year).
  - hk_results: Eastmoney main indicators since 2015 (amounts in CNY, as in the weekly table), fetched once and topped up from the weekly table.
  - us_monthly / hk_monthly and us_splits / hk_splits: ~11 years of month-end closes as traded and monthly total returns for the candidates, the index and the FX rates own-history P/B needs (HKDCNY=X; the US reporting currencies as <CUR>=X); new months on Sundays.
  - cn_forecasts: the market-wide 业绩预告 table, daily from a week before the newest notice (started with the last 400 days).
  - cn/us/hk_consensus: the consensus table appended once a week with its snapshot date, so revisions have a record.
  - Measured 2026-10-18: 13.8 MB in all (hk_results 4.8, cn_annual 3.4, cn_valuation 2.6, us_monthly 1.2, hk_monthly 0.9, us_annual 0.6, cn_forecasts 0.4, consensus snapshots 0.06), plus 0.3 MB for 扣非 EPS and ROE in the weekly results tables; growth ~6 MB a year, mostly consensus snapshots and monthly prices. The first build with Phase 7 backfills them once (CN ~10 min; US ~13 min, SEC companyfacts read again for every company plus 1,100 monthly series; HK ~11 min). After that a weekday build adds under 1 s (业绩预告) and a Sunday ~15 s (new months, and re-asking Yahoo for the ~40 HK symbols it has no data for).

## Phases (done when)
1. Foundation + delivery test: TEST text + PDF arrive on my phone, and I confirm the PDF opens.
2. CN data + valuation: `run --market cn --no-notes` builds 15 CN picks from cache in under 5 min, tests pass, and I review the picks CSV and agree they make sense.
3. CN notes + report + keyword: DeepSeek notes appear in the CN PDF, and texting the keyword returns the CN report within 30 s.
4. US: same as Phase 2 for US, and the keyword report contains CN + US.
5. HK + full report: HK picks reviewed, issuer dedupe works across markets, and the keyword returns the full 45-stock report.
6. Daily schedule + tracking: the 06:30 build works on 2 consecutive days, `track` prints a scorecard, and cleanup keeps data/ + reports/ well under 2 GB.

Phases 7-12 are valuation v2 (docs/REVIEW.md rev. 4, Part A; approved 2026-10-18), each built in its own session and worktree. v1 keeps producing the report until Phase 10.

7. History data, production bug fixes and bucket names: history covers ≥ 90% of each universe (say how many of the rest are companies listed under 5 years); the tables add < 50 MB; the daily build grows < 30 s; tests on saved samples pass; a `--no-notes` run in the worktree shows checks 1-2 applied and the report and summary read 买入 / 持有 / 卖出.
8. v2 engine in shadow mode: all three markets run in < 60 s; pre-profit names get no value; no value above 3× price without 低; every stock with a confirmed break shows our probability with its evidence, the market's implied probability and one probability-weighted value; MU-, NVDA- and Omnicom-type cases are checked by hand; tests cover the residual-income math (a hand-checked case), the history-weight rules and the quality screen; I review one day of v2 lists.
9. Backtest, calibration, signal tracking: out-of-sample tables exist for v1 and v2; the parameters come from in-sample and hold out of sample; the switch rule is evaluated and reported to me.
10. Switch the report to v2 (only if Phase 9 says so) and phone-first cards: the keyword reply works in < 30 s with the v2 report; I review the 45 picks; the PDF reads without zoom.
11. Deep-dive lane and event layer: at most 3 deep dives per market per day; cached per filing; every used number has a verified quote (tested on saved filings); every abnormal move on a pick is labelled with or without a matching event; cards show 深度核查 and 近期事件 lines; the 06:30 build grows < 5 min.
12. Data cross-checks and drift alarms: disagreement counts are printed every run and tests use saved samples.

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
  - Announcements: CNINFO.
  - Backup: the Tushare token in .env.
  - The a-stock-data skill documents many CN endpoints.
- US (verified in Phase 4, 2026-10-17):
  - Universe: the Nasdaq screener, api.nasdaq.com/api/screener/stocks?tableonly=true&download=true (every NASDAQ/NYSE/AMEX listing in one call: price, market value, sector, industry). Its market value is company-wide on every share class and ADR, so shares = market value / price; its price can lag Yahoo by a day, so market value is rescaled to Yahoo's close and a stock whose screener price matches none of Yahoo's last 3 closes within 1% is dropped. The Eastmoney list (push2 clist) is blocked, as for CN. The 1,100 largest ordinary shares are kept up to date (config `us_candidates`).
  - Trailing-12-month fundamentals: SEC companyfacts (data.sec.gov/api/xbrl/companyfacts), 4 at a time, at most ~8 requests/s, User-Agent = SEC_USER_AGENT from .env; refreshed weekly per company (~5 min for 1,100). Files are 1-8 MB: they are parsed in memory and never written to disk. TTM = year-to-date + last fiscal year - same YTD a year earlier (the CN formula); growth = TTM vs the TTM a year earlier. Concepts are merged per period in a preference order because companies switch tags between filings; banks without a revenue total get net interest income + noninterest income.
  - Gaps (changed in the Phase 4 review): Yahoo fundamentals-timeseries (ws/fundamentals-timeseries/v1/finance/timeseries), one call per company, weekly, for companies SEC can't cover: no recent us-gaap 10-Q/10-K (foreign filers), no CIK, or a missing field (e.g. MLPs report partners' capital). It gives TTM revenue / profit / gross profit / operating cash flow and the balance sheet in the reporting currency; growth is TTM vs the TTM a year earlier, else the fiscal year a year earlier, else the same quarter a year earlier, else the last two fiscal years (semiannual reporters). 259 of 262 gap companies covered on 2026-10-17 (~80 s); 796 of the top 800 have complete data.
  - Not used: FMP's free key. It served 7 of 184 gap companies (402 "premium" for ASML, NVO, SAP, AZN, SHEL, HSBC, TM, RY...) and stops at ~250 calls a day, which dropped 168 of the top 800.
  - Annual history (Phase 7): the same companyfacts files, forms 10-K, 20-F and 40-F, in us-gaap or ifrs-full: 20-F filers such as TSM and NVO report in ifrs-full (NVO has no ProfitLossAttributableToOwnersOfParent: ProfitLoss and Equity instead), ASML and BABA in us-gaap. One currency per company, the one with the most annual figures (TSM: TWD; its USD convenience figures cover the same years but appear only once each). Companies SEC has no annual history for: Yahoo fundamentals-timeseries annual types (4-5 years).
  - Monthly prices (Phase 7): the Yahoo chart API with interval=1mo and events=div,split over 11 years, for the candidates, ^GSPC and FX (<CUR>=X). Yahoo's closes are split-adjusted (NVDA Nov 2015: 0.79); they are stored as traded (× later split ratios: 31.72) to match the book value per share reported then, and monthly returns come from adjclose. Bars start at local midnight, and the current month appears twice (month start and last trade): only complete months are kept.
  - Analyst consensus EPS (added in Phase 4, for the forward lens and check 2): Nasdaq api/analyst/<symbol>/earnings-forecast, the first three fiscal years not yet reported; analysts = estimates behind next year's EPS. 2-4 s per call, so 4 at a time, weekly (~13 min for 1,100).
  - Price history and dividends: the Yahoo chart API (v8/finance/chart), one call per stock, incremental. It answers 429 to a full browser User-Agent but works with "Mozilla/5.0". Returns come from the adjusted close inside each response (splits and dividends included), stored as close + implied prev_close like the CN table. Trading calendar: ^GSPC (stored as SPX).
  - 10-year yield: FRED DGS10 (FRED_API_KEY).
  - FX for gap companies reporting in another currency: Yahoo "<CUR>=X" (21 currencies on 2026-10-17; ECB rates via frankfurter have no TWD, CLP, COP, PEN or KZT).
  - Headlines: the SEC filing list (data.sec.gov/submissions), see Method 8.
- HK (verified in Phase 5, 2026-10-17):
  - Company list: Eastmoney datacenter RPT_HKF10_INFO_ORGPROFILE (every HK profile: name, ORG_CODE, industry, GICS-style industry type, organisation type, listing date; ~7,000 rows incl. delisted names, weekly). The Eastmoney list (push2 clist, fs = m:128+t:3,m:128+t:4,m:128+t:1) is blocked, as for CN and US.
  - Results: Eastmoney datacenter RPT_HKF10_FN_MAININDICATOR, one market-wide table filtered by report date (periods ending in the last ~2.2 years, ~12,500 rows; weekly, daily in March, April and August): year-to-date revenue and profit, growth (in the reporting currency, like Eastmoney's CN 业绩报表), BPS, gross margin, operating cash flow, debt/assets, issued shares, and Eastmoney's market value, PE-TTM and PB for the candidate list and the consistency checks. The 1,200 largest ordinary shares by that market value are kept up to date (config `hk_candidates`). TTM = year-to-date + last fiscal year - same period a year earlier, on each company's own fiscal year (the row's start date: March, June... year ends).
  - History (Phase 7): the same table since 2015-01-01, ~70,000 rows (140 pages), also ROE_AVG and BASIC_EPS (added to the weekly fetch too). Its TOTAL_MARKET_CAP, PE_TTM and PB_TTM are today's values on every row, not history, so the history table leaves them out. Monthly prices as for US (0700.HK, ^HSI), plus HKDCNY=X, since book values are in CNY.
  - Its amounts are all in CNY, converted at each period-end rate (HSBC and AIA at 7.0288 CNY per USD for FY2025), and no field names the reporting currency. About 30% of HK companies report in HKD or USD; with the 2026 RMB move, reading their amounts as CNY at today's rate would overstate profit and book by 2-6%. So each row goes back to the reporting currency (Yahoo's, below) at that period end's rate (Yahoo '<CUR>CNY=X' close, ~0.5% from Eastmoney's rates), the TTM is summed there, and converted to HKD at today's rate.
  - Not Yahoo fundamentals-timeseries: its HK trailing series stops at December 2025 for 563 of 1,154 candidates (half-year interims are missing), so the TTM would be six months stale.
  - Consensus EPS and the reporting currency: Yahoo quoteSummary earningsTrend + earnings (this and next fiscal year, last year's actual, analyst count, estimate currency; financialCurrency), one call per stock, weekly (~8 min for 1,200); it needs Yahoo's A3 cookie (from fc.yahoo.com) and the crumb for it. Eastmoney's RPT_WEB_RESPREDICT has no HK rows. 384 of the 1,200 candidates have 3+ analysts (2026-10-17).
  - Price history and dividends: the Yahoo chart API (symbol 0700.HK), as for US; trading calendar ^HSI (stored as HSI). ~9 min for the first 385 days of 1,200 stocks.
  - 10-year yield: hkgb.gov.hk daily closing reference pricings workbook (HKD_DailyClosingReferencePricings_IBPandGSBP.xls, benchmark 10-year), read with xlrd. The HKMA API (api.hkma.gov.hk, IBP/GSBP) stops at June 2026 (monthly bulletin) and answered 405 after ~7 quick calls.
  - Issuer ids for the dedupe: ORG_CODE from the HK profiles above, the CN quotes (RPT_VALUEANALYSIS_DET) and Eastmoney RPT_USF10_INFO_ORGPROFILE (every US ticker, weekly).
  - Headlines: HKEXnews titleSearchServlet.do with the stockId from activestock_sehk_c.json.
  - FX: Yahoo "<CUR>=X" for HKD and the reporting and estimate currencies (CNY, USD, SGD, JPY, EUR...), and ~900 days of daily "<CUR>CNY=X" closes for the period-end rates.
- FX, only needed when a company reports in a different currency from the one it trades in: ECB rates via api.frankfurter.dev.
- Legacy references (read only), all under ~/Developer/EquitySignalsClawbot-legacy/:
  - Sources/EquitySignalsClawbotCore/PublicUniverse.swift (around line 1310, the Eastmoney list call)
  - Sources/EquitySignalsClawbotCore/MacroPanel.swift (rate sources)
  - Sources/EquitySignalsClawbotCore/EastmoneyHKFinancialStatements.swift
  - script/a_stock_snapshot_sidecar.py (Tencent/Sina A-share calls)
