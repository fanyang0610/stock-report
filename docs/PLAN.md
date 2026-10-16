# Plan

## Status (update at the end of each phase)
- Phase 1 Foundation + delivery test: done 2026-10-17 (TEST text + PDF arrived on the phone, PDF opens)
- Phase 2 CN data + valuation: not started
- Phase 3 CN notes + report + keyword: not started
- Phase 4 US: not started
- Phase 5 HK + full 45-stock report: not started
- Phase 6 Daily schedule + tracking: not started
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
- Liquidity: 20-day average daily turnover of at least ¥50m (CN), HK$20m (HK) or US$10m (US). These are config values.
- Keep the top 800 by total market value.

### 2. Peer groups
Use the industry from the data source (the Eastmoney industry field in v1). Merge groups with fewer than 8 members into the nearest broader group, or compare them market-wide.

### 3. Metrics
Use the latest data, trailing 12 months where possible:
- price, market value, P/E, P/B, ROE
- revenue growth, net profit growth, gross margin
- debt/assets, operating cash flow ÷ net profit, dividend yield
- 12-month price return excluding the last month
- 1-year volatility

Winsorize each metric at the 2nd and 98th percentile within the market.

### 4. Fair value (per stock, in its quote currency)
- Banks, insurers and brokers: justified P/B = (ROE − g) / (r − g). Blend it 50/50 with the P/B the peer group pays for that ROE (a cross-sectional fit of P/B on ROE).
- Other profitable companies: the P/E the peer group pays for similar ROE and growth (a fit of log P/E on ROE and growth within the group).
- Loss-making companies: P/S fitted on gross margin and growth. If no fit is possible, the stock has no fair value and is excluded.
- Fair value mid = fitted multiple × the company's own metric.
- Fair value low/high = from the 25th/75th percentile of the group's fit residuals.
- r = 10-year government bond yield + equity premium (CN 6%, HK 6%, US 5%). g = min(ROE × retention, 3%). Both are config values.
- Absolute cross-check: a simple residual-income value at the same r. If the peer value and the absolute value differ by more than 50%, mark the stock 低信心.
- Upside = fair value mid / price − 1.

### 5. Scores (sector-neutral z-scores within each market)
- Value: upside, earnings yield, book yield (for financials)
- Quality: ROE, gross margin, cash conversion, low leverage
- Growth: revenue and profit growth
- Momentum: 12-month return excluding the last month
- Risk: low volatility

Composite = 0.35 value + 0.25 quality + 0.15 growth + 0.15 momentum + 0.10 risk. The weights live in config.toml.

### 6. Buckets (per market, always 5 each)
- 买入 BUY: upside ≥ 15%, quality ≥ peer-group median and momentum z ≥ −0.5. Take the top 5 by composite score.
- 持有/不追高 HOLD: quality in the market's top 30% and upside between −10% and +15%. Take the top 5 by quality score. These are good companies priced about right: hold them if you own them, don't chase them if you don't.
- 卖出/回避 SELL: upside ≤ −15%, plus at least one of: quality in the bottom 40%, momentum z ≤ −0.5, or falling profits. The stock must be among the market's 400 largest. Take the 5 with the lowest composite score.
- At most 2 stocks per peer group per bucket, and each stock in only one bucket.
- One issuer appears only once in the whole report. A/H pairs come from Eastmoney's AH list; US ADR ↔ HK pairs come from a small CSV in data/ref/.
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
- Output JSON:
  - note: at most 60 Chinese characters
  - risk: at most 30 characters
  - flag: none | one_off_gain | pending_deal | delisting_or_st | data_suspect
  - reason
- Use a low temperature and validate the JSON.
- Any flag other than none swaps the pick for the next-ranked candidate; log the swap. Numbers are never changed.
- Cache notes per day and ticker. If the API fails, use template text and still ship the report. Expect up to about 60 calls per daily run.

