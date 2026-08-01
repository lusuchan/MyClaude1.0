"""Tests for the renderer.

The renderer is the last thing between the data and the reader, so what
matters here is that every number reaching the page is formatted from the
snapshot and that missing values degrade to a dash rather than a crash.
"""

from __future__ import annotations

from datetime import date, datetime

from briefbot.llm import Citation, LLMResponse
from briefbot.market_clock import EASTERN
from briefbot.market_data import TickerSnapshot
from briefbot.render import (
    _fmt_pct,
    _fmt_price,
    _fmt_volume,
    brief_path,
    caveats_block,
    failures_block,
    price_table,
    render_brief,
    sources_block,
    write_brief,
)
from briefbot.research import ResearchBundle
from conftest import make_snapshot


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def test_missing_values_render_as_a_dash():
    assert _fmt_price(None) == "—"
    assert _fmt_pct(None) == "—"
    assert _fmt_volume(None) == "—"


def test_percentages_always_carry_a_sign():
    assert _fmt_pct(3.456) == "+3.46%"
    assert _fmt_pct(-3.456) == "-3.46%"
    assert _fmt_pct(0.0) == "+0.00%"


def test_prices_are_thousands_separated():
    assert _fmt_price(1234.5) == "1,234.50"


def test_volume_is_abbreviated_by_magnitude():
    assert _fmt_volume(1_500_000_000) == "1.5B"
    assert _fmt_volume(127_400_000) == "127.4M"
    assert _fmt_volume(6_600) == "6.6K"
    assert _fmt_volume(950) == "950"


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def test_price_table_has_a_row_per_ticker(snapshot):
    table = price_table(snapshot)

    assert "**AAA**" in table and "**BBB**" in table
    assert "+11.11%" in table
    assert table.count("\n") == 3  # header, separator, two rows


def test_price_table_reports_an_empty_watchlist_plainly():
    snap = make_snapshot([TickerSnapshot(symbol="X", ok=False, error="nope")])
    assert "No market data" in price_table(snap)


def test_failed_tickers_are_listed_with_their_reason():
    snap = make_snapshot(
        [
            TickerSnapshot(symbol="OK", change_pct=1.0, session_date=date(2026, 7, 31)),
            TickerSnapshot(symbol="BAD", ok=False, error="not found — typo?"),
        ]
    )
    block = failures_block(snap)

    assert "`BAD`" in block and "typo?" in block
    assert "OK" not in block


def test_no_failures_block_when_everything_worked(snapshot):
    assert failures_block(snapshot) == ""


def test_caveats_combine_data_warnings_and_research_errors(snapshot):
    snapshot.warnings.append("data is stale")
    block = caveats_block(snapshot, ResearchBundle(errors=["macro failed"]))

    assert "data is stale" in block
    assert "macro failed" in block


def test_no_caveats_block_when_the_run_was_clean(snapshot):
    assert caveats_block(snapshot, ResearchBundle()) == ""


def test_sources_are_listed_as_markdown_links():
    block = sources_block([Citation(url="https://x.com/a", title="Story A", cited=True)])
    assert "- [Story A](https://x.com/a)" in block


def test_sources_are_truncated_with_a_count():
    cites = [Citation(url=f"https://x.com/{i}", title=f"S{i}") for i in range(40)]
    block = sources_block(cites, limit=5)

    assert block.count("](https://x.com/") == 5
    assert "S4" in block and "S5" not in block
    assert "…and 35 more" in block


def test_no_sources_block_without_citations():
    assert sources_block([]) == ""


# ---------------------------------------------------------------------------
# Whole document
# ---------------------------------------------------------------------------


def test_brief_contains_every_expected_section(snapshot):
    bundle = ResearchBundle(
        movers=LLMResponse(text="m", citations=[Citation(url="https://x.com/a", title="A", cited=True)])
    )
    text = render_brief(snapshot, bundle, "## The read\n\nQuiet.", watchlist_name="test list")

    assert text.startswith("# Daily brief — 2026-07-31")
    assert "test list" in text
    assert "**Market status:**" in text
    assert "**Data through:** close of 2026-07-31" in text
    assert "## The read" in text
    assert "## The numbers" in text
    assert "## Sources" in text
    assert "Phase 1: information only" in text


def test_header_lines_are_not_collapsed_into_one_paragraph(snapshot):
    text = render_brief(snapshot, ResearchBundle(), "prose")
    lines = text.splitlines()
    status_line = next(i for i, line in enumerate(lines) if line.startswith("**Market status:**"))

    assert lines[status_line + 1] == "", "markdown needs a blank line or these run together"


def test_brief_counts_tickers_with_data(snapshot):
    snapshot.snapshots.append(TickerSnapshot(symbol="BAD", ok=False, error="nope"))
    assert "2 of 3 tickers with data" in render_brief(snapshot, ResearchBundle(), "prose")


def test_brief_renders_with_no_data_at_all():
    snap = make_snapshot([TickerSnapshot(symbol="X", ok=False, error="nope")])
    text = render_brief(snap, ResearchBundle(errors=["everything failed"]), "prose")

    assert "No market data was retrieved" in text
    assert "everything failed" in text


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def test_brief_is_named_for_the_session_date(tmp_path):
    path = brief_path(tmp_path, date(2026, 7, 31), date(2026, 8, 1))
    assert path.name == "brief-2026-07-31.md"


def test_brief_falls_back_to_the_generated_date(tmp_path):
    path = brief_path(tmp_path, None, date(2026, 8, 1))
    assert path.name == "brief-2026-08-01.md"


def test_write_brief_creates_the_directory_and_latest(tmp_path, snapshot):
    out = tmp_path / "nested" / "briefs"
    path = write_brief("# hello", out, snapshot)

    assert path.read_text() == "# hello"
    assert (out / "latest.md").read_text() == "# hello"


def test_rerunning_the_same_day_overwrites_rather_than_duplicating(tmp_path, snapshot):
    write_brief("first", tmp_path, snapshot)
    path = write_brief("second", tmp_path, snapshot)

    assert path.read_text() == "second"
    assert len(list(tmp_path.glob("brief-*.md"))) == 1


def test_latest_can_be_suppressed(tmp_path, snapshot):
    write_brief("x", tmp_path, snapshot, also_latest=False)
    assert not (tmp_path / "latest.md").exists()
