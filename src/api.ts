const DEFAULT_API_BASE_URL = "/api/v1";

export type AccessRole = "organizer" | "participant";
export type ContestStatus = "draft" | "published";
export type EnrollmentStatus = "registered" | "disabled";
export type AccessCodeStatus = "active" | "revoked" | "expired";
export type AttemptStatus = "active" | "completed" | "expired";
export type TaskStatus = "active" | "answered" | "skipped";

export type ApiErrorPayload = {
  code?: string;
  message: string;
  details?: unknown;
  requestId?: string;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly details?: unknown;
  readonly requestId?: string;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message);
    this.name = "ApiError";
    this.status = status;
    this.code = payload.code;
    this.details = payload.details;
    this.requestId = payload.requestId;
  }
}

export type ContestSummary = {
  id: string;
  title: string;
  status: ContestStatus;
  durationMinutes: number;
  environmentKey?: string;
  participantCount?: number;
  createdAt?: string;
  publishedAt?: string | null;
};

export type Contest = ContestSummary & {
  description?: string | null;
  environmentFamilies?: string[];
  taskConfig?: Record<string, unknown>;
  settings?: Record<string, unknown>;
  updatedAt?: string;
};

export type ParticipantSummary = {
  id: string;
  displayName: string;
  externalRef?: string | null;
};

export type EnrollmentSummary = {
  id: string;
  contestId: string;
  participantId: string;
  participant?: ParticipantSummary;
  status: EnrollmentStatus;
  createdAt?: string;
};

export type AttemptSummary = {
  id: string;
  enrollmentId: string;
  number: number;
  seed: number;
  status: AttemptStatus;
  startedAt?: string | null;
  deadlineAt?: string | null;
  finishedAt?: string | null;
};

export type RedeemCodeResponse = {
  accessToken: string;
  tokenType: "bearer" | string;
  role: AccessRole;
  expiresAt?: string | null;
};

export type CreateContestInput = {
  title: string;
  durationMinutes: number;
  description?: string;
  environmentKey?: string;
  taskConfig?: Record<string, unknown>;
  environmentFamilies?: string[];
  settings?: Record<string, unknown>;
};

export type EnrollmentInput = {
  displayName: string;
  externalRef?: string;
};

export type AddEnrollmentsInput = {
  participants: EnrollmentInput[];
};

export type AddEnrollmentsResponse = {
  enrollments: EnrollmentSummary[];
  createdCount: number;
};

export type GenerateCodesInput = {
  rotate?: boolean;
  expiresAt?: string | null;
};

export type GeneratedAccessCode = {
  enrollmentId: string;
  participantId: string;
  participantName: string;
  participantExternalRef?: string;
  code: string;
  codeLabel: string;
  status: AccessCodeStatus;
  expiresAt?: string | null;
};

export type GenerateCodesResponse = {
  codes: GeneratedAccessCode[];
  generatedCount: number;
};

export type ParticipantContext = {
  contest: ContestSummary;
  participant: ParticipantSummary;
  enrollment: EnrollmentSummary;
  attempt?: AttemptSummary | null;
};

export type StartAttemptInput = Record<string, never>;

export type StartAttemptResponse = {
  attempt: AttemptSummary;
  created: boolean;
};

export type Chess960PublicState = {
  kind: "chess960_validation";
  prompt: string;
  backRank: string[];
  responseHint: string;
};

export type ParticipantTask = {
  id: string;
  ordinal: number;
  family: string;
  generatorVersion: string;
  difficulty: number;
  status: TaskStatus;
  publicState: Chess960PublicState;
  createdAt?: string;
  resolvedAt?: string | null;
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

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  token?: string;
  body?: unknown;
  signal?: AbortSignal;
};

export type AuthenticatedRequestOptions = {
  token: string;
  signal?: AbortSignal;
};

export type PublicRequestOptions = {
  signal?: AbortSignal;
};

type UnknownRecord = Record<string, unknown>;

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

function readNumber(record: UnknownRecord, ...keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
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

function requiredString(record: UnknownRecord, label: string, ...keys: string[]): string {
  const value = readString(record, ...keys);
  if (!value) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: `Сервер вернул некорректное поле «${label}».`,
      details: record,
    });
  }
  return value;
}

function parseContestStatus(value: unknown): ContestStatus {
  return value === "published" ? value : "draft";
}

function parseEnrollmentStatus(value: unknown): EnrollmentStatus {
  return value === "disabled" ? value : "registered";
}

function parseAttemptStatus(value: unknown): AttemptStatus {
  return value === "completed" || value === "expired" ? value : "active";
}

