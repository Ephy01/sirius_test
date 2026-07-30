from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def uuid_string() -> str:
    return str(uuid.uuid4())


def enum_type(enum_class: type[enum.Enum], name: str) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
    )


class ContestStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class EnrollmentStatus(str, enum.Enum):
    REGISTERED = "registered"
    DISABLED = "disabled"


class AccessCodeStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class AttemptStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


class AttemptGrantStatus(str, enum.Enum):
    PENDING = "pending"
    CONSUMED = "consumed"


class TaskStatus(str, enum.Enum):
    ACTIVE = "active"
    ANSWERED = "answered"
    SKIPPED = "skipped"


class Contest(Base):
    __tablename__ = "contests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    environment_key: Mapped[str] = mapped_column(
        String(80), nullable=False, default="mixed"
    )
    task_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[ContestStatus] = mapped_column(
        enum_type(ContestStatus, "contest_status"),
        nullable=False,
        default=ContestStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    enrollments: Mapped[list[Enrollment]] = relationship(
        back_populates="contest", cascade="all, delete-orphan"
    )


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    external_ref: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="participant")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("contest_id", "participant_id", name="uq_enrollment_contest_participant"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    contest_id: Mapped[str] = mapped_column(
        ForeignKey("contests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        enum_type(EnrollmentStatus, "enrollment_status"),
        nullable=False,
        default=EnrollmentStatus.REGISTERED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    contest: Mapped[Contest] = relationship(back_populates="enrollments")
    participant: Mapped[Participant] = relationship(back_populates="enrollments")
    access_codes: Mapped[list[AccessCode]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan"
    )
    attempts: Mapped[list[Attempt]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan"
    )
    attempt_grants: Mapped[list[AttemptGrant]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan"
    )


class AccessCode(Base):
    __tablename__ = "access_codes"
    __table_args__ = (
        # As with attempts, NULLs stay non-conflicting while true marks the sole active row.
        UniqueConstraint("enrollment_id", "active_slot", name="uq_access_code_one_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    enrollment_id: Mapped[str] = mapped_column(
        ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lookup_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[AccessCodeStatus] = mapped_column(
        enum_type(AccessCodeStatus, "access_code_status"),
        nullable=False,
        default=AccessCodeStatus.ACTIVE,
    )
    active_slot: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    enrollment: Mapped[Enrollment] = relationship(back_populates="access_codes")


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "number", name="uq_attempt_enrollment_number"),
        # SQL treats NULLs as distinct, so only rows with active_slot=true are unique.
        UniqueConstraint("enrollment_id", "active_slot", name="uq_attempt_one_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    enrollment_id: Mapped[str] = mapped_column(
        ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[AttemptStatus] = mapped_column(
        enum_type(AttemptStatus, "attempt_status"),
        nullable=False,
        default=AttemptStatus.ACTIVE,
    )
    active_slot: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    enrollment: Mapped[Enrollment] = relationship(back_populates="attempts")
    tasks: Mapped[list[TaskInstance]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )
    events: Mapped[list[AttemptEvent]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


class AttemptGrant(Base):
    """A persistent, one-shot permission to start the next retry.

    Consumed grants are retained for auditability. ``pending_slot`` is true
    only while the grant can be consumed, which lets the database enforce at
    most one pending grant for an enrollment while retaining its full history.
    """

    __tablename__ = "attempt_grants"
    __table_args__ = (
        UniqueConstraint(
            "enrollment_id",
            "pending_slot",
            name="uq_attempt_grant_one_pending",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    enrollment_id: Mapped[str] = mapped_column(
        ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[AttemptGrantStatus] = mapped_column(
        enum_type(AttemptGrantStatus, "attempt_grant_status"),
        nullable=False,
        default=AttemptGrantStatus.PENDING,
    )
    pending_slot: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("attempts.id", ondelete="SET NULL"), nullable=True, unique=True
    )

    enrollment: Mapped[Enrollment] = relationship(back_populates="attempt_grants")
    consumed_attempt: Mapped[Attempt | None] = relationship()


class TaskInstance(Base):
    __tablename__ = "task_instances"
    __table_args__ = (
        UniqueConstraint("attempt_id", "ordinal", name="uq_task_attempt_ordinal"),
        # NULLs remain non-conflicting while true identifies the one current task.
        UniqueConstraint("attempt_id", "active_slot", name="uq_task_one_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    family: Mapped[str] = mapped_column(String(80), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(80), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        enum_type(TaskStatus, "task_status"),
        nullable=False,
        default=TaskStatus.ACTIVE,
    )
    active_slot: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=True)
    public_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    private_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    participant_answer: Mapped[str | None] = mapped_column(Text)
    evaluation_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempt: Mapped[Attempt] = relationship(back_populates="tasks")
    events: Mapped[list[AttemptEvent]] = relationship(back_populates="task")
    interactions: Mapped[list[TaskInteraction]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskInteraction(Base):
    """One idempotent participant action inside a stateful task."""

    __tablename__ = "task_interactions"
    __table_args__ = (
        UniqueConstraint(
            "task_instance_id",
            "sequence",
            name="uq_task_interaction_sequence",
        ),
        UniqueConstraint(
            "task_instance_id",
            "client_action_id",
            name="uq_task_interaction_client_action",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    task_instance_id: Mapped[str] = mapped_column(
        ForeignKey("task_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    client_action_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    task: Mapped[TaskInstance] = relationship(back_populates="interactions")


class AttemptEvent(Base):
    """Immutable-by-convention telemetry record.

    Application code only inserts these rows. There are deliberately no update
    or delete endpoints for event data.
    """

    __tablename__ = "attempt_events"
    __table_args__ = (
        UniqueConstraint("attempt_id", "sequence", name="uq_attempt_event_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_instances.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )

    attempt: Mapped[Attempt] = relationship(back_populates="events")
    task: Mapped[TaskInstance | None] = relationship(back_populates="events")
