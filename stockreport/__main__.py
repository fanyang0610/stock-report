"""Command line: uv run python -m stockreport <command>."""

import argparse
import fcntl
import logging
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from stockreport import crosscheck, deliver, history, lists, report, review, signals, track, verdicts
from stockreport.cleanup import cleanup
from stockreport.config import CONFIG, DATA, REPORTS, ROOT, setup_logging
from stockreport.fetch import eastmoney, profiles
from stockreport.fetch import fetch as fetch_market
from stockreport.listener import listen
from stockreport.render import html_to_pdf, render_html, text_summary
from stockreport.render.testdata import test_report
from stockreport.score import score
from stockreport.universe import build_cn, build_hk, build_us

log = logging.getLogger("stockreport")
SHOW = ["rank", "code", "name", "sector", "price", "g_value", "g_quality", "g_growth", "g_momentum", "score", "why"]


def scored(market: str, today: date) -> tuple[pd.DataFrame, dict]:
    """The market's universe with the score (the long-run components from the annual reports public by today; CN: 扣非
    TTM and SUE from the reports noticed by today, next year's consensus now and 91 days ago from the research reports;
    US: profit and book to common shareholders)."""
    universe, info = {"cn": build_cn, "us": build_us, "hk": build_hk}[market](today)
    universe["price_date"] = info["quote_date"]
    universe = universe.join(signals.long_run(history.YEARS[market](), today.isoformat()))
    cn = None
    if market == "cn":
        table = pd.read_csv(eastmoney.CN_DEDUCT, dtype={"code": str, "period": str, "notice_date": str})
        cn = signals.cn_deduct(table, today.isoformat())
        universe = universe.join(cn)
        if eastmoney.CN_REPORTS.exists():  # next year: after the first fiscal year without an annual report
            reports = pd.read_csv(eastmoney.CN_REPORTS, dtype={"code": str, "publish": str})
            bonus = pd.read_csv(eastmoney.DIVIDENDS, dtype={"code": str, "ex_date": str}).reindex(
                columns=["code", "ex_date", "bonus"])
            year = universe["period"].str[:4].astype(int) + np.where(universe["period"].str.endswith("12-31"), 2, 1)
            universe = universe.join(signals.cn_revisions(reports, bonus, year, today.isoformat())).assign(rev_year=year)
    if market == "us":
        pref = history.us_preferred(universe, today)[["pref_share", "pref_div_share"]]
        universe = universe.join(pref).fillna({"pref_share": 0.0, "pref_div_share": 0.0})
    return score(universe, market, cn), info


def build_market(market: str, today: date) -> None:
    """Fetch (failed steps keep their cache), score and list one market -> its lists CSV and snapshot."""
    failed = fetch_market(market, today)
    report.save_failed(today, market, failed)
    df, info = scored(market, today)
    out_lists = lists.build(df, market, today)
    try:  # the results review's sources and passages (no DeepSeek: the review runs when you ask for a report)
        review.gather(market, out_lists, today)
    except Exception:
        log.exception("%s review sources failed; the review shows 审核暂不可用 for this market", market.upper())
    try:  # what each company does, for the cards (a failure leaves the line out)
        profiles.update(market, out_lists["code"].tolist(), today)
    except Exception:
        log.exception("%s company profiles failed", market.upper())
    try:  # alarms only: a failure is logged and never stops the build
        drift = crosscheck.drift(df, market, today)
    except Exception:
        log.exception("%s drift alarms failed", market.upper())
        drift = ["Drift alarms failed (see the log)"]

    snap = DATA / "snapshots" / today.isoformat()
    snap.mkdir(parents=True, exist_ok=True)
    out = REPORTS / today.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    out_lists.to_csv(out / f"{market}_lists.csv", index=False, encoding="utf-8-sig")
    df.to_csv(snap / f"{market}.csv.gz", compression="gzip")

    print(f"{market.upper()} data: quotes {info['quote_date']}, daily prices {info['price_date']}")
    if failed:
        print(f"WARNING: fetch failed for {', '.join(failed)}; used the last cached data")
    print("Universe: " + " -> ".join(f"{k} {v}" for k, v in info["stages"].items()))
    for reason, codes in info["dropped"].items():
        if codes:
            print(f"  dropped {len(codes)} ({reason}): {' '.join(codes[:12])}{' ...' if len(codes) > 12 else ''}")
    print("\n".join(info.get("checks", [])))
    have = {c[2:]: f"{df[c].notna().mean():.0%}" for c in df.columns if c.startswith("p_")}
    print(f"Scored {len(df)}; components present: {have}")
    print("\n".join(drift))
    show = out_lists.assign(score=out_lists["score"].round(3), weight=out_lists["weight"].map("{:.1%}".format))
    for name, words in (("buy", "why"), ("hold", "reason"), ("sell", "weak")):
        part = show.loc[show["list"] == name, SHOW[:-1] + [words, "risk"]]
        print(f"\n== {name} ({len(part)})\n" + part.to_string(index=False))
    print(f"\nWrote {(out / f'{market}_lists.csv').relative_to(ROOT)} and the snapshot {(snap / f'{market}.csv.gz').relative_to(ROOT)}")


