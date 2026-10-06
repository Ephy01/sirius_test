import { requestFile, type DownloadedFile } from "./files";
import { request, type AuthenticatedRequestOptions } from "./http";
import {
  parseAttemptStatus,
  parseContestSummary,
  parseEnrollment,
  parseEnrollmentStatus,
  parseParticipant,
  type AttemptStatus,
  type ContestSummary,
  type EnrollmentStatus,
  type EnrollmentSummary,
  type ParticipantSummary,
} from "./models";
import { invalidResponse } from "./errors";
import {
  expectRecord,
  isRecord,
  parseList,
  readNullableString,
  readNumber,
  readString,
  requiredString,
  unwrapItems,
} from "./parsing";

const CONTEST_ENVIRONMENT = "mixed";

export type AccessCodeStatus = "active" | "revoked" | "expired";

export type CreateContestInput = {
  title: string;
  durationMinutes: number;
  taskConfig?: Record<string, unknown>;
};

export type EnrollmentInput = {
  displayName: string;
  externalRef?: string;
};

export type AddEnrollmentsInput = {
  participants: EnrollmentInput[];
};

export type AddEnrollmentsResponse = {
  enrollments: EnrollmentSummary[];
  createdCount: number;
};

export type GeneratedAccessCode = {
  enrollmentId: string;
  participantId: string;
  participantName: string;
  participantExternalRef?: string;
  code: string;
  codeLabel: string;
  status: AccessCodeStatus;
  expiresAt?: string | null;
};

export type GenerateCodesResponse = {
  codes: GeneratedAccessCode[];
  generatedCount: number;
  skippedCount: number;
};

export type AccessCodeOverview = {
  id: string;
  last4: string;
  status: AccessCodeStatus;
  createdAt?: string;
  expiresAt?: string | null;
  revokedAt?: string | null;
  redeemedAt?: string | null;
};

export type AttemptOverview = {
  id: string;
  number: number;
  status: AttemptStatus;
  startedAt?: string | null;
  deadlineAt?: string | null;
  finishedAt?: string | null;
};

export type ContestEnrollmentAccess = {
  id: string;
  contestId: string;
  participantId: string;
  participant: ParticipantSummary;
  status: EnrollmentStatus;
  createdAt?: string;
  latestCode: AccessCodeOverview | null;
  latestAttempt: AttemptOverview | null;
  attemptGrantPending: boolean;
};

export type RotatedAccessCode = {
  enrollmentId: string;
  code: string;
  codeLabel: string;
  status: AccessCodeStatus;
  expiresAt?: string | null;
};

export type AttemptGrantResponse = {
  enrollmentId: string;
  pending: boolean;
  created: boolean;
};

export type TaskFamilyVariant = {
  key: string;
  title: string;
  description: string;
};

/** A task family as the server describes it for the contest builder. */
export type TaskFamily = {
  key: string;
  title: string;
  description: string;
  /** Who wrote the plugin; empty for built-in families. */
  author: string;
  version: string;
  source: "builtin" | "module";
  module: string | null;
  listed: boolean;
  scriptedOnly: boolean;
  interactive: boolean;
  defaultWeight: number;
  defaultSkin: string | null;
  minDifficulty: number;
  maxDifficulty: number;
  /** Names of the levels from the lowest one, when the family names them. */
  levelTitles: string[];
  variants: TaskFamilyVariant[];
};

export type TaskModuleProblem = {
  module: string;
  error: string;
};

export type TaskFamilyCatalog = {
  items: TaskFamily[];
  problems: TaskModuleProblem[];
};

function parseAccessCodeStatus(value: unknown): AccessCodeStatus {
  return value === "revoked" || value === "expired" ? value : "active";
}

