from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from automation.api.api import Api
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
                 futures_max_leverage: int, spot_api: SpotApi, futures_api: FuturesApi, order_storage: OrderStorage,
                 logger: Logger) -> None:
        assert market_type in (self.MARKET_TYPE_SPOT, self.MARKET_TYPE_FUTURES)
        assert isinstance(futures_leverage, int) or futures_leverage == self.LEVERAGE_SMART
        self._market_type: str = market_type
        self._trade_amounts: Dict[str, Dict[str, Decimal]] = {
            self.MARKET_TYPE_SPOT: spot_trade_amounts,
            self.MARKET_TYPE_FUTURES: futures_trade_amounts,
        }
        self._futures_leverage: Union[str, int] = futures_leverage
        self._futures_max_leverage: int = futures_max_leverage
        self._spot_api: SpotApi = spot_api
        self._futures_api: FuturesApi = futures_api
        self._order_storage: OrderStorage = order_storage
        self._logger: Logger = logger

    def process(self, content: str, parent_content: Optional[str]) -> None:
        message = MessageParser.parse(content, parent_content)
        market_type = self._get_market_type(message.symbol)

        if isinstance(message, BuyMessage):
            return self._buy(market_type, message)
        elif isinstance(message, SellMessage):
            return self._sell(market_type, message)

        raise UnknownMessage()

    def process_spot_message(self, msg: Dict[str, Any]) -> None:
        if msg['e'] == 'executionReport':
            order_list_id = msg['g'] if msg['g'] != -1 else None
            order = Order(symbol=msg['s'], side=msg['S'], order_type=msg['o'], status=msg['X'], order_id=msg['i'],
                          order_list_id=order_list_id, quantity=parse_decimal(msg['l']), price=parse_decimal(msg['L']))
            self._process_message_order(order)

    def process_futures_message(self, message: Dict[str, Any]) -> None:
        if message['data']['e'] == 'ORDER_TRADE_UPDATE':
            msg = message['data']['o']
            order = Order(symbol=msg['s'], side=msg['S'], order_type=msg['o'], status=msg['X'], order_id=msg['i'],
                          order_list_id=None, quantity=parse_decimal(msg['l']), price=parse_decimal(msg['L']),
                          futures=True, original_type=msg['ot'])
            self._process_message_order(order)

    def _get_market_type(self, symbol: str) -> str:
        amount = self._get_trade_amount(self.MARKET_TYPE_FUTURES, symbol)
        currency = self._get_currency(symbol)
        # fallback to spot when futures not available for symbol or insufficient balance
        futures = (self._market_type == self.MARKET_TYPE_FUTURES and self._futures_api.is_futures(symbol)
                   and amount != Decimal(0) and amount <= self._futures_api.get_available_balance(currency))

        return self.MARKET_TYPE_FUTURES if futures else self.MARKET_TYPE_SPOT

    def _get_trade_amount(self, market_type: str, symbol: str) -> Decimal:
        currency = self._get_currency(symbol)
        amounts = self._trade_amounts[market_type]

        return amounts.get(currency, Decimal(0))

    def _buy(self, market_type: str, message: BuyMessage) -> None:
        amount = trade_amount = self._get_trade_amount(market_type, message.symbol)

        if amount == Decimal(0):
            self._logger.log(
                f'SKIPPING {market_type} {message.symbol}',
                body=Logger.join_contents(message.content, message.parent_content),
            )
            return

        if market_type == self.MARKET_TYPE_FUTURES:
            self._futures_api.leverage = self._get_futures_leverage(message, amount)

        api = self._get_api(market_type)
        api.check_min_notional(message.symbol, message.buy_price, trade_amount, len(message.targets), message.stop_loss)
        symbol_info = api.get_symbol_info(message.symbol)

        if message.buy_type == BuyMessage.BUY_MARKET:
            buy_order = api.market_buy(message.symbol, trade_amount)
        elif message.buy_type == BuyMessage.BUY_LIMIT:
            assert message.buy_price is not None
            buy_order = api.limit_buy(message.symbol, message.buy_price, trade_amount)
        else:
            raise UnknownMessage()

        if buy_order.status == Order.STATUS_NEW:
            buy_order.buy_message = message
            self._order_storage.add_limit_order(buy_order)

            self._logger.log_message(
                symbol=message.symbol,
                content=Logger.join_contents(message.content, message.parent_content),
                parts=[
                    f'{market_type} limit buy order created {message.symbol}',
                    f'price: {round(buy_order.price, symbol_info.price_precision)}',
                ],
            )
        elif buy_order.status == Order.STATUS_FILLED:
            api.oco_sell(message.symbol, buy_order.quantity, message.targets, message.stop_loss)
            self._logger.log_message(
                symbol=message.symbol,
                content=Logger.join_contents(message.content, message.parent_content),
                parts=[
                          f'{market_type} market bought {message.symbol}',
                          f'price: {round(buy_order.price, symbol_info.price_precision)}',
                      ] + self._get_oco_message_parts(message.targets, message.stop_loss, symbol_info.price_precision),
            )
        else:
            raise Exception(f'Unknown order status {buy_order.status}')

    def _get_futures_leverage(self, message: BuyMessage, amount: Decimal) -> int:
        if self._futures_leverage != self.LEVERAGE_SMART:
            assert isinstance(self._futures_leverage, int)

            return self._futures_leverage

        if message.buy_type == BuyMessage.BUY_LIMIT:
            assert message.buy_price is not None
            buy_price = message.buy_price
        else:
            buy_price = self._futures_api.get_current_price(message.symbol)

        leverage = min(int(buy_price / (buy_price - message.stop_loss)), self._futures_max_leverage)
        target_quantity = amount / leverage / buy_price / len(message.targets)
        stop_loss_amount = target_quantity * message.stop_loss
        min_notional = self._futures_api.get_symbol_info(message.symbol).min_notional

        # decrease leverage when stop loss amount is lower than min notional
        if stop_loss_amount < min_notional:
            multiplier = min_notional / stop_loss_amount
            leverage = max(int(leverage / multiplier), 1)

        return leverage

    def _sell(self, market_type: str, message: SellMessage) -> None:
        if message.sell_type != SellMessage.SELL_MARKET:
            raise UnknownMessage()

        if market_type == self.MARKET_TYPE_SPOT:
            oco_orders = self._spot_api.get_oco_sell_orders(message.symbol)
            assert len(oco_orders) != 0, f'None {market_type} OCO sell orders found'
            total_quantity = Decimal(0)

            for limit_maker, _ in oco_orders:
                self._spot_api.cancel_order(limit_maker.symbol, limit_maker.order_id)
                total_quantity += limit_maker.quantity
        elif market_type == self.MARKET_TYPE_FUTURES:
            total_quantity = self._futures_api.get_position_quantity(message.symbol)
            assert total_quantity != Decimal(0), 'Empty position'
        else:
            raise Exception(f'Unknown market type {market_type}')

        api = self._get_api(market_type)
        sell_order = api.market_sell(message.symbol, total_quantity)
        symbol_info = api.get_symbol_info(message.symbol)
        self._logger.log_message(symbol=message.symbol, content='', parts=[
            f'{market_type} market sold {message.symbol}',
            f'price: {round(sell_order.price, symbol_info.price_precision)}',
        ] + self._get_profit_message_parts(message.symbol, total_quantity, sell_order.price, api))

    def _process_message_order(self, order: Order) -> None:
        if order.side == Order.SIDE_BUY:
            if order.type == Order.TYPE_LIMIT:
                self._process_limit_buy_order(order)
        elif order.side == Order.SIDE_SELL:
            if self._is_oco_sell(order):
                self._process_oco_sell_order(order)

    @staticmethod
    def _is_oco_sell(order: Order) -> bool:
        if order.futures:
            return order.type == Order.TYPE_LIMIT or (order.type == Order.TYPE_MARKET
                                                      and order.original_type == Order.TYPE_STOP_MARKET)
        else:
            return order.type in (Order.TYPE_LIMIT_MAKER, Order.TYPE_STOP_LOSS_LIMIT)

    def _process_limit_buy_order(self, api_order: Order) -> None:
        original_order = self._order_storage.get_order_by_symbol_and_order_id(api_order.symbol, api_order.order_id)

        if original_order is None:
            return

        if api_order.status == Order.STATUS_CANCELED:
            self._order_storage.remove(original_order)
        elif api_order.status == Order.STATUS_FILLED:
            buy_message = original_order.buy_message
            assert buy_message is not None
            market_type = self.MARKET_TYPE_FUTURES if api_order.futures else self.MARKET_TYPE_SPOT
            self._get_api(market_type).oco_sell(original_order.symbol, api_order.quantity, buy_message.targets,
                                                buy_message.stop_loss)
            symbol_info = self._spot_api.get_symbol_info(original_order.symbol)
            self._logger.log_message(
                symbol=original_order.symbol,
                content=Logger.join_contents(buy_message.content, buy_message.parent_content),
                parts=[
                          f'{market_type} limit bought {original_order.symbol}',
                          f'price: {round(original_order.price, symbol_info.price_precision)}',
                      ] + self._get_oco_message_parts(buy_message.targets, buy_message.stop_loss,
                                                      symbol_info.price_precision),
            )
            self._order_storage.remove(original_order)

    def _process_oco_sell_order(self, sell_order: Order) -> None:
        if sell_order.status != Order.STATUS_FILLED:
            return

        market_type = self.MARKET_TYPE_FUTURES if sell_order.futures else self.MARKET_TYPE_SPOT
        typ = (sell_order.original_type or sell_order.type).replace('_', ' ').lower()
        api = self._get_api(market_type)
        symbol_info = api.get_symbol_info(sell_order.symbol)
        self._logger.log_message(symbol=sell_order.symbol, content='', parts=[
            f'{market_type} {typ} sold {sell_order.symbol}',
            f'price: {round(sell_order.price, symbol_info.price_precision)}',
        ] + self._get_profit_message_parts(sell_order.symbol, sell_order.quantity, sell_order.price, api))

    def _get_profit_message_parts(self, symbol: str, quantity: Decimal, sell_price: Decimal, api: Api) -> List[str]:
        buy_order = api.get_last_buy_order(symbol)

        if buy_order is None or buy_order.quantity < quantity:
            return ['unknown profit']

        diff = sell_price - buy_order.price
        symbol_info = api.get_symbol_info(symbol)

        return [
            f'profit: {diff / buy_order.price * 100:.2f} %',
            f'gain: {round(diff * quantity, symbol_info.price_precision)} {self._get_currency(symbol)}',
        ]

    def _get_api(self, market_type: str) -> Api:
        return {
            self.MARKET_TYPE_FUTURES: self._futures_api,
            self.MARKET_TYPE_SPOT: self._spot_api,
        }[market_type]

    @staticmethod
    def _get_oco_message_parts(targets: List[Decimal], stop_loss: Decimal, price_precision: int) -> List[str]:
        return [
            'OCO sell order created',
            'TP: ' + ', '.join(f'{round(price, price_precision)}' for price in targets),
            f'SL: {round(stop_loss, price_precision)}',
        ]

    @staticmethod
    def _get_currency(symbol: str) -> str:
        for currency in ('USDT', 'BTC'):
            if currency in symbol:
                return currency
        else:
            raise Exception(f'Unknown currency for {symbol}')
