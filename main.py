"""影片落位预测 Bot — WebSocket 长连接版"""

import asyncio
import concurrent.futures
import inspect
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
import websockets

from config import FEISHU_APP_ID, FEISHU_APP_SECRET
from bot.handlers import BotHandler

FEISHU_DOMAIN = "https://open.feishu.cn"
WS_ENDPOINT_URI = "/callback/ws/endpoint"
SEEN_FILE = Path(__file__).parent / ".seen_msg_ids"
SEEN_MAX = 500
SEEN_KEEP = 300

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


class TokenCache:
    def __init__(self):
        self._token = ""
        self._expire = 0
        self._lock = threading.Lock()

    def get(self) -> str:
        now = time.time()
        if self._token and now < self._expire:
            return self._token
        with self._lock:
            if self._token and now < self._expire:
                return self._token
            resp = requests.post(
                f"{FEISHU_DOMAIN}/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
                timeout=10,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise Exception(f"获取token失败: {data}")
            self._token = data["tenant_access_token"]
            self._expire = now + data.get("expire", 7200) - 300
            return self._token


_token_cache = TokenCache()


def _feishu_post(path: str, json_body: dict | None = None, files: dict | None = None, data: dict | None = None):
    headers = {"Authorization": f"Bearer {_token_cache.get()}"}
    kwargs = {"headers": headers, "timeout": 60}
    if files is not None:
        kwargs["files"] = files
        if data:
            kwargs["data"] = data
    else:
        kwargs["json"] = json_body or {}
    resp = requests.post(f"{FEISHU_DOMAIN}{path}", **kwargs)
    return resp.json()


class MessageSender:
    def send_text(self, chat_id: str, text: str):
        content = json.dumps({"text": text}, ensure_ascii=False)
        resp = _feishu_post(
            f"/open-apis/im/v1/messages?receive_id_type=chat_id",
            {"receive_id": chat_id, "msg_type": "text", "content": content},
        )
        if resp.get("code") == 0:
            logging.info(f"已发送文本到 {chat_id}")
        else:
            logging.error(f"发送文本失败 code={resp.get('code')} msg={resp.get('msg')}")

    def send_file(self, chat_id: str, file_bytes: BytesIO, filename: str):
        file_bytes.seek(0)
        file_size = file_bytes.getbuffer().nbytes

        upload_resp = _feishu_post(
            "/open-apis/im/v1/files",
            files={"file": (filename, file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"file_name": filename, "file_type": "xlsx"},
        )
        if upload_resp.get("code") != 0:
            logging.error(f"文件上传失败: {upload_resp}")
            return

        file_key = upload_resp.get("data", {}).get("file_key", "")
        if not file_key:
            logging.error(f"未获取到 file_key: {upload_resp}")
            return

        content = json.dumps({"file_key": file_key}, ensure_ascii=False)
        send_resp = _feishu_post(
            f"/open-apis/im/v1/messages?receive_id_type=chat_id",
            {"receive_id": chat_id, "msg_type": "file", "content": content},
        )
        if send_resp.get("code") == 0:
            logging.info(f"已发送文件到 {chat_id}")
        else:
            logging.error(f"发送文件失败 code={send_resp.get('code')} msg={send_resp.get('msg')}")


_seen_cache: set[str] | None = None
_seen_lock = threading.RLock()


def _init_seen():
    global _seen_cache
    _seen_cache = set()
    if SEEN_FILE.exists():
        with open(SEEN_FILE, "r") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    _seen_cache.add(stripped)


def _trim_seen():
    with _seen_lock:
        if not SEEN_FILE.exists():
            return
        with open(SEEN_FILE, "r") as f:
            all_lines = [line.strip() for line in f if line.strip()]
        if len(all_lines) <= SEEN_MAX:
            return
        kept = all_lines[-SEEN_KEEP:]
        with open(SEEN_FILE, "w") as f:
            for line in kept:
                f.write(line + "\n")
        global _seen_cache
        _seen_cache = set(kept)


def _is_duplicate(msg_id: str) -> bool:
    global _seen_cache
    with _seen_lock:
        if _seen_cache is None:
            _init_seen()
        if msg_id in _seen_cache:
            return True
        _seen_cache.add(msg_id)
        with open(SEEN_FILE, "a") as f:
            f.write(msg_id + "\n")
            f.flush()
            os.fsync(f.fileno())
        if len(_seen_cache) > SEEN_MAX:
            _trim_seen()
        return False


def _is_content_duplicate(content_str: str) -> bool:
    return False


def _pb_write_varint(buf: bytearray, n: int):
    while n > 127:
        buf.append((n & 0x7F) | 0x80)
        n >>= 7
    buf.append(n & 0x7F)


def _pb_write_tag(buf: bytearray, field: int, wire: int):
    _pb_write_varint(buf, (field << 3) | wire)


def _pb_write_string(buf: bytearray, field: int, value: str):
    _pb_write_tag(buf, field, wire=2)
    encoded = value.encode("utf-8")
    _pb_write_varint(buf, len(encoded))
    buf.extend(encoded)


def _pb_write_int32(buf: bytearray, field: int, value: int):
    _pb_write_tag(buf, field, wire=0)
    _pb_write_varint(buf, value)


def _pb_write_uint64(buf: bytearray, field: int, value: int):
    _pb_write_tag(buf, field, wire=0)
    _pb_write_varint(buf, value)


def encode_ping_frame(service_id: int) -> bytes:
    buf = bytearray()
    header_buf = bytearray()
    _pb_write_string(header_buf, 1, "type")
    _pb_write_string(header_buf, 2, "ping")
    _pb_write_int32(buf, 4, 0)
    _pb_write_uint64(buf, 2, 0)
    _pb_write_uint64(buf, 1, 0)
    _pb_write_tag(buf, 3, 0)
    _pb_write_varint(buf, service_id)
    _pb_write_tag(buf, 5, 2)
    _pb_write_varint(buf, len(header_buf))
    buf.extend(header_buf)
    return bytes(buf)


def decode_frame(data: bytes) -> dict:
    result = {}
    pos = 0
    while pos < len(data):
        if pos >= len(data):
            break
        tag = data[pos]
        pos += 1
        field = tag >> 3
        wire = tag & 0x07
        if wire == 0:
            value = 0
            shift = 0
            while pos < len(data):
                b = data[pos]
                pos += 1
                value |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            result[field] = value
        elif wire == 2:
            length = 0
            shift = 0
            while pos < len(data):
                b = data[pos]
                pos += 1
                length |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            value = data[pos:pos + length]
            pos += length
            if field == 5:
                headers = []
                hpos = 0
                while hpos < len(value):
                    htag = value[hpos]
                    hpos += 1
                    hfield = htag >> 3
                    hwire = htag & 0x07
                    if hwire == 2:
                        hlen = 0
                        hshift = 0
                        while hpos < len(value):
                            hb = value[hpos]
                            hpos += 1
                            hlen |= (hb & 0x7F) << hshift
                            hshift += 7
                            if not (hb & 0x80):
                                break
                        headers.append((hfield, value[hpos:hpos + hlen].decode("utf-8")))
                        hpos += hlen
                result[field] = headers
            else:
                result[field] = value
    return result


class FeishuWsClient:
    def __init__(self, handler: BotHandler):
        self._sender = MessageSender()
        self._handler = handler
        self._service_id = ""
        self._reconnect_interval = 120
        self._ping_interval = 120
        self._ws = None
        self._ping_task = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    def _get_ws_url(self) -> str:
        resp = requests.post(
            f"{FEISHU_DOMAIN}{WS_ENDPOINT_URI}",
            headers={"locale": "zh"},
            json={"AppID": FEISHU_APP_ID, "AppSecret": FEISHU_APP_SECRET},
            timeout=30,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"获取WS地址失败: {data}")
        dd = data.get("data", {})
        if dd.get("ClientConfig"):
            cc = dd["ClientConfig"]
            self._reconnect_interval = cc.get("ReconnectInterval", 120)
            self._ping_interval = cc.get("PingInterval", 120)
        return dd["URL"]

    async def _ping_loop(self):
        while True:
            try:
                if self._ws is not None:
                    sid = int(self._service_id) if self._service_id else 0
                    ping = encode_ping_frame(sid)
                    await self._ws.send(ping)
            except Exception as e:
                logging.warning(f"ping失败: {e}")
            await asyncio.sleep(self._ping_interval)

    def _dispatch_sync(self, event_data: dict):
        try:
            event = event_data.get("event", {})
            msg = event.get("message", {})
            msg_id = msg.get("message_id", "")

            if _is_duplicate(msg_id):
                return

            create_time_ms = msg.get("create_time", "")
            if create_time_ms:
                try:
                    age = time.time() - int(create_time_ms) / 1000
                    if age > 180:
                        logging.info(f"[跳过] 消息过旧 ({age:.0f}s 前)")
                        return
                except (ValueError, OSError):
                    pass

            chat_id = msg.get("chat_id", "")
            msg_type = msg.get("message_type", "")

            sender_info = event.get("sender", {})
            if sender_info.get("sender_type") == "app":
                return

            if msg_type != "text":
                logging.info(f"[跳过] 非文本消息: {msg_type}")
                return

            content_str = msg.get("content", "{}")

            logging.info(f"[消息] chat_id={chat_id} content={content_str[:100]}")

            try:
                content_json = json.loads(content_str)
                text = content_json.get("text", "")
            except (json.JSONDecodeError, AttributeError):
                text = content_str

            if not text:
                logging.info("[跳过] 空文本")
                return

            text = re.sub(r'@\S+\s*', '', text).strip()
            logging.info(f"[文本] {text}")

            if text.strip().lower() != "/start" and _is_content_duplicate(content_str):
                logging.info("[跳过] 内容重复")
                return

            user_id = sender_info.get("sender_id", {}).get("open_id", "")
            self._handler.handle_message(user_id, chat_id, text)

        except Exception as e:
            logging.error(f"[分发异常] {e}")
            traceback.print_exc()

    async def _process_event(self, event_data: dict):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._dispatch_sync, event_data)

    async def _read_loop(self):
        while True:
            try:
                raw = await self._ws.recv()
                if isinstance(raw, str):
                    continue
                frame = decode_frame(raw)
                ft = frame.get(4, -1)
                if ft == 0:
                    continue
                elif ft == 1:
                    payload = frame.get(8, b"")
                    if not payload:
                        continue
                    event_data = json.loads(payload.decode("utf-8"))
                    asyncio.create_task(self._process_event(event_data))
            except websockets.exceptions.ConnectionClosed:
                logging.warning("连接断开")
                break
            except Exception as e:
                logging.error(f"读取异常: {e}")
                traceback.print_exc()

    async def _try_connect(self):
        url = self._get_ws_url()
        u = urlparse(url)
        q = parse_qs(u.query)
        self._service_id = q.get("service_id", [""])[0]
        logging.info(f"WS地址: {url[:80]}...")
        logging.info(f"服务ID: {self._service_id}")

        params = inspect.signature(websockets.connect).parameters
        kwargs = {"proxy": None} if "proxy" in params else {}
        self._ws = await websockets.connect(url, **kwargs)
        logging.info("WS已连接")
        self._ping_task = asyncio.create_task(self._ping_loop())
        await self._read_loop()

    async def connect(self):
        while True:
            try:
                await self._try_connect()
            except Exception as e:
                logging.error(f"连接失败: {e}")
            if self._ws is not None:
                await self._ws.close()
                self._ws = None
            if self._ping_task is not None:
                self._ping_task.cancel()
                self._ping_task = None
            logging.info(f"将在 {self._reconnect_interval}s 后重连...")
            await asyncio.sleep(self._reconnect_interval)

    def start(self):
        asyncio.run(self.connect())


def main():
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        logging.error("请先在 .env 中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        sys.exit(1)

    sender = MessageSender()
    handler = BotHandler(sender)

    logging.info(f"🚀 影片落位预测 Bot 启动中... (App ID: {FEISHU_APP_ID})")
    logging.info("WebSocket 长连接模式，监听群聊消息中...")

    client = FeishuWsClient(handler)
    client.start()


if __name__ == "__main__":
    main()
