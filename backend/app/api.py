import hmac
import hashlib
import json
import secrets
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from .dependencies import (
    OrganizerDependency,
    ParticipantEnrollmentDependency,
    SessionDependency,
    SettingsDependency,
    api_error,
)
from .environments import (
    CHESS960_FAMILY,
    DICE_CHESS_FAMILY,
    GEO_GRAPH_FAMILY,
    GEO_PROBABILITY_FAMILY,
    GEO_TRANSFORM_FAMILY,
    GEO_ZENDO_FAMILY,
    GEOMETRY_GENERATOR_VERSION,
    INTERACTIVE_FAMILIES,
    MACHINE_REACH_FAMILY,
    NIM_LIKE_FAMILY,
    PENULTIMA_FAMILY,
    PENULTIMA_LEGACY_GENERATOR_VERSION,
    derive_task_seed,
    evaluate_task,
    generate_task,
    generator_version_for,
    interact_task,
)
from .environments.chess_world.director import (
    DIRECTOR_VERSION as CHESS_DIRECTOR_VERSION,
    CompletedTask,
    DirectorDecision,
    DirectorPhase,
    FamilySettings as DirectorFamilySettings,
    decide_next_task as decide_next_chess_task,
)
from .environments.director import (
    DIRECTOR_VERSION as SHARED_DIRECTOR_VERSION,
    decide_next_task as decide_next_shared_task,
)
from .environments.geometry_world.director import (
    DIRECTOR_VERSION as GEOMETRY_DIRECTOR_VERSION,
    decide_next_task as decide_next_geometry_task,
)
from .environments.machines import SUB_KINDS as MACHINE_REACH_SUB_KINDS
from .models import (
    AccessCode,
    AccessCodeStatus,
    Attempt,
    AttemptEvent,
    AttemptGrant,
    AttemptGrantStatus,
    AttemptStatus,
    Contest,
    ContestStatus,
    Enrollment,
    Participant,
    TaskInteraction,
    TaskInstance,
    TaskStatus,
    utc_now,
)
from .schemas import (
    AccessRedeemRequest,
    AccessRedeemResponse,
    AccessCodeSummary,
    AttemptGrantResponse,
    AttemptStartResponse,
    CodeGenerationRequest,
    CodeGenerationResponse,
    CodeRotationRequest,
    ContestCreate,
    ContestListResponse,
    ContestResponse,
    CurrentTaskResponse,
    EnrollmentBulkCreate,
    EnrollmentBulkResponse,
    EnrollmentResponse,
    GeneratedCodeResponse,
    HealthResponse,
    NextTaskResponse,
    OrganizerAttemptSummary,
    OrganizerEnrollmentListResponse,
    OrganizerEnrollmentResponse,
    ParticipantContextResponse,
    TaskActionResponse,
    TaskAnswerRequest,
    TaskInteractionRequest,
    TaskInteractionResponse,
)
from .security import (
    generate_access_code,
    hash_access_code,
    issue_bearer_token,
    normalize_code,
)

router = APIRouter(prefix="/api/v1")

FAMILY_ALIASES = {
    "chess960": "chess960",
    "chess_960": "chess960",
    "dice_chess": DICE_CHESS_FAMILY,
    "dice-chess": DICE_CHESS_FAMILY,
    "dice&chess": DICE_CHESS_FAMILY,
    "penultima": PENULTIMA_FAMILY,
    "micro_penultima": PENULTIMA_FAMILY,
    "micro-penultima": PENULTIMA_FAMILY,
    "geo_zendo": GEO_ZENDO_FAMILY,
    "geometry_zendo": GEO_ZENDO_FAMILY,
    "geo_transform": GEO_TRANSFORM_FAMILY,
    "geometry_transform": GEO_TRANSFORM_FAMILY,
    "geo_probability": GEO_PROBABILITY_FAMILY,
    "geometry_probability": GEO_PROBABILITY_FAMILY,
    "geo_graph": GEO_GRAPH_FAMILY,
    "geometry_graph": GEO_GRAPH_FAMILY,
    "machine_reach": MACHINE_REACH_FAMILY,
    "machine-reach": MACHINE_REACH_FAMILY,
    "nim_like": NIM_LIKE_FAMILY,
    "nim-like": NIM_LIKE_FAMILY,
}
WORLD_FAMILIES = {
    "chess_world": frozenset({"chess960", DICE_CHESS_FAMILY, PENULTIMA_FAMILY}),
    "geometry_world": frozenset(
        {
            GEO_ZENDO_FAMILY,
            GEO_TRANSFORM_FAMILY,
            GEO_PROBABILITY_FAMILY,
            GEO_GRAPH_FAMILY,
        }
    ),
}
WORLD_FAMILIES["mixed"] = frozenset(
    {
        *frozenset().union(*WORLD_FAMILIES.values()),
        MACHINE_REACH_FAMILY,
        NIM_LIKE_FAMILY,
    }
)
WORLD_DEFAULT_FAMILY = {
    "chess_world": "chess960",
    "geometry_world": GEO_ZENDO_FAMILY,
    "mixed": "chess960",
}
WORLD_DIRECTOR_VERSION = {
    "chess_world": CHESS_DIRECTOR_VERSION,
    "geometry_world": GEOMETRY_DIRECTOR_VERSION,
    "mixed": SHARED_DIRECTOR_VERSION,
}
FAMILY_INTERACTION_ACTIONS = {
    PENULTIMA_FAMILY: frozenset({"move"}),
    GEO_ZENDO_FAMILY: frozenset({"probe"}),
    MACHINE_REACH_FAMILY: frozenset({"apply_op", "undo"}),
}
FAMILY_ROUTE_VERSION = "weighted-family-route-v1"
ADAPTIVE_TRAJECTORY_MODE = "adaptive"


@dataclass(frozen=True)
class FamilyTaskSettings:
    family: str
    weight_units: int
    initial_difficulty: int
    max_difficulty: int
    skin: str | None = None
    locked_chapter: bool = False
    sub_kinds: tuple[str, ...] = ()


def _as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _get_contest_or_404(session: SessionDependency, contest_id: str) -> Contest:
    contest = session.get(Contest, contest_id)
    if contest is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "CONTEST_NOT_FOUND", "Контест не найден.")
    return contest


def _get_enrollment_for_contest_or_404(
    session: SessionDependency,
    *,
    contest_id: str,
    enrollment_id: str,
) -> Enrollment:
    enrollment = session.scalar(
        select(Enrollment)
        .options(joinedload(Enrollment.participant))
        .where(
            Enrollment.id == enrollment_id,
            Enrollment.contest_id == contest_id,
        )
    )
    if enrollment is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "ENROLLMENT_NOT_FOUND",
            "Участник не найден в этом контесте.",
        )
    return enrollment


def _expire_access_code_if_needed(code: AccessCode, now: datetime) -> bool:
    if (
        code.status == AccessCodeStatus.ACTIVE
        and code.expires_at is not None
        and _as_utc(code.expires_at) <= now
    ):
        code.status = AccessCodeStatus.EXPIRED
        code.active_slot = None
        return True
    return False


def _new_access_code_values(
    session: SessionDependency,
    settings: SettingsDependency,
) -> tuple[str, str]:
    for _ in range(12):
        plaintext = generate_access_code()
        lookup_hash = hash_access_code(plaintext, settings)
        hash_exists = session.scalar(
            select(AccessCode.id).where(AccessCode.lookup_hash == lookup_hash)
        )
        if hash_exists is None:
            return plaintext, lookup_hash
    raise api_error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "CODE_GENERATION_FAILED",
        "Не удалось создать уникальный код.",
    )


def _expire_attempt_if_needed(
    session: SessionDependency,
    attempt: Attempt,
    now: datetime,
) -> bool:
    if (
        attempt.status == AttemptStatus.ACTIVE
        and _as_utc(attempt.deadline_at) <= now
    ):
        attempt.status = AttemptStatus.EXPIRED
        attempt.active_slot = None
        attempt.finished_at = now
        _append_event(
            session,
            attempt_id=attempt.id,
            event_type="attempt_expired",
            payload={"deadline_at": _as_utc(attempt.deadline_at).isoformat()},
        )
        return True
    return False


