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

## 2. Model choice — decided: Sonnet 5, no change needed

**Status: closed (2026-08-02). Payito's call: Sonnet 5 — cheaper and more
effective, and there is no need for Opus just to run web searches and
synthesise.**

That confirms the existing default rather than changing it. `DEFAULT_MODEL` in
`config.py:17` was already `claude-sonnet-5`, so no code changed; the decision
closes the question rather than moving the setting. `BRIEF_MODEL` still works as
an override if you ever want to A/B it, and `.env.example` documents it.

The original open question was whether the synthesis call — the judgement step,
one call per day — would read better on a bigger model. It stays answered no.
Reopen it only if the prose itself starts disappointing you; the research calls
are search-and-summarise, which Sonnet handles well, and they run daily so cost
compounds.

## 3. The watchlist — settled at eleven names, and the last `why` field is now answered

**Status: fully resolved (2026-08-02). Reconciled across two branches that had
each solved half of it, and the one line that was still yours is now closed.**

`watchlist.json` holds eleven names:

> SPY, QQQ, GOOG, META, AAPL, TSLA, NVDA, MSFT, AMZN, JPM, XLE

Seven of those are yours directly — GOOG, META, AAPL, TSLA, NVDA, MSFT, AMZN,
the mega-cap names off your personal watchlist. SPY and QQQ are the two
benchmarks you confirmed when asked, and they sit at the top of the file, ahead
of the single names, because they are reference points rather than positions.
JPM and XLE you added after seeing them mentioned in the test suite — they were
fixtures there, never on the briefed list, and you said you wanted them actually
briefed. They are the two reads the tech names cannot give you: a bank for rates
and credit, an energy ETF for where geopolitics shows up in a price first.

Commodities and crypto stay deliberately held back — that is the separate
market-analyst path on its own branch, not merged into Phase 1. See item 10.

### The one thing here that was still a question for you — now answered

**Status: closed (2026-08-02).** `GOOG`'s `why` said `"own it"`, which I could
not verify and would not silently drop. Payito confirmed it: GOOG's reason is
the same as the other seven Mag 7 names, **and** he owns it. Both halves were
true — the ownership claim was real, and it was also incomplete, because the
line said only the part that made GOOG different and none of the part it shared
with its peers.

The field now reads:

> `"Magnificent 7, tracking -- AI/tech boom bellwether; also a position Payito holds"`

That matters to the research prompt rather than being cosmetic: the old string
told the model *only* that the ticker was owned, so GOOG was the one Mag 7 name
whose prompt context omitted the bellwether framing the other seven get. It now
carries both, and the ownership signal is stated plainly rather than implied by
two words.

The other ten still say what each name is for structurally, which remains the
honest limit of what I can write without knowing what you hold.

### Two things about the file itself

- **SPY and QQQ are not editable in the way the other nine are.** Phase 1
  requires both benchmarks and `tests/test_config_cli.py` asserts they are
  present, in its own test. Drop one and the suite fails, deliberately. The
  reason it is two and not one: everything else is an individual tech name, so
  the first question about any move is whether it is a market story or a
  stock-specific one. A day where QQQ falls and SPY does not is a different day
  from one where both fall, and one benchmark cannot tell those apart.
- **Eleven is past the 5–10 you originally set, so I moved the fence.** The size
  bound now allows 5–12 rather than 5–10; at eleven names the old bound would
  have failed the suite. I did not treat that as a decision to bring to you,
  since you asked for the eleventh and twelfth names directly, but it is your
  constraint that moved, so you should know it moved. Cost is barely affected:
  research is two Claude calls regardless of list length, so each added name is
  one more yfinance fetch and a little more context, not another round trip. If
  the list keeps growing, the thing that degrades first is the brief's
  readability, not the bill.

### The typographic-quote trap, which will happen again

Worth keeping even though it is fixed. Your edit landed on `main` as `e338486`
with curly `“` `”` instead of ASCII `"` — almost certainly a paste from an
editor that autocorrects quotes. JSON does not accept them, so
`load_watchlist()` raised `ConfigError` before a single price was fetched, and
Phase 1 was down end to end: both `python -m briefbot` and `pytest` failed at
that first step. Nothing in `briefbot/` was wrong and nothing in `briefbot/`
changed.

If you edit `watchlist.json` in that same editor it will happen again, and the
failure will look like a crash rather than a typo. The file is now deliberately
ASCII-only, including the prose in `notes`, so anything non-ASCII appearing in
it is a signal rather than a style choice. Quick check before a run:

```bash
python3 -c "import json; json.load(open('watchlist.json')); print('valid json')"
```

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
- **Nothing is left open on GitHub.** PRs #1 and #3 merged to `main`; #4 and #5
  merged to `claude/daily-brief-phase-1-24xgbn`, which is what let the two lines
  drift apart in the first place — see item 10. This reconciliation is on
  `claude/progress-planning-5dv3mp` and needs a PR into `main` to land.

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

1. ~~**If the fix exists on another branch or in another session, it will now
   conflict with this one.**~~ **It did, and it has been resolved.** The fix
   existed on `main` as PR #3, and had done since before this was written — two
   different edits to the same block of ticker lines, exactly as predicted. Both
   sides are now merged into one line of history; see item 10 and the
   reconciliation entry in `PROGRESS.md`. The lesson worth keeping: the conflict
   was predicted correctly and then not acted on for two sessions, because
   checking cost a `git fetch` that nobody ran.
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

