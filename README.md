# stock-report

Text the WeChat bot "股票报告" / "股票简报" / "stock report" / "stock brief" and get back a short
text summary plus a PDF of 45 stocks (US, HK, CN × buy / hold / sell × 5), picked by valuing each
market in peer groups. Free data only. Method, phases and status: [docs/PLAN.md](docs/PLAN.md).
Rules for coding agents: [AGENTS.md](AGENTS.md).

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
uv run python -m stockreport run                 # CN, US and HK: fetch, value, pick, DeepSeek notes -> reports/<date>/report.pdf + summary.txt
uv run python -m stockreport run --market us     # one market, then the report (other markets: their newest picks)
uv run python -m stockreport run --no-notes      # same with template notes (no DeepSeek calls)
uv run python -m stockreport track               # average return of past picks (data/picks.csv) vs each market's index
uv run python -m stockreport send                # send the newest report's text + PDF (asks first); --test sends fake data
uv run python -m stockreport listen              # answer the keyword for ~55 s (launchd restarts it 10 s after it ends)
uv run python -m stockreport cleanup --dry-run   # what retention would delete, and data/ + reports/ size
node bridge/wechat.mjs status                    # is the bot's reply window open?
uv run pytest
```
Weights, thresholds, retention periods and the DeepSeek model are in `config.toml`.

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
- `stockreport/`: `fetch/` (one module per source) → `universe.py` → `value.py` → `score.py` → `pick.py` →
  `notes.py` (DeepSeek, CNINFO titles) → `report.py` + `render/` (HTML, PDF, text summary); `deliver.py` talks
  to WeChat; `listener.py` answers the keyword; `track.py` logs picks and prints the scorecard; `cleanup.py` applies retention
- `bridge/wechat.mjs`: Node helper with the commands `status`, `poll-messages`, `notify`, `notify-batch`, `send-file`, `send-image`
- `data/`, `reports/`, `logs/`: caches and outputs (git-ignored)

The bot can only reply for a while after you last messaged it, so text it first if `status` says it isn't ready.
Not investment advice.
