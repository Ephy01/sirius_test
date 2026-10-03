"""Sandbox for task authors: generate, play and check a task without a contest.

Nothing is stored. The author's browser keeps both states and sends them back,
which is acceptable because the sandbox is open to organizers only.
"""

import secrets
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, status

from ..dependencies import OrganizerDependency, api_error
from ..schemas import (
    SandboxAnswerRequest,
    SandboxAnswerResponse,
    SandboxGenerateRequest,
    SandboxInteractRequest,
    SandboxInteractResponse,
    SandboxTaskResponse,
)
from ..tasks import FAMILIES, TaskFamily, resolve_family

router = APIRouter(prefix='/sandbox')

# A browser reads the seed as a JavaScript number, which is exact only up to 2**53.
SANDBOX_SEED_BITS = 53


def _family(name: str) -> TaskFamily:
    family = FAMILIES.get(resolve_family(name) or '')
    if family is None:
        raise api_error(status.HTTP_404_NOT_FOUND, 'TASK_FAMILY_UNKNOWN', 'Такого семейства задач нет.')
    return family


def _run(step: Callable[[], Any]) -> Any:
    """Call task code and turn its failure into a message the author can read."""

    try:
        return step()
    except Exception as error:
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, 'TASK_CODE_FAILED', f'{type(error).__name__}: {error}'
        ) from error


def _reference(family: TaskFamily, private_state: dict) -> dict:
    answer, commands = (
        _run(lambda: family.reference_answer(private_state)) if family.reference_answer else (None, [])
    )
    details = _run(lambda: family.debug_details(private_state)) if family.debug_details else []
    return {'reference_answer': answer, 'reference_commands': list(commands), 'details': list(details)}


@router.post('/tasks', response_model=SandboxTaskResponse)
def generate_sandbox_task(
    payload: SandboxGenerateRequest, _organizer: OrganizerDependency
) -> SandboxTaskResponse:
    family = _family(payload.family)
    seed = payload.seed if payload.seed is not None else secrets.randbits(SANDBOX_SEED_BITS)
    context = {'sub_kinds': [payload.sub_kind]} if payload.sub_kind else {}
    public_state, private_state = _run(lambda: family.generate(seed, payload.difficulty, context))
    return SandboxTaskResponse(
        family=family.key,
        generator_version=family.version,
        seed=seed,
        difficulty=payload.difficulty,
        public_state=public_state,
        private_state=private_state,
        **_reference(family, private_state),
    )


@router.post('/interactions', response_model=SandboxInteractResponse)
def interact_in_sandbox(
    payload: SandboxInteractRequest, _organizer: OrganizerDependency
) -> SandboxInteractResponse:
    family = _family(payload.family)
    action = family.actions.get(payload.action_type)
    if action is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'TASK_INTERACTION_ACTION_NOT_SUPPORTED',
            'Эта команда не поддерживается текущей задачей.',
        )
    request = {'probe': payload.probe, 'op_id': payload.op_id}
    action_payload = {
        **{key: value for key, value in request.items() if value is not None},
        'client_action_id': secrets.token_hex(8),
        'first_action_latency_ms': 0,
    }
    transition = _run(lambda: action(action_payload, payload.public_state, payload.private_state))
    return SandboxInteractResponse(
        public_state=transition.public_state,
        private_state=transition.private_state,
        accepted=transition.accepted,
        completed=transition.completed,
        reason=transition.reason,
        message=transition.message,
        evaluation=transition.evaluation_state,
        **_reference(family, transition.private_state),
    )


@router.post('/answers', response_model=SandboxAnswerResponse)
def answer_in_sandbox(
    payload: SandboxAnswerRequest, _organizer: OrganizerDependency
) -> SandboxAnswerResponse:
    family = _family(payload.family)
    evaluation = dict(_run(lambda: family.evaluate(payload.answer, payload.private_state)))
    return SandboxAnswerResponse(
        evaluation=evaluation, finalized=evaluation.get('should_finalize') is not False
    )
