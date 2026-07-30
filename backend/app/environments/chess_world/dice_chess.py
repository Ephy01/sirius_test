from __future__ import annotations

import itertools
import random
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from math import prod
from typing import Any

FAMILY_KEY = "dice_chess"
GENERATOR_VERSION = "dice-chess-probability-v1"

PIECE_CODES = ("K", "Q", "R", "B", "N", "P")
PIECE_LABELS = {
    "K": "король",
    "Q": "ферзь",
    "R": "ладья",
    "B": "слон",
    "N": "конь",
    "P": "пешка",
}
ANSWER_TOLERANCE = Fraction(1, 200)


@dataclass(frozen=True)
class DiceEvent:
    event_type: str
    targets: tuple[str, ...]
    exact_count: int | None
    favorable_outcomes: int
    total_outcomes: int
    probability: Fraction


def calculate_event_probability(
    *,
    dice_faces: tuple[tuple[str, ...], ...],
    event_type: str,
    targets: tuple[str, ...],
    exact_count: int | None = None,
) -> tuple[int, int, Fraction]:
    """Calculate exact probability by enumerating the finite outcome space."""

    def matches(outcome: tuple[str, ...]) -> bool:
        if event_type == "at_least_one":
            return targets[0] in outcome
        if event_type == "exactly_k":
            return outcome.count(targets[0]) == exact_count
        if event_type == "contains_both":
            return all(target in outcome for target in targets)
        raise ValueError(f"Unsupported Dice & Chess event: {event_type!r}")

    total_outcomes = prod(len(faces) for faces in dice_faces)
    favorable_outcomes = sum(
        1 for outcome in itertools.product(*dice_faces) if matches(outcome)
    )
    probability = Fraction(favorable_outcomes, total_outcomes)
    return favorable_outcomes, total_outcomes, probability


def _generate_dice_faces(
    rng: random.Random,
    dice_count: int,
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(rng.choice(PIECE_CODES) for _ in range(6))
        for _ in range(dice_count)
    )


def _nontrivial_events(
    dice_faces: tuple[tuple[str, ...], ...],
    available_event_types: tuple[str, ...],
) -> dict[str, list[DiceEvent]]:
    pieces = sorted(set(itertools.chain.from_iterable(dice_faces)))
    candidate_specs: list[tuple[str, tuple[str, ...], int | None]] = []
    if "at_least_one" in available_event_types:
        candidate_specs.extend(
            ("at_least_one", (piece,), None)
            for piece in pieces
        )
    if "exactly_k" in available_event_types:
        candidate_specs.extend(
            ("exactly_k", (piece,), exact_count)
            for piece in pieces
            for exact_count in range(1, len(dice_faces) + 1)
        )
    if "contains_both" in available_event_types:
        candidate_specs.extend(
            ("contains_both", pair, None)
            for pair in itertools.combinations(pieces, 2)
        )

    by_type = {event_type: [] for event_type in available_event_types}
    for event_type, targets, exact_count in candidate_specs:
        favorable, total, probability = calculate_event_probability(
            dice_faces=dice_faces,
            event_type=event_type,
            targets=targets,
            exact_count=exact_count,
        )
        if 0 < probability < 1:
            by_type[event_type].append(
                DiceEvent(
                    event_type=event_type,
                    targets=targets,
                    exact_count=exact_count,
                    favorable_outcomes=favorable,
                    total_outcomes=total,
                    probability=probability,
                )
            )
    return {event_type: events for event_type, events in by_type.items() if events}


def _piece_description(piece: str) -> str:
    return f"{piece} — {PIECE_LABELS[piece]}"


