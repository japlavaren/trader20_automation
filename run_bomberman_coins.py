import traceback
import os
import yaml
from argparse import ArgumentParser
from decimal import Decimal

from binance.client import Client as BinanceClient
from discord import Client as DiscordClient, Message as DiscordMessage
from mypy.applytype import Optional

from automation.binance_api import BinanceApi
from automation.bomberman_coins import BombermanCoins
from automation.config import config
from automation.logger import Logger
from automation.parser.message_parser import UnknownMessage


def get_config(path: Optional[str]):
    if path:
        with open(path) as h:
            cfg = yaml.safe_load(h)
            return cfg

    config_file = "config.yaml"
    with open(config_file) as h:
        cfg = yaml.safe_load(h)
        return cfg


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--config', default=None)
    args = parser.parse_args()
    config_path = getattr(args, 'config')
    config = get_config(config_path)

    trade_amount = config["app"]["trade-amount"]

    logger = Logger('log/bomberman_coins.log', config['email']['recipient'], config['email']['host'],
                    config['email']['user'], config['email']['password'])

    discord_client = DiscordClient()
    binance_client = BinanceClient(config['binance_api']['key'], config['binance_api']['secret'])
    binance_api = BinanceApi(binance_client)
    bomberman_coins = BombermanCoins(trade_amount, binance_api, logger, config)


    @discord_client.event
    async def on_message(message: DiscordMessage) -> None:
        try:
            if message.channel.id == config['discord']['channel']:
                parent_content = None

                if message.reference is not None and message.reference.resolved is not None:
                    parent_content = message.reference.resolved.content

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
