"""Safe, family-aware serialization of the visible task state for the model.

Единственный источник данных — ``task.public_state`` (то, что уже отрисовано
участнику) и видимые ``TaskInteraction``. Никаких private_state, сидов,
эталонных ответов и вычисленных математических признаков: сериализаторы
только переупаковывают уже показанное.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

from ..models import TaskInstance, TaskInteraction

# Rendered classification labels, matching what the participant UI shows.
_CLASSIFICATION_LABELS = {
    "positive": "подходит",
    "negative": "не подходит",
}


@dataclass(frozen=True)
class AiVisibleContext:
    payload: dict[str, Any]
    canonical_json: str
    sha256: str


def _classification_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _CLASSIFICATION_LABELS.get(value, value)


def _card_role(card_id: str, classification: str | None, tested: bool) -> str:
    if card_id.startswith("E"):
        return (
            "positive_example"
            if classification == "подходит"
            else "negative_example"
        )
    if card_id.startswith("T"):
        return "target"
    return "tested_probe" if tested else "available_probe"


def _zendo_visibility(public: dict[str, Any]) -> tuple[dict[str, str], dict[str, str | None]]:
    """Roles and *already revealed* classifications for every visible card."""

    content = public.get("content") if isinstance(public.get("content"), dict) else {}
    classification: dict[str, str | None] = {}
    tested: set[str] = set()
    for example in content.get("examples") or []:
        if isinstance(example, dict) and isinstance(example.get("card_id"), str):
            classification[example["card_id"]] = _classification_label(
                example.get("classification")
            )
    for observation in content.get("probe_observations") or []:
        if isinstance(observation, dict) and isinstance(observation.get("card_id"), str):
            card_id = observation["card_id"]
            tested.add(card_id)
            classification[card_id] = _classification_label(
                observation.get("classification")
            )
    roles: dict[str, str] = {}
    for example in content.get("examples") or []:
        if isinstance(example, dict) and isinstance(example.get("card_id"), str):
            card_id = example["card_id"]
            roles[card_id] = _card_role(card_id, classification.get(card_id), False)
    for probe in content.get("probe_cards") or []:
        if isinstance(probe, dict) and isinstance(probe.get("card_id"), str):
            card_id = probe["card_id"]
            roles[card_id] = _card_role(card_id, None, card_id in tested)
    for target in content.get("targets") or []:
        if isinstance(target, dict) and isinstance(target.get("card_id"), str):
            roles[target["card_id"]] = "target"
    return roles, classification


def _zendo_limits(public: dict[str, Any]) -> dict[str, Any]:
    content = public.get("content") if isinstance(public.get("content"), dict) else {}
    return {
        "probesRemaining": content.get("probes_remaining"),
        "probeBudget": content.get("probe_budget"),
    }


def _graph_cards(public: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Group the shared scene into per-card vertex/edge lists."""

    scene = public.get("scene") if isinstance(public.get("scene"), dict) else {}
    cards: dict[str, dict[str, Any]] = {}
    for point in scene.get("points") or []:
        if not isinstance(point, dict):
            continue
        group = point.get("group")
        if not isinstance(group, str):
            continue
        card = cards.setdefault(group, {"vertices": [], "edges": []})
        card["vertices"].append(
            {
                "id": point.get("id"),
                "label": point.get("label"),
                "x": point.get("x"),
                "y": point.get("y"),
                "color": point.get("color"),
            }
        )
    for edge in scene.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        group = edge.get("group")
        if not isinstance(group, str):
            continue
        card = cards.setdefault(group, {"vertices": [], "edges": []})
        card["edges"].append(
            {
                "source": edge.get("source"),
                "target": edge.get("target"),
                "directed": False,
            }
        )
    return cards


def _build_scene_zendo_context(public: dict[str, Any]) -> dict[str, Any]:
    """geo_zendo / point_zendo: карточки — подграфы общей сцены."""

    roles, classifications = _zendo_visibility(public)
    cards = _graph_cards(public)
    visible = []
    for card_id in sorted(roles):
        card = cards.get(card_id, {"vertices": [], "edges": []})
        visible.append(
            {
                "id": card_id,
                "role": roles[card_id],
                "classification": classifications.get(card_id),
                "vertices": card["vertices"],
                "edges": card["edges"],
            }
        )
    return {"cards": visible, "limits": _zendo_limits(public)}


def _build_token_zendo_context(public: dict[str, Any]) -> dict[str, Any]:
    roles, classifications = _zendo_visibility(public)
    cards_value = public.get("cards") if isinstance(public.get("cards"), dict) else {}
    visible = []
    for card_id in sorted(roles):
        tokens = cards_value.get(card_id)
        visible.append(
            {
                "id": card_id,
                "role": roles[card_id],
                "classification": classifications.get(card_id),
                "tokens": tokens if isinstance(tokens, list) else [],
            }
        )
    return {"cards": visible, "limits": _zendo_limits(public)}


def _build_grid_zendo_context(public: dict[str, Any]) -> dict[str, Any]:
    roles, classifications = _zendo_visibility(public)
    cards_value = public.get("cards") if isinstance(public.get("cards"), dict) else {}
    visible = []
    for card_id in sorted(set(roles) | set(cards_value)):
        rows = cards_value.get(card_id)
        visible.append(
            {
                "id": card_id,
                "role": roles.get(card_id, "tested_probe"),
                "classification": classifications.get(card_id),
                "rows": rows if isinstance(rows, list) else None,
            }
        )
    content = public.get("content") if isinstance(public.get("content"), dict) else {}
    observations = [
        {
            "pattern": observation.get("card_id"),
            "classification": _classification_label(observation.get("classification")),
        }
        for observation in content.get("probe_observations") or []
        if isinstance(observation, dict)
    ]
    return {
        "gridSize": public.get("grid_size"),
        "cards": visible,
        "drawnProbes": observations,
        "limits": _zendo_limits(public),
    }


