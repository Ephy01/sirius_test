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

export type DownloadedFile = {
  blob: Blob;
  filename: string;
};

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

export type AccessCodeOverview = {
  id: string;
  last4: string;
  status: AccessCodeStatus;
  createdAt?: string;
  expiresAt?: string | null;
  revokedAt?: string | null;
  redeemedAt?: string | null;
};

export type AttemptOverview = {
  id: string;
  number: number;
  status: AttemptStatus;
  startedAt?: string | null;
  deadlineAt?: string | null;
  finishedAt?: string | null;
};

export type ContestEnrollmentAccess = {
  id: string;
  contestId: string;
  participantId: string;
  participant: ParticipantSummary;
  status: EnrollmentStatus;
  createdAt?: string;
  latestCode: AccessCodeOverview | null;
  latestAttempt: AttemptOverview | null;
  attemptGrantPending: boolean;
};

export type RotatedAccessCode = {
  enrollmentId: string;
  code: string;
  codeLabel: string;
  status: AccessCodeStatus;
  expiresAt?: string | null;
};

export type AttemptGrantResponse = {
  enrollmentId: string;
  pending: boolean;
  created: boolean;
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

export type ParticipantTelemetryInput = {
  clientEventId: string;
  clientSessionId: string;
  eventType: ParticipantTelemetryEventType;
  attemptId?: string | null;
  taskId?: string | null;
  clientTimestamp?: string | null;
  clientElapsedMs?: number | null;
  payload?: Record<string, unknown>;
};

export type StartAttemptInput = Record<string, never>;

export type StartAttemptResponse = {
  attempt: AttemptSummary;
  created: boolean;
};

export type ChessPieceSymbol = "K" | "Q" | "R" | "B" | "N" | "P";
export type ChessBoardPieceSymbol = `w${ChessPieceSymbol}` | `b${ChessPieceSymbol}`;
export type ChessBoardState = (ChessBoardPieceSymbol | null)[][];

export type WorldContext = {
  world: string;
  episode: number;
  family: string;
  phase: "calibration" | "chapter" | "remediation" | "rotation" | string;
};

export type DiceDefinition = {
  id: string;
  label: string;
  faces: ChessPieceSymbol[];
};

export type DiceChessPublicState = {
  kind: "dice_chess_probability";
  prompt: string;
  dice: DiceDefinition[];
  sampleSpaceSize: number;
  eventDescription?: string;
  responseHint: string;
  worldContext?: WorldContext;
};

export type DiceChessPositionPublicState = {
  kind: "dice_chess_position_probability";
  prompt: string;
  board: ChessBoardState;
  sideToMove: "white" | "black";
  die: DiceDefinition;
  sampleSpaceSize: number;
  eventDescription: string;
  responseHint: string;
  worldContext?: WorldContext;
};

export type DiceChessInventoryPublicState = {
  kind: "dice_chess_board_inventory_probability";
  prompt: string;
  board: ChessBoardState;
  die: DiceDefinition;
  sampleSpaceSize: number;
  eventDescription: string;
  responseHint: string;
  worldContext?: WorldContext;
};

export type GeometryPoint = {
  id: string;
  group: string;
  x: number;
  y: number;
  label?: string;
  color?: string;
};

export type GeometryEdge = {
  id: string;
  group: string;
  source: string;
  target: string;
  color?: string;
};

export type GeometryScene = {
  bounds: {
    minX: number;
    maxX: number;
    minY: number;
    maxY: number;
  };
  points: GeometryPoint[];
  edges: GeometryEdge[];
};

export type GeometryPublicState = {
  kind: "geometry_atlas";
  family:
    | "geo_zendo"
    | "geo_transform"
    | "geo_probability";
  variant: string;
  prompt: string;
  scene: GeometryScene;
  content: Record<string, unknown>;
  interaction: Record<string, unknown>;
  responseHint: string;
  worldContext?: WorldContext;
};

export type TokenCard = {
  num: number;
  color: "R" | "G" | "B";
};

export type TokenZendoPublicState = {
  kind: "token_zendo";
  family: "token_zendo";
  variant: string;
  prompt: string;
  cards: Record<string, TokenCard[]>;
  content: Record<string, unknown>;
  interaction: Record<string, unknown>;
  responseHint: string;
  worldContext?: WorldContext;
};

export type FoldStep = {
  axis: "vertical" | "horizontal" | "diagonal";
  direction: string;
  label: string;
};

export type FoldPunchPublicState = {
  kind: "fold_punch";
  family: "fold_punch";
  variant: string;
  prompt: string;
  sheetSize: number;
  folds: FoldStep[];
  folded: {
    width: number;
    height: number;
    triangle: boolean;
    holes: [number, number][];
  };
  responseHint: string;
  worldContext?: WorldContext;
};

export type WiringObservation = {
  chord: string;
  training: boolean;
  effect: number[];
  lampsAfter: number[];
};

export type HiddenWiringPublicState = {
  kind: "hidden_wiring";
  family: "hidden_wiring";
  variant: "reach_target" | "predict_chords";
  prompt: string;
  legend: string;
  lampCount: number;
  buttonCount: number;
  ops: MachineOperation[];
  current: number[];
  target?: number[];
  examChords?: { id: string; label: string }[];
  chordBudget: number;
  chordsRemaining: number;
  observations: WiringObservation[];
  responseHint: string;
  worldContext?: WorldContext;
};

export type GridZendoPublicState = {
  kind: "grid_zendo";
  family: "grid_zendo";
  variant: string;
  prompt: string;
  cards: Record<string, string[]>;
  gridSize: number;
  content: Record<string, unknown>;
  interaction: Record<string, unknown>;
  responseHint: string;
  worldContext?: WorldContext;
};

export type PointZendoPublicState = {
  kind: "point_zendo";
  family: "point_zendo";
  variant: string;
  prompt: string;
  scene: GeometryScene;
  content: Record<string, unknown>;
  interaction: Record<string, unknown>;
  responseHint: string;
  worldContext?: WorldContext;
};

export type MachineSubKind =
  | "lamps_gf2"
  | "numeric_machine"
  | "perm_puzzle";

export type MachineState =
  | { lamps: number[] }
  | { value: number }
  | { cards: number[] };

export type MachineOperation = {
  id: string;
  label: string;
  spec: Record<string, unknown>;
};

export type MachinePanelPublicState = {
  kind: "machine_panel";
  subKind: MachineSubKind;
  prompt: string;
  ops: MachineOperation[];
  start: MachineState;
  target: MachineState;
  current: MachineState;
  stepsSoftCap: number;
  stepsTaken: number;
  responseHint: string;
  worldContext?: WorldContext;
};

export type BoardPoint = {
  row: number;
  col: number;
};

export type LeaperBoardPublicState = {
  kind: "chess";
  subKind: "leaper_board";
  prompt: string;
  ops: MachineOperation[];
  start: BoardPoint;
  target: BoardPoint;
  current: BoardPoint;
  stepsSoftCap: number;
  stepsTaken: number;
  rows: number;
  cols: number;
  blocked: BoardPoint[];
  jump?: { a: number; b: number };
  board: ChessBoardState;
  responseHint: string;
  worldContext?: WorldContext;
};

export type ClassicMathSubKind = "share_paradox" | "bar_seating";

export type ClassicMathTable = {
  columns: string[];
  rows: string[][];
};

export type ClassicMathPublicState = {
  kind: "classic_math_free_response";
  family: "classic_math";
  subKind: ClassicMathSubKind;
  title: string;
  prompt: string;
  responseHint: string;
  submissionTemplate: string;
  answerFormat: "free_response";
  scripted: true;
  table?: ClassicMathTable;
  seatCount?: number;
  worldContext?: WorldContext;
};

export type TaskPublicState =
  | DiceChessPublicState
  | DiceChessInventoryPublicState
  | DiceChessPositionPublicState
  | GeometryPublicState
  | TokenZendoPublicState
  | PointZendoPublicState
  | GridZendoPublicState
  | HiddenWiringPublicState
  | FoldPunchPublicState
  | MachinePanelPublicState
  | LeaperBoardPublicState
  | ClassicMathPublicState;

export type ParticipantTask = {
  id: string;
  ordinal: number;
  family: string;
  generatorVersion: string;
  difficulty: number;
  status: TaskStatus;
  publicState: TaskPublicState;
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

export type TaskInteractionInput =
  | {
      actionType: "probe";
      probe: string;
      clientActionId: string;
    }
  | {
      actionType: "hint";
      clientActionId: string;
    }
  | {
      actionType: "apply_op";
      opId: string;
      clientActionId: string;
    }
  | {
      actionType: "undo";
      clientActionId: string;
    };

export type DebugAnswerResponse = {
  family: string;
  answer: string;
  commands: string[];
  details: string[];
};

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

export type TaskInteractionResponse = {
  task: ParticipantTask;
  accepted: boolean;
  completed: boolean;
  message: string;
  clientActionId: string;
};

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  token?: string;
  body?: unknown;
  signal?: AbortSignal;
  keepalive?: boolean;
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

function parseAccessCodeStatus(value: unknown): AccessCodeStatus {
  return value === "revoked" || value === "expired" ? value : "active";
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
    status: parseAttemptStatus(value.status),
    startedAt: readNullableString(value, "startedAt", "started_at"),
    deadlineAt: readNullableString(value, "deadlineAt", "deadline_at"),
    finishedAt: readNullableString(value, "finishedAt", "finished_at"),
  };
}

function parseAccessCodeOverview(value: unknown): AccessCodeOverview | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: "Сервер вернул некорректные данные кода доступа.",
      details: value,
    });
  }

  return {
    id: requiredString(value, "code.id", "id"),
    last4: requiredString(value, "code.last4", "last4"),
    status: parseAccessCodeStatus(value.status),
    createdAt: readString(value, "createdAt", "created_at"),
    expiresAt: readNullableString(value, "expiresAt", "expires_at"),
    revokedAt: readNullableString(value, "revokedAt", "revoked_at"),
    redeemedAt: readNullableString(value, "redeemedAt", "redeemed_at"),
  };
}

