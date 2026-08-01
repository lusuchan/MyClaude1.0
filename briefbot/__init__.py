"""briefbot — Phase 1 of the trading project: an automated daily market brief.

Pipeline shape:

    market_data  ->  research  ->  synthesis  ->  render

Numbers are computed deterministically in :mod:`briefbot.market_data`. The LLM
is only ever asked for judgement and prose, never arithmetic.
"""

__version__ = "0.1.0"