### 9. Report and delivery
- PDF: Jinja2 HTML → PDF via headless Chrome, in the order overview, US, HK, CN. The footer gives the data date per market, a one-line description of the method and "not investment advice".
- Text summary: 45 lines of "代码 名称 动作 现价→公允价 空间%", grouped by market and bucket, at most 4,000 bytes.
- Listener: a launchd job runs `listen` every 60 s. It polls, matches the keyword (trailing punctuation trimmed, case-insensitive) and sends the newest report: text first, then the PDF.
  - It always replies. If today's report isn't ready, it sends the newest one with its date in the title.
  - If a send fails, it retries once and logs the failure.
  - It dedupes by message id, stored in data/state.json.
- Only one process may poll the bot. The old listener is stopped.

### 10. Schedule and tracking
- A launchd job runs `run` daily at 06:30 Beijing time: after the US close, and CN/HK use the previous close.
- If a market's fetch fails, reuse its last good data and say so in the report.
- Every run appends its picks to data/picks.csv: date, market, bucket, ticker, price, fair value mid, composite score, conviction.
- `track` reports the average return by market and bucket against each market's index (CSI 300, Hang Seng, S&P 500) at 1 week, 1 month and 3 months.

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

## Phases (done when)
1. Foundation + delivery test: TEST text + PDF arrive on my phone, and I confirm the PDF opens.
2. CN data + valuation: `run --market cn --no-notes` builds 15 CN picks from cache in under 5 min, tests pass, and I review the picks CSV and agree they make sense.
3. CN notes + report + keyword: DeepSeek notes appear in the CN PDF, and texting the keyword returns the CN report within 30 s.
4. US: same as Phase 2 for US, and the keyword report contains CN + US.
5. HK + full report: HK picks reviewed, issuer dedupe works across markets, and the keyword returns the full 45-stock report.
6. Daily schedule + tracking: the 06:30 build works on 2 consecutive days, `track` prints a scorecard, and cleanup keeps data/ + reports/ well under 2 GB.

## Data sources (free; verify each endpoint while building)
- CN:
  - Universe and quotes: the Eastmoney list API push2.eastmoney.com/api/qt/clist/get, which returns all A-shares in pages.
    - fs = m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23
    - fields: f12 code, f14 name, f2 price, f6 turnover, f9 P/E, f20 market value, f23 P/B, f37 ROE, f100 industry
  - Quarterly results for all A-shares: Eastmoney datacenter 业绩报表 (AKShare stock_yjbb_em).
  - Price history: Eastmoney or Tencent daily kline.
  - A/H pairs: the Eastmoney AH list.
  - 10-year yield: ChinaBond.
  - Announcements: CNINFO.
  - Backup: the Tushare token in .env.
  - The a-stock-data skill documents many CN endpoints.
- US:
  - Universe: the same Eastmoney list (fs = m:105,m:106,m:107) or the Nasdaq screener.
  - Trailing-12-month fundamentals: SEC companyfacts per company from data.sec.gov, at most 10 requests per second, with User-Agent = SEC_USER_AGENT from .env. These files are large, so extract the fields and delete the raw files in the same run; refresh weekly.
  - Gaps (e.g. foreign filers): the free FMP key (FMP_API_KEY, about 250 calls per day).
  - Price history: the Yahoo chart API.
  - 10-year yield: FRED DGS10 (FRED_API_KEY).
  - Headlines: the SEC filing list.
- HK:
  - Universe and quotes: the Eastmoney list (fs = m:128+t:3,m:128+t:4,m:128+t:1).
  - Fundamentals: Eastmoney HK financial indicators per stock, for the screened names only (AKShare has wrappers).
  - 10-year yield: HK government bond (hkgb.gov.hk).
  - Headlines: HKEXnews titles.
- FX, only needed when a company reports in a different currency from the one it trades in: ECB rates via api.frankfurter.dev.
- Legacy references (read only), all under ~/Developer/EquitySignalsClawbot-legacy/:
  - Sources/EquitySignalsClawbotCore/PublicUniverse.swift (around line 1310, the Eastmoney list call)
  - Sources/EquitySignalsClawbotCore/MacroPanel.swift (rate sources)
  - Sources/EquitySignalsClawbotCore/EastmoneyHKFinancialStatements.swift
  - script/a_stock_snapshot_sidecar.py (Tencent/Sina A-share calls)