function parseAttemptOverview(value: unknown): AttemptOverview | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: "Сервер вернул некорректные данные попытки.",
      details: value,
    });
  }

  return {
    id: requiredString(value, "attempt.id", "id"),
    number: readNumber(value, "number") ?? 1,
    status: parseAttemptStatus(value.status),
    startedAt: readNullableString(value, "startedAt", "started_at"),
    deadlineAt: readNullableString(value, "deadlineAt", "deadline_at"),
    finishedAt: readNullableString(value, "finishedAt", "finished_at"),
  };
}

function parseContestEnrollmentAccess(
  value: unknown,
  contestId: string,
): ContestEnrollmentAccess {
  if (!isRecord(value)) {
    throw new ApiError(502, {
      code: "invalid_api_response",
      message: "Сервер вернул некорректную строку доступа участника.",
      details: value,
    });
  }

  const participant = parseParticipant(value.participant);
  const latestCode = value.latestCode ?? value.latest_code;
  const latestAttempt = value.latestAttempt ?? value.latest_attempt;

  return {
    id: requiredString(value, "enrollment.id", "id"),
    contestId:
      readString(value, "contestId", "contest_id") ?? contestId,
    participantId:
      readString(value, "participantId", "participant_id") ?? participant.id,
    participant,
    status: parseEnrollmentStatus(value.status),
    createdAt: readString(value, "createdAt", "created_at"),
    latestCode: parseAccessCodeOverview(latestCode),
    latestAttempt: parseAttemptOverview(latestAttempt),
    attemptGrantPending:
      value.attemptGrantPending === true || value.attempt_grant_pending === true,
  };
}

