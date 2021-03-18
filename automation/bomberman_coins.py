from decimal import Decimal
from time import sleep
from typing import Any, Dict, List, Optional

from automation.binance_api import BinanceApi
from automation.functions import parse_decimal
from automation.logger import Logger
from automation.order_storage import OrderStorage
from automation.parser.message_parser import BuyMessage, MessageParser, UnknownMessage
from automation.parser.sell_message_parser import SellMessage
from automation.order import Order


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
        api_order = Order(symbol=msg['s'], side=msg['S'], order_type=msg['o'], status=msg['X'], order_id=msg['i'],
                          order_list_id=msg['g'] if msg['g'] != -1 else None,
                          quantity=parse_decimal(msg['l']), price=parse_decimal(msg['L']))

        if api_order.side == Order.SIDE_BUY:
            if api_order.type == Order.TYPE_LIMIT:
                self._process_limit_buy_order(api_order)
        elif api_order.side == Order.SIDE_SELL:
            if api_order.type in (Order.TYPE_LIMIT_MAKER, Order.TYPE_STOP_LOSS_LIMIT):
                self._process_oco_sell_order(api_order)

    def _spot_buy(self, message: BuyMessage) -> None:
        amount = self._spot_trade_amounts.get(message.currency, Decimal(0))

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
            self._logger.log_message(
                content=Logger.join_contents(message.content, message.parent_content),
                parts=[
                    f'Spot limit buy order created {buy_order.symbol}',
                    f'price: {buy_order.price}',
                ],
            )
        elif buy_order.status == Order.STATUS_FILLED:
            sleep(1)  # creating sell order directly after market buy caused problems
            self._api.oco_sell(message.symbol, buy_order.quantity, message.targets, message.stop_loss)
            self._logger.log_message(
                content=Logger.join_contents(message.content, message.parent_content),
                parts=[
                          f'Spot market bought {buy_order.symbol}',
                          f'price: {buy_order.price}',
                      ] + self._get_oco_message_parts(message.targets, message.stop_loss),
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
        self._logger.log_message('', [
            f'Spot market sold {symbol}',
            f'price: {sell_order.price}',
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
            self._logger.log_message(
                content=Logger.join_contents(buy_message.content, buy_message.parent_content),
                parts=[
                          f'Spot limit bought {original_order.symbol}',
                          f'price: {original_order.price}',
                      ] + self._get_oco_message_parts(buy_message.targets, buy_message.stop_loss),
            )
            self._order_storage.remove(original_order)

    def _process_oco_sell_order(self, sell_order: Order) -> None:
        if sell_order.status != Order.STATUS_FILLED:
            return

        typ = sell_order.type.lower().replace('_', ' ')
        self._logger.log_message('', [
            f'Spot OCO {typ} sold {sell_order.symbol}',
            f'price: {sell_order.price}',
        ] + self._get_profit_message_parts(sell_order.symbol, sell_order.quantity, sell_order.price))

    def _get_profit_message_parts(self, symbol: str, quantity: Decimal, sell_price: Decimal) -> List[str]:
        buy_order = self._api.get_last_buy_order(symbol)

        if buy_order is None or buy_order.quantity < quantity:
            return ['unknown profit']

        diff = sell_price - buy_order.price

        return [
            f'profit: {diff / buy_order.price * 100:.2f}%',
            f'gain: {diff * quantity}',
        ]

    @staticmethod
    def _get_oco_message_parts(targets: List[Decimal], stop_loss: Decimal) -> List[str]:
        return [
            'OCO sell order created',
            'TP: ' + ', '.join(str(target) for target in targets),
            f'SL: {stop_loss}',
        ]
