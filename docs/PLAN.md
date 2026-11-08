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
  Your OK came 2026-11-01 (stage 4 switches it on).
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
- Stage 3, redone 2026-11-01 (the first version, commit 930a02b, picked only from each index fund's index and sized by
  index weight; you rejected that on 2026-10-31: "Stages", item 3). Kept from it: revisions in every momentum family,
  forward E/P, all families ranked within sectors, the review's same-sector replacement, holdings judged within their
  sector. New: a growth family (four families, equal weights), EBIT/EV and dividend yield in value, 8-year
  profitability, margin stability and low volatility in quality (signals.py, score.py; history.YEARS for the annual
  reports, fetch/yahoo.py for EBIT, debt, cash, minorities and accruals in all three markets); the buys from the whole
  scored market, each sector's places by its free-float share (CN via the CSI 300's float factors, US total value, HK
  HK-listed value), its best scores, equal amounts, leaving out Quantitative Value's distress and accruals screen, HK's
  small caps and partnerships (lists.py). Removed: the index-only parent, index-weight sizing and UCITS caps, SPY's
  weight file, the index share on cards and in the text, `track`'s weighting. 102 tests pass. The 2026-11-01 build
  (reports/2026-11-01; 75 min with Sunday's weekly refreshes and the first Yahoo fetch of CN and HK; ~3 min from the
  day's data):
  - coverage of the scored stocks: EBIT/EV CN 90%, US 86%, HK 86%; 8-year profitability 96-100%; margin stability CN
    90%, US 57% (a quarter of US filers tag no gross profit; financials have none), HK 81%; 5-year profit growth
    87-98%; forward E/P and revisions as before (revisions CN 30%, US 93%, HK 70%);
  - the screen takes 68 of 778 CN stocks, 64 of 794 US and 29 of 388 HK, among them the US #10 and #13 scores,
    Exelixis and NVIDIA (its working capital grew by 6.3% of its assets, net of depreciation, in its last fiscal
    year), and HK's #14, 六福集团; HK's small-cap band leaves out another ~150 HK names, partnerships 4 US names;
  - places: CN 电子 4, 通信 and 银行 2 each, 12 sectors 1; US technology 8 (Micron, TSMC, Sandisk, Alphabet, Western
    Digital, ASML, Dell, Microsoft), consumer discretionary 3, industrials, finance and health care 2 each; HK 金融 6
    (中国太平, 新华保险, 建设银行, 工商银行, 广发证券, 中国太保), 非日常生活消费品 and 通讯服务 3 each. Of each
    market's 10 largest by free float the lists hold CN 2 (中际旭创, 药明康德), US 3 (Microsoft, Alphabet, TSMC), HK 4
    (建设银行, 中国海洋石油, 工商银行, 网易);
  - your spot checks (examples, not targets): Micron is the US #7 score and a buy (value A on next year's P/E of 4.3,
    growth and momentum A); AMD ranks 183rd (value E: EV/EBIT 106, P/S 20; growth and momentum A) and Eli Lilly 139th
    (value E, growth A; its accruals put it in the screen), neither bought nor avoided; GM ranks 556th (quality and
    growth E: EV/EBIT ~33 with GM Financial's debt against a P/E of ~7) and Stellantis 782nd of 794 (a loss, value C,
    momentum E; screened as likely distressed), neither bought; NVIDIA is the technology #2 score but screened;
  - history (docs/BACKTEST.md section 23, without analyst data, EBIT/EV or the screen): 20 names over the fund a year
    CN +3.8% (65% of windows), US +1.9% (53%), HK +5.5% (68%) (with 2026-11-02's fixes); largest falls CN −35%
    (fund −37%), US −23% (−24%), HK −41% (−47%); worst 12 months 6-8 points worse than the funds'. US quality ran against its published direction
    there (−9.8 points a year, low volatility −14.5): no bug found; survivors only, in a high-volatility decade
    (plausible, untested); the family stays and the 预期 line says so.
  The fresh-context stage review confirmed the list construction, no index-only selection or index-weight sizing left,
  the point-in-time long-run components, no name rule, no choice made on the history, and every status figure. Its
  findings and the answers: (1) the distress inputs weren't winsorized as CHS's are, so market-to-book exploded on
  negative books from buybacks (Booking, PCCW) and the most negative books left the screen: fixed (winsorized at the
  5th/95th percentile, a negative book counted as the highest market-to-book; 12 US names left the screen, mostly
  buyback companies with negative books such as Booking, Hilton, AutoZone and Lowe's; PCCW came back into HK's list); (2) the accruals change after Alphabet was screened out: the reviewer judged
  it a definition fix applied to every stock, but this plan wrongly said it was Quantitative Value's definition (QV
  uses the cash-flow form): corrected, with the reason ("Lists"); the cards' cash backing keeps the cash-flow form, as
  answered there; (3) US 8-year profitability mixed ROE into the ROA average where assets were missing: fixed (ROA
  only); (4) HK bought 俊知集团, HK$3.4bn and +573% in a year, against "no small caps": fixed (HK's small-cap band
  can't be bought); (5) the US #1 was Western Midstream, a partnership a non-US holder can't hold cleanly: fixed
  (partnerships can't be bought; ONEOK takes the place); stale plan lines, the 预期 line's "少 0.0%", the unused SPY
  sample: fixed. Answered, not changed: three memory makers (Micron, Sandisk, Western Digital) in the US list's
  technology places, as each sector's best scores (no industry cap is in the borrowed methods); Kenvue is a buy while
  Kimberly-Clark's part-stock purchase of it is pending, which the review's fixed-price takeover rule doesn't catch
  (a review rule, outside this stage); HK's #1, 中国太平, rests on a trailing P/E of 1.8 after its 2025 profit tripled
  on investment gains, from Eastmoney (its own P/E agrees); its report PDF is still unreadable to the deep dive
  (stage 2's follow-up); Yahoo puts Visa's accruals at 14% of assets while its profit equals its cash flow, a source
  quirk that changes no buy.
- Stage 4 (an easy report, the company line, a summary that fits, switching on): built 2026-11-02. The PDF leads with
  今天要做什么 on one page (holdings to sell or re-check, the review's removals, the 20 buys, the changes, avoid names,
  预期 in one sentence, a five-line guide); market pages have one card per buy with the business line, 为什么买 and
  风险 / 短板; holdings to keep are one table; the method, evidence and review rules are on the back pages (21 pages on
  2026-11-02, 24 before). Company lines for all 200 names (fetch/profiles.py; DeepSeek lines for 66 US and 20 long
  CN/HK texts, notes.lines). The summary is a message with the actions first: 3,244 bytes on 2026-11-02, every case
  of the test data under 3,700 (tests/test_report.py::test_summary_fits). The keyword path (report.fresh: review +
  build, nothing sent) took 11.4 s on 2026-11-01 with some reviews redone. 104 tests pass; app Python 5,654 lines.
  The fresh-context stage review confirmed the score, the lists and the review rules unchanged (two list changes
  that day came from data: 1,911 new broker estimates moved 招商证券 above 广发证券; HK's 长飞光纤光缆 and 联想集团 tie at
  0.744186 and row order picked one) and rule 2 kept. Its findings, fixed: past lists' names shown as your holdings
  without saying so; 风险 printed for a mere weakest component (now 短板); the 50-character cut misled on 10 of 25 long
  CN/HK business lines (now a DeepSeek line from the whole text); vague US lines from one sentence (now three);
  avoid cards repeating the debt figure; the AI note denying a deep dive's finding it hadn't seen (CF) or advising
  hold on a 复核 name (new reviews); 预期 implying the full method ran in the history (now 简化版); the summary could cut
  all of HK on a day of many sells (sells become counts last). Answered: review_kind read from the review line's
  prefix is kept (one place, review.line's own words); exact score ties and Skydance's 退市 flag (an 8-K title that
  may concern a retired share class) are outside this stage (follow-ups).
- Exact score ties (2026-11-02, a fault found in stage 4's review): they went to whichever row came first, or to a
  float's last bit, so two builds from the same data could buy different names (HK 长飞光纤光缆 and 联想集团 at 0.744186).
  Now the larger free-float value, then the lower code, scores compared at 12 decimals ("Lists"; score.ranked). It
  changes CN's 国防军工 buy to 中国船舶 (from 中航光电) and, on 11-02, HK's 日常消费品 buy to 农夫山泉 (from 万洲国际); the
  history run: CN +4.3% (63%), US +1.9% (53%), HK +5.5% (68%) (BACKTEST.md section 23). Its fresh-context review
  found the float's-last-bit ties the first version missed (fixed) and the docs' "no buy changes" (corrected). 105
  tests.
- Three fixes and a check, 2026-11-02 (your words: "I have no holdings. Every list should be treated as new."):
  - the holdings check counted the test builds' lists as recommendations (90 names: CN 31, US 32, HK 27). First
    removed when you said you hold nothing; then, on your correction ("neutral 'hold' advice ... doesn't mean you need
    to know the investor's actual portfolio"), restored as a neutral hold rating (持有建议) of the lists actually sent
    to you ("Holding rule"). Its fresh-context review found the first version's 12-month rule broken (dated from the
    first listing inside a moving 12-month window, a sell showed for one day at most and names dropped off unjudged),
    picks.csv losing the 11:33 list you were sent, and a table that would grow to 45-80 names: all fixed. Its
    re-check found a 继续持有 at 12 months promising a year it wouldn't follow, the table losing a 复核's news concern,
    replies from an older list dated today, a sent text not logged when the PDF failed, and stale wording: fixed.
    Answered, unchanged: rated names stay reviewed before avoid names (a hard flag turns a rating into 卖出; on an
    avoid name it only annotates); a `run` finishing in the second between a reply's build and its log. On
    2026-11-02 it is empty (nothing was sent before); the PDF is 15 pages;
  - CN free-float factors at the CSI file's date ("Lists"): with 9-30 weights against today's values, a stock's
    factor moved with its October price (新易盛 −50%, factor 5.1×; now 2.7× at most). CN's places: 电子 4 → 3 and
    通信 2 → 1 (生益科技 and 中天科技 out), 非银金融 1 → 2 and 家用电器 0 → 1 (广发证券 and 海信视像 in); history
    +4.3% (63%) → +3.8% (65%) a year over the fund (BACKTEST.md section 23);
  - an 8-K Item 3.01 that only moves the listing to another exchange is routine ("Results review"): Skydance's hard
    退市 flag on the US avoid list was its move from Nasdaq to the NYSE. The fresh-context review found the first
    deficiency check too narrow (a move offered as a cure would have passed) and a failed read dropping all of a
    stock's filings: both fixed, with its test cases; it confirmed the CN factor exactly (members at 100% float
    2.67-2.69×) and the place changes;
  - the first unattended day: the 06:30 build ran 21 min, exit 0, no errors; your keyword at 11:33 was answered in
    4 s, the text then the PDF (logs/2026-11-02.log); the listener had run 399 times without a failure.
- Stage 5 (three ratings, Buy 20 / Hold 10 / Sell 10, no portfolio check): done 2026-11-02. Your words: the project
  was meant to split each market into stocks expected to go up, be stable and go down, as a sell-side analyst rates
  them, with no regard to anyone's holdings. Hold is the 10 steadiest prices among the 400 largest names in the middle
  fifth of the score, at most 2 a sector ("Lists": the brokers' relative ratings, the persistence of volatility); Sell
  is the avoid list renamed (the same rule); Buy is unchanged. Removed: the holdings check, the neutral hold rating,
  the holding rule, data/holdings.csv and `hold`, the review's holding role, holdings among the deep dives. The review
  runs Buy, then Hold, then Sell, then the benches (small point (a)); a hard red flag takes a name off Hold as off Buy.
  data/sent.csv logs the buys report.build returned for the text sent (small point (b); buys.csv is gone). Every card
  has the Goal's fields, the re-check date 12 months on. The history (BACKTEST.md section 24): Hold over the fund CN
  −1.0% (ahead in 51% of windows), US −6.2% (37%), HK −2.2% (43%), with 0.7-0.8 times the fund's volatility and
  smaller falls (CN −17% against −37%); Sell trailed the fund in 57%, 57% and 63% of windows but on average only in HK
  (CN +1.4%, US +1.5%, HK −0.5%); the history leaves out delisted companies, which flatters Sell most; it decided
  nothing. The 2026-11-02 evening build (`run` 688 s, then `review`: 170 names, 126 reviewed in 13 s, no hard flag, 0
  quotes rejected): Hold CN 中国核电…招商公路, US Royal Bank of Canada…Ventas, HK 交通银行…福耀玻璃 ("Lists"); the PDF
  17 pages, the summary 3,484 bytes with every name. data/picks.csv's old v3 rows relabelled (Storage). 108 tests
  pass; app Python 5,693 lines (5,769 before).
  The fresh-context stage review confirmed the Buy, bench and Sell lists identical to the old code's on the same
  snapshots, the Hold rule as written, no holdings path left, the review order, the Hold removal, the sent log, rule 2,
  and that the Hold rule was fixed in code before the history ran. Its findings and the answers:
  - Hold was worded 预计和大盘差不多、股价较稳（涨跌通常都比大盘小）, which neither the definition nor the history bears
    out for single names: fixed. The report now says 评分居中、不偏涨也不偏跌、股价较稳, that the 10 together moved
    less and fell less than the fund but lagged strong markets, that a single name can still move a lot, and that
    daily volatility misses a steady slide ("Lists"). The definition stays: its parts rest on published evidence, and a
    rule to drop recent fallers would be fitted to two names (中国旺旺, 中国飞鹤);
  - Sell's average beat Hold's in all three markets, and page 1 showed Sell's 平均多赚 without the survivorship caveat:
    the caveat is now on page 1 and in the summary's last line; nothing is changed for the numbers (rules 3 and 12);
  - Sell cards hid a clean or pending review (8 of 30): fixed (it ends the 为什么卖出 line);
  - Hold didn't leave out the buys' bench, so a name could become both after a review removal: fixed (no list
    changed on 11-02; the history's HK Hold −2.3% → −2.2%);
  - wrong figures in the docs (the scored counts 796 and 390; section 23's HK 10 and 5 best, moved by the frames'
    rebuild with that day's float factors; section 24's "written before this run"): fixed;
  - answered, unchanged: HK's "400 largest" is its whole ~390-name field, so HK Sell can hold HK$2-4bn names (the avoid
    rule as it was; the stage changes Sell only for evidence); the scoreboard pools removed Buy and Hold names in one
    bucket (the comparison is removed against replacement either way); the old-CSV mapping it questioned was removed,
    as every market now has stage-5 lists; stage-reviewer.md's checklist now names the three ratings.
  - Follow-ups, not this stage: US names came from Nasdaq's screener, which calls Bank of Nova Scotia's common share
    "Bank Nova Scotia Halifax Pfd 3", and the AI note repeated that it is a preferred share (fixed the same day: "US
    company names" below); Moderna's 194% volatility rests on one +177% day in Yahoo's prices (2026-08-19), a real
    move (your confirmation, 2026-11-02): nothing to change.
- US company names (2026-11-02, a follow-up of stage 5's review): from Yahoo's quote longName instead of the
  Nasdaq screener's names (Data sources, US); BNS's card now reads The Bank of Nova Scotia, its new note no longer
  calls it a preferred share, and no card says Pfd. The names change no list (the same snapshot gives the same lists
  with either set of names; the four partnerships still read as such). All 170 cached reviews were redone once (their
  entries had no name), 18 s. `run --market us` then `review`: the PDF 17 pages, the summary 3,490 bytes. 109 tests.
- Switched on with your OK of 2026-11-01 (rule 9), on 2026-11-02 from this checkout: the 06:30 `run` job
  (com.stockreport.daily; ~/Library/LaunchAgents now holds the repo's plist, the old fetch-only one replaced); one
  `send --test` at 04:39 (the test text, 3,617 bytes, then the test PDF, 股票报告_测试_20261102.pdf, after your
  message to the bot opened its reply window); the keyword listener (com.stockreport.listen). `send` had never run
  in this build: the subcommand's parser shadowed the send function (fixed). The keyword reply is report.fresh
  (review within 20 s, build) then the text, then the PDF: two messages (listener.reply), 11.4 s before sending on
  2026-11-01; WeChat's two sends took ~3 s in past replies.
- One AI step, and nothing needs Claude Code (2026-11-07; your words: "make sure every step on this project can run
  without AI assistance except only one step that using deepseek to screen and comments on the final report", then
  "i can close claude code completely and still run the project, just putting the AI part rely on deepseek token and
  ensure the quality ... i dont want to reduce project quality"). Checked: launchd runs the 06:30 `run` and the
  listener with the project's own Python and no step calls Claude. DeepSeek was called in three places (the review,
  a company-line pass, the deep dives' questionnaire); now only in the review, one call per name that screens and
  comments ("Results review"). The deep dives' hard flags are kept as passages code cuts from the latest periodic
  report (passages.py), read in that call for every Buy and Hold name and bench (3 reports a market a day before);
  their AI-read profit check and non-recurring share went (rule 2: the AI reads no number; the check never found a
  fault); the company line comes back in the same call (notes.line). Filled on 2026-11-07: CN 51 reports (6 with a
  passage, once every CN report's board pledge 不存在任何虚假记载 was left out of the keywords), US 43 (29), HK 46 (25);
  median 0 / 2,026 / 1,054 characters. The review that afternoon met a DeepSeek outage (120 of 165 calls failed with
  HTTP 500s or timeouts, a two-word prompt too; no failure earlier this month): the report went out marked
  审核暂不可用 for those names, as built. The 45 done: no hard flag; soft concerns from passages (ARCC's derivative
  suits in its 10-Q; 华安证券's lawsuit it won, read as litigation: a soft note's noise); 7 new US lines, all kept.
  A name whose sources all failed has no review call, so no new line that day (its card shows the source text).
  README says what runs when and how to refresh the 预期 numbers by hand. App Python 5,459 lines (5,707); 107 tests.
  Not done, at your word ("deepseek is crashed ... wrap it up now"): the review's cold timing with passages on the
  keyword path (DeepSeek still down), and the fresh-context review (stopped before it reported).
- Stage 6 (correct the score's inputs): done 2026-11-07. You gave me an outside review (Codex's, of the 2026-11-02
  checkout) to judge; each claim was checked against the current code and data before anything changed.
  - Taken, as "The score" says: CN annual 扣非 from the stated amount (the rebuild was over 10% off in 22% of the
    years); the long-run figures on total assets in every market, the 8-year ROA and the 5-year profit growth over
    assets (a return on the book broke on small and negative books: HK losses over pre-listing negative books read as
    high returns, 京东物流's 8-year figure 47.9%, now −4.2%, 快手's 45.7%, now −23.4%, Wynn Macau's 66%, now −1.0%;
    US growth over a book shrunk by buybacks reached 296% for Seagate and 12,740% for Ubiquiti; CN's past books took
    EPS restated for later bonus shares); HK annual figures in the reporting currency (the yuan's 7% from 2020 to 2025
    was in every HKD and USD reporter's growth); forward E/P on the next 12 months (Micron's "next year" was the fiscal
    year to August 2028); the card names the fiscal year revised. Data fetched once: CN fiscal years 2009-2025 with
    total assets, the HK history with total assets (merged, so companies Eastmoney no longer lists keep their rows),
    the CNY rates for 12 years.
  - Checked and not taken: that HK past books used the wrong share count (Eastmoney's HK book per share is the year's
    equity over today's count, so the book was right; my own first fix took that year's count, caught when 邮储银行's
    8-year ROE went from 10% to 15%, and reverted); that a missing debt line is a missing value (every scored name
    without one is debt-free; only a missing cash line now leaves EBIT/EV out: HK 02583); that a fiscal year's roll
    reads as a revision (both dates are already the same year).
  - Already gone: the replacement and holding-policy faults (no holdings since stage 5), one-off profits through the
    deep dives (removed 11-07; per-company amounts would break rules 2 and 3). For stages 7 and 8 ("Stages"): the
    history's dividend yield, its risk figure, a neutral basket, the review line's wording, the money one lot of each
    buy takes; the forward scorecard. Not taken: earnings normalized over a cycle and places by industry (no recipe
    borrowed here does either; the US list's three memory and storage makers on 11-07, Micron, Sandisk and Western
    Digital, are each the sector's best scores, with the risk that brings), a parent-and-subsidiary screen (no free
    ownership data; HK holds both PCCW and its subsidiary HKT).
  - What it changes, the same 2026-11-07 snapshots scored by the code before and after: buys CN 6 (广发证券, 生益科技,
    新奥股份, 中远海控, 东鹏饮料, 艾力斯 → 燕京啤酒, 沪电股份, 上港集团, 川投能源, 华安证券, 药明康德; ROA doesn't reward
    leverage: 东鹏饮料's 8-year ROE 37% is an ROA of 14%), US 4 (Equinor, Expedia, NetApp, Seagate → HF Sinclair,
    Alphabet, UMC, Yum China; Expedia's and Seagate's growth had stood on small books), HK 4 (香港交易所, 永利澳门, 农业银行,
    先声药业 → 晶苑国际, 药明康德, 国泰海通, 华泰证券); Hold CN 3, US 3, HK 4; Sell CN 3, US 1, HK 0. No name lost the 8-year
    figure; the 5-year growth now covers CN 792 of 794 names (777), US 733 of 789 (701), HK 369 of 406 (353).
  - The history (BACKTEST.md sections 23-24): the 20 names over the fund CN +3.8% (65%) → +2.2% (53%), US +1.9% (53%) →
    +1.5% (54%), HK +5.5% (68%) → +6.6% (69%); the family check within 1.8 points (HK quality −2.9% → −1.1%). It
    decides nothing (rules 3 and 12): a first version (ROE with a −50% floor) gave CN +4.4% and was replaced for its
    fault. `run` (06:30's lists rebuilt; 384 s, no fetch failures): CN 794, US 789, HK 406 scored; the PDF and a
    3,366-byte summary; nothing sent. 112 tests; app Python 5,513 lines (5,460).
  - The fresh-context stage review confirmed the 扣非 join point-in-time (both notice dates agree in every fiscal year)
    and the quarterly TTM and SUE unchanged by the added years, the HK conversion and its book-per-share reading
    (Tencent 2017, HSBC 2020), the 12-month weights for December, August and March year ends and for a year ended but
    not reported, the US untouched by the floor, no rule for a named stock, and BACKTEST's figures. Its findings: (1)
    the −50% floor fell mostly on profitable HK pre-listing years (古茗, 布鲁可), while CN left such years out:
    replaced by ROA as above; (2) four figures in this entry didn't match the outputs (HK names losing the 8-year
    figure, the floor's year counts, a ratio range, 艾力斯's cause): rewritten with the ROA version; (3) CN's analyst
    count is the rating institutions, not a count per year: worded so ("Forward E/P"). Answered, unchanged: 中国太平's
    P/E of 1.9 on 2025's investment gains and Tesla's next-12-months P/E on Nasdaq's lower FY2027 estimate (the
    consensus as the sources give it); 五粮液 a Hold while its 2027 consensus fell 31% in 91 days (the revision is in
    its score, not on a Hold card; after the ROA change it is no longer a Hold).
  - Found on the way, not this stage's: the 06:30 build met Yahoo HTTP 403s, so its US closes stayed a day old while
    Nasdaq's listing price was fresh, and "listing price vs Yahoo closes differ >1%" dropped 469 of 800 names; the US
    lists of that morning's report came from the other 329 (rule 4 wants a market that can't be built to show its
    last good lists; nothing was sent: data/sent.csv is unchanged since 11-03). Fixed the same day
    (__main__.build_market): a market whose daily prices couldn't be updated isn't built, so its newest earlier lists
    stand, with their date (the report's 今日未能更新，沿用 … 的名单); tests/test_build.py.
- Stage 7 (what the report says to expect): done 2026-11-08. No list rule changed; the history (BACKTEST.md sections
  23-25) and the report's words did.
  - The history's dividend yield is missing, not 0 (backtest/panel.py; qvm.prepare for the cached snapshots): a 0 for
    every stock made each sector's yield percentile one value, so section 23's dividend spreads (CN −5.3%, HK +6.0%)
    only sorted sectors by size; deleted. It changed 5% of CN's month-lists, 9% of the US's and 2% of HK's, by one name
    (two in one US and one HK month); every mean moved 0.1 points or less (20 names over the fund CN +2.2% (54%), US
    +1.5% (54%), HK +6.6% (69%)), a few tail figures up to 1.1 (CN Hold's 10th percentile −25.3% → −26.4%).
  - The family check cuts its fifths within each peer group and month, the groups weighted by their share of the
    month's stocks: at most 0.7 points from the market-wide fifths (HK growth +6.6% → +5.9%, CN the score +1.6% →
    +2.0%); US quality −9.6%, the score −4.1%.
  - Each held year's own largest fall at month-end marks against the fund's over the same months, in the Buy, Hold and
    Sell 预期 lines: the 20 names' median year CN −12% (fund −10%), US −9% (−8%), HK −11% (−15%), the worst −30% (−28%),
    −26% (−19%), −33% (−23%). The overlapping portfolio's fall (−36%, −23%, −40%) moved to the back pages.
  - The neutral basket (the same places, every name of the sector that can be bought, equal amounts): over the fund CN
    +3.2%, US +3.0%, HK −0.1%; the 20 names over it CN −1.0% (ahead in 36% of windows), US −1.5% (43%), HK +6.8% (75%).
    In this history CN's and the US's lead came from the equal amounts and the places and picking cost a little; HK's
    is the picks. The basket's hundreds of mid-sized names are where "today's listings only" flatters most. It decides
    nothing (rules 3 and 12); the back pages say it per market.
  - A clean review's line says what it read: 近期公告、新闻和定期报告未见重大风险 (46 cards on 11-07), or 近期公告和新闻…
    where the latest report wasn't cut (27: the Sell names, and Buy or Hold names whose report waits for the day's
    quota, such as Alphabet's).
  - One line a market on the money one lot of every buy takes at equal amounts: CN 89.6 万元 (中际旭创), US 2.85 万美元
    (ASML, US$1,425 a share), HK 86.0 万港元 (长飞光纤光缆) on the lists the report shows (the stage's brief had
    HK$834k and US$12.6k).
  - Page 1's spacing tightened: on 11-07 its guide spilled two lines onto a second page (a removal and 7 gone names in
    two markets). Re-rendered after `review` (147 names in 17 s, 0 failed): 19 pages, the summary 3,454 bytes; nothing
    sent. 113 tests; app Python 5,542 lines (5,518).
  - The fresh-context stage review confirmed the basket's places and field the buys' own in every month (weights sum to
    1), each held year's fall on the list's own month-end path before costs with the returns unchanged, the split exact
    (the 20 names over the fund = the basket's lead + the picks', the same windows), the review line true to the sources
    on all 73 clean cards, the lot figures, and no rule chosen on a result or for a name. Its findings, fixed: page 1's
    guide still said the Hold 10 "跌得少", which the held-year falls don't bear out in the US and HK (gone; "Lists");
    "every figure 0.1 points, one name" (a few tail figures moved up to 1.1, two names in two months), BACKTEST's HK
    mean (+12.1%), the done date; a review state without its sources claimed all three (now 审核未见重大风险);
    review.py at 404 lines (400); the final PDF's pages read again. Answered, unchanged: 定期报告 is named where code cut
    no passage (29 of 46: the report was searched for the hard-flag topics and none was found) and where the US "report"
    was a 40-F cover document (RY, TRP: passages.py's limit, a follow-up); the family check's pooled small sectors and
    the groups without a fifth (0.5% of US stocks) are written in qvm.families and BACKTEST.
  - Found on the way and fixed after the stage, at your word ("fix here"): 科达制造 left CN Buy on a hard
    持续经营疑虑或债务违约 flag quoting "关于法院受理子公司破产清算的公告", a subsidiary's liquidation (its 9-month profit
    +66%); going_concern had no subsidiary test, as management has. Now such a quote is a soft concern ("Results
    review"; quotes.SUBSIDIARY since 2026-11-08, tests/test_review.py). Of the cached reviews only 科达制造's changed: reviewed again, it
    is back in CN Buy (浙江鼎力 back on the bench), its card showing the liquidation as 市场可能在担心; the report
    rebuilt (18 pages, the summary 3,366 bytes); nothing sent. review.py 400 lines.
- Stage 8 (a forward scorecard that answers the goal): done 2026-11-08. track.py rewritten; the price fetch keeps the
  funds and the cohorts' names; one line on each market page.
  - The record is data/picks.csv, not data/sent.csv: picks.csv holds every report's three ratings with their prices
    (each day's last build, so the review's removals when a review ran), sent.csv only the buys and only on the days
    you asked: with it a month you didn't ask would have no cohort, and Hold and Sell never one.
  - Cohorts: each market's first report of each month, recorded the day after (the day's last build may still change
    its lists) in data/cohorts.csv.gz: the Buy, Hold and Sell names, equal amounts within each; the fund; the 对照组合
    from the day's snapshot (lists.buyable and lists.slots, as backtest/qvm.neutral: each sector's places spread equally
    over all its names that can be bought). Held 12 months from the first close after the report's day (a Saturday
    report starts at Monday's close, a Monday report at Tuesday's: the cohort is the day's last build, which an evening
    review may change after that day's close).
  - The funds with dividends: SPY and 2800.HK from Yahoo's adjusted closes like every US and HK price; 510300 from the
    通达信 packages (kept beside the CSI 300), whose prev-close the exchange lowers by each distribution: on 2026-01-19,
    its ex-date, the prev-close was 4.736 against the 4.859 close before (a 0.123 distribution), so the day's return
    is +0.04% (close 4.738), as on Yahoo's adjusted close.
  - Month-end marks in data/cohort_marks.csv: each group's value at each month's last close after the start and at the
    12-month close, written once a later close is in, never recomputed, with the cohort's first close, so the price
    files' 385-day window can't move or erase them; both files are written whole and swapped in. A name with no price
    that day, or one with neither a trade nor a price change (a suspended name shows its last close with volume 0;
    volume alone won't do, as Yahoo gives every HK row volume 0 on half days such as 12-24 and 12-31) is left out of its
    group's value and counted as unresolved, with its growth to its last close kept beside the mark; it counts again
    once it trades, its return running from its last close. A mark with an unresolved name waits for 5 later closes, so
    a name a failed Yahoo fetch missed is filled in first (each fetch reaches 10 days back). A name that delists stays
    unresolved, so it is out of every later mark and the 12-month value, as the stage asked ("unresolved rather than
    flat"); the line says how many, and its last-close growth is kept should a later stage value it. tracked() keeps
    the funds and the last 13 months' cohort names priced.
  - The first cohort is 2026-11-07's lists, not 11-01's: the first report of November built with the score as it
    stands (stage 6's inputs, rebuilt that evening); 11-01 had no Hold list, and 11-01..11-05 came before stage 6's
    corrections. Recorded for all three markets: Buy 20, Hold 10, Sell 10; the 对照组合 CN 617 names, US 652, HK 199,
    its places the buys' in every sector. Its first close is Monday 11-09's; the first marks come with December's first
    close. (11-08's lists, from Sunday's weekly data at the same price date, differ in the US by 5 buys, 5 Hold and 3
    Sell names; by the rule November's cohort is 11-07's.) Its CN Buy holds 科达制造: 11-07's report was re-rendered on
    11-08 at 07:01 with the subsidiary going-concern fix, which rewrote picks.csv's 11-07 rows (the evening review had
    removed it on the false flag, 浙江鼎力 in its place). Kept, as the report of that day now reads; since then a report
    re-rendered for a past day no longer rewrites that day's rows (report.build logs picks only for today).
  - `track` prints each cohort's marks against the fund and the 对照组合 and its value at the newest close (shown, not
    kept); `run` records new cohorts and marks before the report. The report's market page carries one 实盘记录 line
    under the 预期 box, in every report: its figures change once a month, and one report a month would miss the days
    you ask. Before the first mark it says when the numbers come; after, Buy against the fund and the 对照组合, Hold and
    Sell against the fund (Sell trailing is the rating being right), the average over cohorts and how many led, and the
    distinct names left out; a figure missing that month is left out of the line. The WeChat summary is unchanged.
  - Storage, at your word ("have a mechanism to clean up unnecessary cache and data"): snapshots and reports are kept
    30 days, not 400 and 90 ("Storage and cleanup": ~1.8 GB at steady state before, ~1.1 GB now); the backtest's one
    snapshot copied out of cleanup's way (panel.today_snapshot read data/snapshots/2026-10-18, which retention would
    have deleted). Not deleted without your OK: the old engines' outputs in data/backtest (255 MB) and data/events and
    data/deepdive (0.5 MB), which nothing reads.
  - Found on the way: re-rendering a report with report.build alone drops the day's review and rewrites picks.csv's
    rows for the day; 11-08's was restored with `review` (cached, 1 s; the summary byte-identical to the morning's).
  - Tests (tests/test_track.py): the first close, the marks due, the month-firsts, month-end values with a dividend, an
    unresolved name and its return, a half day's volume 0, the wait before a mark with an unresolved name, the
    对照组合's weights with a partnership, and marks kept when the price file rolls on; the report line without a missing
    figure; the 通达信 sample keeps 510300; the dry run no longer reads the real scorecard files. 119 tests; app Python
    5,755 lines (5,542).
  - The fresh-context stage review confirmed the record and the month-first rule, START chosen before any result, the
    first close for morning and evening builds and across holidays, the marks once a later close is in and never
    redone, dividends in all three funds (SPY's past year +10.9% against the S&P 500's +9.8%, 2800 −4.5% against the
    Hang Seng's −7.6%), suspended names chained from their last close, the 对照组合 rebuilt from the snapshot to the same
    weights (summing to 1, its places the buys' in every sector, every buy inside it), and nothing reading snapshots or
    reports older than 30 days. Its findings, fixed: (1) HK half days give volume 0 to every row, so 12-31's HK mark
    would have left out Buy, Hold, Sell and the fund for good and broken the line through January (a name now counts
    as traded with a trade or a price change); (2) the line left "分别、。" for a missing figure, counted cohorts without
    one and the same name in two cohorts (now left out, counted over the cohorts with both, distinct names); (4) a mark
    could be taken from a partial Yahoo fetch (the 5-close wait); (5) re-rendering a past day rewrote its record (the
    guard above; 11-07's case kept and written); (6) an evening review after the report day's close could change a
    cohort that started at that close (the first close is now the day after); (7) the two kept files written in place
    (swapped in whole); (8) the 510300 figure (+2.6% was the distribution), the report folders (16 days), the market
    order in `track`, a "done when" for this stage. Answered: (3) delisted names stay unresolved, as the stage asked,
    with their last-close growth kept (above). Outside this stage, as follow-ups: FMX left US Buy on 11-08 on a hard
    flag quoting an adverse opinion that is on its internal control, not on its accounts (the same overreach as
    科达制造's); GE Aerospace's Sell rank rests on the conglomerate's 8-year ROA and 5-year growth from before the
    spin-off.
- After stage 8, at your word ("Do this task here"): FMX's hard flag. It left US Buy on 11-08 (MNST in its place) on
  "expressed an adverse opinion thereon" from its 20-F, the auditor's reference to its report on internal control; the
  opinion on its accounts was clean. An opinion on internal control is now a soft concern ("Results review";
  quotes.about, which also holds the subsidiary test, so review.py stays at 399 lines). Of the cached reviews only
  FMX's had a hard audit or going-concern flag; only it was reviewed again (one DeepSeek call): back in US Buy, its card
  showing 市场可能在担心：内部控制被出具非标准意见, MNST back on the bench; 11-08's report re-rendered with `review`;
  nothing sent. No fresh-context review for a rule this size, at your word on tokens; the tests cover FMX's own
  passage, an HK qualified opinion and CN opinions on the accounts and on internal control. 120 tests; app Python 5,788
  lines.

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
  market. Stage 3's redo added the ingredients of the other recipes named at the start (Seeking Alpha's growth grade,
  Alpha Architect's Quantitative Value, Greenblatt's Magic Formula, the dividend-low-volatility indexes) and replaced
  NAPS's 2 names per sector with places by each sector's share of the market ("Lists").

## Goal
- On the WeChat keyword (股票报告 / 股票简报 / stock report / stock brief), within 30 s, two messages (a text summary and
  a PDF), in Chinese. Per market (CN → US → HK), three ratings, each a list of the top candidates, rated as a
  sell-side analyst rates stocks, without anyone's portfolio (stage 5, your words of 2026-11-02):
  - **买入 (Buy, expected to go up, beating the market):** 20 names from the whole liquid market, equal amounts, the
    sectors in proportion to the market's: the buy portfolio ("Lists");
  - **持有 (Hold, expected to be stable):** 10 names;
  - **卖出 (Sell, expected to go down, lagging the market):** 10 names;
  - **预期 (what to expect):** how each rating did in our history and what published research says.
- **Moderate.** The aim is to beat the market's index fund over the year you hold the names, at about the market's level
  of risk. Not a defensive tilt (low volatility, dividends) and not an aggressive one (small caps, a few concentrated
  bets, chasing the hottest stocks). Stage 3's redo uses dividend yield and low volatility as two of the score's 21
  ingredients (each about a twenty-fourth of the score), not as the strategy: the dividend-low-volatility indexes hold
  only those names, while the list still takes each sector's best overall scores, with the sectors in proportion to the
  market's, so it doesn't become a dividend fund.
- **Honest expectations.** Published factor portfolios have beaten their index by a few percent a year on average, have
  lost to it in roughly 4 years out of 10 (AAII's real-money portfolio: beat the index in 55% of rolling years), and
  their edge shrank after publication (McLean-Pontiff: about −58%). No list is a guarantee; the report says so.

## The method

### Universe
- Scored: the 800 largest after the filters (liquidity floors as built; HK has fewer that pass them). Buys: the whole
  scored universe (stage 3's redo; "Lists"), not an index's members, without small caps: the CN and US 800 are large
  and mid caps (about the CSI 300 + 500 and the S&P 500 + 400: down to CNY 20bn and $12bn on 2026-11-01), while HK's
  ~390 reach down to HK$3bn, so HK's buys leave out Hang Seng's SmallCap band ("Lists"). Hold and Sell: the largest 400.
- Out only on facts: figures that fail the cross-checks, ST / *ST, suspended, under 12 months of prices, and (from stage
  2) a hard red flag. Everything else is left to the score, so a troubled company ranks low rather than vanishing.

### The score: four families, equal weights
Each component is a percentile among the stock's peers on the date, point-in-time; a family is the percentile rank among
the peers of the mean of its components' percentiles (a missing component is skipped; a missing family counts as 50);
the score is the mean of the four families. Ranking each family before combining is Stockopedia's way and makes the
weights equal in effect: a plain mean of percentiles spreads much less than one percentile, which let one-component
momentum drive the score (fixed in stage 1 after the stage review).
- **Peers (stage 3):** the stock's sector, financials apart from the rest (their components differ: no S/P, cash
  backing or debt, which made a bank's one or two components outrank everyone's three-component means in stage 1). Why
  within sectors: Seeking Alpha grades every factor against the stock's sector, MSCI's Diversified Multiple-Factor
  indexes score value and quality relative to the sector, and Asness, Porter and Stevens (2000) find industry-relative
  value and momentum predict returns better than the raw figures. A sector with fewer than 10 scored stocks is too
  small for fifths: its stocks are ranked against the whole market of their kind (financials or the rest). Sectors: CN
  申万 level 1, US the Nasdaq sector, HK Eastmoney's first-level industry type.

| Family | CN | HK | US |
|---|---|---|---|
| 价值 Value | E/P on 扣非 TTM, forward E/P, B/P, S/P, EBIT/EV, dividend yield | E/P, forward E/P, B/P, S/P, EBIT/EV, dividend yield | the same |
| 质量 Quality | ROE, cash backing, debt ÷ assets, 8-year ROA, margin stability, low volatility | the same as CN | gross profit ÷ assets, cash backing, liabilities ÷ assets, 8-year ROA, margin stability, low volatility |
| 成长 Growth | revenue growth, profit growth, 5-year profit growth over assets | the same | the same |
| 动量 Momentum | earnings momentum (SUE), revisions | 12-1-month price return, revisions | 12-1-month price return, revisions |

- **Why four families (stage 3's redo).** You named Seeking Alpha's quant grades, Alpha Architect's Quantitative Value,
  Greenblatt's Magic Formula and the dividend-low-volatility indexes at the start, and stage 1 borrowed only
  Stockopedia's three families. Seeking Alpha grades five factors within sectors (value, growth, profitability,
  momentum, EPS revisions) and its ratings beat the market in its live record (a University of Kentucky study, 2024);
  its profitability is our quality and its revisions are in our momentum, as Stockopedia's momentum rank holds them,
  so growth is the family that was missing. Equal weights, as before: Seeking Alpha doesn't publish its weights and
  nothing here is fitted (AGENTS.md rule 3).
- **Value:** a composite of six ratios, so no single ratio decides: Stockopedia's ValueRank is an equal blend of P/B,
  P/E, P/S, P/FCF, EBIT/EV and dividend yield (free cash flow isn't in the free CN and HK tables). E/P is CN's strongest
  value measure (Liu-Stambaugh-Yuan 2019). B/P only where book > 0 (negative book from buybacks is undefined, not cheap
  or dear). S/P not for banks, insurers and brokers.
  - **EBIT/EV** (stage 3's redo): trailing operating profit before interest and tax over market value + debt +
    minorities − cash. Greenblatt's Magic Formula and Gray and Carlisle's Quantitative Value rank on it (they found it
    the best single value measure in US data 1964-2011, as did Loughran and Wellman 2011), and it is in ValueRank
    because it counts the debt E/P ignores: on 2026-11-01 GM's P/E is ~7 but its EV/EBIT ~33 with GM Financial's
    $129bn of debt. From Yahoo's fundamentals timeseries in all three markets (trailing EBIT, the latest total debt,
    cash with short-term investments, minorities, in the reporting currency, turned into the quote currency). Yahoo
    lists no debt or minorities line where there is none, so a missing one counts as 0 (stage 6 checked: on 2026-11-07
    the scored names without a debt line were Arista, Franco-Nevada, Intuitive Surgical, Monster, Nextracker, United
    Therapeutics, 同花顺, 大全能源 and three more A-shares, all debt-free; Apple, Microsoft, Alphabet, NVIDIA and Meta have
    no minorities line); a missing cash line means the balance sheet wasn't read (every company holds cash; HK 02583's
    record had no cash, debt or liabilities) and, like a missing EBIT, leaves EBIT/EV out. Not for financials (their
    debt is their product). Coverage: see Status.
  - **Dividend yield** (stage 3's redo): cash dividends with ex-dates in the last 365 days over the price (0 for a
    non-payer). In ValueRank, and the first sort of 中证红利低波 (50 high-yield, low-volatility A-shares, yield-weighted)
    and 恒生港股通红利低波 (HK, net-yield-weighted): a cash yield is hard to fake, which matters most in CN and HK.
- **Quality:** profitability (Novy-Marx 2013; Asness-Frazzini-Pedersen's quality-minus-junk, which holds in 23 of 24
  countries), cash backing = −(net profit − operating cash flow) ÷ revenue (Sloan 1996), and balance-sheet strength
  (lower debt is better; not for financials, whose leverage is their business). Stage 3's redo adds:
  - **8-year profitability** (Gray and Carlisle's franchise power: 8-year averages of ROA and return on capital): the
    average yearly ROA, the year's profit ÷ its total assets (CN 扣非 profit, US profit to common, HK profit to
    shareholders), of the last 8 fiscal years public by the date, at least 5, each year clipped to −50%..150%. A year
    of high profit doesn't make a franchise; eight do. Stage 6 (history.py, signals.long_run):
    - On assets in every market. Until stage 6 CN and HK took ROE, their tables being thought to have no yearly
      assets; they have them (主要财务指标's TOTAL_ASSETS_PK, the HK main indicators' TOTAL_ASSETS). A return on the
      book breaks where the book is small or negative: from buybacks and payouts (why the US took ROA), or from
      preferred shares booked as liabilities before a listing (common among recent HK listings: 古茗, 快手, 京东物流).
      Eastmoney's ROE divides by the book whatever its sign, so Wynn Macau's 2020-22 losses entered at +470% (clipped
      to 150%), +69% and +54%, and PCCW's 2025 loss at +140%. A first fix counted a year without positive equity as
      −50%; the fresh-context review found it fell mostly on profitable pre-listing years in HK (古茗, 布鲁可) while CN
      left such years out. ROA has a figure for every year with assets, whatever the book.
    - CN takes the 扣非 amount and the total assets each annual report states (主要财务指标, by its notice date; since
      2009), no longer profit × 扣非 EPS ÷ EPS, clipped and set to 1 where EPS wasn't positive: that rebuild was over
      10% off in 22% of the fiscal years and over 50% off in 8% (中国船舶 2022: a CNY 0.17bn loss for the 2.75bn the
      report states; 中际旭创 2023: 2.98bn for 2.12bn). A year without the stated amounts has no figure (rule 5).
    - HK's annual figures are in the company's reporting currency: Eastmoney gives every amount in CNY at its
      period's rate, so the 5-year profit growth below mixed the yuan's moves into a company's growth (an HKD or USD
      reporter's profit grew 7% from the end of 2020 to the end of 2025 on the rate alone: CNY 6.52 → 7.00 a dollar).
      Each year goes back at its period's rate (Yahoo's daily <CUR>CNY=X, kept from October 2014), the same conversion
      the universe's HK figures use; a company without a known reporting currency has none.
  - **Margin stability** (franchise power's second half): the mean gross margin of those years over its standard
    deviation, at least 5 years; not for financials. Gray and Carlisle take the better of margin stability and margin
    growth; growth is in its own family here.
  - **Low volatility** (quality-minus-junk's safety: low beta and low volatility; the dividend-low-volatility indexes'
    second sort): the 1-year volatility of daily returns, lower is better. The low-volatility effect is strongest in CN
    (Blitz, Hanauer and van Vliet 2021: 2000-2018, also among the largest and most liquid A-shares).
- **Growth** (stage 3's redo; Seeking Alpha's growth grade, within sectors):
  - revenue growth and profit growth: the latest report against a year earlier (CN and HK year to date, from 业绩报表
    and the HK main indicators; US trailing 12 months). Revenue surprises are followed by drift (Jegadeesh and Livnat
    2006); one year only, as 5-year past sales growth predicts lower returns (Lakonishok, Shleifer and Vishny 1994);
  - 5-year profit growth over assets: the latest fiscal year's profit minus that of 5 years before, over the total
    assets 5 years before (quality-minus-junk's growth in ROA, one of its growth measures; CN 扣非 profit, US profit to
    common, HK profit to shareholders), from the annual reports public by the date. Over the book until stage 6 (its
    growth in ROE): CN's past book was the book per share × profit ÷ EPS, an EPS 业绩报表 restates for later bonus
    shares while the book per share stays as reported (CATL 2022: CNY 288bn for its ~164bn), and a book can be small
    or negative (above); assets have neither fault, and the 8-year figure is on assets too.
  - Analysts' forecast growth is left out: stocks with the highest forecast growth have done worse (La Porta 1996), and
    forward E/P already uses next year's estimate.
- **Momentum:** the 12-1-month price return in the US and HK. In CN the price trend hasn't paid over 20 years (Jansen,
  Swinkels and Zhou 2021: past-return anomalies weak in A-shares), while earnings surprises are followed by drift
  (A-share studies, 2000-2020). So CN uses SUE: the latest quarter's 扣非 EPS minus the same quarter a year earlier,
  divided by the standard deviation of that change over the preceding 8 quarters, from the notice date. Stockopedia's own
  momentum rank mixes price and earnings momentum, so this stays within the method. HK's evidence on price momentum is
  mixed rather than negative, so it keeps the standard definition.
- **Forward E/P (stage 3):** the consensus EPS for the next 12 months over the price, at least 3 analysts (CN
  Eastmoney's 研报一致预期, US Nasdaq's consensus, HK Yahoo's). The predicted E/P is the largest part of the earnings
  yield in MSCI's Barra equity models, whose value factor MSCI's multi-factor indexes use; it judges a fast-growing
  company on the profit analysts expect, not only the last 12 months (on 2026-10-26 NVIDIA's trailing P/E was 26, next
  year's 13). The next 12 months (stage 6; universe.forward), as I/B/E/S and FactSet build their 12-month forward
  EPS: this fiscal year's estimate and next year's, each weighted by the share of the next 12 months its fiscal year
  covers; once this year has ended (its report still to come), next year's alone, which ends within 12 months (HK's
  table has no third year). Until stage 6 it was next year's estimate alone, whose horizon ran from 13 months (a
  December year end in November) to 25: in November 2026 Micron's "next year" was its fiscal year to August 2028, and
  175 of the ~1,080 US names with estimates had one 14-25 months out. The card says 未来 12 个月 PE. The analyst count
  is as before: next year's estimates in the US and HK, which also covers this year (an analyst who estimates next
  year estimates this one: on 2026-11-07 every A-share with 3+ brokers on 2027 had at least as many on 2026); in CN
  the consensus table's count of rating institutions (RATING_ORG_NUM), not a count per year.
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
  as a halving. Next year: the year after the first fiscal year without an annual report. The up-minus-down ratio
  (S&P DJI's second measure) needs each analyst's revisions over 3 months, which Yahoo gives only for 30 days; one
  definition in all three markets instead. Both dates are the same fiscal year in every market (Yahoo's trend keeps
  the +1y year; CN's brokers are filtered by the year), so a year's roll is never read as a revision; the card names
  the year revised (分析师 3 个月上调 2028 财年盈利预测: Micron's).
- No weights are fitted and nothing is chosen on our backtest.
- **How each ingredient is built** (stage 1; stockreport/signals.py):
  - Percentiles are taken over the whole scored universe (the 800 largest after the filters); the three lists then
    take their own size cuts.
  - CN 扣非 comes from 主要财务指标 (year-to-date 扣非 net profit as an amount, each quarter since 2015 and each fiscal
    year since 2009 for the long-run figures, by its first notice date), because 业绩报表 has 扣非 EPS only in half-year and annual reports. E/P = 扣非 TTM profit ÷ market value
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
- **Three ratings (stage 5, 2026-11-02).** Each market is split by the score into three sections and each section's
  top candidates are listed, as a sell-side analyst rates a stock Buy, Hold or Sell without knowing his clients'
  holdings: 20 Buy, 10 Hold, 10 Sell (your numbers). No portfolio enters the lists.
  - What "expected to go up / be stable / go down" can mean here. Brokers' ratings are relative: JPMorgan's Overweight /
    Neutral / Underweight expect a stock to beat, match or trail the average total return of the analyst's coverage over
    the next 6-12 months, Morgan Stanley's Overweight / Equal-weight / Underweight the same against the analyst's
    industry coverage over 12-18 months (their research disclosures). The score is built the same way: each family is
    ranked within the stock's sector, and the research behind it measures returns against the market, not their sign.
    So 买入 is expected to beat the market, 卖出 to trail it (in a rising market it may still rise), and the report says
    so in those words.
  - Sections: in the published sorts of composite factor scores the return spread is between the top and the bottom
    fifths; the middle has no expected edge either way. So the score's top fifth leans to Buy, its bottom fifth to
    Sell, the middle to Hold, and each list takes its section's best candidates by its own rule below.
  - Re-check date: 12 months from the report, for every rating: the rating's horizon (the brokers' 6-18 months; the
    history measures 12 months; NAPS holds a year). The lists are rebuilt each day, so a rating can change sooner; the
    newest report has the current one. (Before stage 5 a buy's re-check came sooner if its rank fell; with no holdings
    check there is nothing to re-check before the year ends.)
- **Buys (stage 3's redo):** 20 names from the whole scored market, equal amounts:
  - what can't be bought (it stays scored and can be rated Sell; the screen keeps it off Hold too):
    - Quantitative Value's screen (Gray and Carlisle, step 1: avoid a permanent loss): the 5% of each market's
      non-financials most likely to fail within 12 months by Campbell, Hilscher and Szilagyi's model (2008, Table 4,
      12-month horizon: profit and liabilities and cash over market value + liabilities, the past year's return,
      3-month volatility, size, market-to-book; each input winsorized at its 5th and 95th percentile among the market's
      non-financials, as CHS winsorize theirs, and a book still negative after CHS's adjustment counted as the highest
      market-to-book; the constant and the market terms drop out of a ranking, the US-only $15 price term is left out;
      liabilities and cash from Yahoo where the market's own tables lack them), and the 5% with the largest accruals:
      Sloan's (1996) working-capital accruals, the latest fiscal year's working-capital increase less depreciation over
      total assets, from Yahoo's cash-flow statement. A stock without the figures isn't screened. The model was
      estimated on US firms; in CN and HK it ranks the same signs of distress (losses, leverage, falling price,
      volatility, little cash) without an estimate of its own there.
      - The accruals: Gray and Carlisle's STA is net income minus operating cash flow over assets (the cash-flow form
        of Hribar and Collins 2002), and the first version here used that form. It also counts mark-to-market gains on
        investments, which Richardson, Sloan, Soliman and Tuna (2005) class as financial-asset accruals, the reliable
        kind that doesn't predict low returns; Alphabet's trailing profit held $129bn of them in 2026, which screened it
        out. Found in the spot checks; the screen now uses Sloan's own operating accruals for every stock. The quality
        family's cash backing (a sixth of quality, on the cards as 利润缺少现金支撑) keeps profit minus operating cash
        flow: profit that cash doesn't back, investment gains included, is what that card line says, and CN and HK
        have no current working-capital figures (only Yahoo's annual ones).
      - Beneish's M-score, the screen's third measure, needs receivables, current assets, PP&E and SG&A, which the
        tables we keep don't carry in every market: left out;
    - HK small caps: the names making up the last 5% of the field's HK-listed value, Hang Seng's SmallCap band (the
      Composite's LargeCap, MidCap and SmallCap cover the top 80%, the next 15% and the last 5% of its value): about
      180 of HK's ~390, under ~HK$20bn. Moderate risk, as agreed: no small caps;
    - partnerships (US master limited partnerships, K-1 units): a non-US holder has 10% of a sale's gross proceeds
      withheld and tax withheld on distributions (US tax code §1446(a), (f)), and the S&P 500 doesn't admit them. They
      were kept in the universe in Phase 4 for scoring and stay there;
  - places: each sector gets 20 × its share of the scored market's free-float value, rounded by the largest remainders
    (a sector can't get more places than it has names). How the share is measured, from the index providers' practice
    (MSCI, FTSE, S&P and CSI all weight by free float: shares held by the state, a parent or founders don't trade):
    - CN: market value × the CSI 300's free-float factor (each member's index weight over its share of the members'
      market value, from CSI's month-end file; the median factor for the ~500 others). Total value would give banks
      22% and 石油石化 7% of the places on 2026-10-31; by free float they are 10% and 2% (the CSI 300: 12% and 2%),
      since the state holds most of their shares. The members' market value is taken at the file's date (today's ÷
      the price change since, chained so bonus shares don't count; 2026-11-02 fix): with today's against a month-end
      weight, a member's factor moved with its price since the month end (新易盛 fell 50% in October 2026 and its
      factor doubled, to 5.1× its market value), which gave 电子 and 通信 a place each too many on 2026-11-02. The
      factor is relative (each member's free-float ratio over the members' average), so most exceed 1; a constant
      scale cancels in the sector shares;
    - US: total market value: by sector it is within 2 points of the S&P 500's float-adjusted weights (technology 40%
      against 42%), and it includes the foreign companies listed in the US, which the S&P 500 leaves out;
    - HK: HK-listed value (Yahoo's listed-class shares × price): an A+H company's A shares can't be bought in Hong Kong,
      and total value would give financials 37% instead of 29%. HK has no free free-float source (the Hang Seng's own
      weights aren't published per stock; Yahoo's floatShares counts all classes and puts ICBC at 62%);
  - picks: each sector's places go to its best scores; the next one is the sector's bench, which replaces a buy the
    review removes;
  - exact ties (2026-11-02): a tie goes to the larger free-float value, then the lower code (score.ranked), for the
    buys, the bench and the market rank; the Sell list is that order reversed (the lowest first, so of tied names
    the smaller); Hold's ties in volatility go to the lower code. Scores are compared at 12 decimals: equal means can differ in a float's last bit (中航光电 and
    中国船舶 both score 25/29, from 26,28,20,26 and 29,16,28,27 of 29 peers, stored 0.8620689655172414 and …413).
    Why: the same data must give the same list. Each family is a percentile among a sector's few dozen peers, so
    exact ties are common (on 2026-11-01, 162 CN, 253 US and 131 HK names shared a score with another), and they went
    to whichever row came first or to a float's last bit: HK's 长飞光纤光缆 and 联想集团 both scored 0.744186 for one
    place, and two builds picked differently. The larger name first, as each sector's places follow free-float value;
    the code only orders names that tie on both. What it changed: CN's 国防军工 place goes to 中国船舶 (free float
    457bn against 中航光电's 110bn; 2026-11-01 and 11-02); on 11-02 HK's 日常消费品 place goes to 农夫山泉 over 万洲国际
    (0.646552 both); bench names (11-01 US HALO for EHC, HK 古茗 for 青岛啤酒; 11-02 US NUE for MLI, HK 香港中华煤气 for
    华润电力) and the order of tied avoid names;
  - money: equal amounts, 5% each (Stockopedia's NAPS and AAII's model portfolios hold their names equally).
  - Why this replaces stage 3's first version (commit 930a02b: only the CSI 300 / S&P 500 / HK's largest 200, the
    largest index weight × score, money by index weight × score within UCITS 5/10/40). You rejected it on 2026-10-31:
    picking only from the index misses the rest of the liquid market (foreign companies listed in the US, the A-shares
    and HK names outside the indexes), and sizing by index weight is another bias, towards the largest names (US: 40% in
    NVIDIA, Amazon, Meta and Micron). The sector places keep what that version fixed: two places a sector gave every
    sector a tenth of the list whatever its size (US technology is ~40% of the market), which drifted the list away from
    the market it is measured against (the US 20 names trailed SPY by 2.9 points a year in 2018-2026). How you split
    your money between the list, funds or bonds is your business, not the report's.
  - Spot checks on 2026-11-01 (examples, not targets): see Status.
- **Hold (stage 5):** the 10 steadiest prices among the 400 largest names in the middle fifth of the market's score
  (from the top, the 40th to the 60th percentile), at most 2 per sector, not in Quantitative Value's screen, not a buy
  or a buy's bench, not vetoed (lists.holds). The next 5 in that order are Hold's bench, which replaces a Hold name the review removes.
  - Why the middle fifth, not the whole middle three fifths: its names lean neither to the top nor to the bottom (in the
    sorts the second and fourth fifths lean a little), the market-perform reading of a Hold.
  - Why the steadiest price (the lowest 1-year volatility of daily returns, the quality family's low-volatility measure
    and the dividend-low-volatility indexes' second sort): your word is "stable", and past volatility predicts future
    volatility well: it is persistent, which is why the low-volatility research sorts on it (Blitz and van Vliet 2007:
    portfolios sorted on past volatility keep their order out of sample; in China Blitz, Hanauer and van Vliet 2021).
    Among names with no expected edge these are the likeliest to stay near where they are. The same research found the
    least volatile stocks earned about the market's return with less risk ("lower risk without lower return"); they
    move less than the market both ways (low betas: Baker, Bradley and Wurgler 2011), so in a strongly rising year the
    list trails and in a falling one it falls less. What it doesn't promise, as the report says (the stage review's
    first finding): that a single Hold moves less than its index (a single stock rarely does: on 2026-11-02 every US
    and HK Hold and 8 of the 10 CN Holds had a higher 1-year volatility than their index), or that it holds its price
    over a year: daily volatility misses a steady slide (中国旺旺 −46% in a year at 29%), which the card's 风险 line names
    when the fall is 30%+ in 6 months. So the report words Hold as 评分居中、不偏涨也不偏跌、股价较稳, not "in line with
    the market", and says the 10 together moved less than the fund but lagged strong markets (stage 7: "fell less"
  went, as each held year's fall doesn't bear it out in the US and HK: US median −8.9% against SPY's −8.3%).
  - Why the 400 largest and 2 a sector, as Sell: names an investor is likely to know or hold, and the steadiest prices
    cluster in a few sectors (banks, utilities); why not the screen: a name likely to fail, or with the largest
    accruals, isn't expected to be stable.
  - Why not the 10 closest to the median score: a score's distance from the median says nothing about how a price will
    move, and it changes with every small move of the score.
  - On 2026-11-02 (the evening build): CN 中国核电, 平安银行, 兴业银行, 中国交建, 青岛啤酒, 国货航, 中国中车, 光大证券,
    上汽集团, 招商公路 (1-year volatility 16-22%); US Royal Bank of Canada, Xcel, TC Energy, Bank of Nova Scotia,
    McDonald's, Procter & Gamble, Illinois Tool Works, Pfizer, Canadian National, Ventas (16-23%; in the US rebuild an
    hour later Costco, its score rank 321 after one more company's Yahoo figures arrived, took Procter & Gamble's
    place: the middle fifth starts at 318); HK 交通银行, 招商银行,
    中国电信, 光大环境, 信和置业, 中国中车, 中国神华, 中国飞鹤, 中国旺旺, 福耀玻璃 (19-29%). Score ranks 323-470 of 796 (CN),
    336-469 of 794 (US), 163-223 of 390 (HK).
- **Sell:** the 10 lowest scores among the 400 largest, at most 2 per sector (lists.sells; the avoid list until stage 5,
  the same rule), each card with its weakest components and risks. A hard red flag only adds to its card.
- **No holdings check (stage 5).** Until 2026-11-02 the lists included a check of your holdings by NAPS's 12-month rule
  (data/holdings.csv and `hold`), then a neutral hold rating of the names sent to you. You said it is not our concern
  ("this has nothing to do what i hold in my portfolio"): both are removed, with the holding rule. How you split your
  money between the list, funds and bonds stays yours.
### Cards
- The price; the rank; the four grades A-E (fifths of each family); one line on why it's there (its two strongest
  components in words, with the figure); the key risk (a loss, heavy debt (70%+ of assets, the SASAC warning line; not
  financials) or a 30%+ fall in 6 months, else its weakest component); the cost of one board lot (CN 100 shares, US 1
  share, HK the board lot from HKEX's List of Securities, verified 2026-10-24: Tencent 100, HSBC 400, China Mobile 500,
  AIA 200); the re-check date (12 months on, the rating's horizon: "Lists"); what the company does in one line (stage
  4, "Report"). A buy's share of the money (5%, the same for every buy) is in the list's heading. Stage 5: every
  rating's card has all of this; why it's there is 为什么买 (the two strongest components) on a Buy, 为什么持有 (its place
  in the market's score and its 1-year volatility) on a Hold, 为什么卖出 (the weakest components and the risks) on a
  Sell. A ratio is worded by its side of the peers' median (同行中市盈率低 / 高), cash backing, momentum, the SUE,
  the revisions and the growth figures by their sign (the revisions as the estimate's 3-month change).
- From stage 2: the review's line (审核：… for a hard red flag, 市场可能在担心 … with its quoted source, or
  审核进行中 / 审核暂不可用; a clean review says what it read, stage 7: 近期公告、新闻和定期报告未见重大风险, or 近期公告和新闻…
  for a name whose latest report wasn't cut: a Sell name, or one still waiting for its report to be read) and the AI note (one sentence, words only). Stage 4: a soft concern shows the
  first one found, with 等 N 条 when there are more (a card has room for one; the rule and the findings are unchanged).
- Each market section opens with its 预期 line: from the history run, the 20-name portfolio's average 12-month return
  over the index fund, the share of 12-month windows it beat the fund, its worst 12 months and each held year's own
  largest fall from a peak at month-end marks (the median year's and the worst year's, against the fund's over the same
  months; stage 7: before, the overlapping portfolio's over the whole history, which no single buyer holds; now on the
  back pages), marked as simulated; the details and the published evidence are on the back pages (stage 4). Stage 5:
  under the Hold heading the Hold 10's average over the fund, their volatility against the fund's and their held-year
  falls; under the Sell heading the share of windows the Sell 10 trailed the fund, their average over it, their own
  average return and that the history leaves out delisted companies, which flatters Sell most (BACKTEST.md section
  24).

### Report (stage 4)
- The reader isn't an investment expert, so the decision comes first and the method last.
- Page 1, 今天要做什么, per market (stage 5): what the review removed and the name that took its place, the 20 buys by
  name with the amount and the date they are held to, what changed since the market's last report sent to you before
  today (data/sent.csv; counts, and the names gone when 8 or fewer), the 10 Hold and the 10 Sell names, the 预期 line in
  one sentence for all three; then a five-line guide (the three ratings in plain words, relative to the market and
  without anyone's portfolio; the three lists; the grades in words; the review; no guarantee).
- Market pages: the 预期 line in plain words; the money one board lot of every buy takes at equal amounts (stage 7:
  the dearest lot over its share of the money, 5%: on 2026-11-07 CN 89.6 万元 for 中际旭创's, US 2.85 万美元 for
  ASML's, HK 86.0 万港元 for 长飞光纤光缆's; arithmetic, worded as not advice); then each buy's card (rank, name, ticker,
  sector, price, one-lot cost, re-check date; the business line; the grades; 为什么买; 风险; the review's finding,
  "审核：近期公告、新闻和定期报告未见重大风险" on the risk line; the AI note), 新 on a name new since the last report; 审核剔除 and your vetoes; then Hold and Sell, each opening with
  its 预期 line, as cards with the same fields (为什么持有, 为什么卖出; stage 5).
  US cards are named by Eastmoney's Chinese short name (美光科技), with the English name beside it.
- Back pages: how the score and the lists are built, the three ratings, the review rules, where the words come from,
  the 预期 details (the 10 and 5 name ranges, the overlapping portfolio's largest fall, the neutral basket's split of
  the lead into the picks and the equal amounts with the places (stage 7), the history's limits, families running
  against the research) and the published evidence.
- The business line (verified 2026-11-01; all 200 names of the day found, CN 72, HK 62, US 66):
  - CN: Eastmoney's F10 company table RPT_F10_BASIC_ORGINFO, MAIN_BUSINESS (主营业务, often a short list of products:
    卫星化学 "(聚)丙烯、丙烯酸及酯、乙二醇…的生产和销售"); HK: RPT_HKF10_INFO_ORGPROFILE, MAIN_BUSINESS ("主要从事保险业务");
    the profile where either is blank. One call per market for the lists' names (codes `in (...)`, ~1 s). A first
    sentence up to 50 characters wide is shown as written (56 of 72 CN, 58 of 62 HK on 2026-11-02).
  - US: Eastmoney's US profiles (RPT_USF10_INFO_ORGPROFILE) often open with the state and year of incorporation
    (Allstate, Bristol-Myers Squibb, ASML) or are out of date (Sandisk's is about its spin-off), while Yahoo's
    quoteSummary assetProfile longBusinessSummary opens with what the company does ("Sandisk Corporation develops,
    manufactures, and sells data storage devices..."): its first sentences, up to 400 characters (one call a name, with
    the crumb). Eastmoney's US table gives the Chinese short names.
  - One Chinese line for a US text or a longer CN/HK one, by DeepSeek in the review's own call for the name (since
    2026-11-07; a separate call per company before): the text is given as 公司业务介绍 beside the card, ~25 characters
    asked from that text only, kept only when it is Chinese and has no figure (notes.line, notes.FIGURE), saved in the
    profiles table once written. A cached review is redone while the company still needs a line. Why not cut the long CN/HK text: the stage review found a cut at 50 characters misled on 10 of 25 lines
    (通威股份 read as a feed maker, its polysilicon and solar cells cut off; 中国国航 "主要由航空客运。"). Until the
    review has run, or without DeepSeek, a card shows the source's first sentence (cut with … past 50 characters; US in
    English, past 150).
  - Rule 2: the facts come from these sources. DeepSeek only translates and shortens a text code gives it, can't add a
    number (a line with one is dropped), and the source stays in the table beside its line. 2026-11-02: 66 of 66 US
    lines and 20 of 20 long CN/HK ones kept. data/fundamentals/<market>_profiles.csv.gz, fetched again after 180 days.
- The card's risk line says 风险 for a loss, debt of 70%+ or a 30%+ fall in 6 months, else 短板 (the weakest component,
  which isn't a risk by itself; the page 1 guide says so). A Sell card's reasons leave out a fact its weak line
  already shows (负债率高（88%） and 负债率 88%).
- "Changes" compare the buys with the last report sent to you (data/sent.csv). Stage 5 (small point (b) of the last
  review): the sender logs the buys report.build returned for the very text it sent, not reports/<day>/buys.csv, which
  a `run` finishing between the reply's build and its log could have rewritten (the file is gone). A reply that falls
  back to a report built earlier (the reviewed build failed) logs nothing: which list that file holds isn't certain.
- The WeChat summary (stage 5): the three ratings in one line, 审核剔除 with the replacement, then per market the data
  date, the 20 buys by name (US: the ticker and the Chinese short name, else the English name without Inc, Corp…; （新）
  on a new name), the change counts with the names gone, the 10 Hold and the 10 Sell names, the review's hard findings
  on Hold and Sell names, the 预期 line, and a last line pointing to the PDF. Over 3,600 bytes (90% of WeChat's 4,000),
  first the gone names become a count, then the 新 marks go, then US Hold and Sell keep only their tickers (a US name
  without a Chinese short name is long), then 预期 keeps only the buys' part, then US Hold and Sell become counts, then
  every market's; cutting whole lines from the end (fit_bytes) stays the last guard. The test data (CN and HK names
  five characters, three gone names a market): with US names in Chinese every name shows (3,542 bytes); with every US
  name in English, Hold and Sell go by count (3,176).
  2026-11-02 (11-01's lists, marked not updated): 3,244 bytes, the re-check names as counts; the test data (every US
  name long and in English) 3,617 bytes, and 3,620 with 12 sells in each market (tests/test_report.py).

### The history run (stage 1, once)
- On the existing month-end frames (CN 2019-01.., US 2018-01.., HK 2016-10..): each month's 20-name portfolio in equal
  amounts, held 12 months with a round trip of costs (0.2% US, 0.3% CN, 0.6% HK), against the index fund with dividends
  (SPY, 2800.HK, 510300.SS). Also its 10 and 5 best scores, to show how much fewer names widen the range.
- Each family's top fifth against its bottom fifth over the whole sample, per market.
- Stage 3's redo: the whole snapshot is the field; free float then is market value × today's float factor (CN: the
  CSI 300's; HK: HK-listed over all shares; US: market value). The snapshots have no consensus estimates and Yahoo keeps
  no history of EBIT, debt, cash and accruals, so the history's score has no forward E/P, revisions or EBIT/EV, and no
  screen; the long-run components come from the annual reports public by each month end. The report says so.
- Stage 5: each month's Hold and Sell 10 by the live rules (lists.holds, without that month's buys; lists.sells), held
  12 months the same way, with their volatility and largest fall against the fund's (BACKTEST.md section 24). Without
  the screen's inputs in the history, Hold isn't screened there.
- Stage 7: the snapshots carry no dividends, so the history's dividend yield is missing, not 0 (a 0 for every stock
  made its percentile one value per sector); the family check cuts its fifths within each peer group and month,
  weighted by the groups' share of the month's stocks; each month's list's own largest fall over its 12 months
  (month-end marks) against the fund's over the same months; a neutral basket (the same sector places, every name in
  the sector that can be bought, equal amounts within it) to split the 20 names' lead into the picks and the equal
  amounts with the places (BACKTEST.md section 25). It decides nothing.
- The CN frames are point-in-time by report date but hold only companies still listed (Eastmoney drops delisted ones),
  with restated 扣非 figures; US and HK hold today's listings. So every market's numbers are flattered, and the report
  says so (corrected in stage 1: this line said CN had delisted names).

### Results review (stage 2; only when you ask for a report)
The project's one AI step (2026-11-07, your words: "i can close claude code completely and still run the project,
just putting the AI part rely on deepseek token and ensure the quality"). Everything before it is code and runs
unattended (launchd: the 06:30 `run`, the keyword listener); without DeepSeek the report still goes out, marked
审核暂不可用.
The numbers can't see a fraud investigation, a going-concern doubt, an agreed takeover, or a story the market is
worried about. DeepSeek reads the stock's non-routine filings of the last 90 days (CNINFO, HKEXnews, SEC), the
passages code cut from its latest periodic report, and free headlines, at temperature 0 with a fixed checklist and
JSON out, one call per name; every finding quotes its source and code checks the quote (quotes.py). It never reads,
writes or changes a number (rule 2). The same call writes the note and the company line ("Report"). It reviews what the cards show first, in their order (every
market's 20 Buy names, then the 10 Hold, then the 10 Sell; stage 5, small point (a) of the last review), then the
benches (the next name of each sector held, the next 5 Hold names), up to 10 calls at a time, within a 20-second
budget; each review is cached per stock and redone only
for a name new to a list, a new filing or headline, or a review over 7 days old. A name not reviewed in time shows
审核进行中 and is finished in the background; if DeepSeek is down, the report goes out marked 审核暂不可用. The 06:30
build makes no DeepSeek calls.
- **Hard red flags** remove a Buy or a Hold name (the next name of its bench takes its place, of its sector first,
  listed under 审核剔除 with the reason and source: such a name is neither expected to beat the market nor to be
  stable; stage 5), and are noted on a Sell name: a regulator's investigation, a fraud finding or a
  Wells notice; a non-standard audit opinion or the auditor resigning; a going-concern doubt or a debt default; delisting
  or ST risk, or a suspension; an agreed takeover, merger or privatisation not yet completed, for cash, the acquirer's
  shares or both (2026-11-01: the rule first said "at a fixed price", which missed Kenvue, a US buy whose sale to
  Kimberly-Clark for 0.14625 of its shares plus $3.50 a share is pending: once a sale is agreed, the price follows the
  deal's terms and the acquirer, not the company's own results, and it stops trading at the closing); sanctions or a ban
  naming the company.
- **Soft concerns only annotate** (an industry downturn, a lost customer, a guidance cut, management leaving,
  litigation, a one-off gain): the card says 市场可能在担心 …. Cheap stocks carry bad news by
  nature, and that is where value pays off on average.
- **Data check:** by code, not the review: every valuation input is compared with a second source (crosscheck.py), and
  a stock whose figures disagree is dropped (rule 5). The deep dives' AI-read profit check was removed on 2026-11-07:
  in 18 reports it compared 8, 7 agreed within 0.3% and the 8th was its own unit misread; nothing since.
- The review can't be backtested (an LLM reading old news knows what happened next), so its powers stay this narrow; the
  scoreboard follows each removed name against the name that replaced it.
- **How it is built** (stage 2; review.py, passages.py):
  - Sources, gathered by the build with no DeepSeek (~60 s a market; reports/<date>/<market>_sources.json): each name's
    filings of the last 90 days from a per-stock query (CNINFO, HKEXnews' title search, SEC's filing list), routine ones
    dropped by the filing rules (events.classify), the newest 20; and headlines of the last 30 days, the newest 15.
    Per-stock queries rather than the old market-wide event feed, which only held the days the build ran (10 back;
    removed 2026-10-26). The routine rules drop bond, guarantee and auditor titles; a default, an overdue debt or an
    auditor resigning is checked first and kept as a risk filing (events.ALARM; found by the stage review).
    A US 8-K's Item 3.01 covers both a delisting or listing-rule notice and a company's own move to another exchange;
    for one, the item's text is read (fetch/filings.listing_moved) and a move with no deficiency language is routine
    (2026-11-02: Skydance's move from Nasdaq to the NYSE had been read as a hard 退市 flag from the item's title). Any
    sign of a listing problem keeps it a notice (compliance, a hearing or panel, a bid-price or listing rule, a letter
    received, a merger or Form 25: the review found a move offered as a cure for a deficiency would otherwise pass),
    and a filing that can't be read stays as filed.
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
    - a going-concern quote about a subsidiary alone (子公司, 附属公司, subsidiary; not 公司及子公司 or "the Company and
      its subsidiaries") is a soft concern (其他负面事件), on the card but not removing the name (2026-11-08, stage 7's
      review: 科达制造 left CN Buy on "关于法院受理子公司破产清算的公告" while its 9-month profit rose 66%). A group's
      subsidiary going under isn't the group failing, as a subsidiary's executive leaving isn't a CEO change (the
      management rule below); the checklist's going_concern is the company's own doubt, default or bankruptcy;
    - an audit opinion on internal control (a SOX 404 adverse opinion: a material weakness; a 内部控制审计报告's 否定意见)
      rather than on the accounts is a soft concern, 内部控制被出具非标准意见 (2026-11-08, stage 8's review: FMX left US
      Buy on "expressed an adverse opinion thereon", which its 20-F's auditor's report says of its report on internal
      control; its accounts' opinion was clean). The hard flag is for a qualified or adverse opinion on the accounts, a
      disclaimer, or the auditor resigning: the accounts can't be relied on. A material weakness says a control failed,
      and the US studies find a small price reaction to it, not a collapse (Beneish, Billings and Hodder 2008; Hammersley,
      Myers and Shakespeare 2008); in CN its consequence, the 其他风险警示 (ST) the exchanges impose for a 否定意见 on
      internal control, comes as its own announcement and is a hard flag (delisting). What the opinion is on: the
      subject named right after the opinion word (否定意见的内部控制审计报告; adverse opinion on internal control), else
      the nearest one before it in its sentence, read from the source line the quote was cut from; none named counts as
      the accounts (quotes.about, with the subsidiary test);
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
    not blocked, else to the best other one, and the money is split equally again. With none left the list is
    shorter.
    The scoreboard logs each removed name (bucket removed) and the name that took its place (bucket replacement), so
    `track` shows the two side by side.
  - Your confirm verdict (`verdict CODE confirm --until D --reason "..."`) overrides the review for that name until its
    date or the next report period: a Buy or Hold name stays, and the card says 你已确认 with your reason. A veto
    keeps a name off the Buy and Hold lists.
  - Cached per stock (data/review/<market>/<code>.json); the keyword reply waits `budget` (20 s), then sends what is
    done, and a background `review` finishes the rest. `review` runs it all without a limit.
    The AI note is dropped if it holds a figure (a digit, or one in characters like 三成), so every number on a card
    comes from code, and when code rejected, dropped or changed any finding the note was written with, so it never
    names a concern the card doesn't show. Stage 4: it gives no buy, sell or hold advice (a status is code's). (A note
    is no longer written without the periodic report: the passages are in its call since 2026-11-07, which ends stage
    4's CF case, a note denying the FTC investigation its 10-Q names.)
  - Periodic-report passages (2026-11-07; passages.py; the deep-dive lane of 2026-10-26..11-07 before them): filing
    titles rarely name an agreed sale of the company, a non-standard audit opinion, a going-concern doubt or an
    investigation stated in a report (Kenvue's pending sale to Kimberly-Clark, for 0.14625 of its shares plus $3.50, is
    only in its 10-Q; the deep dives found it on 2026-11-01). The build reads the latest periodic report (CN annual,
    half-year and quarterly reports; HK's in English; US 10-K, 10-Q, 20-F, 40-F) of the Buy and Hold names and their
    benches, at most 15 new filings per market a day, cached per filing (data/passages/), and code cuts the text around
    the hard-flag words (passages.KEYWORDS: 300 characters before and 700 after the first two hits of each, 6,000 at
    most; 1-3,000 characters a report on 2026-11-07, 2-9 s a report). They are numbered source lines in the review's
    call. A hard red flag quoted from a passage must say it plainly (passages.strict, the deep dives' rules): a
    non-standard opinion and not a standard one; a going-concern doubt, not a mention; an investigation opened (立案, a
    Wells notice, an SEC subpoena or the Division of Enforcement, 欺诈, 虚假记载, 造假), else a soft concern, and
    legal-proceedings boilerplate ("in the ordinary course") never hard; a sale of the company itself ("acquire ... the
    Company", "Company shareholders will receive", 被吸收合并, 协议安排, 私有化), not one it is buying, nor one completed
    or terminated. Other hard kinds from a passage are soft (their filings' titles carry them). Denials are dropped as
    for titles.
  - Why the deep dives' own DeepSeek pass went (2026-11-07): one AI step, and no quality lost. Its hard flags are kept
    (above), now for every Buy and Hold name and bench rather than 3 reports a market a day; in 36 reports read
    (2026-10-25..11-01) it found one hard flag (Kenvue, kept by the passages) and two soft concerns (CF's FTC inquiry,
    世纪华通's 2024 penalty), which the review reads in the same passages. Removed with it: the AI-read profit
    check (see Data check) and the non-recurring share of profit, a number read by the AI (rule 2); the review's
    one_off concern still comes from titles and headlines.

## Checks, and what each one decides
- **pytest** on the score math (peer percentiles, families, SUE, revisions, the long-run components, the distress
  logit, the list's places, picks, screen and equal amounts, the Hold and Sell lists) and the parsers, on small saved samples:
  catches calculation and parsing bugs.
- **The data cross-checks** (built): a stock whose figures disagree with the second source is dropped (rule 5).
- **The history run's family check** (fifths within sectors, stage 7): a family running strongly against its published direction over the whole sample
  in a market sends me looking for a data or definition bug. If none is found, the family stays (the published evidence
  is far longer than ours), and the report says so.
- **The history run's portfolio numbers:** they fill the report's 预期 line. They don't decide whether the report ships.
- **The fresh-eyes review** at the end of each stage (.claude/agents/stage-reviewer.md): catches what I missed, and
  spot-checks a few Buy, Hold and Sell names against their filings and news for common sense.
- **The live scorecard** (`track`, stage 8): the first report of each month starts a cohort per market (its 20 Buy, 10
  Hold and 10 Sell, equal amounts within each), held 12 months against the index fund with dividends and the 对照组合
  (the same sector places, every name that can be bought); month-end values kept as observed (data/cohort_marks.csv).
  One line on each market page (实盘记录, figures that change once a month); `track` prints every cohort. It catches
  live data faults and builds the method's own record, where the history can't (forward E/P, revisions, EBIT/EV and the
  screen; today's listings only). It decides nothing on its own and never holds anything up.

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
3. **Stage 3, redone (2026-10-31): the whole liquid market, the best scores, equal amounts, and the borrowed
   ingredients that were missing** (your words, 2026-10-31: "you are saying you only pick stocks from each market's
   index fund? then you are missing a lot ... your list is now index heavy, which is also another kind of bias"; and
   why Seeking Alpha's quant grades, Alpha Architect's Quantitative Value, Greenblatt's Magic Formula and the
   dividend-low-volatility indexes you named at the start weren't borrowed). The first version (commit 930a02b) picked
   only from the CSI 300 / S&P 500 / HK's largest 200, the largest index weight × score in each sector, sized by index
   weight × score within UCITS 5/10/40 (US: 40% in NVIDIA, Amazon, Meta, Micron).
   - Kept from 930a02b: analyst revisions in each momentum family, forward E/P in value, every family ranked within
     sector peers (signals.peers), the review's same-sector replacement, holdings judged within their sector, HK's
     listed-share cap, the card wording fixes, grades as exact fifths. The 可做空 label stays dropped.
   - Undone: buys only from the index (lists.parent), the largest index weight × score (lists.positions), money by index
     weight × score with UCITS caps (lists.weigh), the SPY weight file, the index weight on cards and in the report,
     `track`'s weighting. Never again: advice on how to split your money between the list and a fund.
   - Lists: the 20 buys come from the whole scored market (the 800 largest after the liquidity floors in CN and US, all
     that pass them in HK; no small caps), each sector given places by its share of the market's free-float value,
     filled by the sector's best scores, equal amounts; the bench is each sector's next name. How "share of the market"
     is measured, per market, from evidence ("Lists").
   - Score: four families, equal weights. Growth joins as Seeking Alpha's fifth grade does (revenue and profit growth,
     the 5-year change in ROE as in Asness-Frazzini-Pedersen's quality-minus-junk). Value adds EBIT/EV (Greenblatt's
     and Gray-Carlisle's value measure, in Stockopedia's ValueRank too) and dividend yield (ValueRank; 中证红利低波,
     恒生港股通红利低波); quality adds 8-year average profitability and gross-margin stability (Gray-Carlisle's
     franchise power) and low volatility (quality-minus-junk's safety; the dividend-low-volatility indexes). Buys skip
     the 5% most likely distressed (Campbell-Hilscher-Szilagyi probability) and the 5% with the largest accruals, as
     Quantitative Value's first step. Each with its evidence per market in "The score"; a field the free data lacks in
     a market is skipped there (rule 5).
   - AGENTS.md's Goal and rules 3 and 4 follow; the Goal's "not a defensive tilt" stays, with dividends and low
     volatility as two of the score's ~20 ingredients.
   - The history run again (docs/BACKTEST.md section 23) for the 预期 line; it fills the report and decides nothing.
   - Spot checks you gave (examples, not targets): Micron, AMD, Eli Lilly; Stellantis, GM.
   - Done when: pytest passes, with the new components, the new parsers on saved samples and the list construction; a
     full `run` renders all three markets; the history numbers are in BACKTEST.md section 23 and the 预期 lines; the
     fresh-context stage review has run and its findings are fixed or answered; this plan's status is updated and the
     work is committed on main.
4. **A report that is easy to read, a line on what each company does, a summary that fits, and switching it on**
   (your words, 2026-11-01: "Shorten the text summary so it fits, not simply shorten long US names, but overall should
   make sense; Turning the report on by loading the 06:30 daily build, sending one test report to WeChat and switching
   the keyword reply back on; also re-write the full pdf report to make it more easy reading, more user friendly, more
   concise and sharper ... somewhere too much information while somewhere is unclear about the key message; also maybe
   add a short intro of each company to tell what they do").
   - The PDF, for a reader who isn't an investment expert ("Report"): the first page says what to do and what changed
     (each market's buys, the holdings to sell or re-check, what the review removed, the names new to or gone from the
     list since the last report) and what to expect, in plain words; each card gives the company's business in one
     line, why it is there and its one key risk, with the price, the four grades, the one-lot cost, the review's
     finding, the AI note and the re-check date; holdings to sell or re-check get full rows, those kept one compact
     table; the method, the evidence and the review rules move to the back. Nothing the Goal requires leaves a card.
   - The company line ("Report"): from free sources, verified live; DeepSeek only translates a sentence code gives it,
     with no figures (rule 2).
   - The WeChat summary as a message: the actions first, then per market the buys by name, the avoid names and the
     预期 line, and a pointer to the PDF; all three markets fit under 4,000 bytes with room to spare.
   - Switching on, with your OK of 2026-11-01 (rule 9): the 06:30 `run` job loaded, one `send --test`, the keyword
     listener loaded.
   - Not changed: the score, the lists, the review rules.
   - Done when: pytest passes, with a test that a full three-market summary from the test data fits; a full `review`
     renders the new PDF and a summary that fits; I've read the PDF's pages and fixed what reads badly; both jobs run
     from this checkout and the one test send went out; the fresh-context stage review has run and its findings are
     fixed or answered; this plan's status is updated and the work is committed on main.
5. **Three ratings per market, Buy 20 / Hold 10 / Sell 10, and no portfolio check** (your words, 2026-11-02: "divide
   the market to three sections, stocks expect price to go up would be categorized as buy, while price to be stable
   would be categorized as hold, and price to go down would be categorized as sell. then pick the top candidates from
   each sections. this has nothing to do what i hold in my portfolio ... just like when a sell-side analyst issue a
   stock report, he would rate this stock with buy, hold or sell, without need to consider his clients holdings ... i
   am ok with you enlarge the buy list from top 5 to top 20, while i still want you to keep the hold and sell list to
   be 10 each per market").
   - Buy: the 20-name portfolio as built. Hold: 10 names, defined from published evidence ("Lists"). Sell: the avoid
     list (the 10 lowest scores among the 400 largest, at most 2 per sector), renamed and reworded.
   - Removed: the holdings check and the neutral hold rating (lists.held, check, recorded, cycle; the holding rule;
     data/holdings.csv and `hold`; the review's holding role; holdings among the deep dives; the 持仓检查 / 持有建议
     sections of the PDF and the summary).
   - The review in the order the cards show them (Buy, Hold, Sell, then the benches); a hard red flag or data_suspect
     takes a name off the Hold list as off the Buy list. data/sent.csv logs the buys report.build returned for the
     text that went out (not a file a later `run` may have rewritten).
   - Cards: everything AGENTS.md's Goal lists, on all three ratings, with the re-check date a rating's 12 months.
   - History: each month's Hold and Sell 10 against the fund (docs/BACKTEST.md section 24) in the 预期 line; it fills
     the report and decides nothing.
   - AGENTS.md's Goal and rule 4 follow, and this plan's Goal, Lists, Cards, Report and the review's roles.
   - Not changed: the score, the buy list, the review's red-flag rules.
   - Done when: pytest passes, with tests for the Hold selection, the Sell list and the removed holdings path; a full
     `run`, then `review`, renders the new PDF and a summary that fits, and I've read the PDF's pages and fixed what
     reads badly; the Hold and Sell history is in BACKTEST.md and the 预期 line; the fresh-context stage review has
     run and its findings are fixed or answered; this plan's status and AGENTS.md are updated and the work is
     committed on main.
6. **Correct the score's inputs** (your OK of 2026-11-07, "Start Stage A", after my reading of an outside review of
   the 2026-11-02 checkout: what it got right, what was already gone or handled, what breaks the rules; Status).
   - CN annual 扣非 from the amount each report states; the long-run figures on total assets in every market (8-year
     ROA, 5-year profit growth over assets); HK annual figures in the reporting currency; forward E/P on the next 12
     months, the card naming the fiscal year revised; EBIT/EV only with a cash line ("The score").
   - Not changed: the families, the weights, the lists' rules, the review.
   - Done when: pytest passes, with tests for each; the lists before and after on the same snapshots are compared and
     each changed buy is explained; a full `run`; the history run again (BACKTEST.md sections 23-24) and its 预期
     numbers; the fresh-context stage review has run and its findings are fixed or answered; this plan's status is
     updated and the work is committed on main.
7. **What the report says to expect** (done 2026-11-08; Status): the history's dividend yield as missing, not 0 (the
   snapshots carry none, so section 23's dividend spreads only sorted sectors by their size); the family check within
   sectors; each held year's own largest fall against the fund's over the same months (the 预期 line's fall is now the
   12 overlapping cohorts'); a neutral basket (the same sector places, every eligible name, equal amounts) to show how
   much of the lead over the fund is the picks and how much the equal amounts and places; the review line says what it
   read (公告、新闻、定期报告摘录); one line a market with the money one lot of each buy takes.
8. **A forward scorecard that answers the goal** (done 2026-11-08; Status): the first report of each month starts a
   cohort (20 Buy, 10 Hold, 10 Sell, and the 对照组合 of stage 7) held 12 months from the next close after the report,
   against the funds with dividends (SPY, 2800.HK, 510300); each cohort's month-end value kept as observed, so the price
   cleanup can't erase it; a suspended name stays unresolved rather than flat. Replaced: `track`'s picks with dividends
   against price indexes, stopped at 3 months, every day's list pooled. With it, at your word (2026-11-08), retention
   cut to what the build and the scorecard read ("Storage and cleanup"). Done when: pytest passes, with tests for the
   cohort's first close, the month-end values, an unresolved name and the basket's weights on small samples; a first
   cohort exists and `track` prints it; the fresh-context stage review has run and its findings are fixed or answered;
   this plan's status is updated and the work is committed on main.

## Kept from the old build
- The fetchers and cross-checks; the history tables; the SEC frames with dead companies; the point-in-time CN panel.
- The backtest snapshots and the stage-1 harness (index funds, costs, month-end frames).
- The event feed's filing rules (events.py), which classify the review's filings. Removed on 2026-10-26, unused since
  stage 2: the feed's market-wide fetch (every build read the latest days' filings of all three markets into
  data/events/, and nothing read the rows), its abnormal-move labels and the old per-stock title fetchers in cninfo.py,
  hkex.py and sec.py. The deep-dive lane's hard-flag rules (now passages.strict) and its quote check; the verdicts
  (veto or confirm with an expiry).
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
sectors within ±5% of the parent, each stock within ±2% of its parent weight). Stage 3's redo: Seeking Alpha, "Quant
Ratings & Factor Grades FAQ" (five sector-relative factor grades) and Cumming et al. (University of Kentucky, 2024) on
its record; Gray and Carlisle, "Quantitative Value" (Wiley 2012: the forensic and distress screens, EBIT/TEV, franchise
power); Campbell, Hilscher and Szilagyi, "In Search of Distress Risk" (JF 2008; NBER w12362, Table 4); Greenblatt, "The
Little Book That Beats the Market" (2006: EBIT/EV and return on capital); Loughran and Wellman, "New evidence on the
relation between the enterprise multiple and average stock returns" (JFQA 2011); Stockopedia, "The ValueRank" (P/B, P/E,
P/S, P/FCF, EBIT/EV, dividend yield); 中证红利低波动指数 (H30269) and 恒生港股通红利低波动指数 methodologies; Blitz, Hanauer
and van Vliet, "The volatility effect in China" (JAR 2021); Jegadeesh and Livnat, "Revenue surprises and stock returns"
(JAE 2006); Lakonishok, Shleifer and Vishny, "Contrarian investment, extrapolation and risk" (JF 1994); La Porta,
"Expectations and the cross-section of stock returns" (JF 1996). Stage 5: JPMorgan's and Morgan Stanley's rating
definitions in their research disclosures (Overweight / Neutral / Underweight against the average total return of the
analyst's coverage over 6-12 months; Overweight / Equal-weight / Underweight against the industry coverage over 12-18
months); Blitz and van Vliet, "The volatility effect: lower risk without lower return" (JPM 2007); Baker, Bradley and
Wurgler, "Benchmarks as limits to arbitrage: understanding the low-volatility anomaly" (FAJ 2011).

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
- Daily snapshot: data/snapshots/<date>/<market>.csv.gz with the computed metrics and scores per stock (~1.4 MB a day
  for the three). Kept 30 days (400 until stage 8): code reads only the newest earlier one (drift alarms, verdicts) and a
  cohort's day, the day after it (the scorecard's 对照组合); the backtest's one (2026-10-18, US and HK) is copied to
  data/backtest/today_snap_<market>.csv.gz.
- Reports: reports/<date>/ (PDF, summary, lists CSVs, review sources; ~3 MB a day) kept 30 days (90 until stage 8): code
  reads each market's newest lists. data/picks.csv (every report's three ratings) is tiny and kept forever.
- The scorecard (stage 8): data/cohorts.csv.gz (each month's cohort: the three ratings, the fund, the 对照组合's names and
  weights; ~9 KB a month) and data/cohort_marks.csv (each group's month-end values, a few KB a year), kept forever,
  outside cleanup's folders.
- Logs: kept 30 days.
- All retention periods are config values.
- `cleanup` runs automatically at the end of every `run`. `cleanup --dry-run` lists what would be deleted and the space it would free.
- After each run, log the total size of data/ + reports/. If it exceeds 2 GB, add a warning line to the report footer.
- Cleanup only ever deletes inside this project's data/, reports/ and logs/ folders.
- Phase 6 estimate (2026-10-17): price files ~33 MB (rolling 385 days), snapshots ~1 MB a day × 400 = ~400 MB, reports ~1.7 MB a day × 90 = ~150 MB, raw ~3 MB a day × 7 = ~20 MB; steady state ~0.6 GB of the 2 GB limit.
- Measured 2026-11-08 (stage 8): data/ + reports/ 1.0 GB, of which data/backtest 869 MB (cleanup doesn't touch it),
  history 21, prices 33, snapshots 18 (16 days), reports 36 (16 days). Snapshots and reports had grown to ~1.4 and ~3
  MB a day, so the old periods would have settled near 1.8 GB; at 30 days ~1.1 GB, and ~0.85 GB without the old
  engines' outputs in data/backtest that nothing reads now (s1_*, s3_*: 255 MB; stage1.py's and the removed stage-3
  scripts'; rebuildable).
- Phase 11, since 2026-11-07: data/passages/<market>/ keeps the passages cut from each periodic report read (a few KB each, at most 45 a day, deleted after 400 days; data/deepdive/ before); filing documents are read in memory and never stored; data/verdicts.csv is tiny.
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
    cn_index (the CSI 300's weights, CN's free-float factors, daily; us_index, SPY's, removed in the redo),
    quotes/hk_yahoo_shares (HK-listed shares, daily); stage 3's redo: fundamentals/cn_yahoo and hk_yahoo (Yahoo's
    trailing EBIT, debt, cash, minorities and liabilities, weekly, ~0.2 MB each);
    a few tens of KB each.
  - data/sent.csv (2026-11-02): date, market, ticker, name and the lists' date of each report's buys sent to you (for
    the "changes" line), a few KB a year, kept. data/picks.csv's rows of the old v3 method (2026-10-17..21, Buy 5 /
    Hold 5 / Sell 5 a market) were bucketed v3 buy / v3 hold / v3 sell in stage 5, so `track` keeps them apart from the
    new Hold and Sell, and the avoid rows (the Sell rule since 2026-10-24) became sell.
  - Stage 4: fundamentals/<market>_profiles (each listed name's Chinese short name and business line; US also Yahoo's
    English sentence and its Chinese line), fetched again after 180 days, a few tens of KB each.
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
    quarter. data/history/cn_deduct.csv.gz (2.9 MB, 2015-03.., and each December 31 from 2009: stage 6, the
    long-run figures' annual 扣非, ~3,000-5,400 rows a year), each period once, the open one daily.
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
  - CSI 300 weights (stage 3, verified 2026-10-26; since the redo only CN's free-float factors, "Lists"): CSI's month-end file
    oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/closeweight/000300closeweight.xls (300 rows,
    weights in %, the date first), read with xlrd. Banks are 12% of the CSI 300 against 24% of the largest 300's total
    market value (state holdings aren't free float), 石油石化 1.7% against 7.4%.
  - Backup: the Tushare token in .env.
  - The a-stock-data skill documents many CN endpoints.
  - Backtest (verified in Phase 9, 2026-10-18): 通达信 packages exist from 2021-08-13; RPT_VALUEANALYSIS_DET has every trading day from 2018-01-02 (pageSize 5000: one request a day; CHANGE_RATE = close ÷ ex-rights prev-close, identical to the packages), but only for companies still listed (delisted ones are dropped from it and from 业绩报表); 业绩报表 back to 2009; the 申万 change history (swsresearch.com xls; Python's TLS client is refused, curl works); the research-report archive (reportapi report/list) pages to the end, but its predict*Eps fields are relative to today (2019-2023 reports have none, 2024 reports only FY2026); RPT_RES_PROFITPREDICT and RPT_WEB_RESPREDICT hold the current years only; CNINFO's market-wide query stops after ~80 pages a day; the Tushare token has no API access.
- US (verified in Phase 4, 2026-10-17):
  - Universe: the Nasdaq screener, api.nasdaq.com/api/screener/stocks?tableonly=true&download=true (every NASDAQ/NYSE/AMEX listing in one call: price, market value, sector, industry). Its market value is company-wide on every share class and ADR, so shares = market value / price; its price can lag Yahoo by a day, so market value is rescaled to Yahoo's close and a stock whose screener price matches none of Yahoo's last 3 closes within 1% is dropped. Share counts (2026-10-25, crosscheck.us_shares): the screener's count is wrong at times (Monster's 2:1 split of 2026-08-11 counted 3:1, Cboe 7% high) and adds Up-C units and voting-only classes that the parent's profit and book leave out (Carvana, TKO, Symbotic, Blue Owl: 30-370%; Ferrari's special voting shares, On's class B). So before the universe is cut, three counts in the listed security's units (an ADR's depositary shares) are judged by the filings: the screener's and Yahoo's two quote counts (v7 quote, 11 calls a day: impliedSharesOutstanding, every class, as Alphabet's three and Berkshire's in B shares; sharesOutstanding, the listed class, as an Up-C's class A). The judges, in the filer's units, × Yahoo's splits since: SEC's basic weighted-average shares of the latest quarter (the EPS denominator) and the latest 10-Q/10-K cover count; for filers with neither (20-F filers), the last annual EPS denominator, only where Yahoo's two counts agree (Itau's 20-F tags one class's count: half the company). The screener's count stands when a judge is within 5% of it (often it is the cover's, newer than the quarter: Gartner's buyback, the shares Martin Marietta and Public Storage issued in acquisitions since); else the first Yahoo count a judge is within 5% of is used; else, more than 20% off every other count, the stock is dropped (rule 5). Yahoo's statement count (OrdinarySharesNumber) is no judge: it leaves out AB InBev's restricted shares, sums Blue Owl's Up-C classes, puts Berkshire in A shares and CME in thousands, and a version that used it set Martin Marietta and Public Storage back to July. Why the parent's count: the published value research's market equity is CRSP's shares of the listed classes (summed across classes, as for Alphabet and Berkshire) against Compustat's parent earnings and common equity, with S/P on consolidated revenue over that market value; an Up-C's unlisted units aren't in it. Not settled, the screener's count stands: an Up-C without an SEC count (Ares: its filings tag the counts per class only, which companyfacts leaves out, and its two Yahoo counts look like Berkshire's; the per-class counts are only in the 10-Q's XBRL instance) and a dual-listed company (Rio Tinto: the screener's is the plc's, the profit the group's). The Eastmoney list (push2 clist) is blocked, as for CN. The 1,100 largest ordinary shares are kept up to date (config `us_candidates`).
  - Company names (2026-11-02): Yahoo's v7 quote longName, read in the daily share-count call (no extra request;
    1,090 of the 1,100 candidates), else the screener's (nasdaq.named). About 20 of the 794 screener names carried
    share-class, registry or domicile words or errors ("Bank Nova Scotia Halifax Pfd 3", "Kimco Realty Corporation
    (HC)", "Mizuho Financial Group Inc. Sponosred ADR (Japan)", "Marsh", "DBA Sempra", "Generac Holdlings Inc"), which
    the cards showed and the review's prompt read as facts: the DeepSeek note on BNS, a Hold, called its common share
    a preferred one. Yahoo's shortName repeats the screener's, so longName. Verified 2026-11-02 on BNS ("The Bank of
    Nova Scotia"), BRK-B, GOOGL, RY, TD and the 20; the four partnerships still end in LP / L.P., so they still can't
    be bought. A cached review is now redone when the name it was written for changes (review.valid).
  - Trailing-12-month fundamentals: SEC companyfacts (data.sec.gov/api/xbrl/companyfacts), 4 at a time, at most ~8 requests/s, User-Agent = SEC_USER_AGENT from .env; refreshed weekly per company (~5 min for 1,100). Files are 1-8 MB: they are parsed in memory and never written to disk. TTM = year-to-date + last fiscal year - same YTD a year earlier (the CN formula), or, after an annual report for less than a year (a fiscal-year change's transition period, a merger's successor stub), the fewest reported periods added and subtracted end to end that span the 12 months (not otherwise: L3Harris tags its fiscal-year revenue with Q4's dates); growth = TTM vs the TTM a year earlier. Concepts are merged per period in a preference order because companies switch tags between filings, with three rules from the Phase 12 cross-checks (2026-10-19), also in the annual history: revenue is chosen per period, because companies also tag parts of it with its concepts (ASC 606 fee revenue at M&T, AmEx and SoFi, Blue Owl's "Revenues", Zions' non-interest revenue subtotal) and totals before intersegment eliminations (Williams' ASC 606 total, Hasbro's "Revenues"): the concept within 5% of what the income statement implies (gross profit + cost of revenue, else operating income + total costs and expenses), else the largest concept (REITs' rent: OperatingLeaseLeaseIncome), and for banks net interest + noninterest income when larger; a 12-month figure comes only from a 10-K (Comfort Systems' Q1 2026 10-Q tagged Q1 2025 revenue as the 2025 year); equity and net income are the parent's: the total including minorities less MinorityInterest when only the total is tagged (AT&T, Carlyle, TPG, Royalty Pharma), ProfitLoss less the minorities' share when NetIncomeLoss is missing (Invesco).
  - Gaps (changed in the Phase 4 review; freshness: 200 days, 300 for half-year reporters): Yahoo fundamentals-timeseries (ws/fundamentals-timeseries/v1/finance/timeseries), one call per company, weekly, for companies SEC can't cover: no recent us-gaap 10-Q/10-K (foreign filers), no CIK, or a missing field (e.g. MLPs report partners' capital). It gives TTM revenue / profit / gross profit / operating cash flow and the balance sheet in the reporting currency; growth is TTM vs the TTM a year earlier, else the fiscal year a year earlier, else the same quarter a year earlier, else the last two fiscal years (semiannual reporters). 259 of 262 gap companies covered on 2026-10-17 (~80 s); 796 of the top 800 have complete data. Changed in Phase 12: fetched weekly for all 1,100 candidates (gap companies first), as the second source of the cross-checks, with NetIncome (before preferred dividends) and OrdinarySharesNumber added; ~5 min the first time. Stage 3's redo (verified 2026-11-01): also EBIT (trailing), TotalDebt, CashCashEquivalentsAndShortTermInvestments and MinorityInterest (latest quarter, else year), for EBIT/EV and the distress probability (GM: EBIT 5.2bn, debt 128.7bn with GM Financial's, cash 27.8bn); the same call for CN (600519.SS / 000001.SZ, the 1,200 largest A-shares) and HK (the 1,200 candidates) into cn_yahoo / hk_yahoo, weekly, ~12 min each the first time. Yahoo's A-share series were current on 2026-11-01 (600519 to 2026-06-30, 300750 to 2026-09-30); a series older than the freshness rule leaves EBIT/EV out for that stock.
  - Not used: FMP's free key. It served 7 of 184 gap companies (402 "premium" for ASML, NVO, SAP, AZN, SHEL, HSBC, TM, RY...) and stops at ~250 calls a day, which dropped 168 of the top 800.
  - Annual history (Phase 7): the same companyfacts files, forms 10-K, 20-F and 40-F, in us-gaap or ifrs-full: 20-F filers such as TSM and NVO report in ifrs-full (NVO has no ProfitLossAttributableToOwnersOfParent: ProfitLoss and Equity instead), ASML and BABA in us-gaap. One currency per company, the one with the most annual figures (TSM: TWD; its USD convenience figures cover the same years but appear only once each). Companies SEC has no annual history for: Yahoo fundamentals-timeseries annual types (4-5 years).
  - Monthly prices (Phase 7): the Yahoo chart API with interval=1mo and events=div,split over 11 years, for the candidates, ^GSPC and FX (<CUR>=X). Yahoo's closes are split-adjusted (NVDA Nov 2015: 0.79); they are stored as traded (× later split ratios: 31.72) to match the book value per share reported then, and monthly returns come from adjclose. Bars start at local midnight, and the current month appears twice (month start and last trade): only complete months are kept.
  - Analyst consensus EPS (added in Phase 4, for the forward lens and check 2): Nasdaq api/analyst/<symbol>/earnings-forecast, the first three fiscal years not yet reported; analysts = estimates behind next year's EPS. 2-4 s per call, so 4 at a time, weekly (~13 min for 1,100).
  - Revisions (stage 3, verified 2026-10-26): Yahoo quoteSummary modules=earningsTrend for the 1,100 candidates, weekly
    (~7 min): the +1y period's avg, numberOfAnalysts, earningsCurrency and epsTrend's 90daysAgo (the same fiscal year:
    MU's +1y is FY2028, 162.9 then and 206.9 now, while its 0y FY2027 was 153.9 then). epsRevisions counts up and down
    revisions for 7 and 30 days only (90 days is blank).
  - S&P 500 weights: SPY's holdings file was read in stage 3's first version; removed in the redo (US free float ≈ total value by sector).
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
  - FX: Yahoo "<CUR>=X" for HKD and the reporting and estimate currencies (CNY, USD, SGD, JPY, EUR...), and 12 years of daily "<CUR>CNY=X" closes for the period-end rates (900 days until stage 6; the HK annual history
    goes back to 2015; data/fx_cny.csv.gz, ~280 KB, rewritten with each HK fetch).
- FX, only needed when a company reports in a different currency from the one it trades in: ECB rates via api.frankfurter.dev.
- Legacy references (read only), all under ~/Developer/EquitySignalsClawbot-legacy/:
  - Sources/EquitySignalsClawbotCore/PublicUniverse.swift (around line 1310, the Eastmoney list call)
  - Sources/EquitySignalsClawbotCore/MacroPanel.swift (rate sources)
  - Sources/EquitySignalsClawbotCore/EastmoneyHKFinancialStatements.swift
  - script/a_stock_snapshot_sidecar.py (Tencent/Sina A-share calls)
