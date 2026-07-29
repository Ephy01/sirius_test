from __future__ import annotations

import random
import re
from collections import Counter
from typing import Any

FAMILY_KEY = "chess960"
GENERATOR_VERSION = "chess960-validation-v1"

EXPECTED_PIECES = Counter("RNBQKBNR")


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


def generate_chess960_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
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


def evaluate_chess960_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    predicted_valid = _classify_validity_answer(answer)
    expected_valid = bool(private_state["is_valid"])
    return {
        "correct": predicted_valid is not None and predicted_valid == expected_valid,
        "parsed": predicted_valid is not None,
        "predicted_valid": predicted_valid,
    }
