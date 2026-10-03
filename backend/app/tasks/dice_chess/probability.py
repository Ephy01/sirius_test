"""Parsing and scoring of probability answers for dice_chess tasks."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

PIECE_CODES = ('K', 'Q', 'R', 'B', 'N', 'P')
ANSWER_TOLERANCE = Fraction(1, 200)


def parse_probability_answer(answer: str) -> Fraction | None:
    normalized = answer.strip().replace('\u00a0', ' ')

    fraction_match = re.search(r'(?<![\d.,])([+-]?\d+)\s*/\s*(\d+)(?![\d.,])', normalized)
    if fraction_match:
        denominator = int(fraction_match.group(2))
        if denominator == 0:
            return None
        return Fraction(int(fraction_match.group(1)), denominator)

    percent_match = re.search(r'(?<![\d.,])([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))\s*%', normalized)
    if percent_match:
        try:
            value = Decimal(percent_match.group(1).replace(',', '.'))
        except InvalidOperation:
            return None
        return Fraction(value) / 100

    number_matches = re.finditer(r'(?<![\d.,/])([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))(?![\d.,/])', normalized)
    for number_match in number_matches:
        try:
            value = Fraction(Decimal(number_match.group(1).replace(',', '.')))
        except InvalidOperation:
            continue
        if 0 <= value <= 1:
            return value
    return None


def evaluate_dice_chess_answer(*, answer: str, private_state: dict[str, Any]) -> dict[str, Any]:
    parsed_probability = parse_probability_answer(answer)
    expected_data = private_state['probability']
    expected_probability = Fraction(int(expected_data['numerator']), int(expected_data['denominator']))
    in_range = parsed_probability is not None and Fraction(0) <= parsed_probability <= Fraction(1)
    error = (
        abs(parsed_probability - expected_probability)
        if parsed_probability is not None and in_range
        else None
    )
    return {
        'correct': error is not None and error <= ANSWER_TOLERANCE,
        'parsed': in_range,
        'submitted_probability': (
            {'numerator': parsed_probability.numerator, 'denominator': parsed_probability.denominator}
            if parsed_probability is not None and in_range
            else None
        ),
        'absolute_error': (
            {'numerator': error.numerator, 'denominator': error.denominator} if error is not None else None
        ),
    }
