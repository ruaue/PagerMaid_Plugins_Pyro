import contextlib

from pyrogram import filters

from pagermaid.enums import Message
from pagermaid.listener import raw_listener


@raw_listener(filters.private & filters.voice & filters.incoming)
async def voice_only_contact(message: Message):
    with contextlib.suppress(Exception):
        if message.from_user.is_contact:
            return
        await message.delete()
