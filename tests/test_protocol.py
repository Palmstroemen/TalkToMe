"""Tests for the line-based JSON protocol between addon and speech service."""

import json

from ttm_core import protocol
from ttm_core.protocol import LineDecoder, encode, make_message


def test_make_message():
    assert make_message("hello", token="abc", version=1) == {"type": "hello", "token": "abc", "version": 1}


def test_encode_is_one_utf8_line():
    data = encode(make_message("transcript", text="Zwölf Millimeter"))
    assert data.endswith(b"\n")
    assert data.count(b"\n") == 1
    assert json.loads(data.decode("utf-8")) == {"type": "transcript", "text": "Zwölf Millimeter"}


def test_roundtrip():
    decoder = LineDecoder()
    msg = make_message("transcript", text="Schließe den Sketch", stt_ms=812)
    assert decoder.feed(encode(msg)) == [msg]


def test_decoder_handles_split_lines():
    decoder = LineDecoder()
    data = encode(make_message("state", state="listening"))
    assert decoder.feed(data[:5]) == []
    assert decoder.feed(data[5:]) == [{"type": "state", "state": "listening"}]


def test_decoder_handles_multibyte_char_split_across_chunks():
    decoder = LineDecoder()
    data = encode(make_message("transcript", text="ö"))
    split = data.index("ö".encode("utf-8")) + 1      # in the middle of the umlaut
    assert decoder.feed(data[:split]) == []
    assert decoder.feed(data[split:]) == [{"type": "transcript", "text": "ö"}]


def test_decoder_handles_several_lines_in_one_chunk():
    decoder = LineDecoder()
    data = encode(make_message("a")) + encode(make_message("b"))
    assert [m["type"] for m in decoder.feed(data)] == ["a", "b"]


def test_decoder_skips_invalid_lines():
    decoder = LineDecoder()
    data = b"not json\n" + b"[1, 2]\n" + b'{"no_type": 1}\n' + encode(make_message("ok"))
    assert decoder.feed(data) == [{"type": "ok"}]
    assert decoder.invalid == 3


def test_decoder_ignores_empty_lines():
    decoder = LineDecoder()
    assert decoder.feed(b"\n\r\n" + encode(make_message("ok"))) == [{"type": "ok"}]
    assert decoder.invalid == 0


def test_decoder_drops_overlong_line_and_recovers():
    decoder = LineDecoder(max_line=100)
    assert decoder.feed(b"x" * 150) == []
    assert decoder.feed(b"x" * 50 + b"\n" + encode(make_message("ok"))) == [{"type": "ok"}]
    assert decoder.invalid == 1


def test_check_hello():
    assert protocol.check_hello(make_message("hello", token="t", version=protocol.VERSION), "t")
    assert not protocol.check_hello(make_message("hello", token="wrong", version=protocol.VERSION), "t")
    assert not protocol.check_hello(make_message("hello", version=protocol.VERSION), "t")
    assert not protocol.check_hello(make_message("listen", token="t"), "t")
    assert not protocol.check_hello(make_message("hello", token="t", version=protocol.VERSION + 1), "t")
