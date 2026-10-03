import { request, type AuthenticatedRequestOptions } from "./http";
import {
  expectRecord,
  isRecord,
  readNullableString,
  readNumber,
  readString,
  type UnknownRecord,
} from "./parsing";

export type AiTurnUsage = {
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
};

export type AiTurnRemaining = {
  task: number;
  attempt: number;
};

export type AiTurn = {
  id: string;
  status: string;
  assistantMessage: string | null;
  model: string;
  usage: AiTurnUsage;
  remaining: AiTurnRemaining;
};

export type AiHistoryTurn = {
  id: string;
  status: string;
  userMessage: string;
  assistantMessage: string | null;
  createdAt: string;
  completedAt: string | null;
};

export type AiTurnHistory = {
  turns: AiHistoryTurn[];
  remaining: AiTurnRemaining;
};

function parseAiRemaining(value: unknown): AiTurnRemaining {
  if (!isRecord(value)) return { task: 0, attempt: 0 };
  return {
    task: readNumber(value, "task") ?? 0,
    attempt: readNumber(value, "attempt") ?? 0,
  };
}

function parseAiTurn(body: UnknownRecord): AiTurn {
  const usageValue = isRecord(body.usage) ? body.usage : {};
  return {
    id: readString(body, "id") ?? "",
    status: readString(body, "status") ?? "completed",
    assistantMessage:
      readNullableString(body, "assistantMessage", "assistant_message") ??
      null,
    model: readString(body, "model") ?? "",
    usage: {
      inputTokens: readNumber(usageValue, "inputTokens", "input_tokens") ?? null,
      outputTokens:
        readNumber(usageValue, "outputTokens", "output_tokens") ?? null,
      totalTokens:
        readNumber(usageValue, "totalTokens", "total_tokens") ?? null,
    },
    remaining: parseAiRemaining(body.remaining),
  };
}

export async function sendAiTurn(
  taskId: string,
  input: { clientActionId: string; message: string },
  options: AuthenticatedRequestOptions,
): Promise<AiTurn> {
  const body = expectRecord(
    await request(
      `/participant/tasks/${encodeURIComponent(taskId)}/ai/turns`,
      {
        ...options,
        method: "POST",
        body: {
          clientActionId: input.clientActionId,
          message: input.message,
        },
      },
    ),
    "Сервер вернул некорректный ответ ассистента.",
  );
  return parseAiTurn(body);
}

export async function getAiTurns(
  taskId: string,
  options: AuthenticatedRequestOptions,
): Promise<AiTurnHistory> {
  const body = expectRecord(
    await request(
      `/participant/tasks/${encodeURIComponent(taskId)}/ai/turns`,
      options,
    ),
    "Сервер вернул некорректную историю диалога.",
  );
  const turnsValue = Array.isArray(body.turns) ? body.turns : [];
  return {
    turns: turnsValue.flatMap((item): AiHistoryTurn[] => {
      if (!isRecord(item)) return [];
      const id = readString(item, "id");
      const userMessage = readString(item, "userMessage", "user_message");
      if (!id || userMessage === undefined) return [];
      return [
        {
          id,
          status: readString(item, "status") ?? "completed",
          userMessage,
          assistantMessage:
            readNullableString(
              item,
              "assistantMessage",
              "assistant_message",
            ) ?? null,
          createdAt: readString(item, "createdAt", "created_at") ?? "",
          completedAt:
            readNullableString(item, "completedAt", "completed_at") ?? null,
        },
      ];
    }),
    remaining: parseAiRemaining(body.remaining),
  };
}
