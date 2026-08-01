# Multi-asset research notes — eight symbols from the other app

**Research only. No application code has been written and none should be until
the recommendation in §6 has been read and decided.** No changes were made to
`market_data.py`, no new fetch functions exist, and `watchlist.json` is
untouched.

Written the same way as `PHASE2_NOTES.md`: where I verified something by
running it against live Yahoo, I say so and give the number. Where I am
relaying documentation or reasoning about what a field *means*, I say that
instead. The two are kept apart deliberately, because on this question most of
the plausible-sounding answers are wrong in ways only a real pull exposes.

**Probe environment.** yfinance **1.5.2**, pandas **3.0.5**, Python 3.11, run
**Saturday 2026-08-01 ~12:00 ET**, latest completed NYSE session 2026-07-31.
Pulls went through `build_session()` from `market_data.py` — the project's own
curl_cffi path — with `period="1y"`, `auto_adjust=False`, `timeout=30`, i.e.
byte-for-byte how Phase 1 fetches today. Fundamentals came from the same
`_fetch_fundamentals()` surface, plus one unfiltered `.info` pull so that
"Yahoo does not have it" could be told apart from "Phase 1 does not map it".

> Note on `requirements.txt`: it pins `yfinance>=0.2.55`. The verified results
> below are from 1.5.2. Field availability on Yahoo has historically moved
> between versions, so treat the field table as true for 1.5.2 specifically.

---

## 0. Two things that block work, found before the research started

Neither is in scope to fix here. Both are stated first because they change what
you should do next more than anything else in this document.

### `watchlist.json` on `main` is not valid JSON — Phase 1 cannot start

The current `main` (`e338486`, "Update watchlist.json", today 17:44 +0200) has
the file written with typographic quotes — `“name”` — instead of ASCII `"`.
Verified by running the project's own loader:

```
ConfigError: watchlist at /home/user/MyClaude1.0/watchlist.json is not valid
JSON: Expecting property name enclosed in double quotes: line 2 column 1 (char 2)
```

`load_watchlist()` raises `ConfigError` at `json.loads`, in `config.py`, before
any market data is fetched. This is upstream of every degrade-gracefully path
in the pipeline — the "one bad ticker must not end the run" logic never gets
reached, because there is no watchlist to iterate. **Phase 1 is currently
broken end to end on `main`.** It is a purely mechanical fix — 33 `“`/`”` pairs
to replace, zero straight quotes left in the file — and I have deliberately not
made it, per the scope line in the brief.

Worth noting the failure mode is a *good* one: it is loud, immediate, and names
the file and the column. Nothing silently ran with a partial list.

**The test suite already catches this.** Running `pytest` on `main` right now:

```
FAILED tests/test_config_cli.py::test_the_shipped_watchlist_is_valid
1 failed, 210 passed, 11 deselected
```

So the guard exists and works — it was simply never run, because the change
landed through GitHub's web UI rather than a session. Nothing needs to be built
here; the existing test would have blocked this on any local commit or CI run.
That is an argument for CI on `main` rather than for more tests.

### The watchlist content itself changed, and CLAUDE.md is now stale

What `main` actually contains (7 tickers, no `why` field on any entry):

> GOOG (Alphabet Class C), META, AAPL, TSLA, NVDA, MSFT, AMZN

CLAUDE.md still documents the old 9: SPY, QQQ, AAPL, MSFT, NVDA, AMZN, GOOGL,
JPM, XLE. Four names are gone (SPY, QQQ, JPM, XLE), two are new (META, TSLA),
and GOOGL became GOOG. The `why` field is gone from every entry — `Holding.why`
still exists and still flows into `summarize_for_prompt()` as "on the list
for: …", so that context is simply absent from the research prompts now.

The new `notes` field states the decision this document exists to answer:

> "Indices, commodities, and crypto held back for now, pending a separate
> market-analyst path."

