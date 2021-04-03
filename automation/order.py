from decimal import Decimal
from typing import Any, Dict, Optional

from binance.client import Client

from automation.functions import parse_decimal
from automation.message.buy_message import BuyMessage


class Order:
    SIDE_BUY = Client.SIDE_BUY
    SIDE_SELL = Client.SIDE_SELL

    TYPE_MARKET = Client.ORDER_TYPE_MARKET
    TYPE_LIMIT = Client.ORDER_TYPE_LIMIT
    TYPE_STOP_MARKET = 'STOP_MARKET'
    TYPE_LIMIT_MAKER = 'LIMIT_MAKER'
    TYPE_STOP_LOSS_LIMIT = 'STOP_LOSS_LIMIT'

    STATUS_NEW = 'NEW'
    STATUS_FILLED = 'FILLED'
    STATUS_CANCELED = 'CANCELED'

    def __init__(self, symbol: str, side: str, order_type: str, status: str, order_id: int,
                 order_list_id: Optional[int], quantity: Decimal, price: Decimal, futures: bool = False,
                 original_type: Optional[str] = None) -> None:
        assert order_list_id != -1
        self.side: str = side
        self.symbol: str = symbol
        self.type: str = order_type
        self.status: str = status
        self.order_id: int = order_id
        self.order_list_id: Optional[int] = order_list_id
        self.quantity: Decimal = quantity
        self.price: Decimal = price
        self.futures: bool = futures
        self.original_type: Optional[str] = original_type
        self.buy_message: Optional[BuyMessage] = None

    @staticmethod
    def from_dict(values: Dict[str, Any], quantity_key: str, price_key: str = 'price', price: Decimal = None,
                  futures: bool = False) -> 'Order':
        if price is None:
            price = parse_decimal(values[price_key])

        quantity = parse_decimal(values[quantity_key])
        order_list_id = values['orderListId'] if values.get('orderListId', -1) != -1 else None

        return Order(values['symbol'], values['side'], values['type'], values['status'], values['orderId'],
                     order_list_id, quantity, price, futures)
