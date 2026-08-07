import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import (
    AccessCodeStatus,
    AttemptStatus,
    ContestStatus,
    EnrollmentStatus,
    TaskStatus,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def normalize_naive_datetimes_as_utc(self):
        for field_name in type(self).model_fields:
            value = getattr(self, field_name, None)
            if isinstance(value, datetime) and value.tzinfo is None:
                setattr(self, field_name, value.replace(tzinfo=timezone.utc))
        return self


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    service: str


class AccessRedeemRequest(ApiModel):
    code: str = Field(min_length=3, max_length=80)

    @field_validator("code")
    @classmethod
    def clean_code(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("code must not be blank")
        return cleaned


class AccessRedeemResponse(ApiModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    role: Literal["organizer", "participant"]
    expires_at: datetime


class ContestCreate(ApiModel):
    title: str = Field(min_length=1, max_length=200)
    duration_minutes: int = Field(default=60, ge=5, le=480)
    environment_key: Literal["mixed", "chess_world", "geometry_world"] = "mixed"
    task_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must not be blank")
        return cleaned


class ContestResponse(ApiModel):
    id: str
    title: str
    duration_minutes: int
    environment_key: str
    task_config: dict[str, Any]
    status: ContestStatus
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class ContestListResponse(ApiModel):
    items: list[ContestResponse]


class ParticipantContestResponse(ApiModel):
    """Contest metadata that is safe to expose before and during an attempt."""

    id: str
    title: str
    duration_minutes: int
    environment_key: str
    status: ContestStatus
    created_at: datetime
    published_at: datetime | None


class ParticipantInput(ApiModel):
    external_ref: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=200)

    @field_validator("external_ref", "display_name")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be blank")
        return cleaned


class EnrollmentBulkCreate(ApiModel):
    participants: list[ParticipantInput] = Field(min_length=1, max_length=1_000)

    @field_validator("participants")
    @classmethod
    def unique_external_refs(cls, value: list[ParticipantInput]) -> list[ParticipantInput]:
        refs = [participant.external_ref for participant in value]
        if len(set(refs)) != len(refs):
            raise ValueError("external_ref values must be unique within the request")
        return value


class ParticipantResponse(ApiModel):
    id: str
    external_ref: str
    display_name: str


class EnrollmentResponse(ApiModel):
    id: str
    contest_id: str
    participant_id: str
    status: EnrollmentStatus
    participant: ParticipantResponse
    created_at: datetime


class EnrollmentBulkResponse(ApiModel):
    items: list[EnrollmentResponse]
    created_count: int


class CodeGenerationRequest(ApiModel):
    rotate: bool = False
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_future(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        if normalized <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        return normalized


class CodeRotationRequest(ApiModel):
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_future(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        if normalized <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        return normalized


class GeneratedCodeResponse(ApiModel):
    enrollment_id: str
    participant: ParticipantResponse
    code: str
    last4: str
    status: AccessCodeStatus
    expires_at: datetime | None


class CodeGenerationResponse(ApiModel):
    items: list[GeneratedCodeResponse]
    generated_count: int
    skipped_count: int


class AttemptResponse(ApiModel):
    id: str
    enrollment_id: str
    number: int
    status: AttemptStatus
    started_at: datetime
    deadline_at: datetime
    finished_at: datetime | None


class AttemptStartResponse(ApiModel):
    attempt: AttemptResponse
    created: bool


class AccessCodeSummary(ApiModel):
    id: str
    last4: str
    status: AccessCodeStatus
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    redeemed_at: datetime | None


class OrganizerAttemptSummary(ApiModel):
    id: str
    number: int
    status: AttemptStatus
    started_at: datetime
    deadline_at: datetime
    finished_at: datetime | None


class OrganizerEnrollmentResponse(ApiModel):
    id: str
    contest_id: str
    participant_id: str
    status: EnrollmentStatus
    participant: ParticipantResponse
    created_at: datetime
    latest_code: AccessCodeSummary | None
    latest_attempt: OrganizerAttemptSummary | None
    attempt_grant_pending: bool


class OrganizerEnrollmentListResponse(ApiModel):
    items: list[OrganizerEnrollmentResponse]


class AttemptGrantResponse(ApiModel):
    enrollment_id: str
    pending: bool
    created: bool
    granted_at: datetime


class ParticipantContextResponse(ApiModel):
    contest: ParticipantContestResponse
    enrollment: EnrollmentResponse
    participant: ParticipantResponse
    active_attempt: AttemptResponse | None


ClientTelemetryEventType = Literal[
    "client_task_viewed",
    "client_command_submitted",
    "client_focus",
    "client_blur",
    "client_visibility_visible",
    "client_visibility_hidden",
    "client_chat_paste",
    "client_copy",
]


class ClientTelemetryRequest(ApiModel):
    client_event_id: str = Field(min_length=1, max_length=128)
    client_session_id: str = Field(min_length=1, max_length=128)
    event_type: ClientTelemetryEventType
    attempt_id: str | None = Field(default=None, min_length=1, max_length=36)
    task_id: str | None = Field(default=None, min_length=1, max_length=36)
    client_timestamp: datetime | None = None
    client_elapsed_ms: int | None = Field(
        default=None,
        ge=0,
        le=604_800_000,
        strict=True,
    )
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("client_event_id", "client_session_id")
    @classmethod
    def clean_client_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("client identifier must not be blank")
        if any(
            not (
                character.isascii()
                and (character.isalnum() or character in {"-", "_", ".", ":"})
            )
            for character in cleaned
        ):
            raise ValueError("client identifier contains unsupported characters")
        return cleaned

    @field_validator("attempt_id", "task_id")
    @classmethod
    def clean_optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("identifier must not be blank")
        return cleaned

    @field_validator("payload")
    @classmethod
    def bound_payload_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 64:
            raise ValueError("payload has too many top-level fields")
        try:
            encoded = json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ValueError("payload must be valid JSON") from error
        if len(encoded) > 8_192:
            raise ValueError("payload exceeds 8 KiB")
        return value


class TaskResponse(ApiModel):
    id: str
    ordinal: int
    family: str
    generator_version: str
    difficulty: int
    status: TaskStatus
    public_state: dict[str, Any]
    created_at: datetime
    completed_at: datetime | None


class TaskProgressItem(ApiModel):
    ordinal: int
    status: TaskStatus


class TaskProgressResponse(ApiModel):
    items: list[TaskProgressItem]


class CurrentTaskResponse(ApiModel):
    task: TaskResponse | None


class NextTaskResponse(ApiModel):
    task: TaskResponse
    created: bool


class TaskAnswerRequest(ApiModel):
    answer: str = Field(min_length=1, max_length=4_000)

    @field_validator("answer")
    @classmethod
    def answer_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer must not be blank")
        return value


class TaskActionResponse(ApiModel):
    task: TaskResponse
    message: str


class TaskInteractionRequest(ApiModel):
    client_action_id: str = Field(min_length=1, max_length=128)
    action_type: Literal["probe", "apply_op", "undo", "hint"]
    probe: str | None = Field(default=None, min_length=1, max_length=80)
    op_id: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("client_action_id")
    @classmethod
    def clean_interaction_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be blank")
        return cleaned

    @model_validator(mode="after")
    def validate_action_payload(self):
        if self.action_type == "probe":
            if self.probe is None or not self.probe.strip():
                raise ValueError("probe action requires probe")
            self.probe = self.probe.strip()
            if self.op_id is not None:
                raise ValueError("probe action contains an unrelated payload")
        elif self.action_type == "apply_op":
            if self.op_id is None or not self.op_id.strip():
                raise ValueError("apply_op action requires op_id")
            self.op_id = self.op_id.strip()
            if self.probe is not None:
                raise ValueError("apply_op action contains an unrelated payload")
        elif any(value is not None for value in (self.probe, self.op_id)):
            raise ValueError(
                f"{self.action_type} action must not contain a payload"
            )
        return self


class TaskInteractionResponse(ApiModel):
    task: TaskResponse
    accepted: bool
    completed: bool
    message: str
    client_action_id: str


class DebugAnswerResponse(ApiModel):
    """Reference answer for the active task (organizer debug mode only)."""

    family: str
    answer: str
    commands: list[str]
    details: list[str]


class AiTurnRequest(ApiModel):
    """Participant message to the assistant (ТЗ Alice AI, §9.1: camelCase)."""

    client_action_id: str = Field(
        min_length=1, max_length=128, alias="clientActionId"
    )
    message: str = Field(min_length=1, max_length=16_000)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("client_action_id")
    @classmethod
    def clean_action_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("clientActionId must not be blank")
        return cleaned


class AiTurnUsage(ApiModel):
    input_tokens: int | None = Field(default=None, serialization_alias="inputTokens")
    output_tokens: int | None = Field(default=None, serialization_alias="outputTokens")
    total_tokens: int | None = Field(default=None, serialization_alias="totalTokens")


class AiTurnRemaining(ApiModel):
    task: int
    attempt: int


class AiTurnResponse(ApiModel):
    id: str
    status: str
    assistant_message: str | None = Field(
        default=None, serialization_alias="assistantMessage"
    )
    model: str
    usage: AiTurnUsage
    remaining: AiTurnRemaining


class AiTurnHistoryItem(ApiModel):
    id: str
    status: str
    user_message: str = Field(serialization_alias="userMessage")
    assistant_message: str | None = Field(
        default=None, serialization_alias="assistantMessage"
    )
    created_at: datetime = Field(serialization_alias="createdAt")
    completed_at: datetime | None = Field(
        default=None, serialization_alias="completedAt"
    )


class AiTurnHistoryResponse(ApiModel):
    turns: list[AiTurnHistoryItem]
    remaining: AiTurnRemaining