So the eight symbols below were *deliberately excluded* from the Phase 1
watchlist today. That framing matters for §6: the question is not "how do we
squeeze these into the existing list", it is "what shape does the separate path
need". CLAUDE.md's standing rule says to keep it current truth — it is not,
right now.

---

## 1. Ticker resolution — verified, and three of the guesses were wrong

Every symbol below was pulled. "Resolves" means a non-empty 1y OHLCV frame plus
an `.info` payload actually came back.

| Display name | **Use this** | What Yahoo calls it | quoteType | Verdict on the candidate list |
|---|---|---|---|---|
| DXY | `DX-Y.NYB` | US Dollar Index | INDEX | `DX=F` **does not exist** — HTTP 404, "Quote not found for symbol: DX=F" |
| GOLD | `GC=F` | Gold Aug 26 | FUTURE | confirmed — but see the `GOLD` trap below |
| SILVER | `SI=F` | Silver Sep 26 | FUTURE | confirmed |
| USOIL | `CL=F` | Crude Oil Sep 26 | FUTURE | confirmed as **WTI**; `BZ=F` (Brent) also resolves and is a different benchmark |
| NASDAQ | `^NDX` | NASDAQ-100 | INDEX | **`^NDX` is the Nasdaq-100.** `^IXIC` is the Composite — both resolve |
| SPX500 | `^GSPC` | S&P 500 | INDEX | confirmed; `^SPX` also resolves and returns the identical close |
| IBEX35 | `^IBEX` | IBEX 35 | INDEX | confirmed — but see the `IBEX` trap below |
| BTCUSDC | `BTC-USD` | Bitcoin USD | CRYPTOCURRENCY | **no USDC pair exists on Yahoo** — see below |

### The two dangerous ones: symbols that resolve to the wrong asset silently

This is the finding I would put in front of anyone wiring these up.

- **`GOLD`** resolves. It returns a full, healthy frame — 251 bars, real
  volume, 17 mapped info keys. It is **`Gold.com, Inc.`, `quoteType=EQUITY`,
  close $41.36.** It is not the metal. Gold was $4,049.10 on the same day.
- **`IBEX`** resolves. It is **`IBEX Limited`, `quoteType=EQUITY`, close
  $35.34, currency USD.** It is not the Spanish index, which closed at
  €19,782.90.

Both would sail through `fetch_ticker()` without raising. `_is_not_found()`
never fires, because nothing failed — Yahoo answered the question it was asked.
The brief would print a plausible number under a label saying "Gold", and the
research step would go and find news about the wrong company. **The display
names in the other app are not safe to pass to yfinance directly**, and there
is no error path that catches this. It has to be a fixed, reviewed mapping.

The symbols that fail *safely* (empty frame → `TickerNotFound`, handled) were
`DX=F`, `XAUUSD=X`, `XAGUSD=X`, `SILVER`, `USOIL`, `^IBEX35`, `BTC-USDC`,
`BTCUSDC=X`, `BTCUSDC`.

### BTCUSDC has no exact match — this is a real, if small, fidelity loss

Verified: `BTC-USDC`, `BTCUSDC=X` and `BTCUSDC` all return empty frames. Yahoo
has no USDC-quoted pair for bitcoin. `BTC-USD` is the only option.

*Relayed, not verified:* USDC is a USD-pegged stablecoin, so BTC-USD tracks
BTC-USDC closely but not exactly — they differ by the peg basis and by which
venues each aggregates. For a daily brief that difference is almost certainly
below the noise floor. For anything that ever computes a P&L against actual
USDC-denominated holdings, it is a real basis and should not be quietly
ignored. Worth recording in the mapping that this one is an approximation while
the other seven are exact.

### Futures tickers are rolling front-month series, not one instrument

Verified from the `longName` field: `GC=F` is **"Gold Aug 26"**, `SI=F` is
**"Silver Sep 26"**, `CL=F` is **"Crude Oil Sep 26"**. These are continuous
front-month series whose underlying contract changes through the year. Two
consequences, both verified:

