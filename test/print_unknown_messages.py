from discord import Client

from automation.config import config
from automation.parser.message_parser import MessageParser, UnknownMessage

if __name__ == '__main__':
    dc = Client()


    @dc.event
    async def on_ready() -> None:
        channel = dc.get_channel(config['discord']['channel'])
        messages = []

        async for message in channel.history():
            content = message.content
            parent_content = message.reference.resolved.content if message.reference is not None else None
            messages.append((content, parent_content))

        for content, parent_content in messages:
            try:
                MessageParser.parse(content, parent_content)
                continue
            except (UnknownMessage, AssertionError):
                print(f'{content}\n-----\n{parent_content}\n\n\n')

        await dc.close()


    dc.run(config['discord']['token'], bot=False)
