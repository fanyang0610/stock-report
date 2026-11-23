"""Stage 26: a margin gap that has lasted, and an A+H line too short to read its own margins."""

from datetime import date

import pandas as pd
import pytest

from stockreport.research import compare, fade, rating, value

KEEP = {"margin_keep": {"above": 0.8, "below": 0.6}, "lasting_keep": {"above": 0.95, "below": 0.9}}
K = {"ebit": 30.0, "shares": 10.0, "ind_margin": 0.1, "tax_effective": 0.25} | KEEP
CONS = {"eps": [2.25], "revenue": [100.0], "eps0": 2.25}


def sheet(margins):
    return {"valuation": {"ttm": {"revenue": 100.0, "ni": 22.5, "pretax": 30.0}, "balance": {}}, "summary": {},
            "history": [{"ebit_margin": x} for x in margins]}


def test_gap_spells_split_lasting_from_new():
    d = pd.DataFrame({"gap": [0.1] * 4, "later": [0.05] * 4, "start": ["2020"] * 4,
                      "prev1": [0.05, 0.01, 0.05, -0.04], "prev2": [0.04, 0.05, 0.01, 0.05]})
    lasting, new = fade.gap_spells(d, "above")
    assert list(lasting.index) == [0] and list(new.index) == [1, 3]  # row 2, two years on its side, is in neither
    lasting, new = fade.gap_spells(d.assign(gap=-0.1, prev1=-d["prev1"], prev2=-d["prev2"]), "below")
    assert list(lasting.index) == [0] and list(new.index) == [1, 3]


def test_margin_gaps_among_counts_the_chosen_companies_with_the_whole_tables_drift():
    years = [str(y) for y in range(2010, 2019)]
    m = pd.DataFrame({y: [0.10, 0.10, 0.10] for y in years}, index=["a", "b", "c"])
    m.loc["a", "2015"] = 0.20
    m.loc["b", "2015"] = 0.20
    among = pd.DataFrame({y: [True, False, True] for y in years}, index=m.index)
    d = fade.margin_gaps(m, 5, False, 3, "above", among=among)
    assert list(d.index) == ["a"] and d["gap"].iloc[0] == pytest.approx(0.10)


def stepped(years: int, first: int = 3) -> pd.DataFrame:
    """200 flat companies (no market drift) and 40 whose margin steps up 10 points for 3 years in a staggered year, then
    keeps 90% of the gap each year."""
    rows = {f"flat{n}": [0.10] * years for n in range(200)}
    for n in range(40):
        start = first + n % 3
        rows[f"c{n}"] = [0.10 if i < start else 0.20 if i <= start + 2 else 0.10 + 0.10 * 0.9 ** (i - start - 2)
                         for i in range(years)]
    return pd.DataFrame(rows, index=[str(2015 + y) for y in range(years)]).T


def test_lasting_keep_reads_only_the_decided_sides(monkeypatch):
    for fn in (fade.lasting_keep, fade.margin_keep):
        fn.cache_clear()
    monkeypatch.setattr(fade, "margin_table", lambda market: stepped(11))  # too short for the 8-year median's 3 horizons
    monkeypatch.setattr(fade, "LASTING_SIDES", {"cn": ("above",), "hk": ()})
    got = fade.lasting_keep("cn")
    assert got["above"] == pytest.approx(0.9, abs=0.001)  # so the 5 years' median before: the path's own rate
    assert got["below"] == pytest.approx(fade.margin_keep("cn")["below"], nan_ok=True)  # a side not decided: stage 14's
    fade.lasting_keep.cache_clear()
    assert fade.lasting_keep("hk") == pytest.approx(fade.margin_keep("hk"), nan_ok=True)  # no side: stage 14's rates
    for fn in (fade.lasting_keep, fade.margin_keep):
        fn.cache_clear()


