"""Command line: uv run python -m stockreport <command>."""

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport import crosscheck, deliver, history, lists, report, signals, track, verdicts
from stockreport.cleanup import cleanup
from stockreport.config import DATA, REPORTS, ROOT, setup_logging
from stockreport.fetch import eastmoney
from stockreport.fetch import fetch as fetch_market
from stockreport.listener import listen
from stockreport.render import html_to_pdf, render_html, text_summary
from stockreport.render.testdata import test_report
from stockreport.score import score
from stockreport.universe import build_cn, build_hk, build_us

log = logging.getLogger("stockreport")
SHOW = ["rank", "code", "name", "sector", "price", "g_value", "g_quality", "g_momentum", "score", "why"]


def scored(market: str, today: date) -> tuple[pd.DataFrame, dict]:
    """The market's universe with the score (CN: 扣非 TTM and SUE from the reports noticed by today; US: profit and
    book to common shareholders)."""
    universe, info = {"cn": build_cn, "us": build_us, "hk": build_hk}[market](today)
    universe["price_date"] = info["quote_date"]
    cn = None
    if market == "cn":
        table = pd.read_csv(eastmoney.CN_DEDUCT, dtype={"code": str, "period": str, "notice_date": str})
        cn = signals.cn_deduct(table, today.isoformat())
        universe = universe.join(cn)
    if market == "us":
        pref = history.us_preferred(universe, today)[["pref_share", "pref_div_share"]]
        universe = universe.join(pref).fillna({"pref_share": 0.0, "pref_div_share": 0.0})
    return score(universe, market, cn), info


def build_market(market: str, today: date) -> None:
    """Fetch (failed steps keep their cache), score and list one market -> its lists CSV and snapshot."""
    failed = fetch_market(market, today)
    report.save_failed(today, market, failed)
    df, info = scored(market, today)
    dropped = {code: reason for reason, codes in info["dropped"].items() for code in codes}
    out_lists = lists.build(df, market, today, dropped)
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
    show = out_lists.assign(score=out_lists["score"].round(3))
    for name, words in (("buy", "why"), ("avoid", "weak")):
        part = show.loc[show["list"] == name, SHOW[:-1] + [words, "risk"]]
        print(f"\n== {name} ({len(part)})\n" + part.to_string(index=False))
    held = show[show["list"] == "holding"]
    if len(held):
        print("\n== holdings\n" + held[["code", "name", "since", "status", "reason"]].to_string(index=False))
    print(f"\nWrote {(out / f'{market}_lists.csv').relative_to(ROOT)} and the snapshot {(snap / f'{market}.csv.gz').relative_to(ROOT)}")


def run(markets: list[str]) -> int:
    """Build each market, then the report once; a market that fails keeps its newest earlier lists. No DeepSeek
    calls: the results review comes with stage 2."""
    started, today, crashed = time.monotonic(), date.today(), []
    for market in markets:
        try:
            build_market(market, today)
        except Exception:
            log.exception("%s build failed; the report shows its newest earlier lists", market.upper())
            crashed.append(market)
    pdf, summary = report.build(today)
    print(f"Wrote {pdf.relative_to(ROOT)} ({pdf.stat().st_size // 1024} KB) and summary.txt "
          f"({len(summary.encode('utf-8'))} bytes)")
    cleanup()
    print(f"Done in {time.monotonic() - started:.0f}s" + (f"; failed: {', '.join(crashed)}" if crashed else ""))
    return 1 if crashed else 0


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
        (summary, pdf), what, title = build_test(today), "TEST", f"股票报告_测试_{today:%Y%m%d}.pdf"
    else:
        found = report.newest()
        if not found:
            print("No report yet: run `run` first.")
            return 1
        day, pdf, summary = found
        what, title = f"the {day}", f"股票报告_{day.replace('-', '')}.pdf"
    if not wait_for_window():
        print("Still no reply window. Text the bot, then run this again.")
        return 1
    print("Reply window is open.")
    if not confirm(f"Send 2 WeChat messages ({what} text summary + PDF)? [y/N] ", assume_yes):
        print("Not sent.")
        return 1
    deliver.send_text(summary)
    print("1/2 text summary sent", flush=True)
    time.sleep(1)
    deliver.send_file(pdf, title=title)
    print("2/2 PDF sent. Check your phone: did both arrive, and does the PDF open?")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stockreport")
    sub = parser.add_subparsers(dest="command", required=True)
    send = sub.add_parser("send", help="send the text summary + PDF to WeChat")
    send.add_argument("--test", action="store_true", help="send the TEST report (fake data)")
    send.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    sub.add_parser("listen", help="answer the WeChat keyword for ~55 s (launchd restarts it 10 s after it ends)")
    fetch = sub.add_parser("fetch", help="update the cached data for a market")
    fetch.add_argument("--market", choices=["cn", "us", "hk"], required=True)
    run_p = sub.add_parser("run", help="fetch, score, list and write the report (PDF + text summary)")
    run_p.add_argument("--market", choices=["cn", "us", "hk"], help="one market (default: all three)")
    sub.add_parser("track", help="average return of past lists vs each market's index")
    hold = sub.add_parser("hold", help="record a stock you hold (not the index fund; no arguments: list them); "
                                       "the next `run` checks it")
    hold.add_argument("code", nargs="?", help="ticker, e.g. 600519, 00700 or AAPL")
    hold.add_argument("--date", help="the day you bought it, YYYY-MM-DD (default: today)")
    hold.add_argument("--sold", action="store_true", help="remove it")
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
    if args.command == "hold":
        print(lists.hold(args.code, args.date, args.sold, date.today()))
        return 0
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
