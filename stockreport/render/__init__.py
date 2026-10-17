"""Report rendering: Jinja2 HTML → PDF via headless Chrome, plus the WeChat text summary."""

import subprocess
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BUCKETS = [("buy", "买入"), ("hold", "持有/不追高"), ("sell", "卖出/回避")]

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(["html", "j2"]),
)
_env.filters["pct"] = lambda x: f"{x:+.1%}"
_env.filters["num"] = lambda x: f"{x:,.2f}"


def render_html(report: dict, out: Path) -> Path:
    html = _env.get_template("report.html.j2").render(r=report, buckets=BUCKETS)
    out.write_text(html, encoding="utf-8")
    return out


def html_to_pdf(html: Path, pdf: Path) -> Path:
    # --no-pdf-header-footer drops Chrome's own date/URL/page-number lines (Chrome 155 still honours it).
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [CHROME, "--headless", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
             "--no-pdf-header-footer", f"--print-to-pdf={pdf.resolve()}", html.resolve().as_uri()],
            check=True, capture_output=True, timeout=120,
        )
    if not pdf.exists() or pdf.stat().st_size == 0:
        raise RuntimeError(f"Chrome produced no PDF at {pdf}")
    return pdf


def fit_bytes(lines: list[str], limit: int) -> str:
    """Join lines, dropping whole lines from the end until the text fits in `limit` UTF-8 bytes."""
    text = "\n".join(lines)
    if len(text.encode("utf-8")) <= limit:
        return text
    tail = "…（已截断，完整内容见 PDF）"
    while lines and len("\n".join(lines + [tail]).encode("utf-8")) > limit:
        lines = lines[:-1]
    return "\n".join(lines + [tail])


def text_summary(report: dict, limit: int = 4000) -> str:
    """One line per pick: 代码 名称 动作 现价→公允价 空间%, grouped by market and bucket."""
    lines = [f"{'【测试数据】' if report.get('test') else ''}{report['title']} {report['date']}"]
    if report.get("test"):
        lines.append("以下为虚构数据，仅用于测试发送。")
    for m in report["markets"]:
        lines += ["", f"{m['name']}（数据 {m['data_date']}，{m['currency']}）"]
        if m.get("stale"):
            lines.append(f"注意：{m['stale']}")
        for key, label in BUCKETS:
            picks = [p for p in m["picks"] if p["bucket"] == key]
            if not picks:
                continue
            lines.append(f"〔{label}〕")
            for p in picks:
                flag = " 低信心" if p.get("low_conviction") else ""
                lines.append(f"{p['ticker']} {p['name']} {p['action']} "
                             f"{p['price']:,.2f}→{p['fv_mid']:,.2f} {p['upside']:+.1%}{flag}")
        for ai, label in ((True, "AI 标记后替换："), (False, "其他市场已入选、不重复列出：")):
            out = [s["out"].split(" ", 1)[-1] for s in m.get("swaps", []) if s.get("ai", True) == ai]
            if out:
                lines.append(label + "、".join(out))
    lines += ["", "详见 PDF。非投资建议。"]
    return fit_bytes(lines, limit)
