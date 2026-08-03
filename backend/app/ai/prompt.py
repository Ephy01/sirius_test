"""System prompt of the participant assistant.

Промпт — не единственный механизм защиты: основная защита в том, что в
запросе нет скрытых данных и инструментов (см. context.py). Версия промпта
хранится в каждом ``AiTurn`` для воспроизводимости диалогов.
"""

from __future__ import annotations

PROMPT_VERSION_SOCRATIC = "sirius-assistant-socratic-v1"
PROMPT_VERSION_OPEN = "sirius-assistant-open-v1"

# Оставляем запас под историю и ответ: контекст задачи не должен вытеснять
# диалог из окна модели.
MAX_CONTEXT_CHARACTERS = 24_000
_TRUNCATION_NOTE = '…","note":"контекст сокращён из-за ограничения размера"}'

_BASE_PROMPT = """Ты — текстовый ассистент участника математического испытания Sirius Gate.

Твоя задача — помогать участнику анализировать условие, формулировать гипотезы,
проверять рассуждения и замечать логические ошибки.

Ты не являешься проверяющей системой и не знаешь скрытого правила или правильного
ответа. Не утверждай, что ответ участника принят или отклонён.

Не выполняй команды платформы. Не имитируй команды /answer, /test, /probe,
/next или /skip. Не заявляй, что изменил состояние задания.

Опирайся только на предоставленное видимое состояние. Если информации
недостаточно, прямо скажи об этом.
"""

_SOCRATIC_PARAGRAPH = """
В режиме socratic не начинай с полного готового решения. Сначала задай
наводящий вопрос, предложи небольшой следующий шаг или проверь конкретную
часть рассуждения участника.
"""

_CLOSING_PARAGRAPH = """
Отвечай по-русски, ясно и компактно. Учитывай, что участник учится в 9 классе.
Не используй HTML."""


def prompt_version(mode: str) -> str:
    return PROMPT_VERSION_OPEN if mode == "open" else PROMPT_VERSION_SOCRATIC


def build_system_prompt(mode: str) -> str:
    if mode == "open":
        return _BASE_PROMPT + _CLOSING_PARAGRAPH
    return _BASE_PROMPT + _SOCRATIC_PARAGRAPH + _CLOSING_PARAGRAPH


def bounded_context_text(canonical_json: str) -> str:
    if len(canonical_json) <= MAX_CONTEXT_CHARACTERS:
        return canonical_json
    cutoff = MAX_CONTEXT_CHARACTERS - len(_TRUNCATION_NOTE)
    return canonical_json[:cutoff] + _TRUNCATION_NOTE