def _active_attempt(
    session: SessionDependency,
    enrollment_id: str,
    *,
    lock: bool = False,
) -> Attempt | None:
    statement = select(Attempt).where(
        Attempt.enrollment_id == enrollment_id,
        Attempt.status == AttemptStatus.ACTIVE,
    )
    if lock:
        statement = statement.with_for_update()
    attempt = session.scalar(statement)
    if attempt is not None and _expire_attempt_if_needed(session, attempt, utc_now()):
        session.commit()
        return None
    return attempt


def _require_active_attempt(
    session: SessionDependency,
    enrollment: Enrollment,
) -> Attempt:
    # PostgreSQL serializes task commands per attempt. SQLite ignores
    # FOR UPDATE but still enforces the uniqueness constraints used below.
    attempt = _active_attempt(session, enrollment.id, lock=True)
    if attempt is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "ACTIVE_ATTEMPT_REQUIRED",
            "Сначала запустите попытку. Истёкшую попытку продолжить нельзя.",
        )
    return attempt


def _active_task(session: SessionDependency, attempt_id: str) -> TaskInstance | None:
    return session.scalar(
        select(TaskInstance).where(
            TaskInstance.attempt_id == attempt_id,
            TaskInstance.status == TaskStatus.ACTIVE,
        )
    )


def _append_event(
    session: SessionDependency,
    *,
    attempt_id: str,
    event_type: str,
    task_instance_id: str | None = None,
    payload: dict | None = None,
) -> AttemptEvent:
    stored_sequence = session.scalar(
        select(func.max(AttemptEvent.sequence)).where(
            AttemptEvent.attempt_id == attempt_id
        )
    )
    pending_sequences = [
        event.sequence
        for event in session.new
        if isinstance(event, AttemptEvent) and event.attempt_id == attempt_id
    ]
    sequence = max([stored_sequence or 0, *pending_sequences]) + 1
    event = AttemptEvent(
        attempt_id=attempt_id,
        task_instance_id=task_instance_id,
        event_type=event_type,
        sequence=sequence,
        payload=payload or {},
    )
    session.add(event)
    return event


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return min(maximum, max(minimum, value))


def _weight_units(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        weight = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return 0
    if not weight.is_finite() or weight <= 0:
        return 0
    capped = min(weight, Decimal("1000"))
    return max(
        1,
        int((capped * 1000).to_integral_value(rounding=ROUND_HALF_UP)),
    )


def _task_family_settings_from_config(
    config: dict,
    environment_key: str = "chess_world",
) -> tuple[list[FamilyTaskSettings], int]:
    """Read implemented families from both legacy and current configs."""

    allowed_families = WORLD_FAMILIES.get(environment_key, frozenset())
    families = config.get("families")
    raw_families: list[object]
    if isinstance(families, list):
        raw_families = families
    else:
        # Empty and older contests predate the family constructor; Chess960 is
        # their safe default.
        raw_families = [WORLD_DEFAULT_FAMILY.get(environment_key, "chess960")]

    parsed: dict[str, FamilyTaskSettings] = {}
    for raw_family in raw_families:
        if isinstance(raw_family, str):
            raw_key = raw_family
            values: dict = {}
        elif isinstance(raw_family, dict):
            if raw_family.get("enabled", True) is False:
                continue
            raw_key = raw_family.get("family", raw_family.get("key"))
            values = raw_family
        else:
            continue
        if not isinstance(raw_key, str):
            continue
        family = FAMILY_ALIASES.get(raw_key.strip().casefold())
        if (
            family is None
            or family not in allowed_families
            or family in parsed
        ):
            continue
        weight_units = _weight_units(values.get("weight", 1))
        if weight_units == 0:
            continue
        difficulty_cap = 5 if environment_key == "mixed" else 10
        initial = _bounded_int(
            values.get("initial_difficulty"),
            default=1,
            minimum=1,
            maximum=difficulty_cap,
        )
        maximum = _bounded_int(
            values.get("max_difficulty"),
            default=difficulty_cap,
            minimum=initial,
            maximum=difficulty_cap,
        )
        parsed[family] = FamilyTaskSettings(
            family=family,
            weight_units=weight_units,
            initial_difficulty=initial,
            max_difficulty=maximum,
            skin=(
                values.get("skin").strip()
                if isinstance(values.get("skin"), str)
                and values.get("skin").strip()
                else None
            ),
            locked_chapter=values.get("locked_chapter") is True,
            sub_kinds=tuple(
                item.strip()
                for item in values.get("sub_kinds", [])
                if isinstance(item, str) and item.strip()
            )
            if isinstance(values.get("sub_kinds"), list)
            else (),
        )

    threshold = _bounded_int(
        config.get("adaptation_threshold"),
        default=3,
        minimum=1,
        maximum=20,
    )
    return sorted(parsed.values(), key=lambda item: item.family), threshold


def _task_family_settings(
    contest: Contest,
) -> tuple[list[FamilyTaskSettings], int]:
    config = contest.task_config if isinstance(contest.task_config, dict) else {}
    return _task_family_settings_from_config(config, contest.environment_key)


def _select_task_family(
    *,
    attempt_seed: int,
    ordinal: int,
    settings: list[FamilyTaskSettings],
) -> FamilyTaskSettings:
    route_seed = derive_task_seed(
        attempt_seed,
        ordinal,
        "family_route",
        FAMILY_ROUTE_VERSION,
    )
    selection = route_seed % sum(item.weight_units for item in settings)
    cursor = 0
    for item in settings:
        cursor += item.weight_units
        if selection < cursor:
            return item
    raise RuntimeError("Weighted family selection did not produce a family")


def _task_difficulty(
    session: SessionDependency,
    *,
    attempt_id: str,
    family: str,
    initial: int,
    maximum: int,
    threshold: int,
) -> int:
    answered_tasks = session.scalars(
        select(TaskInstance).where(
            TaskInstance.attempt_id == attempt_id,
            TaskInstance.family == family,
            TaskInstance.status == TaskStatus.ANSWERED,
        )
    )
    correct_count = sum(
        1
        for task in answered_tasks
        if isinstance(task.evaluation_state, dict)
        and task.evaluation_state.get("correct") is True
    )
    return min(maximum, initial + correct_count // threshold)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _seed_relevant_task_config(config: dict) -> dict:
    """Remove presentation-only skin choices from deterministic seed material."""

    normalized = json.loads(json.dumps(config))
    families = normalized.get("families")
    if isinstance(families, list):
        for family in families:
            if isinstance(family, dict):
                family.pop("skin", None)
    return normalized


def _seed_relevant_generation_context(context: dict) -> dict:
    """Remove database identities from cross-participant task seed material."""

    return {
        key: value
        for key, value in context.items()
        if key not in {"context_hash", "parent_task_id"}
    }


def _attempt_seed(contest: Contest, attempt_number: int) -> int:
    config = contest.task_config if isinstance(contest.task_config, dict) else {}
    cohort_seed = config.get("cohort_seed")
    if cohort_seed is None or isinstance(cohort_seed, (dict, list, bool)):
        return secrets.randbits(63)
    identity = json.dumps(
        ["cohort-attempt-v1", str(cohort_seed), attempt_number],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return int.from_bytes(
        hashlib.sha256(identity).digest()[:8],
        byteorder="big",
    ) & ((1 << 63) - 1)


def _attempt_task_config(
    session: SessionDependency,
    *,
    attempt_id: str,
    contest: Contest,
) -> dict:
    started_event = session.scalar(
        select(AttemptEvent)
        .where(
            AttemptEvent.attempt_id == attempt_id,
            AttemptEvent.event_type == "attempt_started",
        )
        .order_by(AttemptEvent.sequence)
        .limit(1)
    )
    payload = (
        started_event.payload
        if started_event is not None and isinstance(started_event.payload, dict)
        else {}
    )
    snapshot = payload.get("task_config_snapshot")
    if isinstance(snapshot, dict):
        return snapshot
    return contest.task_config if isinstance(contest.task_config, dict) else {}


def _attempt_environment_key(
    session: SessionDependency,
    *,
    attempt_id: str,
    contest: Contest,
) -> str:
    started_event = session.scalar(
        select(AttemptEvent)
        .where(
            AttemptEvent.attempt_id == attempt_id,
            AttemptEvent.event_type == "attempt_started",
        )
        .order_by(AttemptEvent.sequence)
        .limit(1)
    )
    payload = (
        started_event.payload
        if started_event is not None and isinstance(started_event.payload, dict)
        else {}
    )
    snapshot = payload.get("environment_key_snapshot")
    if isinstance(snapshot, str) and snapshot in WORLD_FAMILIES:
        return snapshot
    if contest.environment_key in WORLD_FAMILIES:
        return contest.environment_key
    return "chess_world"


def _adaptive_trajectory(
    config: dict,
    environment_key: str = "chess_world",
) -> tuple[bool, str | None]:
    trajectory = config.get("trajectory")
    if not isinstance(trajectory, dict):
        return False, None
    if str(trajectory.get("mode") or "").strip().casefold() != ADAPTIVE_TRAJECTORY_MODE:
        return False, None
    expected_version = WORLD_DIRECTOR_VERSION.get(environment_key)
    if expected_version is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "ENVIRONMENT_NOT_SUPPORTED",
            "Среда этого контеста не поддерживается.",
        )
    configured_version = str(
        trajectory.get("director_version") or expected_version
    )
    if configured_version != expected_version:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "DIRECTOR_VERSION_NOT_AVAILABLE",
            "Версия адаптивной траектории этого контеста не поддерживается.",
        )
    raw_start = trajectory.get("start_family")
    if not isinstance(raw_start, str):
        return True, None
    return True, FAMILY_ALIASES.get(raw_start.strip().casefold())


def _director_phase_for_task(task: TaskInstance) -> DirectorPhase:
    private = task.private_state if isinstance(task.private_state, dict) else {}
    metadata = private.get("world_director")
    phase_value = metadata.get("phase") if isinstance(metadata, dict) else None
    try:
        return DirectorPhase(str(phase_value))
    except ValueError:
        return DirectorPhase.ROTATION


def _director_evidence(task: TaskInstance) -> int:
    if task.status == TaskStatus.SKIPPED:
        return -1
    evaluation = (
        task.evaluation_state
        if isinstance(task.evaluation_state, dict)
        else {}
    )
    if evaluation.get("correct") is not True:
        return -1
    if evaluation.get("efficient") is False:
        return 0
    return 1


def _director_signal(
    *,
    family: str,
    evaluation: dict,
    skipped: bool = False,
) -> str:
    if skipped or evaluation.get("correct") is not True:
        return "struggle"
    if evaluation.get("efficient") is False:
        return "pass"
    return "strong"


def _evaluation_with_telemetry(
    task: TaskInstance,
    evaluation: dict,
) -> dict:
    enriched = dict(evaluation)
    raw_score = enriched.get("continuous_score")
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        raw_score = 1.0 if enriched.get("correct") is True else 0.0
    enriched["continuous_score"] = min(1.0, max(0.0, float(raw_score)))
    enriched["difficulty"] = task.difficulty
    enriched["family"] = task.family
    enriched["generator_version"] = task.generator_version
    return enriched


def _director_history(
    session: SessionDependency,
    *,
    attempt_id: str,
) -> list[CompletedTask]:
    tasks = list(
        session.scalars(
            select(TaskInstance)
            .where(
                TaskInstance.attempt_id == attempt_id,
                TaskInstance.status != TaskStatus.ACTIVE,
            )
            .order_by(TaskInstance.ordinal)
        ).all()
    )
    history: list[CompletedTask] = []
    for task in tasks:
        private = task.private_state if isinstance(task.private_state, dict) else {}
        raw_stage = private.get("chapter_stage")
        chapter_stage = (
            raw_stage
            if isinstance(raw_stage, int) and not isinstance(raw_stage, bool)
            else None
        )
        history.append(
            CompletedTask(
                task_id=task.id,
                family=task.family,
                difficulty=task.difficulty,
                evidence=_director_evidence(task),
                phase=_director_phase_for_task(task),
                chapter_stage=chapter_stage,
            )
        )
    return history


def _adaptive_director_decision(
    *,
    environment_key: str = "chess_world",
    attempt_seed: int,
    settings: list[FamilyTaskSettings],
    history: list[CompletedTask],
    start_family: str | None,
) -> DirectorDecision:
    enabled = {item.family for item in settings}
    decide = {
        "geometry_world": decide_next_geometry_task,
        "chess_world": decide_next_chess_task,
        "mixed": decide_next_shared_task,
    }.get(environment_key, decide_next_shared_task)
    return decide(
        seed=attempt_seed,
        families=[
            DirectorFamilySettings(
                family=item.family,
                weight=item.weight_units,
                initial_difficulty=item.initial_difficulty,
                max_difficulty=item.max_difficulty,
                locked_chapter=item.locked_chapter,
            )
            for item in settings
        ],
        history=history,
        start_family=start_family if start_family in enabled else None,
    )


def _contextual_task_seed(base_seed: int, context_hash: str) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{base_seed}:{context_hash}".encode("ascii")).digest()[:8],
        byteorder="big",
    ) & ((1 << 63) - 1)


