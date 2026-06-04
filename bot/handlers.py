"""飞书 Bot 交互逻辑 - 状态机管理 (WebSocket 长连接版)"""

import re
from enum import Enum

from scraper.maoyan import MaoyanClient
from excel.generator import generate_excel
from bot import cards


class State(Enum):
    AWAITING_DATE = "awaiting_date"
    AWAITING_MOVIES = "awaiting_movies"
    AWAITING_DAPAN = "awaiting_dapan"


class BotHandler:
    def __init__(self, sender):
        self._maoyan = MaoyanClient()
        self._sender = sender
        self._sessions: dict[str, dict] = {}

    def handle_message(self, user_id: str, chat_id: str, text: str):
        text = text.strip()

        if text.lower() == "/start":
            self._start_new_session(user_id, chat_id)
            return

        session = self._sessions.get(user_id)
        if not session:
            self._sender.send_text(chat_id, cards.welcome())
            return

        state = session["state"]

        if state == State.AWAITING_DATE:
            self._handle_date(user_id, chat_id, session, text)
        elif state == State.AWAITING_MOVIES:
            self._handle_movies(user_id, chat_id, session, text)
        elif state == State.AWAITING_DAPAN:
            self._handle_dapan(user_id, chat_id, session, text)

    def _start_new_session(self, user_id: str, chat_id: str):
        self._sessions[user_id] = {"state": State.AWAITING_DATE}
        self._sender.send_text(chat_id, cards.ask_date())

    def _handle_date(self, user_id, chat_id, session, text: str):
        date_str = _parse_date(text)
        if not date_str:
            self._sender.send_text(chat_id, cards.invalid_format("请按格式输入日期，如 6.15 或 6/15"))
            return

        session["date"] = date_str
        session["state"] = State.AWAITING_MOVIES
        self._sender.send_text(chat_id, cards.ask_movies(date_str))

    def _handle_movies(self, user_id, chat_id, session, text: str):
        parsed = _parse_movies(text)
        if not parsed:
            self._sender.send_text(
                chat_id,
                cards.invalid_format(
                    "格式错误，请按格式输入：\n片名:占比, 片名:占比\n"
                    "支持 17.6%、0.176、5.6 等格式，中英文符号均可"
                ),
            )
            return

        session["movies_user"] = parsed
        session["state"] = State.AWAITING_DAPAN
        self._sender.send_text(chat_id, cards.ask_dapan(session["date"]))

    def _handle_dapan(self, user_id, chat_id, session, text: str):
        dapan = _parse_number(text)
        if dapan is None:
            self._sender.send_text(chat_id, cards.invalid_format("请输入有效数字，如 420000"))
            return

        session["dapan_total"] = dapan
        date_str = session["date"]

        self._sender.send_text(chat_id, cards.querying())

        try:
            matched, total_show_count = self._maoyan.fetch_by_date(list(session["movies_user"].keys()), date_str)
        except Exception as e:
            self._sender.send_text(chat_id, cards.error(f"猫眼数据获取失败: {e}"))
            return

        for m in matched:
            m["cumulative_share"] = session["movies_user"].get(m["name"], 0)

        excel_bytes = generate_excel(
            date_str=date_str,
            movies=matched,
            dapan_total=dapan,
            total_show_count=total_show_count,
        )

        movie_count = len(matched)
        self._sender.send_text(chat_id, cards.result(date_str, movie_count, dapan))
        self._sender.send_file(chat_id, excel_bytes, "影片落位预测.xlsx")
        self._sender.send_text(chat_id, cards.summary(date_str, matched, dapan, total_show_count))

        del self._sessions[user_id]


def _parse_date(text: str) -> str | None:
    text = text.strip()
    patterns = [
        r"^(\d{1,2})[./](\d{1,2})$",
        r"^\d{4}[-/](\d{1,2})[-/](\d{1,2})$",
    ]
    for pat in patterns:
        m = re.match(pat, text)
        if m:
            return f"{int(m.group(1))}.{int(m.group(2))}"
    return None


def _parse_movies(text: str) -> dict[str, float] | None:
    result = {}
    parts = re.split(r"[,，;；\n、]+", text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(.+)[:：=\-＞→\s]+(.+)$", part)
        if not m:
            return None
        name = m.group(1).strip()
        share_str = m.group(2).strip().rstrip("%％")
        if share_str.lower() == "nan" or share_str == "":
            return None
        try:
            share = float(share_str)
        except ValueError:
            return None
        if "%" in m.group(2) or "％" in m.group(2) or share > 1:
            share = share / 100
        result[name] = share
    return result if result else None


def _parse_number(text: str) -> int | None:
    text = text.strip().replace(",", "").replace("，", "").replace(" ", "")
    m = re.match(r"^([\d.]+)(万)?$", text)
    if not m:
        return None
    num = float(m.group(1))
    if m.group(2):
        num *= 10000
    return int(num)
