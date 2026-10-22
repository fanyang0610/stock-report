# Backtest, calibration and signal tracking (Phase 9, 2026-10-18)

v1 and v2 were run point-in-time on every month end: CN 2019-01 to 2026-09 (93 dates), US 2018-01 to 2026-09
(105), HK 2016-10 to 2026-09 (120). Parameters were chosen on the in-sample dates (up to 2023-12) and checked on
the out-of-sample dates (2024-01 to 2026-09; 12-month returns exist for the first 21 of them). Code:
`backtest/` (outside the app); every table below can be rebuilt (see "Rerun"). Generated tables:
data/backtest/results.md.

## 1. Verdict

- **Switch rule (A4): not met with the size floor you chose; met without it.**
  - With buys limited to the largest companies (config now, section 13), v2 beats v1 on both the 12-month rank
    correlation and the buy − sell spread only in CN. In HK its buy − sell falls below v1's (+27.1% against
    +30.6%). Its 高 picks were right 55% of the time, its 低 picks 57% (only 7 picks).
  - Without the floor, v2 passed in CN and HK, not in the US (v1's rank correlation is higher). Its 高 picks were
    right 67% of the time (81), its 低 picks 33% (3).
  - **Your decision (2026-10-18): v1 keeps the report.** v2 stays in shadow mode with the size floor, and
    `track --signal` collects live evidence before the switch is revisited.
- **What it is a test of.** There is no free consensus history (section 2), so both methods ran without
  consensus: v1 without its forward lens and check 2, v2 on its ROE path. The US and HK universes are today's
  listings, and CN misses the companies delisted since (section 9).
- **How strong.** Every 12-month number has wide error bands (t-statistics mostly 0.5-2.5, for overlapping
  windows). v2's edge comes from its sells (CN −19% against the universe over 12 months, HK −12%) and from HK's
  rank correlation. In CN neither method ranked stocks usefully over 12 months after 2023: the rank correlation
  is about 0 for both (it was +0.13 for v2 and +0.08 for v1 in 2019-2023). At 1 and 3 months both stay positive.
- **Calibration changed five values** (config.toml `[v2]`, section 4). The biggest is how fast excess returns
  fade. In A-shares and HK, a company's ROE above the market's keeps only ~20% (CN) and ~10% (HK) of its lead after
  5-10 years. Even ROE jumps that held 3 years were gone by year 5-6 in CN. v2 had assumed most of it lasts.
- **Your three review questions (section 6).**
  - Momentum in the buy ranking helps in- and out-of-sample: it is now 0.5 sd next to v2's upside.
  - The industry-relative floor stays. A market-wide floor or no floor did no better in-sample and worse out of
    sample.
  - The steady/cyclical history split is the best-calibrated base-rate grouping in CN. 中际旭创 keeps the steady
    rate (12% today; such breaks kept 6% after 2023).
- **Checks 1-2 (section 7).** Check 1 stays: in CN and HK the names it removed trailed their replacements by 22
  and 8 points over 12 months; in the US it cost 16 points. Check 2 and the analyst split of check 1 could not be
  measured: no consensus history, and the 2026 window had no such case. Both stay, and `track --signal` now
  measures them on every snapshot.
- **News test (section 8).** Moves with news did not continue and moves without news did not reverse. News should
  label moves, not enter the score.
- **US review (section 12, after your question on the US buys).**
  - v2 is mostly a value screen. In the backtest its ranking correlates 0.65-0.84 with plain earnings yield. What
    it adds beyond plain earnings and book yield is not significant (out of sample: CN +0.018, US −0.063, HK
    −0.023), though its buckets beat plain-cheapness buckets in CN and HK.
  - Three biases are fixed: foreign listings now carry their country's premium; the US keeps a 10-year fade;
    the expected-return rule, which favoured short-duration stocks, is gone.
  - Today's US buys: Incyte, Merck, Ecopetrol, Target, ORIX. MSFT (+64%) and META (+60%) now qualify but rank
    lower on momentum; NVDA (+97%) and TSM (+67%) fail the momentum floor.
- **Size floor (section 13, your choice).** Buys now come only from the 300 largest companies (CN, US) or the 200
  largest (HK), and US buys only from US listings.
  - In-sample buy returns are about the same on average (CN +1.4, HK +5.3, US −6.8 points). Out of sample they
    fall in every market: CN −5.8, US −4.7, HK −6.8 points.
  - Today's buys are large, familiar names: Merck, Applied Materials, Schwab; 万华化学, 上港集团; 中信股份,
    中国太保.

## 2. Data, point-in-time

| | CN (main test) | US (secondary) | HK (secondary) |
|---|---|---|---|
| Dates | month ends 2019-01..2026-09 | 2018-01..2026-09 (A4 says 2016: the SEC table starts with FY2015, so growth exists from early 2017 and the universe has under 300 names until 2017-12; built from 2016-10, scored from 2018-01) | 2016-10..2026-09 |
| Prices, returns | Eastmoney valuation history daily (2018-01-02 on; its CHANGE_RATE is close ÷ ex-rights prev-close: identical to the 通达信 packages on all 197,636 overlapping rows), 通达信 daily packages from 2021-08-13 (the archive's first day) | Yahoo month-end total returns (current candidates) | Yahoo month-end total returns (current candidates) |
| Fundamentals | 业绩报表 every quarter since 2009, used after its NOTICE_DATE; balance sheets when that period's results were out | annual SEC/Yahoo reports after the filing date (no quarterly history: trailing = last fiscal year) | Eastmoney main indicators, public 90 days after the period (A4) |
| Universe | Eastmoney's stocks that day, listed ≥ 1 year, ¥50m turnover (通达信 period only), ST names out (通达信 names, 2021-08+), top 800 by market value: 738-800 a date | today's candidates with 2 annual reports, top 800: 314 (2018) to 733 | today's candidates, top 410 by market value (the HK$20m turnover screen needs volumes the monthly table lacks; ~410 pass it today): 337-394 |
| Industry | 申万 L2 of that day (change history) | today's Nasdaq industry | today's Eastmoney industry |
| Consensus | none, except 2026-01..09 (section 8) | none | none |
| Discount rate | ChinaBond 10-year history | FRED DGS10 | US 10-year − today's HK-US gap (no free HK history) |

What doesn't exist for free (probed 2026-10-18):
- **Consensus history.** The research-report archive labels its EPS fields relative to today: a 2019-2023 report
  shows no forecast and a 2024 report only FY2026. RPT_RES_PROFITPREDICT and RPT_WEB_RESPREDICT hold the current
  years only. The Tushare token has no API access.
- **CNINFO's whole history.** The market-wide announcement query stops after ~80 pages a day.

Downloads: ~2.8 GB of 通达信 packages, parsed in memory, never stored. data/backtest is 0.89 GB, so data/ + reports/
is 0.95 GB.

## 3. v1 vs v2 out of sample (2024-01..2026-09)

Rank correlation (IC) of the upside with later returns, mean over dates (t-statistic). Buckets: average return
of the 5 picks minus the equal-weight universe. Rows:
- v2: calibrated, config.toml now, including the US review;
- v2 (Phase 8): the first guesses;
- E/P and B/P: plain benchmarks that rank on earnings or book yield, buying the 5 cheapest (2 per industry) and
  selling the 5 dearest among the 400 largest.

| | IC 1m | IC 3m | IC 12m | buy 12m | sell 12m | buy − sell 12m | buy hit 12m | buy vs index 12m |
|---|---|---|---|---|---|---|---|---|
| **CN** v1 | +0.031 (1.2) | +0.040 (1.0) | −0.009 (−0.2) | −0.9% | +3.0% | −4.0% (−0.2) | 37% | +6.7% |
| CN v2 | +0.045 (1.0) | +0.075 (1.2) | −0.003 (0.0) | −7.8% | −19.2% | +11.4% (0.7) | 41% | −0.1% |
| CN v2 (no size floor) | +0.045 | +0.075 | −0.003 | −2.0% | −19.2% | +17.2% (1.3) | 48% | +5.7% |
| CN v2 (Phase 8) | +0.042 | +0.063 | −0.029 | −9.5% | −10.8% | +1.3% | 36% | −1.8% |
| CN E/P | +0.045 | +0.068 | −0.041 | −13.8% | −21.4% | +7.6% | 29% | −6.1% |
| CN B/P | +0.038 | +0.064 | −0.003 | −17.3% | +24.8% | −42.1% | 25% | −9.7% |
| **US** v1 | +0.018 (1.0) | +0.039 (1.7) | +0.076 (1.6) | +2.7% | +1.3% | +1.4% (0.1) | 50% | +5.8% |
| US v2 | +0.013 (0.6) | +0.036 (1.1) | +0.060 (1.0) | +0.4% | −9.0% | +9.3% (0.6) | 40% | +3.5% |
| US v2 (no size floor) | +0.013 | +0.036 | +0.060 | +5.1% | −9.0% | +14.1% (1.0) | 56% | +8.2% |
| US v2 (Phase 8) | +0.012 | +0.035 | +0.064 | +4.2% | −8.4% | +12.7% | 52% | +7.3% |
| US E/P | +0.023 | +0.049 | +0.075 | +14.1% | +13.4% | +0.7% | 66% | +17.2% |
| US B/P | +0.035 | +0.076 | +0.160 (2.5) | +21.2% | −8.4% | +29.6% (1.4) | 74% | +24.3% |
| **HK** v1 | +0.043 (2.4) | +0.067 (2.5) | +0.049 (1.5) | +8.5% | −22.1% | +30.6% (1.3) | 49% | +14.8% |
| HK v2 | +0.048 (2.1) | +0.087 (2.6) | +0.099 (2.5) | +15.3% | −11.8% | +27.1% (1.4) | 56% | +21.6% |
| HK v2 (no size floor) | +0.048 | +0.087 | +0.099 | +22.1% | −11.8% | +33.9% (1.7) | 59% | +28.4% |
| HK v2 (Phase 8) | +0.042 | +0.079 | +0.083 | +14.0% | −13.0% | +27.0% | 67% | +20.3% |
| HK E/P | +0.072 | +0.116 | +0.116 | −12.3% | −5.6% | −6.7% | 28% | −6.0% |
| HK B/P | +0.057 | +0.090 | +0.110 | −10.8% | −22.3% | +11.5% | 28% | −4.5% |

In-sample (for reference), IC 12m and buy − sell 12m:

| | v1 | v2 | E/P | B/P |
|---|---|---|---|---|
| CN | +0.084 / −4.4% | +0.135 / +4.7% (no floor +3.3%) | +0.087 / −10.5% | +0.152 / −4.5% |
| US | −0.003 / −3.4% | +0.056 / −1.7% (no floor +5.1%) | −0.039 / 0.0% | −0.027 / +17.1% |
| HK | +0.074 / +12.1% | +0.131 / +7.2% (no floor +1.9%) | +0.080 / −14.6% | +0.092 / −0.9% |

- **Ranking:** v2 ranks about as well as the better of plain earnings and book yield, not better.
- **Buckets:** in CN and HK, v2's (quality screen, confidence, momentum) beat plain cheapness in both samples.
  In the US, plain book yield's buckets were far better out of sample (+29.6% against +14.1%), though not in
  the ranking in-sample.
- **US caveat:** today's listings only (section 9), so it says little.

## 4. Calibration (config.toml `[v2]`)

All changes together (including the US review and the size floor), averaged over the three markets:

| | in-sample | out of sample |
|---|---|---|
| IC 12m | +0.094 → +0.107 | +0.039 → +0.052 |
| buy 12m | 3.4% → 2.7% | 2.9% → 2.6% (8.4% without the floor) |
| buy − sell 12m | 5.2% → 3.4% | 13.7% → 15.9% (21.7% without the floor) |

v1: IC +0.052 in-sample / +0.039 out of sample, buy − sell 1.4% / 9.4%.

Return grids re-ran v2 with one value changed at a time; the score is the in-sample 12-month IC averaged over
the three markets (buy-bucket return for the momentum settings). A value replaces the Phase 8 guess only if it
gains at least 0.005 IC (or 1 point of buy return) in-sample; it should then not lose out of sample. The panel
studies use the yearly history (CN 2009-2025 from the backtest tables, US and HK 2015-2025). Section 5 has
their numbers.

| Parameter | Phase 8 | In-sample evidence | Chosen | Out of sample |
|---|---|---|---|---|
| φ (long-run share of excess ROE) | 0.15 + 0.45 × stability + 0.2 × margin, all markets | Panel: the share of a normal excess ROE still there after k years is CN 0.70, 0.54, 0.44, 0.37, 0.31, 0.24, 0.21, 0.18 (k = 1-8) and flat across stability and margin; HK 0.54, 0.34, 0.26 (k = 1-3); US 0.90, 0.78, 0.77. Returns: lower φ +0.002 IC (CN, HK prefer it; the US prefers the formula) | CN, HK: flat 0.2; US: unchanged | flat 0.2 everywhere: +0.025 IC |
| Fade years (after year 3) | 10 | Returns: 3 years +0.006 IC (CN +0.008, HK +0.011, US −0.002), in the joint run with the other choices; CN's panel curve is near its floor within ~6 years. Per market (US review): the US in-sample prefers 10 (0.056 vs 0.053) | CN, HK 3; US 10 | CN, HK +0.002 IC each |
| Country premium (US: foreign listings) | none | Foreign listings: 22% of the US universe, 33% of v2's US buys; those lost 7.3% (79) in-sample and 4.8% (35) out of sample against +3.7% / +7.0% for US buys. The country's median implied return over home listings' (5+ listings, the rest pooled), weight 0 / 0.5 / 1: buy 12m in-sample −0.0% / −0.8% / −0.9% | 1 (your choice; no in-sample gain) | buy 12m +4.3% / +6.4% / +5.1%; foreign buys −5.2% → +0.4%, their share 28% → 23% |
| Expected return ≥ required ± 2 points for buys and sells | on | The same 20-60% upside is ~2.4 points a year on a low P/B and ~1.1 on a high P/B: the rule favours short duration (MSFT +37% and META +32% failed it). Off: US buy 12m in-sample +1.7% → −0.9%, CN 5.1% → 4.9%, HK unchanged | off (your choice; no in-sample gain) | US buy 12m 5.9% → 5.1%, CN −1.3% → −2.0% |
| Persistence floor under a new regime (PHI_NEW) | 0.5 | Panel, breaks that kept half their jump after 3 years, share of the new excess left after k years: CN in-sample 0.49 / 0.08 / −0.01 / 0.06 (k = 4-7), HK 0.36 at k = 4, US 1.08 at k = 4 (today's listings only) | CN 0.05, HK 0.1, US 0.5 | CN 0.58 / 0.20 / 0.06 / −0.05; HK 0.20 / 0.11 / 0.25; US 0.92 / 0.86 / 0.89 / 0.94 |
| Own last boom (log-odds) | ±0.5 | Panel: coefficient ~0 in every market; out-of-sample log loss = the base rate's | 0 | — |
| Buys only from the largest companies (CN, US 300; HK 200), US buys from US listings | none | Section 13. Buy 12m in-sample about the same (CN +1.4, HK +5.3, US −6.8 points) | on (your choice) | buy 12m lower in every market (CN −5.8, US −4.7, HK −6.8 points) |
| Momentum weight in the buy ranking | 0 | Buy return 12m: 0 → 3.4%, 0.25 → 4.8%, 0.5 → 5.7%, 1.0 → 5.3% | 0.5 | 2.9% → 5.8% |
| λ (industry premium) | 0.5 | 0: +0.001 IC; 1.0: −0.002 | 0.5 (no gain) | 0 would have been +0.011 |
| Discount rate | implied | configured −0.032 IC (US −0.045, HK −0.046) | implied (your default) | configured would have been +0.013 |
| Anchor weights | intrinsic/peer/own 0.6/0.3/0.1, cyclical 0.5/0.1/0.4 | intrinsic only ±0.000; more peer −0.006; more own −0.005; equal −0.007 | unchanged | intrinsic only +0.002 |
| History weight and cycle rules | (1.0, 0, 0.3, 0.6), band 0.3-0.7 | Panel: halving the cycle factors forecasts the next 3 years' ROE better (MAE 8.40 vs 8.59 points pooled; 10.11 vs 10.33 out of sample); returns: −0.011 IC | unchanged (the value's job is ranking) | — |
| Consensus haircut | 10/25/50% | not testable (no consensus history) | unchanged | — |
| Momentum floor | industry z ≥ −0.5 | section 6 | unchanged | — |
| Base-rate grouping | steady / cyclical | section 6 | unchanged | — |

Confidence and the 12-month expectation (A2.5), out of sample:

| | 高 | 中 | 低 |
|---|---|---|---|
| Buy and sell picks right (12 months), all markets | 55% (107 picks; 67% of 81 without the size floor) | 62% (516) | 57% (7) |
| Any valued stock: sign of the upside right (CN / US / HK) | 51% / 55% / 57% | 53% / 57% / 51% | 55% / 56% / 52% |
| β, share of the log gap closed in 12 months (CN / US / HK) | +0.14 / −0.01 / +0.19 | +0.09 / +0.10 / +0.16 | −0.01 / +0.01 / +0.01 |

β is small: a +50% upside has meant about +4% over the universe in the next 12 months (CN, HK 高/中), and ~0 at
低. β by archetype, out of sample: financials +0.09-0.10 in every market; steady −0.02 to +0.03; growth −0.05 to
+0.04. Before Phase 10 prints a 12-month expectation, it should use β by band and market. Confidence orders β
in CN and HK, but not the hit rate of the sign, and not in the US.

## 5. Panel studies

**Regime base rates** (up-breaks; "kept" = at least half of the ROE jump 3 years later). Base rates fell sharply
after 2023: CN 24% in-sample → 10% out of sample, US 64% → 38%, HK 18% → 20%. Every model overpredicts out of
sample (CN predicted 23%, realized 10%). Production measures the base rates on every run from all known
outcomes, so they follow such drift. Out-of-sample log loss (lower is better):

| Grouping | CN | US | HK |
|---|---|---|---|
| all episodes | 0.389 | 0.807 | 0.499 |
| steady / cyclical (v2) | **0.373** | 0.821 | 0.500 |
| any loss in 5 years | 0.381 | 0.811 | **0.496** |
| 2+ revenue down years | 0.385 | **0.802** | 0.498 |
| new ROE ≥ 35% | 0.378 | 0.808 | 0.503 |
| logistic on all evidence | 0.354 | 0.943 | 0.482 |

Evidence one at a time (in-sample logistic, out-of-sample log loss against the base rate):
- **CN:** cyclical history helps (0.373 vs 0.389), then the level of the new ROE (higher lasts less, 0.377) and
  ROE volatility (0.383).
- **US:** nothing helps.
- **HK:** revenue acceleration and ROE volatility help marginally.
- **The stock's own earlier episode:** no power anywhere, hence weight 0.
- **Untested:** consensus durability, revisions, 业绩预告 type and the capex gauge, which need consensus or have
  under 10 yearly observations. They keep their first-guess weights.

The full logistic model is better calibrated in CN and HK but worse in the US. It isn't adopted: its gain in
CN rests on two collinear terms (jump size and new level).

**Normal ROE** as a forecast of the next 3 years' average ROE, mean absolute error in points (CN, in / out of
sample): today's ROE 7.65 / 8.07, 10-year mean 10.18 / 11.45, v2's normal 7.62 / 7.98. Normalization beats
both benchmarks, but only narrowly against today's ROE.

## 6. Your review questions (2026-10-18)

**Momentum in the buy ranking** (v2's buys ranked by confidence-weighted upside + w × momentum z; buy return
over the universe at 12 months / share beating it):

| w (industry floor) | CN in | US in | HK in | CN out | US out | HK out |
|---|---|---|---|---|---|---|
| 0 (Phase 8) | +3.9% / 57% | +1.3% / 47% | +4.9% / 50% | −9.5% / 36% | +4.2% / 52% | +14.0% / 67% |
| 0.25 | +7.2% / 62% | +1.0% / 47% | +6.3% / 56% | −9.2% / 38% | +7.1% / 55% | +12.1% / 66% |
| **0.5 (chosen)** | +6.1% / 60% | +1.8% / 48% | +9.2% / 58% | −7.1% / 39% | +4.4% / 53% | +20.0% / 66% |
| 1.0 | +7.3% / 61% | +2.3% / 51% | +6.3% / 57% | −7.8% / 38% | +5.6% / 53% | +29.6% / 67% |

Consensus revisions in the ranking can't be tested historically. In the 2026 window (section 8), the 1-month
FY2027 revision had a 1-month IC of +0.057 (t 1.0, 8 dates).

**The momentum floor** (w = 0 / w = 0.5; buy return 12m averaged over the markets):

| Floor | in, w 0 | out, w 0 | in, w 0.5 | out, w 0.5 |
|---|---|---|---|---|
| industry-relative z ≥ −0.5 (v2) | 3.4% | 2.9% | **5.7%** | 5.8% |
| whole market z ≥ −0.5 | 4.2% | 2.1% | 4.2% | 4.4% |
| no floor | 4.2% | −0.2% | 3.2% | 5.0% |

At w = 0 the market floor and no floor gain 0.8 points in-sample (under the 1-point bar) and lose out of sample.
With momentum in the ranking, the industry floor is best in-sample. NVDA stays out of the buys: its momentum is
still below its industry's.

**The base-rate history group for 中际旭创.** In CN the steady/cyclical split is the best-calibrated simple
grouping out of sample (table above):
- In-sample steady-history breaks kept 19%, cyclical-history ones 32%.
- After 2023 steady-history breaks kept 6% and cyclical ones 19%.
- Pooling all episodes ("all", 17% today) or splitting on losses is worse.

So 中际旭创 keeps the steady base rate, 12% from today's whole panel.

## 7. Checks 1-2 (v1)

Names the checks removed from v1's buy and hold picks, against the names that took their places. Return over the
universe; n = name-dates.

| | 1 month | 3 months | 12 months |
|---|---|---|---|
| CN excluded / replacements | +2.1% / −1.8% (50) | −0.4% / +2.4% (45) | **−20.7% / +1.3% (42)** |
| US | −0.8% / −0.2% (42) | −2.6% / −0.5% (42) | +6.7% / −9.2% (38) |
| HK | −1.0% / +1.0% (99) | −2.3% / +4.0% (99) | **−0.7% / +7.0% (96)** |

- **Check 1 stays.** Every exclusion above is check 1's, because check 2 needs consensus. Check 1 avoided 22 points
  of underperformance in CN and 8 in HK over 12 months, and cost 16 in the US (38 name-dates). v2 ignores the
  checks: its normal earnings are its answer.
- **Check 1 split by analysts: not measurable.** No consensus history. In the 2026 window the 10 names check 1
  removed (江波龙, 德明利, 佰维存储, ...) had fewer than 3 brokers in the archive, or brokers expecting next year's
  EPS below the last 12 months.
- **Check 2 stays as it is.** It never changed a pick: in the 2026 window it flagged 0-3 candidates a month, none
  in the top 5. It agrees with v2's own logic (earnings analysts expect to fall back aren't normal earnings).