def _penultima_generation_context(
    session: SessionDependency,
    *,
    attempt_id: str,
) -> dict:
    previous = session.scalar(
        select(TaskInstance)
        .where(
            TaskInstance.attempt_id == attempt_id,
            TaskInstance.family == PENULTIMA_FAMILY,
        )
        .order_by(TaskInstance.ordinal.desc())
        .limit(1)
    )
    if previous is None:
        payload: dict = {
            "parent_task_id": None,
            "branch": "initial",
        }
        return {**payload, "context_hash": _canonical_hash(payload)}

    private = previous.private_state if isinstance(previous.private_state, dict) else {}
    evaluation = (
        previous.evaluation_state
        if isinstance(previous.evaluation_state, dict)
        else {}
    )
    chapter_stage_value = private.get("chapter_stage")
    chapter_stage = (
        chapter_stage_value
        if isinstance(chapter_stage_value, int)
        and not isinstance(chapter_stage_value, bool)
        else 1
    )

    if previous.status == TaskStatus.SKIPPED or evaluation.get("skipped") is True:
        branch = "remediate"
        next_stage = chapter_stage
    elif evaluation.get("correct") is True and chapter_stage >= 3:
        branch = "new_chapter"
        next_stage = 1
    elif evaluation.get("correct") is True and evaluation.get("efficient") is True:
        branch = "advance"
        next_stage = min(3, chapter_stage + 1)
    elif evaluation.get("correct") is True:
        branch = "consolidate"
        next_stage = min(3, chapter_stage + 1)
    else:
        branch = "remediate"
        next_stage = chapter_stage

    payload = {
        "parent_task_id": previous.id,
        "branch": branch,
        "previous_shortest_path_length": private.get(
            "initial_shortest_path_length"
        ),
        "recent_observations": private.get("recent_observations", []),
    }
    if branch == "new_chapter":
        payload["exclude_rule_key"] = private.get("rule_key")
        payload["exclude_rule_fingerprint"] = private.get(
            "rule_fingerprint"
        )
    if branch != "new_chapter":
        payload["chapter"] = {
            "chapter_id": private.get("chapter_id"),
            "chapter_stage": next_stage,
            "rule_key": private.get("rule_key"),
            "rule_spec": private.get("rule_spec"),
            "blockers": private.get("blockers", []),
            "current_square": private.get("current_square"),
            "piece_name": private.get("piece_name"),
        }
    return {**payload, "context_hash": _canonical_hash(payload)}


def _task_state_hash(task: TaskInstance) -> str:
    return _canonical_hash(
        {
            "public_state": task.public_state,
            "private_state": task.private_state,
            "status": task.status.value,
        }
    )


