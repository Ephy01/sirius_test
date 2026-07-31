from __future__ import annotations

import json
from datetime import datetime, timezone

from .models import Attempt, Contest, Enrollment, TaskInstance, utc_now

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


def _task_lines(task: TaskInstance) -> list[str]:
    return [
        f"--- TASK ordinal={task.ordinal} ---",
        f"task_id: {task.id}",
        f"family: {_header_text(task.family)}",
        f"generator_version: {_header_text(task.generator_version)}",
        f"difficulty: {task.difficulty}",
        f"status: {task.status.value}",
        f"created_at_utc: {_utc_text(task.created_at)}",
        f"completed_at_utc: {_utc_text(task.completed_at)}",
        f"duration: {_duration_text(task.created_at, task.completed_at)}",
        f"current_public_state: {_payload_text(task.public_state)}",
    ]


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