- **Live tracking.** `track --signal` now recomputes v1's picks with and without the checks on every saved
  snapshot. It reports the excluded names against the replacements, and splits check 1 by "3+ analysts expect
  next year's EPS ≥ the last 12 months". The answer builds from today's snapshots on.

## 8. News test, revisions and the 2026 consensus window (CN)

**News test (A2.8).**
- Sample: 2,400 one-day moves beyond 2.5 standard deviations against the CSI 300, top-800 stocks, 2021-08 to
  2026-07, half up and half down.
- "With news": an announcement on CNINFO the day before or the day of the move that names results, a forecast,
  a contract or award, M&A, a buyback, holder buying or selling, a placement, an investigation, an inquiry
  letter, a dividend, a project or capacity. The company's own "abnormal trading" notice doesn't count. 630 moves
  had news, 1,770 didn't.
- Results: return after the move in its direction, over the CSI 300 (t):

| | 5 days | 20 days | 60 days |
|---|---|---|---|
| in-sample, up with news (135) | −0.6% (−1.2) | −1.9% (−2.1) | −3.2% (−2.2) |
| in-sample, up without news (398) | +0.3% (0.8) | +0.2% (0.3) | +0.1% (0.1) |
| in-sample, down with news (182) | +0.8% (1.7) | −0.1% | −0.9% |
| in-sample, down without news (357) | −0.2% | −0.8% (−1.4) | −0.8% |
| out of sample, up with news (125) | −0.5% | −0.7% | +2.4% (1.5) |
| out of sample, up without news (542) | +1.3% (3.4) | +1.8% (2.6) | +2.5% (2.5) |
| out of sample, down with news (188) | 0.0% | −0.5% | +1.0% |
| out of sample, down without news (473) | +0.1% | −0.3% | −1.8% (−2.1) |

