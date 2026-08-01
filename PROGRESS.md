# Progress

_Last updated: 2026-08-01, overnight session._

**Phase 1 is done and working.** The pipeline produces a real daily brief end to
end for the nine-ticker watchlist. Error handling and tests are in. Phase 2
research is written up with no Phase 2 code, as asked.

---

## Done

### The pipeline

- **`market_data.py`** — yfinance OHLCV pull, per-ticker error isolation, retry
  with exponential backoff, 30s timeout. Derived metrics all computed in plain
  Python: 1d/5d/21d/YTD change, 20-day volume ratio, 52-week range and distance
  from the high, intraday range. Fundamentals (sector, market cap, P/E, yield)
  are best-effort and never fail a run.
- **`market_clock.py`** — NYSE session state (open / pre-market / after-hours /
  closed / weekend / holiday) and holidays computed from rules, including Good
  Friday via Gregorian Easter, so nothing goes stale in January. Early closes
  handled.
- **`research.py`** — two Claude web-search calls: what moved the tickers, and
  the macro/geopolitical backdrop. Separate so one failing leaves the other.
- **`synthesis.py`** — writes prose only, from finished numbers.
- **`render.py`** — assembles the markdown. Table, caveats and sources rendered
  mechanically from the snapshot.
- **`pipeline.py` / `cli.py`** — orchestration with degradation at every step;
  `--dry-run`, `--skip-research`, `--tickers`, `--strict`, `-v`.

### Verified working

Three live end-to-end runs. The most recent: 9/9 tickers, 12 web searches, 25
cited sources, ~90 seconds. It correctly attributed AAPL's -7.35% to Q4 guidance
and the memory shortage, AMZN's +15.32% to the AWS beat, and — the part that
matters most — reported NVDA's +2.93% as having **no specific catalyst found**
rather than inventing one.

### Error handling

Everything degrades, nothing crashes. Full matrix in the README. Covered: one
bad ticker, unknown/delisted symbols, rate limits, network failures, either
research call failing, synthesis failing, no API key, an unwritable output
directory, market closed, stale data, partial sessions.

Two failure modes found and fixed while testing:

1. **A 100x dividend-yield bug.** yfinance has shipped `dividendYield` as a
   fraction in older versions and a percentage in current ones; my scale
   heuristic guessed wrong and would have printed Apple's 0.35% yield as 35%.
   Now derived from `dividendRate / price`, where no scale ambiguity is
   possible.
2. **Retry stacking.** The Anthropic SDK retries twice by default; stacked with
   ours, a rate-limited call would have fired up to nine requests. Set
   `max_retries=0` so there is one retry policy.

### Tests

209 offline tests (no network) plus 11 opt-in live tests (`pytest -m live`,
all passing). The two properties that get explicit coverage: one failing ticker
or step never prevents a brief, and the numbers in the table come from the
snapshot even when the model states a different figure in its prose.

### Docs

`README.md` (setup, running, architecture, degradation matrix, known limits),
`NOTES_FOR_PAYITO.md` (decisions needing you), `CLAUDE.md` updated to current
truth, `PHASE2_NOTES.md` (research only).

---

## Needs you

Detail in `NOTES_FOR_PAYITO.md`. The short version:

1. **Put your own `ANTHROPIC_API_KEY` in `.env`** — required. Without it you get
   a numbers-only brief, not a crash.
2. **Edit `watchlist.json`** — the nine tickers are my guess, not your positions.
3. **Decide on scheduling** — a working cron line is in the README; I did not
   install it.
4. Optional: try `BRIEF_MODEL=claude-opus-5` for the synthesis step and see if
   the writing reads better. I had no basis for spending your money benchmarking
   this.

---

## Next, when you want it

Nothing is in progress. Phase 1 is complete and Phase 2 is deliberately
unstarted — `PHASE2_NOTES.md` is research, not a plan I began executing.

Reasonable next moves, roughly in order of value:

- **Run it a few mornings and read the output.** The honest test of a brief is
  whether it is worth reading on a day when nothing much happened. Three runs on
  one very loud earnings day is not enough to know.
- **Delivery** — email or Slack, once you are actually reading it daily.
- **Phase 2 signal layer** — the notes cover indicators, the data quality work it
  forces (adjusted closes, survivorship bias), and the honest warning that the
  gap between "indicator computed correctly" and "signal worth acting on" is the
  entire difficulty. Read that file before starting.

## Time left over

I finished the assigned scope with time to spare and did not invent work to fill
it. What I spent the remaining time on: a third live run to confirm the
hardening changes held, tightening the sources list from 104 unfiltered search
results down to 25 actually-cited ones, and the Phase 2 writeup. No Phase 2 code
was written.
