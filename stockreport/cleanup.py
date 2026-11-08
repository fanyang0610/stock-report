"""Storage retention (PLAN.md Method section 11). Only ever deletes dated entries inside
data/raw, data/snapshots, reports and logs, and research folders (data/research/<market>/<code>) not used for a while."""

import logging
import shutil
from datetime import date, timedelta
from pathlib import Path

from stockreport.config import CONFIG, DATA, LOGS, REPORTS

log = logging.getLogger(__name__)


def size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


def expired(today: date) -> list[Path]:
    keep = CONFIG["retention"]
    out = []
    for folder, days in ((DATA / "raw", keep["raw"]), (DATA / "snapshots", keep["snapshots"]),
                         (REPORTS, keep["reports"]), (LOGS, keep["logs"])):
        cutoff = (today - timedelta(days=days)).isoformat()
        out += [p for p in sorted(folder.glob("????-??-??*")) if p.name[:10] < cutoff]
    cutoff = (today - timedelta(days=keep["research"])).isoformat()
    for stock in sorted((DATA / "research").glob("[a-z][a-z]/*")):  # by its newest file: the last time it was built
        newest = max((f.stat().st_mtime for f in stock.iterdir()), default=0)
        if stock.is_dir() and date.fromtimestamp(newest).isoformat() < cutoff:
            out.append(stock)
    return out


def cleanup(dry_run: bool = False, today: date | None = None) -> int:
    """Delete (or list) expired data; returns the total size of data/ + reports/ afterwards."""
    allowed = [(DATA / "raw").resolve(), (DATA / "snapshots").resolve(), REPORTS.resolve(), LOGS.resolve()] + [
        (DATA / "research" / m).resolve() for m in ("cn", "us", "hk")]
    freed = 0
    for path in expired(today or date.today()):
        if path.resolve().parent not in allowed:
            raise RuntimeError(f"refusing to delete outside the retention folders: {path}")
        size = size_of(path)
        freed += size
        print(f"{'would delete' if dry_run else 'deleted'} {path.relative_to(DATA.parent)} ({size / 1e6:.1f} MB)")
        if not dry_run:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    total = size_of(DATA) + size_of(REPORTS)
    print(f"{'would free' if dry_run else 'freed'} {freed / 1e6:.1f} MB; data/ + reports/ = {total / 1e6:.1f} MB")
    log.info("storage: data/ + reports/ = %.1f MB", total / 1e6)
    if total > CONFIG["storage"]["warn_gb"] * 1e9:
        log.warning("data/ + reports/ exceed %.1f GB", CONFIG["storage"]["warn_gb"])
    return total
