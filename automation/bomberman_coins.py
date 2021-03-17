from decimal import Decimal
from typing import Dict, List, Optional

from automation.binance_api import BinanceApi
from automation.logger import Logger
from automation.order_storage import OrderStorage
from automation.parser.message_parser import BuyMessage, MessageParser, UnknownMessage
from automation.parser.sell_message_parser import SellMessage
from automation.order import Order
from automation.symbol_watcher import SymbolWatcher


class BombermanCoins:
    def __init__(self, spot_trade_amounts: Dict[str, Decimal], api: BinanceApi, symbol_watcher: SymbolWatcher,
                 order_storage: OrderStorage, logger: Logger) -> None:
        self._spot_trade_amounts: Dict[str, Decimal] = spot_trade_amounts
        self._api: BinanceApi = api
        self._symbol_watcher: SymbolWatcher = symbol_watcher
        self._order_storage: OrderStorage = order_storage
        self._logger: Logger = logger

    def process(self, content: str, parent_content: Optional[str]) -> None:
        message = MessageParser.parse(content, parent_content)

        if isinstance(message, BuyMessage):
            return self._spot_buy(message)
        elif isinstance(message, SellMessage):
            return self._spot_sell(message)

        raise UnknownMessage()

    def process_changed_orders(self, last_micro_time: int) -> None:
        for symbol in self._symbol_watcher.symbols:
            api_orders = self._api.get_all_orders(symbol)
            self._process_changed_limit_orders(symbol, api_orders)
            self._process_sold_orders(api_orders, last_micro_time)

    def _spot_buy(self, message: BuyMessage) -> None:
        amount = self._spot_trade_amounts.get(message.currency, Decimal(0))

        if amount == Decimal(0):
            msg = f'SKIPPING spot {message.symbol}'
            self._logger.log(msg, message.content)
            return

        self._symbol_watcher.add_symbol(message.symbol)

        if message.buy_type == BuyMessage.BUY_MARKET:
            buy_order = self._api.market_buy(message.symbol, amount)
        elif message.buy_type == BuyMessage.BUY_LIMIT:
            assert message.buy_price is not None
            buy_order = self._api.limit_buy(message.symbol, message.buy_price, amount)
        else:
            raise UnknownMessage()

        if buy_order.status == Order.STATUS_NEW:
            buy_order.buy_message = message
            self._order_storage.add_limit_order(buy_order)
            self._logger.log_message(message.content, [
                f'Spot limit buy order {buy_order.symbol}',
                f'price: {buy_order.price}',
            ])
        elif buy_order.status == Order.STATUS_FILLED:
            self._api.oco_sell(message.symbol, buy_order.quantity, message.targets, message.stop_loss)
            self._logger.log_message(message.content, [
                f'Spot market bought {buy_order.symbol}',
                f'price: {buy_order.price}',
                'TP: ' + ', '.join(str(target) for target in message.targets),
                f'SL: {message.stop_loss}',
            ])
        else:
            raise Exception(f'Unknown order status {buy_order.status}')

    def _spot_sell(self, message: SellMessage) -> None:
        if message.sell_type == SellMessage.SELL_MARKET:
            return self._spot_market_sell(message)

        raise UnknownMessage()

    def _spot_market_sell(self, message: SellMessage) -> None:
        symbol = message.symbol
        oco_orders = self._api.get_oco_sell_orders(symbol)
        assert len(oco_orders) != 0, 'None OCO sell orders found'
        total_quantity = Decimal(0)

        # cancel all oco orders
        for oco_order, _ in oco_orders:
            self._api.cancel_order(symbol, oco_order.order_id)
            total_quantity += oco_order.quantity

        sell_order = self._api.market_sell(symbol, total_quantity)
        parts = [
            f'Spot market sold {symbol}',
            f'price: {sell_order.price}',
        ]
        buy_order = self._api.get_last_buy_order(symbol)

        if buy_order is not None and buy_order.quantity >= total_quantity:
            diff = sell_order.price - buy_order.price
            parts.append(f'profit: {diff / buy_order.price * 100:.2f}%')
            parts.append(f'gain: {diff * total_quantity}')
        else:
            parts.append('unknown profit')

        self._logger.log_message('', parts)

    def _process_changed_limit_orders(self, symbol: str, api_orders: List[Order]) -> None:
        limit_orders = self._order_storage.get_orders_by_symbol(symbol)
        limit_order_ids = set(order.order_id for order in limit_orders)

        for api_order in api_orders:
            if api_order.order_id in limit_order_ids:
                limit_order = [order for order in limit_orders if order.order_id == api_order.order_id][0]

                if api_order.status == Order.STATUS_CANCELED:
                    self._order_storage.remove(limit_order)
                elif api_order.status == Order.STATUS_FILLED:
                    buy_message = limit_order.buy_message
                    assert buy_message is not None
                    self._api.oco_sell(limit_order.symbol, limit_order.quantity, buy_message.targets,
                                       buy_message.stop_loss)
                    self._logger.log_message(buy_message.content, [
                        f'Spot limit bought {limit_order.symbol}',
                        f'price: {limit_order.price}',
                        'TP: ' + ', '.join(str(target) for target in buy_message.targets),
                        f'SL: {buy_message.stop_loss}',
                    ])

    def _process_sold_orders(self, api_orders: List[Order], last_micro_time: int) -> None:
        for order in api_orders:
            if order.time >= last_micro_time and self._is_oco_filled_sell_order(order):
                sell_order = order
                typ = order.type.lower().replace('_', ' ')
                parts = [
                    f'Spot {typ} sold {sell_order.symbol}',
                    f'price: {sell_order.price}',
                ]
                buy_order = self._api.get_last_buy_order(sell_order.symbol)

                if buy_order is not None and buy_order.quantity >= sell_order.quantity:
                    diff = sell_order.price - buy_order.price
                    parts.append(f'profit: {diff / buy_order.price * 100:.2f}%')
                    parts.append(f'gain: {diff * sell_order.quantity}')
                else:
                    parts.append('unknown profit')

                self._logger.log_message('', parts)

    @staticmethod
    def _is_oco_filled_sell_order(order: Order) -> bool:
        return (order.side == Order.SIDE_SELL and order.status == Order.STATUS_FILLED
                and order.type in (Order.TYPE_LIMIT_MAKER, Order.TYPE_STOP_LOSS_LIMIT))
