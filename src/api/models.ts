import { invalidResponse } from "./errors";
import {
  expectRecord,
  readNullableString,
  readNumber,
  readString,
  requiredString,
} from "./parsing";

export type ContestStatus = "draft" | "published";
export type EnrollmentStatus = "registered" | "disabled";
export type AttemptStatus = "active" | "completed" | "expired";

export type ContestSummary = {
  id: string;
  title: string;
  status: ContestStatus;
  durationMinutes: number;
  participantCount?: number;
  createdAt?: string;
  publishedAt?: string | null;
};

export type ParticipantSummary = {
  id: string;
  displayName: string;
  externalRef?: string | null;
};

export type EnrollmentSummary = {
  id: string;
  contestId: string;
  participantId: string;
  participant?: ParticipantSummary;
  status: EnrollmentStatus;
  createdAt?: string;
};

export type AttemptSummary = {
  id: string;
  enrollmentId: string;
  number: number;
  status: AttemptStatus;
  startedAt?: string | null;
  deadlineAt?: string | null;
  finishedAt?: string | null;
};

function parseContestStatus(value: unknown): ContestStatus {
  return value === "published" ? value : "draft";
}

export function parseEnrollmentStatus(value: unknown): EnrollmentStatus {
  return value === "disabled" ? value : "registered";
}

export function parseAttemptStatus(value: unknown): AttemptStatus {
  return value === "completed" || value === "expired" ? value : "active";
}

export function parseContestSummary(value: unknown): ContestSummary {
  const record = expectRecord(value, "Сервер вернул некорректные данные контеста.");

  return {
    id: requiredString(record, "contest.id", "id"),
    title: requiredString(record, "contest.title", "title", "name"),
    status: parseContestStatus(record.status),
    durationMinutes:
      readNumber(record, "durationMinutes", "duration_minutes") ?? 60,
    participantCount: readNumber(record, "participantCount", "participant_count"),
    createdAt: readString(record, "createdAt", "created_at"),
    publishedAt: readNullableString(record, "publishedAt", "published_at"),
  };
}

export function parseParticipant(value: unknown): ParticipantSummary {
  const record = expectRecord(value, "Сервер вернул некорректные данные участника.");

  return {
    id: requiredString(record, "participant.id", "id"),
    displayName: requiredString(
      record,
      "participant.displayName",
      "displayName",
      "display_name",
      "name",
    ),
    externalRef: readNullableString(
      record,
      "externalRef",
      "external_ref",
      "externalId",
      "external_id",
    ),
  };
}

export function parseEnrollment(value: unknown): EnrollmentSummary {
  const record = expectRecord(
    value,
    "Сервер вернул некорректную регистрацию участника.",
  );

  const participant =
    record.participant === undefined ? undefined : parseParticipant(record.participant);
  const participantId =
    readString(record, "participantId", "participant_id") ?? participant?.id;
  if (!participantId) {
    throw invalidResponse("Сервер вернул регистрацию без участника.", record);
  }

  return {
    id: requiredString(record, "enrollment.id", "id"),
    contestId: requiredString(record, "enrollment.contestId", "contestId", "contest_id"),
    participantId,
    participant,
    status: parseEnrollmentStatus(record.status),
    createdAt: readString(record, "createdAt", "created_at"),
  };
}

export function parseAttempt(value: unknown): AttemptSummary {
  const record = expectRecord(value, "Сервер вернул некорректные данные попытки.");

  return {
    id: requiredString(record, "attempt.id", "id"),
    enrollmentId: requiredString(
      record,
      "attempt.enrollmentId",
      "enrollmentId",
      "enrollment_id",
    ),
    number: readNumber(record, "number") ?? 1,
    status: parseAttemptStatus(record.status),
    startedAt: readNullableString(record, "startedAt", "started_at"),
    deadlineAt: readNullableString(record, "deadlineAt", "deadline_at"),
    finishedAt: readNullableString(record, "finishedAt", "finished_at"),
  };
}
