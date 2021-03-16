import re
from typing import Tuple

from unidecode import unidecode


class UnknownMessage(Exception):
    pass


def normalize(msg: str) -> str:
    msg = unidecode(msg)  # remove diacritic
    msg = ' '.join(msg.split())  # remove multiple spaces
    msg = re.sub(r'\s*:\s*', ': ', msg)  # normalize spaces around colon
    msg = re.sub(r'\s*/\s*', '/', msg)  # remove spaces around slash

    return msg.lower()


def parse_symbol(normalized: str) -> Tuple[str, str]:
    pairs = re.findall(r'([\da-z]+)/(usdt?|btc)', normalized)
    assert len(pairs) == 1, 'None or more than one symbol found'
    coin, currency = [s.upper() for s in pairs[0]]

    # replace USD to USDT
    if 'USD' in currency and 'USDT' not in currency:
        currency = currency.replace('USD', 'USDT')

    symbol = coin + currency

    return symbol, currency
