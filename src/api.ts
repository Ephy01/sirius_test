const DEFAULT_API_BASE_URL = "/api/v1";
const CONTEST_ENVIRONMENT = "mixed";

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
  participantCount?: number;
  createdAt?: string;
  publishedAt?: string | null;
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
  role: AccessRole;
  expiresAt?: string | null;
};

export type CreateContestInput = {
  title: string;
  durationMinutes: number;
  taskConfig?: Record<string, unknown>;
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
  skippedCount: number;
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

export type ChessPieceSymbol = "K" | "Q" | "R" | "B" | "N" | "P";
export type ChessBoardPieceSymbol = `w${ChessPieceSymbol}` | `b${ChessPieceSymbol}`;
export type ChessBoardState = (ChessBoardPieceSymbol | null)[][];

export type DiceDefinition = {
  id: string;
  label: string;
  faces: ChessPieceSymbol[];
};

export type DiceChessPositionPublicState = {
  kind: "dice_chess_position_probability";
  prompt: string;
  board: ChessBoardState;
  sideToMove: "white" | "black";
  die: DiceDefinition;
  eventDescription: string;
  responseHint: string;
};

export type DiceChessInventoryPublicState = {
  kind: "dice_chess_board_inventory_probability";
  prompt: string;
  board: ChessBoardState;
  die: DiceDefinition;
  eventDescription: string;
  responseHint: string;
};

export type BoardPoint = {
  row: number;
  col: number;
};

export type ChessCoveragePieceId = "N" | "B" | "R" | "Q";

export type ChessCoveragePieceType = {
  id: ChessCoveragePieceId;
  label: string;
  baseCost: number;
  repeatSurcharge: number;
  limit: number;
  moveLabel: string;
  offsets: BoardPoint[];
};

export type ChessCoveragePlacement = {
  id: string;
  piece: ChessCoveragePieceId;
  row: number;
  col: number;
  cost: number;
};

export type ChessCoveragePublicState = {
  kind: "chess_coverage";
  family: "chess_coverage";
  prompt: string;
  targets: BoardPoint[];
  pieceTypes: ChessCoveragePieceType[];
  placements: ChessCoveragePlacement[];
  pieceCounts: Record<string, number>;
  coveredTargets: BoardPoint[];
  totalCost: number;
  maxPlacements: number;
  allCovered: boolean;
  responseHint: string;
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
  family: "geo_zendo" | "geo_transform" | "geo_probability";
  variant: string;
  prompt: string;
  scene: GeometryScene;
  content: Record<string, unknown>;
  responseHint: string;
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
  responseHint: string;
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
};

export type GridZendoPublicState = {
  kind: "grid_zendo";
  family: "grid_zendo";
  variant: string;
  prompt: string;
  cards: Record<string, string[]>;
  gridSize: number;
  content: Record<string, unknown>;
  responseHint: string;
};

export type PointZendoPublicState = {
  kind: "point_zendo";
  family: "point_zendo";
  variant: string;
  prompt: string;
  scene: GeometryScene;
  content: Record<string, unknown>;
  responseHint: string;
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
  responseHint: string;
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
};

export type TaskPublicState =
  | ChessCoveragePublicState
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
  message?: string;
  clientActionId: string;
};

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

function readNumber(record: UnknownRecord, ...keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return undefined;
}

function readStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function invalidResponse(message: string, details?: unknown): ApiError {
  return new ApiError(502, { code: "invalid_api_response", message, details });
}

function expectRecord(value: unknown, message: string): UnknownRecord {
  if (!isRecord(value)) throw invalidResponse(message, value);
  return value;
}

function requiredString(record: UnknownRecord, label: string, ...keys: string[]): string {
  const value = readString(record, ...keys);
  if (!value) {
    throw invalidResponse(`Сервер вернул некорректное поле «${label}».`, record);
  }
  return value;
}

