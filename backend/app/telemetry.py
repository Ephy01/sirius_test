from __future__ import annotations

import json
from datetime import datetime, timezone

from .environments import IMPLEMENTED_FAMILIES
from .models import (
    AiTurn,
    AiTurnStatus,
    Attempt,
    Contest,
    Enrollment,
    TaskInstance,
    utc_now,
)

TELEMETRY_FORMAT_VERSION = "1"
REDACTED_VALUE = "[REDACTED]"
SENSITIVE_PAYLOAD_KEYS = frozenset(
    {
        "access_code",
        "access_token",
        "authorization",
        "code",
        "code_hmac_secret",
        "cohort_seed",
        "lookup_hash",
        "private_state",
        "security_secret",
        "seed",
        "token",
    }
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_text(value: datetime | None) -> str:
    if value is None:
        return "-"
    return _as_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _header_text(value: object) -> str:
    return " ".join(str(value).splitlines())


def _elapsed_ms(later: datetime, earlier: datetime) -> int:
    return max(
        0,
        int((_as_utc(later) - _as_utc(earlier)).total_seconds() * 1000),
    )


def _duration_text(started_at: datetime, finished_at: datetime | None) -> str:
    if finished_at is None:
        return "open"
    return f"{_elapsed_ms(finished_at, started_at)}ms"


def _redact_payload(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): (
                REDACTED_VALUE
                if str(key).casefold() in SENSITIVE_PAYLOAD_KEYS
                else _redact_payload(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_payload(child) for child in value]
    return value


def _payload_text(value: object) -> str:
    encoded = json.dumps(
        _redact_payload(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    # JSON permits these Unicode separators as literal characters, while many
    # editors render them as line breaks. Escape them so one event always
    # remains exactly one physical line in the exported timeline.
    return (
        encoded.replace("\u0085", "\\u0085")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _family_text(family: object) -> str:
    """Label rows of families that were removed from the content rotation.

    The export must stay readable for historical attempts whose family no
    longer exists in the registry.
    """

    text = _header_text(family)
    if str(family) not in IMPLEMENTED_FAMILIES:
        return f"{text} (retired)"
    return text


def _continuous_score(task: TaskInstance) -> float | None:
    evaluation = (
        task.evaluation_state
        if isinstance(task.evaluation_state, dict)
        else {}
    )
    value = evaluation.get("continuous_score")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _learning_slopes(tasks: list[TaskInstance]) -> list[tuple[str, float | None]]:
    """Per-family OLS slope of continuous_score over the encounter index.

    A research export only (never part of season-one scoring): the slope
    is ``null`` while a family has fewer than two scored encounters.
    """

    scores_by_family: dict[str, list[float]] = {}
    for task in tasks:
        score = _continuous_score(task)
        if score is None:
            continue
        scores_by_family.setdefault(task.family, []).append(score)
    slopes: list[tuple[str, float | None]] = []
    for family in sorted(scores_by_family):
        scores = scores_by_family[family]
        if len(scores) < 2:
            slopes.append((family, None))
            continue
        count = len(scores)
        mean_x = (count + 1) / 2
        mean_y = sum(scores) / count
        covariance = sum(
            (index - mean_x) * (score - mean_y)
            for index, score in enumerate(scores, start=1)
        )
        variance = sum(
            (index - mean_x) ** 2
            for index in range(1, count + 1)
        )
        slopes.append((family, covariance / variance))
    return slopes


def _task_lines(task: TaskInstance) -> list[str]:
    return [
        f"--- TASK ordinal={task.ordinal} ---",
        f"task_id: {task.id}",
        f"family: {_family_text(task.family)}",
        f"generator_version: {_header_text(task.generator_version)}",
        f"difficulty: {task.difficulty}",
        f"status: {task.status.value}",
        f"created_at_utc: {_utc_text(task.created_at)}",
        f"completed_at_utc: {_utc_text(task.completed_at)}",
        f"duration: {_duration_text(task.created_at, task.completed_at)}",
        f"current_public_state: {_payload_text(task.public_state)}",
    ]


def _indent_block(text: str) -> list[str]:
    return [f"  {line}" for line in text.splitlines()] or ["  (пусто)"]


def _ai_transcript_lines(attempt: Attempt, tasks: list[TaskInstance]) -> list[str]:
    """Full dialogue transcript plus usage totals (ТЗ Alice AI §19)."""

    turns: list[tuple[TaskInstance, AiTurn]] = [
        (task, turn)
        for task in tasks
        for turn in sorted(task.ai_turns, key=lambda item: item.sequence)
    ]
    turns.sort(key=lambda pair: (pair[1].created_at, pair[1].sequence))
    lines = ["--- AI TRANSCRIPT ---"]
    if not turns:
        lines.append("(no ai turns)")
        return lines

    completed = 0
    failed = 0
    total_input = 0
    total_output = 0
    latencies: list[int] = []
    tasks_with_ai: set[str] = set()
    for task, turn in turns:
        tasks_with_ai.add(task.id)
        lines.append("")
        lines.append(
            f"[{_utc_text(turn.created_at)}] TASK {task.ordinal} / USER"
        )
        lines.extend(_indent_block(turn.user_message))
        if turn.status == AiTurnStatus.COMPLETED:
            completed += 1
            lines.append(
                f"[{_utc_text(turn.completed_at)}] TASK {task.ordinal} / ALICE AI"
            )
            lines.extend(_indent_block(turn.assistant_message or ""))
        else:
            failed += 1
            lines.append(
                f"[{_utc_text(turn.completed_at)}] TASK {task.ordinal} / "
                f"{turn.status.value.upper()}"
            )
        lines.append(f"  model: {_header_text(turn.model_version or turn.model_uri)}")
        lines.append(f"  latency_ms: {turn.latency_ms if turn.latency_ms is not None else '-'}")
        lines.append(f"  input_tokens: {turn.input_tokens if turn.input_tokens is not None else '-'}")
        lines.append(f"  output_tokens: {turn.output_tokens if turn.output_tokens is not None else '-'}")
        lines.append(f"  prompt_version: {_header_text(turn.prompt_version)}")
        lines.append(f"  context_hash: {turn.public_context_hash}")
        lines.append(f"  status: {turn.status.value}")
        if turn.error_code:
            lines.append(f"  error_code: {_header_text(turn.error_code)}")
        total_input += turn.input_tokens or 0
        total_output += turn.output_tokens or 0
        if turn.latency_ms is not None:
            latencies.append(turn.latency_ms)

    flagged = sum(1 for _task, turn in turns if turn.provider == "tripwire")
    lines.append("")
    lines.append("--- AI SUMMARY ---")
    lines.append(f"ai_turns_completed: {completed}")
    lines.append(f"ai_turns_failed: {failed}")
    lines.append(f"ai_messages_flagged: {flagged}")
    lines.append(f"ai_total_input_tokens: {total_input}")
    lines.append(f"ai_total_output_tokens: {total_output}")
    lines.append(
        "ai_latency_avg_ms: "
        + (str(round(sum(latencies) / len(latencies))) if latencies else "-")
    )
    lines.append(
        "ai_latency_max_ms: " + (str(max(latencies)) if latencies else "-")
    )
    lines.append(f"ai_tasks_with_dialogue: {len(tasks_with_ai)}")
    return lines


def _attempt_lines(attempt: Attempt) -> list[str]:
    tasks = sorted(attempt.tasks, key=lambda task: (task.ordinal, task.id))
    events = sorted(attempt.events, key=lambda event: (event.sequence, event.id))
    tasks_by_id = {task.id: task for task in tasks}
    lines = [
        f"=== ATTEMPT number={attempt.number} ===",
        f"attempt_id: {attempt.id}",
        f"status: {attempt.status.value}",
        f"started_at_utc: {_utc_text(attempt.started_at)}",
        f"deadline_at_utc: {_utc_text(attempt.deadline_at)}",
        f"finished_at_utc: {_utc_text(attempt.finished_at)}",
        f"duration: {_duration_text(attempt.started_at, attempt.finished_at)}",
        f"task_count: {len(tasks)}",
        f"event_count: {len(events)}",
        "",
    ]
    if tasks:
        for task in tasks:
            lines.extend(_task_lines(task))
            lines.append("")
    else:
        lines.extend(["--- NO TASKS ---", ""])

    lines.append("--- LEARNING SLOPES ---")
    slopes = _learning_slopes(tasks)
    if slopes:
        for family, slope in slopes:
            lines.append(
                "learning_slope "
                f"{_family_text(family)}: "
                + ("null" if slope is None else f"{slope:+.4f}")
            )
    else:
        lines.append("(no scored tasks)")
    lines.append("")

    lines.extend(_ai_transcript_lines(attempt, tasks))
    lines.append("")

    lines.append("--- EVENT TIMELINE ---")
    previous_timestamp: datetime | None = None
    for event in events:
        event_payload = event.payload if isinstance(event.payload, dict) else {}
        client_payload = event_payload.get("payload")
        if not isinstance(client_payload, dict):
            client_payload = {}
        client_timestamp = event_payload.get("client_timestamp")
        client_elapsed_ms = event_payload.get("client_elapsed_ms")
        client_sequence = client_payload.get("client_sequence")
        task = (
            tasks_by_id.get(event.task_instance_id)
            if event.task_instance_id is not None
            else None
        )
        delta_previous = (
            0
            if previous_timestamp is None
            else _elapsed_ms(event.created_at, previous_timestamp)
        )
        task_elapsed = (
            f"{_elapsed_ms(event.created_at, task.created_at)}ms"
            if task is not None
            else "-"
        )
        lines.append(
            " | ".join(
                (
                    f"seq={event.sequence:06d}",
                    f"utc={_utc_text(event.created_at)}",
                    f"t+attempt={_elapsed_ms(event.created_at, attempt.started_at)}ms",
                    f"delta_previous={delta_previous}ms",
                    f"client_utc={_header_text(client_timestamp) if client_timestamp else '-'}",
                    (
                        f"client_t+session={client_elapsed_ms}ms"
                        if isinstance(client_elapsed_ms, int)
                        else "client_t+session=-"
                    ),
                    (
                        f"client_seq={client_sequence}"
                        if isinstance(client_sequence, int)
                        else "client_seq=-"
                    ),
                    f"task_ordinal={task.ordinal if task is not None else '-'}",
                    f"task_id={event.task_instance_id or '-'}",
                    f"t+task={task_elapsed}",
                    f"type={_header_text(event.event_type)}",
                    f"payload={_payload_text(event.payload)}",
                )
            )
        )
        previous_timestamp = event.created_at
    if not events:
        lines.append("(no events)")
    return lines


def format_enrollment_telemetry(
    *,
    contest: Contest,
    enrollment: Enrollment,
    attempts: list[Attempt],
    generated_at: datetime | None = None,
) -> str:
    participant = enrollment.participant
    ordered_attempts = sorted(attempts, key=lambda attempt: (attempt.number, attempt.id))
    lines = [
        "SIRIUS GATE PARTICIPANT TELEMETRY",
        f"format_version: {TELEMETRY_FORMAT_VERSION}",
        f"generated_at_utc: {_utc_text(generated_at or utc_now())}",
        f"contest_id: {contest.id}",
        f"contest_title: {_header_text(contest.title)}",
        f"enrollment_id: {enrollment.id}",
        f"participant_id: {participant.id}",
        f"participant_external_ref: {_header_text(participant.external_ref)}",
        f"participant_display_name: {_header_text(participant.display_name)}",
        f"attempt_count: {len(ordered_attempts)}",
        "",
    ]
    if not ordered_attempts:
        lines.append("=== NO ATTEMPTS ===")
    else:
        for index, attempt in enumerate(ordered_attempts):
            if index:
                lines.append("")
            lines.extend(_attempt_lines(attempt))
    return "\n".join(lines) + "\n"
