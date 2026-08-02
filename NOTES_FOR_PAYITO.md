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

**One naming trap, which already cost a session.** The remote environment
supplies its key as `API_KEY`, not `ANTHROPIC_API_KEY`. `config.py:91` reads
`ANTHROPIC_API_KEY` first and falls back to `API_KEY`, so briefbot works either
way and always has. But anything that checks for the documented name alone —
including me, in the session that added JPM and XLE — will conclude there is no
key when there is one, and quietly skip the live verification that matters.
`.env.example` documents the canonical name only, which is right for your
machine; the alias is worth knowing about for anywhere else this runs.

## 2. Model choice — I picked Sonnet, you may want to revisit

I defaulted to `claude-sonnet-5` for all three calls. Reasoning: the research
calls are mostly search-and-summarise, which Sonnet handles well, and they run
every day, so cost compounds.

The synthesis call is the one where a bigger model might genuinely read better —
it is the judgement step, and it is one call per day. Try
`BRIEF_MODEL=claude-opus-5` in `.env` for a week and see whether the writing is
noticeably sharper. I did not benchmark this; I had no basis to spend your money
comparing.

## 3. The watchlist is yours now — settled, but the `why` fields are still mine

**Status: resolved. Noted here because it was open for a while.**

`watchlist.json` holds eleven names:

> SPY, QQQ, GOOG, META, AAPL, TSLA, NVDA, MSFT, AMZN, JPM, XLE

The first nine are the ones you specified. JPM and XLE you added after seeing
them mentioned in the test suite — they were fixtures there, never on the
briefed list, and you said you wanted them actually briefed. They are the two
reads the tech names cannot give you: a bank for rates and credit, an energy
ETF for where geopolitics shows up in a price first.

Three things worth knowing about it:

- **SPY and QQQ are not editable in the way the other nine are.** Phase 1
  requires both benchmarks and `tests/test_config_cli.py` asserts they are
  present. Drop one and the suite fails, deliberately.
- **The `why` field on each entry is still my wording, not yours.** It feeds
  the research prompt, so it is worth filling in honestly — "I own this" and
  "I am thinking about shorting this" produce different research. Mine say what
  each name is for structurally, which is the best I can do without knowing
  your positions.
- **Eleven is past the 5–10 you originally set, so I moved the fence.** The
  test that bounds the watchlist size now allows 5–12 rather than 5–10; at
  eleven names the old bound would have failed the suite. I did not treat that
  as a decision to bring to you, since you asked for the eleventh and twelfth
  names directly, but it is your constraint that moved, so you should know it
  moved. Cost is barely affected: research is two Claude calls regardless of
  list length, so each added name is one more yfinance fetch and a little more
  context, not another round trip. If the list keeps growing, the thing that
  degrades first is the brief's readability, not the bill.

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

## 8. The watchlist fix had not actually landed here — now it has

**Status: resolved. Worth reading once, because of how it was found.**

The new CLAUDE.md described a watchlist this repo did not have. It said the
nine names were SPY, QQQ, GOOG, META, AAPL, TSLA, NVDA, MSFT, AMZN, and that a
test asserted both benchmarks were present. What was actually on this branch
was my original placeholder list — SPY, QQQ, AAPL, MSFT, NVDA, AMZN, GOOGL,
JPM, XLE — and a test that checked only for SPY. You confirmed CLAUDE.md's list
is the correct one, so the repo has been brought to match it:

- `watchlist.json` now holds those nine names in that order, with SPY and QQQ
  labelled as benchmarks, plus JPM and XLE at the end — see item 3.
- `tests/test_config_cli.py` now asserts both benchmarks are present, in its
  own test, with the reason in a comment. Dropping either fails the suite.
- `README.md` and item 3 above describe the real list instead of the old one.

**The part worth keeping in mind.** The fix was already made somewhere — your
instructions referred to it as done, and CLAUDE.md was written as though it
had landed. It had not landed on `claude/new-session-wxejp7`, and there is no
watchlist commit anywhere in this branch's history; the last ten commits are
the Phase 1 build. So a change you had good reason to think was applied was
live in the docs and absent from the code, and nothing would have caught that
except reading the JSON. Two loose ends follow from it:

1. **If the fix exists on another branch or in another session, it will now
   conflict with this one.** Two different edits to the same block of ticker
   lines. Worth checking before merging anything watchlist-shaped.
2. **The benchmark assertion is the durable half of this.** The ticker list can
   drift again; a test cannot drift silently. That is why it went in as its own
   test rather than one more line in the existing one.

**A footnote that turned into item 3's second half.** Two unit tests in
`tests/test_market_data.py` use JPM and XLE as sample symbols, and one live
test fetches JPM. Those exercise the fetch path against particular payload
shapes and never touched the briefed list, so I left them alone. Mentioning
that is what prompted you to add both names to the actual watchlist — worth
recording, because it means the tests were the only place those two names had
existed since the placeholder list was replaced.
