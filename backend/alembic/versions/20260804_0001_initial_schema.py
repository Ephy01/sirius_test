"""Create the initial Sirius Gate schema.

Revision ID: 20260804_0001
Revises:
Create Date: 2026-08-04

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260804_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("environment_key", sa.String(length=80), nullable=False),
        sa.Column("task_config", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "published", name="contest_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "participants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("external_ref", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_ref"),
    )
    op.create_table(
        "enrollments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contest_id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum("registered", "disabled", name="enrollment_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contest_id"], ["contests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "contest_id",
            "participant_id",
            name="uq_enrollment_contest_participant",
        ),
    )
    op.create_index("ix_enrollments_contest_id", "enrollments", ["contest_id"])
    op.create_index("ix_enrollments_participant_id", "enrollments", ["participant_id"])
    op.create_table(
        "access_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("enrollment_id", sa.String(length=36), nullable=False),
        sa.Column("lookup_hash", sa.String(length=64), nullable=False),
        sa.Column("last4", sa.String(length=4), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "revoked",
                "expired",
                name="access_code_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("active_slot", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enrollment_id"], ["enrollments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "enrollment_id",
            "active_slot",
            name="uq_access_code_one_active",
        ),
    )
    op.create_index("ix_access_codes_enrollment_id", "access_codes", ["enrollment_id"])
    op.create_index("ix_access_codes_lookup_hash", "access_codes", ["lookup_hash"], unique=True)
    op.create_table(
        "attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("enrollment_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "completed", "expired", name="attempt_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("active_slot", sa.Boolean(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enrollment_id"], ["enrollments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("enrollment_id", "active_slot", name="uq_attempt_one_active"),
        sa.UniqueConstraint("enrollment_id", "number", name="uq_attempt_enrollment_number"),
    )
    op.create_index("ix_attempts_enrollment_id", "attempts", ["enrollment_id"])
    op.create_table(
        "attempt_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("enrollment_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "consumed", name="attempt_grant_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("pending_slot", sa.Boolean(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_attempt_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["consumed_attempt_id"], ["attempts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["enrollment_id"], ["enrollments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("consumed_attempt_id"),
        sa.UniqueConstraint(
            "enrollment_id",
            "pending_slot",
            name="uq_attempt_grant_one_pending",
        ),
    )
    op.create_index("ix_attempt_grants_enrollment_id", "attempt_grants", ["enrollment_id"])
    op.create_table(
        "client_telemetry_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("client_event_id", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id",
            "client_event_id",
            name="uq_client_telemetry_receipt_attempt_event",
        ),
    )
    op.create_index(
        "ix_client_telemetry_receipt_attempt_created",
        "client_telemetry_receipts",
        ["attempt_id", "created_at"],
    )
    op.create_table(
        "task_instances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("family", sa.String(length=80), nullable=False),
        sa.Column("generator_version", sa.String(length=80), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "answered", "skipped", name="task_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("active_slot", sa.Boolean(), nullable=True),
        sa.Column("public_state", sa.JSON(), nullable=False),
        sa.Column("private_state", sa.JSON(), nullable=False),
        sa.Column("participant_answer", sa.Text(), nullable=True),
        sa.Column("evaluation_state", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", "active_slot", name="uq_task_one_active"),
        sa.UniqueConstraint("attempt_id", "ordinal", name="uq_task_attempt_ordinal"),
    )
    op.create_index("ix_task_instances_attempt_id", "task_instances", ["attempt_id"])
    op.create_table(
        "ai_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("task_instance_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("client_action_id", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "completed",
                "failed",
                "cancelled",
                name="ai_turn_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("assistant_message", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_uri", sa.String(length=200), nullable=False),
        sa.Column("model_version", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("public_context_hash", sa.String(length=64), nullable=False),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("finish_reason", sa.String(length=40), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["task_instance_id"],
            ["task_instances.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id",
            "client_action_id",
            name="uq_ai_turn_attempt_client_action",
        ),
        sa.UniqueConstraint(
            "task_instance_id",
            "sequence",
            name="uq_ai_turn_task_sequence",
        ),
    )
    op.create_index("ix_ai_turns_attempt_id", "ai_turns", ["attempt_id"])
    op.create_index("ix_ai_turns_task_instance_id", "ai_turns", ["task_instance_id"])
    op.create_table(
        "attempt_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("task_instance_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["task_instance_id"],
            ["task_instances.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", "sequence", name="uq_attempt_event_sequence"),
    )
    op.create_index("ix_attempt_events_attempt_id", "attempt_events", ["attempt_id"])
    op.create_index("ix_attempt_events_created_at", "attempt_events", ["created_at"])
    op.create_index("ix_attempt_events_event_type", "attempt_events", ["event_type"])
    op.create_index(
        "ix_attempt_events_task_instance_id",
        "attempt_events",
        ["task_instance_id"],
    )
    op.create_table(
        "task_interactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_instance_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("client_action_id", sa.String(length=128), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_instance_id"],
            ["task_instances.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_instance_id",
            "client_action_id",
            name="uq_task_interaction_client_action",
        ),
        sa.UniqueConstraint(
            "task_instance_id",
            "sequence",
            name="uq_task_interaction_sequence",
        ),
    )
    op.create_index(
        "ix_task_interactions_task_instance_id",
        "task_interactions",
        ["task_instance_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_interactions_task_instance_id", table_name="task_interactions")
    op.drop_table("task_interactions")
    op.drop_index("ix_attempt_events_task_instance_id", table_name="attempt_events")
    op.drop_index("ix_attempt_events_event_type", table_name="attempt_events")
    op.drop_index("ix_attempt_events_created_at", table_name="attempt_events")
    op.drop_index("ix_attempt_events_attempt_id", table_name="attempt_events")
    op.drop_table("attempt_events")
    op.drop_index("ix_ai_turns_task_instance_id", table_name="ai_turns")
    op.drop_index("ix_ai_turns_attempt_id", table_name="ai_turns")
    op.drop_table("ai_turns")
    op.drop_index("ix_task_instances_attempt_id", table_name="task_instances")
    op.drop_table("task_instances")
    op.drop_index(
        "ix_client_telemetry_receipt_attempt_created",
        table_name="client_telemetry_receipts",
    )
    op.drop_table("client_telemetry_receipts")
    op.drop_index("ix_attempt_grants_enrollment_id", table_name="attempt_grants")
    op.drop_table("attempt_grants")
    op.drop_index("ix_attempts_enrollment_id", table_name="attempts")
    op.drop_table("attempts")
    op.drop_index("ix_access_codes_lookup_hash", table_name="access_codes")
    op.drop_index("ix_access_codes_enrollment_id", table_name="access_codes")
    op.drop_table("access_codes")
    op.drop_index("ix_enrollments_participant_id", table_name="enrollments")
    op.drop_index("ix_enrollments_contest_id", table_name="enrollments")
    op.drop_table("enrollments")
    op.drop_table("participants")
    op.drop_table("contests")