- Verdict: the A2.8 pattern doesn't hold. In-sample, up-moves with news reversed. After 2023, up-moves without
  news continued and down-moves without news bounced. So attribution doesn't enter the score. Phase 11's event
  layer should label moves (with or without a matching event) and leave values alone.

**2026 consensus window.** Point-in-time consensus for 2026-01..09: per stock, the median of each broker's newest
report in the trailing 120 days. Years 1-3 are FY2026-28; FY2025 forecasts are gone from the archive, so year 1
is blank before a stock's FY2025 report. About 185 stocks a month had 3+ brokers in two consecutive months.
- Rank IC, 1 month / 3 months: v1 +0.017 / +0.067, v2 +0.048 / +0.185 (6-8 dates, t ≤ 1); FY2027 revision over
  the month +0.057 (t 1.0) / +0.037. Too short to calibrate anything.
- Weekly consensus snapshots (Phase 7) give live revisions from 2026-11-15; `track --signal` scores them as they
  come.

## 9. Limits

- **No consensus history.** The switch rule was evaluated on the no-forecast versions of v1 and v2. The
  forecast-dependent pieces weren't tested before 2026, and the 2026 window is too short to test them:
  - v1: the forward lens and check 2;
  - v2: consensus years 1-3 and their haircut, analyst confirmation of regime breaks, revisions in the ranking.

  They go to `track --signal` on the live snapshots (section 11). Confidence is mostly 低 in the backtest (53-63%
  of stocks; production 29-36%).
- **Survivorship.**
  - CN: Eastmoney's tables drop delisted companies (乐视网 and 康得新 are missing from 2019 rows). In the
    通达信 period, 0-170 A-shares traded on a month end (70 on average) are missing from Eastmoney's table that
    day: 0.9% of the market's turnover on average, at most 2.6%. They can't be valued (no fundamentals). The
    same gap before 2021-08 can't be seen.
  - US and HK: today's listings only, which overstates persistence and base rates (US breaks kept ~90% of their
    new excess).
- **US** has annual numbers only (growth = fiscal year on year), and the universe is thin before 2018.
- **HK** fundamentals are lagged 3 months. The universe is the top 410 by market value: 307 of today's 407
  production names are in it.
- **No turnover screen or ST data before 2021-08** (CN). Industries for US/HK are today's.
- **Overlapping 12-month windows.** The t-statistics count n ÷ 12 independent observations. In-sample 12-month
  returns of 2023 dates run into 2024.
- **A4's sector premium from each sector's own historical implied return wasn't run.** λ from 0 to 1 moved the
  IC by at most 0.003, so the industry premium barely matters for ranking.

## 10. Today's v2 lists after calibration (2026-10-18 snapshot, `v2 --date 2026-10-18`)

