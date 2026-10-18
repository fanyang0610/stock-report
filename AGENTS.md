# stock-report: rules for coding agents

## Goal
On a WeChat keyword (股票报告 / 股票简报 / stock report / stock brief), reply within 30 s with exactly two messages: a text summary and a PDF report of 45 stocks. The 45 are US, HK and CN × buy 买入 / hold 持有 / sell 卖出 × 5. Each card shows price, intrinsic value, expected return, confidence, upside, two drivers, key risk, an AI note and a re-check trigger, and for regime breaks our persistence probability (the valuation v2 cards arrive in Phase 10; until then the card shows the peer fair-value range).

## Read first
docs/PLAN.md has the method, the phases and the current status. Do only the phase you were asked to do.

## Layout
stockreport/fetch/ (one module per data source) → universe.py → value.py → score.py → pick.py → notes.py (DeepSeek) → render/ (HTML → PDF) → deliver.py; plus listener.py and track.py.
Valuation v2 runs in shadow mode after pick.py (Phase 8, docs/PLAN.md Method 12): history.py → engine.py → regime.py → anchors.py → shadow.py.
bridge/wechat.mjs is the WeChat helper (Node). data/ is the daily cache and reports/ the outputs; both are git-ignored.

## Rules
1. Free data only. Follow the Storage section in docs/PLAN.md: raw responses are temporary, only small extracted tables are kept, and cleanup runs after every build. data/ + reports/ must stay under 2 GB.
2. All numbers come from code + data. The LLM never writes forecasts, prices, fair values or scores. DeepSeek only writes short notes from numbers we give it, and may flag a pick to be swapped for the next one. In the deep-dive lane DeepSeek may extract facts from primary filings, each with the quoted sentence; code checks the quote against the filing text and takes the number from the quote.
3. Value every stock with one rule-based engine (intrinsic residual-income value, peer and own-history anchors), calibrated by backtest. No hand-typed per-company assumptions. Per-company research only through the bounded deep-dive lane (rule-triggered, at most 3 per market per day, cached per filing) and user verdicts (veto or confirm with an expiry, never numbers). a-stock-data is fine as an endpoint reference.
4. Buckets are rank-based: always 5 per cell. A cell short of strong candidates shows the next-ranked names marked 低信心 (low conviction). Never fail the whole report.
5. Missing or inconsistent data: drop the stock and take the next one. Never invent data or hard-code tickers into the picks.
6. Keep it small: no frameworks, "gates", "contracts", ledgers, hashes, attestations or handoff documents. Target under 6,000 lines of app Python (stockreport/), with files under 400 lines. Ask before adding a dependency.
7. Tests: pytest for the valuation/scoring math and the parsers (using small saved samples), plus one end-to-end dry run. Nothing more.
8. One phase per session. When its "done when" is met, update the status in docs/PLAN.md, commit, then stop and report in 10 lines or fewer.
9. Ask me before: sending any WeChat message, creating or pushing to GitHub repos, installing launchd jobs, or adding any paid service.
10. Never print, log or commit secrets from .env.
11. If something is ambiguous or a phase can't be done as written, stop and ask. Don't build workarounds.

## Commands
uv run python -m stockreport fetch --market cn|us|hk
uv run python -m stockreport run [--market cn|us|hk] [--no-notes]   # picks + notes + PDF
uv run python -m stockreport send [--test]                          # text summary + PDF to WeChat
uv run python -m stockreport listen                                 # keyword listener (launchd)
uv run python -m stockreport v2 [--market cn|us|hk] [--date D]      # valuation v2 (shadow) on a saved snapshot
uv run python -m stockreport track                                  # performance scorecard
uv run python -m stockreport cleanup [--dry-run]                    # apply storage retention
uv run pytest