function parseContestSummary(value: unknown): ContestSummary {
  if (!isRecord(value)) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: "Сервер вернул некорректные данные контеста.",
      details: value,
    });
  }

  return {
    id: requiredString(value, "contest.id", "id"),
    title: requiredString(value, "contest.title", "title", "name"),
    status: parseContestStatus(value.status),
    durationMinutes:
      readNumber(value, "durationMinutes", "duration_minutes") ?? 60,
    participantCount: readNumber(value, "participantCount", "participant_count"),
    environmentKey: readString(value, "environmentKey", "environment_key"),
    createdAt: readString(value, "createdAt", "created_at"),
    publishedAt: readNullableString(value, "publishedAt", "published_at"),
  };
}

function parseParticipant(value: unknown): ParticipantSummary {
  if (!isRecord(value)) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: "Сервер вернул некорректные данные участника.",
      details: value,
    });
  }

  return {
    id: requiredString(value, "participant.id", "id"),
    displayName: requiredString(
      value,
      "participant.displayName",
      "displayName",
      "display_name",
      "name",
    ),
    externalRef: readNullableString(
      value,
      "externalRef",
      "external_ref",
      "externalId",
      "external_id",
    ),
  };
}

function parseEnrollment(value: unknown): EnrollmentSummary {
  if (!isRecord(value)) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: "Сервер вернул некорректную регистрацию участника.",
      details: value,
    });
  }

  const participant =
    value.participant === undefined ? undefined : parseParticipant(value.participant);
  const participantId =
    readString(value, "participantId", "participant_id") ?? participant?.id;
  if (!participantId) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: "Сервер вернул регистрацию без участника.",
      details: value,
    });
  }

  return {
    id: requiredString(value, "enrollment.id", "id"),
    contestId: requiredString(value, "enrollment.contestId", "contestId", "contest_id"),
    participantId,
    participant,
    status: parseEnrollmentStatus(value.status),
    createdAt: readString(value, "createdAt", "created_at"),
  };
}

function parseAttempt(value: unknown): AttemptSummary {
  if (!isRecord(value)) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: "Сервер вернул некорректные данные попытки.",
      details: value,
    });
  }

  return {
    id: requiredString(value, "attempt.id", "id"),
    enrollmentId: requiredString(
      value,
      "attempt.enrollmentId",
      "enrollmentId",
      "enrollment_id",
    ),
    number: readNumber(value, "number") ?? 1,
    seed: readNumber(value, "seed") ?? 0,
    status: parseAttemptStatus(value.status),
    startedAt: readNullableString(value, "startedAt", "started_at"),
    deadlineAt: readNullableString(value, "deadlineAt", "deadline_at"),
    finishedAt: readNullableString(value, "finishedAt", "finished_at"),
  };
}

function parseTaskStatus(value: unknown): TaskStatus {
  if (value === "answered" || value === "skipped") return value;
  return "active";
}

function parseParticipantTask(value: unknown): ParticipantTask {
  if (!isRecord(value)) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: "Сервер вернул некорректную задачу.",
      details: value,
    });
  }

  const publicStateValue = value.publicState ?? value.public_state;
  if (!isRecord(publicStateValue)) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: "Сервер вернул задачу без публичного состояния.",
      details: value,
    });
  }

  const backRankValue = publicStateValue.backRank ?? publicStateValue.back_rank;
  const backRank =
    typeof backRankValue === "string"
      ? Array.from(backRankValue)
      : Array.isArray(backRankValue)
        ? backRankValue.filter((piece): piece is string => typeof piece === "string")
        : [];
  if (backRank.length !== 8) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: "Сервер вернул некорректную позицию Chess960.",
      details: value,
    });
  }

  const kind = readString(publicStateValue, "kind");
  if (kind !== "chess960_validation") {
    throw new ApiError(502, {
      code: "unsupported_task_kind",
      message: "Этот тип задачи пока не поддерживается интерфейсом.",
      details: value,
    });
  }

  return {
    id: requiredString(value, "task.id", "id"),
    ordinal: readNumber(value, "ordinal") ?? 1,
    family: requiredString(value, "task.family", "family"),
    generatorVersion: requiredString(
      value,
      "task.generatorVersion",
      "generatorVersion",
      "generator_version",
    ),
    difficulty: readNumber(value, "difficulty") ?? 1,
    status: parseTaskStatus(value.status),
    publicState: {
      kind,
      prompt: requiredString(publicStateValue, "task.prompt", "prompt"),
      backRank,
      responseHint: requiredString(
        publicStateValue,
        "task.responseHint",
        "responseHint",
        "response_hint",
      ),
    },
    createdAt: readString(value, "createdAt", "created_at"),
    resolvedAt: readNullableString(
      value,
      "resolvedAt",
      "resolved_at",
      "completedAt",
      "completed_at",
      "answeredAt",
      "answered_at",
    ),
  };
}

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

export class ApiClient {
  readonly baseUrl: string;

