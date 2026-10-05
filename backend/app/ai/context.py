from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sirius_gate import blocks

from ..models import TaskInstance, TaskInteraction
from ..tasks import FAMILIES


@dataclass(frozen=True)
class AiVisibleContext:
    payload: dict[str, Any]
    canonical_json: str
    sha256: str


def _scalar_fields(public_state: dict[str, Any]) -> dict[str, Any]:
    """Fallback for families without their own context: scalar public fields only."""

    return {key: value for key, value in public_state.items() if isinstance(value, (str, int, float, bool))}


def _default_view(public_state: dict[str, Any]):
    return blocks.for_assistant if public_state.get('kind') == blocks.KIND else _scalar_fields


def _interaction_history(interactions: list[TaskInteraction]) -> list[dict[str, Any]]:
    history = []
    for interaction in sorted(interactions, key=lambda item: item.sequence):
        request = interaction.request_payload if isinstance(interaction.request_payload, dict) else {}
        result = interaction.result_payload if isinstance(interaction.result_payload, dict) else {}
        entry: dict[str, Any] = {'action': interaction.action_type}
        if isinstance(request.get('probe'), str):
            entry['input'] = request['probe']
        elif isinstance(request.get('op_id'), str):
            entry['input'] = request['op_id']
        if isinstance(result.get('accepted'), bool):
            entry['accepted'] = result['accepted']
        message = result.get('message')
        if isinstance(message, str) and message:
            entry['result'] = message
        history.append(entry)
    return history


def build_task_context(task: TaskInstance, interactions: list[TaskInteraction]) -> AiVisibleContext:
    public = task.public_state if isinstance(task.public_state, dict) else {}
    family = FAMILIES.get(task.family)
    builder = family.ai_context if family is not None and family.ai_context else _default_view(public)
    payload = {
        'task': {
            'id': task.id,
            'family': task.family,
            'kind': public.get('kind'),
            'difficulty': task.difficulty,
            'prompt': public.get('prompt'),
        },
        'visibleState': builder(public),
        'interactionHistory': _interaction_history(interactions),
        'answerFormat': public.get('response_hint'),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return AiVisibleContext(payload=payload, canonical_json=canonical, sha256=digest)
