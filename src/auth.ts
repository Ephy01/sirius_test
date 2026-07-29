export type AccessRole = "organizer" | "participant";

export type AccessSession = {
  role: AccessRole;
  codeLabel: string;
  createdAt: string;
};

export const DEMO_CODES = {
  organizer: "ORBIT-ADMIN",
  participant: "SIRIUS-2026",
} as const;

const SESSION_KEY = "sirius-gate:access-session";

export function normalizeAccessCode(value: string) {
  return value.toUpperCase().replace(/\s+/g, "").replace(/[–—]/g, "-");
}

export function resolveAccessCode(value: string): AccessRole | null {
  const normalized = normalizeAccessCode(value);

  if (normalized === DEMO_CODES.organizer) return "organizer";
  if (normalized === DEMO_CODES.participant) return "participant";

  return null;
}

export function createAccessSession(role: AccessRole, code: string): AccessSession {
  const normalized = normalizeAccessCode(code);
  return {
    role,
    codeLabel: normalized.slice(-4).padStart(normalized.length, "•"),
    createdAt: new Date().toISOString(),
  };
}

export function loadAccessSession(): AccessSession | null {
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;

    const session = JSON.parse(raw) as AccessSession;
    if (session.role !== "organizer" && session.role !== "participant") return null;
    return session;
  } catch {
    return null;
  }
}

export function saveAccessSession(session: AccessSession) {
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearAccessSession() {
  window.sessionStorage.removeItem(SESSION_KEY);
  window.sessionStorage.removeItem("sirius-gate:participant-deadline");
}
