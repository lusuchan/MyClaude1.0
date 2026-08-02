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

Watchlist lives in `watchlist.json` (11 tickers: two benchmarks, SPY and QQQ,
then GOOG, META, AAPL, TSLA, NVDA, MSFT, AMZN, then JPM for rates/credit and
XLE for geopolitics). Output goes to `briefs/`.

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
- Check `claude-capabilities-checklist.md` before starting a phase's work — see
  "Using Claude's own capabilities" below; this is not optional context, it's
  part of the job
- Architecture calls, anything that spends money, or anything that changes
  direction go in `NOTES_FOR_PAYITO.md` and stay there for Payito to decide —
  handle the small stuff, surface the forks, never both silently

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

## Using Claude's own capabilities

This project has two goals, not one: a working trading bot, and Payito
actually learning what Claude can do by building it rather than by being told.
A phase that ships without touching a capability the checklist flagged for it
has only done half the job.

`claude-capabilities-checklist.md`, in Payito's Claude.ai project for this
build, is the map: what's been used, what's queued for which phase, what's
explicitly out of scope for now. Read it before starting a phase's work, not
after finishing it.

When something on that list would genuinely serve what's being built this
session — not just be interesting — use it, and say so in `PROGRESS.md`: what
it is, why this phase needed it, its real limits. If nothing fits, say that
too, briefly, rather than silently skipping the check. Don't reach for a
capability that doesn't serve the actual work just to check a box; log it in
the checklist backlog instead and move on, same as the checklist itself
already says.

The reasoning behind phase decisions and the fuller roadmap live in
`project-instructions.md` in that same Claude.ai project — read for context,
but the rules in this file are what actually govern this repo.

## Getting started

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then add ANTHROPIC_API_KEY

python -m briefbot                 # full brief
python -m briefbot --skip-research # numbers only, no API cost
pytest                             # 212 tests, no network
pytest -m live                     # 11 more, opt-in, real network and API
```

`.github/workflows/ci.yml` runs that same offline suite on every pull request,
against Python 3.11 and 3.12, plus a parse-and-ASCII check on `watchlist.json`.
It needs no secrets — `pytest.ini` pins `-m "not live"`, so CI never spends
money or touches Yahoo. The live tests stay opt-in and stay yours to run.
