# stock-report

A daily stock-rating report for China A-shares, US and Hong Kong stocks, delivered over WeChat.

Text the bot **股票报告**, **股票简报**, **stock report** or **stock brief** and within about 30 seconds you get two
messages: a short text summary and a PDF report. For each market the report rates stocks the way a sell-side analyst
does, without looking at anyone's portfolio:

| Rating | How many | Meaning |
|---|---|---|
| 买入 Buy | 20 | Expected to beat the market. Chosen from the whole liquid market, sectors in proportion to the market, equal amounts. |
| 持有 Hold | 10 | Expected to be roughly stable. |
| 卖出 Sell | 10 | Expected to lag the market. |

Each stock gets a card: price, grades for value, quality, growth and momentum, why it is on the list, the key risk, the
cost of one board lot, what the review found, a short AI note and a date to check it again. The report also says what
each rating's history suggests you should expect.

**The aim is moderate:** beat the market's index fund over the year you hold the names, at about the market's level of
risk. Published factor portfolios like this one have beaten their index by a few percent a year on average and lost to
it in roughly 4 years out of 10. No list is a guarantee. **This is not investment advice.**

## How it works

```
fetch/  ──►  universe  ──►  signals  ──►  score  ──►  lists  ──►  review  ──►  report (PDF + text)  ──►  WeChat
free data    800 largest    value, quality,  one score   Buy/Hold/  DeepSeek     render/              deliver.py
per market   liquid stocks  growth, momentum per market  Sell       checks picks
```

1. **Data.** Free sources only (exchanges, SEC, Eastmoney, Tencent, Yahoo and others), cached in `data/`.
2. **Score.** Every stock gets one rule-based score: four families (value, quality, growth, momentum) with equal
   weights, each stock ranked against its own sector. The ingredients come from published research for each market,
   not from tuning to our own backtest.
3. **Lists.** The best scores fill the Buy list sector by sector; Hold and Sell follow fixed rules.
4. **Review.** The only AI step. DeepSeek reads each listed company's recent filings, report passages and headlines and
   flags problems, each backed by a quote. Code checks every quote; a hard red flag (fraud, insolvency, an agreed sale
   of the company…) swaps the pick for the next one. The AI writes words only, never numbers. If DeepSeek is
   unavailable, the report still goes out, marked 审核暂不可用.
5. **Deliver.** The report is rendered to PDF with headless Chrome and sent through a WeChat bot.

The full method, with the research behind each choice, is in [docs/PLAN.md](docs/PLAN.md).

### Runs on its own

Nothing at runtime needs Claude Code. Two macOS launchd jobs do the work:

- **06:30 daily build** (`run`): fetch, score, lists, the review's sources and an unreviewed PDF. A few minutes on
  weekdays, ~30 minutes on Sundays (weekly fundamentals).
- **Keyword listener** (`listen`): when you text the keyword, it runs the review and sends the text and PDF.

## Setup

