"""Command line: uv run python -m stockreport <command>."""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport import deliver, report
from stockreport.cleanup import cleanup
from stockreport.config import CONFIG, DATA, REPORTS, ROOT, setup_logging
from stockreport.fetch import fetch as fetch_market
from stockreport.listener import listen
from stockreport.pick import CSV_COLUMNS, pick, print_table
from stockreport.render import html_to_pdf, render_html, text_summary
from stockreport.render.testdata import test_report
from stockreport.score import score
from stockreport.universe import build_cn, build_hk, build_us
from stockreport.value import value


def discount_rate(market: str) -> tuple[float, str]:
    """r = latest 10-year government yield + the market's equity premium."""
    rates = pd.read_csv(DATA / "rates.csv", dtype={"date": str})
    latest = rates[rates["market"] == market].sort_values("date").iloc[-1]
    return latest["y10"] / 100 + CONFIG["value"]["equity_premium"][market], latest["date"]


def run(market: str, use_ai: bool) -> int:
    started, today = time.monotonic(), date.today()
    failed = fetch_market(market, today)
    universe, info = {"cn": build_cn, "us": build_us, "hk": build_hk}[market](today)
    r, rate_date = discount_rate(market)
    df = score(value(universe, r))
    df["r"], df["price_date"] = r, info["quote_date"]
    picks = pick(df)

    snap = DATA / "snapshots" / today.isoformat()
    snap.mkdir(parents=True, exist_ok=True)
    df.to_csv(snap / f"{market}.csv.gz", compression="gzip")
    out = REPORTS / today.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    picks[CSV_COLUMNS].to_csv(out / f"{market}_picks.csv", index=False, encoding="utf-8-sig")

    print(f"{market.upper()} data: quotes {info['quote_date']}, daily prices {info['price_date']}, "
          f"10y yield {rate_date} -> r = {r:.2%}")
    if failed:
        print(f"WARNING: fetch failed for {', '.join(failed)}; used the last cached data")
    print("Universe: " + " -> ".join(f"{k} {v}" for k, v in info["stages"].items()))
    for reason, codes in info["dropped"].items():
        if codes:
            print(f"  dropped {len(codes)} ({reason}): {' '.join(codes[:12])}{' ...' if len(codes) > 12 else ''}")
    print(f"Fair value: {df['fv_mid'].notna().sum()} of {len(df)} valued; "
          f"methods {df['method'].value_counts().to_dict()}")
    print_table(picks)
    print(f"\nWrote {(out / f'{market}_picks.csv').relative_to(ROOT)} and the snapshot "
          f"{(snap / f'{market}.csv.gz').relative_to(ROOT)}")
    pdf, summary = report.build(today, use_ai)
    print(f"Wrote {pdf.relative_to(ROOT)} ({pdf.stat().st_size // 1024} KB) and summary.txt "
          f"({len(summary.encode('utf-8'))} bytes)")
    cleanup()
    print(f"Done in {time.monotonic() - started:.0f}s")
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
        (summary, pdf), what, title = build_test(today), "TEST", f"股票报告_测试_{today:%Y%m%d}.pdf"
    else:
        found = report.newest()
        if not found:
            print("No report yet: run `run --market cn` first.")
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
    run_p = sub.add_parser("run", help="fetch, value, score, pick, write notes and the PDF")
    run_p.add_argument("--market", choices=["cn", "us", "hk"], default="cn")
    run_p.add_argument("--no-notes", action="store_true", help="template notes instead of DeepSeek")
    clean = sub.add_parser("cleanup", help="apply the storage retention periods")
    clean.add_argument("--dry-run", action="store_true", help="only list what would be deleted")
    args = parser.parse_args(argv)

    if args.command == "run":
        setup_logging()
        return run(args.market, not args.no_notes)
    if args.command == "listen":
        setup_logging(console=False)
        return listen()
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
