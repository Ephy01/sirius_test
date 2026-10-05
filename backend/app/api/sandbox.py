"""Sandbox for task authors: generate, play and check a task without a contest.

The work is done by ``sirius_gate.sandbox``, the same code the task editor runs in
the author's browser. Nothing is stored: the browser keeps the state of the task
and sends it back, which is acceptable because the sandbox is open to organizers only.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, status

from sirius_gate import sandbox
from sirius_gate.family import TaskFamily

from ..dependencies import OrganizerDependency, api_error
from ..schemas import (
    SandboxAnswerRequest,
    SandboxAnswerResponse,
    SandboxGenerateRequest,
    SandboxInteractRequest,
    SandboxInteractResponse,
    SandboxTaskResponse,
)
from ..tasks import FAMILIES, resolve_family

router = APIRouter(prefix='/sandbox')

STATUS_OF = {sandbox.ActionNotSupported: status.HTTP_409_CONFLICT}


def _family(name: str) -> TaskFamily:
    family = FAMILIES.get(resolve_family(name) or '')
    if family is None:
        raise api_error(status.HTTP_404_NOT_FOUND, 'TASK_FAMILY_UNKNOWN', 'Такого семейства задач нет.')
    return family


def _reply(step: Callable[[], Any]) -> Any:
    try:
        return step()
    except sandbox.SandboxError as error:
        code = STATUS_OF.get(type(error), status.HTTP_422_UNPROCESSABLE_ENTITY)
        raise api_error(code, error.code, str(error)) from error


@router.post('/tasks', response_model=SandboxTaskResponse)
def generate_sandbox_task(
    payload: SandboxGenerateRequest, _organizer: OrganizerDependency
) -> SandboxTaskResponse:
    family = _family(payload.family)
    return _reply(
        lambda: sandbox.generate(
            family, difficulty=payload.difficulty, seed=payload.seed, sub_kind=payload.sub_kind
        )
    )


@router.post('/interactions', response_model=SandboxInteractResponse)
def interact_in_sandbox(
    payload: SandboxInteractRequest, _organizer: OrganizerDependency
) -> SandboxInteractResponse:
    family = _family(payload.family)
    return _reply(
        lambda: sandbox.interact(
            family,
            action_type=payload.action_type,
            state=payload.state,
            probe=payload.probe,
            op_id=payload.op_id,
        )
    )


@router.post('/answers', response_model=SandboxAnswerResponse)
def answer_in_sandbox(
    payload: SandboxAnswerRequest, _organizer: OrganizerDependency
) -> SandboxAnswerResponse:
    family = _family(payload.family)
    return _reply(lambda: sandbox.answer(family, answer=payload.answer, state=payload.state))
