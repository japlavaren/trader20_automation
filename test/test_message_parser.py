from discord import Client

from automation.config import config
from automation.message_parser import MessageParser, UnknownMessage

if __name__ == '__main__':
    dc = Client()


    @dc.event
    async def on_ready() -> None:
        channel = dc.get_channel(config['discord']['channel'])
        messages = [message.content async for message in channel.history()]

        for message in messages:
            # ignore this message
            if '12.01.21 WRX/USDT' in message:
                continue

            try:
                MessageParser.parse(message)
            except UnknownMessage:
                print(message + '\n')

        await dc.close()


    dc.run(config['discord']['token'], bot=False)
