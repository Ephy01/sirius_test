import { parsePublicState, type TaskPublicState } from "../tasks/registry";
import { invalidResponse } from "./errors";
import { request, type AuthenticatedRequestOptions } from "./http";
import {
  parseAttempt,
  parseContestSummary,
  parseEnrollment,
  parseParticipant,
  type AttemptSummary,
  type ContestSummary,
  type EnrollmentSummary,
  type ParticipantSummary,
} from "./models";
import {
  expectRecord,
  isRecord,
  readNumber,
  readString,
  readStringList,
  requiredString,
} from "./parsing";

export type TaskStatus = "active" | "answered" | "skipped";

export type TaskProgressEntry = {
  ordinal: number;
  status: TaskStatus;
};

export type ParticipantContext = {
  contest: ContestSummary;
  participant: ParticipantSummary;
  enrollment: EnrollmentSummary;
  attempt?: AttemptSummary | null;
};

export type ParticipantTelemetryEventType =
  | "client_task_viewed"
  | "client_command_submitted"
  | "client_focus"
  | "client_blur"
  | "client_visibility_visible"
  | "client_visibility_hidden"
  | "client_chat_paste"
  | "client_copy";

export type ParticipantTelemetryEvent = {
  clientEventId: string;
  clientSessionId: string;
  eventType: ParticipantTelemetryEventType;
  attemptId?: string;
  taskId?: string;
  clientTimestamp: string;
  clientElapsedMs: number;
  payload?: Record<string, unknown>;
};

export type StartAttemptInput = Record<string, never>;

export type StartAttemptResponse = {
  attempt: AttemptSummary;
  created: boolean;
};

export type ParticipantTask = {
  id: string;
  ordinal: number;
  family: string;
  difficulty: number;
  status: TaskStatus;
  publicState: TaskPublicState;
};

export type CurrentTaskResponse = {
  task: ParticipantTask | null;
};

export type NextTaskResponse = {
  task: ParticipantTask;
  created: boolean;
};

export type TaskActionResponse = {
  task: ParticipantTask;
  message: string;
};

export type TaskInteractionInput =
  | {
      actionType: "probe";
      probe: string;
      clientActionId: string;
    }
  | {
      actionType: "apply_op";
      opId: string;
      clientActionId: string;
    }
  | {
      actionType: "hint" | "undo" | "reset";
      clientActionId: string;
    };

export type DebugAnswerResponse = {
  family: string;
  answer: string;
  commands: string[];
  details: string[];
};

export type TaskInteractionResponse = {
  task: ParticipantTask;
  accepted: boolean;
  completed: boolean;
  message?: string;
  clientActionId: string;
};

function parseTaskStatus(value: unknown): TaskStatus {
  return value === "answered" || value === "skipped" ? value : "active";
}

function parseParticipantTask(value: unknown): ParticipantTask {
  const record = expectRecord(value, "Сервер вернул некорректную задачу.");
  const publicState = parsePublicState(
    expectRecord(
      record.publicState ?? record.public_state,
      "Сервер вернул задачу без публичного состояния.",
    ),
  );

  return {
    id: requiredString(record, "task.id", "id"),
    ordinal: readNumber(record, "ordinal") ?? 1,
    family: requiredString(record, "task.family", "family"),
    difficulty: readNumber(record, "difficulty") ?? 1,
    status: parseTaskStatus(record.status),
    publicState,
  };
}

export async function getParticipantContext(
  options: AuthenticatedRequestOptions,
): Promise<ParticipantContext> {
  const body = expectRecord(
    await request("/participant/context", options),
    "Сервер вернул некорректный контекст участника.",
  );
  const attempt = body.activeAttempt ?? body.active_attempt;

  return {
    contest: parseContestSummary(body.contest),
    participant: parseParticipant(body.participant),
    enrollment: parseEnrollment(body.enrollment),
    attempt:
      attempt === null
        ? null
        : attempt === undefined
          ? undefined
          : parseAttempt(attempt),
  };
}

export async function getTaskProgress(
  options: AuthenticatedRequestOptions,
): Promise<TaskProgressEntry[]> {
  const body = await request("/participant/tasks/progress", options);
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw invalidResponse("Сервер вернул некорректный прогресс задач.", body);
  }
  return body.items.flatMap((item): TaskProgressEntry[] => {
    if (!isRecord(item)) return [];
    const ordinal = item.ordinal;
    const status = item.status;
    if (
      typeof ordinal !== "number" ||
      (status !== "active" && status !== "answered" && status !== "skipped")
    ) {
      return [];
    }
    return [{ ordinal, status }];
  });
}

