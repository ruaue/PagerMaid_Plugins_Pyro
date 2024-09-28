import platform
import tarfile
import json
from pathlib import Path

from pagermaid.enums import Message
from pagermaid.enums.command import CommandHandler
from pagermaid.listener import listener
from pagermaid.services import client
from pagermaid.utils import lang, execute, safe_remove

VERSION = "1.7.9"
DATA_PATH = Path("data") / "speedtest_go"
DATA_PATH.mkdir(parents=True, exist_ok=True)
FILE_PATH = DATA_PATH / (f"{VERSION}.exe" if platform.system() == "Windows" else VERSION)
FILE_TAR_PATH = DATA_PATH / f"{VERSION}.tar.gz"


def unit_convert(byte):
    """Converts byte into readable formats."""
    power = 1000
    zero = 0
    units = {0: "", 1: "Kb/s", 2: "Mb/s", 3: "Gb/s", 4: "Tb/s"}
    while byte > power:
        byte /= power
        zero += 1
    return f"{round(byte, 2)} {units[zero]}"


class NotSupportSystem(BaseException):
    """不支持的系统"""


def get_download_url() -> str:
    system = platform.system()
    system_str = {"Windows": "Windows", "Darwin": "Darwin", "Linux": "Linux"}.get(system)
    if not system_str:
        raise NotSupportSystem(f"不支持的系统: {system}")
    bits, _ = platform.architecture()
    processor = platform.processor()
    arm = "arm" in processor.lower()
    software_type = ""
    if bits == "64bit":
        if arm:
            software_type = "arm64"
        else:
            software_type = "x86_64"
    else:
        software_type = "i386"
    return f"https://github.com/showwin/speedtest-go/releases/download/v{VERSION}/speedtest-go_{VERSION}_{system_str}_{software_type}.tar.gz"


def unzip_file():
    tar = tarfile.open(FILE_TAR_PATH)
    file_names = tar.getnames()
    for file_name in file_names:
        if not file_name.startswith("speedtest-go"):
            continue
        tar.extract(file_name, DATA_PATH)
        (DATA_PATH / file_name).rename(FILE_PATH)
    tar.close()
    safe_remove(str(FILE_TAR_PATH))


async def download_go() -> None:
    if FILE_PATH.exists():
        return
    if FILE_TAR_PATH.exists():
        FILE_TAR_PATH.unlink()
    url = get_download_url()
    head = await client.head(url, follow_redirects=True)
    try:
        head.raise_for_status()
    except Exception as e:
        raise NotSupportSystem(f"下载链接生成失败，请联系管理员：{e}")
    file_data = await client.get(url, follow_redirects=True)
    with open(FILE_TAR_PATH, "wb") as f:
        f.write(file_data.content)
    try:
        unzip_file()
    except Exception as e:
        raise NotSupportSystem(f"解压失败，请联系管理员：{e}")


async def run_command(command: str) -> str:
    await download_go()
    args = [str(FILE_PATH)] + command.split()
    result = await execute(" ".join(args))
    return result


async def get_all_ids():
    data = await run_command("-l --json")
    return ("附近的测速点有：\n\n" + data) if data else "获取失败，请联系管理员"


async def run_speedtest(server: int) -> str:
    args = f"--server={server} --json" if server else "--json"
    _data = await run_command(args)
    try:
        result = json.loads(_data)
        result["server"] = result["servers"][0]
    except json.JSONDecodeError:
        return "解析输出失败，请联系管理员"
    latency = round(result['server']['latency'] / 1000 / 1000, 2)
    return (
        f"**Speedtest** \n"
        f"Server: `{result['server']['name']} - "
        f"{result['server']['country']}` \n"
        f"Sponsor: `{result['server']['sponsor']}` \n"
        f"Upload: `{unit_convert(result['server']['ul_speed'])}` \n"
        f"Download: `{unit_convert(result['server']['dl_speed'])}` \n"
        f"Latency: `{latency}ms` \n"
        f"Timestamp: `{result['timestamp']}`"
    )


@listener(
    command="speedtest_go",
    need_admin=True,
    description=lang('speedtest_des'),
    parameters="(list/server id)",
)
async def speedtest_go(message: Message):
    """ Tests internet speed using speedtest. """
    try:
        server = int(message.arguments)
    except ValueError:
        server = 0
    msg: Message = await message.edit(lang("speedtest_processing"))
    des = await run_speedtest(server)
    return await msg.edit(des)


speedtest_go: "CommandHandler"


@speedtest_go.sub_command(
    command="list",
)
async def speedtest_go_list(message: Message):
    msg: Message = await message.edit(lang("speedtest_processing"))
    try:
        des = await get_all_ids()
    except NotSupportSystem as e:
        des = str(e)
    return await msg.edit(des)
