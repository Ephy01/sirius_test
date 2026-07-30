import {
  ApiError,
  api,
  type AccessRole as ApiAccessRole,
  type AttemptSummary,
  type ContestSummary,
  type EnrollmentSummary,
  type ParticipantSummary,
} from "./api";

export type AccessRole = ApiAccessRole;

export type AccessSession = {
  token: string;
  role: AccessRole;
  codeLabel: string;
  createdAt: string;
  expiresAt?: string | null;
  contest?: ContestSummary;
  participant?: ParticipantSummary;
  enrollment?: EnrollmentSummary;
  attempt?: AttemptSummary | null;
};

type StoredAccessSession = {
  version: 2;
  session: AccessSession;
};

type UnknownRecord = Record<string, unknown>;

const SESSION_KEY = "sirius-gate:access-session";
const PARTICIPANT_DEADLINE_KEY = "sirius-gate:participant-deadline";

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(record: UnknownRecord, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string") return value;
  }
  return undefined;
}

function readNullableString(
  record: UnknownRecord,
  ...keys: string[]
): string | null | undefined {
  for (const key of keys) {
    const value = record[key];
    if (value === null || typeof value === "string") return value;
  }
  return undefined;
}

function getSessionStorage(): Storage | null {
  if (typeof window === "undefined") return null;

  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function isIsoDate(value: string): boolean {
  return Number.isFinite(Date.parse(value));
}

function parseContest(value: unknown): ContestSummary | undefined {
  if (!isRecord(value)) return undefined;

  const id = readString(value, "id");
  const title = readString(value, "title");
  const durationMinutes = value.durationMinutes;
  const status = value.status;
  if (
    !id ||
    !title ||
    typeof durationMinutes !== "number" ||
    !Number.isFinite(durationMinutes) ||
    (status !== "draft" && status !== "published")
  ) {
    return undefined;
  }

  return {
    id,
    title,
    durationMinutes,
    status,
    environmentKey: readString(value, "environmentKey"),
    participantCount:
      typeof value.participantCount === "number" &&
      Number.isFinite(value.participantCount)
        ? value.participantCount
        : undefined,
    createdAt: readString(value, "createdAt"),
    publishedAt: readNullableString(value, "publishedAt"),
  };
}

function parseParticipant(value: unknown): ParticipantSummary | undefined {
  if (!isRecord(value)) return undefined;

  const id = readString(value, "id");
  const displayName = readString(value, "displayName");
  if (!id || !displayName) return undefined;

  return {
    id,
    displayName,
    externalRef: readNullableString(value, "externalRef"),
  };
}

function parseEnrollment(value: unknown): EnrollmentSummary | undefined {
  if (!isRecord(value)) return undefined;

  const id = readString(value, "id");
  const contestId = readString(value, "contestId");
  const participant = parseParticipant(value.participant);
  const participantId = readString(value, "participantId") ?? participant?.id;
  const status = value.status;
  if (
    !id ||
    !contestId ||
    !participantId ||
    (status !== "registered" && status !== "disabled")
  ) {
    return undefined;
  }

  return {
    id,
    contestId,
    participantId,
    participant,
    status,
    createdAt: readString(value, "createdAt"),
  };
}

function parseAttempt(value: unknown): AttemptSummary | null | undefined {
  if (value === null) return null;
  if (!isRecord(value)) return undefined;

  const id = readString(value, "id");
  const enrollmentId = readString(value, "enrollmentId");
  const status = value.status;
  if (
    !id ||
    !enrollmentId ||
    (status !== "active" &&
      status !== "completed" &&
      status !== "expired")
  ) {
    return undefined;
  }

  return {
    id,
    enrollmentId,
    number:
      typeof value.number === "number" && Number.isFinite(value.number)
        ? value.number
        : 1,
    status,
    startedAt: readNullableString(value, "startedAt"),
    deadlineAt: readNullableString(value, "deadlineAt"),
    finishedAt: readNullableString(value, "finishedAt"),
  };
}

function parseAccessSession(value: unknown): AccessSession | null {
  if (!isRecord(value)) return null;

  const token = readString(value, "token", "accessToken", "access_token");
  const role = readString(value, "role");
  const codeLabel = readString(value, "codeLabel", "code_label");
  const createdAt = readString(value, "createdAt", "created_at");
  const expiresAt = readNullableString(value, "expiresAt", "expires_at");

  if (
    !token ||
    (role !== "organizer" && role !== "participant") ||
    !codeLabel ||
    !createdAt ||
    !isIsoDate(createdAt)
  ) {
    return null;
  }
  if (expiresAt !== undefined && expiresAt !== null && !isIsoDate(expiresAt)) {
    return null;
  }
  if (expiresAt && Date.parse(expiresAt) <= Date.now()) return null;

  return {
    token,
    role,
    codeLabel,
    createdAt,
    expiresAt,
    contest: parseContest(value.contest),
    participant: parseParticipant(value.participant),
    enrollment: parseEnrollment(value.enrollment),
    attempt: parseAttempt(value.attempt),
  };
}

function maskAccessCode(code: string): string {
  const compact = code.replace(/-/g, "");
  const suffix = compact.slice(-4);
  return suffix ? `•••• ${suffix}` : "••••";
}

export function normalizeAccessCode(value: string): string {
  return value
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "")
    .replace(/[‐‑‒–—―−]/g, "-");
}

export async function redeemAccessCode(
  value: string,
  signal?: AbortSignal,
): Promise<AccessSession> {
  const code = normalizeAccessCode(value);
  if (!code) {
    throw new ApiError(400, {
      code: "access_code_required",
      message: "Введите код доступа.",
    });
  }

  const response = await api.redeemCode(code, { signal });
  const session: AccessSession = {
    token: response.accessToken,
    role: response.role,
    codeLabel: maskAccessCode(code),
    createdAt: new Date().toISOString(),
    expiresAt: response.expiresAt,
  };

  saveAccessSession(session);
  return session;
}

export function loadAccessSession(): AccessSession | null {
  const storage = getSessionStorage();
  if (!storage) return null;

  try {
    const raw = storage.getItem(SESSION_KEY);
    if (!raw) return null;

    const parsed: unknown = JSON.parse(raw);
    const candidate =
      isRecord(parsed) && parsed.version === 2 && "session" in parsed
        ? parsed.session
        : parsed;
    const session = parseAccessSession(candidate);

    // Old demo sessions had no server token. They are intentionally invalidated.
    if (!session) storage.removeItem(SESSION_KEY);
    return session;
  } catch {
    storage.removeItem(SESSION_KEY);
    return null;
  }
}

export function saveAccessSession(session: AccessSession): void {
  const storage = getSessionStorage();
  if (!storage) return;

  const validated = parseAccessSession(session);
  if (!validated) {
    throw new TypeError("Некорректная сессия доступа.");
  }

  const stored: StoredAccessSession = { version: 2, session: validated };
  storage.setItem(SESSION_KEY, JSON.stringify(stored));
}

export function updateAccessSession(
  patch: Partial<
    Pick<AccessSession, "contest" | "participant" | "enrollment" | "attempt">
  >,
): AccessSession | null {
  const current = loadAccessSession();
  if (!current) return null;

  const next: AccessSession = { ...current, ...patch };
  saveAccessSession(next);
  return next;
}

export function clearAccessSession(): void {
  const storage = getSessionStorage();
  if (!storage) return;

  storage.removeItem(SESSION_KEY);
  storage.removeItem(PARTICIPANT_DEADLINE_KEY);
}
