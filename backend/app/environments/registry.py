from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .chess_world.chess960 import (
    FAMILY_KEY as CHESS960_FAMILY,
    GENERATOR_VERSION as CHESS960_GENERATOR_VERSION,
    LEGACY_GENERATOR_VERSION as CHESS960_LEGACY_GENERATOR_VERSION,
    evaluate_chess960_answer,
    evaluate_chess960_validation_answer,
    generate_chess960_task,
    generate_chess960_validation_task,
)
from .chess_world.dice_chess import (
    GENERATOR_VERSION as DICE_CHESS_PROBABILITY_GENERATOR_VERSION,
    evaluate_dice_chess_answer,
    generate_dice_chess_task,
)
from .chess_world.dice_chess_mission import (
    GENERATOR_VERSION as DICE_CHESS_LEGACY_MISSION_GENERATOR_VERSION,
    evaluate_dice_chess_mission_answer,
    generate_dice_chess_mission_task,
)
from .chess_world.dice_chess_world import (
    FAMILY_KEY as DICE_CHESS_FAMILY,
    GENERATOR_VERSION as DICE_CHESS_GENERATOR_VERSION,
    evaluate_dice_chess_world_answer,
    generate_dice_chess_world_task,
)
from .chess_world.dice_chess_position import (
    GENERATOR_VERSION as DICE_CHESS_POSITION_GENERATOR_VERSION,
    evaluate_dice_chess_position_answer,
    generate_dice_chess_position_task,
)
from .chess_world.penultima import (
    FAMILY_KEY as PENULTIMA_FAMILY,
    GENERATOR_VERSION as PENULTIMA_GENERATOR_VERSION,
    PenultimaTransition,
    generate_penultima_task,
    transition_penultima_move,
)
from .geometry_world import (
    GENERATOR_VERSION as GEOMETRY_GENERATOR_VERSION,
    GEO_GRAPH_FAMILY,
    GEO_PROBABILITY_FAMILY,
    GEO_TRANSFORM_FAMILY,
    GEO_ZENDO_FAMILY,
    SUPPORTED_FAMILIES as GEOMETRY_FAMILIES,
    evaluate_geometry_atlas_answer,
    generate_geometry_atlas_task,
    transition_geo_zendo_probe,
)

IMPLEMENTED_FAMILIES = frozenset(
    {CHESS960_FAMILY, DICE_CHESS_FAMILY, PENULTIMA_FAMILY, *GEOMETRY_FAMILIES}
)
INTERACTIVE_FAMILIES = frozenset({PENULTIMA_FAMILY, GEO_ZENDO_FAMILY})
GENERATOR_VERSIONS = {
    CHESS960_FAMILY: CHESS960_GENERATOR_VERSION,
    DICE_CHESS_FAMILY: DICE_CHESS_GENERATOR_VERSION,
    PENULTIMA_FAMILY: PENULTIMA_GENERATOR_VERSION,
    **{family: GEOMETRY_GENERATOR_VERSION for family in GEOMETRY_FAMILIES},
}


@dataclass(frozen=True)
class GeneratedTask:
    public_state: dict[str, Any]
    private_state: dict[str, Any]


@dataclass(frozen=True)
class InteractionTransition:
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    accepted: bool
    completed: bool
    reason: str
    message: str
    normalized_input: str
    evaluation_state: dict[str, Any] | None


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


def generator_version_for(family: str) -> str:
    try:
        return GENERATOR_VERSIONS[family]
    except KeyError as error:
        raise ValueError(f"Unsupported task family: {family!r}") from error


