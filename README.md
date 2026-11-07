# stock-report

Text the WeChat bot "股票报告" / "股票简报" / "stock report" / "stock brief" and get back a short
text summary plus a PDF: per market (CN, US, HK) three ratings, as a sell-side analyst rates stocks: 20 Buy (the
buy portfolio: each sector's best scores across the whole liquid market, sector places by free-float share, equal
amounts), 10 Hold and 10 Sell, ranked on value, quality, growth and momentum (Stockopedia- and Seeking Alpha-style,
equal family weights, each stock against its sector). Free data only. Method, stages and status:
[docs/PLAN.md](docs/PLAN.md). Rules for coding agents: [AGENTS.md](AGENTS.md).

## Runs on its own
Nothing here needs Claude Code: close it and the project keeps running.
- 06:30 every day, launchd runs `run`: fetch, score, the three lists, the review's sources (filing titles, headlines and
  the passages code cuts from each listed name's latest periodic report) and an unreviewed PDF. No AI.
- When you text the keyword, the listener (launchd) runs the results review, then sends the text and the PDF.
- The results review is the only AI step, on DeepSeek (`DEEPSEEK_API_KEY` in `.env`): one call per listed name that
  screens (findings that quote a source; code checks each quote, and a hard red flag swaps a Buy or Hold name for the
  next one) and comments (the AI note and a one-line company description, words only). If DeepSeek is down or the key
  is missing, the report still goes out, marked 审核暂不可用.
- By hand, when you want: `verdict` (veto or confirm a name), `track` (the scorecard), and refreshing the 预期
  (what-to-expect) numbers from the history: `uv run python -m backtest.run build cn|us|hk`, then
  `uv run python -m backtest.qvm frame cn|us|hk`, then `uv run python -m backtest.qvm run cn|us|hk` (after a daily
  build; docs/BACKTEST.md section 24).

## Setup
- macOS with Google Chrome (used headless to print the PDF), Node 18+ and [uv](https://docs.astral.sh/uv/).
- The `cli-wechat-bridge` npm package installed globally at `~/.npm-global/lib/node_modules/`
  and logged in to the bot (`wechat-setup`).
- `.env` in the project root (never committed) with at least `EQUITYSIGNALS_WECHAT_RECIPIENT_ID`;
  later phases also use `DEEPSEEK_API_KEY`, `FRED_API_KEY`, `SEC_USER_AGENT` (name + contact email, required by SEC), `TUSHARE_TOKEN`.
- `uv sync`

## Commands
```
uv run python -m stockreport fetch --market cn   # update data/ (first run backfills ~13 months of prices, ~40 min)
uv run python -m stockreport run                 # CN, US and HK: fetch, score, lists -> reports/<date>/report.pdf + summary.txt
uv run python -m stockreport run --market us     # one market, then the report (other markets: their newest lists)
uv run python -m stockreport review              # the results review (DeepSeek), then the reviewed PDF + summary
uv run python -m stockreport track               # average return of past lists (data/picks.csv) vs each market's index
uv run python -m stockreport send                # review, then send the text + PDF (asks first); --test sends fake data
uv run python -m stockreport listen              # answer the keyword for ~55 s (launchd restarts it 10 s after it ends)
uv run python -m stockreport verdict 600519 veto --until 2026-12-31 --reason "..."  # keep a name off Buy and Hold
uv run python -m stockreport verdict             # list the verdicts in force (they end at their date or the next report)
uv run python -m stockreport cleanup --dry-run   # what retention would delete, and data/ + reports/ size
node bridge/wechat.mjs status                    # is the bot's reply window open?
uv run pytest
```
List sizes, thresholds, retention periods and the DeepSeek model are in `config.toml`.

## Keyword listener (launchd)
`launchd/com.stockreport.listen.plist` runs `listen` with the project's `.venv` Python: each run polls for ~55 s
and launchd starts the next one 10 s after it ends, so a keyword waits at most ~15 s. Only one process may poll
the bot, so stop any other listener on the same bot first. Install / remove:
```
cp launchd/com.stockreport.listen.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.stockreport.listen.plist
launchctl bootout gui/$(id -u)/com.stockreport.listen
```
Replies are logged in `logs/<date>.log`; crashes land in `logs/launchd-listen.log`.

## Daily build (launchd)
`launchd/com.stockreport.daily.plist` runs `run` (all three markets) at 06:30 by the Mac's clock (China
Standard Time). It never polls the bot, so it runs alongside the listener. Daily runs take a few minutes;
Sundays (weekly fundamentals and consensus) ~30 min. A run missed while the Mac sleeps starts when it wakes.
Output goes to `logs/<date>-daily.log`. Install / remove:
```
cp launchd/com.stockreport.daily.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.stockreport.daily.plist
launchctl bootout gui/$(id -u)/com.stockreport.daily
```

## Layout
- `stockreport/`: `fetch/` (one module per source) → `universe.py` → `signals.py` → `score.py` → `lists.py` →
  `report.py` + `render/` (HTML, PDF, text summary); `deliver.py` talks to WeChat; `listener.py` answers the keyword;
  `track.py` logs the lists and prints the scorecard; `cleanup.py` applies retention; `review.py` is the results review
  (the one DeepSeek call per name), with `passages.py` (periodic-report passages, cut by code), `notes.py` (the card
  text it reads, the note and line it writes) and `quotes.py` (the quote checks)
- `bridge/wechat.mjs`: Node helper with the commands `status`, `poll-messages`, `notify`, `notify-batch`, `send-file`, `send-image`
- `data/`, `reports/`, `logs/`: caches and outputs (git-ignored)

The bot can only reply for a while after you last messaged it, so text it first if `status` says it isn't ready.
Not investment advice.
