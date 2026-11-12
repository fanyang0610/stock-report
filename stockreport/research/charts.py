"""The research report's charts as inline SVG (no chart library): the price against the index, ten years of revenue
and margin (or ROE), the valuation's methods against the price and the street (a football field), and the P/E or P/B
against its own history."""

import math
from html import escape

import pandas as pd

W, H, PAD = 640, 220, (46, 16, 22, 34)  # width, height, padding left / top / right / bottom
LABEL = 200  # the football field's label column
BLUE, GREY, RED, GREEN, INK = "#2f54eb", "#9aa1ab", "#c41d1d", "#389e0d", "#1f2329"


def frame(body: str, h: int = H) -> str:
    return (f'<svg viewBox="0 0 {W} {h}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="PingFang SC, sans-serif" '
            f'font-size="11">{body}</svg>')


def scale(lo: float, hi: float, a: float, b: float):
    span = (hi - lo) or 1
    return lambda x: a + (x - lo) / span * (b - a)


def ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    step = 10 ** math.floor(math.log10((hi - lo) / n or 1))
    step *= next(m for m in (1, 2, 2.5, 5, 10) if (hi - lo) / (step * m) <= n)
    return [step * i for i in range(math.ceil(lo / step), math.floor(hi / step) + 1)]


def axis_y(lo, hi, y, fmt) -> str:
    out = ""
    for t in ticks(lo, hi):
        out += (f'<line x1="{PAD[0]}" x2="{W - PAD[2]}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="#eef0f3"/>'
                f'<text x="{PAD[0] - 6}" y="{y(t) + 4:.1f}" text-anchor="end" fill="{GREY}">{fmt(t)}</text>')
    return out


def line(xs, ys, color, width=1.6, dash="") -> str:
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" stroke-dasharray="{dash}"/>'


def legend(items, y=12) -> str:
    out, x = "", PAD[0]
    for label, color in items:
        out += f'<rect x="{x}" y="{y - 8}" width="10" height="3" fill="{color}"/><text x="{x + 14}" y="{y - 4}" fill="{INK}">{escape(label)}</text>'
        x += 24 + 12 * len(label)
    return out