function unwrapItems(body: unknown, message: string): unknown[] {
  if (Array.isArray(body)) return body;
  if (isRecord(body) && Array.isArray(body.items)) return body.items;
  throw invalidResponse(message, body);
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

function parseTaskStatus(value: unknown): TaskStatus {
  return value === "answered" || value === "skipped" ? value : "active";
}

export function parseContestSummary(value: unknown): ContestSummary {
  const record = expectRecord(value, "Сервер вернул некорректные данные контеста.");

  return {
    id: requiredString(record, "contest.id", "id"),
    title: requiredString(record, "contest.title", "title", "name"),
    status: parseContestStatus(record.status),
    durationMinutes:
      readNumber(record, "durationMinutes", "duration_minutes") ?? 60,
    participantCount: readNumber(record, "participantCount", "participant_count"),
    createdAt: readString(record, "createdAt", "created_at"),
    publishedAt: readNullableString(record, "publishedAt", "published_at"),
  };
}

export function parseParticipant(value: unknown): ParticipantSummary {
  const record = expectRecord(value, "Сервер вернул некорректные данные участника.");

  return {
    id: requiredString(record, "participant.id", "id"),
    displayName: requiredString(
      record,
      "participant.displayName",
      "displayName",
      "display_name",
      "name",
    ),
    externalRef: readNullableString(
      record,
      "externalRef",
      "external_ref",
      "externalId",
      "external_id",
    ),
  };
}

export function parseEnrollment(value: unknown): EnrollmentSummary {
  const record = expectRecord(
    value,
    "Сервер вернул некорректную регистрацию участника.",
  );

  const participant =
    record.participant === undefined ? undefined : parseParticipant(record.participant);
  const participantId =
    readString(record, "participantId", "participant_id") ?? participant?.id;
  if (!participantId) {
    throw invalidResponse("Сервер вернул регистрацию без участника.", record);
  }

  return {
    id: requiredString(record, "enrollment.id", "id"),
    contestId: requiredString(record, "enrollment.contestId", "contestId", "contest_id"),
    participantId,
    participant,
    status: parseEnrollmentStatus(record.status),
    createdAt: readString(record, "createdAt", "created_at"),
  };
}

export function parseAttempt(value: unknown): AttemptSummary {
  const record = expectRecord(value, "Сервер вернул некорректные данные попытки.");

  return {
    id: requiredString(record, "attempt.id", "id"),
    enrollmentId: requiredString(
      record,
      "attempt.enrollmentId",
      "enrollmentId",
      "enrollment_id",
    ),
    number: readNumber(record, "number") ?? 1,
    status: parseAttemptStatus(record.status),
    startedAt: readNullableString(record, "startedAt", "started_at"),
    deadlineAt: readNullableString(record, "deadlineAt", "deadline_at"),
    finishedAt: readNullableString(record, "finishedAt", "finished_at"),
  };
}

function parseAccessCodeOverview(value: unknown): AccessCodeOverview | null {
  if (value === null || value === undefined) return null;
  const record = expectRecord(value, "Сервер вернул некорректные данные кода доступа.");

  return {
    id: requiredString(record, "code.id", "id"),
    last4: requiredString(record, "code.last4", "last4"),
    status: parseAccessCodeStatus(record.status),
    createdAt: readString(record, "createdAt", "created_at"),
    expiresAt: readNullableString(record, "expiresAt", "expires_at"),
    revokedAt: readNullableString(record, "revokedAt", "revoked_at"),
    redeemedAt: readNullableString(record, "redeemedAt", "redeemed_at"),
  };
}

function parseAttemptOverview(value: unknown): AttemptOverview | null {
  if (value === null || value === undefined) return null;
  const record = expectRecord(value, "Сервер вернул некорректные данные попытки.");

  return {
    id: requiredString(record, "attempt.id", "id"),
    number: readNumber(record, "number") ?? 1,
    status: parseAttemptStatus(record.status),
    startedAt: readNullableString(record, "startedAt", "started_at"),
    deadlineAt: readNullableString(record, "deadlineAt", "deadline_at"),
    finishedAt: readNullableString(record, "finishedAt", "finished_at"),
  };
}

function parseContestEnrollmentAccess(
  value: unknown,
  contestId: string,
): ContestEnrollmentAccess {
  const record = expectRecord(
    value,
    "Сервер вернул некорректную строку доступа участника.",
  );
  const participant = parseParticipant(record.participant);

  return {
    id: requiredString(record, "enrollment.id", "id"),
    contestId: readString(record, "contestId", "contest_id") ?? contestId,
    participantId:
      readString(record, "participantId", "participant_id") ?? participant.id,
    participant,
    status: parseEnrollmentStatus(record.status),
    createdAt: readString(record, "createdAt", "created_at"),
    latestCode: parseAccessCodeOverview(record.latestCode ?? record.latest_code),
    latestAttempt: parseAttemptOverview(
      record.latestAttempt ?? record.latest_attempt,
    ),
    attemptGrantPending:
      record.attemptGrantPending === true || record.attempt_grant_pending === true,
  };
}

function parseGeneratedCodes(body: unknown): GenerateCodesResponse {
  const items = unwrapItems(body, "Сервер вернул некорректный список кодов.");
  const counters = isRecord(body) ? body : {};

  return {
    codes: items.map((value) => {
      const item = expectRecord(value, "Сервер вернул некорректный код доступа.");
      const participant = isRecord(item.participant) ? item.participant : {};

      return {
        enrollmentId: requiredString(
          item,
          "enrollmentId",
          "enrollmentId",
          "enrollment_id",
        ),
        participantId: requiredString(participant, "participantId", "id"),
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
        status: parseAccessCodeStatus(item.status),
        expiresAt: readNullableString(item, "expiresAt", "expires_at"),
      };
    }),
    generatedCount:
      readNumber(counters, "generatedCount", "generated_count") ?? items.length,
    skippedCount: readNumber(counters, "skippedCount", "skipped_count") ?? 0,
  };
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

function isChessBoardCell(
  value: unknown,
): value is ChessBoardPieceSymbol | null {
  return (
    value === null ||
    (typeof value === "string" &&
      value.length === 2 &&
      (value[0] === "w" || value[0] === "b") &&
      isChessPieceSymbol(value[1]))
  );
}

function isCoveragePieceId(value: unknown): value is ChessCoveragePieceId {
  return value === "N" || value === "B" || value === "R" || value === "Q";
}

function parseDiceDefinition(value: unknown): DiceDefinition | null {
  if (!isRecord(value)) return null;
  const faces: unknown[] =
    typeof value.faces === "string"
      ? Array.from(value.faces)
      : Array.isArray(value.faces)
        ? value.faces
        : [];
  if (faces.length !== 6 || !faces.every(isChessPieceSymbol)) return null;
  return {
    id: readString(value, "id") ?? "die-1",
    label: readString(value, "label") ?? "Кубик 1",
    faces,
  };
}

function parseChessBoard(value: unknown): ChessBoardState | null {
  if (!Array.isArray(value) || value.length !== 8) return null;
  const board: ChessBoardState = [];
  for (const rank of value) {
    if (
      !Array.isArray(rank) ||
      rank.length !== 8 ||
      !rank.every(isChessBoardCell)
    ) {
      return null;
    }
    board.push([...rank]);
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

function parseBoardPoints(value: unknown): BoardPoint[] | null {
  if (!Array.isArray(value)) return [];
  const points = value.map(parseBoardPoint);
  return points.every((point): point is BoardPoint => point !== null)
    ? points
    : null;
}

function parseLamps(value: unknown): number[] | null {
  return Array.isArray(value) && value.every((item) => item === 0 || item === 1)
    ? (value as number[])
    : null;
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

type PublicStateBase = {
  prompt: string;
  responseHint: string;
};

function readContent(state: UnknownRecord): Record<string, unknown> {
  return isRecord(state.content) ? state.content : {};
}

function parseChessCoverageState(
  state: UnknownRecord,
  base: PublicStateBase,
): ChessCoveragePublicState {
  const boardSize = readNumber(state, "boardSize", "board_size");
  const targets = parseBoardPoints(state.targets);
  const coveredTargets = parseBoardPoints(
    state.coveredTargets ?? state.covered_targets,
  );
  const pieceTypeValues = state.pieceTypes ?? state.piece_types;
  const pieceCountValue = state.pieceCounts ?? state.piece_counts;
  const pieceTypes = Array.isArray(pieceTypeValues)
    ? pieceTypeValues.flatMap((item): ChessCoveragePieceType[] => {
        if (!isRecord(item)) return [];
        const id = readString(item, "id");
        const baseCost = readNumber(item, "baseCost", "base_cost");
        const repeatSurcharge = readNumber(
          item,
          "repeatSurcharge",
          "repeat_surcharge",
        );
        const limit = readNumber(item, "limit");
        const offsets = parseBoardPoints(item.offsets);
        if (
          !isCoveragePieceId(id) ||
          baseCost === undefined ||
          repeatSurcharge === undefined ||
          limit === undefined ||
          !offsets ||
          offsets.length === 0
        ) {
          return [];
        }
        return [{
          id,
          label: readString(item, "label") ?? id,
          baseCost,
          repeatSurcharge,
          limit,
          moveLabel:
            readString(item, "moveLabel", "move_label") ?? "особый прыжок",
          offsets,
        }];
      })
    : [];
  const placements = Array.isArray(state.placements)
    ? state.placements.flatMap((item): ChessCoveragePlacement[] => {
        if (!isRecord(item)) return [];
        const id = readString(item, "id");
        const piece = readString(item, "piece");
        const row = readNumber(item, "row");
        const col = readNumber(item, "col");
        const cost = readNumber(item, "cost");
        if (
          !id ||
          !isCoveragePieceId(piece) ||
          row === undefined ||
          col === undefined ||
          cost === undefined
        ) {
          return [];
        }
        return [{ id, piece, row, col, cost }];
      })
    : [];
  const pieceCounts = isRecord(pieceCountValue)
    ? Object.fromEntries(
        Object.entries(pieceCountValue).flatMap(([key, item]) =>
          typeof item === "number" && Number.isFinite(item)
            ? [[key, item] as const]
            : [],
        ),
      )
    : {};
  if (
    boardSize !== 8 ||
    pieceTypes.length === 0 ||
    !targets ||
    targets.length === 0 ||
    !coveredTargets
  ) {
    throw invalidResponse(
      "Сервер вернул некорректную шахматную расстановку.",
      state,
    );
  }

  return {
    kind: "chess_coverage",
    family: "chess_coverage",
    ...base,
    targets,
    pieceTypes,
    placements,
    pieceCounts,
    coveredTargets,
    totalCost: readNumber(state, "totalCost", "total_cost") ?? 0,
    maxPlacements: readNumber(state, "maxPlacements", "max_placements") ?? 0,
    allCovered: state.allCovered === true || state.all_covered === true,
  };
}

function parseDiceChessState(
  kind:
    | "dice_chess_board_inventory_probability"
    | "dice_chess_position_probability",
  state: UnknownRecord,
  base: PublicStateBase,
): DiceChessInventoryPublicState | DiceChessPositionPublicState {
  const board = parseChessBoard(state.board);
  const die = parseDiceDefinition(state.die);
  const eventDescription = readString(
    state,
    "eventDescription",
    "event_description",
  );
  if (kind === "dice_chess_board_inventory_probability") {
    if (!board || !die || !eventDescription) {
      throw invalidResponse(
        "Сервер вернул некорректную задачу Dice & Chess.",
        state,
      );
    }
    return { kind, ...base, board, die, eventDescription };
  }

  const sideToMove = readString(state, "sideToMove", "side_to_move");
  if (
    !board ||
    !die ||
    !eventDescription ||
    (sideToMove !== "white" && sideToMove !== "black")
  ) {
    throw invalidResponse(
      "Сервер вернул некорректную позицию Dice & Chess.",
      state,
    );
  }
  return { kind, ...base, board, sideToMove, die, eventDescription };
}

function parseGeometryState(
  state: UnknownRecord,
  base: PublicStateBase,
): GeometryPublicState {
  const scene = parseGeometryScene(state.scene);
  const family = readString(state, "family");
  const variant = readString(state, "variant");
  if (
    !scene ||
    !variant ||
    (family !== "geo_zendo" &&
      family !== "geo_transform" &&
      family !== "geo_probability")
  ) {
    throw invalidResponse(
      "Сервер вернул некорректную геометрическую сцену.",
      state,
    );
  }
  return {
    kind: "geometry_atlas",
    family,
    variant,
    ...base,
    scene,
    content: readContent(state),
  };
}

function parseHiddenWiringState(
  state: UnknownRecord,
  base: PublicStateBase,
): HiddenWiringPublicState {
  const variant = readString(state, "variant");
  const lampCount = readNumber(state, "lampCount", "lamp_count");
  const buttonCount = readNumber(state, "buttonCount", "button_count");
  const operations = parseMachineOperations(state.ops);
  const current = parseLamps(state.current);
  if (
    (variant !== "reach_target" && variant !== "predict_chords") ||
    lampCount === undefined ||
    buttonCount === undefined ||
    !operations ||
    !current
  ) {
    throw invalidResponse(
      "Сервер вернул некорректную панель скрытой проводки.",
      state,
    );
  }
  const examChordsValue = state.examChords ?? state.exam_chords;
  const examChords = Array.isArray(examChordsValue)
    ? examChordsValue.flatMap((item) => {
        if (!isRecord(item)) return [];
        const id = readString(item, "id");
        if (!id) return [];
        return [{ id, label: readString(item, "label") ?? id }];
      })
    : undefined;
  const observations = Array.isArray(state.observations)
    ? state.observations.flatMap((item): WiringObservation[] => {
        if (!isRecord(item)) return [];
        const chord = readString(item, "chord");
        const effect = parseLamps(item.effect);
        const lampsAfter = parseLamps(item.lampsAfter ?? item.lamps_after);
        if (!chord || !effect || !lampsAfter) return [];
        return [{
          chord,
          training: item.training === true,
          effect,
          lampsAfter,
        }];
      })
    : [];

  return {
    kind: "hidden_wiring",
    family: "hidden_wiring",
    variant,
    ...base,
    lampCount,
    buttonCount,
    ops: operations,
    current,
    target: parseLamps(state.target) ?? undefined,
    examChords,
    chordBudget: readNumber(state, "chordBudget", "chord_budget") ?? 8,
    chordsRemaining:
      readNumber(state, "chordsRemaining", "chords_remaining") ?? 8,
    observations,
  };
}

function parseFoldPunchState(
  state: UnknownRecord,
  base: PublicStateBase,
): FoldPunchPublicState {
  const sheetSize = readNumber(state, "sheetSize", "sheet_size") ?? 8;
  const folds: FoldStep[] = Array.isArray(state.folds)
    ? state.folds.flatMap((item) => {
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
  const folded = isRecord(state.folded) ? state.folded : {};
  const holes =
    Array.isArray(folded.holes) &&
    folded.holes.every(
      (item) =>
        Array.isArray(item) &&
        item.length === 2 &&
        item.every((part) => typeof part === "number"),
    )
      ? (folded.holes as [number, number][])
      : null;
  const width = readNumber(folded, "width");
  const height = readNumber(folded, "height");
  if (folds.length === 0 || !holes || width === undefined || height === undefined) {
    throw invalidResponse("Сервер вернул некорректную задачу дырокола.", state);
  }

  return {
    kind: "fold_punch",
    family: "fold_punch",
    variant: readString(state, "variant") ?? "unfold_holes",
    ...base,
    sheetSize,
    folds,
    folded: {
      width,
      height,
      triangle: folded.triangle === true,
      holes,
    },
  };
}

function parseGridZendoState(
  state: UnknownRecord,
  base: PublicStateBase,
): GridZendoPublicState {
  const variant = readString(state, "variant");
  const gridSize = readNumber(state, "gridSize", "grid_size") ?? 5;
  const cards: Record<string, string[]> = {};
  if (isRecord(state.cards)) {
    for (const [cardId, rows] of Object.entries(state.cards)) {
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
    throw invalidResponse("Сервер вернул некорректные узоры grid_zendo.", state);
  }

  return {
    kind: "grid_zendo",
    family: "grid_zendo",
    variant,
    ...base,
    cards,
    gridSize,
    content: readContent(state),
  };
}

function parsePointZendoState(
  state: UnknownRecord,
  base: PublicStateBase,
): PointZendoPublicState {
  const scene = parseGeometryScene(state.scene);
  const variant = readString(state, "variant");
  if (!scene || !variant) {
    throw invalidResponse("Сервер вернул некорректную сцену point_zendo.", state);
  }

  return {
    kind: "point_zendo",
    family: "point_zendo",
    variant,
    ...base,
    scene,
    content: readContent(state),
  };
}

function parseTokenZendoState(
  state: UnknownRecord,
  base: PublicStateBase,
): TokenZendoPublicState {
  const variant = readString(state, "variant");
  const cards: Record<string, TokenCard[]> = {};
  if (isRecord(state.cards)) {
    for (const [cardId, tokens] of Object.entries(state.cards)) {
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
    throw invalidResponse(
      "Сервер вернул некорректные карточки token_zendo.",
      state,
    );
  }

  return {
    kind: "token_zendo",
    family: "token_zendo",
    variant,
    ...base,
    cards,
    content: readContent(state),
  };
}

function parseMachinePanelState(
  state: UnknownRecord,
  base: PublicStateBase,
): MachinePanelPublicState {
  const subKindValue = readString(state, "subKind", "sub_kind");
  const subKind =
    subKindValue === "lamps_gf2" ||
    subKindValue === "numeric_machine" ||
    subKindValue === "perm_puzzle"
      ? subKindValue
      : undefined;
  const operations = parseMachineOperations(state.ops);
  const start = subKind ? parseMachineState(state.start, subKind) : null;
  const target = subKind ? parseMachineState(state.target, subKind) : null;
  const current = subKind ? parseMachineState(state.current, subKind) : null;
  if (!subKind || !operations || !start || !target || !current) {
    throw invalidResponse("Сервер вернул некорректное состояние машины.", state);
  }

  return {
    kind: "machine_panel",
    subKind,
    ...base,
    ops: operations,
    start,
    target,
    current,
    stepsSoftCap: readNumber(state, "stepsSoftCap", "steps_soft_cap") ?? 24,
    stepsTaken: readNumber(state, "stepsTaken", "steps_taken") ?? 0,
  };
}

function parseLeaperBoardState(
  state: UnknownRecord,
  base: PublicStateBase,
): LeaperBoardPublicState {
  const rows = readNumber(state, "rows");
  const cols = readNumber(state, "cols");
  const operations = parseMachineOperations(state.ops);
  const start = parseBoardPoint(state.start);
  const target = parseBoardPoint(state.target);
  const current = parseBoardPoint(state.current);
  const blocked = parseBoardPoints(state.blocked);
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
    !blocked
  ) {
    throw invalidResponse("Сервер вернул некорректную доску прыгуна.", state);
  }

  return {
    kind: "chess",
    subKind: "leaper_board",
    ...base,
    ops: operations,
    start,
    target,
    current,
    stepsSoftCap: readNumber(state, "stepsSoftCap", "steps_soft_cap") ?? 24,
    stepsTaken: readNumber(state, "stepsTaken", "steps_taken") ?? 0,
    rows,
    cols,
    blocked,
  };
}

function parseClassicMathState(
  state: UnknownRecord,
  base: PublicStateBase,
): ClassicMathPublicState {
  const family = readString(state, "family");
  const subKind = readString(state, "subKind", "sub_kind");
  const title = readString(state, "title");
  const answerFormat = readString(state, "answerFormat", "answer_format");
  const submissionTemplate = readString(
    state,
    "submissionTemplate",
    "submission_template",
  );
  if (
    family !== "classic_math" ||
    (subKind !== "share_paradox" && subKind !== "bar_seating") ||
    !title ||
    !submissionTemplate ||
    answerFormat !== "free_response"
  ) {
    throw invalidResponse("Сервер вернул некорректную классическую задачу.", state);
  }

  let table: ClassicMathTable | undefined;
  if (isRecord(state.table) && Array.isArray(state.table.columns)) {
    const columns = readStringList(state.table.columns);
    const rows = Array.isArray(state.table.rows)
      ? state.table.rows.flatMap((row): string[][] =>
          Array.isArray(row) &&
          row.length === columns.length &&
          row.every((cell) => typeof cell === "string")
            ? [row as string[]]
            : [],
        )
      : [];
    if (
      columns.length === state.table.columns.length &&
      columns.length > 0 &&
      rows.length > 0
    ) {
      table = { columns, rows };
    }
  }

  return {
    kind: "classic_math_free_response",
    family,
    subKind,
    title,
    ...base,
    submissionTemplate,
    answerFormat,
    scripted: true,
    table,
  };
}

function parsePublicState(state: UnknownRecord): TaskPublicState {
  const kind = readString(state, "kind");
  const base: PublicStateBase = {
    prompt: requiredString(state, "task.prompt", "prompt"),
    responseHint:
      readString(state, "responseHint", "response_hint") ??
      (kind === "machine_panel" || kind === "chess"
        ? "/op op1 · /undo · done / impossible"
        : "/answer ваш ответ"),
  };

  switch (kind) {
    case "chess_coverage":
      return parseChessCoverageState(state, base);
    case "dice_chess_board_inventory_probability":
    case "dice_chess_position_probability":
      return parseDiceChessState(kind, state, base);
    case "geometry_atlas":
      return parseGeometryState(state, base);
    case "hidden_wiring":
      return parseHiddenWiringState(state, base);
    case "fold_punch":
      return parseFoldPunchState(state, base);
    case "grid_zendo":
      return parseGridZendoState(state, base);
    case "point_zendo":
      return parsePointZendoState(state, base);
    case "token_zendo":
      return parseTokenZendoState(state, base);
    case "machine_panel":
      return parseMachinePanelState(state, base);
    case "chess":
      if (readString(state, "subKind", "sub_kind") === "leaper_board") {
        return parseLeaperBoardState(state, base);
      }
      break;
    case "classic_math_free_response":
      return parseClassicMathState(state, base);
  }

  throw new ApiError(502, {
    code: "unsupported_task_kind",
    message: "Этот тип задачи пока не поддерживается интерфейсом.",
    details: state,
  });
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

function decodeFilename(value: string): string | undefined {
  try {
    return decodeURIComponent(value);
  } catch {
    return undefined;
  }
}

function contentDispositionFilename(value: string | null): string | undefined {
  if (!value) return undefined;

  const encodedMatch = value.match(
    /(?:^|;)\s*filename\*\s*=\s*(?:"([^"]+)"|([^;]+))/i,
  );
  if (encodedMatch) {
    const encodedValue = (encodedMatch[1] ?? encodedMatch[2] ?? "").trim();
    const decoded = decodeFilename(
      encodedValue.match(/^[^']*'[^']*'(.*)$/)?.[1] ?? encodedValue,
    );
    if (decoded !== undefined) return decoded;
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

export function saveDownloadedFile(file: DownloadedFile): void {
  const url = URL.createObjectURL(file.blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.filename;
  anchor.hidden = true;
  document.body.append(anchor);

  try {
    anchor.click();
  } finally {
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
  }
}

export class ApiClient {
  readonly baseUrl: string;

  constructor(baseUrl = getDefaultApiBaseUrl()) {
    this.baseUrl = normalizeBaseUrl(baseUrl);
  }

  private async send(path: string, init: RequestInit): Promise<Response> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, init);
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

  private async request(path: string, options: RequestOptions = {}): Promise<unknown> {
    const headers = new Headers({ Accept: "application/json" });
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    if (options.token) headers.set("Authorization", `Bearer ${options.token}`);

    const response = await this.send(path, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
      keepalive: options.keepalive,
    });
    return readResponseBody(response);
  }

  private async requestFile(
    path: string,
    fallbackFilename: string,
    options: AuthenticatedRequestOptions,
  ): Promise<DownloadedFile> {
    const response = await this.send(path, {
      method: "GET",
      headers: new Headers({
        Accept: "text/plain, application/octet-stream",
        Authorization: `Bearer ${options.token}`,
      }),
      signal: options.signal,
    });

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

  async redeemCode(code: string): Promise<RedeemCodeResponse> {
    const body = await this.request("/access/redeem", {
      method: "POST",
      body: { code },
    });
    const response = expectRecord(
      isRecord(body) && isRecord(body.session) ? body.session : body,
      "Сервер вернул некорректную сессию доступа.",
    );

    const role = readString(response, "role");
    if (role !== "organizer" && role !== "participant") {
      throw invalidResponse("Сервер вернул неизвестную роль доступа.", body);
    }

    return {
      accessToken: requiredString(
        response,
        "accessToken",
        "accessToken",
        "access_token",
        "token",
      ),
      role,
      expiresAt: readNullableString(response, "expiresAt", "expires_at"),
    };
  }

  async listContests(options: AuthenticatedRequestOptions): Promise<ContestSummary[]> {
    const body = await this.request("/contests", options);
    return unwrapItems(body, "Сервер вернул некорректный список контестов.").map(
      parseContestSummary,
    );
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
  ): Promise<ContestSummary> {
    const body = await this.request("/contests", {
      ...options,
      method: "POST",
      body: {
        title: input.title,
        duration_minutes: input.durationMinutes,
        environment_key: CONTEST_ENVIRONMENT,
        task_config: input.taskConfig,
      },
    });
    return parseContestSummary(body);
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
    const items = unwrapItems(body, "Сервер вернул некорректный список регистраций.");

    return {
      enrollments: items.map(parseEnrollment),
      createdCount:
        (isRecord(body)
          ? readNumber(body, "createdCount", "created_count")
          : undefined) ?? items.length,
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
    return unwrapItems(body, "Сервер вернул некорректный список доступов.").map(
      (item) => parseContestEnrollmentAccess(item, contestId),
    );
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

  async downloadEnrollmentTelemetrySummary(
    contestId: string,
    enrollmentId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<DownloadedFile> {
    return this.requestFile(
      `/contests/${encodeURIComponent(contestId)}/enrollments/${encodeURIComponent(enrollmentId)}/telemetry/summary`,
      `summary-${enrollmentId}.md`,
      options,
    );
  }

  async rotateEnrollmentCode(
    contestId: string,
    enrollmentId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<RotatedAccessCode> {
    const body = await this.request(
      `/contests/${encodeURIComponent(contestId)}/enrollments/${encodeURIComponent(enrollmentId)}/codes/rotate`,
      {
        ...options,
        method: "POST",
        body: {},
      },
    );
    const value = expectRecord(
      isRecord(body) && isRecord(body.item) ? body.item : body,
      "Сервер вернул некорректный новый код.",
    );

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
    const body = expectRecord(
      await this.request(
        `/contests/${encodeURIComponent(contestId)}/enrollments/${encodeURIComponent(enrollmentId)}/attempts/grant`,
        {
          ...options,
          method: "POST",
        },
      ),
      "Сервер вернул некорректное подтверждение новой попытки.",
    );

    return {
      enrollmentId:
        readString(body, "enrollmentId", "enrollment_id") ?? enrollmentId,
      pending: body.pending === true,
      created: body.created === true,
    };
  }

  async generateCodes(
    contestId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<GenerateCodesResponse> {
    return parseGeneratedCodes(
      await this.request(`/contests/${encodeURIComponent(contestId)}/codes`, {
        ...options,
        method: "POST",
        body: {},
      }),
    );
  }

  async recoverCodes(
    contestId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<GenerateCodesResponse> {
    return parseGeneratedCodes(
      await this.request(
        `/contests/${encodeURIComponent(contestId)}/codes/recover`,
        { ...options, method: "POST" },
      ),
    );
  }

  async publishContest(
    contestId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<ContestSummary> {
    const body = await this.request(
      `/contests/${encodeURIComponent(contestId)}/publish`,
      { ...options, method: "POST" },
    );
    return parseContestSummary(body);
  }

  async getParticipantContext(
    options: AuthenticatedRequestOptions,
  ): Promise<ParticipantContext> {
    const body = expectRecord(
      await this.request("/participant/context", options),
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

  async getTaskProgress(
    options: AuthenticatedRequestOptions,
  ): Promise<TaskProgressEntry[]> {
    const body = await this.request("/participant/tasks/progress", options);
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

  async recordParticipantTelemetry(
    event: ParticipantTelemetryEvent,
    options: AuthenticatedRequestOptions,
  ): Promise<void> {
    await this.request("/participant/telemetry", {
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
    const body = expectRecord(
      await this.request("/participant/tasks/current", options),
      "Сервер вернул некорректный ответ задачи.",
    );

    return {
      task: body.task === null ? null : parseParticipantTask(body.task),
    };
  }

  async getNextTask(
    options: AuthenticatedRequestOptions,
  ): Promise<NextTaskResponse> {
    const body = expectRecord(
      await this.request("/participant/tasks/next", {
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

  async answerTask(
    taskId: string,
    answer: string,
    options: AuthenticatedRequestOptions,
  ): Promise<TaskActionResponse> {
    const body = expectRecord(
      await this.request(
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

  async interactWithTask(
    taskId: string,
    input: TaskInteractionInput,
    options: AuthenticatedRequestOptions,
  ): Promise<TaskInteractionResponse> {
    const body = expectRecord(
      await this.request(
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

  async getParticipantDebugAnswer(
    taskId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<DebugAnswerResponse> {
    const body = expectRecord(
      await this.request(
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

  async sendAiTurn(
    taskId: string,
    input: { clientActionId: string; message: string },
    options: AuthenticatedRequestOptions,
  ): Promise<AiTurn> {
    const body = expectRecord(
      await this.request(
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

  async getAiTurns(
    taskId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<AiTurnHistory> {
    const body = expectRecord(
      await this.request(
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

  async skipTask(
    taskId: string,
    options: AuthenticatedRequestOptions,
  ): Promise<TaskActionResponse> {
    const body = expectRecord(
      await this.request(
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
}

export const api = new ApiClient();
