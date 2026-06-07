"""Observe-only BlueShift strategy template.

Paste this into a BlueShift strategy project to verify that account, portfolio,
and market-data access work before adding execution logic.
"""

from blueshift.api import record, schedule_function, symbol
from blueshift.api import date_rules, time_rules


def initialize(context):
    context.asset = symbol("SPY")
    context.did_record_start = False

    schedule_function(
        record_open_state,
        date_rule=date_rules.every_day(),
        time_rule=time_rules.market_open(minutes=5),
    )
    schedule_function(
        record_close_state,
        date_rule=date_rules.every_day(),
        time_rule=time_rules.market_close(minutes=5),
    )


def record_open_state(context, data):
    record_state(context, data, "open")


def record_close_state(context, data):
    record_state(context, data, "close")


def record_state(context, data, label):
    portfolio = context.portfolio
    account = context.account

    last_price = data.current(context.asset, "price")
    positions = portfolio.positions
    position = positions.get(context.asset)
    quantity = 0 if position is None else position.quantity

    record(
        price=last_price,
        cash=portfolio.cash,
        portfolio_value=portfolio.portfolio_value,
        net_exposure=account.net_exposure,
        quantity=quantity,
    )

    print(
        "observe_only",
        label,
        context.asset,
        "price",
        last_price,
        "cash",
        portfolio.cash,
        "portfolio_value",
        portfolio.portfolio_value,
        "net_exposure",
        account.net_exposure,
        "quantity",
        quantity,
    )


def handle_data(context, data):
    # Intentionally no orders. Use scheduled records above for connection checks.
    return