export async function recordParticipantTelemetry(
  event: ParticipantTelemetryEvent,
  options: AuthenticatedRequestOptions,
): Promise<void> {
  await request("/participant/telemetry", {
    ...options,
    method: "POST",
    keepalive: true,
    body: {
      client_event_id: event.clientEventId,
      client_session_id: event.clientSessionId,
      event_type: event.eventType,
      attempt_id: event.attemptId,
      task_id: event.taskId,
      client_timestamp: event.clientTimestamp,
      client_elapsed_ms: event.clientElapsedMs,
      payload: event.payload,
    },
  });
}

export async function startAttempt(
  input: StartAttemptInput,
  options: AuthenticatedRequestOptions,
): Promise<StartAttemptResponse> {
  const body = await request("/participant/attempts/start", {
    ...options,
    method: "POST",
    body: input,
  });
  const attempt = isRecord(body) && body.attempt !== undefined ? body.attempt : body;

  return {
    attempt: parseAttempt(attempt),
    created: isRecord(body) && typeof body.created === "boolean" ? body.created : false,
  };
}

export async function getCurrentTask(
  options: AuthenticatedRequestOptions,
): Promise<CurrentTaskResponse> {
  const body = expectRecord(
    await request("/participant/tasks/current", options),
    "Сервер вернул некорректный ответ задачи.",
  );

  return {
    task: body.task === null ? null : parseParticipantTask(body.task),
  };
}

export async function getNextTask(
  options: AuthenticatedRequestOptions,
): Promise<NextTaskResponse> {
  const body = expectRecord(
    await request("/participant/tasks/next", {
      ...options,
      method: "POST",
    }),
    "Сервер вернул некорректный ответ следующей задачи.",
  );

  return {
    task: parseParticipantTask(body.task),
    created: typeof body.created === "boolean" ? body.created : false,
  };
}

export async function answerTask(
  taskId: string,
  answer: string,
  options: AuthenticatedRequestOptions,
): Promise<TaskActionResponse> {
  const body = expectRecord(
    await request(
      `/participant/tasks/${encodeURIComponent(taskId)}/answer`,
      {
        ...options,
        method: "POST",
        body: { answer },
      },
    ),
    "Сервер вернул некорректное подтверждение ответа.",
  );

  return {
    task: parseParticipantTask(body.task),
    message:
      readString(body, "message") ??
      "Ответ зафиксирован. Когда будете готовы, перейдите дальше.",
  };
}

export async function interactWithTask(
  taskId: string,
  input: TaskInteractionInput,
  options: AuthenticatedRequestOptions,
): Promise<TaskInteractionResponse> {
  const body = expectRecord(
    await request(
      `/participant/tasks/${encodeURIComponent(taskId)}/interactions`,
      {
        ...options,
        method: "POST",
        body: {
          action_type: input.actionType,
          ...(input.actionType === "probe"
            ? { probe: input.probe }
            : input.actionType === "apply_op"
              ? { op_id: input.opId }
              : {}),
          client_action_id: input.clientActionId,
        },
      },
    ),
    "Сервер вернул некорректный результат хода.",
  );

  return {
    task: parseParticipantTask(body.task),
    accepted: body.accepted === true,
    completed: body.completed === true,
    message: readString(body, "message"),
    clientActionId:
      readString(body, "clientActionId", "client_action_id") ??
      input.clientActionId,
  };
}

export async function getParticipantDebugAnswer(
  taskId: string,
  options: AuthenticatedRequestOptions,
): Promise<DebugAnswerResponse> {
  const body = expectRecord(
    await request(
      `/participant/tasks/${encodeURIComponent(taskId)}/debug-answer`,
      options,
    ),
    "Сервер вернул некорректный эталонный ответ.",
  );
  return {
    family: readString(body, "family") ?? "",
    answer: readString(body, "answer") ?? "",
    commands: readStringList(body.commands),
    details: readStringList(body.details),
  };
}

export async function skipTask(
  taskId: string,
  options: AuthenticatedRequestOptions,
): Promise<TaskActionResponse> {
  const body = expectRecord(
    await request(
      `/participant/tasks/${encodeURIComponent(taskId)}/skip`,
      {
        ...options,
        method: "POST",
      },
    ),
    "Сервер вернул некорректное подтверждение пропуска.",
  );

  return {
    task: parseParticipantTask(body.task),
    message:
      readString(body, "message") ??
      "Задача пропущена. Когда будете готовы, перейдите дальше.",
  };
}
