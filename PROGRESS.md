# Progress

_Last updated: 2026-08-01, docs-only session._

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

### The working agreement is now written down as a rule, not a suggestion

**What changed.** `CLAUDE.md` was replaced with a version you supplied
verbatim. Two things that used to sit in a closing "worth a read for context"
section are now standing rules: `claude-capabilities-checklist.md` gets read
before a phase's work starts and what it produced gets logged here, and
architecture calls, spending, and changes of direction go to
`NOTES_FOR_PAYITO.md` and stay there for you. The file also now states that
Phase 1 requires both benchmarks, SPY and QQQ, as a hard requirement rather
than a watchlist preference.

Then the same pattern got fixed everywhere else it appeared. `README.md` used
to point at CLAUDE.md as a place to look up the roadmap; it now says those
rules govern work in this repo and names the two things the README itself does
not cover. `NOTES_FOR_PAYITO.md` opened by saying nothing in it blocked the
build, which read as "these were already handled"; it now says plainly that
this is where your decisions live and that a provisional call is not a decision
made for you. `PHASE2_NOTES.md` now names the two gates on starting Phase 2 —
the open questions being yours, and the checklist read — instead of only
gating on reading the file. In this file, the model choice moved out of
"Optional:" and into a decision that stays open because it spends money on
every run, and the next-steps section now carries the checklist step.

**Why.** The project has two goals, and only one of them was written down as
binding. Framing a capability check or a decision fork as background reading
means it gets skipped under time pressure by exactly the sessions that most
need it — the docs said "worth a read" about the part that is actually the job.

**Verified.** Documentation only: no code, tests, or `watchlist.json` touched
(`git diff --stat` shows five markdown files and nothing else). `pytest` still
reports 211 passing offline tests, unchanged, since nothing it covers moved.

**One conflict, not resolved here.** The new `CLAUDE.md` describes a watchlist
this repo does not have, and a benchmark test that does not exist. Written up
as item 8 in `NOTES_FOR_PAYITO.md` rather than guessed at, since resolving it
either way means editing `watchlist.json` or the test suite — both out of scope
for a docs-only session, and both your call.

---

## Needs you

Detail in `NOTES_FOR_PAYITO.md`. The short version:

1. **Put your own `ANTHROPIC_API_KEY` in `.env`** — required. Without it you get
   a numbers-only brief, not a crash.
2. **Edit `watchlist.json`** — the nine tickers are my guess, not your positions.
3. **Decide on scheduling** — a working cron line is in the README; I did not
   install it.
4. **Decide the synthesis model** — try `BRIEF_MODEL=claude-opus-5` and see if
   the writing reads better. Not an optional extra: it spends your money on
   every run, so it is your call and it stays open until you make it. I had no
   basis for benchmarking it for you.

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

Whatever comes next, the first step is the same one CLAUDE.md sets out: read
`claude-capabilities-checklist.md` before the phase's work starts, use what
genuinely serves it, and record here what was used and why — or that nothing
fit. That check is part of the work, not preparation for it.

## Time left over

I finished the assigned scope with time to spare and did not invent work to fill
it. What I spent the remaining time on: a third live run to confirm the
hardening changes held, tightening the sources list from 104 unfiltered search
results down to 25 actually-cited ones, a real-world degradation check against a
bogus ticker (which found bug 3 above), and the Phase 2 writeup. No Phase 2 code
was written.
