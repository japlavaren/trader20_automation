import re
from abc import ABC, abstractmethod
from typing import Optional

from unidecode import unidecode

from automation.message.message import Message


class Parser(ABC):
    @abstractmethod
    def parse(self, content: str, parent_content: Optional[str]) -> Message:
        pass

    @staticmethod
    def _normalize(msg: str) -> str:
        msg = unidecode(msg)  # remove diacritic
        msg = re.sub(r'[ \t]+', ' ', msg)  # remove multiple spaces, keep new lines
        msg = re.sub(r'\s*([:/])\s*', r'\1', msg)  # remove spaces around colon and slash

        return msg.lower()

    @staticmethod
    def _parse_symbol(normalized: str) -> str:
        symbols = re.findall(r'([\da-z]+/(?:usdt?|btc))', normalized)
        assert len(symbols) == 1, 'None or more than one symbol found'
        symbol = symbols[0].replace('/', '').upper()

        # replace USD to USDT
        if 'USD' in symbol and 'USDT' not in symbol:
            symbol = symbol.replace('USD', 'USDT')

        return symbol
