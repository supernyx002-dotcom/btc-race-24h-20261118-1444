"""
btc-race-24h-20261118-1444 — make.fun entry (Python 3.13 / stdlib only).

CANONICAL LOCATION: main.py at the repository root (the grader runs
`python3 -P -s /bot/main.py`, where /bot is this repository). A second
copy lives at bot/main.py, identical except for its header note.

WIRE PROTOCOL — agent-fun/bars-replay/v1, verified against the kit
(protocol.schema.json, RULES.txt, sdk/makefun_bars.py):
  * stdin/stdout are newline-delimited JSON. The harness sends `hello`
    once, then one `batch` per minute, then `done`. The bot answers
    EVERY batch with exactly one reply
    {"type": "reply", "seq": <batch seq>, "orders": [...]}, echoing seq.
  * A buy order is {"side": "buy", "symbol": "CBBTC",
    "notional_quote_units": <int USDC raw units, 6 decimals>,
    "max_slippage_bps": 100}. A sell order is the same shape with
    "side": "sell" and "qty": <int cbBTC raw units, 8 decimals>
    instead of notional_quote_units. No other keys, no floats.
  * Prices are integer strings at price_scale 5 (USDC = int / 1e5);
    qty_scale 8, quote_scale 6. Start capital 1,000 USDC
    (1,000,000,000 quote units). Long only: shorts=false, leverage=false,
    max 1 open position, max 16 orders/reply, max weight 10000 bps.
  * Orders decided on the batch of the bar closing at minute t fill at
    the OPEN of the next bar; fee 4 bps + modelled slippage 2 bps +
    constant-product price impact against that bar's open depth.
    A full-size round trip costs ~26 bps, so a trade must catch a move
    larger than that. The dev gate is net PnL > 0 on the frozen 24h dev
    window — a flat bot scores exactly 0 and FAILS, so this bot trades.
  * The vendored shim vendor/makefun_bars.py is a byte-identical copy
    of the kit's sdk/makefun_bars.py (RULES.txt: such a copy under
    vendor/ is left out of the authorship counts). It owns the wire:
    one reply per batch, client_ids, order validation.
  * Deterministic: no clock, no network, no files, no unseeded random.
    The same bars give the same replies, run after run.

STRATEGY — deterministic trend + mean-reversion hybrid on closes:
  * Trend filter: EMA(20) vs EMA(90). Momentum: RSI(14).
    Volatility: std of 1-minute log returns over 20 bars.
  * Long in uptrends, flat in downtrends (NO shorting — the kit's
    caps say shorts=false, so a "sell" only ever closes a long).
  * Mean-reversion dip-buy: RSI < 30 while the longer trend is not
    strongly down -> small long.
  * Position sizing: target up to 100% of equity when the signal is strong,
    scaled down when 1-minute volatility is high. Take-profit: trim
    half when the position is up > 4% and RSI > 70. Stop / drawdown
    guard: flatten if equity is down > 12% from its running peak, then
    sit out 30 bars. Minimum order $10, minimum 45-bar cooldown
    between trades, max_slippage_bps 100 (1%, as the kit baselines use).
  * Sizing and the position are read from the harness's own account
    (state.cash / state.equity / state.positions), never from a private
    book, so a rejected fill can never desync the bot.
"""

import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (os.path.join(_HERE, "vendor"),
              os.path.join(os.path.dirname(_HERE), "vendor")):
    if os.path.isfile(os.path.join(_cand, "makefun_bars.py")):
        sys.path.insert(0, _cand)
        break

import makefun_bars  # noqa: E402  (vendored kit shim, stdlib only)

# ---------------------------------------------------------------- config
SYMBOL = "CBBTC"
PRICE_SCALE = 5       # USDC = price_int / 10**5
QTY_SCALE = 8         # cbBTC raw units
QUOTE_SCALE = 6       # USDC raw units
QUOTE_PER_USDC = 10 ** QUOTE_SCALE
MIN_ORDER_QUOTE = 1_000_000          # 1 USDC, kit min_notional
MAX_SLIPPAGE_BPS = 100               # 1%, as the kit baselines use
TRADE_COOLDOWN_BARS = 45  # tuned on the kit dev window (see TESTS.md)
RANGE_SPREAD = 0.0008   # |EMA12-EMA48|/price below this = range regime
RANGE_RSI_BUY = 0
RANGE_RSI_SELL = 70
DD_GUARD_PCT = 0.12
DD_COOLDOWN_BARS = 30
TP_PCT = 0.04
BASE_TARGET = 1.00
MAX_TARGET = 1.00
MIN_TARGET = 0.30


# ---------------------------------------------------------------- helpers
class Ema:
    def __init__(self, period):
        self.alpha = 2.0 / (period + 1.0)
        self.value = None

    def update(self, x):
        if self.value is None:
            self.value = x
        else:
            self.value += self.alpha * (x - self.value)
        return self.value


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(len(closes) - period, len(closes)):
        d = closes[i] - closes[i - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


def realised_vol(closes, period=20):
    if len(closes) < period + 1:
        return 0.0
    rets = []
    for i in range(len(closes) - period, len(closes)):
        if closes[i - 1] > 0 and closes[i] > 0:
            rets.append(math.log(closes[i] / closes[i - 1]))
    if len(rets) < 2:
        return 0.0
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var)


