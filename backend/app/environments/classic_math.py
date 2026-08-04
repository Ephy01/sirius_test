"""Fixed, automatically judged classic-mathematics anchor tasks.

The first pilot deliberately keeps these tasks scripted: their wording and
reference mathematics are versioned content, not LLM output.  The evaluator
checks an exact machine-readable conclusion and only the presence (not the
mathematical validity) of the participant's reasoning.
"""

from __future__ import annotations

import re
from typing import Any

FAMILY_KEY = "classic_math"
GENERATOR_VERSION = "classic-math-v1"
PUBLIC_KIND = "classic_math_free_response"

SHARE_PARADOX = "share_paradox"
BAR_SEATING = "bar_seating"
SUB_KINDS = frozenset({SHARE_PARADOX, BAR_SEATING})

JUDGE_VERSION = "classic-math-conclusion-v2"

_ANSWER_PREFIX = re.compile(r"^\s*/answer(?:\s+|$)", re.IGNORECASE)
_SHARE_CONCLUSION = re.compile(
    r"\s*сравнения\s*:\s*"
    r"5\s*/\s*6\s*>\s*8\s*/\s*10\s*;\s*"
    r"6\s*/\s*14\s*>\s*4\s*/\s*10\s*;\s*"
    r"11\s*/\s*20\s*<\s*12\s*/\s*20\s*",
    re.IGNORECASE,
)
_BAR_CONCLUSION = re.compile(
    r"\s*ответ\s*:\s*первое\s+место\s*(?:=|:|-)?\s*(9|17)\s*;\s*"
    r"максимум\s*(?:=|:|-)?\s*13\s*",
    re.IGNORECASE,
)
_REASONING_MARKER = re.compile(r"\bобоснование\s*:", re.IGNORECASE)


def _clean_answer(answer: str) -> str:
    return _ANSWER_PREFIX.sub("", answer, count=1).strip()


def _submission_parts(answer: str) -> tuple[str, str]:
    """Split conclusion and reasoning around the explicit marker.

    The participant console currently uses a one-line input, so a newline is
    optional.  ``Обоснование:`` is the stable boundary in both forms.
    """

    cleaned = _clean_answer(answer)
    marker = _REASONING_MARKER.search(cleaned)
    if marker is None:
        return "", ""
    conclusion = cleaned[: marker.start()].strip()
    reasoning = cleaned[marker.end() :].strip()
    return conclusion, reasoning


