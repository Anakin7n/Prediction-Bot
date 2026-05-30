"""测试 bot/handlers.py 中的纯解析函数"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.handlers import _parse_date, _parse_movies, _parse_number


# ── _parse_date ──────────────────────────────────────────────

def test_parse_date_dot_format():
    assert _parse_date("6.15") == "6.15"


def test_parse_date_slash_format():
    assert _parse_date("6/15") == "6.15"


def test_parse_date_zero_padded():
    assert _parse_date("06/15") == "6.15"


def test_parse_date_full_iso():
    assert _parse_date("2026-06-15") == "6.15"


def test_parse_date_empty():
    assert _parse_date("") is None


def test_parse_date_garbage():
    assert _parse_date("abc") is None


def test_parse_date_whitespace():
    assert _parse_date("  6.15  ") == "6.15"


# ── _parse_movies ────────────────────────────────────────────

def test_parse_movies_simple():
    result = _parse_movies("消失的人:0.176, 狗阵:0.147")
    assert result == {"消失的人": 0.176, "狗阵": 0.147}


def test_parse_movies_percent_auto_convert():
    result = _parse_movies("消失的人:17.6%")
    assert result["消失的人"] == pytest.approx(0.176)


def test_parse_movies_big_number_auto_convert():
    result = _parse_movies("消失的人:17.6")
    assert result["消失的人"] == pytest.approx(0.176)


def test_parse_movies_chinese_colon():
    result = _parse_movies("消失的人：0.176")
    assert result == {"消失的人": 0.176}


def test_parse_movies_equals_separator():
    result = _parse_movies("消失的人=0.176")
    assert result == {"消失的人": 0.176}


def test_parse_movies_semicolon():
    result = _parse_movies("A:0.1;B:0.2")
    assert result == {"A": 0.1, "B": 0.2}


def test_parse_movies_chinese_semicolon():
    result = _parse_movies("A：0.1；B：0.2")
    assert result == {"A": 0.1, "B": 0.2}


def test_parse_movies_chinese_dunhao():
    result = _parse_movies("A:0.1、B:0.2")
    assert result == {"A": 0.1, "B": 0.2}


def test_parse_movies_fullwidth_percent():
    result = _parse_movies("消失的人:17.6％")
    assert result["消失的人"] == pytest.approx(0.176)


def test_parse_movies_newline_separator():
    result = _parse_movies("A:0.1\nB:0.2")
    assert result == {"A": 0.1, "B": 0.2}


def test_parse_movies_three_entries():
    result = _parse_movies("A:0.1, B:0.2, C:0.3")
    assert result == {"A": 0.1, "B": 0.2, "C": 0.3}


def test_parse_movies_empty():
    assert _parse_movies("") is None


def test_parse_movies_no_separator():
    assert _parse_movies("消失的人") is None


def test_parse_movies_nan_value():
    assert _parse_movies("消失的人:NaN") is None


def test_parse_movies_trailing_spaces():
    """当前行为：名字前的空格被 strip 清除，但分隔符周围的空格落在名字尾部。
       这是 regex 中 \\s 使分隔符类与 .+ 贪婪匹配交互的结果。
       用户输入 " 消失的人 : 0.176" → 名字解析为 "消失的人 :"。"""
    result = _parse_movies("  消失的人 : 0.176  ")
    assert result["消失的人 :"] == pytest.approx(0.176)
    assert len(result) == 1


# ── _parse_number ────────────────────────────────────────────

def test_parse_number_plain():
    assert _parse_number("420000") == 420000


def test_parse_number_with_commas():
    assert _parse_number("420,000") == 420000


def test_parse_number_chinese_commas():
    assert _parse_number("420，000") == 420000


def test_parse_number_wan():
    assert _parse_number("42万") == 420000


def test_parse_number_wan_decimal():
    assert _parse_number("42.5万") == 425000


def test_parse_number_spaces():
    assert _parse_number("42 0000") == 420000


def test_parse_number_empty():
    assert _parse_number("") is None


def test_parse_number_garbage():
    assert _parse_number("abc") is None