function parseTaskStatus(value: unknown): TaskStatus {
  if (value === "answered" || value === "skipped") return value;
  return "active";
}

function isChessPieceSymbol(value: unknown): value is ChessPieceSymbol {
  return (
    value === "K" ||
    value === "Q" ||
    value === "R" ||
    value === "B" ||
    value === "N" ||
    value === "P"
  );
}

function isChessBoardPieceSymbol(
  value: unknown,
): value is ChessBoardPieceSymbol {
  return (
    typeof value === "string" &&
    value.length === 2 &&
    (value[0] === "w" || value[0] === "b") &&
    isChessPieceSymbol(value[1])
  );
}

function parsePieceSymbols(
  value: unknown,
  expectedLength: number,
): ChessPieceSymbol[] | null {
  const pieces =
    typeof value === "string"
      ? Array.from(value)
      : Array.isArray(value)
        ? value
        : [];
  return pieces.length === expectedLength && pieces.every(isChessPieceSymbol)
    ? pieces
    : null;
}

function parseDiceDefinition(
  value: unknown,
  index = 0,
): DiceDefinition | null {
  if (!isRecord(value)) return null;
  const faces = parsePieceSymbols(value.faces, 6);
  if (!faces) return null;
  return {
    id: readString(value, "id") ?? `die-${index + 1}`,
    label: readString(value, "label") ?? `Кубик ${index + 1}`,
    faces,
  };
}

function parseChessBoard(
  value: unknown,
  expectedRows = 8,
  expectedCols = 8,
): ChessBoardState | null {
  if (!Array.isArray(value) || value.length !== expectedRows) return null;
  const board: ChessBoardState = [];
  for (const rank of value) {
    if (!Array.isArray(rank) || rank.length !== expectedCols) return null;
    if (
      !rank.every(
        (piece) => piece === null || isChessBoardPieceSymbol(piece),
      )
    ) {
      return null;
    }
    board.push([...rank] as (ChessBoardPieceSymbol | null)[]);
  }
  return board;
}

function parseMachineOperations(value: unknown): MachineOperation[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const operations = value.flatMap((item): MachineOperation[] => {
    if (!isRecord(item)) return [];
    const id = readString(item, "id");
    const label = readString(item, "label");
    if (!id || !label) return [];
    return [{
      id,
      label,
      spec: isRecord(item.spec) ? item.spec : {},
    }];
  });
  return operations.length === value.length ? operations : null;
}

function parseMachineState(
  value: unknown,
  subKind: MachineSubKind,
): MachineState | null {
  if (!isRecord(value)) return null;
  if (subKind === "lamps_gf2") {
    const lamps = value.lamps;
    if (
      !Array.isArray(lamps) ||
      lamps.length === 0 ||
      !lamps.every((lamp) => lamp === 0 || lamp === 1)
    ) {
      return null;
    }
    return { lamps: [...lamps] as number[] };
  }
  if (subKind === "numeric_machine") {
    const number = readNumber(value, "value");
    return number === undefined ? null : { value: number };
  }
  const cards = value.cards;
  if (
    !Array.isArray(cards) ||
    cards.length === 0 ||
    !cards.every((card) => Number.isInteger(card))
  ) {
    return null;
  }
  return { cards: [...cards] as number[] };
}

function parseBoardPoint(value: unknown): BoardPoint | null {
  if (!isRecord(value)) return null;
  const row = readNumber(value, "row");
  const col = readNumber(value, "col");
  if (
    row === undefined ||
    col === undefined ||
    !Number.isInteger(row) ||
    !Number.isInteger(col)
  ) {
    return null;
  }
  return { row, col };
}

