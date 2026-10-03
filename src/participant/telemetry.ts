import { useEffect, useRef } from "react";
import type {
  ParticipantTelemetryEvent,
  ParticipantTelemetryEventType,
} from "../api";
import { createClientActionId } from "./clientActionId";

const MAX_TELEMETRY_TEXT_BYTES = 6_000;
const MAX_TELEMETRY_QUEUE_LENGTH = 5_000;
const MAX_PERSISTED_TELEMETRY_EVENTS = 300;
const TELEMETRY_STORAGE_PREFIX = "sirius-gate:telemetry:";

type QueuedTelemetry = {
  event: ParticipantTelemetryEvent;
  retryCount: number;
};

export type EmitTelemetry = (
  eventType: ParticipantTelemetryEventType,
  payload?: Record<string, unknown>,
  taskId?: string,
) => void;

export function telemetryText(value: string) {
  const encoder = new TextEncoder();
  const originalByteLength = encoder.encode(value).byteLength;
  const originalJsonByteLength = encoder.encode(JSON.stringify(value)).byteLength;
  if (originalJsonByteLength <= MAX_TELEMETRY_TEXT_BYTES) {
    return {
      text: value,
      originalByteLength,
      originalJsonByteLength,
      truncated: false,
    };
  }

  const characters = Array.from(value);
  let lower = 0;
  let upper = characters.length;
  while (lower < upper) {
    const middle = Math.ceil((lower + upper) / 2);
    const candidate = characters.slice(0, middle).join("");
    if (
      encoder.encode(JSON.stringify(candidate)).byteLength <=
      MAX_TELEMETRY_TEXT_BYTES
    ) {
      lower = middle;
    } else {
      upper = middle - 1;
    }
  }

  return {
    text: characters.slice(0, lower).join(""),
    originalByteLength,
    originalJsonByteLength,
    truncated: true,
  };
}

function telemetryErrorIsRetryable(error: unknown): boolean {
  if (
    typeof error !== "object" ||
    error === null ||
    !("status" in error) ||
    typeof error.status !== "number"
  ) {
    return true;
  }
  const code =
    "code" in error && typeof error.code === "string" ? error.code : undefined;
  if (code === "TELEMETRY_EVENT_LIMIT_REACHED") return false;
  return (
    error.status === 0 ||
    (error.status === 429 && code === "TELEMETRY_RATE_LIMITED") ||
    error.status >= 500
  );
}

function telemetryStorageKey(attemptId?: string): string | null {
  return attemptId ? `${TELEMETRY_STORAGE_PREFIX}${attemptId}` : null;
}

function loadTelemetryQueue(attemptId?: string): QueuedTelemetry[] {
  const storageKey = telemetryStorageKey(attemptId);
  if (!storageKey || typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.sessionStorage.getItem(storageKey) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value
      .filter(
        (event): event is ParticipantTelemetryEvent =>
          typeof event === "object" &&
          event !== null &&
          typeof event.clientEventId === "string" &&
          typeof event.clientSessionId === "string" &&
          typeof event.eventType === "string" &&
          typeof event.clientTimestamp === "string" &&
          typeof event.clientElapsedMs === "number",
      )
      .slice(0, MAX_PERSISTED_TELEMETRY_EVENTS)
      .map((event) => ({
        event: {
          ...event,
          attemptId: event.attemptId ?? attemptId,
        },
        retryCount: 0,
      }));
  } catch {
    window.sessionStorage.removeItem(storageKey);
    return [];
  }
}

function persistTelemetryQueue(
  attemptId: string | undefined,
  queue: QueuedTelemetry[],
) {
  const storageKey = telemetryStorageKey(attemptId);
  if (!storageKey || typeof window === "undefined") return;
  try {
    if (queue.length === 0) {
      window.sessionStorage.removeItem(storageKey);
      return;
    }
    window.sessionStorage.setItem(
      storageKey,
      JSON.stringify(
        queue
          .slice(0, MAX_PERSISTED_TELEMETRY_EVENTS)
          .map((item) => item.event),
      ),
    );
  } catch {
  }
}

export function useTelemetryQueue(
  attemptId: string | undefined,
  onTelemetry:
    | ((event: ParticipantTelemetryEvent) => Promise<unknown> | unknown)
    | undefined,
  activeTaskId: { readonly current: string },
): EmitTelemetry {
  const telemetryHandlerRef = useRef(onTelemetry);
  const telemetrySessionId = useRef(createClientActionId());
  const telemetryStartedAt = useRef(Date.now());
  const telemetrySequence = useRef(0);
  const telemetryQueue = useRef<QueuedTelemetry[]>(
    loadTelemetryQueue(attemptId),
  );
  const telemetryDrainActive = useRef(false);
  const telemetryRetryTimer = useRef<number | null>(null);

  useEffect(() => {
    telemetryHandlerRef.current = onTelemetry;
    void drainTelemetryQueue();
  }, [onTelemetry]);

  useEffect(
    () => () => {
      if (telemetryRetryTimer.current !== null) {
        window.clearTimeout(telemetryRetryTimer.current);
        telemetryRetryTimer.current = null;
      }
    },
    [],
  );

  function emitTelemetry(
    eventType: ParticipantTelemetryEventType,
    payload: Record<string, unknown> = {},
    taskId = activeTaskId.current,
  ) {
    if (!telemetryHandlerRef.current) return;
    telemetrySequence.current += 1;
    const event: ParticipantTelemetryEvent = {
      clientEventId: createClientActionId(),
      clientSessionId: telemetrySessionId.current,
      eventType,
      attemptId,
      taskId,
      clientTimestamp: new Date().toISOString(),
      clientElapsedMs: Math.max(0, Date.now() - telemetryStartedAt.current),
      payload: {
        ...payload,
        client_sequence: telemetrySequence.current,
      },
    };
    if (telemetryQueue.current.length >= MAX_TELEMETRY_QUEUE_LENGTH) {
      return;
    }
    telemetryQueue.current.push({ event, retryCount: 0 });
    persistTelemetryQueue(attemptId, telemetryQueue.current);
    if (telemetryRetryTimer.current === null) {
      void drainTelemetryQueue();
    }
  }

  async function drainTelemetryQueue() {
    const handler = telemetryHandlerRef.current;
    if (!handler || telemetryDrainActive.current) return;
    telemetryDrainActive.current = true;
    let retryDelay: number | null = null;

    try {
      while (telemetryQueue.current.length > 0) {
        const queued = telemetryQueue.current[0];
        try {
          await handler(queued.event);
          telemetryQueue.current.shift();
          persistTelemetryQueue(attemptId, telemetryQueue.current);
        } catch (error) {
          if (!telemetryErrorIsRetryable(error)) {
            telemetryQueue.current.shift();
            persistTelemetryQueue(attemptId, telemetryQueue.current);
            continue;
          }
          queued.retryCount += 1;
          retryDelay = Math.min(
            10_000,
            250 * 2 ** Math.min(queued.retryCount - 1, 6),
          );
          break;
        }
      }
    } finally {
      telemetryDrainActive.current = false;
      if (retryDelay !== null && telemetryQueue.current.length > 0) {
        telemetryRetryTimer.current = window.setTimeout(() => {
          telemetryRetryTimer.current = null;
          void drainTelemetryQueue();
        }, retryDelay);
      } else if (telemetryQueue.current.length > 0) {
        queueMicrotask(() => void drainTelemetryQueue());
      }
    }
  }

  return emitTelemetry;
}
