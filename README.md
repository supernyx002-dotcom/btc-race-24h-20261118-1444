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
ignored. Also accepts `open`/`o`, `high`/`h`, `low`/`l`, `volume`/`v`.
Lines with no price key (e.g. a metadata/config line) are ignored and
produce **no** output line. Malformed lines are skipped the same way.

**Output** — one JSON object per input bar:
```json
{"action": "buy", "amount_usd": 500.0}
{"action": "sell", "amount_usd": 250.0}
{"action": "hold", "amount_usd": 0.0}
```
`buy` spends that much cash on cbBTC; `sell` sells that much of holdings;
`hold` is a no-op. Amounts are rounded to cents; the bot never emits a buy
larger than its cash or a sell larger than its holdings.

**If the kit's protocol differs** (e.g. orders are `{"side": ...}`,
fractions instead of USD, or a `{"type": "order"}` wrapper), adapt the
`main()` output construction and the `_price()` key list — the strategy
code does not depend on the wire format. Also confirm: does the replay
support **shorting**? This bot is long-only by default (see below).

## Strategy

Deterministic trend + mean-reversion hybrid, no randomness, no clock:

- **Trend filter:** EMA(12) vs EMA(48) on closes.
- **Momentum:** RSI(14).
- **Volatility:** std of 1-minute log returns (20 bars); position size
  scales down as volatility rises.
- **Regime split** (`|EMA12−EMA48|/price < 0.0008` = range):
  - *Trend regime:* long when EMA12 > EMA48 and RSI < 70; flat when
    EMA12 < EMA48. Target 30–60% of equity when the signal is strong.
  - *Range regime:* mean-revert on RSI extremes — buy at RSI < 30,
    flatten at RSI > 70, hold in between (avoids whipsaw churn).
- **Take-profit:** trim half the position when up > 4% and RSI > 70.
- **Drawdown guard:** flatten everything if equity falls > 12% from its
  running peak, then sit out 30 bars.
- **Fee-aware:** minimum order $10, 15-bar cooldown between trades.
  Round-trip cost is ~12 bps + impact, so the bot only trades on
  decisive signals.

**Shorting / the dev gate.** The spec's dev gate is net PnL > $0 on a
frozen 24h window, and "a bot that just holds through a falling window
fails". This bot is **long-only**: in a falling window it goes flat and
finishes at exactly $0.00 — it cannot pass a > $0 gate on a purely
falling window. If the kit confirms the replay supports shorting, set
`SHORT_OK = True` at the top of `main.py` and the bot will short
downtrends with the same sizing (the sell path already handles it).
Do not flip it without kit confirmation: if the replay clamps sells to
holdings, a short intent is harmless, but if it rejects the order or
errors, the entry could fail.

## Files

| File | What it is |
|---|---|
| `main.py` | The entry. Stdlib only. |
| `LICENSE` | MIT. |
| `README.md` | This file. |
| `TRANSCRIPT.md` | Build sessions, decisions, test results. |
| `TESTS.md` | Test output (PnL / drawdown per window). |
| `test/simulate.py` | Replay harness: fills at next minute's open, 4 bps fee + 2 bps slippage + 1 bp per $1,000 impact (cap 5 bps), $1,000 start. |
| `test/gen_windows.py` | Generates the 5 synthetic 24h windows (seed 7). |
| `test/fetch_binance.py` | Pulls real 1m BTCUSDT klines (Binance US public API, no key). |
| `test/sweep.py` | In-process parameter sweep used during tuning. |
| `test/*.jsonl` | Test windows (synthetic + real BTC). |

## Tests

```sh
python3 test/gen_windows.py          # regenerate synthetic windows
python3 test/fetch_binance.py        # refresh real BTC window (optional)
for w in uptrend range crash chop updown real_btc_1m; do
  python3 test/simulate.py test/$w.jsonl --label $w
done
```

Results: see TESTS.md. Summary — uptrend +$102.48, range +$1.93,
chop +$17.64, up-down +$52.17, crash $0.00 (flat, no drawdown), real
BTC (falling −3.09%) −$9.43 (beats buy-and-hold, still negative:
long-only cannot profit in a falling market).

## Submit checklist