1. **The display name changes month to month.** `TickerSnapshot.display_name`
   falls back to `name` when `label` is empty, so a brief would say "Gold Aug
   26" this month and "Gold Oct 26" later. Setting an explicit `label` in the
   mapping avoids this entirely.
2. **`high_52w` / `low_52w` and the 21d/YTD changes span multiple contracts.**
   They are not one instrument's returns. `SI=F` currently reports
   `pct_from_52w_high = -52.5%` and `GC=F` `-27.5%`; those numbers mix
   contracts and are not what a reader will assume they mean.

I also checked whether the largest daily moves in the raw series are roll
artifacts or genuine, by testing whether the prior close falls inside the new
day's High/Low range. **Mixed, and I could not cleanly separate them.**
`SI=F` on 2026-01-30 moved -31.35% with the prior close *inside* the day's
range — a continuous, genuine move. But `SI=F` 2026-01-26 (+14.03%), `GC=F`
2026-02-03 (+6.08%) and `CL=F` 2026-04-08 (-16.41%) all had the prior close
*outside* the day's range, which is what a roll discontinuity looks like — and
also what an ordinary gap open looks like. I am not going to claim I know which
is which. What is verified is that **the discontinuities are present in the raw
series**, which is enough to make the point: this is the futures analogue of
the adjusted-vs-raw problem already flagged in `PHASE2_NOTES.md` §2, and it
lands on indicators harder than it lands on a daily brief.

---

## 2. Field-by-field audit — what actually comes back

Ran `compute_metrics()` and `_apply_fundamentals()` unmodified on all eight,
plus AAPL as an equity control. Values are the real 2026-07-31 pull.

### Price and volume block — computed from OHLCV in plain Python

| Field | DXY | GOLD | SILVER | USOIL | NASDAQ | SPX500 | IBEX35 | BTCUSDC | AAPL |
|---|---|---|---|---|---|---|---|---|---|
| `close` | 99.80 | 4,049.10 | 57.59 | 84.67 | 28,274.20 | 7,489.72 | 19,782.90 | 62,960.01 | 308.91 |
| `prev_close` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `day_open`/`high`/`low` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `volume` | **0** | 16,985 | 138 | 235,395 | 1.19e10 | 5.39e9 | **0** | 1.52e10 | 1.32e8 |
| `change_pct` (1d) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `change_5d_pct` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `change_21d_pct` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `change_ytd_pct` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `avg_volume_20d` | **0** | ✓ | ✓ | ✓ | ✓ | ✓ | **0** | ✓ | ✓ |
| `volume_ratio` | **None** | 3.01 | 0.38 | 0.83 | 1.52 | 1.06 | **None** | 0.61 | 2.60 |
| `high_52w`/`low_52w` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `pct_from_52w_high` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `intraday_range_pct` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `currency` | USD | USD | USD | USD | USD | USD | **EUR** | USD | USD |
| `quote_type` | INDEX | FUTURE | FUTURE | FUTURE | INDEX | INDEX | INDEX | CRYPTO… | EQUITY |
| `bars_used` | 251 | 251 | 251 | 251 | 251 | 251 | **256** | **366** | 251 |

**Every price-derived field works on every asset class, unchanged.** That is
the single most important row in this document and it is verified, not assumed:
`compute_metrics()` needed no modification and produced a correct value for all
eight on 16 of 18 numeric fields.

The two exceptions are both volume:

- **DXY has no volume anywhere.** Frame volume is 0 across a full month,
  `.info averageVolume` is 0, `regularMarketVolume` is absent. This is correct
  and expected — *relayed:* DXY is a computed index over six FX rates; there
  are no shares or contracts changing hands to count. `volume_ratio` comes back
  `None` because `avg_volume_20d` is 0 and the guard `if snapshot.avg_volume_20d`
  catches it. Degrades cleanly, no divide-by-zero.
