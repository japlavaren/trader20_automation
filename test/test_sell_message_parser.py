from unittest import TestCase

from automation.message.sell_message import SellMessage
from automation.message.unknown_message import UnknownMessage
from automation.parser.sell_message_parser import SellMessageParser


class TestBuyMessageParser(TestCase):
    def test_zvysok(self):
        with self.assertRaises(UnknownMessage):
            SellMessageParser.parse(
                content='1. target uzavrite uz teraz. zvysok obchodu nechajte bezat a stoploss dajte na vstup',
                parent_content=None,
            )

    def test_polovicu(self):
        with self.assertRaises(UnknownMessage):
            SellMessageParser.parse(
                content='KEY/USDT uzavrite polovicu pozície už teraz. Stoploss posuňte na vstup. Nejdem to riskovať.',
                parent_content=None,
            )

    def test_zavrite(self):
        msg = SellMessageParser.parse(
            content='Uzavrite teraz cely obchod rovnako sme vo velmi peknom zisku.',
            parent_content='11.03.21 HARD/USDT',
        )
        self.assertEqual(msg.symbol, 'HARDUSDT')
        self.assertEqual(msg.sell_type, SellMessage.SELL_MARKET)

    def test_ukoncite(self):
        msg = SellMessageParser.parse(
            content='ukoncite cely obchod teraz sme +17%. nebudeme riskovat tych par % do targetu.',
            parent_content='12.03.21 ZEN/USDT',
        )
        self.assertEqual(msg.symbol, 'ZENUSDT')
        self.assertEqual(msg.sell_type, SellMessage.SELL_MARKET)

    def test_predajte(self):
        msg = SellMessageParser.parse(
            content='predajte teraz sme +13%.',
            parent_content='01.03.21 WNXM/USD',
        )
        self.assertEqual(msg.symbol, 'WNXMUSDT')
        self.assertEqual(msg.sell_type, SellMessage.SELL_MARKET)

    def test_skoncite(self):
        msg = SellMessageParser.parse(
            content='Skončite celý obchod. Akurát sme cca na vstupe.',
            parent_content='23.01.21 NANO/BTC',
        )
        self.assertEqual(msg.symbol, 'NANOBTC')
        self.assertEqual(msg.sell_type, SellMessage.SELL_MARKET)
