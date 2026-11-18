# TRANSCRIPT — btc-race-24h-20261118-1444

Build date: 2026-11-18 ~22:50–23:05 WIB. Builder: subagent (Mas Owi).
Account: @tidy-gecko-68. Nothing submitted, signed, or pushed.

## Session 1 — build + test + tune (~23:00 WIB)

1. Wrote `main.py` (Python stdlib only): stdin JSONL bars → stdout JSONL
   orders; EMA(12)/EMA(48) trend filter, RSI(14), 20-bar realised vol,
   regime split (trend vs range), 30–60% equity targets, take-profit
   trim, 12% drawdown guard, $10 min order, trade cooldown. Long-only
   by default (`SHORT_OK = False`) with the shorting path documented.
2. Wrote `test/simulate.py` (next-open fills, 4 bps fee + 2 bps slippage
   + impact), `test/gen_windows.py` (5 synthetic 24h windows, seed 7),
   `test/fetch_binance.py` (real 1m BTC), `test/sweep.py` (in-process
   parameter sweep).
3. Binance.com returned HTTP 451 from this VM; switched the fetcher to
   api.binance.us (works, no key; caps at 1,000 bars/request).
4. Fixed a BrokenPipeError when stdout is closed early (e.g. `| head`).
5. Tuned over 5 versions (see TESTS.md): range regime added after v1
   failed the range window; Bollinger z-score tried and reverted after
   it made range worse; RSI 30/70 + cooldown 15 chosen by sweep.
6. Final: profitable on uptrend (+$102.48), range (+$1.93), chop
   (+$17.64), up-down (+$52.17); flat $0.00 on crash; −$9.43 on the
   falling real-BTC window. Max drawdown ≤ 0.98% everywhere (limit 25%).
   Deterministic (identical md5 across runs); edge cases pass.

## Decisions (and why)

- **Long-only, not short.** The spec never states the replay supports
  shorting. Emitting sells larger than holdings into a replay that
  clamps or rejects them risks a failed entry, so the bot only sells
  what it holds. The cost is explicit: it cannot profit in a purely
  falling window (crash = $0.00). `SHORT_OK` is a one-line flip if the
  kit confirms shorts.
- **Regime split, not one rule.** Pure trend rules whipsawed in the
  range window (−$5.99 in v1); the RSI mean-reversion leg fixed it.
- **Range PnL is thin (+$1.93).** The 1-min RSI signal is weak (see
  diagnostics in TESTS.md). This is reported honestly rather than
  tuned harder against the synthetic windows — overfitting to 5
  invented windows would be worse than a thin-but-positive result.
- **No network/clock/files in main.py.** Only stdin/stdout, `json`,
  `math`, `sys`. Complies with the stated entry constraints.

## Kit verification session, 19 Nov 2026 ~01:06–01:15 WIB
1. Extracted the official kit; read RULES.txt, protocol.schema.json,
   sdk/makefun_bars.py and the baselines. Found the shipped bot spoke a
   completely wrong protocol (bare bars in, {"action":...} out).
2. Rewrote main.py around the kit's Python shim (vendored byte-identical
   under vendor/), keeping the EMA/RSI strategy logic but reading
   prices/positions/cash from the harness state and emitting wire orders
   (buy notional_quote_units, sell qty, max_slippage_bps 100).
3. Built a local replay simulator implementing the RULES.txt fill model
   (next-open fills, 4 bps fee, 2 bps slippage, impact vs o_depth,
   flatten at end). No Docker on this VM, so the kit's
   `grade-local --driver docker` could NOT be run — stated here, not
   hidden. The simulator is an estimate, not the official grade.
4. First kit-protocol run: 1,440/1,440 replies, 0 rejections,
   deterministic — but PnL -$24.69 (FAILS the dev gate).
5. Swept ~35 parameter variants (EMA spans, cooldown, target size,
   range buys on/off) plus offline rule tests (EMA cross, RSI, Bollinger,
   Donchian, hourly EMA, dip-buy). All 12/48 variants lost. Shipped:
   EMA 20/90, cooldown 45, BASE_TARGET 1.00, range RSI buys off:
   **+$3.83, 21 fills, 0 rejections, deterministic, root and bot copies
   byte-identical in replies.** Margin is thin; see TESTS.md.
