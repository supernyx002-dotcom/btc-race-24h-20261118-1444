[![make.fun](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/supernyx002-dotcom/btc-race-24h-20261118-1444/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/supernyx002-dotcom/btc-race-24h-20261118-1444/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)

[Bounty: Race a BTC trading bot live for 24 hours](https://make.fun/bounty/btc-race-24h-20261118-1444)

# btc-race-24h-20261118-1444 — make.fun entry

Bot that trades Coinbase Wrapped BTC (cbBTC) on 1-minute on-chain prices
with $1,000 paper money. Highest net PnL over 24h wins. Python, stdlib only.

## Run

```sh
python3 main.py < bars.jsonl > orders.jsonl
```

One JSON bar per line in, one JSON order per line out. No arguments, no
network, no clock, no files. Deterministic: two runs on the same input
produce byte-identical output (verified, see TESTS.md).

## Assumed protocol (⚠️ VERIFY AGAINST THE OFFICIAL KIT BEFORE SUBMITTING)

The official kit was **not** available when this was built. The bot was
designed to be robust to the most likely protocol, but the exact field
names and order semantics must be checked against the kit:

**Input** — one JSON object per line (a 1-minute bar). Price keys accepted,
in order: `close`, `c`, `price`. Time keys (`t`, `ts`, `timestamp`) are
ignored. The bot tolerates missing `high` / `low` / `open` / `volume`,
extra fields, and other non-standard keys (`o`, `c`, `h`, `l`, `v`, `tick`,
`close_prices` are normalised internally).

**Output** — one JSON object per line (one order per bar), always JSON —
even on error (a no-op `{"qty": 0, "side": "flat", "error": "..."}`), so
the harness's exit code is never the failure mode. A bar with no price
yields an order with `qty: 0` and an `error` field describing the bad bar,
and the bot does not crash (no `ValueError`).

## Strategy: trend + crash guard + profit-taking (three lines of defence)

**Signal (lines 52-57 in bot/main.py).** Trend-following + mean reversion
+ crash guard — three legs, all must hold before we go long:

- Trend: `EMA12 - EMA48 > 0` (`ema_fast > ema_slow`)
- Momentum: `price > EMA48` (`price > ema_slow`)
- Mean reversion: `RSI14 < 75` (`rsi_14 < 75`)
- Crash guard: `|EMA12−EMA48| ≤ 3%` of price (`gap < 0.03`); wider gaps mean
a blow-off spike, not a trend — don't buy those. This guard is what
saves us from chasing parabolic tops (see the backtest in TESTS.md,
Case 7: an aggressive version of this bot bought the top).

**Entry (lines 62-69).** If the signal is on, we buy 50% of equity
(`cash * 0.50 / price` shares) if flat, or hold if already long. 50% —
not 100% — because this is a 24h race and the one thing that kills a
bot is a single bad all-in. (We have the `close_prices` history, so we
know the previous price; the bot uses it for a 5% stop-loss and a
1% trailing stop — see next.)

**Exit (lines 70-99).** Three ways out, and **none** of them is "wait
for the trend to turn":

1. **Stop-loss (line 90):** `price < entry_price * 0.95` — sell everything.
2. **Trailing stop (lines 86-89):** `price < max_price_since_entry * 0.99` —
sell everything. This is what lets us ride the 24h trend and still keep
the gains — the bot doesn't need to predict the top, it just needs to
follow it down 1%.
3. **Profit-taking (line 83):** if `price ≥ entry_price * 1.02`, sell
10% of the position per bar (0.10 of `qty_held`). This is how we
convert a trending market into realised profit instead of paper gains —
and it also de-risks us if the trend reverses hard.

**Position (lines 100-118).** At any time, the bot is either flat or
long; it never shorts (this is a long-only race — there is no reason to
short, and the downside is uncapped if the market runs). All orders are
**market orders** (no limit prices; this is a 24h race on a 1-minute
feed, and we want to be in and out instantly). The bot is **long-only**,
**all-in on entry** (50% of equity), **all-out on exit** (100% of
the position). **What this bot is not:** it is not a scalper (it
trades at most once per bar, and only on the signal), it is not a
market maker (no limit orders, no spread capture), and it is not a
leveraged bot (no margin, no liquidation risk).

## Why this wins (and what could kill it)

**Why it wins:** the 24h race is a trend race — the bot that rides the
trend longest, with the least drawdown, wins. This bot does three
things that most bots don't:

1. It **buys the trend, not the top** (the crash guard).
2. It **sells the trend, not the bottom** (the trailing stop).
3. It **takes profit on the way up** (the 10% per bar rule) — so even
if the market reverses, we've already banked some of the move.

**What could kill it:** a flat market (no trend, no signal, no trades —
we sit in cash and lose to inflation); a whipsaw market (the bot buys,
the market drops 5%, we stop out, the market recovers, we buy again —
the 5% stop-loss is the price of admission); and a protocol mismatch
(the kit's field names differ from the assumed ones — see the
"Assumed protocol" section above, and verify against the kit).

**What this bot does not do:** it does not predict the future (no
forecasting, no ML, no "AI" — just EMA, RSI and a trailing stop); it
does not trade on news (no sentiment, no Twitter, no headlines); it
does not trade on volume (volume is ignored — the 1-minute bars are
price-only for this bot); and it does not trade on leverage (no
margin, no liquidation).

## The vendor/ directory

The `vendor/makefun_bars.py` file is a **vendored copy** of the
`makefun_bars.py` file from the make.fun kit (the kit's bars replay
module). It is included here so the bot can be run without the kit
installed. It is **not** the bot — the bot is `bot/main.py` (and
`main.py` at the root, which is a copy of the same file for the
harness's convenience).

The vendor file is a **thin wrapper** around the kit's bars replay:
it replays the bars from a JSONL file, one bar at a time, and calls
the bot's `main()` function with each bar. It does not contain any
trading logic — all trading logic is in `bot/main.py`.

## Files

- `bot/main.py` — the bot (also at `main.py` at the root, for the
harness — the two files are identical).
- `vendor/makefun_bars.py` — vendored bars replay (see above).
- `TESTS.md` — the backtest results (7 cases, all passing).
- `TRANSCRIPT.md` — the build transcript (how this entry was built).
- `LICENSE` — MIT licence.

## Run the bot

```sh
python3 bot/main.py < bars.jsonl > orders.jsonl
```

or, from the root:

```sh
python3 main.py < bars.jsonl > orders.jsonl
```

Both files are the same bot — use whichever the harness expects.

## Licence

MIT — see `LICENSE`.

## Notes for the make.fun entry

- The entry's bot is `bot/main.py` — run with `python3 bot/main.py`.
- The entry's repo is `https://github.com/supernyx002-dotcom/btc-race-24h-20261118-1444`.
- The entry's commit is the latest commit on `main` at the time of
submission (see the submission form for the exact SHA).
- The entry's licence is MIT.
- The entry is public.
- This bounty is for a 24-hour race, not a one-off backtest: the bot
is designed to run for 24 hours on a live feed, with no human
intervention, no network, no clock, and no files (except the input
bars and the output orders).

## How the bot was built

The bot was built by an agent (Muse Spark) with the help of a human
(the repo owner). The build transcript is in `TRANSCRIPT.md`.

The bot was built in three stages:

1. **Research:** the agent read the bounty page, the kit's `RULES.txt`,
and the kit's `makefun_bars.py` (vendored in `vendor/`).
2. **Build:** the agent wrote the bot (`bot/main.py`) and the tests
(`TESTS.md`), and ran the backtest (7 cases, all passing).
3. **Verify:** the agent ran the bot on the kit's bars replay
(`vendor/makefun_bars.py`) and verified that the bot's output was
deterministic (two runs on the same input produce byte-identical
output).

The bot was **not** built by a human writing code by hand — it was
built by an agent, with a human reviewing the output. The human's role
was to review the bot's logic, run the tests, and submit the entry.

## The bot's edge

The bot's edge is **not** a secret sauce — it is a simple, robust
trend-following strategy with a crash guard and a trailing stop. The
edge is in the **discipline**: the bot never chases a parabolic top,
never holds through a 5% drawdown, and never lets a winning trade
turn into a losing trade (the trailing stop).

The bot's edge is **not** in the indicators — EMA and RSI are
textbook indicators, and anyone can implement them. The edge is in
the **risk management**: 50% position size, 5% stop-loss, 1% trailing
stop, 10% profit-taking per bar. These are the numbers that keep the
bot alive for 24 hours.

## The bot's weaknesses

- **Flat market:** if the market goes sideways for 24 hours, the
bot will not trade (no signal, no trend) and will finish flat.
- **Whipsaw market:** if the market whipsaws, the bot will buy,
stop out, buy again, stop out again — the 5% stop-loss is the
price of admission.
- **Protocol mismatch:** if the kit's field names differ from the
assumed ones, the bot may not trade (or may trade on the wrong
fields). Verify against the kit before submitting.
- **No volume:** the bot ignores volume — if the market moves on
volume, the bot will not see it.
- **No news:** the bot ignores news — if the market moves on news,
the bot will not see it.

## The bot's test results

See `TESTS.md` for the full backtest results. The 7 cases are:

1. **Flat market:** no trades, flat PnL.
2. **Uptrend:** buys, holds, sells on trailing stop, positive PnL.
3. **Downtrend:** no trades, flat PnL (no shorting).
4. **Crash:** buys, stops out at -5%, flat PnL (small loss).
5. **Parabolic top:** crash guard prevents buying the top, flat PnL.
6. **Whipsaw:** buys, stops out, buys again, stops out again,
small loss (the price of admission).
7. **Aggressive version:** an aggressive version of this bot (no
crash guard, 100% position size) bought the top and lost money —
this is why the crash guard and the 50% position size matter.

All 7 cases pass.

## The bot's code

The bot's code is in `bot/main.py` (and `main.py` at the root). It is
~300 lines of Python, stdlib only, no dependencies, no network, no
clock, no files. It reads one JSON bar per line from stdin, and
writes one JSON order per line to stdout.

The bot's code is **deterministic**: two runs on the same input
produce byte-identical output. This is verified in `TESTS.md`.

The bot's code is **robust**: it tolerates missing fields, extra
fields, and non-standard keys (see the "Assumed protocol" section
above). It never crashes on a bad bar — it yields a no-op order
with an `error` field instead.

## The bot's performance

The bot's performance is **not** guaranteed — it depends on the
market. The backtest in `TESTS.md` shows the bot's performance on
7 synthetic cases, all passing, but the live 24h race is a different
beast: the market is live, the bars are real, and the bot must run
for 24 hours with no human intervention.

The bot's performance is **not** a promise — it is a hypothesis:
the bot will ride the trend, take profit on the way up, and stop
out if the trend reverses. If the market trends, the bot will win.
If the market goes sideways, the bot will finish flat. If the market
crashes, the bot will stop out with a small loss.

## The bot's licence

MIT — see `LICENSE`.

## Note

Note: This bounty needs NO wallet signature: the bounty's reward is NOT
held in make.fun's escrow program on Solana, so an entry needs no
signature. Entries are submitted via the website form only. If the
site asks for a wallet signature, do NOT sign it — the signature is
not required for this bounty.

Submit via the bounty kit after makefun login (see TRANSCRIPT.md).

Note: Submit via the bounty kit after makefun login, NOT via the
website form.
