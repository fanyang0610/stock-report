# stock-report: rules for coding agents

## Goal
On a WeChat keyword (股票报告 / 股票简报 / stock report / stock brief), reply within 30 s with exactly two messages: a text summary and a PDF report. Per market (US, HK, CN): a 20-name buy portfolio (买入组合; in the US next to an S&P 500 index fund holding half the money), a check of the names you hold (持仓检查: 继续持有 / 复核 / 卖出), 10 names to avoid (回避), and what to expect from the method's history. Each card shows the price, the value, quality and momentum grades, why the name is there, the key risk, the cost of one board lot, the review's finding, an AI note and a re-check date. The aim is moderate: beat the index fund over the year you hold the names, at about the market's level of risk.

## Read first
docs/PLAN.md has the method, the stages and the current status. The earlier plans (v1-v3 with Phases 1-13, and the 2026-10-22 plan) are in docs/archive/ as reference only, not as paths to follow. Do only the stage you were asked to do.

## Layout
stockreport/fetch/ (one module per data source) → universe.py → signals.py (the value, quality and momentum components, percentiles) → score.py (families, score, grades, card lines) → lists.py (buys, holdings, avoid; `hold`) → report.py + render/ (HTML → PDF, text summary) → deliver.py; plus listener.py, track.py and history.py (the multi-year tables).
crosscheck.py compares each market's key figures with a second source and raises day-over-day drift alarms. The event layer (fetch/events.py market-wide filing feeds → events.py classification and abnormal-move labels) and the deep-dive lane (deepdive.py: triggers, fetch/filings.py, DeepSeek questionnaire, quotes.py verification; verdicts.py for your vetoes and confirms) feed the results review. backtest/ (outside the app) holds the backtest harness and data builders; docs/BACKTEST.md has its results and commands.
Stage 2 adds review.py (the results review; notes.py and deepdive.py, not called by the stage-1 build, feed it).
bridge/wechat.mjs is the WeChat helper (Node). data/ is the daily cache and reports/ the outputs; both are git-ignored.

## Rules
1. Free data only. Follow the Storage section in docs/PLAN.md: raw responses are temporary, only small extracted tables are kept, and cleanup runs after every build. data/ + reports/ must stay under 2 GB.
2. All numbers come from code + data. The LLM never writes forecasts, prices, fair values or scores. DeepSeek only writes short notes from numbers we give it, and may flag a pick to be swapped for the next one. In the deep-dive lane DeepSeek may extract facts from primary filings, each with the quoted sentence; code checks the quote against the filing text and takes the number from the quote.
3. Rank every stock with one rule-based score per market: the value, quality and momentum families defined in docs/PLAN.md, equal weights, each market's ingredients taken from published research on that market and never tuned to our backtest. No hand-typed per-company assumptions. Per-company research only through the results review, the bounded deep-dive lane (rule-triggered, at most 3 per market per day, cached per filing) and user verdicts (veto or confirm with an expiry, never numbers). a-stock-data is fine as an endpoint reference.
4. Lists are rank-based and always shown: 20 buys (at most 2 per sector) and 10 avoid names per market. A market whose build fails shows its last good lists with their date. Never fail the whole report.
5. Missing or inconsistent data: drop the stock and take the next one. Never invent data or hard-code tickers into the picks.
6. Keep it small: no frameworks, "gates", "contracts", ledgers, hashes, attestations or handoff documents. Target under 6,000 lines of app Python (stockreport/), with files under 400 lines. Ask before adding a dependency.
7. Tests: pytest for the scoring math and the parsers (using small saved samples), plus one end-to-end dry run. Nothing more.
8. One stage per session. Before reporting a stage done, run the stage-reviewer agent (.claude/agents/stage-reviewer.md) with fresh context and include its answers. When the stage's "done when" is met, update the status in docs/PLAN.md, commit, then stop and report in 10 lines or fewer.
9. Ask me before: sending any WeChat message, creating or pushing to GitHub repos, installing launchd jobs, or adding any paid service.
10. Never print, log or commit secrets from .env.
11. If something is ambiguous or a stage can't be done as written, stop and ask. Don't build workarounds. Investment-method choices are the agent's to make from published evidence, with the reason written in docs/PLAN.md: don't hand the user choices they can't judge, and don't call something the user's goal unless they said it.
12. Usefulness first: a change is worth doing only if it changes what is bought, held or avoided, or what the report says to expect, or fixes a fault. The method changes only to fix a bug or to follow new published evidence, never because a backtest number or one name looked wrong. No pass/fail gates on shipping and no test whose result would change nothing. Don't do work whose only effect is that results look more plausible or better explained (normalizing medians, outlier labels, plausibility targets).

## Commands
uv run python -m stockreport fetch --market cn|us|hk
uv run python -m stockreport run [--market cn|us|hk]                # fetch + score + lists + PDF (no DeepSeek)
uv run python -m stockreport send [--test]                          # text summary + PDF to WeChat
uv run python -m stockreport listen                                 # keyword listener (launchd)
uv run python -m stockreport hold [CODE [--date D] [--sold]]        # your holdings (no args: list)
uv run python -m stockreport track                                  # performance scorecard
uv run python -m stockreport verdict [CODE veto|confirm --until D --reason "..."]  # your verdicts (no args: list)
uv run python -m stockreport cleanup [--dry-run]                    # apply storage retention
uv run pytest
