# Progress

_Last updated: 2026-08-02, reconciliation session. `main` and the Phase 1
branch had diverged into two half-correct versions of Phase 1; they are now one
line of history again. Entries below run oldest-first within each section._

**Phase 1 is done and working.** The pipeline produces a real daily brief end to
end for the eleven-ticker watchlist. Error handling and tests are in. Phase 2
research is written up with no Phase 2 code, as asked.

---

## Fixed

_These two entries are the record from the `main` line of history, kept as
written on 2026-08-01. Specifics in them were later superseded — the watchlist
went from nine names to eleven, the size bound from 5–10 to 5–12, and the
benchmark assertion moved into its own test — but the entries are not rewritten,
because what they record is how the problems were found, and that does not
expire. The reconciliation entry at the bottom of "Done" explains how these came
to sit on a different branch from the rest._

### Benchmarks are now a Phase 1 requirement (2026-08-01)

**What changed.** SPY and QQQ added to `watchlist.json`, at the top and ahead of
the seven single names, because they are benchmarks rather than positions. Nine
tickers total, still inside the 5–10 range Phase 1 calls for.

**Why.** The rest of the watchlist is individual tech names, which on their own
cannot answer the first question worth asking about any move: is this a market
story or a stock-specific one. SPY gives the broad tape, QQQ the tech/growth
comparison for the AI names. Neither is redundant with the other — a day where
QQQ drops and SPY holds says something specific.

**The leftover failing test is closed out.**
`test_the_shipped_watchlist_is_valid` was asserting `"SPY" in wl.symbols`,
hardcoded from the old placeholder list. It now asserts both benchmarks are
present and carries a message saying why, so the requirement is legible rather
than an unexplained string comparison:

```python
assert {"SPY", "QQQ"}.issubset(set(wl.symbols)), (
    "Phase 1 requires a broad-market benchmark (SPY) and a "
    "tech/growth benchmark (QQQ) alongside individual positions"
)
```

**Verified.** `json.load()` parses clean, `pytest` is **211 passed / 0 failed**,
and `--dry-run --skip-research` renders a full 9/9 table.

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
`pytest` was 210 passed / 1 failed at the time — a stale assertion, not this
fix. Closed out by the benchmark entry above.

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

**One conflict, raised rather than guessed at.** The new `CLAUDE.md` described
a watchlist this repo did not have, and a benchmark test that did not exist.
Both were written up as item 8 in `NOTES_FOR_PAYITO.md` and resolved in the
next entry.

### The watchlist now matches CLAUDE.md, and a test holds it there

**What changed.** `watchlist.json` holds SPY, QQQ, GOOG, META, AAPL, TSLA,
NVDA, MSFT, AMZN — the list CLAUDE.md describes, confirmed correct. It had been
carrying my original placeholder nine (GOOGL, JPM and XLE where META, TSLA and
GOOG should have been). `tests/test_config_cli.py` gained
`test_the_shipped_watchlist_carries_both_benchmarks`, asserting SPY and QQQ are
both present, which is the claim CLAUDE.md was already making. `README.md` and
`NOTES_FOR_PAYITO.md` items 3 and 8 now describe the real list.

**Why.** CLAUDE.md is meant to be current truth about this repo, and on the
watchlist it was describing a repo that did not exist here — the fix was
believed done, was live in the docs, and had never landed in the code. Nothing
would have surfaced that except reading the JSON by hand. The benchmark test is
the half of this that lasts: the ticker list can drift again, a failing test
cannot drift quietly.

**Verified.** `pytest` reports 212 passing offline tests, up one from the new
benchmark test; `python -m briefbot --skip-research --dry-run` renders a brief
over the new names, 9 of 9 fetched, so GOOG, META and TSLA all resolve at
Yahoo (that path still hits yfinance — it is the Claude calls it skips). The
benchmark assertion was confirmed to actually bite by removing QQQ from the
watchlist and watching it fail, then restoring it. The two `market_data` unit
tests and one live test that use JPM and XLE were left alone — they exercise
fetch behaviour against particular payload shapes, not the shipped watchlist.

### JPM and XLE join the watchlist, which is now eleven names