def generate_task(
    *,
    family: str,
    generator_version: str,
    seed: int,
    difficulty: int,
    context: dict[str, Any] | None = None,
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
    if (
        family == CHESS960_FAMILY
        and generator_version == CHESS960_LEGACY_GENERATOR_VERSION
    ):
        public_state, private_state = generate_chess960_validation_task(
            seed=seed,
            difficulty=difficulty,
        )
        return GeneratedTask(
            public_state=public_state,
            private_state=private_state,
        )
    if family == DICE_CHESS_FAMILY and generator_version == DICE_CHESS_GENERATOR_VERSION:
        public_state, private_state = generate_dice_chess_world_task(
            seed=seed,
            difficulty=difficulty,
        )
        return GeneratedTask(
            public_state=public_state,
            private_state=private_state,
        )
    if (
        family == DICE_CHESS_FAMILY
        and generator_version == DICE_CHESS_LEGACY_MISSION_GENERATOR_VERSION
    ):
        public_state, private_state = generate_dice_chess_mission_task(
            seed=seed,
            difficulty=difficulty,
        )
        return GeneratedTask(
            public_state=public_state,
            private_state=private_state,
        )
    if (
        family == DICE_CHESS_FAMILY
        and generator_version == DICE_CHESS_PROBABILITY_GENERATOR_VERSION
    ):
        public_state, private_state = generate_dice_chess_task(
            seed=seed,
            difficulty=difficulty,
        )
        return GeneratedTask(
            public_state=public_state,
            private_state=private_state,
        )
    if (
        family == DICE_CHESS_FAMILY
        and generator_version == DICE_CHESS_POSITION_GENERATOR_VERSION
    ):
        public_state, private_state = generate_dice_chess_position_task(
            seed=seed,
            difficulty=difficulty,
        )
        return GeneratedTask(
            public_state=public_state,
            private_state=private_state,
        )
    if family == PENULTIMA_FAMILY and generator_version == PENULTIMA_GENERATOR_VERSION:
        public_state, private_state = generate_penultima_task(
            seed=seed,
            difficulty=difficulty,
            context=context,
        )
        return GeneratedTask(
            public_state=public_state,
            private_state=private_state,
        )
    if family in GEOMETRY_FAMILIES and generator_version == GEOMETRY_GENERATOR_VERSION:
        public_state, private_state = generate_geometry_atlas_task(
            family=family,
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
    if (
        family == CHESS960_FAMILY
        and generator_version == CHESS960_LEGACY_GENERATOR_VERSION
    ):
        return evaluate_chess960_validation_answer(
            answer=answer,
            private_state=private_state,
        )
    if family == DICE_CHESS_FAMILY and generator_version == DICE_CHESS_GENERATOR_VERSION:
        return evaluate_dice_chess_world_answer(
            answer=answer,
            private_state=private_state,
        )
    if (
        family == DICE_CHESS_FAMILY
        and generator_version == DICE_CHESS_LEGACY_MISSION_GENERATOR_VERSION
    ):
        return evaluate_dice_chess_mission_answer(
            answer=answer,
            private_state=private_state,
        )
    if (
        family == DICE_CHESS_FAMILY
        and generator_version == DICE_CHESS_PROBABILITY_GENERATOR_VERSION
    ):
        return evaluate_dice_chess_answer(answer=answer, private_state=private_state)
    if (
        family == DICE_CHESS_FAMILY
        and generator_version == DICE_CHESS_POSITION_GENERATOR_VERSION
    ):
        return evaluate_dice_chess_position_answer(
            answer=answer,
            private_state=private_state,
        )
    if family in GEOMETRY_FAMILIES and generator_version == GEOMETRY_GENERATOR_VERSION:
        return evaluate_geometry_atlas_answer(
            family=family,
            answer=answer,
            private_state=private_state,
        )
    raise ValueError(
        f"Unsupported task evaluator: family={family!r}, version={generator_version!r}"
    )


def interact_task(
    *,
    family: str,
    generator_version: str,
    action_type: str,
    action_payload: dict[str, Any],
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> InteractionTransition:
    if (
        family == PENULTIMA_FAMILY
        and generator_version == PENULTIMA_GENERATOR_VERSION
        and action_type == "move"
    ):
        move = action_payload.get("move")
        if not isinstance(move, str):
            raise ValueError("Penultima move payload must contain a string move")
        transition: PenultimaTransition = transition_penultima_move(
            move=move,
            public_state=public_state,
            private_state=private_state,
        )
        return InteractionTransition(
            public_state=transition.public_state,
            private_state=transition.private_state,
            accepted=transition.accepted,
            completed=transition.completed,
            reason=transition.reason,
            message=transition.message,
            normalized_input=transition.normalized_move,
            evaluation_state=transition.evaluation_state,
        )
    if (
        family == GEO_ZENDO_FAMILY
        and generator_version == GEOMETRY_GENERATOR_VERSION
        and action_type == "probe"
    ):
        probe = action_payload.get("probe")
        if not isinstance(probe, str):
            raise ValueError("Geometry probe payload must contain a string probe")
        transition = transition_geo_zendo_probe(
            card_id=probe,
            public_state=public_state,
            private_state=private_state,
        )
        return InteractionTransition(
            public_state=transition.public_state,
            private_state=transition.private_state,
            accepted=transition.accepted,
            completed=False,
            reason=transition.reason,
            message=transition.message,
            normalized_input=probe.strip().upper(),
            evaluation_state=None,
        )
    raise ValueError(
        "Unsupported task interaction: "
        f"family={family!r}, version={generator_version!r}, action={action_type!r}"
    )
