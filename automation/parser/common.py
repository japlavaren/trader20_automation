import re
from typing import List

from unidecode import unidecode


class UnknownMessage(Exception):
    pass


def normalize(msg: str) -> str:
    msg = unidecode(msg)  # remove diacritic
    msg = ' '.join(msg.split())  # remove multiple spaces
    msg = re.sub(r'\s*:\s*', ': ', msg)  # normalize spaces around colon
    msg = re.sub(r'\s*/\s*', '/', msg)  # remove spaces around slash

    return msg.lower()


def parse_symbol(normalized: str) -> str:
    symbols = re.findall(r'([\da-z]+/(?:usdt?|btc))', normalized)
    assert len(symbols) == 1, 'None or more than one symbol found'

    symbol = symbols[0].replace('/', '').upper()

    # replace USD to USDT
    if 'USD' in symbol and 'USDT' not in symbol:
        symbol = symbol.replace('USD', 'USDT')

    return symbol
