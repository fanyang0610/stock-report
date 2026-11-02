"""Keyword listener (PLAN.md Method section 9). launchd starts `listen` 10 s after the previous run ends;
each run long-polls the bot for about 55 s and answers the keyword with today's report from the newest lists, after
the results review has had its budget (PLAN.md, "Results review"): the text summary, then the PDF. What the budget
left is finished by a background `review`."""

import fcntl
import json
import logging
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone

from stockreport import deliver, report, track
from stockreport.config import CONFIG, DATA, ROOT
from stockreport.render import fit_bytes

log = logging.getLogger(__name__)
KEYWORDS = {"股票报告", "股票简报", "stock report", "stock brief"}
STATE, LOCK = DATA / "state.json", DATA / "listen.lock"
KEEP_IDS = 200
POLL_MS = 35_000  # longer than the server's ~18 s hold: a poll cut short by the client can delay a message
MAX_AGE_MIN = 30  # older keywords (e.g. sent while the Mac slept for hours) are logged, not answered


def is_keyword(text: str) -> bool:
    """A keyword on its own, ignoring case, extra spaces and trailing punctuation."""
    text = re.sub(r"[\s.,!?;:~。，！？；：…、～]+$", "", text.strip())
    return " ".join(text.split()).lower() in KEYWORDS


def age_minutes(received_at: str) -> float:
    sent = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - sent).total_seconds() / 60


def send_with_retry(what: str, send) -> bool:
    for attempt in (1, 2):
        try:
            send()
            return True
        except deliver.DeliveryError as e:
            log.warning("sending the %s failed (attempt %d/2): %s", what, attempt, e)
            time.sleep(3)
    log.error("gave up sending the %s", what)
    return False


def reply(today: date) -> None:
    started = time.monotonic()
    buys = None  # the fallback below sends a report built earlier: its buys aren't known for sure, so not logged
    try:
        pdf, summary, buys = report.fresh(today, CONFIG["review"]["budget"])
        day = today.isoformat()
    except (Exception, SystemExit) as e:  # SystemExit: no lists at all
        log.error("the reviewed report failed (%s); sending the newest built one", e)
        found = report.newest()
        if not found:
            send_with_retry("text", lambda: deliver.send_text("还没有生成过报告，请稍后再试。"))
            return
        day, pdf, summary = found
        if day != today.isoformat():
            summary = fit_bytes([f"（今天的报告还没生成，以下是 {day} 的报告）", *summary.splitlines()],
                                deliver.MAX_TEXT_BYTES)
    built = time.monotonic() - started
    if send_with_retry("text", lambda: deliver.send_text(summary)) and buys is not None:  # the text names every buy
        track.log_sent(today, buys)  # what was sent: the next report's "changes" line
    time.sleep(1)
    send_with_retry("PDF", lambda: deliver.send_file(pdf, title=f"股票报告_{day.replace('-', '')}.pdf"))
    log.info("replied with the %s report in %.0fs (review and build %.0fs)", day, time.monotonic() - started, built)
    subprocess.Popen([sys.executable, "-m", "stockreport", "review", "--background"], cwd=ROOT, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def listen(seconds: int = 40) -> int:
    """Start polls for `seconds` (each runs to the server's ~18 s hold, so a run lasts ~55 s),
    answering at most one keyword per poll."""
    DATA.mkdir(exist_ok=True)
    lock = open(LOCK, "w")
    try:  # only one process may poll the bot
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.info("another listener is running")
        return 0
    seen = json.loads(STATE.read_text())["seen"] if STATE.exists() else []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            messages = deliver.poll(POLL_MS)
        except deliver.DeliveryError as e:
            log.error("poll failed: %s", e)
            time.sleep(20)  # launchd restarts us 10 s after exit; don't retry a dead network every 10 s
            return 1
        replied = False
        for m in messages:
            if m["id"] in seen:
                continue
            seen = (seen + [m["id"]])[-KEEP_IDS:]
            tmp = STATE.with_suffix(".tmp")  # saved before replying, so a crash never sends twice
            tmp.write_text(json.dumps({"seen": seen}))
            tmp.replace(STATE)
            if not is_keyword(m["text"]) or replied:
                continue
            if (age := age_minutes(m["receivedAt"])) > MAX_AGE_MIN:
                log.warning("keyword from %.0f min ago not answered (older than %d min)", age, MAX_AGE_MIN)
                continue
            log.info("keyword %r received", m["text"])
            reply(date.today())
            replied = True
    return 0
