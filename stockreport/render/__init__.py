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
    """The WeChat message: what to do today (holdings to sell or re-check, buys the review removed), then per market the
    buys by name (新 marks a name new since the last report), the holdings to re-check, the avoid names and the 预期
    line, and a pointer to the PDF for the cards. Without recorded holdings the sells and re-checks are a neutral hold
    rating of the names recommended before. Over 90% of `limit` the names gone from the list become a count, then the 新 marks go (the count of new names
    stays), then the holdings to re-check, then those to sell become counts; fit_bytes is the last guard."""
    for level in (0, 1, 2, 3, 4):
        text = "\n".join(summary_lines(report, level))
        if len(text.encode("utf-8")) <= limit * 0.9:
            break
    return fit_bytes(text.splitlines(), limit)


def summary_lines(report: dict, level: int = 0) -> list[str]:
    join = lambda items: "、".join(p["short"] for p in items)
    markets = report["markets"]
    lines = [f"{'【测试数据】' if report.get('test') else ''}{report['title']} {report['date']}"]
    if report.get("test"):
        lines.append("以下为虚构数据，仅用于测试发送。")
    sells = [f"{m['short']} " + (join(m["sell"]) if level < 4 else f"{len(m['sell'])} 只") for m in markets if m["sell"]]
    checks = [f"{m['short']} {len(m['check'])} 只" for m in markets if m["check"]]
    removed = [f"{m['short']} {p['short']}（{p['reason'].split('（')[0].split('：')[0]}）→ "
               f"{p.get('replaced_by') or p['status'].removeprefix('由 ').removesuffix(' 替换')}" for m in markets for p in m["removed"]]
    lines += ["", "今天要做的："]
    if any(m["holdings"] for m in markets) or report.get("recorded", True):
        lines += [*([] if report.get("recorded", True) else ["（持有建议：发给你的推荐里、今天不在名单的股票，如果你持有）"]),
                  "· 卖出：" + ("；".join(sells) if sells else "无"),
                  "· 复核：" + ("、".join(checks) + "（评分下滑或有负面消息，看原因再决定）" if checks else "无")]
    else:
        lines.append("· 持有建议：暂无")
    lines += ["· 审核剔除：" + "；".join(removed)] if removed else []
    for m in markets:
        new = {p["ticker"] for p in (m.get("changes") or {}).get("new", [])}
        lines += ["", f"【{m['short']}】数据 {m['data_date'][5:]}，买入 {len(m['buys'])} 只，每只等额，持有到 {m.get('recheck') or '满 12 个月'}："]
        if m.get("stale"):
            lines.append(f"注意：{m['stale']}")
        lines.append("、".join(p["short"] + ("（新）" if p["ticker"] in new and level < 2 else "") for p in m["buys"]))
        if ch := m.get("changes"):
            gone = ("移出 " + "、".join(ch["gone"]) if level < 1 else f"移出 {len(ch['gone'])} 只") if ch["gone"] else "没有移出"
            lines.append(f"与 {ch['since'][5:]} 相比：新进 {len(new)} 只，{gone}")
        flagged = [p for k in ("holdings", "avoid") for p in m[k] if p.get("review_kind") == "hard"]
        if flagged:
            lines.append("审核发现：" + "；".join(f"{p['short']}（{p['review'].split('（')[0].split('：', 1)[1]}）" for p in flagged))
        if m.get("review"):
            lines.append(m["review"])
        if m["check"]:
            short = level > 2 or len(m["check"]) > 8  # a long re-check list stays in the PDF
            lines.append(f"复核 {len(m['check'])} 只" + ("，名单见 PDF" if short else "：" + join(m["check"])))
        if m["avoid"]:
            lines.append("回避：" + join(m["avoid"]))
        lines.append("预期：" + m["expect"]["short"])
    return lines + ["", "每家公司做什么、为什么选、风险、一手多少钱和审核结果见 PDF。历史模拟不代表未来，不构成投资建议。"]
