from decimal import Decimal
from typing import Dict, List, Optional, Union

from automation.api.api import Api
from automation.api.futures_api import FuturesApi
from automation.api.spot_api import SpotApi
from automation.functions import parse_decimal
from automation.logger import Logger
from automation.message.buy_message import BuyMessage
from automation.message.sell_message import SellMessage
from automation.message.unknown_message import UnknownMessage
from automation.order import Order
from automation.order_storage import OrderStorage
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

    def process_channel_message(self, content: str, parent_content: Optional[str]) -> None:
        message = MessageParser.parse(content, parent_content)

        if isinstance(message, BuyMessage):
            return self._process_channel_buy(message)
        elif isinstance(message, SellMessage):
            return self._process_channel_sell(message)

        raise UnknownMessage()

    def process_api_spot_message(self, msg: dict) -> None:
        if msg['e'] == 'executionReport':
            order_list_id = msg['g'] if msg['g'] != -1 else None
            order = Order(symbol=msg['s'], side=msg['S'], order_type=msg['o'], status=msg['X'], order_id=msg['i'],
                          order_list_id=order_list_id, quantity=parse_decimal(msg['l']), price=parse_decimal(msg['L']))
            self._process_api_order(order)

    def process_api_futures_message(self, message: dict) -> None:
        if message['data']['e'] == 'ORDER_TRADE_UPDATE':
            msg = message['data']['o']
            order = Order(symbol=msg['s'], side=msg['S'], order_type=msg['o'], original_type=msg['ot'], status=msg['X'],
                          order_id=msg['i'], order_list_id=None, quantity=parse_decimal(msg['l']),
                          price=parse_decimal(msg['L']), futures=True)
            self._process_api_order(order)

    def _process_channel_buy(self, message: BuyMessage) -> None:
        symbol = message.symbol
        futures = self._is_futures_symbol(symbol)
        amount = self._get_trade_amount(symbol, futures)

        if amount == Decimal(0):
            market_type = self._get_market_type(futures)
            self._logger.log(
                f'SKIPPING {market_type} {symbol}',
                body=Logger.join_contents(message.content, message.parent_content),
            )
            return

        buy_order = self._create_buy_order(message.buy_type, symbol, amount, message.buy_price, message.targets,
                                           message.stop_loss, futures)
        market_type = self._get_market_type(futures)
        api = self._get_api(futures)
        symbol_info = api.get_symbol_info(symbol)

        if buy_order.status == Order.STATUS_NEW:
            buy_order.buy_message = message
            self._order_storage.add_limit_order(buy_order)

            self._logger.log_message(symbol, Logger.join_contents(message.content, message.parent_content), [
                f'{market_type} limit buy order created {symbol}',
                f'price: {round(buy_order.price, symbol_info.price_precision)}',
            ])
        elif buy_order.status == Order.STATUS_FILLED:
            api.oco_sell(symbol, buy_order.quantity, message.targets, message.stop_loss)
            self._logger.log_message(symbol, Logger.join_contents(message.content, message.parent_content), [
                f'{market_type} market bought {symbol}',
                f'price: {round(buy_order.price, symbol_info.price_precision)}',
                'Sell order created',
                'TP: ' + ', '.join(f'{round(price, symbol_info.price_precision)}' for price in message.targets),
                f'SL: {round(message.stop_loss, symbol_info.price_precision)}',
            ])
        else:
            raise Exception(f'Unknown buy order status {buy_order.status}')

    def _create_buy_order(self, buy_type: str, symbol: str, amount: Decimal, buy_price: Optional[Decimal],
                          targets: List[Decimal], stop_loss: Decimal, futures: bool) -> Order:
        if futures:
            self._futures_api.leverage = self._get_futures_leverage(symbol, amount, buy_price, targets, stop_loss)

        api = self._get_api(futures)
        api.check_min_notional(symbol, buy_price, amount, targets, stop_loss, futures)

        if buy_type == BuyMessage.BUY_MARKET:
            return api.market_buy(symbol, amount)
        elif buy_type == BuyMessage.BUY_LIMIT:
            assert buy_price is not None
            return api.limit_buy(symbol, buy_price, amount)
        else:
            raise UnknownMessage()

    def _get_futures_leverage(self, symbol: str, amount: Decimal, buy_price: Optional[Decimal], targets: List[Decimal],
                              stop_loss: Decimal) -> int:
        if self._futures_leverage != self.LEVERAGE_SMART:
            assert isinstance(self._futures_leverage, int)

            return self._futures_leverage

        if buy_price is None:
            buy_price = self._futures_api.get_current_price(symbol)

        # calculate leverage based on stop loss
        leverage = min(int(buy_price / (buy_price - stop_loss)),
                       self._futures_max_leverage)
        leverage_divisor = self._get_leverage_divisor(symbol, buy_price, targets, stop_loss,
                                                      trade_amount=amount / leverage)

        return max(int(leverage / leverage_divisor), 1)

    def _get_leverage_divisor(self, symbol: str, buy_price: Decimal, targets: List[Decimal], stop_loss: Decimal,
                              trade_amount: Decimal) -> Decimal:
        target_amounts, stop_loss_amount = self._spot_api.get_buy_order_amounts(symbol, trade_amount, buy_price,
                                                                                targets, stop_loss, futures=True)
        min_notional = self._futures_api.get_symbol_info(symbol).min_notional

        # calculate leverage divisor when trade amount is smaller than min notional
        return max(
            min_notional / stop_loss_amount,
            *[min_notional / target_amount for target_amount in target_amounts],
            Decimal(1),
        )

    def _process_channel_sell(self, message: SellMessage) -> None:
        assert message.sell_type == SellMessage.SELL_MARKET
        symbol = message.symbol
        futures = self._is_futures_symbol(symbol)
        quantity = self._get_sell_quantity(symbol, futures)
        api = self._get_api(futures)
        sell_order = api.market_sell(symbol, quantity)
        pnl = api.get_sell_order_pnl(sell_order)

        market_type = self._get_market_type(futures)
        symbol_info = api.get_symbol_info(symbol)
        currency = self._get_currency(symbol)
        self._logger.log_message(symbol, '', [
            f'{market_type} market sold {symbol}',
            f'price: {round(sell_order.price, symbol_info.price_precision)}',
            'PNL: ' + f'{round(pnl, symbol_info.price_precision)} {currency}' if pnl else 'unknown',
        ])

    def _get_sell_quantity(self, symbol: str, futures: bool) -> Decimal:
        if futures:
            total_quantity = self._futures_api.get_open_position_quantity(symbol)
            assert total_quantity != Decimal(0), f'Empty futures position {symbol}'
        else:
            oco_orders = self._spot_api.get_oco_sell_orders(symbol)
            assert len(oco_orders) != 0, f'Empty spot OCO sell orders'
            total_quantity = Decimal(0)

            for limit_maker, _ in oco_orders:
                self._spot_api.cancel_order(limit_maker.symbol, limit_maker.order_id)
                total_quantity += limit_maker.quantity

        return total_quantity

    def _process_api_order(self, order: Order) -> None:
        if order.side == Order.SIDE_BUY and order.type == Order.TYPE_LIMIT:
            self._process_api_limit_buy_order(order)
        elif order.side == Order.SIDE_SELL and self._is_api_filled_oco_sell_order(order):
            self._process_api_filled_oco_sell_order(order)

    def _process_api_limit_buy_order(self, api_order: Order) -> None:
        buy_order = self._order_storage.get_order_by_symbol_and_order_id(api_order.symbol, api_order.order_id)

        if buy_order is None:
            return

        if api_order.status == Order.STATUS_CANCELED:
            self._order_storage.remove(buy_order)
        elif api_order.status == Order.STATUS_FILLED:
            buy_message = buy_order.buy_message
            assert buy_message is not None

            api = self._get_api(buy_order.futures)
            api.oco_sell(buy_order.symbol, api_order.quantity, buy_message.targets,
                         buy_message.stop_loss)
            self._order_storage.remove(buy_order)

            market_type = self.MARKET_TYPE_FUTURES if api_order.futures else self.MARKET_TYPE_SPOT
            symbol_info = self._spot_api.get_symbol_info(buy_order.symbol)
            log_content = Logger.join_contents(buy_message.content, buy_message.parent_content)
            self._logger.log_message(buy_message.symbol, log_content, [
                f'{market_type} limit bought {buy_order.symbol}',
                f'price: {round(buy_order.price, symbol_info.price_precision)}',
                'Sell order created',
                'TP: ' + ', '.join(f'{round(price, symbol_info.price_precision)}' for price in buy_message.targets),
                f'SL: {round(buy_message.stop_loss, symbol_info.price_precision)}',
            ])

    def _process_api_filled_oco_sell_order(self, sell_order: Order) -> None:
        api = self._get_api(sell_order.futures)
        pnl = api.get_sell_order_pnl(sell_order)
        market_type = self._get_market_type(sell_order.futures)
        typ = (sell_order.original_type or sell_order.type).replace('_', ' ').lower()
        symbol_info = api.get_symbol_info(sell_order.symbol)
        currency = self._get_currency(sell_order.symbol)
        self._logger.log_message(sell_order.symbol, '', [
            f'{market_type} {typ} sold {sell_order.symbol}',
            f'price: {round(sell_order.price, symbol_info.price_precision)}',
            'PNL: ' + f'{round(pnl, symbol_info.price_precision)} {currency}' if pnl else 'unknown',
        ])

    @staticmethod
    def _is_api_filled_oco_sell_order(order: Order) -> bool:
        if order.status != Order.STATUS_FILLED:
            return False

        if order.futures:
            return order.type == Order.TYPE_LIMIT or (order.type == Order.TYPE_MARKET
                                                      and order.original_type == Order.TYPE_STOP_MARKET)
        else:
            return order.type in (Order.TYPE_LIMIT_MAKER, Order.TYPE_STOP_LOSS_LIMIT)

    def _get_trade_amount(self, symbol: str, futures: bool) -> Decimal:
        currency = self._get_currency(symbol)
        market_type = self._get_market_type(futures)
        amounts = self._trade_amounts[market_type]

        return amounts.get(currency, Decimal(0))

    def _is_futures_symbol(self, symbol: str) -> bool:
        return (self._market_type == self.MARKET_TYPE_FUTURES and self._futures_api.is_futures_symbol(symbol)
                and self._get_trade_amount(symbol, futures=True) != Decimal(0))

    def _get_api(self, futures: bool) -> Api:
        return self._futures_api if futures else self._spot_api

    @classmethod
    def _get_market_type(cls, futures: bool) -> str:
        return cls.MARKET_TYPE_FUTURES if futures else cls.MARKET_TYPE_SPOT

    @staticmethod
    def _get_currency(symbol: str) -> str:
        for currency in ('USDT', 'BTC'):
            if currency in symbol:
                return currency
        else:
            raise Exception(f'Unknown currency for {symbol}')
