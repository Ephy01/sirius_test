import {
  ApiError,
  api,
  isRecord,
  parseAttempt,
  parseContestSummary,
  parseEnrollment,
  parseParticipant,
  readNullableString,
  readString,
  type AccessRole,
  type AttemptSummary,
  type ContestSummary,
  type EnrollmentSummary,
  type ParticipantSummary,
} from "./api";

export type AccessSession = {
  token: string;
  role: AccessRole;
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

const SESSION_KEY = "sirius-gate:access-session";

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

function parseOptional<T>(
  value: unknown,
  parse: (value: unknown) => T,
): T | undefined {
  return value === undefined ? undefined : parse(value);
}

function parseAccessSession(value: unknown): AccessSession | null {
  if (!isRecord(value)) return null;

  const token = readString(value, "token");
  const role = readString(value, "role");
  const createdAt = readString(value, "createdAt");
  const expiresAt = readNullableString(value, "expiresAt");

  if (
    !token ||
    (role !== "organizer" && role !== "participant") ||
    !createdAt ||
    !isIsoDate(createdAt)
  ) {
    return null;
  }
  if (
    typeof expiresAt === "string" &&
    (!isIsoDate(expiresAt) || Date.parse(expiresAt) <= Date.now())
  ) {
    return null;
  }

  return {
    token,
    role,
    createdAt,
    expiresAt,
    contest: parseOptional(value.contest, parseContestSummary),
    participant: parseOptional(value.participant, parseParticipant),
    enrollment: parseOptional(value.enrollment, parseEnrollment),
    attempt:
      value.attempt === null ? null : parseOptional(value.attempt, parseAttempt),
  };
}

export function normalizeAccessCode(value: string): string {
  return value
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "")
    .replace(/[‐‑‒–—―−]/g, "-");
}

export async function redeemAccessCode(value: string): Promise<AccessSession> {
  const code = normalizeAccessCode(value);
  if (!code) {
    throw new ApiError(400, {
      code: "access_code_required",
      message: "Введите код доступа.",
    });
  }

  const response = await api.redeemCode(code);
  const session: AccessSession = {
    token: response.accessToken,
    role: response.role,
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

    const stored: unknown = JSON.parse(raw);
    const session =
      isRecord(stored) && stored.version === 2
        ? parseAccessSession(stored.session)
        : null;

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
  getSessionStorage()?.removeItem(SESSION_KEY);
}
