import traceback
from argparse import ArgumentParser
from threading import Event, Thread
from time import sleep, time

from binance.client import Client as BinanceClient
from discord import Client as DiscordClient, Message as DiscordMessage

from automation.binance_api import BinanceApi
from automation.bomberman_coins import BombermanCoins
from automation.functions import load_config
from automation.logger import Logger
from automation.order_storage import OrderStorage
from automation.parser.message_parser import UnknownMessage
from automation.symbol_watcher import SymbolWatcher


class CheckOrders(Thread):
    _INTERVAL = 60

    def __init__(self, bomberman_coins: BombermanCoins, logger: Logger, *args, **kwargs) -> None:
        super().__init__(target=self._check_orders, *args, **kwargs)
        self._bomberman_coins: BombermanCoins = bomberman_coins
        self._logger: Logger = logger
        self._stop_event: Event = Event()

    def stop(self) -> None:
        self._stop_event.set()

    def _check_orders(self) -> None:
        last_time = time()

        while not self._stop_event.is_set():
            try:
                if (time() - last_time) >= self._INTERVAL:
                    self._bomberman_coins.process_changed_orders(last_micro_time=int(last_time * 1000))
                    last_time = time()
                else:
                    sleep(1)
            except:
                logger.log('ERROR', traceback.format_exc())


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--config-file')
    args = parser.parse_args()
    config = load_config(args.config_file)

    logger = Logger('log/bomberman_coins.log',
                    config['email']['recipient'],
                    config['email']['host'],
                    config['email']['user'],
                    config['email']['password'])

    discord_client = DiscordClient()
    binance_client = BinanceClient(config['binance_api']['key'],
                                   config['binance_api']['secret'])
    binance_api = BinanceApi(binance_client)
    symbol_watcher = SymbolWatcher('data/symbols.json')
    order_storage = OrderStorage('data/orders.pickle')
    bomberman_coins = BombermanCoins(config['app']['spot']['trade_amount'],
                                     binance_api, symbol_watcher, order_storage, logger)
    check_orders = CheckOrders(bomberman_coins, logger)
    check_orders.start()


    @discord_client.event
    async def on_message(message: DiscordMessage) -> None:
        try:
            if message.channel.id == config['discord']['channel']:
                parent_content = None

                if message.reference is not None and message.reference.resolved is not None:
                    parent_content = message.reference.resolved.content

                bomberman_coins.process(message.content, parent_content)
        except UnknownMessage:
            logger.log('UNKNOWN MESSAGE', message.content)
        except:
            logger.log('ERROR', message.content + '\n\n' + traceback.format_exc())


    try:
        discord_client.run(config['discord']['token'], bot=False)
    except Exception as e:
        check_orders.stop()

        if not isinstance(e, KeyboardInterrupt):
            logger.log('TERMINATED', traceback.format_exc())
            exit(1)