function parseAccessCodeOverview(value: unknown): AccessCodeOverview | null {
  if (value === null || value === undefined) return null;
  const record = expectRecord(value, "Сервер вернул некорректные данные кода доступа.");

  return {
    id: requiredString(record, "code.id", "id"),
    last4: requiredString(record, "code.last4", "last4"),
    status: parseAccessCodeStatus(record.status),
    createdAt: readString(record, "createdAt", "created_at"),
    expiresAt: readNullableString(record, "expiresAt", "expires_at"),
    revokedAt: readNullableString(record, "revokedAt", "revoked_at"),
    redeemedAt: readNullableString(record, "redeemedAt", "redeemed_at"),
  };
}

function parseAttemptOverview(value: unknown): AttemptOverview | null {
  if (value === null || value === undefined) return null;
  const record = expectRecord(value, "Сервер вернул некорректные данные попытки.");

  return {
    id: requiredString(record, "attempt.id", "id"),
    number: readNumber(record, "number") ?? 1,
    status: parseAttemptStatus(record.status),
    startedAt: readNullableString(record, "startedAt", "started_at"),
    deadlineAt: readNullableString(record, "deadlineAt", "deadline_at"),
    finishedAt: readNullableString(record, "finishedAt", "finished_at"),
  };
}

function parseContestEnrollmentAccess(
  value: unknown,
  contestId: string,
): ContestEnrollmentAccess {
  const record = expectRecord(
    value,
    "Сервер вернул некорректную строку доступа участника.",
  );
  const participant = parseParticipant(record.participant);

  return {
    id: requiredString(record, "enrollment.id", "id"),
    contestId: readString(record, "contestId", "contest_id") ?? contestId,
    participantId:
      readString(record, "participantId", "participant_id") ?? participant.id,
    participant,
    status: parseEnrollmentStatus(record.status),
    createdAt: readString(record, "createdAt", "created_at"),
    latestCode: parseAccessCodeOverview(record.latestCode ?? record.latest_code),
    latestAttempt: parseAttemptOverview(
      record.latestAttempt ?? record.latest_attempt,
    ),
    attemptGrantPending:
      record.attemptGrantPending === true || record.attempt_grant_pending === true,
  };
}

function parseGeneratedCodes(body: unknown): GenerateCodesResponse {
  const items = unwrapItems(body, "Сервер вернул некорректный список кодов.");
  const counters = isRecord(body) ? body : {};

  return {
    codes: items.map((value) => {
      const item = expectRecord(value, "Сервер вернул некорректный код доступа.");
      const participant = isRecord(item.participant) ? item.participant : {};

      return {
        enrollmentId: requiredString(
          item,
          "enrollmentId",
          "enrollmentId",
          "enrollment_id",
        ),
        participantId: requiredString(participant, "participantId", "id"),
        participantName: requiredString(
          participant,
          "participantName",
          "displayName",
          "display_name",
        ),
        participantExternalRef: readString(
          participant,
          "externalRef",
          "external_ref",
        ),
        code: requiredString(item, "code", "code"),
        codeLabel:
          readString(item, "codeLabel", "code_label") ??
          `••••${requiredString(item, "last4", "last4")}`,
        status: parseAccessCodeStatus(item.status),
        expiresAt: readNullableString(item, "expiresAt", "expires_at"),
      };
    }),
    generatedCount:
      readNumber(counters, "generatedCount", "generated_count") ?? items.length,
    skippedCount: readNumber(counters, "skippedCount", "skipped_count") ?? 0,
  };
}

function isName(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "";
}

function isInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function hasUniqueKeys(items: readonly { key: string }[]): boolean {
  return new Set(items.map((item) => item.key)).size === items.length;
}

function parseTaskFamilyVariant(value: unknown): TaskFamilyVariant | null {
  if (!isRecord(value)) return null;
  const { key, title, description } = value;
  if (!isName(key) || !isName(title) || typeof description !== "string") {
    return null;
  }
  return { key, title, description };
}

