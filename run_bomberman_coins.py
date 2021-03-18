import traceback
from argparse import ArgumentParser
from typing import Any, Dict

from binance.client import Client as BinanceClient
from binance.websockets import BinanceSocketManager
from discord import Client as DiscordClient, Message as DiscordMessage
from twisted.internet import reactor

from automation.binance_api import BinanceApi
from automation.bomberman_coins import BombermanCoins
from automation.functions import load_config
from automation.logger import Logger
from automation.order_storage import OrderStorage
from automation.parser.message_parser import UnknownMessage

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
    binance_socket = BinanceSocketManager(binance_client)
    binance_api = BinanceApi(binance_client)
    order_storage = OrderStorage('data/orders.pickle')
    bomberman_coins = BombermanCoins(config['app']['spot']['trade_amount'],
                                     binance_api, order_storage, logger)


    @discord_client.event
    async def on_message(message: DiscordMessage) -> None:
        content = ''
        parent_content = None

        try:
            if message.channel.id == config['discord']['channel']:
                content = message.content

                if message.reference is not None and message.reference.resolved is not None:
                    parent_content = message.reference.resolved.content

                bomberman_coins.process(content, parent_content)
        except UnknownMessage:
            logger.log('UNKNOWN MESSAGE', Logger.join_contents(content, parent_content))
        except:
            logger.log('ERROR', Logger.join_contents(content, parent_content) + '\n\n' + traceback.format_exc())


    def process_user_message(msg: Dict[str, Any]) -> None:
        try:
            if msg['e'] == 'executionReport':
                bomberman_coins.process_order_message(msg)
        except:
            logger.log('ERROR', traceback.format_exc())


    try:
        binance_socket.start_user_socket(process_user_message)
        binance_socket.start()

        discord_client.run(config['discord']['token'], bot=False)
    except KeyboardInterrupt:
        exit(0)
    except:
        logger.log('TERMINATED', traceback.format_exc())
        exit(1)
    finally:
        binance_socket.close()
        reactor.stop()  # type: ignore
