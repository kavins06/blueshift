"""SPY simple SMA trend filter for BlueShift.

This is a deliberately simple backtest candidate:
- trade SPY only
- evaluate once per day near the close
- long when the fast SMA is above the slow SMA and price is above fast SMA
- flat otherwise

It is meant as a stable BlueShift smoke strategy, not live-trading approval.
"""

from blueshift.api import get_datetime, order_target_percent, record, symbol


FAST_DAYS = 20
SLOW_DAYS = 60
TARGET_WEIGHT = 0.50
TRADE_MINUTE = 15 * 60 + 55


def initialize(context):
    context.asset = symbol("SPY")
    context.daily_closes = []
    context.last_signal_date = None
    context.current_target = 0.0


def current_close(data, asset):
    try:
        value = data.current(asset, "close")
    except Exception:
        return None
    try:
        if value is None or value != value:
            return None
    except Exception:
        return None
    return float(value)


def average(values):
    return sum(values) / len(values)


def position_quantity(context):
    position = context.portfolio.positions.get(context.asset)
    if position is None:
        return 0
    return getattr(position, "quantity", 0)


def handle_data(context, data):
    now = get_datetime()
    today = now.date()
    local_minute = now.hour * 60 + now.minute

    close = current_close(data, context.asset)
    if close is None:
        return

    if local_minute < TRADE_MINUTE or context.last_signal_date == today:
        record_state(context, close, None, None, "waiting")
        return

    context.last_signal_date = today
    context.daily_closes.append(close)
    if len(context.daily_closes) > SLOW_DAYS:
        context.daily_closes = context.daily_closes[-SLOW_DAYS:]

    if len(context.daily_closes) < SLOW_DAYS:
        print("warmup", today, "close", close, "days", len(context.daily_closes))
        record_state(context, close, None, None, "warmup")
        return

    fast_sma = average(context.daily_closes[-FAST_DAYS:])
    slow_sma = average(context.daily_closes[-SLOW_DAYS:])
    should_be_long = fast_sma > slow_sma and close > fast_sma
    target = TARGET_WEIGHT if should_be_long else 0.0

    if target != context.current_target:
        order_target_percent(context.asset, target)
        context.current_target = target
        print(
            "signal",
            today,
            context.asset,
            "close",
            close,
            "fast_sma",
            fast_sma,
            "slow_sma",
            slow_sma,
            "target",
            target,
        )
    else:
        print(
            "hold",
            today,
            context.asset,
            "close",
            close,
            "fast_sma",
            fast_sma,
            "slow_sma",
            slow_sma,
            "target",
            target,
        )

    record_state(context, close, fast_sma, slow_sma, "long" if should_be_long else "flat")


def record_state(context, close, fast_sma, slow_sma, state):
    record(
        close=close,
        fast_sma=0.0 if fast_sma is None else fast_sma,
        slow_sma=0.0 if slow_sma is None else slow_sma,
        target=context.current_target,
        quantity=position_quantity(context),
        state=state,
    )
