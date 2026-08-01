"""Error types for the brief pipeline.

The guiding rule: a failure in one ticker, or in one whole step, should degrade
the brief rather than kill it. A brief with numbers and no news is still worth
reading at 7am; a traceback is not.
"""

from __future__ import annotations


class BriefError(Exception):
    """Base class for everything this package raises on purpose."""


class ConfigError(BriefError):
    """Watchlist or environment is unusable — the one class we do fail hard on."""


class TickerNotFound(BriefError):
    """Symbol does not resolve to anything with price history.

    Typo, delisting, or an exchange suffix Yahoo wants (e.g. ``BRK-B`` not
    ``BRK.B``). Recorded against the single ticker; the run continues.
    """

    def __init__(self, symbol: str, detail: str = ""):
        self.symbol = symbol
        self.detail = detail
        msg = f"no price history for {symbol!r}"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)


class MarketDataError(BriefError):
    """yfinance/Yahoo failed for a reason that is not 'this ticker is bogus'.

    Rate limiting, network, an unparseable payload. Retried before it reaches
    the caller.
    """

    def __init__(self, symbol: str, detail: str = ""):
        self.symbol = symbol
        self.detail = detail
        super().__init__(f"market data fetch failed for {symbol!r}: {detail}")


class ResearchError(BriefError):
    """The Claude research call failed after retries. The brief degrades to
    data-only rather than aborting."""


class SynthesisError(BriefError):
    """The Claude synthesis call failed after retries. The brief falls back to
    a mechanically-rendered numbers-and-headlines document."""
