"""Report rendering: Jinja2 HTML → PDF via headless Chrome, plus the WeChat text summary."""

import subprocess
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent),
    autoescape=select_autoescape(["html", "j2"]),
)
_env.filters["pct"] = lambda x: f"{x:+.1%}"
_env.filters["num"] = lambda x: f"{x:,.2f}"
_env.filters["pct0"] = lambda x: f"{x:.0%}"


def render_html(report: dict, out: Path) -> Path:
    html = _env.get_template("report.html.j2").render(r=report)
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
    """Per market: the data date, the 预期 line's first sentence, the top 10 buys with their share and grades, what the results
    review removed or flagged, the holdings that need action, and the avoid names; the PDF has the cards."""
    lines = [f"{'【测试数据】' if report.get('test') else ''}{report['title']} {report['date']}"]
    if report.get("test"):
        lines.append("以下为虚构数据，仅用于测试发送。")
    for m in report["markets"]:
        lines += ["", f"【{m['name']}】数据 {m['data_date']}，{m['currency']}"]
        if m.get("stale"):
            lines.append(f"注意：{m['stale']}")
        if m.get("expect"):
            lines.append("预期：" + m["expect"][0])
        lines.append(f"买入组合前 10（共 {len(m['buys'])} 只，从{m.get('index', '指数')}里选，按比例买入，持有 12 个月）：")
        for p in m["buys"][:10]:
            g = p["grades"]
            lines.append(f"{p['rank']}. {p['ticker']} {p['name']} {p.get('share', '')} 价{g['价值']}质{g['质量']}动{g['动量']}")
        if m.get("removed"):
            lines.append("审核剔除：" + "；".join(f"{p['name'] or p['ticker']}（{p['reason'].split('（')[0]}）" for p in m["removed"]))
        flagged = [p for k in ("holdings", "avoid") for p in m[k] if (p.get("review") or "").startswith(("审核：", "数据存疑"))]
        if flagged:
            lines.append("审核发现：" + "；".join(f"{p['name'] or p['ticker']}（{p['review'].split('（')[0].split('：', 1)[1]}）"
                                                for p in flagged))
        if m.get("review"):
            lines.append(m["review"])
        if m["holdings"]:
            counts = {s: [h["name"] or h["ticker"] for h in m["holdings"] if h["status"] == s] for s in ("继续持有", "复核", "卖出")}
            lines.append("持仓检查：" + "；".join(f"{s} {len(v)}" + (f"（{'、'.join(v)}）" if s != "继续持有" and v else "")
                                            for s, v in counts.items() if v))
        if m["avoid"]:
            lines.append("回避：" + "、".join(p["name"] for p in m["avoid"]))
    lines += ["", "详见 PDF。非投资建议。"]
    return fit_bytes(lines, limit)
