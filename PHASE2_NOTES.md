# Phase 2 research notes — a signal layer

**Research only. No Phase 2 code has been written, and none should be until you
have read this and decided the open questions at the end.**

Written after Phase 1 shipped. Where I verified something by running it, I say
so; where I am relaying what the literature or the ecosystem claims, I say that
instead.

---

## 1. The thing worth saying first

The hard part of Phase 2 is not computing indicators. RSI is fifteen lines and
the libraries are mature. The hard part is that **an indicator computed
perfectly is not a signal**, and the distance between those two things is where
essentially all quantitative strategies die.

Three specific traps, all well documented:

- **Backtest overfitting via multiple testing.** Search enough parameter
  combinations and you will find one with a beautiful backtest, by construction,
  from noise alone. Bailey and López de Prado's *Deflated Sharpe Ratio* (2014)
  exists precisely to correct a Sharpe ratio for how many variants you tried
  before reporting it. The uncomfortable implication: **the number of strategies
  you test has to be recorded, or the result is uninterpretable.** That is a
  discipline decision to make before writing code, not after.
- **Look-ahead bias.** Using today's close to decide today's trade. Trivially
  easy to do by accident with vectorised pandas operations, and it produces
  gorgeous fictional results.
- **Survivorship bias.** A watchlist of nine names that all exist and are all
  healthy in 2026 is *already* a survivorship-biased sample. Any backtest over
  today's SPY constituents inherits it.

None of this argues against Phase 2. It argues for building the measurement
discipline into the layer from the start, rather than bolting it on after the
first exciting backtest.

