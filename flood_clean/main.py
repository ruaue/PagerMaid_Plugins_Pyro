import contextlib
import csv
from asyncio import sleep
from datetime import datetime
from pathlib import Path
from typing import List

from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait
from pyrogram.types import ChatEventFilter, ChatEvent

from pagermaid.enums import Client, Message
from pagermaid.enums.command import CommandHandler
from pagermaid.listener import listener

HELP_MSG = """通过表格清理 48 小时内加群的用户

- `get chat_id` 通过群组管理员日志生成表格（表格将会发送到当前会话，请注意隐私安全）
- `do chat_id` 通过表格清理用户，需要附带表格文件，将需要清理的用户最后一列标记为 1 即可。"""
JOIN_USER_FILTER = ChatEventFilter(new_members=True)
BAN_USER_FILTER = ChatEventFilter(new_restrictions=True)
DATA_PATH = Path("data")


class FloodClean:
    @staticmethod
    def get_file_name(chat_id: int) -> Path:
        return DATA_PATH / f"{chat_id}.csv"

    @staticmethod
    def generate_csv_line(event: "ChatEvent", writer: "csv.DictWriter", ids: List[int], banned_ids: List[int]):
        if not event.user:
            return
        user = event.user
        if event.invited_member and event.invited_member.user:
            user = event.invited_member.user
        if user.is_deleted:
            return
        if user.id in ids:
            return
        ids.append(user.id)
        writer.writerow({
            "uid": user.id,
            "full_name": user.full_name,
            "first_name": user.first_name,
            "last_name": user.last_name or "",
            "is_premium": user.is_premium,
            "is_bot": user.is_bot,
            "has_photo": bool(user.photo),
            "username": user.username or "",
            "date": event.date.strftime("%Y-%m-%d %H:%M:%S"),
            "is_kicked": user.id in banned_ids,
            "need_kick": 0,
        })

    @staticmethod
    async def get_banned_users(client: Client, chat_id: int) -> List[int]:
        ids = []
        now = datetime.now()
        async for event in client.get_chat_event_log(chat_id, filters=BAN_USER_FILTER):
            np = event.new_member_permissions
            if not np:
                continue
            if np.status != ChatMemberStatus.BANNED:
                continue
            user = np.user
            if not np.user:
                continue
            uid = user.id
            if np.until_date and np.until_date <= now:
                continue
            if uid not in ids:
                ids.append(uid)
        return ids

    @staticmethod
    async def get_event_log(client: Client, chat_id: int) -> str:
        field_order = [
            "uid",
            "full_name",
            "first_name",
            "last_name",
            "is_premium",
            "is_bot",
            "has_photo",
            "username",
            "date",
            "is_kicked",
            "need_kick",
        ]
        file_name = FloodClean.get_file_name(chat_id)
        ids = []
        banned_ids = await FloodClean.get_banned_users(client, chat_id)
        with open(file_name, 'w', encoding="utf-8", newline='') as csvfile:
            writer = csv.DictWriter(csvfile, field_order)
            writer.writeheader()
            async for event in client.get_chat_event_log(chat_id, filters=JOIN_USER_FILTER):
                FloodClean.generate_csv_line(event, writer, ids, banned_ids)
        return str(file_name)

    @staticmethod
    def get_need_kick_users(chat_id: int) -> List[int]:
        file_name = FloodClean.get_file_name(chat_id)
        ids = []
        with open(file_name, 'r', encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row["need_kick"] == "1":
                    uid = int(row["uid"])
                    if uid not in ids:
                        ids.append(uid)
        return ids

    @staticmethod
    async def try_kick_user(client: Client, message: Message, chat_id: int, uid: int):
        try:
            await client.ban_chat_member(chat_id, uid)
        except FloodWait as e:
            with contextlib.suppress(Exception):
                await message.edit(f"uid: {uid} 遇到 FloodWait，等待 {e.x} 秒")
            await sleep(e.value + 1)
            await FloodClean.try_kick_user(client, message, chat_id, uid)

    @staticmethod
    async def kick_users(client: Client, message: Message, chat_id: int):
        ids = FloodClean.get_need_kick_users(chat_id)
        for index, uid in enumerate(ids):
            if index % 10 == 0:
                with contextlib.suppress(Exception):
                    await message.edit(f"正在清理 {index}/{len(ids)}")
            await FloodClean.try_kick_user(client, message, chat_id, uid)


@listener(command="flood_clean")
async def flood_clean(message: Message):
    await message.edit(HELP_MSG)


flood_clean: "CommandHandler"


@flood_clean.sub_command(command="get")
async def flood_clean_get(client: Client, message: Message):
    if len(message.parameter) != 2:
        return await message.edit(HELP_MSG)
    await message.edit("获取中...请等待")
    chat_id = int(message.parameter[1])
    try:
        file_name = await FloodClean.get_event_log(client, chat_id)
    except Exception as e:
        return await message.edit(f"获取群组管理员日志失败: {e}")
    await message.edit("获取成功")
    await message.reply_document(file_name)


@flood_clean.sub_command(command="do")
async def flood_clean_do(client: Client, message: Message):
    if len(message.parameter) != 2 or (not message.document):
        return await message.edit(HELP_MSG)
    await message.edit("下载中...请等待")
    chat_id = int(message.parameter[1])
    file_name = FloodClean.get_file_name(chat_id)
    await message.download(str(file_name))
    await message.edit("清理中...请等待")
    try:
        await FloodClean.kick_users(client, message, chat_id)
    except Exception as e:
        return await message.edit(f"清理用户失败: {e}")
    await message.edit("清理成功")
