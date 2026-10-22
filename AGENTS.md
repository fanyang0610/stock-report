# stock-report: rules for coding agents

## Goal
On a WeChat keyword (股票报告 / 股票简报 / stock report / stock brief), reply within 30 s with exactly two messages: a text summary and a PDF report. Per market (US, HK, CN): a ranked shortlist of 10 buys (买入候选), a check of the names you hold (持仓检查: 继续持有 / 复核 / 卖出), and 10 names to avoid (回避, marked 可做空 where shorting is possible). Each card shows the price, the expected excess return over the index with its historical range, the signals behind it, what the price implies, the key risk, the review's finding, an AI note and a re-check trigger. You buy a handful of names and hold them for months.

## Read first
docs/PLAN.md has the method, the stages and the current status. The old plan (v1-v3, Phases 1-13) is in docs/archive/PLAN-v1-v3.md as reference only, not as a path to follow. Do only the stage you were asked to do.

## Layout
stockreport/fetch/ (one module per data source) → universe.py → value.py → score.py → pick.py → notes.py (DeepSeek) → render/ (HTML → PDF) → deliver.py; plus listener.py and track.py.
Valuation v3 (Phase 13, docs/PLAN.md Method 16) runs in shadow mode after pick.py: history.py + baserates.py (fetch/frames.py, fetch/swclass.py) → v3.py → shadow.py (trend.py: business-trend votes and the trend × valuation lists; outliers.py: evidence verdicts for outliers).
crosscheck.py compares each market's key figures with a second source and raises day-over-day drift alarms (Phase 12, docs/PLAN.md Method 13). Phase 11 (Methods 14-15): the event layer (fetch/events.py market-wide filing feeds → events.py classification and abnormal-move labels) and the deep-dive lane (deepdive.py: triggers, fetch/filings.py, DeepSeek questionnaire, quotes.py verification; verdicts.py for your vetoes and confirms). signal.py scores signals (the backtest and `track --signal`). backtest/ (outside the app) is the Phase 9 and 13 backtest; docs/BACKTEST.md has its results and commands.
Target after stage 1 ships (docs/PLAN.md): signals.py (the signals) → score.py (the score, the expected return) → lists.py (the funnel, buys, holdings, avoid) → review.py (the results review, from stage 2; notes.py and deepdive.py feed it), with forecast.py (the earnings engine) from stage 3; v1's value.py and v3's baserates.py, v3.py, shadow.py, trend.py and outliers.py go once stage 1 ships.
bridge/wechat.mjs is the WeChat helper (Node). data/ is the daily cache and reports/ the outputs; both are git-ignored.

## Rules
1. Free data only. Follow the Storage section in docs/PLAN.md: raw responses are temporary, only small extracted tables are kept, and cleanup runs after every build. data/ + reports/ must stay under 2 GB.
2. All numbers come from code + data. The LLM never writes forecasts, prices, fair values or scores. DeepSeek only writes short notes from numbers we give it, and may flag a pick to be swapped for the next one. In the deep-dive lane DeepSeek may extract facts from primary filings, each with the quoted sentence; code checks the quote against the filing text and takes the number from the quote.
3. Rank every stock with one rule-based score per market: published signals (valuation from our own earnings forecast, profitability, price trend, risk, issuance, analyst revisions), equal weights among those that pass the sub-period test in docs/PLAN.md. No hand-typed per-company assumptions. Per-company research only through the results review, the bounded deep-dive lane (rule-triggered, at most 3 per market per day, cached per filing) and user verdicts (veto or confirm with an expiry, never numbers). a-stock-data is fine as an endpoint reference.
4. Lists are rank-based: 10 buys and 10 avoid names per market that passes its registered test; a list short of strong candidates shows the next-ranked names marked 低信心 (low conviction). A market that doesn't pass shows no buys: its section says no list beat its index fund and names the fund. Never fail the whole report.
5. Missing or inconsistent data: drop the stock and take the next one. Never invent data or hard-code tickers into the picks.
6. Keep it small: no frameworks, "gates", "contracts", ledgers, hashes, attestations or handoff documents. Target under 6,000 lines of app Python (stockreport/), with files under 400 lines. Ask before adding a dependency.
7. Tests: pytest for the valuation/scoring math and the parsers (using small saved samples), plus one end-to-end dry run. Nothing more.
8. One stage per session. Before reporting a stage done, run the stage-reviewer agent (.claude/agents/stage-reviewer.md) with fresh context and include its answers. When the stage's "done when" is met, update the status in docs/PLAN.md, commit, then stop and report in 10 lines or fewer.
9. Ask me before: sending any WeChat message, creating or pushing to GitHub repos, installing launchd jobs, or adding any paid service.
10. Never print, log or commit secrets from .env.
11. If something is ambiguous or a stage can't be done as written, stop and ask. Don't build workarounds.
12. Usefulness first: a change is worth doing only if it changes what is bought, held or avoided, or the expected return shown, and it passes its registered test. Don't do work whose only effect is that results look more plausible or better explained (normalizing medians, outlier labels, plausibility targets, a rule added because one name looked wrong).

## Commands
uv run python -m stockreport fetch --market cn|us|hk
uv run python -m stockreport run [--market cn|us|hk] [--no-notes]   # picks + notes + PDF
uv run python -m stockreport send [--test]                          # text summary + PDF to WeChat
uv run python -m stockreport listen                                 # keyword listener (launchd)
uv run python -m stockreport v3 [--market cn|us|hk] [--date D]      # valuation v3 (shadow) on a saved snapshot
uv run python -m stockreport track [--signal]                       # performance scorecard (--signal: v1/v3 signals on the snapshots)
uv run python -m stockreport verdict [CODE veto|confirm --until D --reason "..."]  # your verdicts (no args: list)
uv run python -m stockreport cleanup [--dry-run]                    # apply storage retention
uv run pytest