def _task_input_frozen_until(task: TaskInstance) -> datetime | None:
    private = task.private_state if isinstance(task.private_state, dict) else {}
    raw_value = private.get("input_frozen_until")
    if not isinstance(raw_value, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    return _as_utc(parsed)


def _require_task_input_available(task: TaskInstance) -> None:
    frozen_until = _task_input_frozen_until(task)
    now = utc_now()
    if frozen_until is None or frozen_until <= now:
        return
    remaining = max(1, int((frozen_until - now).total_seconds() + 0.999))
    raise api_error(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "TASK_INPUT_FROZEN",
        f"Ввод временно приостановлен. Повторите через {remaining} с.",
    )


def _create_or_get_current_task(
    session: SessionDependency,
    *,
    attempt: Attempt,
    contest: Contest,
) -> tuple[TaskInstance, bool]:
    current = _active_task(session, attempt.id)
    if current is not None:
        return current, False

    task_config = _attempt_task_config(
        session,
        attempt_id=attempt.id,
        contest=contest,
    )
    environment_key = _attempt_environment_key(
        session,
        attempt_id=attempt.id,
        contest=contest,
    )
    family_settings, threshold = _task_family_settings_from_config(
        task_config,
        environment_key,
    )
    if not family_settings:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "TASK_FAMILY_NOT_AVAILABLE",
            "В контесте пока нет семейства задач, поддерживаемого этой версией MVP.",
        )
    latest_ordinal = session.scalar(
        select(func.max(TaskInstance.ordinal)).where(
            TaskInstance.attempt_id == attempt.id
        )
    )
    ordinal = (latest_ordinal or 0) + 1
    adaptive, start_family = _adaptive_trajectory(task_config, environment_key)
    director_decision: DirectorDecision | None = None
    director_history: list[CompletedTask] = []
    if adaptive:
        director_history = _director_history(session, attempt_id=attempt.id)
        director_decision = _adaptive_director_decision(
            environment_key=environment_key,
            attempt_seed=attempt.seed,
            settings=family_settings,
            history=director_history,
            start_family=start_family,
        )
        selected_family = next(
            item
            for item in family_settings
            if item.family == director_decision.family
        )
        difficulty = director_decision.difficulty
    else:
        selected_family = _select_task_family(
            attempt_seed=attempt.seed,
            ordinal=ordinal,
            settings=family_settings,
        )
        difficulty = _task_difficulty(
            session,
            attempt_id=attempt.id,
            family=selected_family.family,
            initial=selected_family.initial_difficulty,
            maximum=selected_family.max_difficulty,
            threshold=threshold,
        )
    generator_version = generator_version_for(selected_family.family)
    if (
        environment_key == "chess_world"
        and selected_family.family == PENULTIMA_FAMILY
    ):
        generator_version = PENULTIMA_LEGACY_GENERATOR_VERSION
    elif (
        environment_key == "geometry_world"
        and selected_family.family == GEO_ZENDO_FAMILY
    ):
        generator_version = GEOMETRY_GENERATOR_VERSION
    seed_family = (
        f"{environment_key}:{selected_family.family}"
        if environment_key == "geometry_world"
        and (
            director_decision is None
            or director_decision.version == GEOMETRY_DIRECTOR_VERSION
        )
        else selected_family.family
    )
    base_task_seed = derive_task_seed(
        attempt.seed,
        ordinal,
        seed_family,
        generator_version,
    )
    generation_context = (
        _penultima_generation_context(session, attempt_id=attempt.id)
        if selected_family.family == PENULTIMA_FAMILY
        else None
    )
    generator_context = dict(generation_context or {})
    if selected_family.skin is not None:
        generator_context["skin"] = selected_family.skin
    if selected_family.sub_kinds:
        generator_context["sub_kinds"] = list(selected_family.sub_kinds)
    director_context_hash: str | None = None
    if director_decision is not None:
        shared_director = director_decision.version == SHARED_DIRECTOR_VERSION
        seed_config = (
            _seed_relevant_task_config(task_config)
            if shared_director
            else task_config
        )
        seed_history = [
            {
                **(
                    {}
                    if shared_director
                    else {"task_id": item.task_id}
                ),
                "family": item.family,
                "difficulty": item.difficulty,
                "evidence": item.evidence,
                "phase": item.phase.value,
                "chapter_stage": item.chapter_stage,
            }
            for item in director_history
        ]
        family_context_hash = (
            _canonical_hash(
                _seed_relevant_generation_context(generation_context)
            )
            if shared_director and generation_context is not None
            else generation_context.get("context_hash")
            if generation_context is not None
            else None
        )
        director_context_hash = _canonical_hash(
            {
                "version": director_decision.version,
                "family": director_decision.family,
                "difficulty": director_decision.difficulty,
                "phase": director_decision.phase.value,
                "reason": director_decision.reason,
                **(
                    {}
                    if shared_director
                    else {"parent_task_id": director_decision.parent_task_id}
                ),
                "task_config_hash": _canonical_hash(seed_config),
                "history": seed_history,
                "family_context_hash": family_context_hash,
            }
        )
        task_seed = _contextual_task_seed(
            base_task_seed,
            director_context_hash,
        )
    elif generation_context is not None:
        generation_context_hash = (
            _canonical_hash(
                _seed_relevant_generation_context(generation_context)
            )
            if environment_key == "mixed"
            else str(generation_context["context_hash"])
        )
        task_seed = _contextual_task_seed(
            base_task_seed,
            generation_context_hash,
        )
    else:
        task_seed = base_task_seed
    generated = generate_task(
        family=selected_family.family,
        generator_version=generator_version,
        seed=task_seed,
        difficulty=difficulty,
        context=generator_context or None,
    )
    public_state = dict(generated.public_state)
    private_state = dict(generated.private_state)
    if selected_family.skin is not None:
        public_state.setdefault("skin", selected_family.skin)
    private_state["world_runtime"] = {
        "world": environment_key,
        "version": f"{environment_key}-runtime-v1",
    }
    if director_decision is not None:
        public_state["world_context"] = {
            "world": environment_key,
            "episode": ordinal,
            "family": selected_family.family,
            "phase": director_decision.phase.value,
        }
        private_state["world_director"] = {
            "version": director_decision.version,
            "phase": director_decision.phase.value,
            "reason": director_decision.reason,
            "parent_task_id": director_decision.parent_task_id,
            "context_hash": director_context_hash,
        }
    task = TaskInstance(
        attempt_id=attempt.id,
        ordinal=ordinal,
        family=selected_family.family,
        generator_version=generator_version,
        seed=task_seed,
        difficulty=difficulty,
        status=TaskStatus.ACTIVE,
        active_slot=True,
        public_state=public_state,
        private_state=private_state,
    )
    session.add(task)
    try:
        session.flush()
        generated_event_payload = {
            "ordinal": ordinal,
            "environment_key": environment_key,
            "family": task.family,
            "generator_version": task.generator_version,
            "seed": task.seed,
            "difficulty": task.difficulty,
            "configured_weight": selected_family.weight_units / 1000,
            "family_route_version": (
                director_decision.version
                if director_decision is not None
                else FAMILY_ROUTE_VERSION
            ),
        }
        if director_decision is not None:
            generated_event_payload.update(
                {
                    "director_version": director_decision.version,
                    "director_phase": director_decision.phase.value,
                    "decision_reason": director_decision.reason,
                    "parent_task_id": director_decision.parent_task_id,
                    "director_context_hash": director_context_hash,
                    "task_config_hash": _canonical_hash(task_config),
                }
            )
        if generation_context is not None:
            generated_event_payload.update(
                {
                    "parent_task_id": (
                        director_decision.parent_task_id
                        if director_decision is not None
                        else generation_context.get("parent_task_id")
                    ),
                    "branch": generation_context["branch"],
                    "context_hash": generation_context["context_hash"],
                }
            )
        elif director_decision is not None:
            generated_event_payload["branch"] = director_decision.phase.value
        _append_event(
            session,
            attempt_id=attempt.id,
            task_instance_id=task.id,
            event_type="task_generated",
            payload=generated_event_payload,
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        current = _active_task(session, attempt.id)
        if current is None:
            raise
        return current, False
    session.refresh(task)
    return task, True


def _get_active_task_or_error(
    session: SessionDependency,
    *,
    attempt: Attempt,
    task_id: str,
) -> TaskInstance:
    task = session.scalar(
        select(TaskInstance).where(
            TaskInstance.id == task_id,
            TaskInstance.attempt_id == attempt.id,
        )
    )
    if task is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "TASK_NOT_FOUND",
            "Задача не найдена в текущей попытке.",
        )
    if task.status != TaskStatus.ACTIVE:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "TASK_ALREADY_CLOSED",
            "Ответ на эту задачу уже зафиксирован.",
        )
    return task


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDependency) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name)


