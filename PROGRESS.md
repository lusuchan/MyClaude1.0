# Progress

_Last updated: 2026-08-01, watchlist fix session._

**Phase 1 is done and working.** The pipeline produces a real daily brief end to
end for the seven-ticker watchlist. Error handling and tests are in. Phase 2
research is written up with no Phase 2 code, as asked.

---

## Fixed

### `watchlist.json` was invalid JSON on `main` (2026-08-01)

**What broke.** Phase 1 was down end to end on `main` (`e338486`). Both
`python -m briefbot` and `pytest` failed at the first step, before any market
data was fetched.

**Root cause.** The watchlist was pasted in with typographic quotes — curly `“`
`”` (U+201C/U+201D) instead of ASCII `"`. JSON only accepts ASCII double quotes,
so `json.load()` never got past line 2:

```
json.decoder.JSONDecodeError: Expecting property name enclosed in
double quotes: line 2 column 1 (char 2)
```

`load_watchlist()` in `config.py` turned that into a `ConfigError` and the run
stopped there. The failure was in the data file, not the code — nothing in
`briefbot/` was at fault and nothing in `briefbot/` changed.

**What changed.** `watchlist.json` rewritten with straight ASCII quotes, and the
seven real tickers kept: GOOG, META, AAPL, TSLA, NVDA, MSFT, AMZN. Indices,
commodities and crypto stay held back for the separate market-analyst path.
`CLAUDE.md` was documenting the old nine-ticker placeholder list; it now matches
the file.

**Verified.** `json.load()` parses clean, and
`python -m briefbot --dry-run --skip-research` renders a full 7/7 table.
`pytest` is 210 passed / 1 failed — see "Needs you" below; the failure is a
stale assertion, not this fix.

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

Three real bugs found and fixed while testing:

1. **A 100x dividend-yield bug.** yfinance has shipped `dividendYield` as a
   fraction in older versions and a percentage in current ones; my scale
   heuristic guessed wrong and would have printed Apple's 0.35% yield as 35%.
   Now derived from `dividendRate / price`, where no scale ambiguity is
   possible.
2. **Retry stacking.** The Anthropic SDK retries twice by default; stacked with
   ours, a rate-limited call would have fired up to nine requests. Set
   `max_retries=0` so there is one retry policy.
3. **Unknown tickers retried three times.** An unknown symbol makes yfinance
   return an empty frame rather than raise, so the resulting error carried none
   of the text markers the not-found check matched on. Every typo cost 4.5s of
   backoff. Found by running the CLI against a bogus symbol, not by a test — the
   existing test passed throughout because it raised an exception whose text
   happened to match.

### Tests

211 offline tests (no network) plus 11 opt-in live tests (`pytest -m live`,
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
2. **One failing test, left failing on purpose.**
   `tests/test_config_cli.py::test_the_shipped_watchlist_is_valid` asserts
   `"SPY" in wl.symbols`, hardcoded against the old placeholder list. SPY is not
   in the real watchlist by design. Fixing it means editing a test to match a
   changed expectation, which is your call, not a thing to slip into a fix PR.
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
results down to 25 actually-cited ones, a real-world degradation check against a
bogus ticker (which found bug 3 above), and the Phase 2 writeup. No Phase 2 code
was written.