  constructor(baseUrl = getDefaultApiBaseUrl()) {
    this.baseUrl = normalizeBaseUrl(baseUrl);
  }

  private async request(path: string, options: RequestOptions = {}): Promise<unknown> {
    const headers = new Headers({ Accept: "application/json" });
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    if (options.token) headers.set("Authorization", `Bearer ${options.token}`);

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method: options.method ?? "GET",
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: options.signal,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(0, {
        code: "network_error",
        message: "Не удалось связаться с сервером. Проверьте подключение и повторите попытку.",
        details: error,
      });
    }
    const body = await readResponseBody(response);

    if (!response.ok) {
      throw new ApiError(
        response.status,
        createErrorPayload(
          response.status,
          response.statusText,
          body,
          response.headers.get("x-request-id") ?? undefined,
        ),
      );
    }

    return body;
  }

  async redeemCode(
    code: string,
    options: PublicRequestOptions = {},
  ): Promise<RedeemCodeResponse> {
    const body = await this.request("/access/redeem", {
      method: "POST",
      body: { code },
      signal: options.signal,
    });

    const response = isRecord(body) && isRecord(body.session) ? body.session : body;
    if (!isRecord(response)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректную сессию доступа.",
        details: body,
      });
    }

    const role = readString(response, "role");
    if (role !== "organizer" && role !== "participant") {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул неизвестную роль доступа.",
        details: body,
      });
    }

    return {
      accessToken: requiredString(
        response,
        "accessToken",
        "accessToken",
        "access_token",
        "token",
      ),
      tokenType: readString(response, "tokenType", "token_type") ?? "bearer",
      role,
      expiresAt: readNullableString(response, "expiresAt", "expires_at"),
    };
  }

  async listContests(options: AuthenticatedRequestOptions): Promise<ContestSummary[]> {
    const body = await this.request("/contests", options);
    const items = Array.isArray(body)
      ? body
      : isRecord(body) && Array.isArray(body.items)
        ? body.items
        : null;

    if (!items) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректный список контестов.",
        details: body,
      });
    }

    return items.map(parseContestSummary);
  }

  async createContest(
    input: CreateContestInput,
    options: AuthenticatedRequestOptions,
  ): Promise<Contest> {
    const body = await this.request("/contests", {
      ...options,
      method: "POST",
      body: {
        title: input.title,
        duration_minutes: input.durationMinutes,
        description: input.description,
        environment_key: input.environmentKey,
        task_config: input.taskConfig,
        environment_families: input.environmentFamilies,
        settings: input.settings,
      },
    });
    const summary = parseContestSummary(body);
    const record = isRecord(body) ? body : {};

    return {
      ...summary,
      description: readNullableString(record, "description"),
      environmentKey: readString(record, "environmentKey", "environment_key"),
      taskConfig: isRecord(record.task_config) ? record.task_config : undefined,
      environmentFamilies: Array.isArray(record.environment_families)
        ? record.environment_families.filter(
            (value): value is string => typeof value === "string",
          )
        : undefined,
      settings: isRecord(record.settings) ? record.settings : undefined,
      updatedAt: readString(record, "updatedAt", "updated_at"),
    };
  }

  async addEnrollments(
    contestId: string,
    input: AddEnrollmentsInput,
    options: AuthenticatedRequestOptions,
  ): Promise<AddEnrollmentsResponse> {
    const body = await this.request(
      `/contests/${encodeURIComponent(contestId)}/enrollments`,
      {
        ...options,
        method: "POST",
        body: {
          participants: input.participants.map((participant) => ({
            display_name: participant.displayName,
            external_ref: participant.externalRef,
          })),
        },
      },
    );
    const items =
      isRecord(body) && Array.isArray(body.items)
        ? body.items
        : Array.isArray(body)
          ? body
          : null;

    if (!items) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректный список регистраций.",
        details: body,
      });
    }

    return {
      enrollments: items.map(parseEnrollment),
      createdCount:
        isRecord(body) ? readNumber(body, "createdCount", "created_count") ?? items.length : items.length,
    };
  }

  async generateCodes(
    contestId: string,
    input: GenerateCodesInput,
    options: AuthenticatedRequestOptions,
  ): Promise<GenerateCodesResponse> {
    const body = await this.request(
      `/contests/${encodeURIComponent(contestId)}/codes`,
      {
        ...options,
        method: "POST",
        body: {
          rotate: input.rotate,
          expires_at: input.expiresAt,
        },
      },
    );
    const items =
      isRecord(body) && Array.isArray(body.items)
        ? body.items
        : Array.isArray(body)
          ? body
          : null;

    if (!items) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректный список кодов.",
        details: body,
      });
    }

    return {
      codes: items.map((item) => {
        if (!isRecord(item)) {
          throw new ApiError(502, {
            code: "invalid_api_response",
            message: "Сервер вернул некорректный код доступа.",
            details: item,
          });
        }
        const status = readString(item, "status");
        const participant = isRecord(item.participant) ? item.participant : {};

        return {
          enrollmentId: requiredString(
            item,
            "enrollmentId",
            "enrollmentId",
            "enrollment_id",
          ),
          participantId: requiredString(
            participant,
            "participantId",
            "id",
          ),
          participantName: requiredString(
            participant,
            "participantName",
            "displayName",
            "display_name",
          ),
          participantExternalRef: readString(
            participant,
            "externalRef",
            "external_ref",
          ),
          code: requiredString(item, "code", "code"),
          codeLabel:
            readString(item, "codeLabel", "code_label") ??
            `••••${requiredString(item, "last4", "last4")}`,
          status: status === "revoked" || status === "expired" ? status : "active",
          expiresAt: readNullableString(item, "expiresAt", "expires_at"),
        };
      }),
      generatedCount:
        isRecord(body) ? readNumber(body, "generatedCount", "generated_count") ?? items.length : items.length,
    };
  }

  async publishContest(
    contestId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<Contest> {
    const body = await this.request(
      `/contests/${encodeURIComponent(contestId)}/publish`,
      { ...options, method: "POST" },
    );
    const summary = parseContestSummary(body);
    const record = isRecord(body) ? body : {};

    return {
      ...summary,
      description: readNullableString(record, "description"),
      environmentKey: readString(record, "environmentKey", "environment_key"),
      taskConfig: isRecord(record.task_config) ? record.task_config : undefined,
      environmentFamilies: Array.isArray(record.environment_families)
        ? record.environment_families.filter(
            (value): value is string => typeof value === "string",
          )
        : undefined,
      settings: isRecord(record.settings) ? record.settings : undefined,
      updatedAt: readString(record, "updatedAt", "updated_at"),
    };
  }

  async getParticipantContext(
    options: AuthenticatedRequestOptions,
  ): Promise<ParticipantContext> {
    const body = await this.request("/participant/context", options);
    if (!isRecord(body)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректный контекст участника.",
        details: body,
      });
    }

    return {
      contest: parseContestSummary(body.contest),
      participant: parseParticipant(body.participant),
      enrollment: parseEnrollment(body.enrollment),
      attempt:
        (body.activeAttempt ?? body.active_attempt) === null
          ? null
          : (body.activeAttempt ?? body.active_attempt) === undefined
            ? undefined
            : parseAttempt(body.activeAttempt ?? body.active_attempt),
    };
  }

  async startAttempt(
    input: StartAttemptInput,
    options: AuthenticatedRequestOptions,
  ): Promise<StartAttemptResponse> {
    const body = await this.request("/participant/attempts/start", {
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

  async getCurrentTask(
    options: AuthenticatedRequestOptions,
  ): Promise<CurrentTaskResponse> {
    const body = await this.request("/participant/tasks/current", options);
    if (!isRecord(body)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректный ответ задачи.",
        details: body,
      });
    }

    return {
      task: body.task === null ? null : parseParticipantTask(body.task),
    };
  }

  async getNextTask(
    options: AuthenticatedRequestOptions,
  ): Promise<NextTaskResponse> {
    const body = await this.request("/participant/tasks/next", {
      ...options,
      method: "POST",
    });
    if (!isRecord(body)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректный ответ следующей задачи.",
        details: body,
      });
    }

    return {
      task: parseParticipantTask(body.task),
      created: typeof body.created === "boolean" ? body.created : false,
    };
  }

  async answerTask(
    taskId: string,
    answer: string,
    options: AuthenticatedRequestOptions,
  ): Promise<TaskActionResponse> {
    const body = await this.request(
      `/participant/tasks/${encodeURIComponent(taskId)}/answer`,
      {
        ...options,
        method: "POST",
        body: { answer },
      },
    );
    if (!isRecord(body)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректное подтверждение ответа.",
        details: body,
      });
    }

    return {
      task: parseParticipantTask(body.task),
      message:
        readString(body, "message") ??
        "Ответ зафиксирован. Когда будете готовы, перейдите дальше.",
    };
  }

  async skipTask(
    taskId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<TaskActionResponse> {
    const body = await this.request(
      `/participant/tasks/${encodeURIComponent(taskId)}/skip`,
      {
        ...options,
        method: "POST",
      },
    );
    if (!isRecord(body)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректное подтверждение пропуска.",
        details: body,
      });
    }

    return {
      task: parseParticipantTask(body.task),
      message:
        readString(body, "message") ??
        "Задача пропущена. Когда будете готовы, перейдите дальше.",
    };
  }
}

export const api = new ApiClient();
