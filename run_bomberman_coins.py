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
from automation.parser.message_parser import UnknownMessage
from automation.trade_storage import TradeStorage


class CheckOrders(Thread):
    _INTERVAL = 60

    def __init__(self, bomberman_coins: BombermanCoins, logger: Logger, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._bomberman_coins: BombermanCoins = bomberman_coins
        self._logger: Logger = logger
        self._stop_event: Event = Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        start = time()

        while not self._stop_event.isSet():
            try:
                if (time() - start) >= self._INTERVAL:
                    self._bomberman_coins.process_changes()
                    start = time()

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
    trades_storage = TradeStorage('data/trades.p')
    bomberman_coins = BombermanCoins(config['app']['spot']['trade_amount'],
                                     binance_api, logger, trades_storage)
    check_orders = CheckOrders(bomberman_coins, logger)
    check_orders.run()


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
