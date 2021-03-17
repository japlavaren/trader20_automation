import pickle
from typing import List

from automation.order import Order


class OrderStorage:
    def __init__(self, file_path: str) -> None:
        self._file_path: str = file_path
        self._orders: List[Order] = self._load()

    def get_orders_by_symbol(self, symbol: str) -> List[Order]:
        return [order for order in self._orders if order.symbol == symbol]

    def add_limit_order(self, order: Order) -> None:
        assert order not in self._orders
        assert order.side == Order.SIDE_BUY
        assert order.type == Order.TYPE_LIMIT
        assert order.status == Order.STATUS_NEW
        assert order.buy_message is not None
        self._orders.append(order)
        self._save()

    def remove(self, order: Order) -> None:
        assert order in self._orders
        self._orders.remove(order)
        self._save()

    def _save(self) -> None:
        with open(self._file_path, 'wb') as h:
            pickle.dump(self._orders, h)

    def _load(self) -> List[Order]:
        try:
            with open(self._file_path, 'rb') as h:
                return pickle.load(h)
        except IOError:
            return []