function parseTaskFamily(value: unknown): TaskFamily | null {
  if (!isRecord(value)) return null;
  const { key, title, description, author, version, source, module } = value;
  const { listed, interactive, scripted_only: scriptedOnly } = value;
  const {
    default_weight: defaultWeight,
    default_skin: defaultSkin,
    min_difficulty: minDifficulty,
    max_difficulty: maxDifficulty,
  } = value;
  const variants = parseList(value.variants, parseTaskFamilyVariant);
  const levelTitles = parseList(value.level_titles, (item) =>
    isName(item) ? item : null,
  );
  if (
    !isName(key) ||
    !isName(title) ||
    typeof description !== "string" ||
    typeof author !== "string" ||
    !levelTitles ||
    !isName(version) ||
    (source !== "builtin" && source !== "module") ||
    (module !== null && !isName(module)) ||
    typeof listed !== "boolean" ||
    typeof scriptedOnly !== "boolean" ||
    typeof interactive !== "boolean" ||
    !isInteger(defaultWeight) ||
    (defaultSkin !== null && !isName(defaultSkin)) ||
    !isInteger(minDifficulty) ||
    !isInteger(maxDifficulty) ||
    minDifficulty < 1 ||
    minDifficulty > maxDifficulty ||
    !variants ||
    !hasUniqueKeys(variants)
  ) {
    return null;
  }

  return {
    key,
    title,
    description,
    author,
    version,
    source,
    module,
    listed,
    scriptedOnly,
    interactive,
    defaultWeight,
    defaultSkin,
    minDifficulty,
    maxDifficulty,
    levelTitles,
    variants,
  };
}

function parseTaskModuleProblem(value: unknown): TaskModuleProblem | null {
  if (!isRecord(value)) return null;
  const { module, error } = value;
  return isName(module) && typeof error === "string"
    ? { module, error }
    : null;
}

export function parseTaskFamilyCatalog(body: unknown): TaskFamilyCatalog {
  const record = isRecord(body) ? body : {};
  const items = parseList(record.items, parseTaskFamily);
  const problems = parseList(record.problems, parseTaskModuleProblem);
  if (!items || !problems || !hasUniqueKeys(items)) {
    throw invalidResponse(
      "Сервер вернул некорректный каталог семейств задач.",
      body,
    );
  }
  return { items, problems };
}

export async function listTaskFamilies(
  options: AuthenticatedRequestOptions,
): Promise<TaskFamilyCatalog> {
  return parseTaskFamilyCatalog(await request("/task-families", options));
}

/** Makes the server read the modules directory again and returns the new catalog. */
export async function reloadTaskModules(
  options: AuthenticatedRequestOptions,
): Promise<TaskFamilyCatalog> {
  return parseTaskFamilyCatalog(
    await request("/task-modules/reload", { ...options, method: "POST" }),
  );
}

export async function listContests(
  options: AuthenticatedRequestOptions,
): Promise<ContestSummary[]> {
  const body = await request("/contests", options);
  return unwrapItems(body, "Сервер вернул некорректный список контестов.").map(
    parseContestSummary,
  );
}

export async function deleteContest(
  contestId: string,
  options: AuthenticatedRequestOptions,
): Promise<void> {
  await request(`/contests/${encodeURIComponent(contestId)}`, {
    ...options,
    method: "DELETE",
  });
}

export async function createContest(
  input: CreateContestInput,
  options: AuthenticatedRequestOptions,
): Promise<ContestSummary> {
  const body = await request("/contests", {
    ...options,
    method: "POST",
    body: {
      title: input.title,
      duration_minutes: input.durationMinutes,
      environment_key: CONTEST_ENVIRONMENT,
      task_config: input.taskConfig,
    },
  });
  return parseContestSummary(body);
}

export async function addEnrollments(
  contestId: string,
  input: AddEnrollmentsInput,
  options: AuthenticatedRequestOptions,
): Promise<AddEnrollmentsResponse> {
  const body = await request(
    `/contests/${encodeURIComponent(contestId)}/enrollments`,
    {
      ...options,
      method: "POST",
      body: {
        participants: input.participants.map((participant) => ({
          display_name: participant.displayName,
          external_ref: participant.externalRef,
        })),
      },
    },
  );
  const items = unwrapItems(body, "Сервер вернул некорректный список регистраций.");

  return {
    enrollments: items.map(parseEnrollment),
    createdCount:
      (isRecord(body)
        ? readNumber(body, "createdCount", "created_count")
        : undefined) ?? items.length,
  };
}

