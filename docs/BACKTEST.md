# Backtest, calibration and signal tracking (Phase 9, 2026-10-18)

v1 and v2 were run point-in-time on every month end: CN 2019-01 to 2026-09 (93 dates), US 2018-01 to 2026-09
(105), HK 2016-10 to 2026-09 (120). Parameters were chosen on the in-sample dates (up to 2023-12) and checked on
the out-of-sample dates (2024-01 to 2026-09; 12-month returns exist for the first 21 of them). Code:
`backtest/` (outside the app); every table below can be rebuilt (see "Rerun"). Generated tables:
data/backtest/results.md.

## 1. Verdict

- **Switch rule (A4): met.** Out of sample, calibrated v2 beats v1 on both the 12-month rank correlation and the
  buy − sell spread in CN and HK, not in the US (v1's rank correlation is higher). v2's 高 buy and sell picks did
  the right thing 72% of the time (74 picks), its 低 picks 33% (only 3 picks: v2 rarely fills with 低).
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

Downloads: ~2.8 GB of 通达信 packages, parsed in memory, never stored. data/backtest is 0.73 GB, so data/ + reports/
is 0.78 GB.

## 3. v1 vs v2 out of sample (2024-01..2026-09)

Rank correlation (IC) of the upside with later returns, mean over dates (t-statistic). Buckets: average return
of the 5 picks minus the equal-weight universe. v2 = calibrated (config.toml now); "v2 (Phase 8)" = the first
guesses.

| | IC 1m | IC 3m | IC 12m | buy 12m | sell 12m | buy − sell 12m | buy hit 12m | buy vs index 12m |
|---|---|---|---|---|---|---|---|---|
| **CN** v1 | +0.031 (1.2) | +0.040 (1.0) | −0.009 (−0.2) | −0.9% | +3.0% | −4.0% (−0.2) | 37% | +6.7% |
| CN v2 | +0.045 (1.0) | +0.075 (1.2) | −0.003 (0.0) | −1.3% | −19.2% | +17.9% (1.4) | 50% | +6.4% |
| CN v2 (Phase 8) | +0.042 | +0.063 | −0.029 | −9.5% | −10.8% | +1.3% | 36% | −1.8% |
| **US** v1 | +0.018 (1.0) | +0.039 (1.7) | +0.076 (1.6) | +2.7% | +1.3% | +1.4% (0.1) | 50% | +5.8% |
| US v2 | +0.013 (0.6) | +0.037 (1.1) | +0.067 (1.1) | +3.1% | −8.3% | +11.4% (0.7) | 54% | +6.2% |
| US v2 (Phase 8) | +0.012 | +0.035 | +0.064 | +4.2% | −8.4% | +12.7% | 52% | +7.3% |
| **HK** v1 | +0.043 (2.4) | +0.067 (2.5) | +0.049 (1.5) | +8.5% | −22.1% | +30.6% (1.3) | 49% | +14.8% |
| HK v2 | +0.048 (2.1) | +0.087 (2.6) | +0.099 (2.5) | +22.1% | −11.8% | +33.9% (1.7) | 59% | +28.4% |
| HK v2 (Phase 8) | +0.042 | +0.079 | +0.083 | +14.0% | −13.0% | +27.0% | 67% | +20.3% |

In-sample (for reference): IC 12m v1 / v2: CN +0.084 / +0.135, US −0.003 / +0.054, HK +0.074 / +0.131;
buy − sell 12m: CN −4.4% / +3.5%, US −3.4% / +6.8%, HK +12.1% / +1.9%. v2's expected return over its required
return ranks about as well as its upside: IC 12m CN −0.019, US +0.086, HK +0.113 out of sample.

## 4. Calibration (config.toml `[v2]`)

All five changes together, averaged over the three markets: IC 12m in-sample +0.094 → +0.107, out of sample
+0.039 → +0.054; buy − sell 12m in-sample 5.2% → 4.1%, out of sample 13.7% → 21.1% (v1: IC +0.052 / +0.039,
buy − sell 1.4% / 9.4%).

Return grids re-ran v2 with one value changed at a time; the score is the in-sample 12-month IC averaged over
the three markets (buy-bucket return for the momentum settings). A value replaces the Phase 8 guess only if it
gains at least 0.005 IC (or 1 point of buy return) in-sample; it should then not lose out of sample. The panel
studies use the yearly history (CN 2009-2025 from the backtest tables, US and HK 2015-2025). Section 5 has
their numbers.

| Parameter | Phase 8 | In-sample evidence | Chosen | Out of sample |
|---|---|---|---|---|
| φ (long-run share of excess ROE) | 0.15 + 0.45 × stability + 0.2 × margin, all markets | Panel: the share of a normal excess ROE still there after k years is CN 0.70, 0.54, 0.44, 0.37, 0.31, 0.24, 0.21, 0.18 (k = 1-8) and flat across stability and margin; HK 0.54, 0.34, 0.26 (k = 1-3); US 0.90, 0.78, 0.77. Returns: lower φ +0.002 IC (CN, HK prefer it; the US prefers the formula) | CN, HK: flat 0.2; US: unchanged | flat 0.2 everywhere: +0.025 IC |
| Fade years (after year 3) | 10 | Returns: 3 years +0.006 IC (CN +0.008, HK +0.011, US −0.002), in the joint run with the other choices; CN's panel curve is near its floor within ~6 years | 3 | +0.002 IC (buy − sell in-sample fell 8.6 → 3.8 points: noted) |
| Persistence floor under a new regime (PHI_NEW) | 0.5 | Panel, breaks that kept half their jump after 3 years, share of the new excess left after k years: CN in-sample 0.49 / 0.08 / −0.01 / 0.06 (k = 4-7), HK 0.36 at k = 4, US 1.08 at k = 4 (today's listings only) | CN 0.05, HK 0.1, US 0.5 | CN 0.58 / 0.20 / 0.06 / −0.05; HK 0.20 / 0.11 / 0.25; US 0.92 / 0.86 / 0.89 / 0.94 |
| Own last boom (log-odds) | ±0.5 | Panel: coefficient ~0 in every market; out-of-sample log loss = the base rate's | 0 | — |
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
| Buy and sell picks right (12 months), all markets | 72% (74 picks) | 64% (553) | 33% (3) |
| Any valued stock: sign of the upside right (CN / US / HK) | 51% / 53% / 57% | 53% / 58% / 51% | 55% / 57% / 52% |
| β, share of the log gap closed in 12 months (CN / US / HK) | +0.14 / −0.04 / +0.19 | +0.09 / +0.11 / +0.16 | −0.01 / +0.01 / +0.01 |

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

| | Phase 8 | Phase 9 |
|---|---|---|
| NVDA | +74% 中 (p 54%) | +42% 中 (p 66%: the own-boom penalty is gone; V_new 562 → 402) |
| MU | +71% 低 | +99% 低 (p 33% → 45%; V_new unchanged, US floor 0.5) |
| 中际旭创 | −20% 中 | −56% 低 (V_new 1,741 → 731: CN breaks fade; p 22%) |
| 江波龙 / 佰维存储 | −29% / +133% | −39% / +10% |
| Toyota / CTSH / OMC | +44% 高 / +68% 高 buy / +129% 低 | +45% / +72% buy / +139% 低 |
| AAPL / 贵州茅台 / 腾讯 | −27% / −18% / +24% | −37% / −34% / −5% (lower φ: CN/HK franchises are worth less) |

Buys, CN: 天华新能, 九安医疗, 招商证券, 青岛银行, 财通证券. US: CPAY, ORIX, Ecopetrol, CTSH, Franklin. HK: 中国太平,
中银航空租赁, 中国民航信息网络, 碧桂园服务, 德翔海运. The CN market-implied return fell from 7.7% to 6.1%: with
less persistence the same prices imply a lower return.

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
uv run python -m backtest.calibrate grid|grid2|grid3 cn|us|hk
uv run python -m backtest.panels_run cn|us|hk              # regime, persistence, normal-ROE panels
uv run python -m backtest.news sample                      # CNINFO, ~50 min
uv run python -m backtest.calibrate compare                # v1 vs v2 (Phase 8 and config.toml)
uv run python -m backtest.report                           # data/backtest/results.md
```