| | Phase 8 | Phase 9 (with the US review) |
|---|---|---|
| NVDA | +74% 中 (p 54%) | +97% 中 (p 66%: the own-boom penalty is gone); fails the momentum floor |
| MU | +71% 低 | +103% 低 (p 33% → 45%; US floor 0.5) |
| TSM | +67% 高 | +67% 高; fails the momentum floor |
| MSFT / META | +37% 高 / +32% 高, failed the expected-return rule | +64% 高 / +60% 中, buy candidates ranked 22nd and 30th |
| 中际旭创 | −20% 中 | −56% 低 (V_new 1,741 → 731: CN breaks fade; p 22%) |
| 江波龙 / 佰维存储 | −29% / +133% | −39% / +10% |
| Toyota / CTSH / OMC | +44% 高 / +68% 高 buy / +129% 低 | +36% (Japan's premium) / +67% / +129% 低 |
| AAPL / 贵州茅台 / 腾讯 | −27% / −18% / +24% | −27% / −34% / −5% (lower φ: CN/HK franchises are worth less) |

Buys with the size floor (section 13); holds and sells are unchanged by it:
- **CN:** 招商证券, 保利发展, 上港集团, 万华化学, 中信特钢.
- **US:** Merck, Target, Charles Schwab, Applied Materials, Cummins.
- **HK:** 中国太平, 中银航空租赁, 中国海外发展, 中信股份, 中国太保.

Before the floor:
- **CN:** 天华新能, 九安医疗, 招商证券, 青岛银行, 财通证券.
- **US:** Incyte, Merck, Ecopetrol, Target, ORIX.
- **HK:** 中国太平, 中银航空租赁, 中国民航信息网络, 碧桂园服务, 德翔海运.

The CN market-implied return fell from 7.7% to 6.1%: with less persistence the same prices imply a lower return.

## 11. Signal tracking and rerun

`uv run python -m stockreport track --signal` scores every saved snapshot with v2 columns, using the same code
as the backtest (stockreport/signal.py):
- v1's and v2's rank IC at 1, 3 and 12 months;
- the buckets against the equal-weight snapshot universe and the index;
- v2 buys by confidence;
- checks 1-2, excluded against replacements, with the analyst split;
- the forecast-dependent pieces the backtest couldn't test: v2's rank correlation among stocks with 3+
  analysts, with the haircut (history weight ≥ 0.5) and without it; analyst-confirmed regime breaks we call
  cheap against those we call dear; the rank correlation of the 4-week consensus revision (from 2026-11-15),
  the evidence for putting revisions in the buy ranking.

It is blank until the first snapshot (2026-10-18) is a month old.

Rerun (≈1.5 h; data/backtest ≈ 0.7 GB):

```
uv run python -m backtest.fetch sw eastmoney tdx reports   # point-in-time CN tables
uv run python -m backtest.run build cn|us|hk               # snapshots, v1, v2 inputs per month end
uv run python -m backtest.calibrate grid|grid2|grid3|grid4 cn|us|hk
uv run python -m backtest.panels_run cn|us|hk              # regime, persistence, normal-ROE panels
uv run python -m backtest.news sample                      # CNINFO, ~50 min
uv run python -m backtest.calibrate compare                # v1 vs v2 (Phase 8 and config.toml)
uv run python -m backtest.report                           # data/backtest/results.md
```

## 12. US review (2026-10-18, after your question on the US buys)

You asked why the US buys were small or foreign names (CPAY, ORIX, Ecopetrol, CTSH, Franklin), with no large
compounders and no AI leaders.

**What v2 is.** Today's US upside rank-correlates with earnings yield 0.49 and book yield 0.41, with ROE 0.02,
momentum −0.22 and size −0.09. In the backtest, without consensus, the correlation with earnings yield is
0.65-0.84 a date. What v2 ranks beyond plain earnings and book yield:

| | CN | US | HK |
|---|---|---|---|
| in-sample | +0.027 (0.7) | +0.045 (2.5) | −0.028 (−0.8) |
| out of sample | +0.018 (0.9) | −0.063 (−1.7) | −0.023 (−0.3) |

The valuation machinery has not shown an edge over plain cheapness. v2's buckets add value in CN and HK
(section 3).

**Biases found and changed:**

| Bias | Evidence | Change |
|---|---|---|
| Foreign listings valued at the US rate | 22% of the US universe, 33% of v2's US buys; those trailed US buys by 11 points in-sample and 12 out of sample | Country premium (config `country_lambda` = 1): the listing country's median implied return over home listings', for countries with 5+ valued listings; the rest pooled. Today: Japan +0.7 points, UK and Ireland +1.1, China +1.9, Brazil +2.5, Canada −0.9, the pool (Colombia, Mexico, Taiwan, ...) +1.1. Ecopetrol's +1.1 is small for Colombian risk; such names would need an external per-country risk premium. |
| Expected return ≥ required + 2 points | The same 20-60% upside is ~2.4 points a year on a low P/B, ~1.1 on a high P/B. MSFT and META failed it at +37% / +32%. | Removed, for buys and sells; the upside thresholds (+20% / −25%) are the margin. |
| A 3-year fade chosen on CN and HK | It cut MSFT +64% → +37%, NVDA +97% → +42%, META +60% → +32%. The US in-sample preferred 10 years. | Fade per market: CN, HK 3; US 10. |

**Effect in the US backtest:**

| | in-sample | out of sample |
|---|---|---|
| IC 12m | 0.054 → 0.056 | 0.067 → 0.060 |
| buy 12m | +0.7% → −0.9% | +3.1% → +5.1% |
| buy − sell 12m | 6.8% → 5.1% | 11.4% → 14.1% |
| foreign buys' share (no country premium → premium) | 22% → 18% | 28% → 23% |

The two rule changes you chose don't pay in-sample, and do out of sample. Neither moved the US switch result:
v1's IC is still higher (0.076).

**Not changed, and why:**
- **Asset-light compounders with small books** (AAPL P/B 45, MA 45, LLY 35, COST 12) stay 27-67% below price
  under any fade. A residual-income value starts from book value, and buybacks shrink it. Growth is capped at
  15% fading to 4%, and the prices imply 120-300% ROE for 10 years. This is a limit of book-based valuation.
  Their confidence is usually 低, and a sell needs deterioration, so v2 rarely sells them (WMT is a sell on its
  net-margin screen).
- **NVDA (+97%), TSM (+67%), UNH and AVGO** fail the industry-relative momentum floor (section 6).
- **The ranking is size-neutral.** The largest companies sit closest to v2's value, and momentum now counts
  in the ranking. So MSFT (+64% 高) ranks 22nd of 72 buy candidates and META 30th, behind names with larger
  upside or stronger momentum.

**Today's US lists:**
- **Buy:** Incyte +70% 中, Merck +52% 高, Ecopetrol +54% 中, Target +26% 高, ORIX +27% 高.
- **Hold:** Allstate, Progressive, Itaú, Viper Energy, Amer Sports.
- **Sell:** Salesforce, RTX, Welltower, Ericsson, Phillips 66.

**What the US test can't settle.** The universe is today's survivors: small stocks beat large ones with an IC
of +0.14, t 3.4, a look-ahead effect. The data is annual and has no consensus. Plain book yield did best out
of sample. So the backtest can't say whether v2's skepticism about the US compounders is right. Holding the
market's compounders and AI leaders would be a quality/growth objective, not a parameter of this engine.

## 13. Size floor (2026-10-18, your choice)

Buys now come only from the 300 largest companies in CN and the US and the 200 largest in HK (config
`buy_largest_n`), and US buys only from US listings (`buy_home_only`). Holds and sells are unchanged. The
valuation is unchanged too; the rule only decides where buys may come from. Before, 13 of 15 buys sat outside
their market's 100 largest. The ranking took the biggest estimated gaps, and those come most often from smaller,
thinly covered companies whose estimates are noisiest (section 12).

**Backtest, buy return over the universe at 12 months (share beating it):**

| | CN | US | HK |
|---|---|---|---|
| in-sample, no floor | +4.9% (62%) | −0.9% (46%) | +4.1% (57%) |
| in-sample, floor | +6.3% (62%) | −7.7% (36%) | +9.4% (66%) |
| out of sample, no floor | −2.0% (48%) | +5.1% (56%) | +22.1% (59%) |
| out of sample, floor | −7.8% (41%) | +0.4% (40%) | +15.3% (56%) |

- In-sample the floor helps CN and HK. It hurts the US, whose test universe (today's listings) flatters smaller
  companies.
- Out of sample it costs buy return in every market. The switch rule now passes only in CN (section 1).
- So the floor buys comprehensibility at a measured cost after 2023, not a return edge. Large companies weren't
  safer in the backtest either: the 100 largest lagged the market by 20+ points over 12 months 29-45% of the
  time, like any stock.

**Today's buys** (upside, confidence, rank by market value):

| | |
|---|---|
| CN | 招商证券 +24% 高 #100; 保利发展 +115% 中 #250; 上港集团 +57% 高 #120; 万华化学 +43% 高 #62; 中信特钢 +44% 高 #248 |
| US | Merck +52% 高 #31; Target +26% 高 #240; Charles Schwab +62% 中 #99; Applied Materials +59% 高 #36; Cummins +69% 高 #235 |
| HK | 中国太平 +33% 高 #151; 中银航空租赁 +72% 高 #188; 中国海外发展 +58% 高 #79; 中信股份 +68% 高 #35; 中国太保 +42% 高 #45 |

Two of them are developers (保利发展, 中国海外发展). v2 sees cheap books and steady history there; the market
prices China property risk that v2's data can't see.

MSFT (+64%) and META (+60%) are within the floor but still rank behind these on upside plus momentum. NVDA
(+97%) and TSM (+67%) still fail the momentum floor.

## 14. Valuation v3 (Phase 13, 2026-10-20; backtest/v3.py)

v3 without consensus (the company's own trend) on the same cached month-end snapshots as v1 (section 2), with
base rates from the history public on each date: CN 申万 level 1 on the annual results since 2009, US SEC frames
since CY2009 (every filer, dead companies included), HK the Eastmoney history since 2015 (survivors). The first
HK dates (2016-10..2018) have too little history for base rates and get no values. v1 here reproduces section 3
exactly. Phase 9's v2 scripts (calibrate.py, studies.py, panels_run.py, report.py) were removed with v2; git
history has them.

**Calibration** (in-sample, a value replaces the default only for ≥ 0.005 more 12-month rank correlation, as in
Phase 9; one at a time, then jointly for the US). Default: 5-year fade, 10% tolerance, long-run ROE = the
largest third's median.

| Parameter | CN in-sample IC 12m | US | HK | Chosen |
|---|---|---|---|---|
| fade years 3 / 5 / 10 / 15 | **0.128** / 0.121 / 0.105 / 0.091 | 0.018 / 0.022 / 0.031 / **0.039** | **0.123** / 0.118 / 0.106 / 0.096 | CN 3, HK 3, US 15 |
| tolerance 0 / 10% / 25% | 0.122 / 0.121 / 0.116 | 0.015 / 0.022 / **0.036** | 0.120 / 0.118 / 0.113 | US 25%, else 10% |
| long-run ROE market / r | 0.121 / 0.110 | 0.022 / **0.038** | 0.118 / 0.118 | US r, else market |
| HK haircut 0 / 10 / 20 / 30% | | | 0.118 / 0.119 / 0.119 / 0.120 | 0 (no value clears the bar) |

US jointly: fade 15 0.039; + tolerance 25% 0.048; + long-run ROE r 0.048; all three **0.052** (chosen; out of sample
0.074, buy − sell −56.1%, against 0.120 and −2.9% for the default). The US in-sample correlations are weak
(t < 1), so this choice mostly follows noise.

**v1 vs v3 vs the plain benchmarks**, 12 months (rank IC, t; buckets vs the equal-weight universe):

| | in IC | out IC (t) | out buy | out sell | out buy − sell |
|---|---|---|---|---|---|
| CN v1 | +0.084 | −0.009 (−0.2) | −0.9% | +3.0% | −4.0% |
| CN v3 | +0.128 | −0.040 (−0.5) | −9.8% | +2.0% | −11.8% |
| CN E/P / B/P | +0.087 / +0.152 | −0.041 / −0.003 | | | +7.6% / −42.1% |
| US v1 | −0.003 | +0.076 (1.6) | +2.7% | +1.3% | +1.4% |
| US v3 | +0.052 | +0.074 (1.7) | +8.7% | +64.8% | −56.1% |
| US E/P / B/P | −0.039 / −0.027 | +0.075 / +0.160 | | | +0.7% / +29.6% |
| HK v1 | +0.074 | +0.049 (1.5) | +8.5% | −22.1% | +30.6% |
| HK v3 | +0.123 | +0.141 (2.1) | +2.0% | +4.9% | −2.9% |
| HK E/P / B/P | +0.080 / +0.092 | +0.116 / +0.110 | | | −6.7% / +11.5% |

- **Done-when (1) is not met.** v3 beats v1 on rank correlation out of sample only in HK (US a tie), on buy − sell
  in no market, and the better of plain E/P and B/P only in HK. It stays in shadow.
- **Ranking vs buckets.** v3's ranking is competitive (HK best of all four; in-sample better than v1 everywhere),
  but its buckets lose: with one discount rate per market, the largest upsides are low-P/B financials and state
  companies, the largest downsides high-P/B growth names, and after 2023 the growth names kept rising (US sells
  +65% over the universe). v3's upside ranks stocks almost exactly as the return the price implies at base-rate
  earnings does (rank correlation 0.97-0.98 on 2026-10-19), and by industry that implied return runs from ~4.5-6%
  (software, semiconductors, staples) to 11-17% (banks, insurers, construction) against one rate per market (CN
  5.0%, US 6.8%, HK 7.6%).
**Industry risk premium (your call, 2026-10-20).** One rate per market turned each industry's pricing into
upside (above). Each stock's rate = the market's + λ × its industry's premium (the median rate its stocks' prices
imply at base-rate earnings, over the market's; 5+ stocks, else the parent sector's; −3..+6 points), measured
within each market. In-sample (other values as chosen above), rank IC 12m / buy − sell 12m:

| λ | CN | US | HK |
|---|---|---|---|
| 0 | 0.128 / +2.8% | 0.052 / −12.1% | 0.123 / +3.1% |
| 0.25 | 0.129 / +7.3% | 0.051 / −10.6% | 0.124 / +1.9% |
| 0.5 | 0.134 / +4.1% | **0.052 / −9.0%** | **0.123 / +7.8%** |
| 0.75 | **0.135 / +4.1%** | 0.051 / −14.5% | 0.118 / +13.6% |
| 1.0 | 0.134 / +3.7% | 0.050 / −13.8% | 0.105 / +15.6% |

Rule (λ targets the levels and the lists, so the bucket spread decides): the best in-sample buy − sell among the λ
whose in-sample rank correlation is within 0.005 of the best: CN 0.75, HK 0.5, US 0.5. US foreign listings also
carry half their country's premium (Phase 9's country premium; in-sample IC 0.052 → 0.060 at 0.5, 0.058 at 1; with
the country field the backtest's US buys are US listings only, as configured).

**v3 with the premiums, out of sample, 12 months** (v1, E/P and B/P as above):

| | IC (t) | buy | sell | buy − sell (t) |
|---|---|---|---|---|
| CN v3 | +0.016 (0.3) | −5.3% | −16.8% | +11.4% (1.1) |
| US v3 | +0.032 (0.9) | +3.4% | +50.6% | −47.2% (−0.9) |
| HK v3 | +0.120 (2.4) | +9.2% | −13.0% | +22.2% (2.0) |

- **Item (1):** CN meets it (beats v1 on both, and E/P and B/P); HK beats v1 and E/P on rank correlation but trails
  v1's buy − sell (+22.2% against +30.6%); the US fails. The better of E/P and B/P is beaten in two of three (CN, HK).
- **The US sells:** the median US sell trailed the universe (−5%), but Micron was a sell on 11 of the 21 dates
  and rose ~450% over the universe within 12 months each time (the 2024-26 memory boom); Corning +174% (7 dates).
  Without Micron US buy − sell is −1.6%, without both +15.3%. The US in-sample correlations are weak (t < 1), and
  the US out-of-sample rank correlation is lower with every in-sample choice than with the defaults (0.120).

- Rerun (~6 min; ~25 min for the grids): `uv run python -m backtest.v3 compare` (data/backtest/v3_results.md) and
  `uv run python -m backtest.v3 grid|lambda|country cn|us|hk` (data/backtest/v3_<grid>_<market>.csv), on the snapshots built by
  `uv run python -m backtest.run build cn|us|hk`.

## 15. Trend first (Phase 13, 2026-10-20; trend.py, outliers.py, backtest/v3.py)

Your call (2026-10-20): read the business trend first, then let valuation ask whether the price already reflects
it, measured separately per market, and tested in- and out of sample before adopting anything. Every number
below is on the same frames as section 14 (v3 without consensus, the industry premium as chosen), so v3's values
and rank correlations are unchanged; what changes is the lists. Rule for adopting: Phase 9's bar in-sample (+0.005
rank correlation, or +1 point of 12-month buy − sell) and then not losing out of sample.

**The evidence** (trend.py, point-in-time): votes of +1 / −1 outside a dead band for revenue growth acceleration
(latest fiscal year over the mean of the two before, ±5 points), profit growth acceleration (growth as the change
over the mean absolute level, ±20 points), the ROE trend (latest over years 2-3 before, ±2 points), 12-1 month
momentum over the market's median (±10 points) and the 4-week consensus revision (±2%, live only). Class: improving
at a vote sum ≥ 2, deteriorating ≤ −2 (≥ 1 / ≤ −1 with price votes only).

**1. Do improving companies keep their growth and ROE longer?** No. On every start public today (the base-rate
panels, business votes only; `persistence`, data/backtest/v3_persistence.md):

| | starts (imp / stable / det) | kept 5% a year, 5 years: imp / stable / det | median years at 10%: imp / det | ROE change in 3 years: imp / det |
|---|---|---|---|---|
| CN | 8,246 / 38,201 / 15,644 | 36% / 44% / 34% | 1.7 / 1.0 | −5.9 / −2.9 points |
| US | 5,949 / 23,595 / 5,241 | 37% / 47% / 48% | 1.6 / 3.2 | −6.2 / +0.2 points |
| HK | 2,464 / 10,946 / 3,242 | 25% / 29% / 23% | 0.9 / 0.9 | −7.4 / −4.4 points |

Within the same growth × ROE cell, improvers kept 5% growth for 3 years as often as deteriorators in CN (+0.00),
less often in the US (−0.15) and HK (−0.07). A year that just accelerated is usually a high base: profit and
ROE revert. Splitting the base-rate cells by this band (in place of size) lowered the in-sample rank correlation
(CN 0.131 vs 0.135, US 0.060 vs 0.060, HK 0.119 vs 0.123; out of sample 0.014 / 0.030 / 0.134 vs 0.016 / 0.032 /
0.120), so it was not adopted and was removed from the app after the test (commit 2e1c2a9 has it).

**2. Your thesis, cell by cell** (12-month return over the universe, in % per date; cheap = v3 upside ≥ 20%,
expensive ≤ −25%; data/backtest/v3_map_cells_<market>.csv):

| | price trend: expensive, rising / falling | cheap, rising / falling | business trend: cheap, improving / deteriorating |
|---|---|---|---|
| CN in / out | +1.2 / −3.4 · +9.4 / −2.4 | +3.5 / +0.2 · −5.4 / −3.1 | −2.2 / +7.1 · +4.6 / −3.9 |
| US in / out | −0.9 / −2.4 · +5.1 / +0.1 | −3.1 / +4.0 · −1.7 / −1.8 | −1.4 / +1.8 · +1.6 / −2.0 |
| HK in / out | +2.0 / −6.1 · +3.1 / +0.1 | +6.9 / −2.9 · −0.2 / +1.1 | +4.5 / −3.3 · +3.9 / −1.6 |

- "Expensive but rising: don't sell" holds in all three markets in both samples.
- "Cheap but deteriorating is a value trap" holds in HK in both samples; in CN and the US it reversed in-sample
  (cheap and deteriorating did better: CN +7.1% against −2.2%), and held out of sample (2024-26, the AI boom).

**3. The trend × valuation map** (shadow.buckets; `map`, data/backtest/v3_map_<market>.csv). Buy: improving (or
stable too) at upside ≥ 20%; a cheap but deteriorating stock is never a buy; an expensive improver is a hold, never
a sell; a strict sell needs a deteriorating trend. Votes counted: all, business only, or price only. 12-month buy −
sell against the universe:

| | v2 rules (before) in / out | best map variant in-sample | its in / out | adopted |
|---|---|---|---|---|
| CN | +4.1% / +11.4% | price votes, buys improving | +3.4% / −6.3% | no (no in-sample gain) |
| US | −7.0% / −47.2% | price votes, buys stable too | +1.3% / −24.5% | **yes** (+8.3 in, +22.7 out) |
| HK | +7.8% / +22.2% | price votes, buys stable too | +10.1% / −2.8% | no (lost 25 points out of sample) |

The other variants: business or all votes lost in-sample in CN (−4.9% to −8.5%) and HK (−7.9% to +4.5%); in the
US they gained less than price votes (−3.8% to −5.5% against −7.0%). The US gain comes from not selling high-momentum names: Micron, a sell on 11 of 21 dates
with v2's rules, is an improver every time. Every t-statistic here is under 1.

**4. The trend in the ranking**: upside percentile + w × class. CN with price votes and w = 0.1: rank
correlation 0.140 in / 0.021 out against 0.135 / 0.016 (+0.005 both, at the bar; CN's buy ranking already adds
0.5 × momentum). The US lost in-sample at every w; HK gained in-sample (up to +0.021) and lost out of sample at
every w. Nothing adopted.

**5. CN, an emotional market (your question, 2026-10-20; `cn`, data/backtest/v3_cn_signals.md).** The A-share
signals a-stock-data documents that the backtest can see point-in-time: limit-up days in 3 months (speculative
heat), abnormal turnover (1-month over 12-month traded value; packages from 2021-08 only), the month's largest
daily return and volatility, the 1-month return, and the latest 业绩预告. Rank correlation, in / out of sample:

| | 1 month | 12 months |
|---|---|---|
| limit-up days | −0.049 (t −3.3) / −0.056 (t −1.8) | −0.072 (t −2.1) / −0.028 |
| abnormal turnover | −0.068 (29 dates) / −0.036 | −0.043 / −0.057 |
| largest daily return | −0.054 / −0.042 | −0.104 / +0.032 |
| volatility | −0.061 / −0.046 | −0.136 / +0.050 |
| 1-month return | −0.031 / −0.046 | +0.025 / −0.010 |
| 业绩预告 tone | +0.010 / +0.022 | −0.033 / +0.068 |

Heat is the one signal with the same sign in both samples at both horizons. By cell, an expensive stock with 2+
limit-up days trailed the universe by 6.0% (in) and 4.4% (out) over 12 months, against +0.2% / +6.7% for an
expensive calm one; for cheap stocks it flips. As a sell rule (strict sells need 2+ / 3+ limit-up days instead of
v2's weakness) it gained in-sample (+9.2% / +8.8% against +4.1%) and lost out of sample (−7.1% / −10.6% against
+11.4%: v2's sells, weak momentum, falling profit or a screen failure, did −16.8%). Not adopted; removed from the
app after the test (commit 2263b4f has it). Northbound flows, margin balances, shareholder counts, lock-up
expiries, institutional visits and the 龙虎榜 have no point-in-time history here; they can be collected from now.

**6. Outliers checked, not normalized (your rule; `outliers`, data/backtest/v3_outliers.md).** Every valued stock
beyond ±100% or labelled gets a verdict (outliers.py): 行业 (its industry is off as a whole: check the method for the
industry), 数据错误 (a figure 20%+ off its second source, revenue too for own-trend growth, or a deep-dive veto:
out of the lists), 证据支持 (the trend explains the price, or a deal / risk / capital filing in 30 days: kept, risk
flagged), else 需复核 (your review list, with what the value rests on). The backtest has no second sources, filings
or deep dives in the past, so its verdicts are 行业 / 证据支持 by the trend / 需复核. Outliers are 24-39% of valued
stock-dates. 12 months later (out of sample; the market was "right" when a cheap one trailed or an expensive one beat
the universe):

| | cheap: 行业 / 证据支持 / 需复核 | expensive: 行业 / 证据支持 / 需复核 |
|---|---|---|
| CN | −4.5% / −1.6% / −0.6% | +22.9% / +3.3% / +1.4% |
| US | −3.5% / −2.2% / −1.5% | +4.5% / −1.3% / −9.5% |
| HK | +2.6% / −5.4% / +3.5% | +2.2% / −2.6% / −9.7% |

Out of sample the market was right about whole industries that looked expensive (CN +22.9%: semiconductors +39%,
communications equipment +98%, electronic components +77%; expensive software fell 16-20%) and about cheap stocks whose trend was deteriorating (证据支持, the value-trap flag: −1.6% / −2.2% /
−5.4%); v3 was right about unexplained expensive outliers in the US and HK (−9.5% / −9.7%). In-sample several of
these signs differ (e.g. CN cheap outliers +1.8% to +2.5%). `track --signal` now reports the same split live.

**7. v1, v3 and the plain benchmarks with the lists as adopted, out of sample, 12 months** (v3's rank correlation
is the same in both rows; the US row is the only change from section 14):

| | rank IC v3 / v1 / better of E/P, B/P | buy − sell v3 before / v3 now / v1 / E/P / B/P |
|---|---|---|
| CN | +0.016 / −0.009 / −0.003 | +11.4% / +11.4% / −4.0% / +7.6% / −42.1% |
| US | +0.032 / +0.076 / +0.160 | −47.2% / **−24.5%** / +1.4% / +0.7% / +29.6% |
| HK | +0.120 / +0.049 / +0.116 | +22.2% / +22.2% / +30.6% / −6.7% / +11.5% |

What didn't work: the business trend as a buy filter in CN and the US, the trend band in the base rates, the trend
in the ranking, the HK map, and the CN heat sell rule. What did: price momentum protecting expensive names from the
sell list (adopted in the US), and the evidence verdicts, which separate whole-industry anomalies (a method
question) from single stocks (a review list) without changing any value.

- Rerun (~6 min for compare; seconds for the rest, on the saved frames): `uv run python -m backtest.v3 compare`,
  then `map cn|us|hk`, `persistence`, `outliers`, `cn`.

## 16. Industry checks and the thin US cell (Phase 13, 2026-10-20, your call: one more round)

Your rule: an industry that is off as a whole points at the method for that industry; a few stocks off are
individuals, checked with evidence. For each industry beyond ±30% today, the part of the method that drives it
(counterfactual medians on the 2026-10-19 snapshot, one component changed at a time), the fix tested in the
backtest, and how the industry did over the next 12 months on past dates when its median was beyond ±30%
(equal-weight industry return over the universe; "market right" when an expensive industry beat it or a cheap one
trailed it).

**Fixes tested** (`fixes` grid, in-sample / out of sample; 12-month rank IC and list buy − sell; bar as Phase 9):

| | CN | US | HK |
|---|---|---|---|
| base | 0.135 / 0.016 · +4.1% / +11.4% | 0.060 / 0.032 · +1.3% / −24.5% | 0.123 / 0.120 · +7.8% / +22.2% |
| no ROE drift in the base-rate path | 0.118 / 0.016 · +0.1% / +9.7% | 0.057 / 0.029 · −3.5% / −12.7% | 0.101 / 0.115 · +7.0% / +14.5% |
| pooled tail hazard, 100 company-years | 0.135 / 0.018 · +4.8% / +12.4% | 0.061 / 0.033 · **+2.6% / −24.0%** | 0.123 / 0.120 · +8.0% / +21.4% |
| pooled tail hazard, 300 | 0.135 / 0.020 · +4.1% / +12.0% | 0.062 / 0.032 · +0.7% / −23.0% | 0.122 / 0.120 · +8.8% / +24.6% |
| industry-level cells (CN 申万 L2, HK level 2) | 0.131 / 0.016 · −0.0% / +1.6% | — | 0.121 / 0.125 · −2.3% / +13.7% |

- **The thin US cell** (technology, 10-20% growth, ROE 8-15%, large: 63 starts) had no company fall behind 13%
  growth in years 5-9 with ~20-27 at risk, so the tail extension carried a zero hazard to 30 years and CACI,
  AMETEK and Roper sat at the 30-year cap. Pooled tail: when fewer than 100 company-years were at risk behind a
  cell's last 3 measured years, its 10-30 year hazard is the market's at the same growth rate. Adopted in the US
  (lists +1.3 points in-sample, +0.5 out; rank IC unchanged); CN and HK don't clear the bar and keep their own
  tails. Today: CACI +447% → +76%, AMETEK +350% → +43%, Roper +290% → +88% (durations 10-13 years); US stocks
  at the cap 22 → 1; beyond ±100% 6.9% → 6.4%.
- **No ROE drift** explains US energy (integrated oil −53% → −21%, E&P −50% → −6% today) but lowers the
  ranking in every market: not adopted (removed after the test; commit 6f780fe has it).
- **Industry-level cells** don't move CN semiconductors (median −44% either way) and lower the lists: not adopted.
- **Analysts' 3 years kept** (durations of at least 3 for covered stocks; Method 16's draft said so, the build
  counts the duration from today) closes most of CN tech's gap today but can't be tested at 12 months (no
  consensus history). On the CN 2026 consensus window (4-6 dates, covered stocks) it was mixed: 1-month IC −0.023
  vs −0.037, 3-month +0.173 vs +0.191, top − bottom fifth over 3 months +4.1% vs −1.9%. Your call; commit 6f780fe
  has the switch.

**Each industry beyond ±30% today:**

| market | industry | median | what drives it (counterfactual median) | when off before: in / out (dates) | reading |
|---|---|---|---|---|---|
| CN | 半导体 | −55% | analysts' 37% growth against a base-rate duration of 0.9 years (analysts' 3 years kept: −36%) | +10.7% (46) / +39.5% (13) | market right in both samples: v3 undervalues the industry |
| CN | 通信设备 | −56% | analysts' 40% growth, duration 0.9 (−36%) | — / +75.5% (2) | new; market right so far |
| CN | 元件 | −44% | analysts' years truncated (−1%) | — / +64.2% (3) | new |
| CN | 自动化设备 | −53% | analysts' years (−32%) | −6.0% (25) / +37.5% (3) | v3 right in-sample |
| CN | 电子化学品Ⅱ | −49% | analysts' years (−28%) | — | new |
| CN | 通用设备 | −49% | analysts' years (−22%) | −4.3% (12) / +51.0% (2) | v3 right in-sample |
| CN | 军工电子Ⅱ | −38% | analysts' years (−17%) | −8.8% (6) / +13.1% (5) | mixed |
| CN | 软件开发 | −57% | the price needs 15% growth for 17 years; no fix moves it | +0.1% (30) / +2.1% (21) | neither: the industry went sideways |
| CN | 乘用车 | +32% | 5 stocks, falling prices (momentum −37%) | — | new |
| US | Integrated oil | −53% | the energy cell's ROE drift (no drift: −21%) | +4.9% (20) / +9.7% (20) | market right in both |
| US | Oil & Gas Production | −50% | ROE drift (−6%) | −4.1% (26) / −5.6% (20) | v3 right in both |
| US | Semiconductors | −49% | analysts' 36% growth, duration 1.6 (−39%) | +3.4% (25) / +121.6% (4) | market right |
| US | Prepackaged Software | −35% | analysts' years (−20%) | +2.0% (53) / −13.9% (21) | mixed; v3 right out of sample |
| US | Life Insurance | +38% | the rate: prices imply 12% against 9.3% used (λ = 1: 0%) | — / −7.3% (1) | new |
| HK | 软件服务 | −31% | the rate: prices imply 5.7% against 6.5% used (λ = 1: 0%) | −3.8% (35) / −6.5% (21) | v3 right in both |
| HK | 银行 | +35% | the rate: prices imply 12% against 9.9% (λ = 1: 0%) | −4.2% (53) / −1.2% (21) | market right in both: cheap banks stayed cheap |
| HK | 建筑 | +37% | the rate: 17% against 9.8% | −7.4% (54) / +0.4% (19) | market right in-sample |
| HK | 其他金融 | +38% | the rate: 13% against 10.3% | +18.5% (2) / +31.4% (5) | v3 right (few dates) |
| HK | 保险 | +48% | the rate: 17% against 10.6% | +0.0% (22) / +24.5% (7) | v3 right out of sample |