def _reasoning_supplied(reasoning: str) -> bool:
    # We intentionally do not claim semantic proof checking.  Six tokens keep
    # an empty or one-word placeholder from receiving the binary score while
    # still allowing concise ninth-grade arguments.
    return len(re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", reasoning)) >= 6


def _selected_sub_kind(context: dict[str, Any] | None) -> str:
    if not isinstance(context, dict):
        raise ValueError("classic_math requires a configured sub_kind")
    direct = context.get("sub_kind")
    if isinstance(direct, str) and direct in SUB_KINDS:
        return direct
    configured = context.get("sub_kinds")
    if isinstance(configured, list) and len(configured) == 1:
        selected = configured[0]
        if isinstance(selected, str) and selected in SUB_KINDS:
            return selected
    raise ValueError("classic_math sub_kind is not supported")


def generate_classic_math_task(
    *,
    seed: int,
    difficulty: int,
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return one of the two versioned fixed tasks selected by contest config."""

    del seed  # Fixed pilot content is intentionally independent of randomness.
    if isinstance(difficulty, bool) or difficulty < 1:
        raise ValueError("classic_math difficulty must be positive")
    sub_kind = _selected_sub_kind(context)

    if sub_kind == SHARE_PARADOX:
        title = "Доли и объединение данных"
        submission_template = (
            "/answer Сравнения: <месяц 1>; <месяц 2>; <вместе> "
            "Обоснование: <не менее одного полного предложения>"
        )
        prompt = (
            "Два программиста, Егор и Вася, сравнили долю "
            "закрытых задач "
            "за два месяца.\n\n"
            "В первый месяц Егор закрыл 5 задач из 6, "
            "а Вася — 8 из 10. "
            "Во второй месяц Егор закрыл 6 задач из 14, "
            "а Вася — 4 из 10. "
            "За два месяца вместе Егор закрыл 11 задач из 20, "
            "а Вася — "
            "12 из 20.\n\n"
            "В каждом отдельном месяце доля Егора выше, но за два "
            "месяца вместе доля Васи выше. Объясните, почему здесь "
            "нет противоречия. Покажите вычисления и объясните роль "
            "распределения задач между месяцами. Одного названия "
            "известного "
            "парадокса недостаточно.\n\n"
            "Отправьте ответ одной строкой: «/answer Сравнения: "
            "<месяц 1>; <месяц 2>; <вместе> Обоснование: "
            "<ваше объяснение>»."
        )
        public_extra: dict[str, Any] = {
            "table": {
                "columns": ["Период", "Егор", "Вася"],
                "rows": [
                    ["Первый месяц", "5 из 6", "8 из 10"],
                    ["Второй месяц", "6 из 14", "4 из 10"],
                    ["Два месяца вместе", "11 из 20", "12 из 20"],
                ],
            }
        }
    else:
        title = "Рассадка вдоль стойки"
        submission_template = (
            "/answer Ответ: первое место <номер>; максимум <число> "
            "Обоснование: <не менее одного полного предложения>"
        )
        prompt = (
            "Вдоль прямой барной стойки расположены 25 мест, "
            "пронумерованных от 1 до 25. Бармен назначает место "
            "первому "
            "посетителю.\n\n"
            "Пусть некоторые места уже заняты. Для каждого "
            "свободного места x определим расстояние до ближайшего "
            "занятого места: d(x) = min |x - s|, где s пробегает "
            "номера занятых мест.\n\n"
            "Каждый следующий посетитель выбирает свободное место "
            "с наибольшим d(x). Если таких мест несколько, он может "
            "выбрать любое. Если наибольшее значение равно 1, "
            "посетитель уходит.\n\n"
            "Укажите хотя бы одно место для первого посетителя, "
            "при котором в итоге сядет максимально возможное число "
            "людей. Найдите это число и докажите оптимальность. "
            "Ответ должен оставаться верным "
            "при любом выборе между равноудалёнными местами.\n\n"
            "Отправьте ответ одной строкой: «/answer Ответ: первое место "
            "<номер>; максимум <число> Обоснование: "
            "<ваше доказательство>»."
        )
        public_extra = {"seat_count": 25}

    public = {
        "kind": PUBLIC_KIND,
        "family": FAMILY_KEY,
        "sub_kind": sub_kind,
        "title": title,
        "prompt": prompt,
        "response_hint": (
            "Отправьте шаблон одной строкой. Итог до маркера "
            "«Обоснование:» проверяется точно; объяснение обязательно."
        ),
        "submission_template": submission_template,
        "answer_format": "free_response",
        "scripted": True,
        **public_extra,
    }
    private = {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "difficulty": difficulty,
        "sub_kind": sub_kind,
        "judge_version": JUDGE_VERSION,
    }
    return public, private


def evaluate_classic_math_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    sub_kind = private_state.get("sub_kind")
    conclusion, reasoning = _submission_parts(answer)
    if sub_kind == SHARE_PARADOX:
        conclusion_valid = _SHARE_CONCLUSION.fullmatch(conclusion) is not None
    elif sub_kind == BAR_SEATING:
        conclusion_valid = _BAR_CONCLUSION.fullmatch(conclusion) is not None
    else:
        raise ValueError("classic_math task has an unsupported sub_kind")

    checks = {
        "conclusion_valid": conclusion_valid,
        "reasoning_supplied": _reasoning_supplied(reasoning),
    }
    correct = all(checks.values())
    if correct:
        result_status = "correct"
    elif not conclusion_valid:
        result_status = "incorrect"
    else:
        result_status = "incomplete_reasoning"
    return {
        "accepted": True,
        "correct": correct,
        "should_finalize": True,
        "continuous_score": 1.0 if correct else 0.0,
        "result_status": result_status,
        "judge_version": JUDGE_VERSION,
        "conclusion_checks": checks,
        "reasoning_checked": False,
        "scoring_basis": "exact_conclusion_and_reasoning_presence",
    }
