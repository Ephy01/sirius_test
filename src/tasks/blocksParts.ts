/** Pieces shared by the blocks of a scene described as data. */

export const TONES = ["plain", "accent", "muted", "good", "bad"] as const;

export type Tone = (typeof TONES)[number];

export function parseTone(value: unknown): Tone | null {
  return TONES.find((name) => name === value) ?? null;
}

export function parseChatCommand(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

/** `undefined` when the command is present but malformed, `null` when the element is not clickable. */
export function parseOptionalCommand(value: unknown): string | null | undefined {
  if (value === undefined || value === null) return null;
  return parseChatCommand(value) ?? undefined;
}
