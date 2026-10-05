import { parsePublicState, type TaskPublicState } from "../tasks/registry";
import { invalidResponse } from "./errors";
import { request, type AuthenticatedRequestOptions } from "./http";
import { isRecord, parseList, type UnknownRecord } from "./parsing";

/**
 * A sandbox task as the browser holds it. The server stores nothing, so both
 * states come as `stateText` and go back with every move exactly as received:
 * parsed here, integers above 2^53 would return changed.
 */
export type SandboxTaskState = {
  publicState: TaskPublicState;
  stateText: string;
  referenceAnswer: string | null;
  referenceCommands: string[];
  details: string[];
};

export type SandboxTask = SandboxTaskState & {
  family: string;
  generatorVersion: string;
  seed: number;
  difficulty: number;
};

export type SandboxInteraction = SandboxTaskState & {
  accepted: boolean;
  completed: boolean;
  reason: string;
  message: string;
  evaluation: UnknownRecord | null;
};

export type SandboxAnswer = {
  evaluation: UnknownRecord;
  finalized: boolean;
};

export type SandboxTaskInput = {
  family: string;
  difficulty: number;
  /** `null` lets the server pick a random one. */
  seed: number | null;
  subKind: string | null;
};

export type SandboxMove =
  | { actionType: "probe"; probe: string }
  | { actionType: "apply_op"; opId: string }
  | { actionType: "hint" | "undo" | "reset" };

export type SandboxInteractionInput = SandboxMove & {
  family: string;
  stateText: string;
};

export type SandboxAnswerInput = {
  family: string;
  answer: string;
  stateText: string;
};

function parseText(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function parseTaskState(body: UnknownRecord): SandboxTaskState | null {
  const {
    public_state: publicState,
    state: stateText,
    reference_answer: referenceAnswer,
  } = body;
  const referenceCommands = parseList(body.reference_commands, parseText);
  const details = parseList(body.details, parseText);
  if (
    !isRecord(publicState) ||
    typeof stateText !== "string" ||
    (referenceAnswer !== null && typeof referenceAnswer !== "string") ||
    !referenceCommands ||
    !details
  ) {
    return null;
  }
  return {
    publicState: parsePublicState(publicState),
    stateText,
    referenceAnswer,
    referenceCommands,
    details,
  };
}

export function parseSandboxTask(body: unknown): SandboxTask {
  const record = isRecord(body) ? body : {};
  const state = parseTaskState(record);
  const { family, seed, difficulty } = record;
  const generatorVersion = record.generator_version;
  if (
    !state ||
    typeof family !== "string" ||
    typeof generatorVersion !== "string" ||
    typeof seed !== "number" ||
    !Number.isSafeInteger(seed) ||
    typeof difficulty !== "number" ||
    !Number.isInteger(difficulty)
  ) {
    throw invalidResponse("Сервер вернул некорректную задачу песочницы.", body);
  }
  return { ...state, family, generatorVersion, seed, difficulty };
}

export function parseSandboxInteraction(body: unknown): SandboxInteraction {
  const record = isRecord(body) ? body : {};
  const state = parseTaskState(record);
  const { accepted, completed, reason, message, evaluation } = record;
  if (
    !state ||
    typeof accepted !== "boolean" ||
    typeof completed !== "boolean" ||
    typeof reason !== "string" ||
    typeof message !== "string" ||
    (evaluation !== null && !isRecord(evaluation))
  ) {
    throw invalidResponse("Сервер вернул некорректный ход песочницы.", body);
  }
  return { ...state, accepted, completed, reason, message, evaluation };
}

export function parseSandboxAnswer(body: unknown): SandboxAnswer {
  const record = isRecord(body) ? body : {};
  const { evaluation, finalized } = record;
  if (!isRecord(evaluation) || typeof finalized !== "boolean") {
    throw invalidResponse(
      "Сервер вернул некорректную проверку ответа песочницы.",
      body,
    );
  }
  return { evaluation, finalized };
}

/** The requests in the field names the server and `sirius_gate.editor` expect. */
export function sandboxTaskBody(input: SandboxTaskInput) {
  return {
    family: input.family,
    difficulty: input.difficulty,
    seed: input.seed,
    sub_kind: input.subKind,
  };
}

export function sandboxInteractionBody(input: SandboxInteractionInput) {
  return {
    family: input.family,
    action_type: input.actionType,
    ...(input.actionType === "probe"
      ? { probe: input.probe }
      : input.actionType === "apply_op"
        ? { op_id: input.opId }
        : {}),
    state: input.stateText,
  };
}

export function sandboxAnswerBody(input: SandboxAnswerInput) {
  return {
    family: input.family,
    answer: input.answer,
    state: input.stateText,
  };
}

export async function generateSandboxTask(
  input: SandboxTaskInput,
  options: AuthenticatedRequestOptions,
): Promise<SandboxTask> {
  return parseSandboxTask(
    await request("/sandbox/tasks", {
      ...options,
      method: "POST",
      body: sandboxTaskBody(input),
    }),
  );
}

export async function interactInSandbox(
  input: SandboxInteractionInput,
  options: AuthenticatedRequestOptions,
): Promise<SandboxInteraction> {
  return parseSandboxInteraction(
    await request("/sandbox/interactions", {
      ...options,
      method: "POST",
      body: sandboxInteractionBody(input),
    }),
  );
}

export async function answerInSandbox(
  input: SandboxAnswerInput,
  options: AuthenticatedRequestOptions,
): Promise<SandboxAnswer> {
  return parseSandboxAnswer(
    await request("/sandbox/answers", {
      ...options,
      method: "POST",
      body: sandboxAnswerBody(input),
    }),
  );
}
