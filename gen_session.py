from telethon import TelegramClient
from telethon.sessions import StringSession
import asyncio

API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"

async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start()
    print("Session string:", client.session.save())

asyncio.run(main())
