from __future__ import annotations

import re

TRIPWIRE_PROVIDER = "tripwire"
TRIPWIRE_PROMPT_VERSION = "sirius-tripwire-v1"
TRIPWIRE_CONTEXT_HASH = "tripwire-no-context"
CRISIS_CATEGORY = "crisis_self_harm"

CRISIS_RESPONSE = (
    "Похоже, тебе сейчас непросто. Пожалуйста, не оставайся с этим один на "
    "один: расскажи взрослому, которому доверяешь, — родителю, учителю или "
    "организатору рядом. Можно бесплатно и анонимно позвонить на телефон "
    "доверия для детей и подростков: 8-800-2000-122 (круглосуточно). "
    "Я всего лишь помощник по задачам и не заменю живого разговора."
)

_CRISIS_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"суицид",
        r"самоубий",
        r"самоповрежд",
        r"селфхарм",
        r"self[\s-]?harm",
        r"поконч\w*\s+с\s+собой",
        r"убь\w*\s+себя",
        r"убить\s+себя",
        r"не\s+хо(?:чу|чется)\s+(?:больше\s+)?жить",
        r"хо(?:чу|чется)\s+умереть",
        r"свести\s+счеты\s+с\s+жизнью",
        r"свожу\s+счеты\s+с\s+жизнью",
        r"(?:вскро\w*|порез\w*|режу)\s+(?:себе\s+)?вены",
    )
)


def _normalize(text: str) -> str:
    lowered = text.casefold().replace("ё", "е")
    return re.sub(r"\s+", " ", lowered)


def crisis_category(message: str) -> str | None:
    """Категория кризисного сообщения или None, если триггеров нет."""

    normalized = _normalize(message)
    for pattern in _CRISIS_PATTERNS:
        if pattern.search(normalized):
            return CRISIS_CATEGORY
    return None