- **^IBEX volume is 0 in the history frame but 107,858,866 in `.info`.** This
  one is a Yahoo inconsistency, not a conceptual gap — the constituent share
  volume genuinely exists and Yahoo reports it on one surface and not the
  other. Verified over a 1-month pull: frame volume sums to exactly 0. Note
  that `^GSPC` and `^NDX` **do** carry frame volume (1.1e11 and 1.8e11 over a
  month), so "indices have no volume" is not a rule you can rely on — it varies
  per index.

**Knock-on effect:** `is_notable_move` is `change_pct >= 2% OR volume_ratio >=
1.75`. With `volume_ratio = None` for DXY and IBEX35, those two silently fall
back to the price test alone. Not a crash, but they are held to a different
standard than the rest of the list, and nothing says so.

### Fundamentals block — mostly absent, and for three different reasons

| Field | DXY | GOLD | SILVER | USOIL | NASDAQ | SPX500 | IBEX35 | BTCUSDC | AAPL |
|---|---|---|---|---|---|---|---|---|---|
| `sector` | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | Technology |
| `industry` | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ | Consumer Elec. |
| `market_cap` | ∅ | ∅ | ∅ | ∅ | ○ | ○ | ○ | **1.26e12** | 4.54e12 |
| `trailing_pe` | ∅ | ∅ | ∅ | ∅ | ○ | ○ | ○ | ∅ | 35.47 |
| `forward_pe` | ∅ | ∅ | ∅ | ∅ | ○ | ○ | ○ | ∅ | 32.28 |
| `dividend_yield_pct` | ∅ | ∅ | ∅ | ∅ | ○ | ○ | ○ | ∅ | 0.35 |

Legend — and this is the distinction the brief asked for, drawn from the
unfiltered `.info` pull rather than guessed:

- **∅ = `None`, and the concept is meaningless for this asset class.** A
  futures contract has no P/E, no sector and no market cap. Neither does a
  currency index. Bitcoin has no P/E or dividend. These are not gaps to be
  filled later; there is nothing to put there, ever.
- **○ = `None`, but the concept is real and Yahoo just does not return it.**
  An equity index genuinely *has* an aggregate P/E, a dividend yield and a
  total market cap — these are quoted numbers in the real world. Yahoo returns
  none of them for `^GSPC`, `^NDX` or `^IBEX`. Verified against raw `.info`:
  the keys are absent, not null. If you ever want index P/E it has to come from
  somewhere other than yfinance.
- **`market_cap` on BTC-USD is populated: 1,263,521,103,872.** This is the one
  fundamental that crosses over. Note `fast_info.market_cap` is `None` for
  BTC-USD while raw `.info marketCap` is populated — `_fetch_fundamentals()`
  reads both and `_apply_fundamentals()` takes `marketCap or market_cap`, so
  the existing code already picks it up correctly. Nothing to change.

**Payload size is a decent proxy for how much fundamental data exists:** AAPL
returns 184 `.info` keys. The eight return 69–90 (DXY 69, indices 70–71,
futures 74, BTC 90). So it is not that these symbols return a thin or broken
payload — they return a *differently shaped* one, roughly 40% the size, with
the entire company-fundamentals block absent.

**No new `None` states are introduced.** Every one of these fields is already
`X | None` on `TickerSnapshot`, and the equity path already reaches all-`None`
whenever `.info` fails — which `market_data.py` explicitly tolerates
("Fundamentals are strictly best-effort").

Verified by reading the call sites rather than assuming: **`render.py`'s
`price_table()` does not render any fundamental at all.** Its nine columns are
Ticker, Close, 1d, 5d, 21d, YTD, Volume, vs 20d avg, vs 52w high — all
price-derived. Sector, market cap, P/E and dividend yield reach only
`summarize_for_prompt()`, which guards each with `if s.sector:` / `if
s.market_cap:` and simply omits the clause. So an all-`None` fundamentals block
changes the LLM's input and nothing else; the table is unaffected.