Sources:
[Deflated Sharpe Ratio (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) ·
[Statistical overfitting and backtest performance (LBL PDF)](https://sdm.lbl.gov/oapapers/ssrn-id2507040-bailey.pdf) ·
[The Seven Sins of Quantitative Investing](https://bookdown.org/palomar/portfoliooptimizationbook/8.2-seven-sins.html) ·
[Backtesting pitfalls guide](https://coriva.eu.org/en/backtesting-pitfalls/)

---

## 2. Data work Phase 2 forces, that Phase 1 got away with

This is the part I would budget most of the time for. Phase 1 reports what
happened yesterday, so small data sins are invisible. A signal layer computes
over a year of history, where they compound.

### Adjusted vs. raw closes — decide this first

Phase 1 fetches with `auto_adjust=False`, so the numbers in the brief are raw
prices. That is right for a brief ("AAPL closed at 308.91" should be the price
that was actually printed).

It is **wrong for indicators.** On an ex-dividend date a raw series shows a drop
that no holder experienced. A 4-for-1 split shows a 75% crash. Any moving
average, RSI or ATR computed over raw prices is contaminated at every corporate
action.

The likely resolution is to fetch both: raw for display, adjusted for
computation. That is a schema change to `TickerSnapshot`, which currently holds
one price series. Worth doing deliberately rather than flipping a flag.

### Point-in-time is not what yfinance gives you

Yahoo returns prices *as adjusted today*, not as they were known historically. A
backtest of a 2019 decision sees 2019 prices adjusted by every split since. For
signal generation on today's data this does not matter. For Phase 3 backtesting
it does, and it is the single strongest argument for a paid point-in-time data
source later.

### Rate limits become a real constraint

Phase 1 makes nine yfinance calls a day. A backtest sweeping parameters over a
year of intraday data makes thousands. Yahoo rate-limits aggressively — I hit
HTTP 429 within minutes during Phase 1 development, before any of the retry
logic was in. Phase 2 needs a local cache (parquet or SQLite) as a
prerequisite, not an optimisation.

---

## 3. Indicator library — verified findings

I probed these against the project's actual `pandas 3.0.5` in a throwaway venv.
Results are from running the code, not from documentation:

| Library | On PyPI | Works on pandas 3.0.5 | Notes |
|---|---|---|---|
| `pandas-ta` | **No — gone** | n/a | The widely-referenced original no longer resolves on PyPI. Most tutorials you will find point here |
| `pandas-ta-classic` 0.6.52 | Yes | **Yes — verified** | Community fork. RSI/ATR/MACD/SMA all computed correctly on our pandas |
| `ta` 0.11.0 | Yes | Not tested | Smaller, pure-Python, fewer indicators |
| `TA-Lib` 0.7.1 | Yes | Not tested | C library, needs a system-level build. Fastest, most painful to install |

**Recommendation: `pandas-ta-classic`,** and take the dependency reluctantly.

The counter-argument worth taking seriously: CLAUDE.md's standing rule says
prefer plain deterministic code for anything numeric. SMA, EMA, RSI, ATR and
MACD are perhaps 80 lines total, fully testable against hand-computed values,
with zero dependency risk — and the `pandas-ta` disappearance is a live
demonstration of that risk. If Phase 2 needs five indicators, write them. If it
needs fifty, take the library.

I lean toward **writing the first handful by hand**, because the tests you write
while doing it are the same tests that catch a look-ahead bug, and because you
will understand exactly what the numbers mean.

---

## 4. What a signal layer actually needs, beyond indicators

Sketched against the existing architecture. Not a plan — a checklist of parts
that turn out to be necessary.

1. **A history store.** Phase 1 holds one snapshot in memory. Signals need a
   series, cached locally, incrementally updated.
2. **Indicator computation over adjusted prices.** Pure functions,
   `series -> series`, no I/O, exhaustively unit-tested. This is the easy part.
3. **A signal definition that is explicit about timing.** Every signal needs to
   state which bar it may look at and which bar it acts on. If that is not
   enforced structurally, look-ahead bias will get in — being careful is not a
   mechanism. The strongest version: signals may only ever read bars strictly
   before the one they fire on, enforced in the type or the function shape.
4. **A signal registry with provenance.** Name, parameters, when added, why.
   This is the multiple-testing ledger from §1. Without it, no backtest number
   downstream can be honestly interpreted.
5. **Somewhere for signals to live in the brief.** Phase 1's brief is the
   natural delivery surface: a "Signals" section listing what fired, alongside
   the existing "What moved". Note that this changes the brief's character from
   informational to suggestive — worth being deliberate about, given the
   standing rule that Phase 4 is where anything acts.
6. **Explicitly *not* a backtester.** That is Phase 3. Resisting the urge to
   backtest a signal the day you write it is most of the discipline.

The good news: Phase 1's shape holds. `market_data.py` already isolates the
deterministic numeric layer from the LLM layer, which is exactly the seam a
signal layer slots into. Signals belong beside `market_data`, computed from raw
bars, and passed to `synthesis` as more finished numbers to write prose about.

---

## 5. Backtesting libraries — for Phase 3, noted now

Not needed yet, but it shapes how signals should be structured, so worth knowing:

- **`backtrader`** — went into long-term maintenance in 2023, author explicit
  that no major features are coming. Widely recommended in older tutorials.
  Probably not the choice for a new 2026 project.
- **`vectorbt`** — fastest for parameter sweeps. Note that "sweep thousands of
  parameter combinations quickly" is precisely the machine that generates the
  overfitting problem in §1. Powerful and dangerous in the same breath.
- **`backtesting.py`** — simplest, event-driven, realistic fills.

Common advice is to triage ideas vectorised and then re-run survivors through an
event-driven engine before believing anything. Reasonable, but it only works if
the trial count is recorded during the triage stage.

Sources:
[Python backtesting landscape 2026](https://python.financial/) ·
[Best Python backtest engines 2026](https://bullalert.ai/blog/best-python-backtest-engines-2026/) ·
[pandas-ta-classic](https://github.com/xgboosted/pandas-ta-classic)

---

## 6. Open questions — yours to answer, not mine

1. **What is a signal *for*, at this stage?** "RSI crossed 30" as something the
   brief mentions is a different feature from something you would size a
   position on. The first is a small addition to Phase 1. The second implies
   Phase 3 before it means anything. Which one are you building?
2. **Hand-written indicators or a library?** My lean is hand-written for the
   first five, per §3, but it is a real trade-off and it is yours.
3. **Are you willing to keep the trial ledger?** If the answer is no, Phase 3
   backtest numbers will not mean much, and it is better to know that going in
   than to discover it after a strategy disappoints live.
4. **Does the brief stay purely informational?** Adding a Signals section moves
   it toward suggestion. The standing rules put action at Phase 4 with a human
   checkpoint; worth deciding explicitly where a *suggestion* sits on that line.

---

## 7. My honest read

Phase 2 is worth doing, and the first useful version of it is smaller than it
sounds: adjusted-price fetching, a local cache, five hand-written indicators
with real tests, and a Signals section in the brief that reports what fired
without claiming it means anything.

That is maybe a day's work and it is genuinely useful — it would tell you when
something on the watchlist is at a 52-week high on rising volume, which the
current brief already half-knows but does not say.

The trap is going straight to parameter optimisation, because that is the fun
part and it is also the part that produces confident nonsense. The data-quality
work in §2 is dull and is what determines whether any of the rest is real.