def qty_for_value(value_quote_units, price_int):
    """cbBTC raw units worth value_quote_units at price_int."""
    return value_quote_units * 10 ** (QTY_SCALE + PRICE_SCALE) // (
        price_int * 10 ** QUOTE_SCALE)


# ---------------------------------------------------------------- bot
class Bot:
    def __init__(self):
        self.closes = []            # float USDC closes, oldest first
        self.ema_fast = Ema(20)
        self.ema_slow = Ema(90)
        self.peak_equity = None     # quote units (int)
        self.bars_since_trade = 10 ** 9
        self.dd_cooldown = 0

    def _target_fraction(self, price, eq_usd, current_frac):
        n = len(self.closes)
        if n < 90:
            return 0.0
        fast = self.ema_fast.value
        slow = self.ema_slow.value
        r = rsi(self.closes, 14)
        vol = realised_vol(self.closes, 20)
        if fast is None or slow is None or r is None:
            return 0.0
        vol_scale = 1.0
        if vol > 0.0005:
            vol_scale = max(0.4, 0.0005 / vol)
        trend_up = fast > slow
        trend_dn = fast < slow
        spread = abs(fast - slow) / slow if slow else 0.0
        if spread < RANGE_SPREAD:
            if r < RANGE_RSI_BUY:
                return BASE_TARGET * vol_scale
            if r > RANGE_RSI_SELL:
                return 0.0
            return current_frac
        if trend_up and r < 70:
            strength = min(1.0, 0.5 + spread * 200.0)
            return max(MIN_TARGET, BASE_TARGET * strength) * vol_scale \
                if strength > 0.6 else BASE_TARGET * 0.8 * vol_scale
        if trend_up and r >= 70:
            return MIN_TARGET * vol_scale
        if trend_dn and r > 30:
            return 0.0
        if trend_dn and r <= 30:
            if spread < 0.002:
                return MIN_TARGET * 0.5 * vol_scale
            return 0.0
        if r < 30 and not trend_dn:
            return BASE_TARGET * vol_scale
        return 0.0

    def on_batch(self, state, batch):
        """Return the wire orders for this batch (list, possibly empty)."""
        if state.warming_up:
            return []
        close_int = state.close(SYMBOL)
        if close_int is None or close_int <= 0:
            return []
        price = close_int / float(10 ** PRICE_SCALE)  # USDC
        self.closes.append(price)
        self.ema_fast.update(price)
        self.ema_slow.update(price)
        self.bars_since_trade += 1
        if self.dd_cooldown > 0:
            self.dd_cooldown -= 1

        equity = state.equity            # quote units (int)
        cash = state.cash                # quote units (int)
        if self.peak_equity is None:
            self.peak_equity = equity
        elif equity > self.peak_equity:
            self.peak_equity = equity
        eq_usd = equity / float(QUOTE_PER_USDC)

        held = state.positions.get(SYMBOL)
        held_qty = held.qty if held else 0
        held_value = state.value(SYMBOL, held_qty) if held_qty else 0
        current_frac = (held_value / equity) if equity > 0 else 0.0
        entry_price = None
        if held and held_qty > 0 and held.cost > 0:
            entry_price = (held.cost * 10 ** (QTY_SCALE + PRICE_SCALE)
                           / (held_qty * 10 ** QUOTE_SCALE)
                           / float(10 ** PRICE_SCALE))

        # --- drawdown guard: flatten, then sit out -------------------
        if self.peak_equity > 0 and \
                (self.peak_equity - equity) / self.peak_equity > DD_GUARD_PCT:
            if held_qty > 0:
                self.dd_cooldown = DD_COOLDOWN_BARS
                self.bars_since_trade = 0
                return [{"side": "sell", "symbol": SYMBOL, "qty": held_qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            return []
        if self.dd_cooldown > 0:
            return []
        if self.bars_since_trade < TRADE_COOLDOWN_BARS:
            return []

        # --- take-profit trim ----------------------------------------
        r = rsi(self.closes, 14)
        if held_qty > 0 and entry_price and r is not None and r > 70 \
                and price > entry_price * (1.0 + TP_PCT):
            half_qty = held_qty // 2
            if state.value(SYMBOL, half_qty) >= MIN_ORDER_QUOTE:
                self.bars_since_trade = 0
                return [{"side": "sell", "symbol": SYMBOL, "qty": half_qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]

        # --- target position -----------------------------------------
        target_frac = self._target_fraction(price, eq_usd, current_frac)
        target_value = int(target_frac * equity)
        diff = target_value - held_value
        if abs(diff) < MIN_ORDER_QUOTE:
            return []
        if diff > 0:
            spend = min(diff, cash)
            if spend < MIN_ORDER_QUOTE:
                return []
            self.bars_since_trade = 0
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": spend,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # diff < 0: sell part of the long (never more than held).
        sell_value = min(-diff, held_value)
        qty = qty_for_value(sell_value, close_int)
        qty = min(qty, held_qty)
        if qty <= 0 or state.value(SYMBOL, qty) < MIN_ORDER_QUOTE:
            # Sell-all is exempt from the min-notional floor; use it when
            # the target is (near) zero, otherwise hold.
            if target_value <= 0 and held_qty > 0:
                self.bars_since_trade = 0
                return [{"side": "sell", "symbol": SYMBOL, "qty": held_qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            return []
        self.bars_since_trade = 0
        return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def main():
    bot = Bot()
    makefun_bars.run(bot.on_batch)


if __name__ == "__main__":
    main()
