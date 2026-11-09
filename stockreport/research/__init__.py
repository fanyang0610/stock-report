"""Single-stock research (PLAN.md "Single-stock research", stages 9-12). Stage 9: per-stock data fetched on demand into
data/research/<market>/<code>/ (small extracted tables; raw responses are parsed in memory), Damodaran's datasets,
the listings name resolution reads, and the fact sheet (`research CODE --facts`)."""

import json
import logging
import math
import time
from datetime import date
from pathlib import Path

import pandas as pd

from stockreport.config import CONFIG, DATA
from stockreport.fetch import write

log = logging.getLogger(__name__)
ROOT = DATA / "research"
# One row per report period, in the reporting currency: the fiscal year (months 12) or the year to date. Shared by the
# three markets' statements so the checks and the fact sheet read one layout. equity is the parent's, with its preferred
# shares and perpetual securities (pref), which book value per common share leaves out.
KEYS = ["revenue", "cogs", "gp", "sga", "rd", "op_income", "interest", "pretax", "tax", "ni", "ni_core", "eps", "da",
        "ocf", "capex", "div_paid", "buyback", "sbc", "assets", "cur_assets", "cur_liab", "cash", "receivables",
        "inventory", "ppe", "goodwill", "intangibles", "liabilities", "debt", "lt_debt", "equity", "pref", "minority",
        "retained", "shares", "contract_liab", "cip"]
STATEMENT = ["period", "months", "currency", "notice"] + KEYS


def folder(market: str, code: str) -> Path:
    path = ROOT / market / code
    path.mkdir(parents=True, exist_ok=True)
    return path


def fresh(path: Path, days: int) -> bool:
    """A cached table written within `days` days (0: today only)."""
    return path.exists() and (date.today() - date.fromtimestamp(path.stat().st_mtime)).days <= days


def cached(path: Path, days: int, make):
    """The table or dict at `path` (.csv.gz or .json) if fresh, else make() saved there. A failed refresh keeps the
    stale cache when there is one (rule 4: never fail the whole report)."""
    if fresh(path, days):
        return load(path)
    try:
        value = make()
    except Exception as e:
        if path.exists():
            log.warning("%s: refresh failed (%s); its cache of %s is used", path, e, date.fromtimestamp(path.stat().st_mtime))
            return load(path)
        raise
    save(path, value)
    return value


def save(path: Path, value) -> None:
    if isinstance(value, pd.DataFrame):
        write(value, path)
    else:
        path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=1))


def load(path: Path):
    if path.suffix == ".json":
        return json.loads(path.read_text())
    return pd.read_csv(path, dtype={"code": str, "period": str, "date": str, "month": str, "notice": str, "org_code": str})


def clean(value):
    """JSON-safe: NaN and inf become null, numpy numbers plain floats."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    return None if isinstance(value, float) and not math.isfinite(value) else value


def num(value) -> float | None:
    """A number from a source field ("1,234", "", None, "-"): None when it isn't one."""
    try:
        out = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def days(key: str) -> int:
    return CONFIG["research"][key]


def stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


CUR = {"CNY": "元", "HKD": "港元", "USD": "美元"}


def number(x) -> bool:
    return isinstance(x, (int, float)) and x == x


def pct(x, sign: bool = False, digits: int = 1) -> str:
    return "-" if not number(x) else f"{x:+.{digits}%}" if sign else f"{x:.{digits}%}"


def times(x) -> str:
    return "-" if not number(x) else f"{x:.1f}倍"


def money(x, currency: str | None = None) -> str:
    """An amount in Chinese units: 1.82万亿元, 1,816亿元, 3.5亿美元."""
    if not number(x):
        return "-"
    unit, a = CUR.get(currency, currency or ""), abs(x)
    text = f"{x / 1e12:.2f}万亿" if a >= 1e12 else f"{x / 1e8:,.0f}亿" if a >= 1e10 else f"{x / 1e8:.1f}亿" if a >= 1e8 \
        else f"{x / 1e4:,.0f}万" if a >= 1e4 else f"{x:,.2f}"
    return text + unit


def price(x, currency: str | None = None) -> str:
    return "-" if not number(x) else f"{x:,.2f}{CUR.get(currency, currency or '')}"