@router.post("/access/redeem", response_model=AccessRedeemResponse)
def redeem_access(
    payload: AccessRedeemRequest,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AccessRedeemResponse:
    normalized_code = normalize_code(payload.code)

    if hmac.compare_digest(normalized_code, normalize_code(settings.organizer_code)):
        token, expires_at = issue_bearer_token(
            settings=settings,
            role="organizer",
            subject="organizer",
        )
        return AccessRedeemResponse(
            access_token=token,
            role="organizer",
            expires_at=expires_at,
        )

    lookup_hash = hash_access_code(normalized_code, settings)
    access_code = session.scalar(
        select(AccessCode)
        .options(
            joinedload(AccessCode.enrollment).joinedload(Enrollment.contest),
            joinedload(AccessCode.enrollment).joinedload(Enrollment.participant),
        )
        .where(AccessCode.lookup_hash == lookup_hash)
    )
    if access_code is None or access_code.status != AccessCodeStatus.ACTIVE:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_ACCESS_CODE",
            "Код не найден, отозван или истёк.",
        )

    now = utc_now()
    if _expire_access_code_if_needed(access_code, now):
        session.commit()
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_ACCESS_CODE",
            "Код не найден, отозван или истёк.",
        )

    enrollment = access_code.enrollment
    contest = enrollment.contest
    if contest.status != ContestStatus.PUBLISHED:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "CONTEST_NOT_PUBLISHED",
            "Контест ещё не опубликован.",
        )

    if access_code.redeemed_at is None:
        access_code.redeemed_at = now
        session.commit()

    token, expires_at = issue_bearer_token(
        settings=settings,
        role="participant",
        subject=enrollment.participant_id,
        additional_claims={
            "enrollment_id": enrollment.id,
            "contest_id": enrollment.contest_id,
            "access_code_id": access_code.id,
        },
        not_after=access_code.expires_at,
    )
    return AccessRedeemResponse(
        access_token=token,
        role="participant",
        expires_at=expires_at,
    )


@router.get("/contests", response_model=ContestListResponse)
def list_contests(
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> ContestListResponse:
    contests = list(session.scalars(select(Contest).order_by(Contest.created_at.desc())).all())
    return ContestListResponse(items=contests)


@router.delete(
    "/contests/{contest_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_contest(
    contest_id: str,
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> Response:
    contest = _get_contest_or_404(session, contest_id)
    session.delete(contest)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/contests", response_model=ContestResponse, status_code=status.HTTP_201_CREATED)
def create_contest(
    payload: ContestCreate,
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> Contest:
    task_config = payload.task_config if isinstance(payload.task_config, dict) else {}
    # Older API clients did not send ``environment_key`` and identified the
    # chess runtime solely by its pinned director version.  Keep those payloads
    # reproducible, while every new client (the current constructor sends the
    # field explicitly) writes the skin-independent ``mixed`` environment.
    environment_key = payload.environment_key
    trajectory = task_config.get("trajectory")
    if (
        "environment_key" not in payload.model_fields_set
        and isinstance(trajectory, dict)
        and trajectory.get("director_version") == CHESS_DIRECTOR_VERSION
    ):
        environment_key = "chess_world"
    configured_families = task_config.get("families")
    if (
        "environment_key" not in payload.model_fields_set
        and isinstance(configured_families, list)
        and configured_families
        and all(
            isinstance(item, dict)
            and "family" not in item
            and isinstance(item.get("key"), str)
            for item in configured_families
        )
    ):
        legacy_families = {
            FAMILY_ALIASES.get(str(item["key"]).strip().casefold())
            for item in configured_families
        }
        legacy_families.discard(None)
        if legacy_families and legacy_families <= WORLD_FAMILIES["chess_world"]:
            environment_key = "chess_world"
        elif (
            legacy_families
            and legacy_families <= WORLD_FAMILIES["geometry_world"]
        ):
            environment_key = "geometry_world"
    allowed_families = WORLD_FAMILIES[environment_key]
    foreign_families: list[str] = []
    if isinstance(configured_families, list):
        for configured in configured_families:
            raw_key = (
                configured
                if isinstance(configured, str)
                else configured.get("family", configured.get("key"))
                if isinstance(configured, dict)
                else None
            )
            if not isinstance(raw_key, str):
                continue
            family = FAMILY_ALIASES.get(raw_key.strip().casefold())
            if family is not None and family not in allowed_families:
                foreign_families.append(raw_key)
    if foreign_families:
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "TASK_FAMILY_WORLD_MISMATCH",
            "Одно или несколько семейств не относятся к указанному миру.",
        )
    if isinstance(configured_families, list):
        for configured in configured_families:
            if not isinstance(configured, dict):
                continue
            raw_family = configured.get("family", configured.get("key"))
            family = (
                FAMILY_ALIASES.get(raw_family.strip().casefold())
                if isinstance(raw_family, str)
                else None
            )
            raw_sub_kinds = configured.get("sub_kinds")
            if family != MACHINE_REACH_FAMILY or raw_sub_kinds is None:
                continue
            if (
                not isinstance(raw_sub_kinds, list)
                or not raw_sub_kinds
                or any(
                    not isinstance(item, str)
                    or item not in MACHINE_REACH_SUB_KINDS
                    for item in raw_sub_kinds
                )
            ):
                raise api_error(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "TASK_SUB_KIND_NOT_AVAILABLE",
                    "Указан неизвестный вариант семейства machine_reach.",
                )
    family_settings, _ = _task_family_settings_from_config(
        task_config,
        environment_key,
    )
    if isinstance(configured_families, list) and not family_settings:
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "TASK_FAMILY_NOT_AVAILABLE",
            "Выбранные семейства не относятся к указанному миру.",
        )
    _adaptive, start_family = _adaptive_trajectory(
        task_config,
        environment_key,
    )
    if start_family is not None and start_family not in allowed_families:
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "TASK_FAMILY_WORLD_MISMATCH",
            "Стартовое семейство не относится к указанному миру.",
        )
    contest_data = payload.model_dump()
    contest_data["environment_key"] = environment_key
    contest = Contest(**contest_data)
    session.add(contest)
    session.commit()
    session.refresh(contest)
    return contest