def _build_hidden_wiring_context(public: dict[str, Any]) -> dict[str, Any]:
    return {
        "legend": public.get("legend"),
        "variant": public.get("variant"),
        "lampCount": public.get("lamp_count"),
        "buttonCount": public.get("button_count"),
        "availableChords": public.get("ops"),
        "startLamps": public.get("start"),
        "currentLamps": public.get("current"),
        "targetLamps": public.get("target"),
        "examChords": public.get("exam_chords"),
        "observations": public.get("observations"),
        "limits": {
            "chordsRemaining": public.get("chords_remaining"),
            "chordBudget": public.get("chord_budget"),
            "firstChordIsFreeTraining": public.get("free_training_probe"),
        },
    }


_MACHINE_KEYS = (
    "sub_kind",
    "ops",
    "start",
    "current",
    "target",
    "steps_soft_cap",
    "steps_taken",
    "history",
    "rows",
    "cols",
    "blocked",
    "jump",
    "board",
    "modulus",
    "cards",
    "value",
)


def _build_machine_context(public: dict[str, Any]) -> dict[str, Any]:
    return {key: public.get(key) for key in _MACHINE_KEYS if key in public}


def _build_fold_punch_context(public: dict[str, Any]) -> dict[str, Any]:
    return {
        "sheetSize": public.get("sheet_size"),
        "folds": public.get("folds"),
        "foldedSheet": public.get("folded"),
    }


_DICE_CHESS_KEYS = (
    "board",
    "die",
    "dice",
    "side_to_move",
    "event_description",
    "sample_space_size",
)


def _build_dice_chess_context(public: dict[str, Any]) -> dict[str, Any]:
    return {key: public.get(key) for key in _DICE_CHESS_KEYS if key in public}


def _build_geo_transform_context(public: dict[str, Any]) -> dict[str, Any]:
    content = public.get("content") if isinstance(public.get("content"), dict) else {}
    cards = _graph_cards(public)
    def _group(group: Any) -> dict[str, Any]:
        if isinstance(group, str) and group in cards:
            return {"id": group, **cards[group]}
        return {"id": group, "vertices": [], "edges": []}
    return {
        "source": _group(content.get("source_group")),
        "image": _group(content.get("image_group")),
        "answerCards": content.get("answer_cards"),
    }


def _build_geo_probability_context(public: dict[str, Any]) -> dict[str, Any]:
    content = public.get("content") if isinstance(public.get("content"), dict) else {}
    cards = _graph_cards(public)
    return {
        "figures": [
            {"id": group, **card} for group, card in sorted(cards.items())
        ],
        "eventDescription": content.get("event_description"),
        "sampleSpaceDescription": content.get("sample_space_description"),
        "sampleSpaceSize": content.get("sample_space_size"),
    }


def _build_generic_context(public: dict[str, Any]) -> dict[str, Any]:
    """Fallback: только безопасные скалярные поля public_state."""

    return {
        key: value
        for key, value in public.items()
        if isinstance(value, (str, int, float, bool))
    }


CONTEXT_BUILDERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "geo_zendo": _build_scene_zendo_context,
    "point_zendo": _build_scene_zendo_context,
    "token_zendo": _build_token_zendo_context,
    "grid_zendo": _build_grid_zendo_context,
    "hidden_wiring": _build_hidden_wiring_context,
    "machine_reach": _build_machine_context,
    "fold_punch": _build_fold_punch_context,
    "dice_chess": _build_dice_chess_context,
    "geo_transform": _build_geo_transform_context,
    "geo_probability": _build_geo_probability_context,
}


def _interaction_history(interactions: list[TaskInteraction]) -> list[dict[str, Any]]:
    history = []
    for interaction in sorted(interactions, key=lambda item: item.sequence):
        request = (
            interaction.request_payload
            if isinstance(interaction.request_payload, dict)
            else {}
        )
        result = (
            interaction.result_payload
            if isinstance(interaction.result_payload, dict)
            else {}
        )
        entry: dict[str, Any] = {"action": interaction.action_type}
        if isinstance(request.get("probe"), str):
            entry["input"] = request["probe"]
        elif isinstance(request.get("op_id"), str):
            entry["input"] = request["op_id"]
        if isinstance(result.get("accepted"), bool):
            entry["accepted"] = result["accepted"]
        message = result.get("message")
        if isinstance(message, str) and message:
            entry["result"] = message
        history.append(entry)
    return history


def build_task_context(
    task: TaskInstance,
    interactions: list[TaskInteraction],
) -> AiVisibleContext:
    public = task.public_state if isinstance(task.public_state, dict) else {}
    builder = CONTEXT_BUILDERS.get(task.family, _build_generic_context)
    payload = {
        "task": {
            "id": task.id,
            "family": task.family,
            "kind": public.get("kind"),
            "difficulty": task.difficulty,
            "prompt": public.get("prompt"),
        },
        "visibleState": builder(public),
        "interactionHistory": _interaction_history(interactions),
        "answerFormat": public.get("response_hint"),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return AiVisibleContext(payload=payload, canonical_json=canonical, sha256=digest)
