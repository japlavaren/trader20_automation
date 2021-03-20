from decimal import Decimal
from typing import Any, Dict, List, Optional

from automation.binance_api import BinanceApi, Precision
from automation.functions import parse_decimal
from automation.logger import Logger
from automation.message.buy_message import BuyMessage
from automation.message.sell_message import SellMessage
from automation.message.unknown_message import UnknownMessage
from automation.order_storage import OrderStorage
from automation.order import Order
from automation.parser.message_parser import MessageParser


class BombermanCoins:
    def __init__(self, spot_trade_amounts: Dict[str, Decimal], api: BinanceApi, order_storage: OrderStorage,
                 logger: Logger) -> None:
        self._spot_trade_amounts: Dict[str, Decimal] = spot_trade_amounts
        self._api: BinanceApi = api
        self._order_storage: OrderStorage = order_storage
        self._logger: Logger = logger

    def process(self, content: str, parent_content: Optional[str]) -> None:
        message = MessageParser.parse(content, parent_content)

        if isinstance(message, BuyMessage):
            return self._spot_buy(message)
        elif isinstance(message, SellMessage):
            return self._spot_sell(message)

        raise UnknownMessage()

    def process_order_message(self, msg: Dict[str, Any]) -> None:
        assert msg['e'] == 'executionReport'
        list_order_id = msg['g'] if msg['g'] != -1 else None
        api_order = Order(symbol=msg['s'], side=msg['S'], order_type=msg['o'], status=msg['X'], order_id=msg['i'],
                          order_list_id=list_order_id, quantity=parse_decimal(msg['l']), price=parse_decimal(msg['L']))

        if api_order.side == Order.SIDE_BUY:
            if api_order.type == Order.TYPE_LIMIT:
                self._process_limit_buy_order(api_order)
        elif api_order.side == Order.SIDE_SELL:
            if api_order.type in (Order.TYPE_LIMIT_MAKER, Order.TYPE_STOP_LOSS_LIMIT):
                self._process_oco_sell_order(api_order)

    def _spot_buy(self, message: BuyMessage) -> None:
        currency = self._get_currency(message.symbol)
        amount = self._spot_trade_amounts.get(currency, Decimal(0))

        if amount == Decimal(0):
            self._logger.log(
                f'SKIPPING spot {message.symbol}',
                body=Logger.join_contents(message.content, message.parent_content),
            )
            return

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
            precision = self._api.get_precision(message.symbol)
            self._logger.log_message(
                content=Logger.join_contents(message.content, message.parent_content),
                parts=[
                    f'Spot limit buy order created {buy_order.symbol}',
                    f'price: {round(buy_order.price, precision.price)}',
                ],
            )
        elif buy_order.status == Order.STATUS_FILLED:
            self._api.oco_sell(message.symbol, buy_order.quantity, message.targets, message.stop_loss)
            precision = self._api.get_precision(message.symbol)
            self._logger.log_message(
                content=Logger.join_contents(message.content, message.parent_content),
                parts=[
                          f'Spot market bought {buy_order.symbol}',
                          f'price: {round(buy_order.price, precision.price)}',
                      ] + self._get_oco_message_parts(message.targets, message.stop_loss, precision),
            )
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
        for oco_order, *_ in oco_orders:
            self._api.cancel_order(symbol, oco_order.order_id)
            total_quantity += oco_order.quantity

        sell_order = self._api.market_sell(symbol, total_quantity)
        precision = self._api.get_precision(message.symbol)
        self._logger.log_message('', [
            f'Spot market sold {symbol}',
            f'price: {round(sell_order.price, precision.price)}',
        ] + self._get_profit_message_parts(symbol, total_quantity, sell_order.price))

    def _process_limit_buy_order(self, api_order: Order) -> None:
        original_order = self._order_storage.get_order_by_symbol_and_order_id(api_order.symbol, api_order.order_id)

        if original_order is None:
            return
        elif api_order.status == Order.STATUS_CANCELED:
            self._order_storage.remove(original_order)
        elif api_order.status == Order.STATUS_FILLED:
            buy_message = original_order.buy_message
            assert buy_message is not None
            self._api.oco_sell(original_order.symbol, api_order.quantity, buy_message.targets,
                               buy_message.stop_loss)
            precision = self._api.get_precision(original_order.symbol)
            self._logger.log_message(
                content=Logger.join_contents(buy_message.content, buy_message.parent_content),
                parts=[
                          f'Spot limit bought {original_order.symbol}',
                          f'price: {round(original_order.price, precision.price)}',
                      ] + self._get_oco_message_parts(buy_message.targets, buy_message.stop_loss, precision),
            )
            self._order_storage.remove(original_order)

    def _process_oco_sell_order(self, sell_order: Order) -> None:
        if sell_order.status != Order.STATUS_FILLED:
            return

        typ = sell_order.type.lower().replace('_', ' ')
        precision = self._api.get_precision(sell_order.symbol)
        self._logger.log_message('', [
            f'Spot OCO {typ} sold {sell_order.symbol}',
            f'price: {round(sell_order.price, precision.price)}',
        ] + self._get_profit_message_parts(sell_order.symbol, sell_order.quantity, sell_order.price))

    def _get_profit_message_parts(self, symbol: str, quantity: Decimal, sell_price: Decimal) -> List[str]:
        buy_order = self._api.get_last_buy_order(symbol)

        if buy_order is None or buy_order.quantity < quantity:
            return ['unknown profit']

        diff = sell_price - buy_order.price
        precision = self._api.get_precision(symbol)

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
