"""Tests for watchlist loading, settings, and the command line."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from briefbot.cli import build_parser, main
from briefbot.config import Holding, Settings, load_settings, load_watchlist
from briefbot.errors import ConfigError
from conftest import FakeAnthropic, make_frame, make_message, text_block


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------


def write_watchlist(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps(payload))
    return path


def test_the_shipped_watchlist_is_valid():
    wl = load_watchlist()
    assert 5 <= len(wl) <= 10, "Phase 1 calls for a small watchlist"
    assert "SPY" in wl.symbols


def test_symbols_are_upper_cased_and_stripped(tmp_path):
    path = write_watchlist(tmp_path, {"tickers": [{"symbol": " spy "}]})
    assert load_watchlist(path).symbols == ("SPY",)


def test_bare_strings_are_accepted(tmp_path):
    path = write_watchlist(tmp_path, {"tickers": ["AAPL", "MSFT"]})
    assert load_watchlist(path).symbols == ("AAPL", "MSFT")


def test_duplicates_are_dropped_not_fatal(tmp_path):
    path = write_watchlist(tmp_path, {"tickers": ["AAPL", "AAPL", "MSFT"]})
    assert load_watchlist(path).symbols == ("AAPL", "MSFT")


def test_labels_and_reasons_are_preserved(tmp_path):
    path = write_watchlist(
        tmp_path, {"tickers": [{"symbol": "SPY", "label": "S&P ETF", "why": "the tape"}]}
    )
    holding = load_watchlist(path).holdings[0]

    assert holding.label == "S&P ETF"
    assert "the tape" in holding.describe()


def test_a_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_watchlist(tmp_path / "nope.json")


def test_malformed_json_is_a_config_error(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text("{not json")
    with pytest.raises(ConfigError, match="not valid JSON"):
        load_watchlist(path)


def test_an_empty_watchlist_is_a_config_error(tmp_path):
    path = write_watchlist(tmp_path, {"tickers": []})
    with pytest.raises(ConfigError, match="no 'tickers'"):
        load_watchlist(path)


def test_an_entry_without_a_symbol_is_a_config_error(tmp_path):
    path = write_watchlist(tmp_path, {"tickers": [{"label": "no symbol here"}]})
    with pytest.raises(ConfigError, match="missing 'symbol'"):
        load_watchlist(path)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_read_the_documented_key_name():
    settings = load_settings({"ANTHROPIC_API_KEY": "abc"})
    assert settings.api_key == "abc"
    assert settings.has_api_key


def test_settings_accept_the_api_key_fallback():
    assert load_settings({"API_KEY": "xyz"}).api_key == "xyz"


def test_the_documented_key_wins_over_the_fallback():
    assert load_settings({"ANTHROPIC_API_KEY": "a", "API_KEY": "b"}).api_key == "a"


def test_no_key_is_reported_honestly():
    assert not load_settings({}).has_api_key


def test_model_and_search_budget_are_overridable():
    settings = load_settings({"BRIEF_MODEL": "custom", "BRIEF_MAX_SEARCHES": "9"})
    assert settings.model == "custom"
    assert settings.max_searches == 9


def test_a_non_numeric_search_budget_is_a_config_error():
    with pytest.raises(ConfigError, match="must be an integer"):
        load_settings({"BRIEF_MAX_SEARCHES": "lots"})


def test_a_relative_output_dir_is_anchored_to_the_repo():
    settings = load_settings({"BRIEF_OUTPUT_DIR": "somewhere"})
    assert settings.output_dir.is_absolute()
    assert settings.output_dir.name == "somewhere"


def test_only_https_proxy_is_picked_up():
    assert load_settings({"HTTPS_PROXY": "http://p:1"}).proxy == "http://p:1"
    assert load_settings({"HTTP_PROXY": "http://p:1"}).proxy is None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class FakeTicker:
    def history(self, **kwargs):
        return make_frame([100.0 + i for i in range(30)])

    def get_info(self):
        return {}

    @property
    def fast_info(self):
        return {}


@pytest.fixture
def cli_env(monkeypatch, tmp_path):
    """A CLI run with no network: fake yfinance, fake Anthropic, temp output."""

    monkeypatch.setattr("briefbot.market_data._make_ticker", lambda s, sess: FakeTicker())
    monkeypatch.setenv("BRIEF_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    fake = FakeAnthropic(
        [
            make_message([text_block("movers")]),
            make_message([text_block("macro")]),
            make_message([text_block("## The read\n\nprose")]),
        ]
    )
    monkeypatch.setattr("anthropic.Anthropic", lambda **kw: fake)
    return fake, tmp_path / "out"


def test_cli_writes_a_brief(cli_env, capsys):
    _, out = cli_env
    assert main(["--tickers", "AAA,BBB"]) == 0

    briefs = list(out.glob("brief-*.md"))
    assert len(briefs) == 1
    assert "## The read" in briefs[0].read_text()


def test_dry_run_prints_and_writes_nothing(cli_env, capsys):
    _, out = cli_env
    assert main(["--tickers", "AAA", "--dry-run"]) == 0

    assert "# Daily brief" in capsys.readouterr().out
    assert not out.exists()


def test_skip_research_needs_no_api_calls(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("briefbot.market_data._make_ticker", lambda s, sess: FakeTicker())
    monkeypatch.setenv("BRIEF_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    assert main(["--tickers", "AAA", "--skip-research", "--dry-run"]) == 0
    assert "## The numbers" in capsys.readouterr().out


def test_strict_mode_signals_degradation(monkeypatch, tmp_path):
    monkeypatch.setattr("briefbot.market_data._make_ticker", lambda s, sess: FakeTicker())
    monkeypatch.setenv("BRIEF_OUTPUT_DIR", str(tmp_path / "out"))

    assert main(["--tickers", "AAA", "--skip-research", "--strict", "--dry-run"]) == 2


def test_degradation_without_strict_still_exits_zero(monkeypatch, tmp_path):
    monkeypatch.setattr("briefbot.market_data._make_ticker", lambda s, sess: FakeTicker())
    monkeypatch.setenv("BRIEF_OUTPUT_DIR", str(tmp_path / "out"))

    assert main(["--tickers", "AAA", "--skip-research", "--dry-run"]) == 0


def test_a_bad_watchlist_path_exits_one(tmp_path, capsys):
    assert main(["--watchlist", str(tmp_path / "nope.json")]) == 1
    assert "config error" in capsys.readouterr().err


def test_empty_tickers_argument_exits_one(capsys):
    assert main(["--tickers", " , "]) == 1
    assert "config error" in capsys.readouterr().err


def test_tickers_flag_overrides_the_watchlist_file(cli_env):
    fake, _ = cli_env
    main(["--tickers", "zzz,yyy", "--dry-run"])

    prompt = fake.calls[0]["messages"][0]["content"]
    assert "ZZZ" in prompt and "YYY" in prompt


def test_parser_defaults_are_off():
    args = build_parser().parse_args([])
    assert not args.skip_research
    assert not args.dry_run
    assert not args.strict
    assert args.verbose == 0
