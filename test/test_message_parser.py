from discord import Client

from automation.config import config
from automation.message_parser import MessageParser, UnknownMessage

if __name__ == '__main__':
    dc = Client()


    @dc.event
    async def on_ready() -> None:
        channel = dc.get_channel(config['discord']['channel'])

        async for message in channel.history():
            try:
                MessageParser.parse(message.content)
            except UnknownMessage:
                print(message.content + '\n')


    dc.run(config['discord']['token'], bot=False)
