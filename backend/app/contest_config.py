"""Reading and validation of a contest ``task_config``."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import status

from sirius_gate.family import MAX_DIFFICULTY

from .dependencies import api_error
from .tasks import FAMILIES, resolve_family
from .tasks.director import DIRECTOR_VERSION

DEFAULT_FAMILY = 'chess_coverage'
ADAPTIVE_MODE = 'adaptive'
MAX_SCRIPTED_POSITION = 100


@dataclass(frozen=True)
class FamilyTaskSettings:
    family: str
    weight_units: int
    initial_difficulty: int
    max_difficulty: int
    skin: str | None = None
    sub_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScriptedTaskSettings:
    family: str
    sub_kind: str
    position: int


def routable_families() -> frozenset[str]:
    return frozenset(key for key, family in FAMILIES.items() if not family.scripted_only)


def bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return min(maximum, max(minimum, value))


def weight_units(value: object) -> int:
    """Weight in thousandths, so fractional weights route deterministically."""

    if isinstance(value, bool):
        return 0
    try:
        weight = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return 0
    if not weight.is_finite() or weight <= 0:
        return 0
    capped = min(weight, Decimal('1000'))
    return max(1, int((capped * 1000).to_integral_value(rounding=ROUND_HALF_UP)))


def _configured_name(item: object) -> object:
    if isinstance(item, dict):
        return item.get('family', item.get('key'))
    return item


def family_settings(config: dict) -> tuple[list[FamilyTaskSettings], int]:
    """Enabled routable families and the adaptation threshold."""

    configured = config.get('families')
    items = configured if isinstance(configured, list) else [DEFAULT_FAMILY]
    allowed = routable_families()
    parsed: dict[str, FamilyTaskSettings] = {}
    for item in items:
        values = item if isinstance(item, dict) else {}
        if values.get('enabled', True) is False:
            continue
        family = resolve_family(_configured_name(item))
        if family is None or family not in allowed or family in parsed:
            continue
        units = weight_units(values.get('weight', 1))
        if units == 0:
            continue
        initial = bounded_int(values.get('initial_difficulty'), default=1, minimum=1, maximum=MAX_DIFFICULTY)
        skin = values.get('skin')
        sub_kinds = values.get('sub_kinds')
        parsed[family] = FamilyTaskSettings(
            family=family,
            weight_units=units,
            initial_difficulty=initial,
            max_difficulty=bounded_int(
                values.get('max_difficulty'), default=MAX_DIFFICULTY, minimum=initial, maximum=MAX_DIFFICULTY
            ),
            skin=skin.strip() if isinstance(skin, str) and skin.strip() else None,
            sub_kinds=tuple(kind.strip() for kind in sub_kinds if isinstance(kind, str) and kind.strip())
            if isinstance(sub_kinds, list)
            else (),
        )
    threshold = bounded_int(config.get('adaptation_threshold'), default=3, minimum=1, maximum=20)
    return sorted(parsed.values(), key=lambda item: item.family), threshold


def scripted_task(config: dict) -> ScriptedTaskSettings | None:
    """The single task pinned by the organizer to a fixed position, if any.

    Scripted tasks live outside ``families`` so the director can neither repeat
    them nor adapt their difficulty.
    """

    tasks = config.get('scripted_tasks')
    if tasks is None or tasks == []:
        return None
    if not isinstance(tasks, list) or len(tasks) != 1 or not isinstance(tasks[0], dict):
        raise ValueError('scripted_tasks must contain exactly one object')
    task = tasks[0]
    family = FAMILIES.get(resolve_family(task.get('family')) or '')
    if family is None or not family.scripted_only:
        raise ValueError('this family cannot be scripted')
    sub_kind = task.get('sub_kind')
    if not isinstance(sub_kind, str) or sub_kind not in family.sub_kinds:
        raise ValueError('sub_kind is not supported')
    position = task.get('position')
    if (
        isinstance(position, bool)
        or not isinstance(position, int)
        or not 1 <= position <= MAX_SCRIPTED_POSITION
    ):
        raise ValueError(f'scripted task position must be from 1 to {MAX_SCRIPTED_POSITION}')
    return ScriptedTaskSettings(family=family.key, sub_kind=sub_kind, position=position)


def adaptive_trajectory(config: dict) -> tuple[bool, str | None]:
    """Whether the director routes the attempt, and the configured start family."""

    trajectory = config.get('trajectory')
    if not isinstance(trajectory, dict):
        return False, None
    if str(trajectory.get('mode') or '').strip().casefold() != ADAPTIVE_MODE:
        return False, None
    if str(trajectory.get('director_version') or DIRECTOR_VERSION) != DIRECTOR_VERSION:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'DIRECTOR_VERSION_NOT_AVAILABLE',
            'Версия адаптивной траектории этого контеста не поддерживается.',
        )
    return True, resolve_family(trajectory.get('start_family'))


def validate_task_config(config: dict) -> None:
    """Reject a config the task flow could not run; raises an API error."""

    try:
        scripted_task(config)
    except ValueError as error:
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            'SCRIPTED_TASK_CONFIG_INVALID',
            'Заскриптованная задача должна быть единственным элементом scripted_tasks: classic_math '
            'с вариантом share_paradox или bar_seating и номером от 1 до 100.',
        ) from error

    configured = config.get('families')
    items = configured if isinstance(configured, list) else []
    names = [name for name in map(_configured_name, items) if isinstance(name, str)]
    trajectory = config.get('trajectory')
    start_name = trajectory.get('start_family') if isinstance(trajectory, dict) else None
    if isinstance(start_name, str):
        names.append(start_name)
    unknown = sorted({name for name in names if resolve_family(name) is None})
    if unknown:
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            'TASK_FAMILY_UNKNOWN',
            f'Семейства неизвестны или выведены из ротации контента: {", ".join(unknown)}.',
        )
    if any(resolve_family(name) not in routable_families() for name in names):
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            'TASK_FAMILY_NOT_ROUTABLE',
            'Одно из семейств можно задать только как заскриптованную задачу.',
        )

    for item in items:
        if not isinstance(item, dict) or item.get('sub_kinds') is None:
            continue
        family = FAMILIES.get(resolve_family(_configured_name(item)) or '')
        if family is None or not family.sub_kinds:
            continue
        sub_kinds = item['sub_kinds']
        if (
            not isinstance(sub_kinds, list)
            or not sub_kinds
            or any(kind not in family.sub_kinds for kind in sub_kinds)
        ):
            raise api_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                'TASK_SUB_KIND_NOT_AVAILABLE',
                f'Указан неизвестный вариант семейства {family.key}.',
            )

    if isinstance(configured, list) and not family_settings(config)[0]:
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            'TASK_FAMILY_NOT_AVAILABLE',
            'Не выбрано ни одного доступного семейства задач.',
        )
    adaptive_trajectory(config)
