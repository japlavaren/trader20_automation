from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from automation.api.api import Api, Precision
from automation.api.futures_api import FuturesApi
from automation.api.spot_api import SpotApi
from automation.functions import parse_decimal
from automation.logger import Logger
from automation.message.buy_message import BuyMessage
from automation.message.sell_message import SellMessage
from automation.message.unknown_message import UnknownMessage
from automation.order_storage import OrderStorage
from automation.order import Order
from automation.parser.message_parser import MessageParser


class BombermanCoins:
    MARKET_TYPE_SPOT = 'SPOT'
    MARKET_TYPE_FUTURES = 'FUTURES'

    LEVERAGE_SMART = 'SMART'

    def __init__(self, market_type: str, spot_trade_amounts: Dict[str, Decimal],
                 futures_trade_amounts: Dict[str, Decimal], futures_leverage: Union[str, int],
                 spot_api: SpotApi, futures_api: FuturesApi, order_storage: OrderStorage, logger: Logger) -> None:
        assert market_type in (self.MARKET_TYPE_SPOT, self.MARKET_TYPE_FUTURES)
        assert isinstance(futures_leverage, int) or futures_leverage == self.LEVERAGE_SMART
        self._market_type: str = market_type
        self._trade_amounts: Dict[str, Dict[str, Decimal]] = {
            self.MARKET_TYPE_SPOT: spot_trade_amounts,
            self.MARKET_TYPE_FUTURES: futures_trade_amounts,
        }
        self._futures_leverage: Union[str, int] = futures_leverage
        self._spot_api: SpotApi = spot_api
        self._futures_api: FuturesApi = futures_api
        self._order_storage: OrderStorage = order_storage
        self._logger: Logger = logger

    def process(self, content: str, parent_content: Optional[str]) -> None:
        message = MessageParser.parse(content, parent_content)
        market_type = self.MARKET_TYPE_FUTURES if self._has_futures(message.symbol) else self.MARKET_TYPE_SPOT

        if isinstance(message, BuyMessage):
            return self._buy(market_type, message)
        elif isinstance(message, SellMessage):
            return self._sell(market_type, message)

        raise UnknownMessage()

    def process_spot_message(self, msg: Dict[str, Any]) -> None:
        if msg['e'] != 'executionReport':
            return

        api_order = Order(symbol=msg['s'], side=msg['S'], order_type=msg['o'], status=msg['X'], order_id=msg['i'],
                          order_list_id=msg['g'] if msg['g'] != -1 else None,
                          quantity=parse_decimal(msg['l']), price=parse_decimal(msg['L']), futures=False)

        if api_order.side == Order.SIDE_BUY:
            if api_order.type == Order.TYPE_LIMIT:
                self._process_spot_limit_buy_order(api_order)
        elif api_order.side == Order.SIDE_SELL:
            if api_order.type in (Order.TYPE_LIMIT_MAKER, Order.TYPE_STOP_LOSS_LIMIT):
                self._process_spot_oco_sell_order(api_order)

    def process_futures_message(self, msg: Dict[str, Any]) -> None:
        a = 1  # TODO

    def _has_futures(self, symbol: str) -> bool:
        return self._market_type == self.MARKET_TYPE_FUTURES and symbol in self._futures_api.futures_symbols

    def _buy(self, market_type: str, message: BuyMessage) -> None:
        currency = self._get_currency(message.symbol)
        amount = self._trade_amounts[market_type].get(currency, Decimal(0))

        if amount == Decimal(0):
            self._logger.log(
                f'SKIPPING {market_type} {message.symbol}',
                body=Logger.join_contents(message.content, message.parent_content),
            )
            return

        api: Api = self._futures_api if market_type == self.MARKET_TYPE_FUTURES else self._spot_api
        precision = api.get_precision(message.symbol)
        self._futures_api.leverage = 1  # TODO

        if message.buy_type == BuyMessage.BUY_MARKET:
            buy_order = api.market_buy(message.symbol, amount)
        elif message.buy_type == BuyMessage.BUY_LIMIT:
            assert message.buy_price is not None
            buy_order = api.limit_buy(message.symbol, message.buy_price, amount)
        else:
            raise UnknownMessage()

        if buy_order.status == Order.STATUS_NEW:
            buy_order.buy_message = message
            self._order_storage.add_limit_order(buy_order)

            self._logger.log_message(
                content=Logger.join_contents(message.content, message.parent_content),
                parts=[
                    f'{market_type} limit buy order created {buy_order.symbol}',
                    f'price: {round(buy_order.price, precision.price)}',
                ],
            )
        elif buy_order.status == Order.STATUS_FILLED:
            api.oco_sell(message.symbol, buy_order.quantity, message.targets, message.stop_loss)
            self._logger.log_message(
                content=Logger.join_contents(message.content, message.parent_content),
                parts=[
                          f'{market_type} market bought {buy_order.symbol}',
                          f'price: {round(buy_order.price, precision.price)}',
                      ] + self._get_oco_message_parts(message.targets, message.stop_loss, precision),
            )
        else:
            raise Exception(f'Unknown order status {buy_order.status}')

    def _sell(self, market_type: str, message: SellMessage) -> None:
        if message.sell_type != SellMessage.SELL_MARKET:
            raise UnknownMessage()

        api: Api = self._futures_api if market_type == self.MARKET_TYPE_FUTURES else self._spot_api
        oco_orders = api.get_oco_sell_orders(message.symbol)
        assert len(oco_orders) != 0, f'None {market_type} OCO sell orders found'
        total_quantity = Decimal(0)

        for orders in oco_orders:
            total_quantity += orders[0].quantity

            for order in orders:
                api.cancel_order(message.symbol, order.order_id)

        sell_order = api.market_sell(message.symbol, total_quantity)
        precision = api.get_precision(message.symbol)
        self._logger.log_message('', [
            f'{market_type} market sold {message.symbol}',
            f'price: {round(sell_order.price, precision.price)}',
        ] + self._get_profit_message_parts(message.symbol, total_quantity, sell_order.price, api))

    def _process_spot_limit_buy_order(self, api_order: Order) -> None:
        # TODO test futures
        original_order = self._order_storage.get_order_by_symbol_and_order_id(api_order.symbol, api_order.order_id)

        if original_order is None:
            return
        elif api_order.status == Order.STATUS_CANCELED:
            self._order_storage.remove(original_order)
        elif api_order.status == Order.STATUS_FILLED:
            buy_message = original_order.buy_message
            assert buy_message is not None
            self._spot_api.oco_sell(original_order.symbol, api_order.quantity, buy_message.targets,
                                    buy_message.stop_loss)
            precision = self._spot_api.get_precision(original_order.symbol)
            self._logger.log_message(
                content=Logger.join_contents(buy_message.content, buy_message.parent_content),
                parts=[
                          f'Spot limit bought {original_order.symbol}',
                          f'price: {round(original_order.price, precision.price)}',
                      ] + self._get_oco_message_parts(buy_message.targets, buy_message.stop_loss, precision),
            )
            self._order_storage.remove(original_order)

    def _process_spot_oco_sell_order(self, sell_order: Order) -> None:
        # TODO test futures
        if sell_order.status != Order.STATUS_FILLED:
            return

        typ = sell_order.type.lower().replace('_', ' ')
        precision = self._spot_api.get_precision(sell_order.symbol)
        self._logger.log_message('', [
            f'Spot OCO {typ} sold {sell_order.symbol}',
            f'price: {round(sell_order.price, precision.price)}',
        ] + self._get_profit_message_parts(sell_order.symbol, sell_order.quantity, sell_order.price, self._spot_api))

    def _get_profit_message_parts(self, symbol: str, quantity: Decimal, sell_price: Decimal, api: Api) -> List[str]:
        buy_order = api.get_last_buy_order(symbol)

        if buy_order is None or buy_order.quantity < quantity:
            return ['unknown profit']

        diff = sell_price - buy_order.price
        precision = api.get_precision(symbol)

        return [
            f'profit: {diff / buy_order.price * 100:.2f}%',
            f'gain: {round(diff * quantity, precision.price)} {self._get_currency(symbol)}',
        ]

    @staticmethod
    def _get_oco_message_parts(targets: List[Decimal], stop_loss: Decimal, precision: Precision) -> List[str]:
        return [
            'OCO sell order created',
            'TP: ' + ', '.join(f'{round(price, precision.price)}' for price in targets),
            f'SL: {round(stop_loss, precision.price)}',
        ]

    @staticmethod
    def _get_currency(symbol: str) -> str:
        return symbol.split('/')[1]