**What changed.** `watchlist.json` gained JPM and XLE at the end of the list,
after the two benchmarks and the seven tech names. `CLAUDE.md`, `README.md` and
`NOTES_FOR_PAYITO.md` item 3 now say eleven. The size bound in
`test_the_shipped_watchlist_is_valid` moved from 5–10 to 5–12, because eleven
names would otherwise have failed a suite that was encoding the original
"5–10 liquid names" instruction.

**Why.** The names came up in the previous entry only as a footnote — JPM and
XLE were sample symbols in the test suite, never on the briefed list. Payito
read that, and wanted them briefed for real. They cover what seven mega-cap
tech names and two equity benchmarks structurally cannot: a bank for rates and
credit, an energy ETF for where geopolitics reaches a price first.

**Why it costs almost nothing.** Research is two Claude calls regardless of how
long the list is — `research_movers` sends the whole snapshot in one prompt and
focuses on the notable movers, and `research_macro` sends the watchlist as
context. So each added name is one more yfinance fetch plus a little more
prompt context, not another round trip. The thing that degrades as the list
grows is the brief's readability, not the bill.

**Verified.** 212 offline tests pass, unchanged — this added names, not tests.
The relaxed size bound was checked in the direction that matters: a 13-name
watchlist still fails it, so the fence moved rather than came down.

A full live run over the eleven names is green: 11/11 tickers, 11 web searches,
24 cited sources, both research calls and synthesis returning. That is the
fourth live end-to-end run and the first on the longer list. JPM and XLE earn
their place immediately — the macro section tied Brent and the Iran/Hormuz
shipping risk to XLE's +33.19% YTD, and the synthesis noted both names were
quiet against a tech-earnings tape rather than ignoring them. It also declined
to attribute XLE's +1.00% Friday move to fresh news, which is the "no clear
catalyst" convention holding on a newly added ticker.

**The capability check, which CLAUDE.md now requires me to record either way.**
`claude-capabilities-checklist.md` lives in Payito's Claude.ai project, not in
this repo, and nothing in this container can read it — so I could not do the
check as written. Saying that plainly is what the rule asks for in place of
silently skipping it. If the intent is that any session working in this repo
can run the check, the checklist needs to exist somewhere the repo can reach;
that is a decision, so it is item 9 in `NOTES_FOR_PAYITO.md`.

One capability did get used and is worth logging on its own terms: the brief
was published as an **Artifact** — a styled, theme-aware web page rendered from
the same markdown, at
`https://claude.ai/code/artifact/bbc1ef37-ef38-40ab-ad78-04508bba10f8`. It
earned its place here because `briefs/` is gitignored and this container is
ephemeral, so the markdown brief had no durable home; the artifact is the only
copy of that run that survives the session. Its real limits: it is a static
snapshot of one run, private until shared, generated by hand rather than by the
pipeline, and nothing in `briefbot/` knows it exists. It is not a delivery
mechanism — delivery is still the open question in item 4 of the notes.

**A verification failure worth recording, since it nearly shipped.** I first
reported that this container had no API key and logged the live run as
impossible. It has one — as `API_KEY`, which `config.py:91` already accepts as
an alias — and my check tested only `ANTHROPIC_API_KEY`. The claim was wrong
in the PR body and in this file before Payito questioned it. The lesson is
narrow and repeatable: check the code's actual resolution order before
declaring a capability absent, rather than probing the documented name and
stopping there.

### `main` and the Phase 1 branch are one line of history again (2026-08-02)

**What was wrong.** Phase 1 existed as two different half-correct versions on
two branches, and neither was complete. `main` had PRs #1 and #3: the
typographic-quote fix, Payito's seven real tickers, and the first benchmark
assertion. `claude/daily-brief-phase-1-24xgbn` had PRs #4 and #5: JPM and XLE,
the doc-binding work, the live verification — but those were merged into the
Phase 1 branch rather than into `main`, so the two lines never met. Seven
commits on one side, six on the other, five files in conflict.