What it says about the method, by group: (1) growth industries (CN tech, US semis and software) are where base
rates override analysts most; the record says the market was right in semiconductors in both CN and the US, v3 in
HK software and (out of sample) US software. (2) Energy: the chained ROE drift carries the 2015-2020 bust forward;
it was wrong for integrated oil and right for E&P. (3) Financials and construction in HK: only half the industry
premium is taken as risk; history sides with the market for banks and construction and with v3 for insurers.

**Stocks beyond ±100% today, by verdict** (your rule: individuals are checked, not normalized):

| | beyond ±100% | 数据错误 | 行业 | 证据支持 | 需复核 (unexplained) |
|---|---|---|---|---|---|
| CN | 37 (4.8%) | 0 | 4 | 18 | 15 (2.0%) |
| US | 50 (6.4%) | 2 | 9 | 20 | 19 (2.4%) |
| HK | 27 (7.8%) | 2 | 8 | 7 | 10 (2.9%) |

The largest remaining driver among unexplained US names is growth at the 40% cap (11 of 50; 5 are recoveries from a
depressed first analyst year: airlines, Stellantis), testable only with consensus history.

With the pooled tail, the US row of section 15's last table becomes: rank IC +0.061 in-sample / +0.033 out of sample, lists +2.6% / −24.0% (CN and HK unchanged); the US outlier split in data/backtest/v3_outliers.md moves by 1-2 points.

