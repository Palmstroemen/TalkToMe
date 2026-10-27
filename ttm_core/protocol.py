# SPDX-License-Identifier: LGPL-2.1-or-later
"""Line-based JSON protocol between the FreeCAD addon and the speech service.

Every message is a JSON object with a "type" field, sent as one UTF-8 line.
See DESIGN.md, section 11.
"""

import hmac
import json

VERSION = 1


def make_message(type_, **fields):
    msg = {"type": type_}
    msg.update(fields)
    return msg


def encode(msg):
    return (json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def check_hello(msg, token):
    """True if msg is a hello of our protocol version carrying the right token."""
    if msg.get("type") != "hello" or msg.get("version") != VERSION:
        return False
    given = msg.get("token")
    return isinstance(given, str) and hmac.compare_digest(given, token)


class LineDecoder:
    """Turns a byte stream into messages. Invalid lines are skipped and counted."""

    def __init__(self, max_line=1_000_000):
        self.max_line = max_line
        self.invalid = 0
        self._buffer = b""
        self._discarding = False     # inside an overlong line, skip up to the next newline

    def feed(self, data):
        self._buffer += data
        messages = []
        while True:
            end = self._buffer.find(b"\n")
            if end < 0:
                break
            line, self._buffer = self._buffer[:end], self._buffer[end + 1:]
            if self._discarding:
                self._discarding = False
                continue
            msg = self._parse(line)
            if msg is not None:
                messages.append(msg)
        if len(self._buffer) > self.max_line:
            self._buffer = b""
            if not self._discarding:
                self._discarding = True
                self.invalid += 1
        return messages

    def _parse(self, line):
        line = line.strip()
        if not line:
            return None
        try:
            msg = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            msg = None
        if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
            self.invalid += 1
            return None
        return msg