export async function listContestEnrollments(
  contestId: string,
  options: AuthenticatedRequestOptions,
): Promise<ContestEnrollmentAccess[]> {
  const body = await request(
    `/contests/${encodeURIComponent(contestId)}/enrollments`,
    options,
  );
  return unwrapItems(body, "Сервер вернул некорректный список доступов.").map(
    (item) => parseContestEnrollmentAccess(item, contestId),
  );
}

export async function downloadEnrollmentTelemetry(
  contestId: string,
  enrollmentId: string,
  options: AuthenticatedRequestOptions,
): Promise<DownloadedFile> {
  return requestFile(
    `/contests/${encodeURIComponent(contestId)}/enrollments/${encodeURIComponent(enrollmentId)}/telemetry`,
    `telemetry-${enrollmentId}.txt`,
    options,
  );
}

export async function downloadEnrollmentTelemetrySummary(
  contestId: string,
  enrollmentId: string,
  options: AuthenticatedRequestOptions,
): Promise<DownloadedFile> {
  return requestFile(
    `/contests/${encodeURIComponent(contestId)}/enrollments/${encodeURIComponent(enrollmentId)}/telemetry/summary`,
    `summary-${enrollmentId}.md`,
    options,
  );
}

export async function rotateEnrollmentCode(
  contestId: string,
  enrollmentId: string,
  options: AuthenticatedRequestOptions,
): Promise<RotatedAccessCode> {
  const body = await request(
    `/contests/${encodeURIComponent(contestId)}/enrollments/${encodeURIComponent(enrollmentId)}/codes/rotate`,
    {
      ...options,
      method: "POST",
      body: {},
    },
  );
  const value = expectRecord(
    isRecord(body) && isRecord(body.item) ? body.item : body,
    "Сервер вернул некорректный новый код.",
  );

  const last4 =
    readString(value, "last4") ??
    readString(value, "codeLabel", "code_label")?.slice(-4);

  return {
    enrollmentId:
      readString(value, "enrollmentId", "enrollment_id") ?? enrollmentId,
    code: requiredString(value, "code", "code"),
    codeLabel:
      readString(value, "codeLabel", "code_label") ??
      (last4 ? `••••${last4}` : "Новый код"),
    status: parseAccessCodeStatus(value.status),
    expiresAt: readNullableString(value, "expiresAt", "expires_at"),
  };
}

export async function grantNextAttempt(
  contestId: string,
  enrollmentId: string,
  options: AuthenticatedRequestOptions,
): Promise<AttemptGrantResponse> {
  const body = expectRecord(
    await request(
      `/contests/${encodeURIComponent(contestId)}/enrollments/${encodeURIComponent(enrollmentId)}/attempts/grant`,
      {
        ...options,
        method: "POST",
      },
    ),
    "Сервер вернул некорректное подтверждение новой попытки.",
  );

  return {
    enrollmentId:
      readString(body, "enrollmentId", "enrollment_id") ?? enrollmentId,
    pending: body.pending === true,
    created: body.created === true,
  };
}

export async function generateCodes(
  contestId: string,
  options: AuthenticatedRequestOptions,
): Promise<GenerateCodesResponse> {
  return parseGeneratedCodes(
    await request(`/contests/${encodeURIComponent(contestId)}/codes`, {
      ...options,
      method: "POST",
      body: {},
    }),
  );
}

export async function recoverCodes(
  contestId: string,
  options: AuthenticatedRequestOptions,
): Promise<GenerateCodesResponse> {
  return parseGeneratedCodes(
    await request(
      `/contests/${encodeURIComponent(contestId)}/codes/recover`,
      { ...options, method: "POST" },
    ),
  );
}

export async function publishContest(
  contestId: string,
  options: AuthenticatedRequestOptions,
): Promise<ContestSummary> {
  const body = await request(
    `/contests/${encodeURIComponent(contestId)}/publish`,
    { ...options, method: "POST" },
  );
  return parseContestSummary(body);
}