### One rendering bug the zero-volume symbols would expose

`_fmt_volume(0.0)` returns the string `"0"`, not `"—"` — verified by calling
it. The guard is `if value is None`, and `0.0` is not `None`. So DXY and IBEX35
would print a literal **0** in the Volume column, asserting that nothing traded,
rather than the em-dash the renderer uses everywhere else for "no data".
`_fmt_ratio(None)` correctly gives `"—"`, so the same row would read
`Volume 0 | vs 20d avg —`, which is self-contradictory. Small, but it is the
brief stating something false rather than declining to state it.

---

## 3. `market_clock.py` — which symbols it is *wrong* for, not merely imprecise

The brief asked for that line to be drawn sharply, so here it is, from a live
run at 12:00 ET on Saturday 2026-08-01, when `market_status()` returned
`state="weekend"`, `note="market closed for the weekend"`.

I tested two separate things: whether the **daily-bar calendar** matches
`is_trading_day()`, and whether the **session-state description** is true of the
asset at a given moment. They give different answers, which is the whole point.

### Calendar agreement — counted over a full year of real bars

| Symbol | Bars on days NYSE model calls closed | NYSE trading days with no bar | Verdict |
|---|---|---|---|
| AAPL (control) | 0 | 0 | exact |
| `CL=F`, `GC=F`, `SI=F` | 0 | 0 | **exact at daily resolution** |
| `DX-Y.NYB` | 0 | 0 | exact at daily resolution |
| `^NDX`, `^GSPC` | 0 | 0 | exact |
| `^IBEX` | **7** | **3** | **wrong in both directions** |
| `BTC-USD` | **115** | 0 | **wrong** |

### Session state — verified against real intraday hours

Pulled 1-hour bars for the last 5 days and listed which ET hours actually
contain trades:

| Symbol | ET hours with bars | Trades outside 09:30–16:00 ET? |
|---|---|---|
| AAPL | 9–15 | no |
| `^GSPC`, `^NDX` | 9–15 | no |
| `^IBEX` | **3–11** | yes — and it has *closed* by 11:35 ET |
| `CL=F`, `GC=F` | **0–16, 18–23** | yes, 23h/day |
| `DX-Y.NYB` | **0–23** | yes, 24h/day |
| `BTC-USD` | **0–23, including Saturday** | yes, 24/7 |

### The verdict, symbol by symbol

**Simply wrong — the model makes a false statement about the asset:**

- **`BTC-USD`.** Wrong on both axes and wrong right now. 115 bars over the past
  year fall on days `is_trading_day()` returns `False` for. At the moment of
  this run the brief would have said "market closed for the weekend" while
  BTC's own `regularMarketTime` was **2026-08-01 12:00 ET — Saturday, the same
  minute the probe ran.** There is no reading of "closed for the weekend" that
  is true of bitcoin. Every holiday note is wrong for it too.
- **`^IBEX`.** Wrong in *both* directions, which is worse than being wrong in
  one. It printed bars on 7 days the NYSE model calls closed (2025-09-01,
  2025-11-27, 2026-01-19, 2026-02-16, 2026-05-25, 2026-06-19, 2026-07-03 — US
  holidays Spain trades through), and printed *no* bar on 3 days the model
  calls open (2025-12-26, 2026-04-06, 2026-05-01 — *relayed:* Boxing Day,
  Easter Monday, Spanish Labour Day). So roughly ten days a year it is
  confidently wrong either way. Separately, it closes at 11:35 ET: from 11:35
  to 16:00 ET the brief says "market open" while IBEX has been shut for hours.
