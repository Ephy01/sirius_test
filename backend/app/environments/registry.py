from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .chess_world.chess960 import (
    FAMILY_KEY as CHESS960_FAMILY,
    GENERATOR_VERSION as CHESS960_GENERATOR_VERSION,
    evaluate_chess960_answer,
    generate_chess960_task,
)


@dataclass(frozen=True)
class GeneratedTask:
    public_state: dict[str, Any]
    private_state: dict[str, Any]


def derive_task_seed(
    attempt_seed: int,
    ordinal: int,
    family: str,
    generator_version: str,
) -> int:
    """Derive a stable signed-64-bit-safe seed from the immutable task identity."""

    identity = json.dumps(
        [attempt_seed, ordinal, family, generator_version],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    digest = hashlib.sha256(identity).digest()
    return int.from_bytes(digest[:8], byteorder="big") & ((1 << 63) - 1)


def generate_task(
    *,
    family: str,
    generator_version: str,
    seed: int,
    difficulty: int,
) -> GeneratedTask:
    if family == CHESS960_FAMILY and generator_version == CHESS960_GENERATOR_VERSION:
        public_state, private_state = generate_chess960_task(
            seed=seed,
            difficulty=difficulty,
        )
        return GeneratedTask(
            public_state=public_state,
            private_state=private_state,
        )
    raise ValueError(
        f"Unsupported task generator: family={family!r}, version={generator_version!r}"
    )


def evaluate_task(
    *,
    family: str,
    generator_version: str,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    if family == CHESS960_FAMILY and generator_version == CHESS960_GENERATOR_VERSION:
        return evaluate_chess960_answer(answer=answer, private_state=private_state)
    raise ValueError(
        f"Unsupported task evaluator: family={family!r}, version={generator_version!r}"
    )