def test_lasting_keep_reads_the_forecasts_8_year_median_when_the_history_allows(monkeypatch):
    seen, real = [], fade.margin_gaps
    def spy(m, window, current, *a, **kw):
        seen.append((window, current))
        return real(m, window, current, *a, **kw)
    for fn in (fade.lasting_keep, fade.margin_keep):
        fn.cache_clear()
    monkeypatch.setattr(fade, "margin_table", lambda market: stepped(17, first=6))
    monkeypatch.setattr(fade, "LASTING_SIDES", {"cn": ("above",)})
    fade.margin_keep("cn")
    monkeypatch.setattr(fade, "margin_gaps", spy)
    fade.lasting_keep("cn")
    assert set(seen) == {(8, True)}  # 17 years give the 8-year median 3 horizons: no fallback to the 5 years before
    for fn in (fade.lasting_keep, fade.margin_keep):
        fn.cache_clear()


@pytest.mark.parametrize("margins,lasting", [
    ([0.20] * 5 + [0.30] * 3, True),  # three reported years 10 points above the 8-year median
    ([0.20] * 6 + [0.30] * 2, False),  # two: a gap that may be a spike keeps the ordinary rate
    ([0.20] * 5 + [0.30, 0.215, 0.30], False),  # a year back within 3 points breaks the run
])
def test_a_lasting_gap_fades_at_its_own_rate(margins, lasting):
    p = value.paths(sheet(margins), K, "ordinary", CONS, 0.02)
    assert p["target_margin"] == pytest.approx(0.20) and p["margin_lasting"] is lasting
    keep = 0.95 if lasting else 0.8
    assert p["margin"][1:] == pytest.approx([0.2 + 0.1 * keep ** t for t in range(1, 10)])


def test_a_side_the_measurement_left_alone_is_not_called_lasting():
    k = K | {"lasting_keep": {"above": 0.8, "below": 0.9}}  # CN above: stage 14's rate stands
    p = value.paths(sheet([0.20] * 5 + [0.30] * 3), k, "ordinary", CONS, 0.02)
    assert p["margin_lasting"] is False and p["margin"][1] == pytest.approx(0.2 + 0.1 * 0.8)
    assert compare.margin_words(p) == "自身 8 年中位数"
    assert "持续 3 年" in compare.margin_words(value.paths(sheet([0.20] * 5 + [0.30] * 3), K, "ordinary", CONS, 0.02))


def test_a_short_line_reads_its_issuers_longer_line(monkeypatch):
    capital = {"equity": 80.0, "debt": 0.0, "cash": 0.0, "revenue": 100.0}
    a = sheet([0.25] * 8) | {"market": "cn", "kind": "company"}
    a["history"] = [x | capital | {"roic": 0.3} for x in a["history"]]
    h = sheet([0.30, 0.31]) | {"market": "hk", "kind": "company"}
    short = sheet([0.30, 0.31]) | {"market": "hk", "kind": "bank"}
    monkeypatch.setattr(rating, "other_lines", lambda x, today: [({"market": "cn", "code": "600276"}, a)])
    line = rating.long_line(h, date(2026, 11, 23))
    assert line["market"] == "cn" and line["s2c"] == pytest.approx(1.25) and len(line["ebit_margin"]) == 8
    assert value.line_rows(h, {"long_line": line}, "roic", 10).tolist() == [0.3] * 8  # the moat reads it too
    assert rating.long_line(short, date(2026, 11, 23)) is None  # another kind of company isn't the same accounts
    assert rating.long_line(a, date(2026, 11, 23)) is None  # its own 5 years stand

    k = K | {"ind_sales_to_capital": 1.07, "long_line": line, "mature_margin": 0.18}
    p = value.paths(h, k, "ordinary", CONS, 0.02)
    assert p["target_margin"] == pytest.approx(0.25) and p["margin_source"] == "other line's 8-year median"
    assert value.sales_to_capital(h, k, p["margin_source"]) == (pytest.approx(1.25), "its CN line's 5-year median")
    alone = value.paths(h, K | {"mature_margin": 0.18}, "ordinary", CONS, 0.02)  # without the other line it was young
    assert alone["target_margin"] == 0.18 and alone["margin_source"] == "profitable peers' median"