- Rerun: `uv run python -m backtest.v3 fixes cn|us|hk` (data/backtest/v3_fixes_<market>.csv).

## 17. Common sense first (Phase 13, 2026-10-20, your calls: US quarterly data, R&D, fit first; no patch rules)

Your points: the US is the most efficient market with the best data, so a sound method should explain US prices
best; a backtest that succeeds too well may be overfit; Micron, AMD and Eli Lilly are dominant and won't halve
soon, troubled carmakers won't double; a business in trouble deserves a limited fair value from the method itself,
not an exclusion rule. Checks in this order, each period run once (backtest/sense.py): fit, then what a gap has
meant, then returns.

**1. US quarterly results** (`backtest.fetch sec`: each company's companyfacts once, every 10-Q/10-K period by its
filing date, data/backtest/us_quarterly.csv.gz, 878 companies). The Phase 9 US snapshots had annual reports only,
up to 15 months stale; CN saw every quarter. On 2025-01, 594 of 815 US names have a newer quarterly report; Micron's
EPS is 3.50, not the 0.70 of its year to August 2024 that made it a v3 sell on 6 dates before it rose 4-10×.

| US | within ±30% | large beyond ½ / 2× | rank IC 12m | buy − sell (mean) | buy − sell (median) |
|---|---|---|---|---|---|
| annual reports (Phase 9) | 34.6% / 36.4% | 32.6% / 33.2% | 0.061 / 0.033 | +2.6% / −24.0% | +5.0% / +8.0% |
| quarterly reports (adopted) | 35.8% / 37.6% | 31.0% / 31.2% | 0.057 / 0.042 | +3.1% / +5.4% | +4.2% / +10.2% |

In-sample / out of sample; "large" = the top third by market value. Against the others on the same quarterly
snapshots, out of sample: v1 rank IC 0.091, buy − sell +24.0%; E/P 0.085 / −3.3%; B/P 0.141 / +14.1% (in-sample
all three were at or below zero: −0.005, −0.030, −0.024). The −24% out of sample, driven by Micron and AMD, was a test-data bug.

**2. R&D as an investment** (written off evenly over 5 years: book + the unwritten R&D, earnings + R&D − write-off;
R&D from SEC for 519 US companies). Fit +0.5 / +0.8 points, rank IC +0.003 / +0.007, buy − sell median −1 point out
of sample; today it lifts the US share beyond ±100% from 6.4% to 8.0% and makes the troubled carmakers look cheaper
still (Ford +82% → +111%, Stellantis +239% → +591%). Not adopted (commit 814b67f has it).

**3. The exclusion rule, removed.** "A business in trouble is never a buy" (814b67f) was a patch on one symptom.
Measured before removal: about neutral on buys, but its first form ("and a healthy one is never a sell") cost CN and
HK 6-28 points: the expensive healthy stocks v3 sold did trail (HK out of sample: median −10% to −41%).

