"""Watchlist loading and run-wide settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigError

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WATCHLIST_PATH = REPO_ROOT / "watchlist.json"

DEFAULT_MODEL = "claude-sonnet-5"


@dataclass(frozen=True)
class Holding:
    """One line of the watchlist."""

    symbol: str
    label: str = ""
    why: str = ""

    def describe(self) -> str:
        bits = [self.symbol]
        if self.label:
            bits.append(f"({self.label})")
        if self.why:
            bits.append(f"— {self.why}")
        return " ".join(bits)


@dataclass(frozen=True)
class Watchlist:
    name: str
    holdings: tuple[Holding, ...]

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(h.symbol for h in self.holdings)

    def __len__(self) -> int:
        return len(self.holdings)


@dataclass(frozen=True)
class Settings:
    """Everything the run needs that is not the watchlist itself."""

    api_key: str | None = None
    model: str = DEFAULT_MODEL
    max_searches: int = 6
    output_dir: Path = field(default=REPO_ROOT / "briefs")
    # Browser profile for curl_cffi. Only matters behind TLS-inspecting
    # proxies, which reset yfinance's default Chrome fingerprint.
    yf_impersonate: str | None = None
    # Proxy URL handed to yfinance's HTTP session. Picked up from the
    # environment so the pipeline works unchanged on a normal network.
    proxy: str | None = None

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Read settings from the environment, loading .env first if present.

    ``ANTHROPIC_API_KEY`` is the documented name. ``API_KEY`` is accepted as a
    fallback because some managed runtimes inject it under that name.
    """

    if env is None:
        load_dotenv(REPO_ROOT / ".env")
        env = dict(os.environ)

    api_key = env.get("ANTHROPIC_API_KEY") or env.get("API_KEY") or None

    output_dir = Path(env.get("BRIEF_OUTPUT_DIR") or (REPO_ROOT / "briefs"))
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir

    # Only HTTPS_PROXY is honoured; the agent proxy in some environments
    # rejects plain-HTTP proxying outright.
    proxy = env.get("HTTPS_PROXY") or env.get("https_proxy") or None

    return Settings(
        api_key=api_key,
        model=env.get("BRIEF_MODEL") or DEFAULT_MODEL,
        max_searches=_int_env("BRIEF_MAX_SEARCHES", 6),
        output_dir=output_dir,
        yf_impersonate=env.get("YF_IMPERSONATE") or None,
        proxy=proxy,
    )


def load_watchlist(path: str | Path | None = None) -> Watchlist:
    """Load and validate the watchlist file."""

    path = Path(path) if path else DEFAULT_WATCHLIST_PATH
    if not path.exists():
        raise ConfigError(f"watchlist not found at {path}")

    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"watchlist at {path} is not valid JSON: {exc}") from exc

    entries = raw.get("tickers")
    if not isinstance(entries, list) or not entries:
        raise ConfigError(f"watchlist at {path} has no 'tickers' list")

    holdings: list[Holding] = []
    seen: set[str] = set()
    for entry in entries:
        if isinstance(entry, str):
            entry = {"symbol": entry}
        if not isinstance(entry, dict):
            raise ConfigError(f"watchlist entry must be a string or object, got {entry!r}")

        symbol = str(entry.get("symbol", "")).strip().upper()
        if not symbol:
            raise ConfigError(f"watchlist entry is missing 'symbol': {entry!r}")
        if symbol in seen:
            continue  # duplicates are a typo, not a reason to stop
        seen.add(symbol)

        holdings.append(
            Holding(
                symbol=symbol,
                label=str(entry.get("label", "")).strip(),
                why=str(entry.get("why", "")).strip(),
            )
        )

    return Watchlist(name=str(raw.get("name") or "watchlist"), holdings=tuple(holdings))
