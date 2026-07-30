from __future__ import annotations

import random
import re
from collections import Counter
from itertools import combinations
from typing import Any

FAMILY_KEY = "chess960"
GENERATOR_VERSION = "chess960-mission-v2"
LEGACY_GENERATOR_VERSION = "chess960-validation-v1"

EXPECTED_PIECES = Counter("RNBQKBNR")
FILES = "abcdefgh"
FILE_PAIRS = tuple(combinations(range(8), 2))
RULES_TEXT = (
    "В Chess960 слоны должны стоять на полях разного цвета, а король — "
    "между двумя ладьями."
)


def chess960_violations(back_rank: str) -> set[str]:
    """Return violated Chess960 starting-position invariants."""

    violations: set[str] = set()
    if len(back_rank) != 8 or Counter(back_rank) != EXPECTED_PIECES:
        return {"piece_set"}

    bishops = [index for index, piece in enumerate(back_rank) if piece == "B"]
    if bishops[0] % 2 == bishops[1] % 2:
        violations.add("bishops_same_color")

    king = back_rank.index("K")
    rooks = [index for index, piece in enumerate(back_rank) if piece == "R"]
    if not rooks[0] < king < rooks[1]:
        violations.add("king_not_between_rooks")
    return violations


def is_valid_chess960(back_rank: str) -> bool:
    return not chess960_violations(back_rank)


def _place_remaining_king_and_rooks(rank: list[str | None], remaining: list[int]) -> None:
    left_rook, king, right_rook = sorted(remaining)
    rank[left_rook] = "R"
    rank[king] = "K"
    rank[right_rook] = "R"


def _build_valid_back_rank(rng: random.Random) -> str:
    rank: list[str | None] = [None] * 8
    rank[rng.choice((0, 2, 4, 6))] = "B"
    rank[rng.choice((1, 3, 5, 7))] = "B"

    remaining = [index for index, piece in enumerate(rank) if piece is None]
    queen = rng.choice(remaining)
    rank[queen] = "Q"

    remaining = [index for index, piece in enumerate(rank) if piece is None]
    for knight in rng.sample(remaining, 2):
        rank[knight] = "N"

    remaining = [index for index, piece in enumerate(rank) if piece is None]
    _place_remaining_king_and_rooks(rank, remaining)
    return "".join(piece or "" for piece in rank)


def _build_same_color_bishops_rank(rng: random.Random) -> str:
    rank: list[str | None] = [None] * 8
    bishop_parity = rng.randrange(2)
    bishop_candidates = list(range(bishop_parity, 8, 2))
    for bishop in rng.sample(bishop_candidates, 2):
        rank[bishop] = "B"

    remaining = [index for index, piece in enumerate(rank) if piece is None]
    queen = rng.choice(remaining)
    rank[queen] = "Q"

    remaining = [index for index, piece in enumerate(rank) if piece is None]
    for knight in rng.sample(remaining, 2):
        rank[knight] = "N"

    remaining = [index for index, piece in enumerate(rank) if piece is None]
    _place_remaining_king_and_rooks(rank, remaining)
    return "".join(piece or "" for piece in rank)


def _build_king_outside_rooks_rank(rng: random.Random) -> str:
    rank = list(_build_valid_back_rank(rng))
    king = rank.index("K")
    rooks = [index for index, piece in enumerate(rank) if piece == "R"]
    rook_to_swap = rng.choice(rooks)
    rank[king], rank[rook_to_swap] = rank[rook_to_swap], rank[king]
    return "".join(rank)


