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
  later phases also use `DEEPSEEK_API_KEY`, `FRED_API_KEY`, `FMP_API_KEY`, `SEC_USER_AGENT`, `TUSHARE_TOKEN`.
- `uv sync`

## Commands
```
uv run python -m stockreport send --test         # build the TEST report and send text + PDF (asks first)
uv run python -m stockreport send --test --yes   # same, without the prompt
node bridge/wechat.mjs status                    # is the bot's reply window open?
uv run pytest
```
Later phases add `fetch`, `run`, `send`, `listen`, `track` and `cleanup` (see AGENTS.md).

## Layout
- `stockreport/`: Python package (`deliver.py` talks to WeChat; `render/` builds the HTML, PDF and text summary)
- `bridge/wechat.mjs`: Node helper with the commands `status`, `poll-messages`, `notify`, `notify-batch`, `send-file`, `send-image`
- `data/`, `reports/`, `logs/`: caches and outputs (git-ignored)

The bot can only reply for a while after you last messaged it, so text it first if `status` says it isn't ready.
Not investment advice.