## 9. The capabilities checklist is now a rule I cannot actually follow

**Status: needs a decision. Small, but it will recur every session.**

CLAUDE.md's new standing rules say to check `claude-capabilities-checklist.md`
before a phase's work, and call it "not optional context, it's part of the job."
That file lives in your Claude.ai project, not in this repo. A session working
in this container cannot read it — I could not, this time — so the rule as
written is one no session running here can comply with.

That is not an argument against the rule. It is a good rule and it is the
reason the file now says so plainly. It just needs the map to be somewhere the
territory can reach. Three options, in the order I would pick them:

1. **Commit the checklist to the repo** — say `docs/claude-capabilities-checklist.md`.
   Then the rule is mechanically followable, the checklist is versioned
   alongside the work it describes, and updates to it show up in review. The
   cost is that it stops being a private scratchpad and becomes a project
   document, which may not be what you want it to be.
2. **Paste it into the session** when a phase starts, the same way you pasted
   the CLAUDE.md update. Zero repo change, but it depends on you remembering
   every time, and the rule says the check happens *before* the work starts.
3. **Soften the rule** to say the check happens wherever the checklist lives,
   and is Payito's to run when working from Claude.ai. Honest, but it gives up
   the thing the rule was written to get.

I did not pick one. Until you do, the honest thing is what I did this session:
say in `PROGRESS.md` that the check could not be run and why, rather than
quietly skipping it and letting the file imply otherwise.

## 10. Branch hygiene — one merge to do, one branch to decide about

**Status: needs a decision, and the first half is a five-minute job.**

Phase 1 spent two sessions existing as two half-correct versions on two
branches, because PRs #4 and #5 were merged into `claude/daily-brief-phase-1-24xgbn`
instead of into `main`. Neither branch could have produced a correct brief with
your real tickers *and* JPM and XLE until now. That is fixed — the reconciliation
is on `claude/progress-planning-5dv3mp`, fully tested — but it is fixed on a
branch, so:

**1. This needs to land on `main`.** Everything is merged, green, and verified
from a clean venv. It wants a PR into `main`, which I have not opened because
you have not asked for one. Say the word and it goes up. Until it lands, `main`
still has the nine-name watchlist and the 5–10 size bound.

**2. `claude/multi-asset-yfinance-research-40r733` is an orphan, and it is not
empty.** It holds `MULTI_ASSET_NOTES.md` — 514 lines of research on commodities,
crypto and multi-asset data sources, findings only, no implementation. It is
branched from before PR #3, so it has no knowledge of any of the watchlist work
and would revert several files if merged naively.

Your own note in `watchlist.json` says commodities and crypto are "held back for
now, pending a separate market-analyst path," so I read this branch as
deliberately unmerged and did **not** touch it. That is the right call for the
tickers. It is a worse call for the document: 514 lines of research that exist
on exactly one branch, in a repo where the trunk has already drifted twice, is
research that will be silently lost the first time someone prunes branches.

Three options, in the order I would pick them:

1. **Cherry-pick just `MULTI_ASSET_NOTES.md` onto the trunk** and leave the
   watchlist alone. The research becomes durable and reviewable; the tickers
   stay held back exactly as you wanted. This is what I would do, and it is
   about ten minutes.
2. **Leave the branch and accept the risk**, having now written down that it
   exists — which is most of the value, and costs nothing.
3. **Merge the branch properly** when the market-analyst path actually starts.
   Fine, but it means resolving a stale conflict later instead of now, and the
   conflict grows with every trunk commit.

I did not pick. It is a direction question about a path you explicitly deferred,
which puts it here rather than in my hands.

## 11. Web-search tool version — a one-line change I did not make

**New, 2026-08-02.** Surfaced while confirming your Sonnet 5 decision.

`briefbot/llm.py:19` pins:

```python
WEB_SEARCH_TOOL_TYPE = "web_search_20250305"
```

That is the basic web-search variant. Sonnet 5 also supports a newer one,
`web_search_20260209`, which adds **dynamic filtering**: it filters search
results *before* they reach the model's context window rather than after,
which is meant to improve both accuracy and token efficiency.

**Why it might genuinely matter here.** Research is not a side feature of this
pipeline, it is one of its four steps, and the failure mode we have actually
seen is a research call returning a near-empty result that the run summary
reported as clean (recorded under the reconciliation entry in `PROGRESS.md`).
Better filtering upstream of the context window is aimed squarely at that class
of problem. It is also a one-line change and costs nothing extra — the docs say
dynamic filtering is free when used with web search.

**Why I did not just do it.** It changes how the research step behaves, and the
standing rule in `CLAUDE.md` is that behaviour and direction changes come to you
rather than getting made quietly. It is also exactly the kind of change whose
effect I cannot honestly assess from one run — I would be swapping a working
component and telling you it was better on the strength of the release notes.

**What I would suggest.** Change it, then read a week of briefs against the
current ones. If you want, I can make the change and note in `PROGRESS.md` that
the comparison is outstanding — but the swap is yours to authorise, and the
verdict needs more than one morning either way.
