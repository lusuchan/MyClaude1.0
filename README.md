# briefbot

Phase 1 of the trading project: an automated daily market brief. Pulls price and
volume data for a watchlist, researches the news and geopolitical backdrop with
Claude's web search, and synthesises both into a readable markdown brief.

Information only. No signals, no recommendations, no execution — see
[CLAUDE.md](CLAUDE.md) for the phase roadmap and the standing rules.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then put your key in it:
#   ANTHROPIC_API_KEY=sk-ant-...
```

## Running it

```bash
python -m briefbot                      # the full brief, written to briefs/
python -m briefbot --dry-run            # print instead of writing
python -m briefbot --skip-research      # numbers only, no API calls, no cost
python -m briefbot --tickers SPY,TSLA   # ad-hoc list, ignores watchlist.json
python -m briefbot -v                   # show progress
```

Output lands in `briefs/brief-YYYY-MM-DD.md`, with `briefs/latest.md` always
pointing at the most recent run.

A full run takes about 90 seconds and costs roughly 200k input tokens across
three Claude calls (two research, one synthesis) plus 12 web searches.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | A brief was written |
| 1 | Nothing useful was produced, or the brief could not be written (its text goes to stdout) |
| 2 | `--strict` only: a brief was written but some step degraded |

## The watchlist

`watchlist.json` at the repo root. Nine liquid names to start — broad-market
ETFs, mega-cap tech, one bank, one energy ETF:

```json
{ "symbol": "SPY", "label": "S&P 500 ETF", "why": "the tape" }
```

`label` and `why` are both optional but both earn their keep: they end up in the
research prompt, so telling the model *why* a ticker is on the list shapes what
it looks for. A bare `"SPY"` string works too.

## How it fits together

```
market_data  ->  research  ->  synthesis  ->  render
  yfinance      Claude +        Claude        markdown
                web search
```

- **`market_data.py`** — OHLCV and best-effort fundamentals. Every number in the
  brief is computed here, in plain Python. The LLM is never asked to do
  arithmetic.
- **`research.py`** — two web-search calls, one for what moved the tickers and
  one for the macro/geopolitical backdrop. Kept separate so one failing still
  leaves the brief half-informed.
- **`synthesis.py`** — writes the prose only.
- **`render.py`** — assembles the document. The price table, caveats and sources
  are rendered mechanically from the snapshot, so no model output sits between
  the reader and a number.
- **`market_clock.py`** — NYSE session state and holidays, computed from rules
  rather than a table that goes stale.

### Degradation

Every step can fail without ending the run, and the brief says what it is
missing:

| What fails | What you get |
|---|---|
| One ticker | The rest of the watchlist, that ticker listed with its error |
| Ticker news research | Prices plus macro context |
| Macro research | Prices plus mover detail |
| Both research calls | A synthesised brief built on prices alone |
| Synthesis | A mechanically written body with the raw research below it |
| No API key | A numbers-only brief |
| Everything | A brief saying so, and exit code 1 |

## Tests

```bash
pytest              # 211 tests, no network
pytest -m live      # 11 more that hit Yahoo and the Claude API for real
```

The live tests are opt-in because they cost time and tokens. They exist because
mocked tests cannot catch an upstream shape change, and yfinance is an
unofficial wrapper around a payload Yahoo alters without notice. They assert on
plausibility — SPY did not move 25% today, the 52-week range brackets the close,
a dividend yield is between 0.1% and 15% — rather than on fixed values.

## Running it every morning

Nothing schedules this yet. A cron line is enough to start:

```cron
30 6 * * 1-5 cd /path/to/repo && ./venv/bin/python -m briefbot >> briefs/run.log 2>&1
```

6:30am on weekdays reads the prior session's close before the open. Delivery
channels (email, Slack) are a later refinement, not a Phase 1 requirement.

## Known limits

- **yfinance is unofficial.** It wraps Yahoo Finance, which changes without
  notice and rate-limits aggressively. Fine for a daily prototype; not something
  to trust unquestioned once real decisions depend on it.
- **Behind a TLS-inspecting proxy**, yfinance's default Chrome impersonation
  gets its connection reset. Set `YF_IMPERSONATE=safari`. Not needed on a normal
  network.
- **Adjusted vs. raw closes.** Bars are fetched with `auto_adjust=False`, so
  percentage moves are raw price changes. A ticker going ex-dividend will show a
  drop that is not a real loss to a holder. It matters little for the daily
  moves this brief reports; it will matter for Phase 2 indicators.
- **Fundamentals are best-effort.** `Ticker.info` is the slowest and flakiest
  surface yfinance exposes; a missing P/E never fails a run.
- **The brief is only as good as the web.** Claude cites its sources and is
  instructed to say "no clear catalyst" rather than guess, but a confidently
  reported wrong story upstream will still land in the brief. Read the sources
  when a claim matters.