def run(markets: list[str]) -> int:
    """Build each market, then the report once; a market that fails keeps its newest earlier lists. No DeepSeek
    calls: the results review runs when you ask for a report (`review`, `send`, the keyword)."""
    started, today, crashed = time.monotonic(), date.today(), []
    for market in markets:
        try:
            build_market(market, today)
        except Exception:
            log.exception("%s build failed; the report shows its newest earlier lists", market.upper())
            crashed.append(market)
    pdf, summary, _ = report.build(today)
    print(f"Wrote {pdf.relative_to(ROOT)} ({pdf.stat().st_size // 1024} KB) and summary.txt "
          f"({len(summary.encode('utf-8'))} bytes)")
    cleanup()
    print(f"Done in {time.monotonic() - started:.0f}s" + (f"; failed: {', '.join(crashed)}" if crashed else ""))
    return 1 if crashed else 0


def review_all(background: bool) -> int:
    """The results review without a time limit (after a keyword reply, `--background`: what its budget left): sources
    gathered for any lists without them, every name reviewed; then, unless in the background, the report written and
    summed up. One at a time (data/review.lock)."""
    started, today = time.monotonic(), date.today()
    lock = open(DATA / "review.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.info("another review is running")
        return 0
    lists, sources = {}, {}
    for market in report.MARKETS:
        if path := report.latest_lists(market, today):
            rows = report.read_lists(path)
            lists[market] = rows
            sources[market] = review.load_sources(market, path.parent.name) or review.gather(market, rows, today, path.parent.name)
            try:
                profiles.update(market, rows["code"].tolist(), today)
            except Exception:
                log.exception("%s company profiles failed", market.upper())
    states = review.run(lists, sources, today, None)
    if background:
        log.info("background review done in %.0fs", time.monotonic() - started)
        return 0
    pdf, summary, _ = report.build(today, states)
    print(review.stats(states))
    print(f"\n{summary}\n\nWrote {pdf.relative_to(ROOT)} in {time.monotonic() - started:.0f}s")
    return 0


def build_test(today: date) -> tuple[str, Path]:
    out = ROOT / "reports" / today.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    report = test_report(today)
    pdf = html_to_pdf(render_html(report, out / "test_report.html"), out / "test_report.pdf")
    summary = text_summary(report, deliver.MAX_TEXT_BYTES)
    (out / "test_summary.txt").write_text(summary, encoding="utf-8")
    print(f"Built {pdf.relative_to(ROOT)} ({pdf.stat().st_size // 1024} KB) and "
          f"test_summary.txt ({len(summary.encode('utf-8'))} bytes)")
    return summary, pdf


def wait_for_window(minutes: int = 5) -> bool:
    """True once the bot may reply. If the window is stale, poll until you text the bot."""
    st = deliver.status()
    if st.get("ready"):
        return True
    age = st.get("lastInboundAgeSeconds")
    ago = f"{age / 3600:.0f} h ago" if age is not None else "unknown"
    print(f"No fresh reply window (your last message to the bot: {ago}). "
          f"Text the bot anything, e.g. 'hi'. Waiting up to {minutes} min...", flush=True)
    deadline = time.monotonic() + minutes * 60
    while time.monotonic() < deadline:
        if deliver.poll(25000):
            break
    return bool(deliver.status().get("ready"))


def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def send(test: bool, assume_yes: bool) -> int:
    """Send the TEST report, or the newest real report, after confirming."""
    if test:
        today = date.today()
        (summary, pdf), what, title, buys = build_test(today), "TEST", f"股票报告_测试_{today:%Y%m%d}.pdf", None
    else:
        today = date.today()
        pdf, summary, buys = report.fresh(today, CONFIG["review"]["budget"])
        what, title = f"the {today} (reviewed)", f"股票报告_{today:%Y%m%d}.pdf"
    if not wait_for_window():
        print("Still no reply window. Text the bot, then run this again.")
        return 1
    print("Reply window is open.")
    if not confirm(f"Send 2 WeChat messages ({what} text summary + PDF)? [y/N] ", assume_yes):
        print("Not sent.")
        return 1
    deliver.send_text(summary)
    if buys is not None:  # the text names every buy: the record of what was sent (the "changes" line)
        track.log_sent(today, buys)
    print("1/2 text summary sent", flush=True)
    time.sleep(1)
    deliver.send_file(pdf, title=title)
    print("2/2 PDF sent. Check your phone: did both arrive, and does the PDF open?")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stockreport")
    sub = parser.add_subparsers(dest="command", required=True)
    send_p = sub.add_parser("send", help="send the text summary + PDF to WeChat")
    send_p.add_argument("--test", action="store_true", help="send the TEST report (fake data)")
    send_p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    sub.add_parser("listen", help="answer the WeChat keyword for ~55 s (launchd restarts it 10 s after it ends)")
    fetch = sub.add_parser("fetch", help="update the cached data for a market")
    fetch.add_argument("--market", choices=["cn", "us", "hk"], required=True)
    run_p = sub.add_parser("run", help="fetch, score, list and write the report (PDF + text summary)")
    run_p.add_argument("--market", choices=["cn", "us", "hk"], help="one market (default: all three)")
    sub.add_parser("track", help="average return of past lists vs each market's index")
    rev = sub.add_parser("review", help="the results review of the newest lists (the one DeepSeek step, no time "
                                        "limit), then the report")
    rev.add_argument("--background", action="store_true", help="finish what a keyword reply's budget left; no report")
    verdict = sub.add_parser("verdict", help="your veto or confirm for a stock (no arguments: list those in force)")
    verdict.add_argument("code", nargs="?", help="ticker, e.g. 600519, 00700 or AAPL")
    verdict.add_argument("action", nargs="?", choices=["veto", "confirm"])
    verdict.add_argument("--until", help="last day it applies, YYYY-MM-DD (it also ends at the next report)")
    verdict.add_argument("--reason", default="", help="why, in a few words (shown on the report)")
    clean = sub.add_parser("cleanup", help="apply the storage retention periods")
    clean.add_argument("--dry-run", action="store_true", help="only list what would be deleted")
    args = parser.parse_args(argv)

    if args.command == "run":
        setup_logging()
        return run([args.market] if args.market else ["cn", "us", "hk"])
    if args.command == "track":
        return track.scorecard()
    if args.command == "review":
        setup_logging(console=not args.background)
        return review_all(args.background)
    if args.command == "listen":
        setup_logging(console=False)
        return listen()
    if args.command == "verdict":
        if not args.code:
            return verdicts.show(date.today())
        if not args.action or not args.until:
            parser.error("verdict needs a code, veto|confirm and --until")
        print(verdicts.add(args.code, args.action, args.until, args.reason, date.today()))
        return 0
    if args.command == "cleanup":
        cleanup(dry_run=args.dry_run)
        return 0
    if args.command == "fetch":
        setup_logging()
        failed = fetch_market(args.market)
        if failed:
            print(f"Failed steps (cached data kept): {', '.join(failed)}", file=sys.stderr)
        return 1 if failed else 0
    if args.command == "send":
        try:
            return send(args.test, args.yes)
        except deliver.DeliveryError as e:
            print(f"Delivery failed: {e}", file=sys.stderr)
            return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