- **`CL=F`, `GC=F`, `SI=F`, `DX-Y.NYB` — wrong on state, right on calendar.**
  Their daily bars line up with NYSE days exactly (0 mismatches in a year), so
  `expected_latest_session` and the staleness check work fine. But at, say,
  03:00 ET the brief says "market closed overnight" while all four are actively
  trading — verified, they have bars in every ET hour from 0 to 8. The 17:00 ET
  hour is missing for the CME contracts (the daily maintenance break) and DXY
  trades straight through all 24. So: trust the calendar, do not trust the
  sentence.

**Imprecise but not wrong:**

- **`^NDX`, `^GSPC`.** Calendar exact, hours exact, no weekend or holiday bars.
  The only wrinkle is the one the brief predicted: their `regularMarketTime`
  is **17:15 and 17:22 ET** against AAPL's clean **16:00 ET**. The index level
  keeps being restated for an hour-plus after the close. So during 16:00–17:30
  ET a value can still move while the brief says the session is over. That is a
  timestamp nuance, not a false statement about whether the market is open.

**One structural consequence, verified by running the real pipeline** on a
mixed list of all eight plus AAPL: `_collect_warnings()` emitted

```
tickers do not share a single latest session date (2026-07-31, 2026-08-01)
— likely a mixed-exchange watchlist
```

That warning is doing its job. But with crypto on the list it will fire **every
single day**, because BTC always has a bar the equities do not. A warning that
is always on is a warning nobody reads, and it would sit in the brief next to
warnings that actually mean something. Note `is_stale` stayed `False` — it uses
`max()` over session dates, so crypto's newer bar masks the check for the other
symbols. If the equity feed were a day late, BTC's presence would hide it.

---

## 4. Currency — the quiet one

`^IBEX` is the only non-USD symbol: `currency="EUR"`, close **19,782.90**.

`TickerSnapshot.currency` already exists and is already populated correctly, so
this is not a schema gap. It is a **rendering** gap: `render.py` and
`summarize_for_prompt()` format every close with the same `{:,.2f}` and no unit.
A table row reading `19,782.90` next to `308.91` with no symbol invites the
reader — and the synthesis model, which is handed the same flat text — to
compare them or to read the IBEX number as dollars. Nothing crashes; the output
is just quietly misleading. Cheap to fix, and it belongs with whatever does the
rendering for these, not in the fetch layer.

---

## 5. What the existing code already handles, unchanged

Verified by running the real `fetch_watchlist()` over all eight plus AAPL:

- All eight fetched successfully in one pass, no errors, no retries triggered.
- `compute_metrics()` needed no changes for any asset class.
- `quote_type` is **already** populated with `INDEX` / `FUTURE` /
  `CRYPTOCURRENCY` / `EQUITY`. The discriminator you would branch on already
  exists on the dataclass and is already correct.
- Missing fundamentals produced `None`, not exceptions.
- `volume_ratio` degraded to `None` on zero-volume symbols without a
  divide-by-zero.
- The mixed-session warning fired correctly.

One field worth knowing about that Phase 1 does **not** currently map:
`.info["market"]` returns `us24_market` (futures + DXY), `us_market` (US
indices), `es_market` (IBEX), `ccc_market` (crypto). That is a ready-made,
Yahoo-maintained asset-class-and-calendar discriminator, present in every
payload, currently discarded by `_fetch_fundamentals()`'s key whitelist.
Verified present on all eight.

---

## 6. The recommendation

**One `TickerSnapshot` schema with more optional fields. Not per-asset-class
types.** And the per-class split you *do* need is one level up, in the session
model, not in the snapshot.

### What drove it

From §2: **16 of the 18 numeric fields populated correctly on all eight
symbols with zero code changes.** The two that did not (`volume`,
`volume_ratio`) failed by returning `0`/`None` through guards that already
exist. Per-asset types would mean eight variants of a dataclass that agree on
16 of 18 fields — that is not a different shape, that is the same shape with
holes.

