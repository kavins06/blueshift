"""GLD refined two-rule intraday playbook for BlueShift.

Research source:
- artifacts/autoresearch/gld-two-rule-refinement-report.md
- artifacts/autoresearch/gld-refined-playbook-trade-tick-replay.md

This is long-only GLD stock logic. It does not trade GLD options.
Backtest and paper-forward this file before any live deployment.
"""

from blueshift.api import get_datetime, get_open_orders, order_target_percent, record, symbol


SESSION_OPEN = 9 * 60 + 30
OPENING_SIGNAL_MINUTE = 9 * 60 + 44
OPENING_ENTRY_MINUTE = 9 * 60 + 50
OPENING_TIME_EXIT_MINUTE = 14 * 60 + 50
OPENING_MIN_MOVE = 0.0010
OPENING_TARGET = 0.0035

FLUSH_SIGNAL_MINUTE = 9 * 60 + 49
FLUSH_ENTRY_MINUTE = 10 * 60 + 35
FLUSH_TIME_EXIT_MINUTE = 12 * 60
FLUSH_THRESHOLD = -0.0020
FLUSH_TARGET = 0.0050

MAX_POSITION_PCT = 0.50
MAX_DAILY_LOSS_PCT = 0.0075
MAX_TRADE_LOSS_PCT = 0.0100


def initialize(context):
    context.asset = symbol("GLD")
    context.session_date = None
    context.prior_close = None
    context.session_open = None
    context.opening_signal = False
    context.flush_signal = False
    context.active_rule = None
    context.entry_price = None
    context.target_price = None
    context.time_exit_minute = None
    context.day_start_value = None
    context.daily_halt = False
    context.last_regular_close = None


def handle_data(context, data):
    now = get_datetime()
    local_minute = (now.hour * 60) + now.minute
    today = now.date()

    if context.session_date != today:
        reset_session(context, today)

    if local_minute < SESSION_OPEN or local_minute >= 16 * 60:
        return

    price = current_price(data, context.asset, "close")
    if price is None:
        return

    if local_minute == SESSION_OPEN:
        context.session_open = current_price(data, context.asset, "open") or price
        if context.day_start_value is None:
            context.day_start_value = context.portfolio.portfolio_value

    update_daily_halt(context)
    manage_open_position(context, data, local_minute, price)

    if context.daily_halt or has_open_orders(context):
        record_state(context, price)
        return

    if local_minute == OPENING_SIGNAL_MINUTE:
        evaluate_opening_signal(context, price)
    elif local_minute == FLUSH_SIGNAL_MINUTE:
        evaluate_flush_signal(context, price)

    if not has_position(context):
        if local_minute == OPENING_ENTRY_MINUTE and context.opening_signal:
            enter_long(context, price, "opening_strength", OPENING_TARGET, OPENING_TIME_EXIT_MINUTE)
        elif local_minute == FLUSH_ENTRY_MINUTE and context.flush_signal:
            enter_long(context, price, "flush_reversal", FLUSH_TARGET, FLUSH_TIME_EXIT_MINUTE)

    context.last_regular_close = price
    record_state(context, price)


def reset_session(context, today):
    if context.last_regular_close is not None:
        context.prior_close = context.last_regular_close
    context.session_date = today
    context.session_open = None
    context.opening_signal = False
    context.flush_signal = False
    context.active_rule = None
    context.entry_price = None
    context.target_price = None
    context.time_exit_minute = None
    context.day_start_value = context.portfolio.portfolio_value
    context.daily_halt = False


def evaluate_opening_signal(context, signal_close):
    if context.session_open is None or context.prior_close is None:
        context.opening_signal = False
        return
    first_move = (signal_close / context.session_open) - 1.0
    context.opening_signal = (
        context.session_open > context.prior_close
        and first_move >= OPENING_MIN_MOVE
    )


def evaluate_flush_signal(context, signal_close):
    if context.session_open is None:
        context.flush_signal = False
        return
    first_move = (signal_close / context.session_open) - 1.0
    context.flush_signal = first_move <= FLUSH_THRESHOLD


def enter_long(context, price, rule_name, target_return, time_exit_minute):
    order_target_percent(context.asset, MAX_POSITION_PCT)
    context.active_rule = rule_name
    context.entry_price = price
    context.target_price = price * (1.0 + target_return)
    context.time_exit_minute = time_exit_minute
    print("entry", rule_name, context.asset, "close", price, "target", context.target_price)


def manage_open_position(context, data, local_minute, price):
    if not has_position(context):
        return
    if context.entry_price is None or context.target_price is None:
        flatten(context)
        return

    high = current_price(data, context.asset, "high") or price
    trade_return = (price / context.entry_price) - 1.0
    if high >= context.target_price:
        print("exit", context.active_rule, "target", context.asset, "close", price)
        flatten(context)
    elif trade_return <= -MAX_TRADE_LOSS_PCT:
        print("exit", context.active_rule, "stop", context.asset, "close", price)
        flatten(context)
    elif context.time_exit_minute is not None and local_minute >= context.time_exit_minute:
        print("exit", context.active_rule, "time", context.asset, "close", price)
        flatten(context)


def update_daily_halt(context):
    if context.day_start_value is None or context.day_start_value <= 0:
        return
    daily_return = (context.portfolio.portfolio_value / context.day_start_value) - 1.0
    if daily_return <= -MAX_DAILY_LOSS_PCT:
        context.daily_halt = True
        if has_position(context):
            flatten(context)


def flatten(context):
    if not has_open_orders(context):
        order_target_percent(context.asset, 0.0)
    context.active_rule = None
    context.entry_price = None
    context.target_price = None
    context.time_exit_minute = None


def has_position(context):
    position = context.portfolio.positions.get(context.asset)
    return position is not None and getattr(position, "quantity", 0) != 0


def has_open_orders(context):
    try:
        orders = get_open_orders(context.asset)
    except TypeError:
        orders = get_open_orders()
    return bool(orders)


def current_price(data, asset, field):
    try:
        value = data.current(asset, field)
    except Exception:
        return None
    try:
        if value is None or value != value:
            return None
    except Exception:
        return None
    return float(value)


def record_state(context, price):
    position = context.portfolio.positions.get(context.asset)
    quantity = 0 if position is None else getattr(position, "quantity", 0)
    record(
        close=price,
        quantity=quantity,
        opening_signal=int(bool(context.opening_signal)),
        flush_signal=int(bool(context.flush_signal)),
        daily_halt=int(bool(context.daily_halt)),
    )