Requirements: macOS, Google Chrome, Node 18+, [uv](https://docs.astral.sh/uv/).

1. `uv sync`
2. Install the `cli-wechat-bridge` npm package globally (`~/.npm-global/lib/node_modules/`) and log in to the bot
   with `wechat-setup`.
3. Create `.env` in the project root (never committed):

   | Variable | Needed for |
   |---|---|
   | `EQUITYSIGNALS_WECHAT_RECIPIENT_ID` | who receives the report |
   | `DEEPSEEK_API_KEY` | the results review |
   | `SEC_USER_AGENT` | US filings (your name and contact email, required by SEC) |
   | `FRED_API_KEY` | US rates |

4. First data load: `uv run python -m stockreport fetch --market cn` (and `us`, `hk`). The first run backfills about
   13 months of prices and takes ~40 minutes per market.
5. Install the launchd jobs (below).

## Usage

```bash
uv run python -m stockreport run                  # all markets: fetch, score, lists -> reports/<date>/
uv run python -m stockreport run --market us      # one market (others keep their newest lists)
uv run python -m stockreport review               # results review (DeepSeek), then the reviewed PDF + summary
uv run python -m stockreport send                 # review, then send to WeChat (asks first); --test sends fake data
uv run python -m stockreport track                # scorecard: each month's picks vs the index fund
uv run python -m stockreport verdict              # list your verdicts in force
uv run python -m stockreport verdict 600519 veto --until 2026-12-31 --reason "..."   # keep a name off Buy and Hold
uv run python -m stockreport research 600519 --facts   # one stock's fact sheet -> data/research/<market>/<code>/facts.json
uv run python -m stockreport cleanup --dry-run    # what retention would delete, and disk use
node bridge/wechat.mjs status                     # is the bot's reply window open?
uv run pytest
```

The WeChat bot can only reply for a while after you last messaged it: if `status` says it isn't ready, text it first.
List sizes, thresholds, retention periods and the DeepSeek model are set in [config.toml](config.toml).

**Refreshing the "what to expect" numbers** (occasionally, after a daily build):
`uv run python -m backtest.run build cn|us|hk`, then `uv run python -m backtest.qvm frame cn|us|hk`, then
`uv run python -m backtest.qvm run cn|us|hk`. Details in [docs/BACKTEST.md](docs/BACKTEST.md), section 24.

### launchd jobs

```bash
cp launchd/com.stockreport.daily.plist launchd/com.stockreport.listen.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.stockreport.daily.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.stockreport.listen.plist
```

Remove with `launchctl bootout gui/$(id -u)/com.stockreport.daily` (or `.listen`). The listener polls for ~55 s and
launchd restarts it 10 s later, so a keyword waits at most ~15 s; only one process may poll the bot. The daily build
runs at 06:30 Mac time (China Standard Time); a run missed during sleep starts on wake. Logs: `logs/<date>.log`,
`logs/<date>-daily.log`, crashes in `logs/launchd-*.log`.

## Project layout

```
stockreport/          the app (Python, ~5,800 lines)
  fetch/              one module per data source
  universe.py         which stocks are scored
  signals.py          value, quality, growth and momentum ingredients
  score.py            families, score, grades, card lines
  lists.py            Buy, Hold, Sell
  review.py           the results review (DeepSeek), with passages.py, notes.py, quotes.py, events.py, verdicts.py
  report.py, render/  HTML -> PDF and the text summary
  deliver.py          WeChat sending; listener.py answers the keyword
  track.py            scorecard; history.py multi-year tables; crosscheck.py second-source checks; cleanup.py retention
bridge/wechat.mjs     Node helper for the WeChat bot
backtest/             backtest harness and data builders (not part of the app)
launchd/              the two launchd jobs
tests/                pytest: scoring math, parsers, one end-to-end dry run
data/ reports/ logs/  caches and outputs (git-ignored, kept under 2 GB)
```

## Documentation

| File | What it holds |
|---|---|
| [docs/PLAN.md](docs/PLAN.md) | The method, the research behind it, the stages and their status. The main reference. |
| [docs/BACKTEST.md](docs/BACKTEST.md) | Backtest results and the commands that produce them. |
| [AGENTS.md](AGENTS.md) | Rules for coding agents working on the project (`CLAUDE.md` links to it). |
| [docs/archive/](docs/archive/) | Earlier plans and reviews (v1–v3 engines, the 2026-10-22 plan). Reference only. |

## Versions and releases

Versions follow `MAJOR.MINOR.PATCH` and live as git tags with notes on the
[Releases page](https://github.com/fanyang0610/stock-report/releases). `v0.x` are the earlier valuation engines,
kept as history; `v1.0.0` (2026-11-02) is the first release of the current method.

A GitHub Action ([.github/workflows/release.yml](.github/workflows/release.yml)) runs on every push to `main` and
releases a new version when the pushed commits change the app. The size of the bump follows how much the change matters
to what you get:

| Level | When | Example |
|---|---|---|
| **major** | The method or the meaning of the ratings changes | a new ranking method; lists rebuilt on a different rule |
| **minor** | A new capability, or a change to what is bought, held, sold or what the report says to expect | a stage completed; a new score ingredient |
| **patch** | A fix that keeps the method | a data parsing fix; a review rule corrected |
| **none** | Nothing the app does changes | docs, tests, backtest scripts |

A commit can state its level with a trailer line `Release: major|minor|patch|none`. Without one, the Action infers it:
a commit starting "Stage *n*" that changes app files is minor, any other change to app files (`stockreport/`,
`bridge/`, `launchd/`, `config.toml`, `pyproject.toml`, `uv.lock`) is patch, everything else is none. The largest level
in a push wins. Preview locally with `bash .github/release.sh --dry-run`.

## Maintaining

- Rules for changes are in [AGENTS.md](AGENTS.md): free data only, numbers from code never from the AI, keep the app
  under ~9,500 lines with files under 400, one stage per session.
- Storage: raw downloads are temporary, only small extracted tables are kept, and `cleanup` runs after every build.
- Secrets stay in `.env`; never print, log or commit them.