From §2 again: **the fundamentals block is not a new problem.** Every one of
those fields is already `Optional`, and the equity path already reaches
all-`None` whenever `.info` fails, which the code explicitly tolerates by
design. The only consumer is `summarize_for_prompt()`, which guards each field
and omits the clause — the rendered table never touches them. Splitting the
type would buy a compile-time guarantee about fields that have exactly one
call site, and that call site already handles them correctly at runtime.

From §5: **the discriminator already exists.** `quote_type` is populated and
correct today. Anything that needs to branch — a renderer that omits the P/E
column for futures, a research prompt that asks about supply and demand instead
of earnings — can branch on it now, without a type split.

### What genuinely does not fit one type

**`MarketStatus`.** This is the real finding of §3, and it is not the thing the
question asked about. `MarketSnapshot` holds *one* `status` for the whole run,
because Phase 1 assumed one exchange. That assumption is now false in a way no
optional field repairs: "market closed for the weekend" is not a missing value
for bitcoin, it is a **false statement**. You cannot represent that as `None`.

So the split is: **one snapshot type, several session models.** Session state
becomes a per-symbol concern keyed off something like `.info["market"]` (§5),
with at minimum a 24/7 model for crypto, a nearly-24/5 model for
futures and DXY, the existing NYSE model for US equities and indices, and a
Madrid-calendar model for IBEX. The single global `MarketStatus` on
`MarketSnapshot` stays as "the NYSE context the brief was generated in", which
is still the right frame for a US-centric morning brief — it just stops being
the answer for every row.

### Two things I would not decide from research alone

Being explicit rather than guessing, per the brief:

1. **Whether these belong in the Phase 1 brief at all, or in the separate
   market-analyst path** the new `watchlist.json` notes point at. Today's
   watchlist decision deliberately pulled indices, commodities and crypto
   *out*. Everything above says the data layer could carry them; none of it
   says the daily brief is the right surface. That is a product call.
2. **How much the futures-roll contamination (§1) actually matters.** For a
   1-day change in a brief, not at all. For 52-week ranges it already produces
   numbers I would not put in front of a reader without a caveat. For Phase 2
   indicators it is the same class of problem as unadjusted splits. I would
   want to see one built partway — a real brief rendered with GC=F and CL=F in
   it — before deciding whether it needs a continuous-contract fix or just a
   footnote. That is a genuine "see it built to know", not a hedge.

### If you want the smallest honest next step

Not a plan, and no code was written for it: a fixed eight-row mapping table
(display name → verified ticker → explicit label → asset class), the `label`
set so futures never render as "Gold Aug 26", and a per-symbol session model.
The fetch layer underneath needs nothing.

---

## 7. My honest read

The mapping question turned out to be the easy half, and it still had two live
traps in it — `GOLD` and `IBEX` both resolve to real, healthy, completely wrong
equities, with no error anywhere. That alone justifies the "confirm every one by
actually pulling it" instruction; three of the eight candidate guesses in the
brief were wrong or non-existent, and two of the wrong ones fail *silently*.

The schema question is less interesting than it looks, and that is good news:
`market_data.py`'s existing separation — deterministic numerics over raw OHLCV,
everything else best-effort and optional — turns out to have been the right
shape for asset classes it was never tested against. It absorbed futures,
indices, a currency index and crypto without modification. The Phase 1
convention of "every step degrades, nothing crashes" is what made that true.

The clock is the actual work, and it is more than a tidy-up. Two of eight
symbols are flatly misdescribed by the current model, four more are misdescribed
outside RTH, and the one warning that would tell you something is wrong is
destined to fire every day and be ignored. If these eight land anywhere near
the brief, that is where the effort goes.

And none of it can be tried until `watchlist.json` parses again.

---

**Sources.** Every table and number above is from live pulls on 2026-08-01
(yfinance 1.5.2), not from documentation. Items explicitly marked *relayed* —
the meaning of the USDC peg, why a computed FX index has no volume, and the
identity of the three Spanish holidays — are reasoning or general knowledge, not
things I verified against a source. The probe scripts were kept out of the repo,
per the no-implementation scope.
