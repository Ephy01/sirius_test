import { ApiError, type ApiErrorPayload } from "./errors";
import { isRecord, readString } from "./parsing";

const DEFAULT_API_BASE_URL = "/api/v1";

type RequestOptions = {
  method?: "GET" | "POST" | "DELETE";
  token?: string;
  body?: unknown;
  signal?: AbortSignal;
  keepalive?: boolean;
};

export type AuthenticatedRequestOptions = {
  token: string;
  signal?: AbortSignal;
};

function normalizeBaseUrl(value: string): string {
  const normalized = value.trim().replace(/\/+$/, "");
  return normalized || DEFAULT_API_BASE_URL;
}

function getDefaultApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  return normalizeBaseUrl(
    typeof configured === "string" ? configured : DEFAULT_API_BASE_URL,
  );
}

const API_BASE_URL = getDefaultApiBaseUrl();

function createErrorPayload(
  status: number,
  statusText: string,
  body: unknown,
  requestId?: string,
): ApiErrorPayload {
  if (isRecord(body)) {
    const detail = body.detail;
    const detailRecord = isRecord(detail) ? detail : undefined;
    const message =
      readString(body, "message", "error") ??
      (detailRecord
        ? readString(detailRecord, "message", "error")
        : undefined) ??
      (typeof detail === "string" ? detail : undefined) ??
      `Запрос завершился с ошибкой ${status}.`;

    return {
      code:
        readString(body, "code", "error_code") ??
        (detailRecord
          ? readString(detailRecord, "code", "error_code")
          : undefined),
      message,
      details: detail ?? body.details,
      requestId: readString(body, "requestId", "request_id") ?? requestId,
    };
  }

  return {
    message:
      typeof body === "string" && body.trim()
        ? body
        : statusText || `Запрос завершился с ошибкой ${status}.`,
    details: body,
    requestId,
  };
}

async function readResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      throw new ApiError(502, {
        code: "invalid_json_response",
        message: "Сервер вернул повреждённый JSON.",
      });
    }
  }

  const text = await response.text();
  return text || undefined;
}

export async function send(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, {
      code: "network_error",
      message: "Не удалось связаться с сервером. Проверьте подключение и повторите попытку.",
      details: error,
    });
  }
  if (response.ok) return response;

  throw new ApiError(
    response.status,
    createErrorPayload(
      response.status,
      response.statusText,
      await readResponseBody(response),
      response.headers.get("x-request-id") ?? undefined,
    ),
  );
}

export async function request(
  path: string,
  options: RequestOptions = {},
): Promise<unknown> {
  const headers = new Headers({ Accept: "application/json" });
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);

  const response = await send(path, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
    keepalive: options.keepalive,
  });
  return readResponseBody(response);
}
