# Trading bot — project context

## What this is

A stocks and ETFs analysis system. **Phase 1 is built and working**: an automated
daily brief combining market data, news, and geopolitical context into one
synthesized read. Growing over time toward real signals (Phase 2), backtesting
(Phase 3), and eventually live trading with a human checkpoint (Phase 4). Not
there yet — do not build execution code until Phase 4 is explicitly underway.

## Where things stand

| Phase | State |
|---|---|
| 1 — daily brief | **Done.** Runs end to end, tested, degrades gracefully |
| 2 — signals | Researched only, see `PHASE2_NOTES.md`. No code written |
| 3 — backtesting | Not started |
| 4 — live trading | Not started, and gated on an explicit decision |

`PROGRESS.md` is the running status. `NOTES_FOR_PAYITO.md` holds decisions that
need Payito. `README.md` covers setup, running, and known limits.

## Phase 1 as built

```
market_data  ->  research  ->  synthesis  ->  render
  yfinance      Claude +        Claude        markdown
                web search
```

- `briefbot/market_data.py` — OHLCV and best-effort fundamentals from yfinance.
  **Every number in the brief is computed here in plain Python.**
- `briefbot/market_clock.py` — NYSE session state and rule-computed holidays.
- `briefbot/research.py` — two Claude web-search calls: ticker news, and the
  macro/geopolitical backdrop.
- `briefbot/synthesis.py` — writes prose only.
- `briefbot/render.py` — assembles the markdown; table and sources rendered
  mechanically.
- `briefbot/pipeline.py`, `briefbot/cli.py` — orchestration and `python -m briefbot`.

Watchlist lives in `watchlist.json` (9 tickers: two benchmarks, SPY and QQQ,
then GOOG, META, AAPL, TSLA, NVDA, MSFT, AMZN). Output goes to `briefs/`.

**Phase 1 requires both benchmarks.** SPY for the broad market and QQQ for
tech/growth, so a move on a single name can be read against the tape rather than
in isolation. A test asserts both are present; they are not optional and not
interchangeable.

## Standing rules for this project

- No order-execution or broker-connection code until Phase 4 is explicitly
  started, and even then every trade requires an explicit human confirmation
  step in the code — never silent, never automatic
- Prefer plain, deterministic code for anything numeric (prices, indicators);
  reserve LLM calls for synthesis, judgment, and natural-language output
- Get one ugly end-to-end run working before polishing anything
- Keep this file updated as the project's actual shape solidifies — treat it as
  current truth, not a historical record

## Conventions that emerged while building Phase 1

Worth keeping as the project grows:

- **Numbers never round-trip through the model.** The LLM receives finished
  figures and writes prose about them; the price table is rendered from the
  snapshot. A test asserts this holds even when the model states a wrong number.
- **Every step degrades, nothing crashes.** One bad ticker, a failed research
  call, a dead API — the brief still ships and says what it is missing. A
  traceback at 7am is worth less than a partial brief.
- **"No clear catalyst" is a valid answer.** The research prompts push hard
  against inventing causes. A confidently wrong explanation for a 7% drop is
  worse than an honest gap, and this only holds if the prompts keep saying so.
- **Trust the data source exactly as far as it deserves.** yfinance is
  unofficial. The opt-in live tests (`pytest -m live`) assert on plausibility
  rather than fixed values, because the failure that actually bites is Yahoo
  changing a payload shape.

## Where the rest of the plan lives

The broader phase roadmap and the reasoning behind these choices live in
Payito's Claude.ai project for this build, in project-instructions.md and
claude-capabilities-checklist.md. Worth a read for context, not required to keep
working here.

## Getting started

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then add ANTHROPIC_API_KEY

python -m briefbot                 # full brief
python -m briefbot --skip-research # numbers only, no API cost
pytest                             # 211 tests, no network
```
