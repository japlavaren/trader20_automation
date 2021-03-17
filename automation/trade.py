from decimal import Decimal
from typing import List, Optional


class Order:
    SIDE_BUY = 'BUY'
    SIDE_SELL = 'SELL'

    TYPE_MARKET = 'MARKET'
    TYPE_LIMIT = 'LIMIT'
    TYPE_LIMIT_MAKER = 'LIMIT_MAKER'
    TYPE_STOP_LOSS_LIMIT = 'STOP_LOSS_LIMIT'
    _TYPES = (TYPE_MARKET, TYPE_LIMIT, TYPE_LIMIT_MAKER, TYPE_STOP_LOSS_LIMIT)

    STATUS_NEW = 'NEW'
    STATUS_FILLED = 'FILLED'
    _STATUS = (STATUS_NEW, STATUS_FILLED)

    def __init__(self, symbol: str, side: str, order_type: str, status: str, order_id: int, quantity: Decimal,
                 price: Decimal, stop_price: Decimal = None) -> None:
        assert side in (self.SIDE_BUY, self.SIDE_SELL), f'Got side {side}'
        assert order_type in self._TYPES, f'Got type {order_type}'
        assert status in self._STATUS, f'Got status {status}'

        self.side: str = side
        self.symbol: str = symbol
        self.type: str = order_type
        self.status: str = status
        self.order_id: int = order_id
        self.quantity: Decimal = quantity
        self.price: Decimal = price
        self.stop_price: Optional[Decimal] = stop_price


class Trade:
    def __init__(self, buy_order: Order) -> None:
        assert buy_order.side == Order.SIDE_BUY
        self.orders: List[Order] = [buy_order]

    @property
    def buy_order(self) -> Order:
        orders = [o for o in self.orders if o.side == Order.SIDE_BUY]
        assert len(orders) == 1

        return orders[0]

    def get_orders_by_type(self, order_type: str) -> List[Order]:
        return [o for o in self.orders if o.type == order_type]

    def add_sell_order(self, sell_order: Order) -> None:
        assert sell_order.side == Order.SIDE_SELL
        assert sell_order not in self.orders

        self.orders.append(sell_order)