def price(daily: pd.DataFrame, code: str, index_code: str, index_name: str) -> str:
    """The last two years, the stock and the index rebased to 100."""
    d = daily.pivot_table(index="date", columns="code", values="close").sort_index()
    d = d[[c for c in (code, index_code) if c in d]].dropna().tail(500)
    if len(d) < 20 or code not in d:
        return ""
    d = d / d.iloc[0] * 100
    lo, hi = float(d.min().min()) * 0.97, float(d.max().max()) * 1.03
    x, y = scale(0, len(d) - 1, PAD[0], W - PAD[2]), scale(lo, hi, H - PAD[3], PAD[1] + 8)
    xs = [x(i) for i in range(len(d))]
    body = axis_y(lo, hi, y, lambda t: f"{t:.0f}") + line(xs, [y(v) for v in d[code]], BLUE, 1.8)
    if index_code in d:
        body += line(xs, [y(v) for v in d[index_code]], GREY, 1.2)
    for i in range(0, len(d), max(len(d) // 6, 1)):
        body += f'<text x="{xs[i]:.1f}" y="{H - 12}" text-anchor="middle" fill="{GREY}">{d.index[i][:7]}</text>'
    return frame(body + legend([("本股", BLUE), (index_name, GREY)]))


def history(rows: list[dict], kind: str) -> str:
    """Revenue bars with the operating margin (financials: ROE) as a line, by fiscal year."""
    rows = [r for r in rows if r.get("revenue")]
    if len(rows) < 3:
        return ""
    fin = kind in ("bank", "insurer", "broker")
    key = "roe" if fin else "ebit_margin" if any(r.get("ebit_margin") is not None for r in rows) else "net_margin"
    rev = [r["revenue"] for r in rows]
    m = [r.get(key) for r in rows]
    unit, div = ("亿", 1e8) if max(rev) < 1e12 else ("万亿", 1e12)
    y = scale(0, max(rev) / div * 1.1, H - PAD[3], PAD[1] + 8)
    known = [v for v in m if v is not None]
    lo, hi = min(known + [0]), max(known + [0.01]) * 1.15
    y2 = scale(lo, hi, H - PAD[3], PAD[1] + 8)
    bw = (W - PAD[0] - PAD[2]) / len(rows)
    body = axis_y(0, max(rev) / div * 1.1, y, lambda t: f"{t:,.0f}" if div == 1e8 else f"{t:.1f}")
    pts = []
    for i, r in enumerate(rows):
        x0 = PAD[0] + i * bw
        body += (f'<rect x="{x0 + bw * 0.18:.1f}" y="{y(r["revenue"] / div):.1f}" width="{bw * 0.64:.1f}" '
                 f'height="{H - PAD[3] - y(r["revenue"] / div):.1f}" fill="#c7d2fe"/>'
                 f'<text x="{x0 + bw / 2:.1f}" y="{H - 12}" text-anchor="middle" fill="{GREY}">{r["period"][:4]}</text>')
        if m[i] is not None:
            pts.append((x0 + bw / 2, y2(m[i])))
            body += f'<text x="{x0 + bw / 2:.1f}" y="{y2(m[i]) - 6:.1f}" text-anchor="middle" fill="{RED}" font-size="10">{m[i]:.0%}</text>'
    body += line([p[0] for p in pts], [p[1] for p in pts], RED, 1.6)
    label = {"roe": "ROE", "ebit_margin": "营业利润率", "net_margin": "净利率"}[key]
    return frame(body + legend([(f"营收（{unit}{rows[-1].get('currency') or ''}）", "#c7d2fe"), (label, RED)]))


def football(val: dict, names: dict) -> str:
    """Each method's value a year from now as a bar, the fair value's bear to bull as a band, the price, the fair value,
    the 12-month target and the street's target as lines."""
    rows = [(names[m], val["methods"][m]["target"], w) for m, w in val["weights"].items()]
    rows += [("悲观 — 乐观情景", None, None)]
    fair, lo, hi_ = (val.get(f"fair_{a}") or val[b] for a, b in (("value", "target"), ("bear", "bear"), ("bull", "bull")))
    marks = [val["price"], val["target"], fair, lo, hi_] + [r[1] for r in rows if r[1] is not None]
    street = (val.get("street") or {}).get("target")
    hi = max(marks + ([street] if street else [])) * 1.08
    h = PAD[1] + 26 * len(rows) + 36
    x = scale(0, hi, LABEL, W - PAD[2] - 60)
    body = ""
    for i, (label, t, w) in enumerate(rows):
        yy = PAD[1] + 10 + i * 26
        body += f'<text x="{LABEL - 6}" y="{yy + 13}" text-anchor="end" fill="{INK}">{escape(label)}{f"（{w:.0%}）" if w else ""}</text>'
        if t is not None:
            body += (f'<rect x="{LABEL}" y="{yy}" width="{max(x(t) - LABEL, 1):.1f}" height="18" fill="#c7d2fe"/>'
                     f'<text x="{x(t) + 4:.1f}" y="{yy + 13}" fill="{INK}">{t:,.0f}</text>')
        else:
            body += (f'<rect x="{x(lo):.1f}" y="{yy}" width="{max(x(hi_) - x(lo), 1):.1f}" height="18" fill="#ffd8bf"/>'
                     f'<text x="{x(hi_) + 4:.1f}" y="{yy + 13}" fill="{INK}">{lo:,.0f} — {hi_:,.0f}</text>')
    bottom = PAD[1] + 10 + len(rows) * 26
    marks = [(v_, c_, l_) for v_, c_, l_ in ((val["price"], INK, "现价"), (val["target"], BLUE, "12 个月目标价"),
                                            (fair, "#722ed1", "合理价值"), (street, GREEN, "市场目标价")) if v_]
    for i, (value, color, label) in enumerate(sorted(marks)):  # labels on their own rows, left to right
        body += (f'<line x1="{x(value):.1f}" x2="{x(value):.1f}" y1="{PAD[1]}" y2="{bottom + 4 + 14 * i}" stroke="{color}" stroke-width="1.5" '
                 f'stroke-dasharray="{"" if color == INK else "4 3"}"/>'
                 f'<text x="{x(value) + (-4 if x(value) > W * 0.7 else 4):.1f}" y="{bottom + 14 + 14 * i}" fill="{color}" '
                 f'text-anchor="{"end" if x(value) > W * 0.7 else "start"}">{label} {value:,.0f}</text>')
    return frame(body, h + 14 * len(marks))


def band(series: dict, key: str, now: float | None) -> str:
    """The P/E (or P/B) by month over its own history, with its median and one standard deviation either side."""
    s = pd.Series(series.get(key) or [], index=series.get("month") or [], dtype=float).dropna()
    s = s[s > 0]
    if len(s) < 24:
        return ""
    med, sd = float(s.median()), float(s.std())
    lo, hi = max(float(s.min()) * 0.9, 0), float(s.max()) * 1.1
    x, y = scale(0, len(s) - 1, PAD[0], W - PAD[2]), scale(lo, hi, H - PAD[3], PAD[1] + 8)
    xs = [x(i) for i in range(len(s))]
    body = axis_y(lo, hi, y, lambda t: f"{t:.0f}" if hi > 10 else f"{t:.1f}")
    for v, dash in ((med, "4 3"), (med + sd, "2 3"), (med - sd, "2 3")):
        if lo < v < hi:
            body += line([xs[0], xs[-1]], [y(v), y(v)], GREY, 1, dash)
    body += line(xs, [y(v) for v in s], BLUE, 1.6)
    for i in range(0, len(s), max(len(s) // 6, 1)):
        body += f'<text x="{xs[i]:.1f}" y="{H - 12}" text-anchor="middle" fill="{GREY}">{s.index[i]}</text>'
    name = {"pe": "市盈率", "pb": "市净率"}[key]
    return frame(body + legend([(f"{name}（中位数 {med:.1f}，虚线为 ±1 个标准差）", BLUE)]))