def generate_chess960_validation_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate the legacy yes/no validation task."""

    rng = random.Random(seed)
    is_valid = rng.randrange(2) == 0
    violation: str | None = None

    if is_valid:
        back_rank = _build_valid_back_rank(rng)
    else:
        violation = rng.choice(("bishops_same_color", "king_not_between_rooks"))
        if violation == "bishops_same_color":
            back_rank = _build_same_color_bishops_rank(rng)
        else:
            back_rank = _build_king_outside_rooks_rank(rng)

    public_state: dict[str, Any] = {
        "kind": "chess960_validation",
        "prompt": (
            "В Chess960 слоны должны стоять на полях разного цвета, а король — "
            "между двумя ладьями. Определите, допустима ли показанная начальная "
            "расстановка."
        ),
        "back_rank": back_rank,
        "response_hint": (
            "Ответьте «да» или «нет»."
            if difficulty <= 1
            else "Ответьте «да» или «нет» и кратко назовите применённое правило."
        ),
    }
    private_state: dict[str, Any] = {
        "is_valid": is_valid,
        "violation": violation,
        "difficulty": difficulty,
    }
    return public_state, private_state


def _classify_validity_answer(answer: str) -> bool | None:
    normalized = " ".join(answer.casefold().split())
    negative_patterns = (
        r"\bнет\b",
        r"\bno\b",
        r"\binvalid\b",
        r"\bневерн\w*",
        r"\bнеправильн\w*",
        r"\bнедопустим\w*",
        r"\bне допустим\w*",
        r"\bне соответствует\b",
        r"\bнаруш\w*",
    )
    if any(re.search(pattern, normalized) for pattern in negative_patterns):
        return False

    positive_patterns = (
        r"\bда\b",
        r"\byes\b",
        r"\bvalid\b",
        r"\bверн\w*",
        r"\bправильн\w*",
        r"\bдопустим\w*",
        r"\bсоответствует\b",
    )
    if any(re.search(pattern, normalized) for pattern in positive_patterns):
        return True
    return None


def evaluate_chess960_validation_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate a legacy yes/no validation task."""

    predicted_valid = _classify_validity_answer(answer)
    expected_valid = bool(private_state["is_valid"])
    return {
        "correct": predicted_valid is not None and predicted_valid == expected_valid,
        "parsed": predicted_valid is not None,
        "predicted_valid": predicted_valid,
    }


def swap_back_rank_files(
    back_rank: str,
    first_file: int,
    second_file: int,
) -> str:
    """Return a rank with the pieces on two different files exchanged."""

    if len(back_rank) != 8:
        raise ValueError("A Chess960 back rank must contain exactly eight pieces")
    if first_file == second_file:
        raise ValueError("A repair must exchange two different files")
    if not 0 <= first_file < 8 or not 0 <= second_file < 8:
        raise ValueError("A file index must be between zero and seven")
    pieces = list(back_rank)
    pieces[first_file], pieces[second_file] = (
        pieces[second_file],
        pieces[first_file],
    )
    return "".join(pieces)


def enumerate_chess960_repairs(
    back_rank: str,
) -> tuple[tuple[str, str], ...]:
    """Enumerate every unordered file pair whose exchange makes the rank valid."""

    repairs: list[tuple[str, str]] = []
    for first_file, second_file in FILE_PAIRS:
        repaired = swap_back_rank_files(back_rank, first_file, second_file)
        if is_valid_chess960(repaired):
            repairs.append(
                (f"{FILES[first_file]}1", f"{FILES[second_file]}1")
            )
    return tuple(repairs)


def _repair_candidates(
    rng: random.Random,
) -> list[tuple[str, tuple[tuple[str, str], ...]]]:
    """Build deterministic, proven-repairable invalid positions."""

    candidates: dict[str, tuple[tuple[str, str], ...]] = {}
    for _ in range(96):
        valid_rank = _build_valid_back_rank(rng)
        first_file, second_file = rng.choice(FILE_PAIRS)
        invalid_rank = swap_back_rank_files(
            valid_rank,
            first_file,
            second_file,
        )
        if is_valid_chess960(invalid_rank):
            continue
        repairs = enumerate_chess960_repairs(invalid_rank)
        if repairs:
            candidates[invalid_rank] = repairs

    if candidates:
        return sorted(candidates.items())

    # The fallback is obtained from the valid classical back rank by exchanging
    # the pieces on b1 and c1, putting both bishops on squares of the same color.
    fallback_rank = "RBNQKBNR"
    fallback_repairs = enumerate_chess960_repairs(fallback_rank)
    if not fallback_repairs:
        raise RuntimeError("The Chess960 repair fallback must remain repairable")
    return [(fallback_rank, fallback_repairs)]


