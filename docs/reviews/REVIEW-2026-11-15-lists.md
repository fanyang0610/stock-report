# Lists check after stages 16 and 17, 2026-11-15 (Fable 5.2, read-only)

The check the method review of 2026-11-13 planned ("How to run it"). Nothing in the code, the data or git was
changed; this file is the only output, uncommitted. Commit checked: ac6f677 (stage 17 on stage 16's 5b2a1a9).

## Verdict

**Sound to push and merge: yes. Confidence about 80%.**

- Stages 16 and 17 do what they say, and each list is better than what main sends today. The saved lists of
  2026-11-15 rebuild exactly from the snapshot, and every name the buffer kept is inside its buffer.
- Nothing found is a regression against main. The faults below are either older than these stages or a narrower
  effect than intended.
- The remaining 20% is the Sell list. It can't be tested on the history (the report says so), and 2 of the 10 US
  Sells are there on a data fault, not on the company.
- Two small fixes should follow the push in one short stage ("17b"): F1 (HK Sell is drawn from micro caps) and F2
  (the buffer protects nothing at the Sell and Hold cut where the sector cap binds). F3-F5 are the systematic Sell
  false positives, each with a structural fix.

## What was checked, and how

- Read: AGENTS.md; PLAN.md ("The score", "Lists", "Cards", Status 16 and 17); the method review; lists.py, score.py,
  signals.distress; `reports/2026-11-15/` (the three lists, summary.txt, report.html as text) and the snapshot.
  BACKTEST.md sections 26-27 only through the Status entries: the brief excludes the backtest as evidence.
- Rebuilt each market's lists from the snapshot with `lists.build`, with the previous ratings and without them.
- Spot-checked 60+ names against the snapshot's figures and, for about 30, against news from the last three months
  (web search; sources in each finding).

## 1. Do the ratings look sensible?

Mostly yes for Buy and Hold. Sell is right in kind and wrong in a few names.

| | Buy 20 | Hold 10 | Sell 10 |
|---|---|---|---|
| CN | Sensible, concentrated (F8) | Sensible | Sensible |
| US | Sensible, concentrated (F8) | Sensible | 6 defensible, 2 arguable, 2 false on data |
| HK | Sensible; 3 names below the score's top fifth | Sensible | Right kind, wrong size: 7 micro caps (F1) |

Names checked:
- **CN Buy.** 卫星化学 (9-month profit +141%, P/E 7), 云铝股份 (P/E 6), 格力电器 (P/E 9, yield 8%), 江苏银行 and
  南京银行: fit the rating. 兆易创新, 中际旭创, 生益科技: earnings still rising, but electronics lost about 10 trillion
  yuan of value since July and 中际旭创 fell 58% from its June high; the market is pricing a peak the score can't see.
- **CN Hold.** 中国铁建, 大秦铁路, 兴业银行, 伊利股份, 中国核电: large, steady, 16-19% volatility. Nothing against them.
- **CN Sell.** 中国东航 and 南方航空 (the three big airlines lost 8.4bn yuan in nine months on fuel), 江淮汽车 (9-month
  loss 1.14bn, operating cash −4.9bn), 芯原股份 (half-year loss 0.61bn, price halved since August), 百利天恒 (9-month
  loss 0.7bn, though its third quarter was profitable and its first drug is approved). All defensible.
- **US Buy.** Alphabet, Meta, TSMC, Regeneron, Target, Allstate: fit. Micron, Sandisk, Western Digital: forward P/E
  4-10, but Micron is 36% below its June peak of about $1,214 and the cycle's top is openly debated. HF Sinclair
  (third-quarter refining margin +183%) and CF (ammonia +27%) are at cyclical highs.
- **US Hold.** Berkshire, Duke, WEC, Royal Bank of Canada, McDonald's, Johnson & Johnson, Costco: steady, nothing in
  the news against them. Costco is a Hold on steadiness at 48 times forward earnings.
- **US Sell.** Defensible as valuation calls: Snowflake (121 times forward earnings, though 86% of analysts say Buy),
  Cloudflare, Bloom Energy (a class action, 12 of 26 analysts at Hold), Moderna (up eight times in a year on one
  trial result, still losing $2.8bn), Boeing (a 9-month loss of $551m), Carvana. Arguable: Constellation and Vistra
  (the policy risk is real after the midterms; the "distress" wording isn't). False on data: Lumentum (F3), Ares (F4).
- **HK Buy.** 中国海洋石油 (9-month profit +17%), 中国移动, 安踏体育, 长实集团: fit. 中国太平 is fourth on a P/E of 1.85
  that a one-off tax effect made (F3).
- **HK Hold.** 中电控股, 招商银行, 香港交易所, 恒安国际, 顺丰控股: steady. Nothing against them.
- **HK Sell.** 黑芝麻智能, 博泰车联, 中国东方航空, 小鹏集团, 亚盛医药: loss-making and expensive, defensible. But see F1.

## Findings

### F1. HK Sell is drawn from the whole field, so it lists micro caps (fix in 17b)
- **Evidence.** `largest = 400` is a count. CN and the US score about 800 names, so it cuts the field in half. HK
  scores 396, so it cuts nothing. 7 of the 10 HK Sells rank 286th to 398th of 396 by size; four are worth HK$4-8bn.
  Five listed in 2024-25. PLAN's reason for the cut is "names an investor is likely to know or hold", and Buy
  already refuses HK small caps ("moderate risk: no small caps").
- **Why now.** The cut is from stage 5. Stage 17's measure made it decisive: small recent listings with losses sit
  at the bottom of value, quality and safety at once.
- **Fix.** Draw HK's Sell and Hold from the band Buy uses: Hang Seng's LargeCap and MidCap, the top 95% of listed
  value (212 names; `small_share`). No new number.
- **What it changes.** 7 of 10 HK Sells. With the 200 largest and no buffer: 中国东方航空, 小鹏集团, 蔚来,
  中国南方航空, 山东黄金, 康方生物, 地平线机器人, 金斯瑞生物科技, 渣打集团, 赣锋锂业. HK Hold is unchanged (all large).

### F2. The buffer is measured before the sector cap, so it protects nothing at the cut (fix in 17b)
- **Evidence.** `lists.sells` and `lists.holds` apply `buffered` to the raw order (first 8, then current names within
  12), then `capped` drops the third name of a sector. Where the cap binds, the list's last places lie beyond raw
  rank 12. On 2026-11-15 the 10 listed Sells sit at raw ranks 1-15 in CN and 1-17 in HK; the Holds at 1-15 (CN) and
  1-13 (HK). A current name near the cut is outside the buffer zone, and a new one at raw 13-15 enters freely.
- **It shows in the plan's own table.** Sell exits over the week, new rule without and with the buffer: CN 5 and 5,
  US 2 and 2, HK 4 and 3. The buffer changed almost nothing.
- **Fix.** Count the buffer's places after the cap: the first 8 capped names, then current names within the first 12
  capped. This is what "Lists" already says ("the new top 8 first, the current names within 12").
- **What it changes.** Fewer Sell and Hold exits in CN and HK; today's lists stay the same.

### F3. One-off items in US and HK trailing profit and EBIT (systematic; data stage after the push)
- **Evidence.**
  - Lumentum (Sell). Fiscal 2026 net loss $6.9bn, of which $7.8bn is a non-cash loss on retiring convertible notes;
    GAAP operating margin was +17.4%. The card says 近 12 个月亏损, EBIT 为负 and 多年平均亏损. Yahoo's EBIT is pretax
    profit plus interest, so the charge is in it. The stock trades at 15 times next year's estimate.
  - Carvana (Sell). The card says EV/EBIT 408.9 on an EBIT of $0.14bn. Its third quarter's operating income alone was
    $714m.
  - Boeing (Sell). Trailing P/E 17.8 comes from a 2025 disposal gain; 2026 is a loss so far. Here the one-off flatters.
  - 中国太平 (HK Buy, 4th). P/E 1.85 and ROE 32% rest on a one-off tax effect the company named in its profit alert.
- **Cause.** CN ranks on 扣非 profit. The US and HK rank on reported profit, and EBIT/EV on Yahoo's figure.
- **Published basis.** Greenblatt and Gray-Carlisle rank on operating earnings. Novy-Marx (2013) uses gross profit
  because lines further down are polluted. Rouen, So and Wang (JFE 2021) find non-core items are transitory and
  mispriced.
- **Fix.** US EBIT from the SEC's operating income, Yahoo's only where it isn't tagged. A core-profit figure for the
  US and HK (the SEC's operating income after tax; HK has no free 扣非) is a larger data question.
- **What it changes.** Lumentum most likely leaves Sell; Carvana's card shows a true figure; 中国太平's value falls.
- **Not verified.** How many of the 790 US names carry such items: the snapshot has no operating-income column.

### F4. Fee businesses that consolidate insurers or funds are read as indebted (systematic; 17b or the universe)
- **Evidence.** Six US names outside `financial` carry liabilities that are their product: Ares (71% of assets,
  consolidated funds), KKR (81%, Global Atlantic), Apollo (93%, Athene), Ameriprise (97%), Carlyle (77%), Equitable
  (100%, a life insurer). The failure logit puts Ares, KKR and Apollo in the riskiest 12-14%, and quality at 0.04-0.19.
  Ares is Sell #4, KKR 22nd, Apollo about 30th. Ares' card says 负债率 71% and 困境概率排前 15%; neither is about Ares'
  own debt. BlackRock already counts as a financial through Nasdaq's broker industry, so the line is uneven.
- **Published basis.** Fama and French (1992) exclude all financial firms (SIC 6000-6999) because their leverage
  doesn't mean distress; Ohlson (1980) fitted his failure score without them. Not verified: whether Campbell,
  Hilscher and Szilagyi excluded them.
- **Fix.** For the two measures that read leverage (the failure logit and debt ÷ assets), treat the whole SIC
  6000-6999 division as not applicable, at the middle. The rest of their scoring stays.
- **What it changes.** Ares' Sell measure goes from 0.10 to about 0.22 (roughly 20th); Rocket Lab takes its place.

### F5. Sell admits names with the strongest momentum (method question; next method stage)
- **Evidence.** 6 of 10 US Sells have a momentum family of 0.63 or more; Bloom Energy 0.93, Moderna 0.88, Lumentum
  0.88. CN has two (昆仑万维 0.82, 江淮汽车 0.79), HK none.
- **The published evidence cuts one way only.** Daniel and Moskowitz (2016) show the losers rebound, and only after
  bear markets; that supports not choosing a Sell for weak momentum. It says nothing for choosing winners. Asness
  (FAJ 1997) finds value's edge weakest among winners and momentum strongest among expensive stocks. The score
  itself gives momentum a third of every Buy.
- **Fix.** A name in momentum's top fifth (grade A) isn't rated Sell, as the 5% likeliest to fail can't be a Buy.
- **What it changes.** US: Bloom Energy, Moderna and Lumentum out; about Rocket Lab, Cardinal Health and Rocket
  Companies in. CN: 昆仑万维 out. Snowflake (0.63) stays, so this is not a rule for it.
- **Confidence: medium.** The Asness paper is from memory; read it before building.

### F6. The Sell card's first line misleads (words; 17b)
- **Evidence.** Each Sell card opens 财务困境概率在全市场非金融股中排前 N%, shown for the riskier half. Snowflake
  (前 9%) generates cash; Constellation (前 9%) earns $3.5bn; 云知声, 极智嘉 and 映恩生物 hold more cash than their
  total liabilities; 中国东航 (前 1%) is state-owned. Among the 800 largest the logit's spread comes mostly from
  leverage, volatility and price-to-book (5th-95th percentile ranges 0.83, 0.81, 0.66; profit 0.41). A reader takes
  it as "may go bankrupt".
- **Fix.** Say what it measures, 综合风险（亏损、负债、股价波动和下跌）排在全市场前 N%, and only in the riskiest tenth,
  where Campbell, Hilscher and Szilagyi's result lies. Page 1: 又贵、质量又差，或财务风险高.
- **What it changes.** The words on about 25 of 30 Sell cards. No list changes.

### F7. The buffer is borrowed without the review calendar it belongs to (new stage)
- **Evidence.** MSCI and CSI apply the 20% buffer at half-yearly reviews; here it runs every day. After it, a week
  still shows 3-5 Buy exits and 4-8 Hold exits per market (PLAN's table); HK Hold keeps 5 of 10. Most sectors have
  one place (CN 14 of 16, HK 8 of 11), where the buffer is "first or second". Page 1 says 要明显掉出范围才换.
- **Fix.** Ratings change at a review: the month's first report, which the 实盘记录 and the history already follow.
  Between reviews the names stay and only prices and the review's removals change.
- **What it changes.** About 12 list changes a year, not about 250 chances; the list a reader holds stays the list.

### F8. The report doesn't say how concentrated the buys are (words; with F7)
- **Evidence.** US: 5 of 20 buys ride one chip cycle (Micron, Sandisk, Western Digital at 83-114% volatility, plus
  TSMC and ASML). CN: 5 in AI hardware (兆易创新, 生益科技, 中际旭创, 睿创微纳, 视源股份), three down 24-56% in six
  months. The buys' median profit growth is still CN +63% and US +66% (the markets +9% and +18%). HK: 华泰证券,
  建设银行 and 工商银行 are at the score's 24th-32nd percentile, below the top fifth the evidence covers.
- **Fix.** One computed sentence per market under the Buy heading, naming the largest industry cluster. No method
  change: stage 16 answered the cluster as the sector-relative design.

### F9. Smaller
- **The first list mixes two methods.** The buffer kept 10 names rated by main's four-family score: CN buys 春风动力,
  德业股份, 柏楚电子 and 上港集团 (over 海康威视, 东航物流, 宇通客车, 天赐材料), HK's 工商银行, US Sell Vistra, 4 Holds.
  All inside their buffers; it washes out. A one-time line in the first report after the merge would explain why
  5-8 buys changed in a week.
- **"新进 7 只，移出 8 只" (US).** The list sent on 11-08 had 21 names. The counts read as an error.
- **A Sell card can cite price weakness** (Constellation: 近一年股价走弱) while page 1 says Sell ignores price moves:
  its risk line comes from all three families.
- **Nasdaq's sectors misplace some names.** Ciena is ranked among utilities (value 0.02), Lumentum among telecom
  carriers. Older than these stages.
- **Safety isn't sector-neutral.** Median failure rank among the US 400 largest: energy 0.06, technology 0.62. The
  cap of 2 a sector limits it.

## 3. The buffer, in short
- The code matches its description, the lists reproduce, and no kept name is outside its buffer or stale.
- It works for Buy. For Sell and Hold it is mostly void where the sector cap binds (F2).
- It can't make a daily list a 12-month rating by itself (F7).

## 4. The wording, in short
- The 预期 split is clear and honest: it tells the reader the picking itself subtracted in CN and the US.
- The Sell 预期 line is long but says the right three things.
- Misleading: the failure-risk line (F6), 明显掉出范围才换 (F7), the Carvana and Lumentum figures (F3).

## Not verified
- No fix is built or run on a week of snapshots; the "what it changes" lines come from one day.
- The 2026-11-15 lists are before the DeepSeek review (`run` doesn't call it).
- News comes from web search summaries, several from aggregators; figures were not checked against filings.
- Asness (1997) and the exclusions in Campbell, Hilscher and Szilagyi (2008) are from memory.

## Short report
- **Push and merge stages 16 and 17: yes, about 80% confident.** Better than main in every list; no regression.
- **Then one short stage, 17b:** HK Sell from large and mid caps (F1, changes 7 of 10 names); the buffer counted
  after the sector cap (F2); the failure-risk wording (F6); financial-sector leverage (F4, Ares out).
- **Systematic Sell false positives:** one-off items (F3: Lumentum, Carvana's figure), consolidated funds and
  insurers (F4: Ares, KKR, Apollo), strong-momentum names (F5). Boeing and Snowflake are not data faults.
- **Later:** a monthly review calendar for the ratings (F7) and a sentence on the buys' concentration (F8).