function parseGeometryScene(value: unknown): GeometryScene | null {
  if (!isRecord(value) || !isRecord(value.bounds)) return null;
  const minX = readNumber(value.bounds, "minX", "min_x");
  const maxX = readNumber(value.bounds, "maxX", "max_x");
  const minY = readNumber(value.bounds, "minY", "min_y");
  const maxY = readNumber(value.bounds, "maxY", "max_y");
  if (
    minX === undefined ||
    maxX === undefined ||
    minY === undefined ||
    maxY === undefined ||
    !Array.isArray(value.points) ||
    !Array.isArray(value.edges)
  ) {
    return null;
  }

  const points = value.points.flatMap((item): GeometryPoint[] => {
    if (!isRecord(item)) return [];
    const id = readString(item, "id");
    const x = readNumber(item, "x");
    const y = readNumber(item, "y");
    if (!id || x === undefined || y === undefined) return [];
    return [{
      id,
      group: readString(item, "group") ?? "main",
      x,
      y,
      label: readString(item, "label"),
      color: readString(item, "color"),
    }];
  });
  const pointIds = new Set(points.map((point) => point.id));
  const edges = value.edges.flatMap((item): GeometryEdge[] => {
    if (!isRecord(item)) return [];
    const source = readString(item, "source");
    const target = readString(item, "target");
    if (!source || !target || !pointIds.has(source) || !pointIds.has(target)) {
      return [];
    }
    return [{
      id: readString(item, "id") ?? `${source}-${target}`,
      group: readString(item, "group") ?? "main",
      source,
      target,
      color: readString(item, "color"),
    }];
  });

  return {
    bounds: { minX, maxX, minY, maxY },
    points,
    edges,
  };
}

