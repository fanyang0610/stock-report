"""Research stage 12, part 2: the background queue (PLAN.md "The router"). The listener queues a request and sends the
acknowledgement; `research --queue`, started detached as the background review is, builds each report in turn and
sends its text summary and PDF, so the listener keeps polling while a report takes its ~15 s to 2 minutes. One worker
at a time (data/research/worker.lock) takes the requests in order from data/research/queue.json, so one company is
never built twice at once; a company already waiting isn't queued again, and one built today is resent from its saved
words (no DeepSeek call)."""

import fcntl
import json
import logging
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime

from stockreport import deliver
from stockreport.config import ROOT as PROJECT
from stockreport.research import ROOT, days, fresh, router

log = logging.getLogger(__name__)
QUEUE, QUEUE_LOCK, WORKER_LOCK = ROOT / "queue.json", ROOT / "queue.lock", ROOT / "worker.lock"


@contextmanager
def queue():
    """The queue {jobs, working}, locked while the block runs and saved after it."""
    ROOT.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        q = json.loads(QUEUE.read_text()) if QUEUE.exists() else {"jobs": [], "working": None}
        yield q
        tmp = QUEUE.with_suffix(".tmp")
        tmp.write_text(json.dumps(q, ensure_ascii=False))
        tmp.replace(QUEUE)


def minutes(line: dict, today: date) -> int:
    """The acknowledgement's estimate (stage 11's timings, warm 13-32 s, cold about a minute; an A+H company values
    both lines): 0 when built today, 1 with this week's data cached, else 2."""
    folder = ROOT / line["market"] / line["code"]
    if (folder / "report.json").exists() and json.loads((folder / "report.json").read_text())["date"] == today.isoformat():
        return 0
    return 1 if fresh(folder / "facts.json", days("statements")) else 2


def add(o: dict, rest: list[str], today: date) -> str:
    """Queue a request for the company `o` (router.issuer) and return the acknowledgement."""
    with queue() as q:
        waiting = ([q["working"]] if q["working"] else []) + q["jobs"]
        if any(j["key"] == o["key"] for j in waiting):
            return f"{router.label(o)}的报告已在生成中，稍后发出。"
        q["jobs"].append({"key": o["key"], "name": o["name"], "lines": o["lines"],
                          "asked": datetime.now().isoformat(timespec="seconds")})
    wait = minutes(o["lines"][0], today) + len(waiting)
    text = f"收到：{router.label(o)}。研究报告{'马上发出' if not wait else f'约 {wait} 分钟后发出'}" + (
        f"（前面还有 {len(waiting)} 份）。" if waiting else "。")
    if rest:
        text += f"\n一次只做一家公司：{'、'.join(f'「{x}」' for x in rest)}请单独再发一条。"
    return text


def start() -> None:
    """Start a worker in the background; it exits at once when one is running (that one takes the new request)."""
    subprocess.Popen([sys.executable, "-m", "stockreport", "research", "--queue"], cwd=PROJECT, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def work() -> int:
    """Answer the queued requests in order, then exit."""
    lock = open(WORKER_LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.info("a research worker is running")
        return 0
    with queue() as q:  # this worker holds the lock, so a job marked working was left by one that stopped
        stopped, q["working"] = q["working"], None
    if stopped:
        log.warning("research for %s was cut off by a stopped worker", stopped["name"])
        deliver.retry("text", lambda: deliver.send_text(f"抱歉，{stopped['name']} 的研究报告没能生成，请再发一次。"))
    while True:
        with queue() as q:
            if not q["jobs"]:
                lock.close()  # released while the queue is locked: a request queued after this starts a new worker
                return 0
            job = q["working"] = q["jobs"].pop(0)
        answer(job, date.today())
        with queue() as q:
            q["working"] = None


def answer(job: dict, today: date) -> None:
    """Build the report (its lead line, else the issuer's next) and send the text summary, then the PDF."""
    from stockreport.research import report
    started = time.monotonic()
    for line in job["lines"]:
        try:
            doc = report.built_today(line["market"], line["code"], today) or report.build(line["market"], line["code"], today)
            break
        except Exception:
            log.exception("research report for %s %s failed", line["market"].upper(), line["code"])
    else:
        deliver.retry("text", lambda: deliver.send_text(f"抱歉，{job['name']} 的研究报告这次没能生成（数据源出错），请稍后再试。"))
        return
    title = f"个股研究_{doc['name']}_{doc['code']}_{today:%Y%m%d}.pdf"
    if deliver.retry("research text", lambda: deliver.send_text(doc["summary"])):
        time.sleep(1)
        deliver.retry("research PDF", lambda: deliver.send_file(doc["pdf"], title=title))
    log.info("research for %s (%s) answered in %.0fs", job["name"], doc["code"], time.monotonic() - started)
