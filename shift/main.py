""" PagerMaid module for channel help. """

import contextlib
import datetime
from asyncio import sleep
from random import uniform
from typing import Any, List, Literal, Optional

import pytz
from pyrogram.enums import ChatType
from pyrogram.errors import FloodWait
from pyrogram.types import Chat

from pagermaid.config import Config
from pagermaid.enums import Client, Message
from pagermaid.enums.command import CommandHandler
from pagermaid.listener import listener
from pagermaid.services import bot, scheduler, sqlite
from pagermaid.utils import lang, logs
from pagermaid.utils.bot_utils import log

WHITELIST = [-1001441461877]
AVAILABLE_OPTIONS_TYPE = Literal["silent", "text", "all", "photo", "document", "video"]
AVAILABLE_OPTIONS = {"silent", "text", "all", "photo", "document", "video"}
HELP_TEXT = """set [from channel] [to channel] (silent) 自动转发频道新消息（可以使用频道用户名或者 id）
del [from channel] 删除转发
backup [from channel] [to channel] (silent) 备份频道（可以使用频道用户名或者 id）
list 顯示目前轉發的頻道
选项说明：
silent: 禁用通知, text: 文字, all: 全部訊息都傳, photo: 圖片, document: 檔案, video: 影片"""


def try_cast_or_fallback(val: Any, t: type) -> Any:
    try:
        return t(val)
    except:
        return val


def check_chat_available(chat: Chat):
    assert (
        chat.type
        in [
            ChatType.CHANNEL,
            ChatType.GROUP,
            ChatType.SUPERGROUP,
            ChatType.BOT,
            ChatType.PRIVATE,
        ]
        and not chat.has_protected_content
    )


@listener(
    command="shift",
    description="开启转发频道新消息功能",
    parameters=HELP_TEXT,
)
async def shift_func(message: Message):
    await message.edit(HELP_TEXT)


shift_func: "CommandHandler"


@shift_func.sub_command(command="set")
async def shift_func_set(client: Client, message: Message):
    if len(message.parameter) < 3:
        return await message.edit(f"{lang('error_prefix')}{lang('arg_error')}")
    options = set(message.parameter[3:] if len(message.parameter) > 3 else ())
    if set(options).difference(AVAILABLE_OPTIONS):
        return await message.edit("出错了呜呜呜 ~ 无法识别的选项。")
    # 检查来源频道
    try:
        source = await client.get_chat(try_cast_or_fallback(message.parameter[1], int))
        assert isinstance(source, Chat)
        check_chat_available(source)
    except Exception:
        return await message.edit("出错了呜呜呜 ~ 无法识别的来源对话。")
    if source.id in WHITELIST:
        return await message.edit("出错了呜呜呜 ~ 此对话位于白名单中。")
    # 检查目标频道
    try:
        target = await client.get_chat(try_cast_or_fallback(message.parameter[2], int))
        assert isinstance(target, Chat)
    except Exception:
        return await message.edit("出错了呜呜呜 ~ 无法识别的目标对话。")
    if target.id in WHITELIST:
        await message.edit("出错了呜呜呜 ~ 此对话位于白名单中。")
        return
    sqlite[f"shift.{source.id}"] = target.id
    sqlite[f"shift.{source.id}.options"] = (
        message.parameter[3:] if len(message.parameter) > 3 else ["all"]
    )
    await message.edit(f"已成功配置将对话 {source.id} 的新消息转发到 {target.id} 。")
    await log(f"已成功配置将对话 {source.id} 的新消息转发到 {target.id} 。")


@shift_func.sub_command(command="del")
async def shift_func_del(message: Message):
    if len(message.parameter) != 2:
        return await message.edit(f"{lang('error_prefix')}{lang('arg_error')}")
    # 检查来源频道
    try:
        source = try_cast_or_fallback(message.parameter[1], int)
        assert isinstance(source, int)
    except Exception:
        return await message.edit("出错了呜呜呜 ~ 无法识别的来源对话。")
    try:
        del sqlite[f"shift.{source}"]
        with contextlib.suppress(Exception):
            del sqlite[f"shift.{source}.options"]
    except Exception:
        return await message.edit("emm...当前对话不存在于自动转发列表中。")
    await message.edit(f"已成功关闭对话 {str(source)} 的自动转发功能。")
    await log(f"已成功关闭对话 {str(source)} 的自动转发功能。")


