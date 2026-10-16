"""Paths, config.toml and logging."""

import logging
import tomllib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"

with open(ROOT / "config.toml", "rb") as f:
    CONFIG = tomllib.load(f)


def setup_logging() -> None:
    LOGS.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in (logging.FileHandler(LOGS / f"{date.today().isoformat()}.log", encoding="utf-8"),
                    logging.StreamHandler()):
        handler.setFormatter(fmt)
        root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
