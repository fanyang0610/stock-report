"""The WeChat listener (PLAN.md Method section 9, "The router"). launchd starts `listen` 10 s after the previous run
ends; each run long-polls the bot for about 55 s. The keyword (layer 1, no AI) gets today's report from the newest
lists, after the results review has had its budget (PLAN.md, "Results review"): the text summary, then the PDF; what
the budget left is finished by a background `review`. Any other message goes to the router (research/router.py:
an exact code or name, DeepSeek, a numbered question kept open in data/state.json); a research request gets an
acknowledgement now and its text summary and PDF from the background queue (research/jobs.py)."""

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
from stockreport.research import jobs, router

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


def save_state(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    tmp.replace(STATE)


def route(text: str, state: dict, today: date) -> bool:
    """A message that isn't the keyword: the router's decision, logged and answered; True when it asks for the
    screening report (the caller sends it, at most once a poll)."""
    pending = state.get("pending")
    if pending and age_minutes(pending["asked"]) > CONFIG["router"]["pending_minutes"]:
        pending = None
    d = router.route(text, pending)
    log.info("message %r: %s (layer %d)%s", text[:80], d["action"], d["layer"],
             f" {d['issuer']['name']} {d['issuer']['lines'][0]['code']}" if d["action"] == "research" else "")
    if d["action"] == "ask":
        state["pending"] = {"asked": datetime.now(timezone.utc).isoformat(), "text": d["text"], "options": d["options"]}
    else:
        state.pop("pending", None)
    save_state(state)
    if d["action"] == "screening":
        return True
    text = jobs.add(d["issuer"], d["rest"], today) if d["action"] == "research" else d["text"]
    deliver.retry("text", lambda: deliver.send_text(text))
    if d["action"] == "research":
        jobs.start()
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
            deliver.retry("text", lambda: deliver.send_text("还没有生成过报告，请稍后再试。"))
            return
        day, pdf, summary = found
        if day != today.isoformat():
            summary = fit_bytes([f"（今天的报告还没生成，以下是 {day} 的报告）", *summary.splitlines()],
                                deliver.MAX_TEXT_BYTES)
    built = time.monotonic() - started
    if deliver.retry("text", lambda: deliver.send_text(summary)) and buys is not None:  # the text names every buy
        track.log_sent(today, buys)  # what was sent: the next report's "changes" line
    time.sleep(1)
    deliver.retry("PDF", lambda: deliver.send_file(pdf, title=f"股票报告_{day.replace('-', '')}.pdf"))
    log.info("replied with the %s report in %.0fs (review and build %.0fs)", day, time.monotonic() - started, built)
    subprocess.Popen([sys.executable, "-m", "stockreport", "review", "--background"], cwd=ROOT, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def listen(seconds: int = 40) -> int:
    """Start polls for `seconds` (each runs to the server's ~18 s hold, so a run lasts ~55 s), answering every
    message and the screening report at most once a poll."""
    DATA.mkdir(exist_ok=True)
    lock = open(LOCK, "w")
    try:  # only one process may poll the bot
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.info("another listener is running")
        return 0
    state = json.loads(STATE.read_text()) if STATE.exists() else {"seen": []}
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
            if m["id"] in state["seen"]:
                continue
            state["seen"] = (state["seen"] + [m["id"]])[-KEEP_IDS:]
            save_state(state)  # saved before replying, so a crash never sends twice
            if (age := age_minutes(m["receivedAt"])) > MAX_AGE_MIN:
                log.warning("message from %.0f min ago not answered (older than %d min)", age, MAX_AGE_MIN)
                continue
            screening = is_keyword(m["text"])
            if not screening:
                try:
                    screening = route(m["text"], state, date.today())
                except Exception:
                    log.exception("message %r could not be routed", m["text"][:80])
                    deliver.retry("text", lambda: deliver.send_text("这条消息暂时没能处理，请稍后再发一次。"))
            if not screening or replied:
                continue
            log.info("screening report asked for by %r", m["text"])
            reply(date.today())
            replied = True
    return 0