This is exactly the collision item 8 of the notes predicted in the abstract
("if the fix exists on another branch or in another session, it will now
conflict with this one"). It had already happened by the time that sentence was
written; nobody had looked.

**What the two sides disagreed about, and how each was settled.**

- **`watchlist.json`** — `main` had nine names with Payito's own label text
  (`Alphabet (Class C)`) and file name (`Phase 1 watchlist`); the branch had
  eleven names with generic labels. Kept eleven, since CLAUDE.md mandates
  JPM and XLE, and restored Payito's authored strings on top. The `notes` field
  is merged from both: the benchmark rule, the JPM/XLE rationale, and Payito's
  own statement that commodities and crypto are deliberately held back.
- **`tests/test_config_cli.py`** — both sides had independently written a
  benchmark requirement. `main` folded it into `test_the_shipped_watchlist_is_valid`
  with a 5–10 size bound; the branch split it into its own test with 5–12. Took
  the branch's split version — eleven names need the wider bound, and a separate
  test names the thing that failed — and carried `main`'s clearer reasoning into
  the comment.
- **`CLAUDE.md`** — took the branch's eleven-ticker description, which is what
  the governing file Payito supplied actually says.
- **`PROGRESS.md` and `NOTES_FOR_PAYITO.md`** — merged rather than picked. Both
  sides' factual records are kept; see the note under "Fixed" about why those
  two entries were not rewritten.

**One thing I flagged instead of deciding.** `main`'s `why` field for `GOOG`
reads `"own it"`. Payito's own edit to `watchlist.json` (`e338486`) contained no
`why` fields at all, and the note attached to it said the names came off a
watchlist screenshot — which is not the same as ownership. So that string is
either something Payito said in the PR #3 session or an inference that hardened
into a fact, and I cannot tell which from the history. It feeds the research
prompt, so it is not cosmetic. Kept it rather than deleting it, because
discarding a possibly-real statement about someone's positions is the worse
error, and raised it as the open item in notes item 3.

**Verified from zero, not incrementally.** The venv was deleted and rebuilt from
`requirements.txt`, so nothing carried over from the pre-merge tree:

- **212 offline tests pass**, 11 deselected. Both stale "211" counts in
  `CLAUDE.md` and `README.md` corrected.
- **All 11 live tests pass** (`pytest -m live`, ~87s) — these hit Yahoo for
  real, which is the check that catches a changed payload shape.
- **The guards were confirmed to bite, not just to pass.** Removing QQQ fails
  the benchmark test; removing SPY fails it on the other assertion with the
  right message; a thirteenth name fails the size bound. A test that has never
  been seen red is not yet evidence.
- **`--skip-research --dry-run` renders 11/11.**
- **A full live end-to-end run**: 11/11 tickers, 12 web searches, 15 cited
  sources, both research calls and synthesis returning, ~101s. That is the fifth
  live run and the first on the reconciled tree.

**One observation from that run, not a bug and not fixed.** The macro research
call came back at 163 characters — a near-empty result, and its content was cut
off mid-sentence about the FOMC vote. Nothing flagged it: the pipeline counts a
short-but-non-empty response as success, so the run reported clean. The brief
was still honest about it, saying the transcript was cut off rather than
inventing the dissent detail, which is the "no clear catalyst" convention
holding under a condition it was not specifically designed for. Worth knowing
that a degenerate research result currently looks identical to a good one in the
run summary. Left alone deliberately — adding a length threshold is a behaviour
change, and this session's job was reconciliation.

**The capability check.** Same answer as last session, for the same reason:
`claude-capabilities-checklist.md` lives in Payito's Claude.ai project and
nothing in this container can read it, so the check could not be run as written.
Recording that rather than skipping it silently is what the rule asks for. It
remains item 9. Nothing on the list was reached for this session in any case —
the work was a git reconciliation and a verification pass, and inventing a use
for a capability here would have been the box-ticking CLAUDE.md warns against.

### Sixth live run — a delivered brief, on request (2026-08-02)

**What this was.** Not a code change. Payito asked for a finished brief off the
reconciled tree, full research and full analysis, and this entry is the record of
that run. Nothing in `briefbot/`, `tests/` or `watchlist.json` was touched.

**The run.** Environment rebuilt from scratch — fresh venv from
`requirements.txt`, no state carried over. `pytest` reports **212 passed, 11
deselected**, matching the documented count. Then a full live run:

- 11/11 tickers, **11 web searches, 22 cited sources**, ~110s.
- Both research calls returned healthy — movers 4274 chars, macro 3462 chars.
  Worth noting against last session's observation: the degenerate 163-char macro
  result did not recur, so that remains an unflagged failure mode rather than a
  standing one.
- Synthesis returned 4259 chars. No step degraded; the run summary was clean.

**The conventions held, checked rather than assumed.** Every figure in the prose
matches the snapshot table — AMZN +15.3/+15.32, AAPL -7.4/-7.35, GOOG
+6.9/+6.88, NVDA +2.9/+2.93. And the "no clear catalyst" rule bit on **three**
names in one run: GOOG, META and NVDA all got an explicit "no same-day catalyst
found" rather than a borrowed cause, with NVDA's +2.93% specifically declining to
claim the AI-infrastructure read-through as a reported event. That is the
convention doing its job on a day when an easy wrong answer was available.

**Data note.** The run was on a Sunday, so the brief covers the Friday 2026-07-31
close and `market_clock` correctly reported "closed for the weekend".

**The capability check, recorded either way as CLAUDE.md requires.**
`claude-capabilities-checklist.md` is still unreachable from this container — but
this session checked one surface previous sessions had not: the Google Drive
connector, searching both by title and by full text. No match. So the answer is
unchanged and now better evidenced: the file lives in Payito's Claude.ai project
and nothing available to a session working in this repo can read it. This stays
item 9.

Two capabilities were used and are worth logging on their own terms:

1. **Artifact** — the brief was published as a styled, theme-aware web page at
   `https://claude.ai/code/artifact/debac76c-0f60-46dc-a7d6-cba7cd4fd875`. Same
   justification as last time and it has not weakened: `briefs/` is gitignored
   and the container is ephemeral, so the rendered artifact plus the markdown
   file sent directly to Payito are the only copies of this run that survive the
   session. Its limits are unchanged: a static snapshot of one run, private until
   shared, generated by hand rather than by the pipeline, and nothing in
   `briefbot/` knows it exists. Still not a delivery mechanism — item 4 is still
   open.
2. **The dataviz validator** — the brief's up/down encoding is red/green, which
   is the textbook colour-vision failure. Rather than eyeball it, the candidate
   pairs were run through the skill's palette validator and iterated until they
   passed: `#0A8F80`/`#C03A26` on light (ΔE 11.6 deutan), `#0FA383`/`#EF5B4C` on
   dark (ΔE 10.3), both inside their mode's lightness band and above the chroma
   floor. The first two attempts failed on chroma and on the dark lightness band
   respectively. Polarity is additionally carried by the explicit +/- sign and by
   bar direction from a centre baseline, so colour is never the only cue. Noted
   because it generalises: any future rendering of this data has the same problem
   and the same fix.

**Rendered and checked, not assumed.** The page was screenshotted headless in
both themes and at mobile width; no horizontal overflow at any width, and one
real layout bug was found and fixed that way (a wrapped ticker pair left a
dangling separator).

Detail in `NOTES_FOR_PAYITO.md`. The short version:

1. **Put your own `ANTHROPIC_API_KEY` in `.env`** — required. Without it you get
   a numbers-only brief, not a crash.
2. ~~**Edit `watchlist.json`**~~ — done. Eleven names, yours. One line still
   needs you: `GOOG`'s `why` says "own it", which I could not verify and did not
   want to silently drop. Confirm or correct it — that field feeds the research
   prompt.
3. **Decide on scheduling** — a working cron line is in the README; I did not
   install it.
4. **Decide the synthesis model** — try `BRIEF_MODEL=claude-opus-5` and see if
   the writing reads better. Not an optional extra: it spends your money on
   every run, so it is your call and it stays open until you make it. I had no
   basis for benchmarking it for you.
5. **Decide what happens to the multi-asset branch** — a 514-line research doc
   that exists only on `claude/multi-asset-yfinance-research-40r733` and is
   deliberately not merged. Item 10 in the notes.

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
