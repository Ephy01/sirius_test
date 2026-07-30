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
    GENERATOR_VERSION as PENULTIMA_LEGACY_GENERATOR_VERSION,
    PenultimaTransition,
    generate_penultima_task as generate_legacy_penultima_task,
    transition_penultima_move as transition_legacy_penultima_move,
)
from .chess_world.penultima_v2 import (
    GENERATOR_VERSION as PENULTIMA_GENERATOR_VERSION,
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
from .geometry_world.zendo_v2 import (
    GENERATOR_VERSION as GEO_ZENDO_GENERATOR_VERSION,
    evaluate_geo_zendo_v2_answer,
    generate_geo_zendo_v2_task,
    transition_geo_zendo_v2_probe,
)
from .machines import (
    FAMILY_KEY as MACHINE_REACH_FAMILY,
    GENERATOR_VERSION as MACHINE_REACH_GENERATOR_VERSION,
    MachineTransition,
    evaluate_machine_answer,
    generate_machine_reach_task,
    transition_machine_action,
)
from .nim_like import (
    FAMILY_KEY as NIM_LIKE_FAMILY,
    GENERATOR_VERSION as NIM_LIKE_GENERATOR_VERSION,
    evaluate_nim_like_answer,
    generate_nim_like_task,
)

IMPLEMENTED_FAMILIES = frozenset(
    {
        CHESS960_FAMILY,
        DICE_CHESS_FAMILY,
        PENULTIMA_FAMILY,
        MACHINE_REACH_FAMILY,
        NIM_LIKE_FAMILY,
        *GEOMETRY_FAMILIES,
    }
)
INTERACTIVE_FAMILIES = frozenset(
    {PENULTIMA_FAMILY, GEO_ZENDO_FAMILY, MACHINE_REACH_FAMILY}
)
GENERATOR_VERSIONS = {
    CHESS960_FAMILY: CHESS960_GENERATOR_VERSION,
    DICE_CHESS_FAMILY: DICE_CHESS_GENERATOR_VERSION,
    PENULTIMA_FAMILY: PENULTIMA_GENERATOR_VERSION,
    MACHINE_REACH_FAMILY: MACHINE_REACH_GENERATOR_VERSION,
    NIM_LIKE_FAMILY: NIM_LIKE_GENERATOR_VERSION,
    **{
        family: (
            GEO_ZENDO_GENERATOR_VERSION
            if family == GEO_ZENDO_FAMILY
            else GEOMETRY_GENERATOR_VERSION
        )
        for family in GEOMETRY_FAMILIES
    },
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
    if (
        family == PENULTIMA_FAMILY
        and generator_version == PENULTIMA_LEGACY_GENERATOR_VERSION
    ):
        public_state, private_state = generate_legacy_penultima_task(
            seed=seed,
            difficulty=difficulty,
            context=context,
        )
        return GeneratedTask(
            public_state=public_state,
            private_state=private_state,
        )
    if (
        family == MACHINE_REACH_FAMILY
        and generator_version == MACHINE_REACH_GENERATOR_VERSION
    ):
        configured_sub_kinds = (
            context.get("sub_kinds")
            if isinstance(context, dict)
            else None
        )
        sub_kind = None
        if isinstance(configured_sub_kinds, list):
            candidates = [
                item for item in configured_sub_kinds if isinstance(item, str)
            ]
            if candidates:
                sub_kind = candidates[seed % len(candidates)]
        public_state, private_state = generate_machine_reach_task(
            seed=seed,
            difficulty=difficulty,
            sub_kind=sub_kind,
        )
        return GeneratedTask(
            public_state=public_state,
            private_state=private_state,
        )
    if (
        family == GEO_ZENDO_FAMILY
        and generator_version == GEO_ZENDO_GENERATOR_VERSION
    ):
        public_state, private_state = generate_geo_zendo_v2_task(
            seed=seed,
            difficulty=difficulty,
        )
        return GeneratedTask(
            public_state=public_state,
            private_state=private_state,
        )
    if family == NIM_LIKE_FAMILY and generator_version == NIM_LIKE_GENERATOR_VERSION:
        public_state, private_state = generate_nim_like_task(
            seed=seed,
            difficulty=difficulty,
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
    if (
        family == MACHINE_REACH_FAMILY
        and generator_version == MACHINE_REACH_GENERATOR_VERSION
    ):
        return evaluate_machine_answer(
            answer=answer,
            private_state=private_state,
        )
    if (
        family == GEO_ZENDO_FAMILY
        and generator_version == GEO_ZENDO_GENERATOR_VERSION
    ):
        return evaluate_geo_zendo_v2_answer(
            answer=answer,
            private_state=private_state,
        )
    if family == NIM_LIKE_FAMILY and generator_version == NIM_LIKE_GENERATOR_VERSION:
        return evaluate_nim_like_answer(
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
        family == PENULTIMA_FAMILY
        and generator_version == PENULTIMA_LEGACY_GENERATOR_VERSION
        and action_type == "move"
    ):
        move = action_payload.get("move")
        if not isinstance(move, str):
            raise ValueError("Penultima move payload must contain a string move")
        legacy_transition: PenultimaTransition = transition_legacy_penultima_move(
            move=move,
            public_state=public_state,
            private_state=private_state,
        )
        return InteractionTransition(
            public_state=legacy_transition.public_state,
            private_state=legacy_transition.private_state,
            accepted=legacy_transition.accepted,
            completed=legacy_transition.completed,
            reason=legacy_transition.reason,
            message=legacy_transition.message,
            normalized_input=legacy_transition.normalized_move,
            evaluation_state=legacy_transition.evaluation_state,
        )
    if (
        family == GEO_ZENDO_FAMILY
        and generator_version == GEO_ZENDO_GENERATOR_VERSION
        and action_type == "probe"
    ):
        probe = action_payload.get("probe")
        if not isinstance(probe, str):
            raise ValueError("Geometry probe payload must contain a string probe")
        transition = transition_geo_zendo_v2_probe(
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
            normalized_input=transition.normalized_card_id,
            evaluation_state=transition.telemetry,
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
    if (
        family == MACHINE_REACH_FAMILY
        and generator_version == MACHINE_REACH_GENERATOR_VERSION
        and action_type in {"apply_op", "undo"}
    ):
        op_id = action_payload.get("op_id")
        client_action_id = action_payload.get("client_action_id")
        if not isinstance(client_action_id, str):
            raise ValueError("Machine action requires client_action_id")
        if op_id is not None and not isinstance(op_id, str):
            raise ValueError("Machine op_id must be a string")
        latency = action_payload.get("first_action_latency_ms")
        transition: MachineTransition = transition_machine_action(
            action_type=action_type,
            public_state=public_state,
            private_state=private_state,
            client_action_id=client_action_id,
            op_id=op_id,
            first_action_latency_ms=(
                latency if isinstance(latency, int) and not isinstance(latency, bool)
                else None
            ),
        )
        return InteractionTransition(
            public_state=transition.public_state,
            private_state=transition.private_state,
            accepted=transition.accepted,
            completed=transition.completed,
            reason=transition.reason,
            message=transition.message,
            normalized_input=transition.normalized_input,
            evaluation_state=transition.evaluation_state,
        )
    raise ValueError(
        "Unsupported task interaction: "
        f"family={family!r}, version={generator_version!r}, action={action_type!r}"
    )