function parseWorldContext(value: unknown): WorldContext | undefined {
  if (!isRecord(value)) return undefined;
  const world = readString(value, "world");
  const episode = readNumber(value, "episode");
  const family = readString(value, "family");
  const phase = readString(value, "phase");
  if (
    !world ||
    episode === undefined ||
    !family ||
    !phase
  ) {
    return undefined;
  }
  return { world, episode, family, phase };
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

  const kind = readString(publicStateValue, "kind");
  const prompt = requiredString(publicStateValue, "task.prompt", "prompt");
  const responseHint =
    readString(publicStateValue, "responseHint", "response_hint") ??
    (kind === "machine_panel" || kind === "chess"
      ? "/op op1 · /undo · done / impossible"
      : "/answer ваш ответ");
  const worldContext = parseWorldContext(
    publicStateValue.worldContext ?? publicStateValue.world_context,
  );
  let publicState: TaskPublicState;

  if (kind === "dice_chess_probability") {
    const diceValue = publicStateValue.dice;
    if (!Array.isArray(diceValue) || diceValue.length < 2 || diceValue.length > 4) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректный набор кубиков.",
        details: value,
      });
    }
    const dice = diceValue.map((die, index): DiceDefinition => {
      const parsed = parseDiceDefinition(die, index);
      if (!parsed) {
        throw new ApiError(502, {
          code: "invalid_api_response",
          message: "Каждый кубик должен содержать шесть шахматных граней.",
          details: die,
        });
      }
      return parsed;
    });
    publicState = {
      kind,
      prompt,
      dice,
      sampleSpaceSize:
        readNumber(
          publicStateValue,
          "sampleSpaceSize",
          "sample_space_size",
        ) ?? 6 ** dice.length,
      eventDescription: readString(
        publicStateValue,
        "eventDescription",
        "event_description",
      ),
      responseHint,
      worldContext,
    };
  } else if (kind === "dice_chess_board_inventory_probability") {
    const board = parseChessBoard(publicStateValue.board);
    const die = parseDiceDefinition(publicStateValue.die);
    const eventDescription = readString(
      publicStateValue,
      "eventDescription",
      "event_description",
    );
    if (!board || !die || !eventDescription) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректную задачу Dice & Chess.",
        details: value,
      });
    }
    publicState = {
      kind,
      prompt,
      board,
      die,
      sampleSpaceSize:
        readNumber(
          publicStateValue,
          "sampleSpaceSize",
          "sample_space_size",
        ) ?? 6,
      eventDescription,
      responseHint,
      worldContext,
    };
  } else if (kind === "dice_chess_position_probability") {
    const board = parseChessBoard(publicStateValue.board);
    const die = parseDiceDefinition(publicStateValue.die);
    const sideToMove = readString(
      publicStateValue,
      "sideToMove",
      "side_to_move",
    );
    const eventDescription = readString(
      publicStateValue,
      "eventDescription",
      "event_description",
    );
    if (
      !board ||
      !die ||
      !eventDescription ||
      (sideToMove !== "white" && sideToMove !== "black")
    ) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректную позицию Dice & Chess.",
        details: value,
      });
    }
    publicState = {
      kind,
      prompt,
      board,
      sideToMove,
      die,
      sampleSpaceSize:
        readNumber(
          publicStateValue,
          "sampleSpaceSize",
          "sample_space_size",
        ) ?? 6,
      eventDescription,
      responseHint,
      worldContext,
    };
  } else if (kind === "geometry_atlas") {
    const scene = parseGeometryScene(publicStateValue.scene);
    const family = readString(publicStateValue, "family");
    const variant = readString(publicStateValue, "variant");
    if (
      !scene ||
      !variant ||
      (family !== "geo_zendo" &&
        family !== "geo_transform" &&
        family !== "geo_probability")
    ) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректную сцену Геометрического мира.",
        details: value,
      });
    }
    publicState = {
      kind,
      family,
      variant,
      prompt,
      scene,
      content: isRecord(publicStateValue.content)
        ? publicStateValue.content
        : {},
      interaction: isRecord(publicStateValue.interaction)
        ? publicStateValue.interaction
        : {},
      responseHint,
      worldContext,
    };
  } else if (kind === "hidden_wiring") {
    const variantValue = readString(publicStateValue, "variant");
    const lampCount = readNumber(publicStateValue, "lampCount", "lamp_count");
    const buttonCount = readNumber(
      publicStateValue,
      "buttonCount",
      "button_count",
    );
    const operations = parseMachineOperations(publicStateValue.ops);
    const parseLamps = (value: unknown): number[] | null =>
      Array.isArray(value) &&
      value.every((item) => item === 0 || item === 1)
        ? (value as number[])
        : null;
    const current = parseLamps(publicStateValue.current);
    if (
      (variantValue !== "reach_target" && variantValue !== "predict_chords") ||
      lampCount === undefined ||
      buttonCount === undefined ||
      !operations ||
      !current
    ) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректную панель скрытой проводки.",
        details: value,
      });
    }
    const target = parseLamps(publicStateValue.target);
    const examChordsValue =
      publicStateValue.examChords ?? publicStateValue.exam_chords;
    const examChords = Array.isArray(examChordsValue)
      ? examChordsValue.flatMap((item) => {
          if (!isRecord(item)) return [];
          const id = readString(item, "id");
          if (!id) return [];
          return [{ id, label: readString(item, "label") ?? id }];
        })
      : undefined;
    const observationsValue = publicStateValue.observations;
    const observations: WiringObservation[] = Array.isArray(observationsValue)
      ? observationsValue.flatMap((item) => {
          if (!isRecord(item)) return [];
          const chord = readString(item, "chord");
          const effect = parseLamps(item.effect);
          const lampsAfter = parseLamps(
            item.lampsAfter ?? item.lamps_after,
          );
          if (!chord || !effect || !lampsAfter) return [];
          return [{
            chord,
            training: item.training === true,
            effect,
            lampsAfter,
          }];
        })
      : [];
    publicState = {
      kind,
      family: "hidden_wiring",
      variant: variantValue,
      prompt,
      legend:
        readString(publicStateValue, "legend") ??
        "Кнопки срабатывают только парами.",
      lampCount,
      buttonCount,
      ops: operations,
      current,
      target: target ?? undefined,
      examChords,
      chordBudget:
        readNumber(publicStateValue, "chordBudget", "chord_budget") ?? 8,
      chordsRemaining:
        readNumber(
          publicStateValue,
          "chordsRemaining",
          "chords_remaining",
        ) ?? 8,
      observations,
      responseHint,
      worldContext,
    };
  } else if (kind === "fold_punch") {
    const foldsValue = publicStateValue.folds;
    const foldedValue = publicStateValue.folded;
    const sheetSize =
      readNumber(publicStateValue, "sheetSize", "sheet_size") ?? 8;
    const folds: FoldStep[] = Array.isArray(foldsValue)
      ? foldsValue.flatMap((item) => {
          if (!isRecord(item)) return [];
          const axis = readString(item, "axis");
          const direction = readString(item, "direction");
          if (
            (axis !== "vertical" &&
              axis !== "horizontal" &&
              axis !== "diagonal") ||
            !direction
          ) {
            return [];
          }
          return [{
            axis,
            direction,
            label: readString(item, "label") ?? direction,
          }];
        })
      : [];
    const parseCellPairs = (value: unknown): [number, number][] | null =>
      Array.isArray(value) &&
      value.every(
        (item) =>
          Array.isArray(item) &&
          item.length === 2 &&
          item.every((part) => typeof part === "number"),
      )
        ? (value as [number, number][])
        : null;
    const holes = isRecord(foldedValue)
      ? parseCellPairs(foldedValue.holes)
      : null;
    const variantValue = readString(publicStateValue, "variant") ?? "unfold_holes";
    if (
      folds.length === 0 ||
      !isRecord(foldedValue) ||
      !holes ||
      readNumber(foldedValue, "width") === undefined ||
      readNumber(foldedValue, "height") === undefined
    ) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректную задачу дырокола.",
        details: value,
      });
    }
    publicState = {
      kind,
      family: "fold_punch",
      variant: variantValue,
      prompt,
      sheetSize,
      folds,
      folded: {
        width: readNumber(foldedValue, "width") ?? sheetSize,
        height: readNumber(foldedValue, "height") ?? sheetSize,
        triangle: foldedValue.triangle === true,
        holes,
      },
      responseHint,
      worldContext,
    };
  } else if (kind === "grid_zendo") {
    const cardsValue = publicStateValue.cards;
    const variant = readString(publicStateValue, "variant");
    const gridSize =
      readNumber(publicStateValue, "gridSize", "grid_size") ?? 5;
    const cards: Record<string, string[]> = {};
    if (isRecord(cardsValue)) {
      for (const [cardId, rows] of Object.entries(cardsValue)) {
        if (
          Array.isArray(rows) &&
          rows.length === gridSize &&
          rows.every(
            (row) =>
              typeof row === "string" &&
              row.length === gridSize &&
              [...row].every((cell) => cell === "0" || cell === "1"),
          )
        ) {
          cards[cardId] = rows as string[];
        }
      }
    }
    if (!variant || Object.keys(cards).length === 0) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректные узоры grid_zendo.",
        details: value,
      });
    }
    publicState = {
      kind,
      family: "grid_zendo",
      variant,
      prompt,
      cards,
      gridSize,
      content: isRecord(publicStateValue.content)
        ? publicStateValue.content
        : {},
      interaction: isRecord(publicStateValue.interaction)
        ? publicStateValue.interaction
        : {},
      responseHint,
      worldContext,
    };
  } else if (kind === "point_zendo") {
    const scene = parseGeometryScene(publicStateValue.scene);
    const variant = readString(publicStateValue, "variant");
    if (!scene || !variant) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректную сцену point_zendo.",
        details: value,
      });
    }
    publicState = {
      kind,
      family: "point_zendo",
      variant,
      prompt,
      scene,
      content: isRecord(publicStateValue.content)
        ? publicStateValue.content
        : {},
      interaction: isRecord(publicStateValue.interaction)
        ? publicStateValue.interaction
        : {},
      responseHint,
      worldContext,
    };
  } else if (kind === "token_zendo") {
    const cardsValue = publicStateValue.cards;
    const variant = readString(publicStateValue, "variant");
    const cards: Record<string, TokenCard[]> = {};
    if (isRecord(cardsValue)) {
      for (const [cardId, tokens] of Object.entries(cardsValue)) {
        if (!Array.isArray(tokens)) continue;
        const parsedTokens = tokens.flatMap((item): TokenCard[] => {
          if (!isRecord(item)) return [];
          const num = readNumber(item, "num");
          const color = readString(item, "color");
          if (
            num === undefined ||
            !Number.isInteger(num) ||
            (color !== "R" && color !== "G" && color !== "B")
          ) {
            return [];
          }
          return [{ num, color }];
        });
        if (parsedTokens.length === tokens.length) {
          cards[cardId] = parsedTokens;
        }
      }
    }
    if (!variant || Object.keys(cards).length === 0) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректные карточки token_zendo.",
        details: value,
      });
    }
    publicState = {
      kind,
      family: "token_zendo",
      variant,
      prompt,
      cards,
      content: isRecord(publicStateValue.content)
        ? publicStateValue.content
        : {},
      interaction: isRecord(publicStateValue.interaction)
        ? publicStateValue.interaction
        : {},
      responseHint,
      worldContext,
    };
  } else if (kind === "machine_panel") {
    const subKindValue = readString(
      publicStateValue,
      "subKind",
      "sub_kind",
    );
    const subKind =
      subKindValue === "lamps_gf2" ||
      subKindValue === "numeric_machine" ||
      subKindValue === "perm_puzzle"
        ? subKindValue
        : undefined;
    const operations = parseMachineOperations(publicStateValue.ops);
    const start = subKind
      ? parseMachineState(publicStateValue.start, subKind)
      : null;
    const target = subKind
      ? parseMachineState(publicStateValue.target, subKind)
      : null;
    const current = subKind
      ? parseMachineState(publicStateValue.current, subKind)
      : null;
    if (!subKind || !operations || !start || !target || !current) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректное состояние машины.",
        details: value,
      });
    }
    publicState = {
      kind,
      subKind,
      prompt,
      ops: operations,
      start,
      target,
      current,
      stepsSoftCap:
        readNumber(publicStateValue, "stepsSoftCap", "steps_soft_cap") ?? 24,
      stepsTaken:
        readNumber(publicStateValue, "stepsTaken", "steps_taken") ?? 0,
      responseHint,
      worldContext,
    };
  } else if (
    kind === "chess" &&
    readString(publicStateValue, "subKind", "sub_kind") === "leaper_board"
  ) {
    const rows = readNumber(publicStateValue, "rows");
    const cols = readNumber(publicStateValue, "cols");
    const operations = parseMachineOperations(publicStateValue.ops);
    const start = parseBoardPoint(publicStateValue.start);
    const target = parseBoardPoint(publicStateValue.target);
    const current = parseBoardPoint(publicStateValue.current);
    const blockedValue = publicStateValue.blocked;
    const blocked = Array.isArray(blockedValue)
      ? blockedValue.map(parseBoardPoint)
      : [];
    const board =
      rows !== undefined && cols !== undefined
        ? parseChessBoard(publicStateValue.board, rows, cols)
        : null;
    const jumpValue = publicStateValue.jump;
    const jumpA = isRecord(jumpValue) ? readNumber(jumpValue, "a") : undefined;
    const jumpB = isRecord(jumpValue) ? readNumber(jumpValue, "b") : undefined;
    if (
      rows === undefined ||
      cols === undefined ||
      !Number.isInteger(rows) ||
      !Number.isInteger(cols) ||
      rows < 1 ||
      rows > 8 ||
      cols < 1 ||
      cols > 8 ||
      !operations ||
      !start ||
      !target ||
      !current ||
      !board ||
      blocked.some((point) => point === null)
    ) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректную доску прыгуна.",
        details: value,
      });
    }
    publicState = {
      kind,
      subKind: "leaper_board",
      prompt,
      ops: operations,
      start,
      target,
      current,
      stepsSoftCap:
        readNumber(publicStateValue, "stepsSoftCap", "steps_soft_cap") ?? 24,
      stepsTaken:
        readNumber(publicStateValue, "stepsTaken", "steps_taken") ?? 0,
      rows,
      cols,
      blocked: blocked as BoardPoint[],
      jump:
        jumpA === undefined || jumpB === undefined
          ? undefined
          : { a: jumpA, b: jumpB },
      board,
      responseHint,
      worldContext,
    };
  } else if (kind === "classic_math_free_response") {
    const family = readString(publicStateValue, "family");
    const subKindValue = readString(
      publicStateValue,
      "subKind",
      "sub_kind",
    );
    const title = readString(publicStateValue, "title");
    const answerFormat = readString(
      publicStateValue,
      "answerFormat",
      "answer_format",
    );
    const submissionTemplate = readString(
      publicStateValue,
      "submissionTemplate",
      "submission_template",
    );
    const subKind =
      subKindValue === "share_paradox" || subKindValue === "bar_seating"
        ? subKindValue
        : undefined;

    if (
      family !== "classic_math" ||
      !subKind ||
      !title ||
      !submissionTemplate ||
      answerFormat !== "free_response"
    ) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректную классическую задачу.",
        details: value,
      });
    }

    const tableValue = publicStateValue.table;
    let table: ClassicMathTable | undefined;
    if (isRecord(tableValue) && Array.isArray(tableValue.columns)) {
      const columns = tableValue.columns.filter(
        (column): column is string => typeof column === "string",
      );
      const rows = Array.isArray(tableValue.rows)
        ? tableValue.rows.flatMap((row): string[][] =>
            Array.isArray(row) &&
            row.length === columns.length &&
            row.every((cell) => typeof cell === "string")
              ? [row as string[]]
              : [],
          )
        : [];
      if (
        columns.length === tableValue.columns.length &&
        columns.length > 0 &&
        rows.length > 0
      ) {
        table = { columns, rows };
      }
    }

    publicState = {
      kind,
      family,
      subKind,
      title,
      prompt,
      responseHint,
      submissionTemplate,
      answerFormat,
      scripted: true,
      table,
      seatCount: readNumber(publicStateValue, "seatCount", "seat_count"),
      worldContext,
    };
  } else {
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
    publicState,
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

function parseAiRemaining(value: unknown): AiTurnRemaining {
  if (!isRecord(value)) return { task: 0, attempt: 0 };
  return {
    task: readNumber(value, "task") ?? 0,
    attempt: readNumber(value, "attempt") ?? 0,
  };
}

function parseAiTurn(body: Record<string, unknown>): AiTurn {
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

function contentDispositionFilename(value: string | null): string | undefined {
  if (!value) return undefined;

  const encodedMatch = value.match(
    /(?:^|;)\s*filename\*\s*=\s*(?:"([^"]+)"|([^;]+))/i,
  );
  if (encodedMatch) {
    const encodedValue = (encodedMatch[1] ?? encodedMatch[2] ?? "").trim();
    const filenameValue =
      encodedValue.match(/^[^']*'[^']*'(.*)$/)?.[1] ?? encodedValue;
    try {
      return decodeURIComponent(filenameValue);
    } catch {
      // Fall back to the regular filename parameter below.
    }
  }

  const quotedMatch = value.match(
    /(?:^|;)\s*filename\s*=\s*"((?:[^"\\]|\\.)*)"/i,
  );
  if (quotedMatch) {
    return quotedMatch[1].replace(/\\(["\\])/g, "$1");
  }

  return value
    .match(/(?:^|;)\s*filename\s*=\s*([^;]+)/i)?.[1]
    ?.trim();
}

function sanitizeFilename(value: string): string {
  return Array.from(
    value.replace(/[\u0000-\u001f\u007f/\\]/g, "_").trim(),
  )
    .slice(0, 180)
    .join("")
    .replace(/^\.+$/, "");
}

function safeDownloadFilename(
  candidate: string | undefined,
  fallback: string,
): string {
  return (
    (candidate ? sanitizeFilename(candidate) : "") ||
    sanitizeFilename(fallback) ||
    "download.txt"
  );
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
        keepalive: options.keepalive,
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

  private async requestFile(
    path: string,
    fallbackFilename: string,
    options: AuthenticatedRequestOptions,
  ): Promise<DownloadedFile> {
    const headers = new Headers({
      Accept: "text/plain, application/octet-stream",
      Authorization: `Bearer ${options.token}`,
    });

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method: "GET",
        headers,
        signal: options.signal,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(0, {
        code: "network_error",
        message:
          "Не удалось связаться с сервером. Проверьте подключение и повторите попытку.",
        details: error,
      });
    }

    if (!response.ok) {
      const body = await readResponseBody(response);
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

    let blob: Blob;
    try {
      blob = await response.blob();
    } catch (error) {
      throw new ApiError(502, {
        code: "invalid_file_response",
        message: "Не удалось прочитать файл, полученный от сервера.",
        details: error,
      });
    }

    return {
      blob,
      filename: safeDownloadFilename(
        contentDispositionFilename(response.headers.get("content-disposition")),
        fallbackFilename,
      ),
    };
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

  async deleteContest(
    contestId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<void> {
    await this.request(`/contests/${encodeURIComponent(contestId)}`, {
      ...options,
      method: "DELETE",
    });
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

  async listContestEnrollments(
    contestId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<ContestEnrollmentAccess[]> {
    const body = await this.request(
      `/contests/${encodeURIComponent(contestId)}/enrollments`,
      options,
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
        message: "Сервер вернул некорректный список доступов.",
        details: body,
      });
    }

    return items.map((item) => parseContestEnrollmentAccess(item, contestId));
  }

  async downloadEnrollmentTelemetry(
    contestId: string,
    enrollmentId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<DownloadedFile> {
    return this.requestFile(
      `/contests/${encodeURIComponent(contestId)}/enrollments/${encodeURIComponent(enrollmentId)}/telemetry`,
      `telemetry-${enrollmentId}.txt`,
      options,
    );
  }

  async rotateEnrollmentCode(
    contestId: string,
    enrollmentId: string,
    input: { expiresAt?: string | null },
    options: AuthenticatedRequestOptions,
  ): Promise<RotatedAccessCode> {
    const body = await this.request(
      `/contests/${encodeURIComponent(contestId)}/enrollments/${encodeURIComponent(enrollmentId)}/codes/rotate`,
      {
        ...options,
        method: "POST",
        body: { expires_at: input.expiresAt },
      },
    );
    const value = isRecord(body) && isRecord(body.item) ? body.item : body;
    if (!isRecord(value)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректный новый код.",
        details: body,
      });
    }

    const last4 =
      readString(value, "last4") ??
      readString(value, "codeLabel", "code_label")?.slice(-4);

    return {
      enrollmentId:
        readString(value, "enrollmentId", "enrollment_id") ?? enrollmentId,
      code: requiredString(value, "code", "code"),
      codeLabel:
        readString(value, "codeLabel", "code_label") ??
        (last4 ? `••••${last4}` : "Новый код"),
      status: parseAccessCodeStatus(value.status),
      expiresAt: readNullableString(value, "expiresAt", "expires_at"),
    };
  }

  async grantNextAttempt(
    contestId: string,
    enrollmentId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<AttemptGrantResponse> {
    const body = await this.request(
      `/contests/${encodeURIComponent(contestId)}/enrollments/${encodeURIComponent(enrollmentId)}/attempts/grant`,
      {
        ...options,
        method: "POST",
      },
    );
    if (!isRecord(body)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректное подтверждение новой попытки.",
        details: body,
      });
    }

    return {
      enrollmentId:
        readString(body, "enrollmentId", "enrollment_id") ?? enrollmentId,
      pending: body.pending === true,
      created: body.created === true,
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

  async recordParticipantTelemetry(
    input: ParticipantTelemetryInput,
    options: AuthenticatedRequestOptions,
  ): Promise<void> {
    await this.request("/participant/telemetry", {
      ...options,
      method: "POST",
      keepalive: true,
      body: {
        client_event_id: input.clientEventId,
        client_session_id: input.clientSessionId,
        event_type: input.eventType,
        attempt_id: input.attemptId,
        task_id: input.taskId,
        client_timestamp: input.clientTimestamp,
        client_elapsed_ms: input.clientElapsedMs,
        payload: input.payload,
      },
    });
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

  async interactWithTask(
    taskId: string,
    input: TaskInteractionInput,
    options: AuthenticatedRequestOptions,
  ): Promise<TaskInteractionResponse> {
    const body = await this.request(
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
    );
    if (!isRecord(body)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректный результат хода.",
        details: body,
      });
    }

    return {
      task: parseParticipantTask(body.task),
      accepted: body.accepted === true,
      completed: body.completed === true,
      message:
        readString(body, "message") ??
        (body.accepted === true
          ? "Арбитр принял ход."
          : "Арбитр отклонил ход."),
      clientActionId:
        readString(body, "clientActionId", "client_action_id") ??
        input.clientActionId,
    };
  }

  async getParticipantDebugAnswer(
    taskId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<DebugAnswerResponse> {
    const body = await this.request(
      `/participant/tasks/${encodeURIComponent(taskId)}/debug-answer`,
      options,
    );
    if (!isRecord(body)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректный эталонный ответ.",
        details: body,
      });
    }
    return {
      family: readString(body, "family") ?? "",
      answer: readString(body, "answer") ?? "",
      commands: Array.isArray(body.commands)
        ? body.commands.filter(
            (item): item is string => typeof item === "string",
          )
        : [],
      details: Array.isArray(body.details)
        ? body.details.filter(
            (item): item is string => typeof item === "string",
          )
        : [],
    };
  }

  async sendAiTurn(
    taskId: string,
    input: { clientActionId: string; message: string },
    options: AuthenticatedRequestOptions,
  ): Promise<AiTurn> {
    const body = await this.request(
      `/participant/tasks/${encodeURIComponent(taskId)}/ai/turns`,
      {
        ...options,
        method: "POST",
        body: {
          clientActionId: input.clientActionId,
          message: input.message,
        },
      },
    );
    if (!isRecord(body)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректный ответ ассистента.",
        details: body,
      });
    }
    return parseAiTurn(body);
  }

  async getAiTurns(
    taskId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<AiTurnHistory> {
    const body = await this.request(
      `/participant/tasks/${encodeURIComponent(taskId)}/ai/turns`,
      options,
    );
    if (!isRecord(body)) {
      throw new ApiError(502, {
        code: "invalid_api_response",
        message: "Сервер вернул некорректную историю диалога.",
        details: body,
      });
    }
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