def generate_dice_chess_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(seed)
    dice_count = 2 + min(2, max(0, (difficulty - 1) // 3))

    available_events = ["at_least_one"]
    if difficulty >= 2:
        available_events.append("exactly_k")
    if difficulty >= 3:
        available_events.append("contains_both")
    available_event_types = tuple(available_events)

    for _ in range(32):
        dice_faces = _generate_dice_faces(rng, dice_count)
        events_by_type = _nontrivial_events(dice_faces, available_event_types)
        if events_by_type:
            break
    else:
        # Formal fallback: at least one K has probability 1/6, regardless of
        # dice_count. It is reached only if every deterministic retry was
        # degenerate.
        dice_faces = (
            ("K", "Q", "Q", "Q", "Q", "Q"),
            *(("R", "R", "R", "R", "R", "R"),) * (dice_count - 1),
        )
        events_by_type = _nontrivial_events(dice_faces, available_event_types)

    event_type = rng.choice(sorted(events_by_type))
    selected_event = rng.choice(events_by_type[event_type])
    targets = selected_event.targets
    exact_count = selected_event.exact_count

    if event_type == "contains_both":
        event_description = (
            "Среди выпавших граней встретятся обе фигуры: "
            f"«{_piece_description(targets[0])}» и "
            f"«{_piece_description(targets[1])}»."
        )
    else:
        target = targets[0]
        if event_type == "at_least_one":
            event_description = (
                "Среди выпавших граней будет хотя бы одна "
                "фигура "
                f"«{_piece_description(target)}»."
            )
        else:
            event_description = (
                f"Ровно на {exact_count} из {dice_count} кубиков "
                "выпадет фигура "
                f"«{_piece_description(target)}»."
            )

    favorable = selected_event.favorable_outcomes
    total = selected_event.total_outcomes
    probability = selected_event.probability
    public_state: dict[str, Any] = {
        "kind": "dice_chess_probability",
        "prompt": (
            f"Одновременно бросают {dice_count} независимых "
            "шестигранных кубика. При броске каждого "
            "кубика выпадает ровно одна грань, и все его "
            "грани равновероятны. "
            "Найдите вероятность описанного события."
        ),
        "dice": [
            {
                "id": f"die-{index}",
                "label": f"Кубик {index}",
                "faces": list(faces),
            }
            for index, faces in enumerate(dice_faces, start=1)
        ],
        "sample_space_size": total,
        "event_description": event_description,
        "response_hint": (
            "Введите вероятность сокращённой дробью a/b, "
            "десятичным числом "
            "или в процентах."
        ),
    }
    private_state: dict[str, Any] = {
        "event_type": event_type,
        "targets": list(targets),
        "exact_count": exact_count,
        "favorable_outcomes": favorable,
        "total_outcomes": total,
        "probability": {
            "numerator": probability.numerator,
            "denominator": probability.denominator,
        },
        "difficulty": difficulty,
    }
    return public_state, private_state


def parse_probability_answer(answer: str) -> Fraction | None:
    normalized = answer.strip().replace("\u00a0", " ")

    fraction_match = re.search(
        r"(?<![\d.,])([+-]?\d+)\s*/\s*(\d+)(?![\d.,])",
        normalized,
    )
    if fraction_match:
        denominator = int(fraction_match.group(2))
        if denominator == 0:
            return None
        return Fraction(int(fraction_match.group(1)), denominator)

    percent_match = re.search(
        r"(?<![\d.,])([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))\s*%",
        normalized,
    )
    if percent_match:
        try:
            value = Decimal(percent_match.group(1).replace(",", "."))
        except InvalidOperation:
            return None
        return Fraction(value) / 100

    number_matches = re.finditer(
        r"(?<![\d.,/])([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))(?![\d.,/])",
        normalized,
    )
    for number_match in number_matches:
        try:
            value = Fraction(
                Decimal(number_match.group(1).replace(",", "."))
            )
        except InvalidOperation:
            continue
        if 0 <= value <= 1:
            return value
    return None


def evaluate_dice_chess_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    parsed_probability = parse_probability_answer(answer)
    expected_data = private_state["probability"]
    expected_probability = Fraction(
        int(expected_data["numerator"]),
        int(expected_data["denominator"]),
    )
    in_range = (
        parsed_probability is not None
        and Fraction(0) <= parsed_probability <= Fraction(1)
    )
    error = (
        abs(parsed_probability - expected_probability)
        if parsed_probability is not None and in_range
        else None
    )
    return {
        "correct": error is not None and error <= ANSWER_TOLERANCE,
        "parsed": in_range,
        "submitted_probability": (
            {
                "numerator": parsed_probability.numerator,
                "denominator": parsed_probability.denominator,
            }
            if parsed_probability is not None and in_range
            else None
        ),
        "absolute_error": (
            {"numerator": error.numerator, "denominator": error.denominator}
            if error is not None
            else None
        ),
    }
