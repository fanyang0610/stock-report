"""Command line: uv run python -m stockreport <command>."""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

from stockreport import deliver
from stockreport.render import html_to_pdf, render_html, text_summary
from stockreport.render.testdata import test_report

ROOT = Path(__file__).resolve().parent.parent


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


def send_test(assume_yes: bool) -> int:
    today = date.today()
    summary, pdf = build_test(today)
    if not wait_for_window():
        print("Still no reply window. Text the bot, then run this again.")
        return 1
    print("Reply window is open.")
    if not confirm("Send 2 WeChat messages (TEST text summary + TEST PDF)? [y/N] ", assume_yes):
        print("Not sent.")
        return 1
    deliver.send_text(summary)
    print("1/2 text summary sent", flush=True)
    time.sleep(1)
    deliver.send_file(pdf, title=f"股票报告_测试_{today:%Y%m%d}.pdf")
    print("2/2 PDF sent. Check your phone: did both arrive, and does the PDF open?")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stockreport")
    sub = parser.add_subparsers(dest="command", required=True)
    send = sub.add_parser("send", help="send the text summary + PDF to WeChat")
    send.add_argument("--test", action="store_true", help="send the TEST report (fake data)")
    send.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    if args.command == "send":
        if not args.test:
            print("Only `send --test` exists until Phase 3.")
            return 2
        try:
            return send_test(args.yes)
        except deliver.DeliveryError as e:
            print(f"Delivery failed: {e}", file=sys.stderr)
            return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
