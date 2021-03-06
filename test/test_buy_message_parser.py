from decimal import Decimal
from unittest import TestCase

from automation.message.buy_message import BuyMessage
from automation.parser.buy_message_parser import BuyMessageParser


class TestBuyMessageParser(TestCase):
    def test_vstup_limit(self):
        content = '''
            16.12.20 IRIS/BTC
            Vstup : 281
            1. target : 310
            2. target : 332
            Stoploss : 260
        '''
        msg = BuyMessageParser.parse(content, parent_content=None)
        self.assertEqual(msg.symbol, 'IRISBTC')
        self.assertEqual(msg.buy_type, BuyMessage.BUY_LIMIT)
        self.assertEqual(msg.buy_price, Decimal('281'))
        self.assertEqual(msg.targets, [Decimal('310'), Decimal('332')])
        self.assertEqual(msg.stop_loss, Decimal('260'))

    def test_limitny_vstup(self):
        content = '''
            12.01.21 1INCH/USDT
            Limitný vstup : 1.0867
            1. target : 1.3546 /24.44%/
            2. target : 1.5412 /41.82%/
            Stoploss : 0.9145 /-15.85%/
        '''
        msg = BuyMessageParser.parse(content, parent_content=None)
        self.assertEqual(msg.symbol, '1INCHUSDT')
        self.assertEqual(msg.buy_type, BuyMessage.BUY_LIMIT)
        self.assertEqual(msg.buy_price, Decimal('1.0867'))
        self.assertEqual(msg.targets, [Decimal('1.3546'), Decimal('1.5412')])
        self.assertEqual(msg.stop_loss, Decimal('0.9145'))

    def test_limitny_prikaz(self):
        content = '''
            06.01.21 BLZ/BTC
            Limitný príkaz : 238 - 240
            1. target : 287 /+20,05%/
            Stoploss : 208 /-12,55%/
        '''
        msg = BuyMessageParser.parse(content, parent_content=None)
        self.assertEqual(msg.symbol, 'BLZBTC')
        self.assertEqual(msg.buy_type, BuyMessage.BUY_LIMIT)
        self.assertEqual(msg.buy_price, Decimal('238'))
        self.assertEqual(msg.targets, [Decimal('287')])
        self.assertEqual(msg.stop_loss, Decimal('208'))

    def test_vstup_market(self):
        content = '''
            17.02.21 OCEAN/USDT
            Vstup : market
            1. target : 1.16 /15.49%/
            2. target : 1.29 /28.20%/
            Stoploss : 0.85 /-14.97%/
        '''
        msg = BuyMessageParser.parse(content, parent_content=None)
        self.assertEqual(msg.symbol, 'OCEANUSDT')
        self.assertEqual(msg.buy_type, BuyMessage.BUY_MARKET)
        self.assertIsNone(msg.buy_price)
        self.assertEqual(msg.targets, [Decimal('1.16'), Decimal('1.29')])
        self.assertEqual(msg.stop_loss, Decimal('0.85'))

    def test_vstup_market2(self):
        content = '''
            09.01.21 KSM/USDT
            Vstup : 67.48 - market
            1. target : 76.81 /13.95%/
            Stoploss : 59.156 /12.14%/
        '''
        msg = BuyMessageParser.parse(content, parent_content=None)
        self.assertEqual(msg.symbol, 'KSMUSDT')
        self.assertEqual(msg.buy_type, BuyMessage.BUY_MARKET)
        self.assertIsNone(msg.buy_price)
        self.assertEqual(msg.targets, [Decimal('76.81')])
        self.assertEqual(msg.stop_loss, Decimal('59.156'))

    def test_vstup_market3(self):
        content = '''
            16.03.21 ALGO/USDT
            Vstup: market 
            1.Target 1.708 /44%/
            Stop Loss: 0.988/16%/
        '''
        msg = BuyMessageParser.parse(content, parent_content=None)
        self.assertEqual(msg.symbol, 'ALGOUSDT')
        self.assertEqual(msg.buy_type, BuyMessage.BUY_MARKET)
        self.assertEqual(msg.targets, [Decimal('1.708')])
        self.assertEqual(msg.stop_loss, Decimal('0.988'))

    def test_target_stop_loss(self):
        content = '''
            18.03.21 WAVES/USDT
            Vstup : market
            1. target : 11.68 /14.25%/
            2. target : 9.10 /-11.05%/
        '''
        msg = BuyMessageParser.parse(content, parent_content=None)
        self.assertEqual(msg.symbol, 'WAVESUSDT')
        self.assertEqual(msg.buy_type, BuyMessage.BUY_MARKET)
        self.assertEqual(msg.targets, [Decimal('11.68')])
        self.assertEqual(msg.stop_loss, Decimal('9.1'))