def _select_repair_candidate(
    *,
    rng: random.Random,
    difficulty: int,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    candidates = _repair_candidates(rng)
    repair_counts = sorted({len(repairs) for _rank, repairs in candidates})

    if difficulty <= 2:
        selected_count = repair_counts[-1]
    elif difficulty == 3:
        selected_count = repair_counts[len(repair_counts) // 2]
    else:
        selected_count = repair_counts[0]

    selected_pool = [
        candidate
        for candidate in candidates
        if len(candidate[1]) == selected_count
    ]
    return rng.choice(selected_pool)


def generate_chess960_mission_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate a repair or counting task for the current Chess960 mission.

    New missions deliberately start with an actionable single-swap repair
    instead of the old yes/no position validation.  The evaluator still
    accepts stored ``validation`` private states, and the legacy generator
    remains available under ``chess960-validation-v1``.
    """

    rng = random.Random(seed)
    back_rank, repairs = _select_repair_candidate(
        rng=rng,
        difficulty=difficulty,
    )
    serialized_repairs = [list(pair) for pair in repairs]

    if difficulty <= 4:
        public_state = {
            "kind": "chess960_mission",
            "variant": "single_swap_repair",
            "prompt": (
                f"{RULES_TEXT} "
                "Показанная расстановка не удовлетворяет правилам Chess960. "
                "Укажите два разных поля первой горизонтали, фигуры на которых "
                "нужно поменять местами, чтобы получить допустимую расстановку."
            ),
            "back_rank": back_rank,
            "response_hint": "Запишите два поля, например: a1 b1.",
        }
        variant = "single_swap_repair"
    else:
        public_state = {
            "kind": "chess960_mission",
            "variant": "repair_count",
            "prompt": (
                f"{RULES_TEXT} "
                "Показанная расстановка не удовлетворяет правилам Chess960. "
                "Сколько существует различных неупорядоченных пар полей первой "
                "горизонтали, обмен фигур на которых делает расстановку допустимой?"
            ),
            "back_rank": back_rank,
            "response_hint": "Введите одно целое число.",
        }
        variant = "repair_count"

    private_state = {
        "variant": variant,
        "difficulty": difficulty,
        "valid_repairs": serialized_repairs,
        "repair_count": len(repairs),
    }
    return public_state, private_state


REPAIR_ANSWER_PATTERN = re.compile(
    r"^\s*([a-hA-H])(?:1)?(?:\s*[-–—:]\s*|\s+)([a-hA-H])(?:1)?\s*$"
)


def parse_chess960_repair_answer(
    answer: str,
) -> tuple[str, str] | None:
    match = REPAIR_ANSWER_PATTERN.fullmatch(answer)
    if match is None:
        return None
    first = f"{match.group(1).casefold()}1"
    second = f"{match.group(2).casefold()}1"
    if first == second:
        return None
    return tuple(sorted((first, second)))


def _parse_repair_count_answer(answer: str) -> int | None:
    match = re.fullmatch(r"\s*(\d+)\s*", answer)
    return int(match.group(1)) if match is not None else None


def evaluate_chess960_mission_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    variant = str(private_state.get("variant") or "validation")
    if variant == "validation":
        return evaluate_chess960_validation_answer(
            answer=answer,
            private_state=private_state,
        )

    valid_repairs = {
        tuple(sorted((str(pair[0]), str(pair[1]))))
        for pair in private_state.get("valid_repairs", [])
        if isinstance(pair, (list, tuple)) and len(pair) == 2
    }
    if variant == "single_swap_repair":
        submitted_repair = parse_chess960_repair_answer(answer)
        return {
            "correct": (
                submitted_repair is not None
                and submitted_repair in valid_repairs
            ),
            "parsed": submitted_repair is not None,
            "submitted_repair": (
                list(submitted_repair)
                if submitted_repair is not None
                else None
            ),
        }

    if variant == "repair_count":
        submitted_count = _parse_repair_count_answer(answer)
        expected_count = int(private_state["repair_count"])
        return {
            "correct": (
                submitted_count is not None
                and submitted_count == expected_count
            ),
            "parsed": submitted_count is not None,
            "submitted_count": submitted_count,
        }

    raise ValueError(f"Unsupported Chess960 mission variant: {variant!r}")


def generate_chess960_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate the current Chess960 mission version."""

    return generate_chess960_mission_task(
        seed=seed,
        difficulty=difficulty,
    )


def evaluate_chess960_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate the current mission while accepting legacy validation state."""

    return evaluate_chess960_mission_answer(
        answer=answer,
        private_state=private_state,
    )
