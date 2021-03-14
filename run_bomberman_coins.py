import traceback
from argparse import ArgumentParser
from decimal import Decimal

from binance.client import Client as BinanceClient
from discord import Client as DiscordClient, Message as DiscordMessage

from automation.binance_api import BinanceApi
from automation.bomberman_coins import BombermanCoins
from automation.config import config
from automation.logger import Logger
from automation.parser.message_parser import UnknownMessage

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('trade-amount', type=Decimal)
    args = parser.parse_args()
    trade_amount = getattr(args, 'trade-amount')

    logger = Logger('log/bomberman_coins.log', config['email']['recipient'], config['email']['host'],
                    config['email']['user'], config['email']['password'])

    discord_client = DiscordClient()
    binance_client = BinanceClient(config['binance_api']['key'], config['binance_api']['secret'])
    binance_api = BinanceApi(binance_client)
    bomberman_coins = BombermanCoins(trade_amount, binance_api, logger)


    @discord_client.event
    async def on_message(message: DiscordMessage) -> None:
        try:
            if message.channel.id == config['discord']['channel']:
                parent_content = message.reference.resolved.content if message.reference is not None else None
                bomberman_coins.process(message.content, parent_content)
        except UnknownMessage:
            logger.log('Bomberman coins UNKNOWN MESSAGE', message.content)
        except:
            logger.log('Bomberman coins ERROR', message.content + '\n\n' + traceback.format_exc())


    try:
        discord_client.run(config['discord']['token'], bot=False)
    except KeyboardInterrupt:
        raise
    except:
        logger.log('Bomberman coins terminated', traceback.format_exc())
        exit(1)
