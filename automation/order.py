from decimal import Decimal
from typing import Any, Dict, Optional

from automation.functions import parse_decimal
from automation.parser.buy_message_parser import BuyMessage


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
    STATUS_CANCELED = 'CANCELED'
    STATUS_EXPIRED = 'EXPIRED'
    _STATUS = (STATUS_NEW, STATUS_FILLED, STATUS_CANCELED, STATUS_EXPIRED)

    def __init__(self, symbol: str, side: str, order_type: str, status: str, order_id: int,
                 order_list_id: Optional[int], time: int, quantity: Decimal, price: Decimal) -> None:
        assert side in (self.SIDE_BUY, self.SIDE_SELL), f'Got side {side}'
        assert order_type in self._TYPES, f'Got type {order_type}'
        assert status in self._STATUS, f'Got status {status}'

        self.side: str = side
        self.symbol: str = symbol
        self.type: str = order_type
        self.status: str = status
        self.order_id: int = order_id
        self.order_list_id: Optional[int] = order_list_id
        self.time: int = time
        self.quantity: Decimal = quantity
        self.price: Decimal = price
        self.buy_message: Optional[BuyMessage] = None

    @staticmethod
    def from_dict(values: Dict[str, Any], quantity_key: str, time_key) -> 'Order':
        order_list_id = values['orderListId'] if values['orderListId'] != -1 else None
        quantity = parse_decimal(values[quantity_key])
        price = parse_decimal(values['price'])

        return Order(values['symbol'], values['side'], values['type'], values['status'], values['orderId'],
                     order_list_id, values[time_key], quantity, price)
