import traceback
from time import sleep

from binance.client import Client as BinanceClient
from binance.websockets import BinanceSocketManager
from pika.adapters.blocking_connection import BlockingConnection
from pika.connection import URLParameters

from automation.api.futures_api import FuturesApi
from automation.api.spot_api import SpotApi
from automation.bomberman_coins import BombermanCoins
from automation.functions import load_config
from automation.logger import Logger
from automation.order_storage import OrderStorage


class BombermanCoinsRunner:
    def __init__(self) -> None:
        self._config: dict = load_config()
        self._logger: Logger = self._create_logger()
        self._binance_client: BinanceClient = self._create_binance_client()
        self._bomberman_coins: BombermanCoins = self._create_bomberman_coins()
        self._rabbit: BlockingConnection = self._create_rabbit()
        self._binance_socket: BinanceSocketManager = self._create_binance_socket()

    def _create_logger(self) -> Logger:
        return Logger('log/bomberman_coins.log',
                      self._config['email']['recipient'],
                      self._config['email']['host'],
                      self._config['email']['user'],
                      self._config['email']['password'])

    def _create_binance_client(self) -> BinanceClient:
        return BinanceClient(self._config['binance_api']['key'],
                             self._config['binance_api']['secret'])

    def _create_bomberman_coins(self) -> BombermanCoins:
        spot_api = SpotApi(self._binance_client)
        futures_api = FuturesApi(self._config['app']['futures']['margin_type'], self._binance_client)
        order_storage = OrderStorage('data/orders.pickle')

        return BombermanCoins(self._config['app']['market_type'],
                              self._config['app']['spot']['trade_amount'],
                              self._config['app']['futures']['trade_amount'],
                              self._config['app']['futures']['leverage'],
                              self._config['app']['futures']['max_leverage'],
                              spot_api, futures_api, order_storage, self._logger)

    def _create_rabbit(self) -> BlockingConnection:
        exchange = self._config['rabbit']['exchange']
        queue = 't20a_' + self._config['email']['recipient']

        connection = BlockingConnection(URLParameters(self._config['rabbit']['url']))
        channel = connection.channel()
        channel.exchange_declare(exchange, exchange_type='fanout', passive=True)
        channel.queue_declare(queue, exclusive=True, auto_delete=True)
        channel.queue_bind(queue, exchange)

        channel.basic_consume(queue, self._rabbit_callback, auto_ack=True)
        channel.start_consuming()

        return connection

    def _rabbit_callback(self, ch, method, properties, body: bytes):
        try:
            self._bomberman_coins.process_channel_message(body)
        except Exception:
            self._logger.log('ERROR', traceback.format_exc())

    def _create_binance_socket(self) -> BinanceSocketManager:
        binance_socket = BinanceSocketManager(self._binance_client)
        binance_socket.start_user_socket(self._binance_spot_callback)

        if self._config['app']['market_type'] == BombermanCoins.MARKET_TYPE_FUTURES:
            # there is no method for listening future changes in binance socket manager
            binance_socket._start_futures_socket(
                self._binance_client._request_futures_api('post', 'listenKey')['listenKey'],
                self._binance_futures_callback,
            )

        binance_socket.start()

        return binance_socket

    def _binance_spot_callback(self, msg: dict) -> None:
        try:
            self._bomberman_coins.process_api_spot_message(msg)
        except Exception:
            self._logger.log('ERROR', traceback.format_exc())

    def _binance_futures_callback(self, msg: dict) -> None:
        try:
            self._bomberman_coins.process_api_futures_message(msg)
        except Exception:
            self._logger.log('ERROR', traceback.format_exc())

    def run(self) -> None:
        while True:
            try:
                sleep(60)
            finally:
                self._rabbit.close()
                self._binance_socket.close()


if __name__ == '__main__':
    runner = BombermanCoinsRunner()
    runner.run()