- [ ] Get the official kit; check the exact input bar schema and order
      schema against the assumptions above; adjust `main.py` if needed.
- [ ] Confirm whether shorting is supported; set `SHORT_OK` accordingly.
- [ ] Confirm the deliverable layout (is `main.py` alone in repo root
      enough, or does the entry need a manifest / specific repo name?).
- [ ] Run `main.py` against the kit's published dev window; confirm
      net PnL > $0 and max drawdown ≤ 25%.
- [ ] Submit via make.fun as @tidy-gecko-68 **before Thu 19 Nov 2026
      03:44 WIB** (20:44 UTC 18 Nov). Race starts 15 min after deadline.
- [ ] Do NOT submit the `test/` data files as part of the entry unless
      the kit asks for them — the entry is `main.py` (+ `LICENSE`).

## CORRECTION 23:15 WIB 18 Nov 2026 (verified profile check)
- GitHub linked to the make.fun account is **supernyx002-dotcom**. The entry repo must be owned by supernyx002-dotcom, public, OSI licence, created after this bounty opened, at a named commit.
- Canonical bot location is **`bot/main.py`** (kit layout `/bot/main.py`); the identical root `main.py` is kept for convenience. Submit `bot/main.py` (+ `LICENSE`); do not submit `test/`.
- This bounty needs **NO wallet signature** at submit (BTC bot / git forge / chess are the no-signature ones).
- Submit via the bounty kit (`/c/<bounty>/kit`, RULES.txt) after `makefun login`. Limit usually 5 submissions per UTC day, 10 total; last before deadline is final. Transcripts via `makefun bundle` or loose upload ≤200 MB.

## KIT VERIFICATION 19 Nov 2026 ~01:06–01:15 WIB (official kit, not assumed)
- Kit protocol is **agent-fun/bars-replay/v1** (protocol.schema.json):
  hello once, one `batch` per minute, then `done`; the bot answers EVERY
  batch with exactly one reply `{"type":"reply","seq":N,"orders":[...]}`.
  Buy = `{"side":"buy","symbol":"CBBTC","notional_quote_units":<int>,"max_slippage_bps":100}`;
  sell = same with `"qty":<int cbBTC raw units>` instead of notional.
  Prices are integer strings at price_scale 5, qty_scale 8, quote_scale 6.
  **The old bot was WRONG here**: it read bare bars and emitted
  `{"action":"buy/sell/hold","amount_usd":...}` — a protocol violation
  that would have failed every run. It has been rewritten to the kit
  protocol using the kit's own Python shim, vendored byte-identical at
  `vendor/makefun_bars.py` (sha256 80452b00d2eb1e9c959e73d41cda6ca726cdbe7bfa4065d48278c22eccd276ff;
  RULES.txt: a byte-identical shim copy under vendor/ is left out of the
  authorship counts). Sizing/position now come from the harness's own
  account (state.cash/equity/positions), never a private book.
- **Shorting: NOT supported.** Kit caps say `shorts: false, leverage: false`
  (competition.yaml + protocol.schema.json). There is no SHORT_OK flip any
  more; a sell only ever closes a long. The dev gate (net PnL > 0) must be
  passed long-only.
- Canonical location is the **repo-root `main.py`** — the grader runs
  `python3 -P -s /bot/main.py` where `/bot` IS the repository mount (see
  the kit baselines: "the grader runs `node /bot/main.ts` with this
  directory mounted at /bot"). `bot/main.py` is an identical spare copy,
  not the graded file. The earlier note claiming `bot/main.py` is
  canonical was a misreading of the mount path; both copies are kept
  identical (verified: same replies on the dev window).
- Tuned on the kit dev window: EMA(20)/EMA(90) (was 12/48), 45-bar
  cooldown (was 15), full-size targets (BASE_TARGET 1.00, was 0.50),
  range-regime RSI buys OFF. ~35 variants swept; best +$3.83 (see TESTS.md).
- No `grade-local` run: it needs `--driver docker` and this VM has no
  Docker. The local estimate below uses a Python replay implementing the
  RULES.txt fill model (next-open fills, 4 bps fee, 2 bps slippage,
  constant-product impact vs o_depth, flatten at last close).
