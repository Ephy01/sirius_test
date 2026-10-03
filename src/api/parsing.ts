import { invalidResponse } from "./errors";

export type UnknownRecord = Record<string, unknown>;

export function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function readString(record: UnknownRecord, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string") return value;
  }
  return undefined;
}

export function readNullableString(
  record: UnknownRecord,
  ...keys: string[]
): string | null | undefined {
  for (const key of keys) {
    const value = record[key];
    if (value === null || typeof value === "string") return value;
  }
  return undefined;
}

export function readNumber(record: UnknownRecord, ...keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return undefined;
}

export function readStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

export function expectRecord(value: unknown, message: string): UnknownRecord {
  if (!isRecord(value)) throw invalidResponse(message, value);
  return value;
}

export function requiredString(
  record: UnknownRecord,
  label: string,
  ...keys: string[]
): string {
  const value = readString(record, ...keys);
  if (!value) {
    throw invalidResponse(`Сервер вернул некорректное поле «${label}».`, record);
  }
  return value;
}

export function unwrapItems(body: unknown, message: string): unknown[] {
  if (Array.isArray(body)) return body;
  if (isRecord(body) && Array.isArray(body.items)) return body.items;
  throw invalidResponse(message, body);
}