**4. What a gap has meant over the next 12 months** (all valued stocks, by v3's gap):

| | US: beat the market / halved / doubled | CN | HK |
|---|---|---|---|
| valued under ½ the price, in | 41% / 1.0% / 2.8% | 35% / 8.2% / 6.0% | 36% / 11.5% / 5.6% |
| valued under ½ the price, out | 42% / 1.6% / 6.5% | 41% / 2.3% / 11.0% | 36% / 4.6% / 12.1% |
| within ±20%, out | 39% / 0.5% / 2.9% | 33% / 0.0% / 6.9% | 37% / 0.8% / 6.3% |
| valued over 2× the price, in | 49% / 1.2% / 6.3% | 52% / 2.0% / 1.9% | 49% / 3.3% / 1.9% |
| valued over 2× the price, out | 43% / 0.9% / 3.1% | 41% / 0.0% / 3.7% | 43% / 1.3% / 5.1% |

Share of the log gap closed within 12 months (per-date slope of log excess return on the log gap): US +0.014 /
−0.004, CN +0.054 / −0.009, HK +0.036 / +0.051, none significant except CN's P/B < 1.5 stocks out of sample
(+0.069, t 2.5). A +100% gap has meant about 0-3% over the universe in a year. Your rule holds in data: the size of
v3's gap is not a near-term price move in any market; in CN and HK its direction carries some information, in the
US hardly any. Healthy businesses valued under ½ halved 1-2% of the time in the US (as often as any healthy
business), 3-12% in CN and HK; troubled ones valued over 2× beat the market 36-46% of the time out of sample.

**5. One cause behind your examples: v3 squeezes every company toward its book value.** Today the median v3 upside
of stocks priced under book is US +60%, CN +44%, HK +44%; of stocks over 4× book US −13%, CN −56%, HK −58%. The
same split runs through the backtest (fit within ±30%: P/B > 4 US 32-34%, CN 25-33%, HK 5-7%). Troubled
businesses sit at the bottom of P/B, dominant growers at the top. What drives each end today:

| | median upside | without analysts | what lifts / sinks the value |
|---|---|---|---|
| US, in trouble, upside ≥ +50% (20) | +76% | −45% | analysts' year-1 EPS 2.4× the reported 12 months (GM: $13.53 adjusted for 2026, half of it reported, against $2.22 reported; Pfizer $2.95 vs $0.76) |
| CN, in trouble, ≥ +50% (34) | +93% | +71% | P/B 0.83; ROE 4.2% against a 5.6% rate recovers to the market's long-run ROE |
| HK, in trouble, ≥ +50% (23) | +100% | +87% | P/B 0.37; the same recovery on a book the market prices at a third |
| healthy, upside ≤ −40%: US 142, CN 146, HK 47 | −57% / −63% / −56% | about the same | P/B 4.6-9.4; base-rate growth durations of 0.8-1.6 years for 14-36% growth |

**6. Structural fixes tested for that cause, none adopted** (scratch tests on the 2026-10-19 snapshots and the base-rate panels):

- *Health-aware base rates.* Business health (levels: revenue growth ±5%, profit growth ±20% or a loss, ROE vs
  8%) adds nothing beyond the growth and ROE bands: ROE 3 and 5 years after a start is within ±0.5 points of the
  cell's average for troubled, neutral and healthy companies alike, in all three markets. Troubled companies'
  ROE was back to 8%+ in years 3-5 in 28% (US), 23% (CN), 19% (HK) of cases, against 45% / 43% / 32% for all;
  the cells already carry that.
- *A health risk premium.* The rate the price implies over the rate v3 uses differs by 0-1 point between troubled
  and healthy businesses (US +2.0 vs +1.6, CN +0.4 vs +0.4, HK +1.0 vs +0.1): no premium to measure.
- *No forced convergence after the measured decade* (ROE stays where similar companies were in year 10). The data
  says convergence is real: the share of a company's ROE distance from the average still there after 10 years is
  25% in the US (18% after 15) and 8% in CN. Fit falls (US 44% → 40%, CN 42% → 32%, HK 42% → 29% within ±30%).
- *What the market pays for fundamentals* (log P/B on ROE, growth, health and size with sector intercepts): R² 0.55
  US, 0.58 CN, 0.36 HK; fit 43% / 44% / 39% (v3 44% / 42% / 42%); the same names stay far off (Stellantis +897%,
  中国建筑 +278%, Apple −60%).

The names off in both methods are the ones priced far from their book: deep under it (Stellantis 0.18×, Chinese
builders and developers ~0.3×) and far over it. Accounting book and reported or adjusted earnings miss what the
market sees there (assets it doesn't believe, recoveries it doubts, assets that never reach the balance sheet).

- Rerun: `uv run python -m backtest.fetch sec` (once; resumable), `uv run python -m backtest.run build us`,
  `uv run python -m backtest.sense build us|cn|hk` (a few minutes each), `uv run python -m backtest.sense us|cn|hk
  [annual|final]`.

## 18. Picking by funnel and score (Phase 13, PLAN.md Method 17, 2026-10-20; backtest/funnel.py)

Your target: a buy beats its market's index (S&P 500, CSI 300, Hang Seng) over 6 months without a blow-up (25%+ below
its start at any month-end within the 6 months); sells trail the index. Stock returns include dividends, the indexes
don't (1-2 points easier over 6 months). In-sample from v3's first valued month (US 2019-02, CN 2019-01, HK 2019-06) to
2023-12, out of sample 2024-01..2026-03 (27 starts). Ranges: 5-95% of a block bootstrap over dates (6-month blocks).
The funnel, inputs, weightings and reading of the pass bar were written into PLAN.md and committed (ba4478b) before
the score was run once.

**Verdict: the funnel and score fail the registered bar.** HK passes every item; the US and CN don't, and the bar needs
two markets. Nothing is built in the app; today's v3 lists stay.

**1. The bar** (6-month returns, the index's and the worst month-end now in the backtest: panel.HORIZONS, `worst_6m`).
Rebuilt with the committed code; the draft's scratch figures came from frames built minutes before the exclusion
rule was removed (CN then 53% / 6.7%).

| 6 months, out of sample (in-sample) | US | CN | HK |
|---|---|---|---|
| today's v3 buys beat the index | 68.9% (47.5%) | 50.4% (51.3%) | 63.7% (64.0%) |
| their blow-ups | 3.7% (11.2%) | 8.1% (7.3%) | 2.2% (12.4%) |
| all stocks: beat the index / blow-ups | 46.1% / 7.8% (49.2% / 10.4%) | 41.7% / 11.3% (45.1% / 18.6%) | 44.1% / 13.3% (52.0% / 24.3%) |
| v1 buys beat the index | 50.4% (48.5%) | 37.8% (49.7%) | 50.4% (57.8%) |

**2. Each input alone** (valued stocks; top fifth / bottom fifth by the input, share that beat the index without a
blow-up; in-sample, then out of sample):

| | US in | US out | CN in | CN out | HK in | HK out |
|---|---|---|---|---|---|---|
| valuation (v3's gap) | 52.1 / 48.4 | 49.0 / 46.3 | 50.1 / 41.8 | 44.3 / 44.9 | 56.7 / 44.5 | 51.3 / 40.1 |
| 6-month price trend | 50.0 / 47.8 | 50.6 / 41.3 | 46.8 / 35.9 | 42.6 / 40.2 | 53.1 / 41.2 | 40.7 / 43.8 |
| quality (v1 z) | 46.8 / 51.2 | 43.6 / 47.4 | 44.1 / 42.2 | 43.4 / 41.0 | 49.5 / 49.8 | 43.5 / 42.0 |
| health (trend.health) | 49.0 / 49.5 | 48.6 / 44.5 | 47.6 / 43.3 | 46.3 / 40.3 | 49.2 / 47.7 | 39.1 / 46.1 |
| business (quality + health without momentum) | 48.1 / 51.2 | 45.3 / 48.2 | 44.5 / 43.7 | 43.5 / 40.3 | 47.4 / 51.3 | 40.0 / 42.1 |
| low volatility | 39.8 / 52.0 | 43.9 / 50.4 | 52.4 / 37.1 | 39.8 / 48.8 | 58.3 / 42.8 | 50.7 / 38.3 |
| low debt (non-financials) | 48.8 / 49.6 | 45.2 / 43.4 | 41.5 / 40.9 | 38.9 / 39.2 | 44.8 / 49.8 | 43.7 / 43.5 |

Blow-ups, top / bottom fifth in-sample: valuation US 11.5 / 11.0%, CN 8.8 / 28.5%, HK 15.2 / 32.0%; low volatility US
5.2 / 16.7%, CN 3.7 / 32.8%, HK 10.1 / 35.7%. Valuation and the trend helped in every market in-sample; low volatility
cut blow-ups everywhere but in the US also cut the beat rate (high-volatility US stocks beat the index more often), and
in CN out of sample it reversed (2024-26 rewarded volatile small caps). Revisions: no history (CN's 2026 window has
3 starts with 6 months of prices).

**3. Confidence calibrated: it isn't.** Rank IC of v3's gap with the 6-month return over the index within each level,
高 / 中 / 低: in-sample US 0.019 / 0.005 / 0.043, CN 0.050 / 0.060 / 0.090, HK 0.013 / 0.023 / 0.069; out of sample US
0.063 / 0.022 / 0.005, CN 0.021 / 0.046 / −0.006, HK 0.084 / 0.092 / 0.108. 高 does not rank better than 低 in-sample in
any market, so confidence leaves the score.

**4. Overlaps** (in-sample mean per-date rank correlation): quality and low debt 0.33 / 0.52 / 0.59 (US / CN / HK;
quality's z contains debt: debt dropped); health and the trend 0.31-0.36 (health's momentum vote: removed in
"business"); valuation and low volatility −0.07 / 0.45 / 0.30 (cheap stocks are calm in CN and HK); valuation and
confidence 0.11-0.26.

**5. What preceded blow-ups** (blow-up rate with the sign over the market's, in-sample / out of sample):

| sign | US | CN | HK |
|---|---|---|---|
| volatility, top fifth | 1.81× / 2.10× | 1.81× / 1.66× | 1.62× / 1.99× |
| a loss over 12 months | 1.71× / 2.13× | 1.31× / 1.74× | 1.54× / 1.79× |
| 6-month trend, bottom fifth | 1.39× / 1.63× | 1.18× / 1.06× | 1.40× / 1.20× |
| CN: 2+ limit-up days in 3 months | | 1.61× / 1.89× | |
| P/B over 4 | 0.96× / 1.36× | 1.63× / 1.70× | 1.63× / 2.14× |
| debt, top fifth (non-financials) | 0.97× / 0.97× | 0.89× / 1.11× | 1.04× / 1.08× |
| health ≤ −1 | 1.23× / 1.16× | 0.83× / 1.12× | 1.00× / 0.85× |
| smallest fifth | 1.14× / 0.91× | 1.04× / 1.13× | 1.08× / 1.34× |
| v3 gap beyond ±100% | 1.06× / 0.92× | 0.46× / 0.31× | 0.67× / 0.51× |

The funnel's blow-up stage (registered signs: log volatility, a loss, the 6-month trend, CN limit-up days; logistic fit
in-sample; out above twice the market's in-sample rate): US 1.7% / 0.9% of stocks set aside, their blow-ups 26.1% /
29.1% against 10.2% / 7.7% (in practice none of them valued by v3: they are loss-makers); CN 8.5% / 9.5%, 42.3% / 22.0%
against 16.4% / 10.2%; HK 3.4% / 2.7%, 56.4% / 23.9% against 23.1% / 13.0%. It finds the blow-ups out of sample too
(2-4×), and costs little: the names it sets aside beat the index about as often or less (CN out of sample more: 46.7%
against 41.2%).

**6. The score, run once.** Inputs per market (in-sample alone test): US valuation, trend; CN valuation, trend,
business, low volatility; HK valuation, trend, low volatility. Chosen in-sample by the funnel survivors' top fifth
(beat without a blow-up): US valuation-led 48.6% (equal 47.8%), CN equal 56.8% (risk-led 57.2%, within 0.5),
HK valuation-led 64.6% (equal 64.0%).

| 6 months, out of sample (in-sample) | US | CN | HK |
|---|---|---|---|
| buys beat the index | 54.1% (54.2%), range 41-63% | 51.1% (57.7%), 32-64% | 64.4% (72.7%), 55-71% |
| their blow-ups | 4.4% (9.8%), 2-9% | 2.2% (3.7%), 0-4% | 1.5% (8.0%), 0-4% |
| today's v3 buys: beat / blow-ups | 68.9% / 3.7% (47.5% / 11.2%) | 50.4% / 8.1% (51.3% / 7.3%) | 63.7% / 2.2% (64.0% / 12.4%) |
| both periods together: buys / today's v3 buys | 54.2% / 8.1% vs 54.2% / 8.8% | 55.6% / 3.2% vs 51.0% / 7.6% | 70.0% / 5.9% vs 63.9% / 9.0% |
| sells trailed the index (today's v3 sells) | 60.0% (53.3%) | 62.2% (59.3%) | 59.3% (50.4%) |
| all valued: top fifth vs bottom fifth over the index, out | +1.7% vs −1.5%; blow-ups 5.3% vs 10.5% | +0.7% vs +5.1%; 5.6% vs 16.7% | +4.0% vs +0.4%; 3.1% vs 22.2% |
| the same, in-sample | +3.0% vs +0.4%; 10.3% vs 10.6% | +4.4% vs −1.7%; 8.8% vs 27.7% | +7.5% vs +3.2%; 10.7% vs 36.5% |
| sub-periods where the top fifth wins on both | 3 of 4 (not 2019-20) | 3 of 4 (not 2024-26) | 3 of 4 (not 2019-20) |
| side checks: buys beat the index at 12 months, out | 54.3% (today's 65.7%) | 44.8% (48.6%) | 58.1% (59.0%) |

The pass bar, item by item (registered reading in PLAN.md Method 17):

| | US | CN | HK |
|---|---|---|---|
| out: buys beat the index ≥ 55% | fail (54.1%) | fail (51.1%) | pass (64.4%) |
| out: blow-ups ≤ half the market's | fail (4.4% > 3.9%) | pass (2.2% ≤ 5.65%) | pass (1.5% ≤ 6.65%) |
| out: at least as good as today's v3 buys on both | fail | pass | pass (+0.7 points; 2 blow-ups against 3) |
| in-sample, the same direction | pass | pass | pass |
| top fifth beats bottom fifth, both samples | pass | fail (out: mean return; beat rate 43.5% vs 42.2%) | pass |
| 3 of 4 sub-periods | pass | pass | pass |
| at least two markets | fail: HK only | | |

Costs and turnover: buys turn over 26-42% a month; one round trip (US 0.2%, CN 0.3%, HK 0.6%, assumed) moves the
beat rate by 0-0.7 points. Gaps beyond +100% among the buys: US 49%, CN 14-35%, HK 33-63%; resting on the gap alone
(the other inputs below their median): US 0, CN 0, HK 4 of 410.

**The rank itself** (your question: the weighted score's rank, not only its top 5). Each input is a percentile among the
day's valued stocks, the score their weighted average, the buys the 5 best-ranked survivors of the funnel. The funnel's
survivors by score fifth (top → bottom), beat the index / blow-ups:

| 6 months | US in | US out | CN in | CN out | HK in | HK out |
|---|---|---|---|---|---|---|
| top fifth | 48.8% / 9.0% | 54.4% / 4.0% | 56.7% / 5.6% | 49.3% / 3.6% | 65.4% / 7.6% | 58.0% / 2.2% |
| second | 47.7% / 8.1% | 44.6% / 5.1% | 53.8% / 9.0% | 46.1% / 5.1% | 55.0% / 16.7% | 49.1% / 6.8% |
| middle | 46.3% / 6.5% | 37.4% / 6.4% | 49.9% / 15.6% | 36.0% / 7.1% | 53.7% / 17.4% | 44.5% / 6.3% |
| fourth | 47.9% / 7.8% | 41.2% / 7.2% | 46.8% / 21.5% | 40.7% / 9.7% | 52.2% / 23.3% | 40.0% / 12.0% |
| bottom fifth | 48.3% / 8.5% | 38.4% / 6.6% | 41.1% / 25.7% | 38.7% / 13.5% | 44.8% / 34.2% | 41.7% / 17.1% |
| median over the index, top / bottom | −0.4% / −0.6% | +2.0% / −5.3% | +2.6% / −5.0% | −0.4% / −6.0% | +5.7% / −2.8% | +4.0% / −5.3% |

The rank sorts blow-ups in every market and both samples, and the beat rate in CN and HK in both samples; in the US
only out of sample (in-sample every fifth beat the index 46-49% of the time). The top fifth (30-40 names a month) beat
the index 49-58% of the time out of sample, so 5-name lists drawn from it sit near the 55% line. Today's ranking with
every input (2026-10-19, scratch, not built): the review page and reports/2026-10-19/m17_ranking.csv; the top of CN
and HK is mostly banks and brokers (cheap, calm, rising).

**7. Survivorship.** CN is close to point-in-time (it misses ~0.9% of turnover, section 9) and is where the score
improved most on today's lists (both samples, both measures), so survivors don't make the design. In the US about
3.8% of the 800 largest SEC filers a year stop filing (2009-2023, mostly takeovers): even if each had been a blow-up,
the 6-month blow-up rates would be under ~2 points higher. HK can't be measured.

**8. Today (2026-10-19, not built; scratch).** The funnel and score would buy US: Microsoft, Qualcomm, Sandisk, MetLife,
Applied Materials; CN: 招商证券, 中国移动, 成都银行, 上港集团, 招商银行; HK: 中信股份, 民生银行, 工商银行, 海尔智家,
中国海外发展. Your examples: MU (score 75th percentile), AMD (28th), LLY (38th) are not sells; GM and Ford rank high
on value but fail the quality screen, Stellantis is set aside as a blow-up risk (chance 23% against 21%): none a buy.
保利发展 (67th) and 中国太平 / 中国人寿 (81st / 79th) drop out of the buys; 绿的谐波 is set aside as a blow-up risk (51%).

- Rerun: `uv run python -m backtest.run build us|cn|hk` (the 6-month columns; about a minute each), `uv run python -m
  backtest.sense build us|cn|hk` (the frames, ~2 min), then `uv run python -m backtest.funnel checks|score us|cn|hk`.

## 19. Stage 1 of the new plan: the signal score against the ship bar (2026-10-22; backtest/stage1.py)

The test docs/PLAN.md registers, run once on the month-end frames (CN 2019-01..2026-09, 87 starts with 6-month returns;
US 2018-01.., 99; HK 2016-10.., 114), after the definitions were committed (714e1a7). The benchmark is each market's index
fund with dividends reinvested (SPY, 2800.HK, 510300.SS adjusted closes): the backtest snapshots carry no dividend yields,
so the plan's stopgap (price index + dividend yield) couldn't be built. Lists pay a round trip of costs. The harness
reproduces Method 17's all-stock beat and blow-up rates (CN 45.1/18.6 and 41.7/11.3, exactly; US out-of-sample blow-ups
7.9 vs 7.8).

**Verdict: the bar fails in every market, in both runs below; the report doesn't switch.**

Two runs. The first (stage1.py `bar`) scored a fresh 10-name list each month held 6 months. The stage review found that the
plan registers the buys held or sold by the holding rule, with random lists held the same way; the second run
(stage1_hold.py, committed before it ran, d2a8c56) does that. Both are below; the plan's own definition is the second.

**Which signals entered** (top fifth − bottom fifth on the mean 6-month return, positive in 3+ of 2019-20, 2021-22, 2023,
2024-26): CN accruals, 12-1 momentum, 6-month trend, no loss, no CN heat (E/P 1/4, B/P 2/4, volatility 2/4 stayed out);
US B/P and the 6-month trend only (volatility and losses were negative in all four: risky US stocks did better); HK E/P,
B/P, accruals, both trends, low volatility, no loss and low issuance.

| 6 months, after costs, over the index fund | CN | US | HK |
|---|---|---|---|
| score's 10 buys: mean (sub-periods positive) | +6.0% (4/4) | −1.0% (1/4) | +4.6% (4/4) |
| share of 1,000 random lists from the same funnel beaten | 100% | 77% | 100% |
| random lists' median | +0.5% | −1.4% | +1.0% |
| best single signal | 12-1 momentum +3.5% | 12-1 momentum −0.7% | 12-1 momentum +8.1% |
| 25%+ falls: buys / random lists | 16.3% / 13.4% | 8.7% / 7.4% | 6.1% / 14.7% |
| beat the index fund | 52.9% | 45.7% | 55.7% |
| expected-return line slope, sub-periods up | 4/4 | 4/4 | 3/4 |
| items failed | 4 (falls) | 1, 2, 3, 4 | 3 (a simpler signal did better) |

HK's item 3 sends the simpler signal: the 12-1 momentum list, checked against items 1, 2 and 4, has the returns (+8.1%,
4/4, all random lists beaten) and fails item 4 (25%+ falls 22.7% against 14.7%).

**The registered holding-rule portfolio** (keep a name while it is in the funnel at or above the median score, fill
to 10 from the top, at most 2 per industry; random portfolios fill at random and sell by the same rule; 25%+ falls per
entered name):

| 6 months from every start, after costs, over the index fund | CN | US | HK |
|---|---|---|---|
| score portfolio: mean (sub-periods positive) | +4.0% (4/4) | +0.7% (2/4) | +3.2% (3/4) |
| random portfolios' median / share beaten | +2.6% / 78% | −0.7% / 90% | +2.0% / 81% |
| best single signal | 12-1 momentum +0.6% | plain E/P −0.2% | 12-1 momentum +5.4% |
| 25%+ falls per entry: score / random | 14.0% / 13.8% | 13.3% / 7.0% | 3.4% / 11.7% |
| a year over the fund; max drawdown (fund's) | +6.7%; −32% (−32%) | +0.6%; −31% (−24%) | +5.6%; −35% (−47%) |
| items failed | 2, 4 | 1, 2, 4 | 2, 3 |

The random portfolios sell by the score too ("held the same way"), so they share part of its skill: in CN and HK the
funnel (large, profitable for 3 years, no extreme blow-up chance) plus that sell rule already beat the index fund by
2-2.6 points per 6 months; the score's buying order adds 1-1.4 points more, which isn't enough to separate it from luck
at the 90% line.

**What it says.** In CN and HK the evidence-based signals pick lists that beat the index fund and every random list,
in every sub-period; what pays (momentum) also crashes more often. The HK score, with low volatility and value in it,
cut the falls to under half the random lists' rate at a lower return. In the US nothing beat SPY: equal-weight lists of
large companies trailed the cap-weighted index over 2018-2026 (random lists −1.4% per 6 months), and the score adds
little. The holding-rule portfolio (reported, not deciding): CN +6.7% a year over the index fund (5 names +10.0%),
drawdown −32% like the fund's; HK +5.6% (5 names +8.4%), −35% against −47%; US +0.6% (5 names −2.7%), −31% against −24%.
Avoid lists: CN beat the index 32% of the time with 29% falls (the 400 largest: 44%, 16%), HK 37% and 38% (48%, 18%);
the US avoid list did no worse than the rest on return.

Rerun: `uv run python -m backtest.run build cn|us|hk`, then `uv run python -m backtest.stage1 frame|bar cn|us|hk`
(data/backtest/index_etf.csv.gz: the index funds' daily adjusted closes from Yahoo, fetched 2026-10-22).

**The stage review** (a fresh-context agent, .claude/agents/stage-reviewer.md) confirmed the verdict item by item and
found the first run's deviation; also: inputs are winsorized at 2/98% (ties at the extremes: 1-2 names a date at the
momentum cap inside the funnel, small); two look-aheads that favour passing (the blow-up fit on 2019-23 outcomes applied
to those dates; signals chosen on the whole sample), so they don't weaken the fail; US negative-book buyback stocks (MCD,
LOW) land at the bottom of B/P and in the avoid list, a definition to fix if the US ever ships.

**The corrected test** (your OK 2026-10-22; the three corrections in docs/PLAN.md, committed before one run, aea2862;
backtest/stage1_fix.py). Risk signals judged on falls entered everywhere they were offered (volatility, a loss, CN heat:
the risky side fell 25%+ more often in 3-4 of 4 sub-periods in every market); return signals as before. Holding-rule
portfolios; random portfolios use no score:

| 6 months from every start, after costs, over the index fund | CN | US | HK |
|---|---|---|---|
| score (signals) | +1.8% (accruals, both trends, volatility, loss, heat) | −2.3% (B/P, 6m trend, volatility, loss) | +3.2% (as before) |
| sub-periods positive | 3/4 (2024-26 −7.5%) | 2/4 | 3/4 |
| random portfolios' median / share beaten | +0.2% / 79% | −1.1% / 18% | +1.5% / 86% |
| 25%+ falls per entry: score / random | 10.3% / 12.4% | 7.7% / 6.7% | 3.4% / 10.5% |
| a year over the fund; max drawdown (fund's) | +2.9%; −16% (−32%) | −4.8%; −25% (−24%) | +5.6%; −35% (−47%) |
| expected-return line, sub-periods up | 4/4 | 0/4 | 3/4 |
| items failed | 2 | 1, 2, 4, 5 | 2 |
| avoid list: trailed the 400 largest and fell more, sub-periods | 4/4 (falls 33% vs 16%) | 2/4 | 2/4 |

**Verdict: fails; the report doesn't switch.** CN and HK fail only item 2: their portfolios beat the index fund with
smaller drawdowns and fewer falls than random picks, but beat 79% and 86% of random portfolios from the same funnel,
under the 90% line. The stage review (fresh context) reproduced both percentiles and found the corrections implemented as
registered, with no sign of tuning (they cut both ways: CN +4.0% -> +1.8% per 6 months, the US 90% -> 18% of random
portfolios). Its reading, which replaces a kinder one here: in CN the score's edge sat in the trend signals and reversed
in 2024-26 (-7.5% against -1.7% for random portfolios; the line's slope there +0.006, flat), so CN looks short of edge,
not only of statistical power; HK looks under-powered (29 names entered in 119 months). The line to clear sits at about
+2.8% (CN) and +3.5% (HK) per 6 months over random picks, 4-5% a year: a 10-name, low-turnover portfolio over these
years can't confirm an edge of the size the plan expects. Signals were chosen on the whole sample, which flatters the
score. CN's avoid-list pass is largely in-sample by construction (the blow-up fit and the risk signals were chosen on
the same falls; high-volatility stocks fall 25%+ more often almost mechanically): not standalone evidence. In the US the
risk signals made it worse: in 2018-2026 the riskier US stocks did better, and nothing beat SPY. This is the third run
on the same data; no further variant is run on it for stage 1.

