"""Execution boundary for future exchange integration.

No live order implementation is present. Environment variables cannot unlock it.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class LiveTradingDisabled(PermissionError):
    """Raised before any authenticated exchange operation can be attempted."""


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    quantity: str
    reduce_only: bool = False

    def validate(self):
        if not self.symbol.endswith('/USDT:USDT'):
            raise ValueError('only USDT-margined perpetuals are supported')
        if self.side not in ('buy', 'sell'):
            raise ValueError('invalid side')
        try:
            quantity = Decimal(self.quantity)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError('invalid quantity') from exc
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError('quantity must be positive and finite')
        if not isinstance(self.reduce_only, bool):
            raise ValueError('reduce_only must be boolean')


class ExecutionGate:
    """Fail-closed boundary. No credentials or exchange client are accepted."""

    def __init__(self, mode='paper'):
        if mode != 'paper':
            raise LiveTradingDisabled('Live trading is not implemented or authorized')
        self.mode = mode

    def simulate(self, intent: OrderIntent):
        intent.validate()
        return {'mode': 'paper', 'status': 'not_submitted',
                'symbol': intent.symbol, 'side': intent.side,
                'quantity': intent.quantity, 'reduce_only': intent.reduce_only}

    def submit_order(self, *_args, **_kwargs):
        raise LiveTradingDisabled('Exchange order submission is disabled')

    def cancel_order(self, *_args, **_kwargs):
        raise LiveTradingDisabled('Exchange order cancellation is disabled')

    def set_leverage(self, *_args, **_kwargs):
        raise LiveTradingDisabled('Authenticated exchange operations are disabled')
