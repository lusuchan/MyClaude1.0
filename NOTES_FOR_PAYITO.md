# Notes for Payito

Things I could not decide for you, or that need your hands.

This file is not a courtesy summary — it is where the decisions that are yours
actually live. Architecture calls, anything that spends money, and anything
that changes direction stop here and wait for you. The small stuff gets handled
and logged in `PROGRESS.md`; the forks get surfaced here. Never both silently.

Nothing below blocked the build. Where I had to move to keep going, I made a
provisional call, said what it was, and left the decision open here — a
provisional call is not a decision made on your behalf.

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

## 3. The watchlist is my guess, not your portfolio

You said 5–10 liquid names were fine if none were defined, so I picked nine:

> SPY, QQQ, AAPL, MSFT, NVDA, AMZN, GOOGL, JPM, XLE

The logic: two broad-market ETFs for the tape, four mega-cap tech names because
that is what actually moves the index, one bank as a rates/credit read, and one
energy ETF because geopolitics shows up there first.

**This is almost certainly not what you actually hold or watch.** Edit
`watchlist.json`. The `why` field on each entry feeds the research prompt, so it
is worth filling in honestly — "I own this" and "I am thinking about shorting
this" produce different research.

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
- **No PR opened.** Work is committed and pushed to
  `claude/daily-brief-phase-1-24xgbn`. Say the word if you want it opened.

## 7. Environment-specific thing you can ignore on your own machine

This container sits behind a TLS-inspecting proxy that resets yfinance's default
Chrome TLS fingerprint. I set `YF_IMPERSONATE=safari` to work around it, and the
code picks the workaround up only when a proxy is actually configured.

On a normal network you need none of this and the variable should stay unset.
Mentioning it only so the `YF_IMPERSONATE` line in `.env.example` does not look
mysterious.

## 8. The new CLAUDE.md describes a watchlist and a test this repo does not have

**Status: unresolved on purpose. Yours to settle.**

The CLAUDE.md you handed me was to be used verbatim, so it is in verbatim. But
three of its factual claims do not match what is actually in the repo, and every
way of fixing that means editing code or `watchlist.json`, which this session
was told not to touch. So it is here rather than guessed at.

**The tickers do not match.** CLAUDE.md now says:

> two benchmarks, SPY and QQQ, then GOOG, META, AAPL, TSLA, NVDA, MSFT, AMZN

`watchlist.json` on this branch holds:

> SPY, QQQ, AAPL, MSFT, NVDA, AMZN, GOOGL, JPM, XLE

Both are nine names and both lead with SPY and QQQ. Beyond that they differ:
CLAUDE.md adds META and TSLA and uses `GOOG`; the repo has `GOOGL` plus JPM
(the rates/credit read) and XLE (the geopolitics read) instead. The repo's
`README.md` and item 3 above both describe the second list, so it is not a
one-line fix — three files and the JSON all have to agree.

**The benchmark test does not exist.** CLAUDE.md says "a test asserts both are
present". `tests/test_config_cli.py:27` asserts the shipped watchlist is 5–10
names and that `SPY` is among them. Nothing asserts `QQQ`. If both benchmarks
are a hard Phase 1 requirement — and the new file says they are, not optional
and not interchangeable — that assertion needs to be written; right now
dropping QQQ would pass the suite.

**The change log it refers to is not in this repo.** Your instructions asked me
to log this "the same way the watchlist fix was". There is no watchlist-fix
entry in `PROGRESS.md` and no such commit in the history — the last ten commits
are the Phase 1 build. Taken together with the ticker mismatch, my read is that
the CLAUDE.md text was written against a version of this project where the
watchlist had already been changed to the GOOG/META/TSLA list, and that change
has not landed on `claude/new-session-wxejp7`. Worth checking whether it exists
somewhere I cannot see before anyone reconciles by hand.

**What I would do, if you want a recommendation.** Decide which nine names you
actually want first — that is question 3 in this file and it was always yours.
Then one short session: update `watchlist.json`, make CLAUDE.md's line, the
README's watchlist section, and item 3 above agree with it, and add the QQQ
assertion next to the SPY one. Until then, CLAUDE.md's ticker list is aspiration
and `watchlist.json` is what actually runs.
