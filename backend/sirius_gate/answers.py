"""Reading the answer a participant typed."""

from __future__ import annotations

import re


def text(answer: str) -> str:
    """The answer in lower case without the ``/answer`` command and outer spaces."""

    return re.sub(r'^\s*/?answer\b', '', answer.strip().casefold()).strip()


def integer(answer: str) -> int | None:
    """The integer a participant sent, with or without the ``/answer`` command."""

    digits = text(answer).replace('\u2212', '-').replace(' ', '')
    return int(digits) if re.fullmatch(r'[+-]?\d{1,18}', digits) else None
