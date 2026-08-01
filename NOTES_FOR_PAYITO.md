# Notes for Payito

Things I could not decide for you, or that need your hands. Nothing here blocked
the build — I made a call, said what it was, and kept going.

---

## 1. You need to put your own API key in `.env` — required

**Status: blocking for you, not for me.**

I built and tested against the API key present in this container's environment.
That key belongs to the session, not to you, and it will not exist when you run
this on your own machine.

```bash
cp .env.example .env
# ANTHROPIC_API_KEY=sk-ant-...
```

Without it, `python -m briefbot` still runs — it degrades to a numbers-only
brief and tells you why. So you will not get a crash, you will get a brief with
no news in it. `.env` is gitignored.

## 2. Model choice — I picked Sonnet, you may want to revisit

I defaulted to `claude-sonnet-5` for all three calls. Reasoning: the research
calls are mostly search-and-summarise, which Sonnet handles well, and they run
every day, so cost compounds.

The synthesis call is the one where a bigger model might genuinely read better —
it is the judgement step, and it is one call per day. Try
`BRIEF_MODEL=claude-opus-5` in `.env` for a week and see whether the writing is
noticeably sharper. I did not benchmark this; I had no basis to spend your money
comparing.

## 3. The watchlist — resolved, your real names are in

**Status: fixed, fully green, ready to merge —
[PR #3](https://github.com/lusuchan/MyClaude1.0/pull/3).** My nine-ticker guess
is gone. `watchlist.json` now holds your seven names plus the two benchmarks you
asked for:

> SPY, QQQ, GOOG, META, AAPL, TSLA, NVDA, MSFT, AMZN

Benchmarks sit at the top of the file, ahead of the seven, because they are
reference points rather than positions. Commodities and crypto are still
deliberately held back — that is the separate market-analyst path on its own
branch, not merged into Phase 1.

### What was broken, and what I fixed

Your edit landed on `main` as `e338486` with typographic quotes — curly `“` `”`
instead of ASCII `"`. Almost certainly a paste from somewhere that autocorrects
quotes. JSON does not accept them, so `load_watchlist()` raised `ConfigError`
before a single price was fetched, and Phase 1 was down end to end: both
`python -m briefbot` and `pytest` failed at that first step.

Nothing in `briefbot/` was wrong and nothing in `briefbot/` changed. The fix is
the same seven tickers, retyped with straight quotes, plus the `why` field filled
in on each — that field feeds the research prompt, so it is worth keeping honest.
`CLAUDE.md` was still describing the old placeholder list and now matches.

**Worth knowing for next time:** if you edit `watchlist.json` in an editor that
autocorrects quotes, this will happen again and the failure will look like a
crash rather than a typo. Quick check before a run:

```bash
python3 -c "import json; json.load(open('watchlist.json')); print('valid json')"
```

### The test that was failing is now fixed

`tests/test_config_cli.py::test_the_shipped_watchlist_is_valid` was asserting
`"SPY" in wl.symbols`, hardcoded from my old placeholder list. I left it failing
in the first pass rather than quietly deleting the line, because the real
question underneath it was yours to answer: does Phase 1 require a benchmark at
all?

You answered yes, and named two. So the assertion now checks that actual
requirement and states it in the failure message, rather than comparing against
one string for reasons a future reader would have to guess at:

```python
assert {"SPY", "QQQ"}.issubset(set(wl.symbols)), (
    "Phase 1 requires a broad-market benchmark (SPY) and a "
    "tech/growth benchmark (QQQ) alongside individual positions"
)
```

**211 passed, 0 failed.** PR #3 is fully green — nothing outstanding on it.

The reason two benchmarks and not one: everything else on the list is an
individual tech name, so the first question about any move is whether it is a
market story or a stock-specific one. SPY answers that for the broad tape, QQQ
for tech/growth specifically. A day where QQQ falls and SPY does not is a
different day from one where both fall, and one benchmark cannot tell those
apart.

The other two checks are clean: `json.load()` parses, and
`python -m briefbot --dry-run --skip-research` renders a full 7/7 table.

## 4. Delivery is still just a file

Phase 1 says a markdown file is fine, so that is what it does: `briefs/latest.md`
plus a dated copy. Nothing schedules it and nothing emails it.

There is a cron line in the README that will work. I did not install it, because
putting a job on your machine's schedule is your call, not mine.

## 5. Two data caveats worth knowing before you trust a number

- **Raw, not adjusted, closes.** Bars come back with `auto_adjust=False`, so a
  ticker going ex-dividend shows a price drop that was not a loss to a holder.
  Negligible for daily moves on this watchlist; it will matter for Phase 2
  indicators, and the Phase 2 notes flag it as a decision you will have to make.
- **yfinance is an unofficial Yahoo wrapper.** It works well and it is free, but
  Yahoo changes payloads without notice and rate-limits hard. The live test suite
  (`pytest -m live`) exists to catch exactly that — run it when a brief looks
  wrong. If this ever becomes load-bearing, the notes in `PHASE2_NOTES.md` cover
  what a paid replacement would take.

## 6. Things I deliberately did not do

- **No order execution, no broker code, nothing touching a real account.**
  Standing rule, and nothing in Phase 1 came near needing it.
- **No paid signups, no spending.** Everything here runs on yfinance (free) and
  your Anthropic key.
- **No Phase 2 code.** You asked for research only. Findings are in
  `PHASE2_NOTES.md`; there is not a line of indicator code in the repo.
- **No PR opened for the Phase 1 build.** That work went up on
  `claude/daily-brief-phase-1-24xgbn` and is now merged. The watchlist fix is
  open as [PR #3](https://github.com/lusuchan/MyClaude1.0/pull/3), unmerged and
  waiting on you.

## 7. Environment-specific thing you can ignore on your own machine

This container sits behind a TLS-inspecting proxy that resets yfinance's default
Chrome TLS fingerprint. I set `YF_IMPERSONATE=safari` to work around it, and the
code picks the workaround up only when a proxy is actually configured.

On a normal network you need none of this and the variable should stay unset.
Mentioning it only so the `YF_IMPERSONATE` line in `.env.example` does not look
mysterious.
