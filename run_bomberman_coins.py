import traceback
from argparse import ArgumentParser
from typing import Any, Dict

from binance.client import Client as BinanceClient
from binance.websockets import BinanceSocketManager
from discord import Client as DiscordClient, Message as DiscordMessage
from twisted.internet import reactor
from twisted.internet.error import ReactorNotRunning

from automation.api.futures_api import FuturesApi
from automation.api.spot_api import SpotApi
from automation.bomberman_coins import BombermanCoins
from automation.functions import load_config
from automation.logger import Logger
from automation.order_storage import OrderStorage
from automation.parser.message_parser import UnknownMessage

OFFICIAL_DISCORD_CHANNEL = 759070661888704613

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--config-file')
    args = parser.parse_args()
    config = load_config(args.config_file)

    discord_client = DiscordClient()
    binance_client = BinanceClient(config['binance_api']['key'],
                                   config['binance_api']['secret'])
    binance_socket = BinanceSocketManager(binance_client)
    spot_api = SpotApi(binance_client)
    futures_api = FuturesApi(config['app']['futures']['margin_type'], binance_client)
    order_storage = OrderStorage('data/orders.pickle')
    logger = Logger('log/bomberman_coins.log',
                    config['email']['recipient'],
                    config['email']['host'],
                    config['email']['user'],
                    config['email']['password'])
    bomberman_coins = BombermanCoins(config['app']['market_type'],
                                     config['app']['spot']['trade_amount'],
                                     config['app']['futures']['trade_amount'],
                                     config['app']['futures']['leverage'],
                                     config['app']['futures']['max_leverage'],
                                     spot_api, futures_api, order_storage, logger)
    discord_channel = config['discord']['channel']
    test_user = config['discord'].get('test_user')


    @discord_client.event
    async def on_message(message: DiscordMessage) -> None:
        content, parent_content = '', None

        try:
            if discord_channel != OFFICIAL_DISCORD_CHANNEL:
                if test_user is not None and str(message.author) != test_user:
                    return

            if message.channel.id == discord_channel:
                content = message.content

                if message.reference is not None and message.reference.resolved is not None:
                    parent_content = message.reference.resolved.content

                bomberman_coins.process_channel_message(content, parent_content)
        except UnknownMessage:
            logger.log('UNKNOWN MESSAGE', Logger.join_contents(content, parent_content))
        except:
            logger.log('ERROR', Logger.join_contents(content, parent_content) + '\n\n' + traceback.format_exc())


    def process_api_spot_message(msg: Dict[str, Any]) -> None:
        try:
            bomberman_coins.process_api_spot_message(msg)
        except:
            logger.log('ERROR', traceback.format_exc())


    def process_api_futures_message(msg: Dict[str, Any]) -> None:
        try:
            bomberman_coins.process_api_futures_message(msg)
        except:
            logger.log('ERROR', traceback.format_exc())


    try:
        binance_socket.start_user_socket(process_api_spot_message)

        if config['app']['market_type'] == BombermanCoins.MARKET_TYPE_FUTURES:
            # there is no method for listening future changes in binance socket manager
            binance_socket._start_futures_socket(
                binance_client._request_futures_api('post', 'listenKey')['listenKey'],
                process_api_futures_message,
            )

        binance_socket.start()
        discord_client.run(config['discord']['token'], bot=False)
    except KeyboardInterrupt:
        exit(0)
    except:
        logger.log('TERMINATED', traceback.format_exc())
        exit(1)
    finally:
        binance_socket.close()

        try:
            reactor.stop()  # type: ignore
        except ReactorNotRunning:
            pass