@shift_func.sub_command(command="backup")
async def shift_func_backup(client: Client, message: Message):
    if len(message.parameter) < 3:
        return await message.edit(f"{lang('error_prefix')}{lang('arg_error')}")
    options = set(message.parameter[3:] if len(message.parameter) > 3 else ())
    if set(options).difference(AVAILABLE_OPTIONS):
        return await message.edit("出错了呜呜呜 ~ 无法识别的选项。")
    # 检查来源频道
    try:
        source = await client.get_chat(try_cast_or_fallback(message.parameter[1], int))
        assert isinstance(source, Chat)
        check_chat_available(source)
    except Exception:
        return await message.edit("出错了呜呜呜 ~ 无法识别的来源对话。")
    if source.id in WHITELIST:
        return await message.edit("出错了呜呜呜 ~ 此对话位于白名单中。")
    # 检查目标频道
    try:
        target = await client.get_chat(try_cast_or_fallback(message.parameter[2], int))
        assert isinstance(target, Chat)
    except Exception:
        return await message.edit("出错了呜呜呜 ~ 无法识别的目标对话。")
    if target.id in WHITELIST:
        return await message.edit("出错了呜呜呜 ~ 此对话位于白名单中。")
    # 开始遍历消息
    await message.edit(f"开始备份频道 {source.id} 到 {target.id} 。")

    # 如果有把get_chat_history方法merge進去就可以實現從舊訊息到新訊息,https://github.com/pyrogram/pyrogram/pull/1046
    # async for msg in client.get_chat_history(source.id,reverse=True):

    async for msg in client.search_messages(source.id):  # type: ignore
        await sleep(uniform(0.5, 1.0))
        await loosely_forward(
            message,
            msg,
            target.id,
            list(options),
            disable_notification="silent" in options,
        )
    await message.edit(f"备份频道 {source.id} 到 {target.id} 已完成。")


# 列出要轉存的頻道
@shift_func.sub_command(command="list")
async def shift_func_list(message: Message):
    from_ids = list(
        filter(
            lambda x: (x.startswith("shift.") and (not x.endswith("options"))),
            list(sqlite.keys()),
        )
    )
    if not from_ids:
        return await message.edit("沒有要轉存的頻道")
    output = "總共有 %d 個頻道要轉存\n\n" % len(from_ids)
    for from_id in from_ids:
        to_id = sqlite[from_id]
        output += "%s -> %s\n" % (
            format_channel_id(from_id[6:]),
            format_channel_id(to_id),
        )
    await message.edit(output)


def format_channel_id(channel_id: str):
    short_channel_id = str(channel_id)[4:]
    return f"[{channel_id}](https://t.me/c/{short_channel_id})"


@listener(is_plugin=True, incoming=True, ignore_edited=True)
async def shift_channel_message(message: Message):
    """Event handler to auto forward channel messages."""
    source = message.chat.id
    target = sqlite.get(f"shift.{source}")
    if not target:
        return
    if message.chat.has_protected_content:
        del sqlite[f"shift.{source}"]
        return
    options = sqlite.get(f"shift.{source}.options") or []

    with contextlib.suppress(Exception):
        if message.media_group_id:
            add_or_replace_forward_group_media(
                target,
                source,
                message.id,
                message.media_group_id,
                options,
                disable_notification="silent" in options,
            )
            return
        await loosely_forward(
            None,
            message,
            target,
            options,
            disable_notification="silent" in options,
        )


async def loosely_forward(
    notifier: Optional[Message],
    message: Message,
    chat_id: int,
    options: List[AVAILABLE_OPTIONS_TYPE],
    disable_notification: bool = False,
):
    # 找訊息類型video、document...
    media_type = message.media.value if message.media else "text"
    if (not options) or "all" in options:
        await forward_messages(
            chat_id, message.chat.id, [message.id], disable_notification, notifier
        )
    elif media_type in options:
        await forward_messages(
            chat_id, message.chat.id, [message.id], disable_notification, notifier
        )
    else:
        logs.debug("skip message type: %s", media_type)


async def forward_messages(
    cid: int,
    from_id: int,
    message_ids: List[int],
    disable_notification: bool,
    notifier: Optional["Message"],
):
    try:
        await bot.forward_messages(
            cid, from_id, message_ids, disable_notification=disable_notification
        )
    except FloodWait as ex:
        min_time: int = ex.value  # type: ignore
        delay = min_time + uniform(0.5, 1.0)
        if notifier:
            await notifier.edit(f"触发 Flood ，暂停 {delay} 秒。")
        await sleep(delay)
        await forward_messages(
            cid, from_id, message_ids, disable_notification, notifier
        )
    except Exception:
        pass  # drop other errors


async def forward_group_media(
    cid: int,
    from_id: int,
    group_id: int,
    options: List[AVAILABLE_OPTIONS_TYPE],
    disable_notification: bool,
):
    try:
        msgs = await bot.get_media_group(from_id, group_id)
    except Exception:
        logs.debug("get_media_group failed for %d %d", from_id, group_id)
        return
    real_msgs = []
    for message in msgs:
        media_type = message.media.value if message.media else "text"
        if (not options) or "all" in options:
            real_msgs.append(message)
        elif media_type in options:
            real_msgs.append(message)
        else:
            logs.debug("skip message type: %s", media_type)
    if not real_msgs:
        return
    real_msgs_ids = [msg.id for msg in real_msgs]
    await forward_messages(cid, from_id, real_msgs_ids, disable_notification, None)


def add_or_replace_forward_group_media(
    cid: int,
    from_id: int,
    message_id: int,
    group_id: int,
    options: List[AVAILABLE_OPTIONS_TYPE],
    disable_notification: bool,
):
    key = f"shift.forward_group_media.{group_id}"
    scheduler.add_job(
        forward_group_media,
        trigger="date",
        args=(cid, from_id, message_id, options, disable_notification),
        id=key,
        name=key,
        replace_existing=True,
        run_date=datetime.datetime.now(pytz.timezone(Config.TIME_ZONE))
        + datetime.timedelta(seconds=4),
    )