@router.post(
    "/contests/{contest_id}/enrollments",
    response_model=EnrollmentBulkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_enrollments(
    contest_id: str,
    payload: EnrollmentBulkCreate,
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> EnrollmentBulkResponse:
    contest = _get_contest_or_404(session, contest_id)
    if contest.status != ContestStatus.DRAFT:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "CONTEST_ALREADY_PUBLISHED",
            "Нельзя менять список участников опубликованного контеста.",
        )

    items: list[Enrollment] = []
    created_count = 0
    for item in payload.participants:
        participant = session.scalar(
            select(Participant).where(Participant.external_ref == item.external_ref)
        )
        if participant is None:
            participant = Participant(
                external_ref=item.external_ref,
                display_name=item.display_name,
            )
            session.add(participant)
            session.flush()
        elif participant.display_name != item.display_name:
            participant.display_name = item.display_name

        enrollment = session.scalar(
            select(Enrollment)
            .options(joinedload(Enrollment.participant))
            .where(
                Enrollment.contest_id == contest.id,
                Enrollment.participant_id == participant.id,
            )
        )
        if enrollment is None:
            enrollment = Enrollment(contest_id=contest.id, participant_id=participant.id)
            enrollment.participant = participant
            session.add(enrollment)
            session.flush()
            created_count += 1
        items.append(enrollment)

    session.commit()
    return EnrollmentBulkResponse(items=items, created_count=created_count)


@router.get(
    "/contests/{contest_id}/enrollments",
    response_model=OrganizerEnrollmentListResponse,
)
def list_enrollments(
    contest_id: str,
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> OrganizerEnrollmentListResponse:
    _get_contest_or_404(session, contest_id)
    enrollments = list(
        session.scalars(
            select(Enrollment)
            .options(
                joinedload(Enrollment.participant),
                selectinload(Enrollment.access_codes),
                selectinload(Enrollment.attempts),
                selectinload(Enrollment.attempt_grants),
            )
            .where(Enrollment.contest_id == contest_id)
            .order_by(Enrollment.created_at, Enrollment.id)
        )
        .unique()
        .all()
    )

    now = utc_now()
    status_changed = False
    for enrollment in enrollments:
        for code in enrollment.access_codes:
            status_changed = _expire_access_code_if_needed(code, now) or status_changed
        for attempt in enrollment.attempts:
            status_changed = (
                _expire_attempt_if_needed(session, attempt, now) or status_changed
            )
    if status_changed:
        session.commit()

    items: list[OrganizerEnrollmentResponse] = []
    for enrollment in enrollments:
        latest_code = (
            max(
                enrollment.access_codes,
                key=lambda code: (code.created_at, code.id),
            )
            if enrollment.access_codes
            else None
        )
        latest_attempt = (
            max(enrollment.attempts, key=lambda attempt: attempt.number)
            if enrollment.attempts
            else None
        )
        items.append(
            OrganizerEnrollmentResponse(
                id=enrollment.id,
                contest_id=enrollment.contest_id,
                participant_id=enrollment.participant_id,
                status=enrollment.status,
                participant=enrollment.participant,
                created_at=enrollment.created_at,
                latest_code=(
                    AccessCodeSummary.model_validate(latest_code)
                    if latest_code is not None
                    else None
                ),
                latest_attempt=(
                    OrganizerAttemptSummary.model_validate(latest_attempt)
                    if latest_attempt is not None
                    else None
                ),
                attempt_grant_pending=any(
                    grant.status == AttemptGrantStatus.PENDING
                    for grant in enrollment.attempt_grants
                ),
            )
        )
    return OrganizerEnrollmentListResponse(items=items)


@router.post("/contests/{contest_id}/codes", response_model=CodeGenerationResponse)
def generate_codes(
    contest_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
    _organizer: OrganizerDependency,
    payload: CodeGenerationRequest = Body(default_factory=CodeGenerationRequest),
) -> CodeGenerationResponse:
    _get_contest_or_404(session, contest_id)
    enrollments = list(
        session.scalars(
            select(Enrollment)
            .options(joinedload(Enrollment.participant), joinedload(Enrollment.access_codes))
            .where(Enrollment.contest_id == contest_id)
            .order_by(Enrollment.created_at)
        )
        .unique()
        .all()
    )
    now = utc_now()
    generated: list[GeneratedCodeResponse] = []
    skipped_count = 0

    for enrollment in enrollments:
        active_codes = [
            code
            for code in enrollment.access_codes
            if code.status == AccessCodeStatus.ACTIVE
            and not _expire_access_code_if_needed(code, now)
        ]
        if active_codes and not payload.rotate:
            skipped_count += 1
            continue
        if payload.rotate:
            for code in active_codes:
                code.status = AccessCodeStatus.REVOKED
                code.active_slot = None
                code.revoked_at = now

        plaintext, lookup_hash = _new_access_code_values(session, settings)

        code = AccessCode(
            enrollment_id=enrollment.id,
            lookup_hash=lookup_hash,
            last4=plaintext[-4:],
            active_slot=True,
            expires_at=payload.expires_at,
        )
        session.add(code)
        session.flush()
        generated.append(
            GeneratedCodeResponse(
                enrollment_id=enrollment.id,
                participant=enrollment.participant,
                code=plaintext,
                last4=code.last4,
                status=code.status,
                expires_at=code.expires_at,
            )
        )

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise api_error(
            status.HTTP_409_CONFLICT,
            "CODE_COLLISION",
            "Возникла коллизия кодов; повторите генерацию.",
        ) from error

    return CodeGenerationResponse(
        items=generated,
        generated_count=len(generated),
        skipped_count=skipped_count,
    )


@router.post(
    "/contests/{contest_id}/enrollments/{enrollment_id}/codes/rotate",
    response_model=GeneratedCodeResponse,
)
def rotate_enrollment_code(
    contest_id: str,
    enrollment_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
    _organizer: OrganizerDependency,
    payload: CodeRotationRequest = Body(default_factory=CodeRotationRequest),
) -> GeneratedCodeResponse:
    _get_contest_or_404(session, contest_id)
    enrollment = _get_enrollment_for_contest_or_404(
        session,
        contest_id=contest_id,
        enrollment_id=enrollment_id,
    )
    now = utc_now()
    active_codes = list(
        session.scalars(
            select(AccessCode)
            .where(
                AccessCode.enrollment_id == enrollment.id,
                AccessCode.status == AccessCodeStatus.ACTIVE,
            )
            .with_for_update()
        ).all()
    )
    for code in active_codes:
        if _expire_access_code_if_needed(code, now):
            continue
        code.status = AccessCodeStatus.REVOKED
        code.active_slot = None
        code.revoked_at = now

    plaintext, lookup_hash = _new_access_code_values(session, settings)
    code = AccessCode(
        enrollment_id=enrollment.id,
        lookup_hash=lookup_hash,
        last4=plaintext[-4:],
        active_slot=True,
        expires_at=payload.expires_at,
    )
    session.add(code)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise api_error(
            status.HTTP_409_CONFLICT,
            "CODE_ROTATION_CONFLICT",
            "Не удалось заменить код; повторите операцию.",
        ) from error
    session.refresh(code)
    return GeneratedCodeResponse(
        enrollment_id=enrollment.id,
        participant=enrollment.participant,
        code=plaintext,
        last4=code.last4,
        status=code.status,
        expires_at=code.expires_at,
    )


@router.post(
    "/contests/{contest_id}/enrollments/{enrollment_id}/attempts/grant",
    response_model=AttemptGrantResponse,
)
def grant_next_attempt(
    contest_id: str,
    enrollment_id: str,
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> AttemptGrantResponse:
    _get_contest_or_404(session, contest_id)
    enrollment = _get_enrollment_for_contest_or_404(
        session,
        contest_id=contest_id,
        enrollment_id=enrollment_id,
    )
    if _active_attempt(session, enrollment.id, lock=True) is not None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "ATTEMPT_ALREADY_ACTIVE",
            "Нельзя выдать новую попытку, пока текущая ещё активна.",
        )

    pending = session.scalar(
        select(AttemptGrant)
        .where(
            AttemptGrant.enrollment_id == enrollment.id,
            AttemptGrant.status == AttemptGrantStatus.PENDING,
        )
        .with_for_update()
    )
    if pending is not None:
        return AttemptGrantResponse(
            enrollment_id=enrollment.id,
            pending=True,
            created=False,
            granted_at=pending.granted_at,
        )

    pending = AttemptGrant(
        enrollment_id=enrollment.id,
        status=AttemptGrantStatus.PENDING,
        pending_slot=True,
    )
    session.add(pending)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(AttemptGrant).where(
                AttemptGrant.enrollment_id == enrollment.id,
                AttemptGrant.status == AttemptGrantStatus.PENDING,
            )
        )
        if existing is None:
            raise
        return AttemptGrantResponse(
            enrollment_id=enrollment.id,
            pending=True,
            created=False,
            granted_at=existing.granted_at,
        )
    session.refresh(pending)
    return AttemptGrantResponse(
        enrollment_id=enrollment.id,
        pending=True,
        created=True,
        granted_at=pending.granted_at,
    )


@router.post("/contests/{contest_id}/publish", response_model=ContestResponse)
def publish_contest(
    contest_id: str,
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> Contest:
    contest = _get_contest_or_404(session, contest_id)
    if contest.status == ContestStatus.DRAFT:
        contest.status = ContestStatus.PUBLISHED
        contest.published_at = utc_now()
        session.commit()
        session.refresh(contest)
    return contest


@router.get("/participant/context", response_model=ParticipantContextResponse)
def participant_context(
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> ParticipantContextResponse:
    attempt = _active_attempt(session, enrollment.id)
    return ParticipantContextResponse(
        contest=enrollment.contest,
        enrollment=EnrollmentResponse.model_validate(enrollment),
        participant=enrollment.participant,
        active_attempt=attempt,
    )


@router.post("/participant/attempts/start", response_model=AttemptStartResponse)
def start_attempt(
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> AttemptStartResponse:
    if enrollment.contest.status != ContestStatus.PUBLISHED:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "CONTEST_NOT_AVAILABLE",
            "Контест недоступен.",
        )

    active = _active_attempt(session, enrollment.id)
    if active is not None:
        return AttemptStartResponse(attempt=active, created=False)

    previous_number = session.scalar(
        select(func.max(Attempt.number)).where(Attempt.enrollment_id == enrollment.id)
    )
    grant: AttemptGrant | None = None
    if previous_number is not None:
        grant = session.scalar(
            select(AttemptGrant)
            .where(
                AttemptGrant.enrollment_id == enrollment.id,
                AttemptGrant.status == AttemptGrantStatus.PENDING,
            )
            .with_for_update()
        )
        if grant is None:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "ATTEMPT_NOT_AVAILABLE",
                "Для новой попытки требуется разрешение организатора.",
            )

    started_at = utc_now()
    attempt_number = (previous_number or 0) + 1
    attempt = Attempt(
        enrollment_id=enrollment.id,
        number=attempt_number,
        seed=_attempt_seed(enrollment.contest, attempt_number),
        status=AttemptStatus.ACTIVE,
        active_slot=True,
        started_at=started_at,
        deadline_at=started_at + timedelta(minutes=enrollment.contest.duration_minutes),
    )
    session.add(attempt)
    try:
        session.flush()
        if grant is not None:
            grant.status = AttemptGrantStatus.CONSUMED
            grant.pending_slot = None
            grant.consumed_at = started_at
            grant.consumed_attempt_id = attempt.id
        _append_event(
            session,
            attempt_id=attempt.id,
            event_type="attempt_started",
            payload={
                "number": attempt.number,
                "started_at": attempt.started_at.isoformat(),
                "deadline_at": attempt.deadline_at.isoformat(),
                "environment_key_snapshot": enrollment.contest.environment_key,
                "source": (
                    "organizer_grant" if grant is not None else "initial_attempt"
                ),
                "task_config_snapshot": (
                    enrollment.contest.task_config
                    if isinstance(enrollment.contest.task_config, dict)
                    else {}
                ),
                "task_config_hash": _canonical_hash(
                    enrollment.contest.task_config
                    if isinstance(enrollment.contest.task_config, dict)
                    else {}
                ),
            },
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        active = _active_attempt(session, enrollment.id)
        if active is None:
            raise
        return AttemptStartResponse(attempt=active, created=False)
    session.refresh(attempt)
    return AttemptStartResponse(attempt=attempt, created=True)


@router.get("/participant/tasks/current", response_model=CurrentTaskResponse)
def current_task(
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> CurrentTaskResponse:
    attempt = _require_active_attempt(session, enrollment)
    task, _created = _create_or_get_current_task(
        session,
        attempt=attempt,
        contest=enrollment.contest,
    )
    return CurrentTaskResponse(task=task)


@router.post("/participant/tasks/next", response_model=NextTaskResponse)
def next_task(
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> NextTaskResponse:
    attempt = _require_active_attempt(session, enrollment)
    task, created = _create_or_get_current_task(
        session,
        attempt=attempt,
        contest=enrollment.contest,
    )
    return NextTaskResponse(task=task, created=created)


def _stored_interaction_response(
    *,
    task: TaskInstance,
    interaction: TaskInteraction,
) -> TaskInteractionResponse:
    result = (
        interaction.result_payload
        if isinstance(interaction.result_payload, dict)
        else {}
    )
    return TaskInteractionResponse(
        task=task,
        accepted=result.get("accepted") is True,
        completed=result.get("completed") is True,
        message=str(result.get("message") or "Действие уже было обработано."),
        client_action_id=interaction.client_action_id,
    )


@router.post(
    "/participant/tasks/{task_id}/interactions",
    response_model=TaskInteractionResponse,
)
def interact_with_task(
    task_id: str,
    payload: TaskInteractionRequest,
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> TaskInteractionResponse:
    attempt = _require_active_attempt(session, enrollment)
    task = session.scalar(
        select(TaskInstance)
        .where(
            TaskInstance.id == task_id,
            TaskInstance.attempt_id == attempt.id,
        )
        .with_for_update()
    )
    if task is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "TASK_NOT_FOUND",
            "Задача не найдена в текущей попытке.",
        )

    if payload.action_type == "move":
        request_payload = {"move": payload.move}
    elif payload.action_type == "probe":
        request_payload = {"probe": payload.probe}
    elif payload.action_type == "apply_op":
        request_payload = {"op_id": payload.op_id}
    else:
        request_payload = {}
    existing = session.scalar(
        select(TaskInteraction).where(
            TaskInteraction.task_instance_id == task.id,
            TaskInteraction.client_action_id == payload.client_action_id,
        )
    )
    if existing is not None:
        if (
            existing.action_type != payload.action_type
            or existing.request_payload != request_payload
        ):
            raise api_error(
                status.HTTP_409_CONFLICT,
                "INTERACTION_ID_REUSED",
                "Этот идентификатор действия уже использован с другими данными.",
            )
        return _stored_interaction_response(task=task, interaction=existing)

    if task.status != TaskStatus.ACTIVE:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "TASK_ALREADY_CLOSED",
            "Эта задача уже завершена.",
        )
    _require_task_input_available(task)
    if task.family not in INTERACTIVE_FAMILIES:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "TASK_INTERACTION_NOT_SUPPORTED",
            "Для этой задачи пошаговые действия не поддерживаются.",
        )
    if payload.action_type not in FAMILY_INTERACTION_ACTIONS.get(
        task.family,
        frozenset(),
    ):
        raise api_error(
            status.HTTP_409_CONFLICT,
            "TASK_INTERACTION_ACTION_NOT_SUPPORTED",
            "Эта команда не поддерживается текущей задачей.",
        )

    previous_hash = _task_state_hash(task)
    transition_payload = {
        **request_payload,
        "client_action_id": payload.client_action_id,
        "first_action_latency_ms": max(
            0,
            int(
                (
                    utc_now() - _as_utc(task.created_at)
                ).total_seconds()
                * 1000
            ),
        ),
    }
    transition = interact_task(
        family=task.family,
        generator_version=task.generator_version,
        action_type=payload.action_type,
        action_payload=transition_payload,
        public_state=task.public_state,
        private_state=task.private_state,
    )
    task.public_state = transition.public_state
    task.private_state = transition.private_state
    if transition.completed:
        task.status = TaskStatus.ANSWERED
        task.active_slot = None
        task.participant_answer = transition.normalized_input
        evaluation_state = _evaluation_with_telemetry(
            task,
            dict(transition.evaluation_state or {}),
        )
        evaluation_state["director_signal"] = _director_signal(
            family=task.family,
            evaluation=evaluation_state,
        )
        task.evaluation_state = evaluation_state
        task.completed_at = utc_now()

    stored_sequence = session.scalar(
        select(func.max(TaskInteraction.sequence)).where(
            TaskInteraction.task_instance_id == task.id
        )
    )
    interaction = TaskInteraction(
        task_instance_id=task.id,
        sequence=(stored_sequence or 0) + 1,
        client_action_id=payload.client_action_id,
        action_type=payload.action_type,
        request_payload=request_payload,
        result_payload={
            "accepted": transition.accepted,
            "completed": transition.completed,
            "reason": transition.reason,
            "message": transition.message,
            "normalized_input": transition.normalized_input,
            "normalized_move": (
                transition.normalized_input
                if payload.action_type == "move"
                else None
            ),
        },
    )
    session.add(interaction)
    session.flush()
    current_hash = _task_state_hash(task)
    _append_event(
        session,
        attempt_id=attempt.id,
        task_instance_id=task.id,
        event_type="task_interaction_submitted",
        payload={
            "interaction_id": interaction.id,
            "client_action_id": payload.client_action_id,
            "action_type": payload.action_type,
            **request_payload,
        },
    )
    _append_event(
        session,
        attempt_id=attempt.id,
        task_instance_id=task.id,
        event_type="task_interaction_resolved",
        payload={
            "interaction_id": interaction.id,
            "client_action_id": payload.client_action_id,
            "accepted": transition.accepted,
            "completed": transition.completed,
            "reason": transition.reason,
            "director_signal": (
                task.evaluation_state.get("director_signal")
                if transition.completed
                and isinstance(task.evaluation_state, dict)
                else None
            ),
            "before_state_hash": previous_hash,
            "after_state_hash": current_hash,
        },
    )
    if (
        task.family == GEO_ZENDO_FAMILY
        and payload.action_type == "probe"
        and transition.accepted
        and isinstance(transition.evaluation_state, dict)
    ):
        _append_event(
            session,
            attempt_id=attempt.id,
            task_instance_id=task.id,
            event_type="zendo_probe",
            payload={
                "interaction_id": interaction.id,
                "client_action_id": payload.client_action_id,
                "card_id": transition.normalized_input,
                **transition.evaluation_state,
            },
        )
    if (
        transition.completed
        and isinstance(task.evaluation_state, dict)
        and not (
            task.family == PENULTIMA_FAMILY
            and task.generator_version == PENULTIMA_LEGACY_GENERATOR_VERSION
        )
    ):
        _append_event(
            session,
            attempt_id=attempt.id,
            task_instance_id=task.id,
            event_type="answer_evaluated",
            payload=task.evaluation_state,
        )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(TaskInteraction).where(
                TaskInteraction.task_instance_id == task_id,
                TaskInteraction.client_action_id == payload.client_action_id,
            )
        )
        if existing is None:
            raise
        if (
            existing.action_type != payload.action_type
            or existing.request_payload != request_payload
        ):
            raise api_error(
                status.HTTP_409_CONFLICT,
                "INTERACTION_ID_REUSED",
                "Этот идентификатор действия уже использован с другими данными.",
            )
        stored_task = session.get(TaskInstance, task_id)
        if stored_task is None:
            raise
        return _stored_interaction_response(
            task=stored_task,
            interaction=existing,
        )
    session.refresh(task)
    return TaskInteractionResponse(
        task=task,
        accepted=transition.accepted,
        completed=transition.completed,
        message=transition.message,
        client_action_id=payload.client_action_id,
    )


@router.post(
    "/participant/tasks/{task_id}/answer",
    response_model=TaskActionResponse,
)
def answer_task(
    task_id: str,
    payload: TaskAnswerRequest,
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> TaskActionResponse:
    attempt = _require_active_attempt(session, enrollment)
    task = _get_active_task_or_error(session, attempt=attempt, task_id=task_id)
    if task.family == PENULTIMA_FAMILY:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "INTERACTIVE_TASK_REQUIRES_MOVE",
            "Эта задача решается ходами. Используйте команду /move.",
        )
    _require_task_input_available(task)
    if task.family == MACHINE_REACH_FAMILY:
        next_private = dict(
            task.private_state
            if isinstance(task.private_state, dict)
            else {}
        )
        interaction = dict(next_private.get("interaction") or {})
        if interaction.get("first_action_latency_ms") is None:
            interaction["first_action_latency_ms"] = max(
                0,
                int(
                    (
                        utc_now() - _as_utc(task.created_at)
                    ).total_seconds()
                    * 1000
                ),
            )
            next_private["interaction"] = interaction
            task.private_state = next_private
    evaluation = dict(
        evaluate_task(
            family=task.family,
            generator_version=task.generator_version,
            answer=payload.answer,
            private_state=task.private_state,
        )
    )
    evaluation = _evaluation_with_telemetry(task, evaluation)
    evaluation["director_signal"] = _director_signal(
        family=task.family,
        evaluation=evaluation,
    )
    if evaluation.get("should_finalize") is False:
        freeze_seconds = evaluation.get("freeze_seconds")
        if (
            isinstance(freeze_seconds, int)
            and not isinstance(freeze_seconds, bool)
            and freeze_seconds > 0
        ):
            frozen_until = utc_now() + timedelta(seconds=freeze_seconds)
            next_private = dict(
                task.private_state
                if isinstance(task.private_state, dict)
                else {}
            )
            next_private["input_frozen_until"] = frozen_until.isoformat()
            task.private_state = next_private
            evaluation["input_frozen_until"] = frozen_until.isoformat()
            _append_event(
                session,
                attempt_id=attempt.id,
                task_instance_id=task.id,
                event_type="task_input_frozen",
                payload={
                    "seconds": freeze_seconds,
                    "until": frozen_until.isoformat(),
                    "reason": evaluation.get("reason"),
                },
            )
        _append_event(
            session,
            attempt_id=attempt.id,
            task_instance_id=task.id,
            event_type="answer_submitted",
            payload={"answer": payload.answer},
        )
        _append_event(
            session,
            attempt_id=attempt.id,
            task_instance_id=task.id,
            event_type="answer_evaluated",
            payload=evaluation,
        )
        session.commit()
        session.refresh(task)
        return TaskActionResponse(
            task=task,
            message=str(
                evaluation.get("feedback")
                or "Ответ пока не завершает задачу."
            ),
        )
    completed_at = utc_now()
    task.participant_answer = payload.answer
    task.evaluation_state = evaluation
    task.status = TaskStatus.ANSWERED
    task.active_slot = None
    task.completed_at = completed_at
    _append_event(
        session,
        attempt_id=attempt.id,
        task_instance_id=task.id,
        event_type="answer_submitted",
        payload={"answer": payload.answer},
    )
    _append_event(
        session,
        attempt_id=attempt.id,
        task_instance_id=task.id,
        event_type="answer_evaluated",
        payload=evaluation,
    )
    session.commit()
    session.refresh(task)
    return TaskActionResponse(
        task=task,
        message="Ответ зафиксирован. Можно перейти к следующей задаче.",
    )


@router.post(
    "/participant/tasks/{task_id}/skip",
    response_model=TaskActionResponse,
)
def skip_task(
    task_id: str,
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> TaskActionResponse:
    attempt = _require_active_attempt(session, enrollment)
    task = _get_active_task_or_error(session, attempt=attempt, task_id=task_id)
    event_payload: dict = {}
    if task.family == PENULTIMA_FAMILY:
        private = task.private_state if isinstance(task.private_state, dict) else {}
        task.evaluation_state = {
            "correct": False,
            "completed": False,
            "skipped": True,
            "efficient": False,
            "director_signal": "struggle",
            "accepted_moves": int(private.get("accepted_moves") or 0),
            "rejected_moves": int(private.get("rejected_moves") or 0),
            "shortest_path_length": int(
                private.get("initial_shortest_path_length") or 0
            ),
        }
        task.evaluation_state = _evaluation_with_telemetry(
            task,
            task.evaluation_state,
        )
        event_payload = dict(task.evaluation_state)
    else:
        task.evaluation_state = {
            "correct": False,
            "skipped": True,
            "director_signal": "struggle",
        }
        task.evaluation_state = _evaluation_with_telemetry(
            task,
            task.evaluation_state,
        )
        event_payload = dict(task.evaluation_state)
    task.status = TaskStatus.SKIPPED
    task.active_slot = None
    task.completed_at = utc_now()
    _append_event(
        session,
        attempt_id=attempt.id,
        task_instance_id=task.id,
        event_type="task_skipped",
        payload=event_payload,
    )
    session.commit()
    session.refresh(task)
    return TaskActionResponse(
        task=task,
        message="Задача пропущена. Можно перейти к следующей.",
    )
