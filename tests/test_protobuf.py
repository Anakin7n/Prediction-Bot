"""测试 main.py 中的 protobuf 编解码函数"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import encode_ping_frame, _parse_ws_frame


def test_ping_frame_is_type_zero():
    """ping 帧的 field 4 = 0（控制帧）"""
    ping = encode_ping_frame(service_id=12345)
    decoded = _parse_ws_frame(ping)
    assert decoded.get(4) == 0


def test_ping_frame_ignores_other_fields():
    """_parse_ws_frame 只捕获 field 4 和 8，其他 field 被跳过"""
    ping = encode_ping_frame(service_id=999)
    decoded = _parse_ws_frame(ping)
    assert decoded == {4: 0}


def test_parse_event_frame():
    """模拟飞书事件帧：field 4=1, field 8=JSON payload"""
    buf = bytearray()
    buf.append((4 << 3) | 0)  # field 4, wire 0
    buf.append(1)              # value = 1
    buf.append((8 << 3) | 2)  # field 8, wire 2
    buf.append(5)              # length = 5
    buf.extend(b"hello")

    result = _parse_ws_frame(bytes(buf))
    assert result == {4: 1, 8: b"hello"}


def test_parse_empty():
    result = _parse_ws_frame(b"")
    assert result == {}


def test_decode_varint_single_byte():
    # field 4, wire 0, value 1
    result = _parse_ws_frame(b"\x20\x01")
    assert result.get(4) == 1


def test_decode_varint_two_bytes():
    # field 4, wire 0, value 300 (0xAC 0x02)
    result = _parse_ws_frame(b"\x20\xAC\x02")
    assert result.get(4) == 300


def test_skip_fixed64():
    """wire type 1 (fixed64) 应被跳过，不影响后续字段"""
    buf = bytearray()
    buf.append((1 << 3) | 1)   # field 1, wire 1
    buf.extend(b"\x00" * 8)    # 8 bytes padding
    buf.append((4 << 3) | 0)   # field 4, wire 0
    buf.append(42)              # value = 42
    result = _parse_ws_frame(bytes(buf))
    assert result == {4: 42}


def test_skip_non_field8_length_delimited():
    """field != 8 的 wire type 2 应跳过内容"""
    buf = bytearray()
    buf.append((5 << 3) | 2)   # field 5, wire 2
    buf.append(3)               # length = 3
    buf.extend(b"xyz")          # skip this
    buf.append((4 << 3) | 0)   # field 4, wire 0
    buf.append(7)               # value = 7
    result = _parse_ws_frame(bytes(buf))
    assert result == {4: 7}


def test_skip_fixed32():
    """wire type 5 (fixed32) 应被跳过"""
    buf = bytearray()
    buf.append((2 << 3) | 5)   # field 2, wire 5
    buf.extend(b"\x00" * 4)    # 4 bytes padding
    buf.append((4 << 3) | 0)   # field 4, wire 0
    buf.append(99)
    result = _parse_ws_frame(bytes(buf))
    assert result == {4: 99}
