import math
import os
import re
from argparse import ArgumentParser
from collections import namedtuple
from decimal import Decimal
from typing import Tuple

from binance.client import Client as BinanceClient
from discord import Client as DiscordClient, Message
from dotenv import load_dotenv

GUILD = 'Trader2.0'
CHANNEL = 'mince-se-zápalnou-šňůrou'
STOP_PRICE_CORRECTION = 1 + (0.5 / 100)
Trade = namedtuple('Trade', 'symbol, targets, stop_loss')


def parse_message(msg: str) -> Trade:
    msg = msg.replace(' : ', ': ')

    assert re.search(r'vstup: market', msg, re.IGNORECASE) is not None
    symbol = re.search(r'\d{2}\.\d{2}\.\d{2} ([A-Z]+/[A-Z]+)', msg).group(1).replace('/', '').lower()
    stop_loss = re.search(r'stoploss: (\d+\.\d+)', msg, re.IGNORECASE).group(1)
    targets = []

    for n in range(1, 3 + 1):
        try:
            price = re.search(fr'{n}\. ?(:?target|take profit): (\d+\.\d+)', msg, re.IGNORECASE).group(1)
            targets.append(price)
        except AttributeError:
            break

    assert len(targets) != 0

    return Trade(symbol, targets, stop_loss)


def get_precision(client: BinanceClient, symbol: str) -> Tuple[int, int]:
    info = client.get_symbol_info(symbol)
    quantity_precision, price_precision = None, None

    def parse(key: str) -> int:
        return int(round(-math.log(Decimal(f[key]), 10), 0))

    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            quantity_precision = parse('stepSize')
        elif f['filterType'] == 'PRICE_FILTER':
            price_precision = parse('tickSize')

    assert quantity_precision is not None
    assert price_precision is not None

    return quantity_precision, price_precision


def create_trade(client: BinanceClient, trade: Trade) -> None:
    market = client.order_market_buy(symbol=trade.symbol, quoteOrderQty=trade_amount)
    quantity_precision, price_precision = get_precision(client, trade.symbol)
    total_quantity = Decimal(market['executedQty'])
    quantity = round(total_quantity / len(trade.targets), quantity_precision)
    quantities = [quantity for _ in trade.targets]
    quantities[-1] = round(total_quantity - sum(quantities[:-1]), quantity_precision)
    stop_price = round(trade.stop_loss / STOP_PRICE_CORRECTION, price_precision)

    for target, total_quantity in zip(trade.targets, quantities):
        client.order_oco_sell(symbol=trade.symbol, quantity=total_quantity, price=target, stopPrice=stop_price,
                              stopLimitPrice=trade.stop_loss, stopLimitTimeInForce='FOK')


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('trade-amount', type=Decimal)
    args = parser.parse_args()
    trade_amount = getattr(args, 'trade-amount')

    load_dotenv('.env')
    api_key = os.getenv('API_KEY')
    api_secret = os.getenv('API_SECRET')
    discord_token = os.getenv('DISCORD_TOKEN')

    dc = DiscordClient()
    bc = BinanceClient(api_key, api_secret)


    @dc.event
    async def on_message(message: Message):
        if message.guild == GUILD and message.channel == CHANNEL:
            try:
                trade = parse_message(message.clean_content)
            except (AssertionError, AttributeError):
                return
            else:
                create_trade(bc, trade)


    dc.run(discord_token, bot=False)
