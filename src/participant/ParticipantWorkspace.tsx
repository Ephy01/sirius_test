import {
  Fragment,
  type ClipboardEvent,
  type FormEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ApiError } from "../api";
import type {
  AiTurn as AiTurnResult,
  AiTurnHistory as AiTurnHistoryResult,
  ChessCoveragePublicState,
  ClassicMathPublicState,
  FoldPunchPublicState,
  HiddenWiringPublicState,
  LeaperBoardPublicState,
  MachinePanelPublicState,
  MachineState,
  TokenCard,
} from "../api";
import "./participant-workspace.css";

export type ChessPieceKind = "K" | "Q" | "R" | "B" | "N";
export type DicePieceKind = ChessPieceKind | "P";
export type DiceFaces = readonly [
  DicePieceKind,
  DicePieceKind,
  DicePieceKind,
  DicePieceKind,
  DicePieceKind,
  DicePieceKind,
];
export type ChessDie = {
  id: string;
  label: string;
  faces: DiceFaces;
};
export type ChessDiceSet =
  | readonly [ChessDie]
  | readonly [ChessDie, ChessDie]
  | readonly [ChessDie, ChessDie, ChessDie]
  | readonly [ChessDie, ChessDie, ChessDie, ChessDie];
export type ChessPieceCode =
  | "wK"
  | "wQ"
  | "wR"
  | "wB"
  | "wN"
  | "wP"
  | "bK"
  | "bQ"
  | "bR"
  | "bB"
  | "bN"
  | "bP";
export type ChessBoardCell = ChessPieceCode | null;
export type ChessBoard = readonly (readonly ChessBoardCell[])[];
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
  points: readonly GeometryPoint[];
  edges: readonly GeometryEdge[];
};

export type ParticipantTask = {
  id: string;
  ordinal: number;
  family: "dice_chess" | (string & {});
  kind:
    | "dice_chess_probability"
    | "dice_chess_board_inventory_probability"
    | "dice_chess_position_probability"
    | (string & {});
  difficulty: number;
  status: "active" | "answered" | "skipped";
  prompt: string;
  board?: ChessBoard;
  dice?: ChessDiceSet;
  sampleSpaceSize?: number;
  eventDescription?: string;
  sideToMove?: "white" | "black";
  geometryScene?: GeometryScene;
  geometryContent?: Record<string, unknown>;
  geometryInteraction?: Record<string, unknown>;
  tokenCards?: Record<string, TokenCard[]>;
  gridCards?: Record<string, string[]>;
  machinePanel?: MachinePanelPublicState;
  wiring?: HiddenWiringPublicState;
  foldPunch?: FoldPunchPublicState;
  leaperBoard?: LeaperBoardPublicState;
  chessCoverage?: ChessCoveragePublicState;
  classicMath?: ClassicMathPublicState;
  responseHint?: string;
  worldPhase?: string;
};

export type TaskProgressEntry = {
  ordinal: number;
  status: "active" | "answered" | "skipped";
};

export type TaskTransitionResult = {
  ordinal: number;
  advanced: boolean;
  message?: string;
};

export type TaskMoveTransitionResult = TaskTransitionResult & {
  accepted: boolean;
  completed: boolean;
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

export type ParticipantWorkspaceProps = {
  task: ParticipantTask;
  attemptId?: string;
  deadlineAt?: string | null;
  contestTitle: string;
  participantName?: string;
  totalTasks?: number;
  taskProgress?: readonly TaskProgressEntry[];
  busy?: boolean;
  error?: string;
  tutorialMode?: boolean;
  onAnswer: (answer: string) => Promise<TaskTransitionResult>;
  onSkip: () => Promise<TaskTransitionResult>;
  onNext: () => Promise<TaskTransitionResult>;
  onProbe?: (
    probe: string,
    clientActionId: string,
  ) => Promise<TaskMoveTransitionResult>;
  onHint?: (clientActionId: string) => Promise<TaskMoveTransitionResult>;
  onGetAnswer?: () => Promise<{
    answer: string;
    commands: string[];
    details: string[];
  }>;
  onApplyOperation?: (
    opId: string,
    clientActionId: string,
  ) => Promise<TaskMoveTransitionResult>;
  onUndo?: (clientActionId: string) => Promise<TaskMoveTransitionResult>;
  onReset?: (clientActionId: string) => Promise<TaskMoveTransitionResult>;
  onAiMessage?: (
    message: string,
    clientActionId: string,
  ) => Promise<AiTurnResult>;
  onLoadAiHistory?: () => Promise<AiTurnHistoryResult>;
  onTelemetry?: (
    event: ParticipantTelemetryEvent,
  ) => Promise<unknown> | unknown;
};

type ConsoleEntry = {
  id: number;
  author: "system" | "participant" | "assistant";
  content: ReactNode;
};

type QueuedTelemetry = {
  event: ParticipantTelemetryEvent;
  retryCount: number;
};

const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"] as const;
const MAX_COMMAND_LENGTH = 4_000;
const MAX_TELEMETRY_TEXT_BYTES = 6_000;
const MAX_TELEMETRY_QUEUE_LENGTH = 5_000;
const MAX_PERSISTED_TELEMETRY_EVENTS = 300;
const TELEMETRY_STORAGE_PREFIX = "sirius-gate:telemetry:";

const PIECE_GLYPHS: Record<ChessPieceCode, string> = {
  wK: "♔",
  wQ: "♕",
  wR: "♖",
  wB: "♗",
  wN: "♘",
  wP: "♙",
  bK: "♚",
  bQ: "♛",
  bR: "♜",
  bB: "♝",
  bN: "♞",
  bP: "♟",
};

const PIECE_NAMES: Record<ChessPieceCode, string> = {
  wK: "белый король",
  wQ: "белый ферзь",
  wR: "белая ладья",
  wB: "белый слон",
  wN: "белый конь",
  wP: "белая пешка",
  bK: "чёрный король",
  bQ: "чёрный ферзь",
  bR: "чёрная ладья",
  bB: "чёрный слон",
  bN: "чёрный конь",
  bP: "чёрная пешка",
};

const DEFAULT_DICE: ChessDiceSet = [
  {
    id: "white",
    label: "Кубик A",
    faces: ["K", "Q", "R", "B", "N", "P"],
  },
  {
    id: "black",
    label: "Кубик B",
    faces: ["K", "Q", "R", "B", "N", "P"],
  },
];

const DICE_GLYPHS: Record<DicePieceKind, string> = {
  K: "♔",
  Q: "♕",
  R: "♖",
  B: "♗",
  N: "♘",
  P: "♙",
};

const BLACK_DICE_GLYPHS: Record<DicePieceKind, string> = {
  K: "♚",
  Q: "♛",
  R: "♜",
  B: "♝",
  N: "♞",
  P: "♟",
};

const DICE_FACE_NAMES: Record<DicePieceKind, string> = {
  K: "король",
  Q: "ферзь",
  R: "ладья",
  B: "слон",
  N: "конь",
  P: "пешка",
};

function normalizeBoard(task: ParticipantTask): ChessBoardCell[][] {
  if (!task.board) {
    return Array.from({ length: 8 }, () => Array<ChessBoardCell>(8).fill(null));
  }

  return task.board.map((rank) => [...rank]);
}

function normalizeDice(task: ParticipantTask): ChessDiceSet {
  if (!task.dice || task.dice.length < 1 || task.dice.length > 4) {
    return DEFAULT_DICE;
  }
  return task.dice;
}

function formatRemainingTime(deadlineAt?: string | null): string {
  if (!deadlineAt) return "--:--";

  const milliseconds = Date.parse(deadlineAt) - Date.now();
  if (!Number.isFinite(milliseconds) || milliseconds <= 0) return "00:00";

  const seconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;

  return hours > 0
    ? [hours, minutes, remainder]
        .map((part) => String(part).padStart(2, "0"))
        .join(":")
    : [minutes, remainder]
        .map((part) => String(part).padStart(2, "0"))
        .join(":");
}

function createClientActionId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `action-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function telemetryText(value: string) {
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

function initialEntries(task: ParticipantTask): ConsoleEntry[] {
  if (task.kind === "chess_coverage") {
    return [
      {
        id: 1,
        author: "system",
        content: (
          <>
            Открыта шахматная расстановка{" "}
            <strong>№{String(task.ordinal).padStart(2, "0")}</strong>.
          </>
        ),
      },
      {
        id: 2,
        author: "system",
        content:
          "Выберите фигуру в палитре и ставьте её на свободные клетки. Покройте все цели с минимальной стоимостью.",
      },
    ];
  }
  if (
    task.kind === "machine_panel" ||
    (task.kind === "chess" && task.family === "machine_reach")
  ) {
    return [
      {
        id: 1,
        author: "system",
        content: (
          <>
            Открыта машина{" "}
            <strong>№{String(task.ordinal).padStart(2, "0")}</strong>.
            Переведите текущее состояние в целевое.
          </>
        ),
      },
      {
        id: 2,
        author: "system",
        content: (
          <>
            Применяйте операции командой <code>/op &lt;id&gt;</code>, отменяйте
            последний шаг через <code>/undo</code>. Итог: <code>done</code>{" "}
            или <code>impossible</code>.
          </>
        ),
      },
    ];
  }
  if (task.kind === "hidden_wiring") {
    return [
      {
        id: 1,
        author: "system",
        content: (
          <>
            Открыта панель{" "}
            <strong>№{String(task.ordinal).padStart(2, "0")}</strong>.
            Проводка скрыта. Кнопки срабатывают только парами.
          </>
        ),
      },
      {
        id: 2,
        author: "system",
        content: (
          <>
            Нажимайте комбинации из двух кнопок командой{" "}
            <code>/op b1+b2</code> или кнопками на панели. Первая проба
            обучающая и не тратит лимит.
          </>
        ),
      },
    ];
  }
  if (
    task.kind === "geometry_atlas" ||
    task.kind === "token_zendo" ||
    task.kind === "point_zendo" ||
    task.kind === "grid_zendo"
  ) {
    return [
      {
        id: 1,
        author: "system",
        content: (
          <>
            Открыта задача{" "}
            <strong>№{String(task.ordinal).padStart(2, "0")}</strong>
            {task.kind === "geometry_atlas" ? " Геометрического мира" : ""}.
          </>
        ),
      },
      {
        id: 2,
        author: "system",
        content:
          task.kind === "grid_zendo" ? (
            <>
              Нарисуйте узор на пустой сетке и проверьте его кнопкой или
              командой <code>/test</code>, затем отправьте итоговый ответ.
            </>
          ) : task.family === "geo_zendo" ||
          task.kind === "token_zendo" ||
          task.kind === "point_zendo" ? (
            <>
              Можно проверить доступную карточку командой{" "}
              <code>/test &lt;код&gt;</code>, затем отправить итоговый ответ.
            </>
          ) : (
            <>
              Введите <code>/help</code>, чтобы увидеть доступные команды.
            </>
          ),
      },
    ];
  }

  return [
    {
      id: 1,
      author: "system",
      content: (
        <>
          Открыта задача{" "}
          <strong>№{String(task.ordinal).padStart(2, "0")}</strong>.
        </>
      ),
    },
    {
      id: 2,
      author: "system",
      content: (
        <>
          Введите <code>/help</code>, чтобы увидеть доступные команды.
        </>
      ),
    },
  ];
}

export function ParticipantWorkspace({
  task,
  attemptId,
  deadlineAt,
  taskProgress,
  busy = false,
  error = "",
  tutorialMode = false,
  onAnswer,
  onSkip,
  onNext,
  onProbe,
  onHint,
  onGetAnswer,
  onApplyOperation,
  onUndo,
  onReset,
  onAiMessage,
  onLoadAiHistory,
  onTelemetry,
}: ParticipantWorkspaceProps) {
  const board = useMemo(() => normalizeBoard(task), [task]);
  const dice = useMemo(() => normalizeDice(task), [task]);
  const [draft, setDraft] = useState("");
  const [entries, setEntries] = useState<ConsoleEntry[]>(() =>
    initialEntries(task),
  );
  const [commandBusy, setCommandBusy] = useState(false);
  const [aiThinking, setAiThinking] = useState(false);
  const aiHistoryTasks = useRef(new Set<string>());
  const [aiRemaining, setAiRemaining] = useState<{
    task: number;
    attempt: number;
  } | null>(null);
  const [remainingTime, setRemainingTime] = useState(() =>
    formatRemainingTime(deadlineAt),
  );
  const entryId = useRef(3);
  const activeTaskId = useRef(task.id);
  const inFlight = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const consoleLogRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const telemetryHandlerRef = useRef(onTelemetry);
  const telemetrySessionId = useRef(createClientActionId());
  const telemetryStartedAt = useRef(Date.now());
  const telemetrySequence = useRef(0);
  const telemetryViewedTasks = useRef(new Set<string>());
  const telemetryQueue = useRef<QueuedTelemetry[]>(
    loadTelemetryQueue(attemptId),
  );
  const telemetryDrainActive = useRef(false);
  const telemetryRetryTimer = useRef<number | null>(null);

  const timeIsUp = Boolean(deadlineAt) && remainingTime === "00:00";
  const isBusy = busy || commandBusy || timeIsUp;
  const isDiceChess = task.family === "dice_chess";
  const isDicePosition =
    task.kind === "dice_chess_position_probability" ||
    task.kind === "dice_chess_board_inventory_probability";
  const isGeometry = task.kind === "geometry_atlas";
  const isZendo =
    (isGeometry && task.family === "geo_zendo") ||
    task.kind === "token_zendo" ||
    task.kind === "point_zendo" ||
    task.kind === "grid_zendo";
  const isMachine =
    task.kind === "machine_panel" ||
    (task.kind === "chess" && task.family === "machine_reach");
  const isWiring = task.kind === "hidden_wiring";
  const isChessCoverage =
    task.kind === "chess_coverage" && Boolean(task.chessCoverage);
  const isLeaperBoard = task.kind === "chess" && Boolean(task.leaperBoard);
  const isClassicMath =
    task.kind === "classic_math_free_response" &&
    task.family === "classic_math";
  const rawStatementPrompt = isDiceChess
    ? task.prompt.replace(
        /\s*Найдите вероятность описанного события\.\s*$/u,
        "",
      )
    : task.prompt;
  const statementPrompt = task.family === "geo_zendo"
    ? rawStatementPrompt
        .replaceAll("Конструкции", "Графы")
        .replaceAll("конструкции", "графы")
        .replaceAll("конструкций", "графов")
    : rawStatementPrompt;
  const statementQuestion =
    isDiceChess && task.eventDescription
      ? `Найдите вероятность того, что ${task.eventDescription
          .charAt(0)
          .toLocaleLowerCase("ru-RU")}${task.eventDescription.slice(1)}`
      : task.eventDescription;
  const statementParagraphs = statementPrompt
    .split(/\n{2,}/u)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  const zendoContent = task.geometryContent ?? {};
  const zendoProbesRemaining =
    typeof zendoContent.probes_remaining === "number"
      ? (zendoContent.probes_remaining as number)
      : undefined;
  const zendoTargetCount = Array.isArray(zendoContent.targets)
    ? zendoContent.targets.length
    : 0;
  const zendoAnswerExample = `/answer ${Array.from(
    { length: Math.max(1, zendoTargetCount) },
    (_, index) => (index % 2 === 0 ? "1" : "0"),
  ).join(" ")}`;
  const transformOptions = Array.isArray(zendoContent.answer_cards)
    ? (zendoContent.answer_cards as unknown[]).flatMap((option) =>
        typeof option === "object" && option !== null && "id" in option
          ? [
              {
                id: String((option as { id: unknown }).id),
                label:
                  "label" in option
                    ? String((option as { label?: unknown }).label)
                    : String((option as { id: unknown }).id),
              },
            ]
          : [],
      )
    : [];
  const briefMetaLines: string[] = [];
  if (isZendo && zendoProbesRemaining !== undefined) {
    briefMetaLines.push(`Осталось проб: ${zendoProbesRemaining}`);
  }
  if (task.wiring) {
    briefMetaLines.push(
      `Доступно проб: ${task.wiring.chordsRemaining} / ${task.wiring.chordBudget}`,
    );
    if (task.wiring.examChords && task.wiring.examChords.length > 0) {
      briefMetaLines.push(
        "экзаменационные комбинации (недоступны для проб): " +
          task.wiring.examChords.map((chord) => chord.id).join(", "),
      );
    }
  }
  if (task.machinePanel) {
    briefMetaLines.push(
      `Шагов: ${task.machinePanel.stepsTaken} / ${task.machinePanel.stepsSoftCap}`,
    );
  }
  if (task.leaperBoard) {
    briefMetaLines.push(
      `Фигура: (${task.leaperBoard.current.row + 1}, ${
        task.leaperBoard.current.col + 1
      })`,
      `Цель: (${task.leaperBoard.target.row + 1}, ${
        task.leaperBoard.target.col + 1
      })`,
      `Шагов: ${task.leaperBoard.stepsTaken} / ${task.leaperBoard.stepsSoftCap}`,
    );
  }
  if (task.chessCoverage) {
    const customPlacement =
      task.chessCoverage.variant === "custom_jump_placement";
    briefMetaLines.push(
      `Выбрано фигур: ${
        customPlacement
          ? task.chessCoverage.placements.length
          : task.chessCoverage.selectedIds.length
      }`,
      `Текущая стоимость: ${
        customPlacement
          ? task.chessCoverage.totalCost
          : task.chessCoverage.totalWeight
      }`,
    );
  }
  if (task.foldPunch) {
    briefMetaLines.push(
      "сгибы выполняются по порядку; дырки пробиты через все слои сразу",
    );
  }
  if (task.gridCards) {
    briefMetaLines.push("узор проверяется целиком");
  }
  if (task.tokenCards) {
    briefMetaLines.push("цвет и число каждой фишки видны на полке");
  }
  if (isGeometry || task.kind === "point_zendo") {
    briefMetaLines.push("все рисунки даны в одной системе обозначений");
  }

  useEffect(() => {
    const updateTimer = () => setRemainingTime(formatRemainingTime(deadlineAt));
    updateTimer();
    const interval = window.setInterval(updateTimer, 1000);
    return () => window.clearInterval(interval);
  }, [deadlineAt]);

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

  useEffect(() => {
    if (activeTaskId.current === task.id) return;
    activeTaskId.current = task.id;
    setDraft("");
    stageRef.current?.scrollTo({ top: 0 });
  }, [task.id]);

  useEffect(() => {
    if (!onLoadAiHistory) return;
    if (aiHistoryTasks.current.has(task.id)) return;
    aiHistoryTasks.current.add(task.id);
    void (async () => {
      try {
        const history = await onLoadAiHistory();
        setAiRemaining(history.remaining);
        setEntries((current) => {
          const restored: ConsoleEntry[] = [];
          for (const turn of history.turns) {
            restored.push({
              id: entryId.current++,
              author: "participant",
              content: turn.userMessage,
            });
            if (turn.assistantMessage) {
              restored.push({
                id: entryId.current++,
                author: "assistant",
                content: turn.assistantMessage,
              });
            }
          }
          return restored.length ? [...current, ...restored] : current;
        });
      } catch {
      }
    })();
  }, [task.id, onLoadAiHistory]);

  useEffect(() => {
    if (telemetryViewedTasks.current.has(task.id)) return;
    telemetryViewedTasks.current.add(task.id);
    emitTelemetry(
      "client_task_viewed",
      {
        ordinal: task.ordinal,
        family: task.family,
        difficulty: task.difficulty,
        task_status: task.status,
        document_visible: document.visibilityState === "visible",
        window_focused: document.hasFocus(),
      },
      task.id,
    );
  }, [task.id]);

  useEffect(() => {
    const handleFocus = () =>
      emitTelemetry("client_focus", {
        document_visible: document.visibilityState === "visible",
      });
    const handleBlur = () =>
      emitTelemetry("client_blur", {
        document_visible: document.visibilityState === "visible",
      });
    const handleVisibility = () =>
      emitTelemetry(
        document.visibilityState === "visible"
          ? "client_visibility_visible"
          : "client_visibility_hidden",
        { window_focused: document.hasFocus() },
      );

    window.addEventListener("focus", handleFocus);
    window.addEventListener("blur", handleBlur);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("blur", handleBlur);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);

  useEffect(() => {
    const log = consoleLogRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [entries, error]);

  function appendEntry(author: ConsoleEntry["author"], content: ReactNode) {
    setEntries((current) => [
      ...current,
      { id: entryId.current++, author, content },
    ]);
  }

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

  async function submitZendoProbe(probe: string) {
    if (!onProbe) {
      appendEntry("system", "Проверка сейчас недоступна.");
      return;
    }
    const transition = await onProbe(probe, createClientActionId());
    appendEntry(
      "system",
      transition.message ??
        (transition.accepted
          ? "Проверка выполнена."
          : "Эту конфигурацию нельзя проверить."),
    );
  }

  async function submitMachineOperation(opId: string) {
    if (!onApplyOperation) {
      appendEntry("system", "Пульт машины сейчас недоступен.");
      return;
    }
    const transition = await onApplyOperation(
      opId,
      createClientActionId(),
    );
    appendEntry(
      "system",
      transition.advanced ? (
        <>
          {transition.message ?? "Задача завершена."} Открыта задача{" "}
          <strong>
            №{String(transition.ordinal).padStart(2, "0")}
          </strong>
          .
        </>
      ) : (
        transition.message ??
          (transition.accepted
            ? `Операция ${opId} применена.`
            : `Операцию ${opId} применить нельзя.`)
      ),
    );
  }

  async function submitMachineUndo() {
    if (!onUndo) {
      appendEntry("system", "Отмена сейчас недоступна.");
      return;
    }
    const transition = await onUndo(createClientActionId());
    appendEntry(
      "system",
      transition.message ??
        (transition.accepted
          ? "Последняя операция отменена."
          : "Отменять пока нечего."),
    );
  }

  async function submitReset() {
    if (!onReset) {
      appendEntry("system", "Возврат в начало сейчас недоступен.");
      return;
    }
    const transition = await onReset(createClientActionId());
    appendEntry(
      "system",
      transition.message ??
        (transition.accepted
          ? "Состояние возвращено в начало."
          : "Состояние уже начальное."),
    );
  }

  async function submitFinalAnswer(answer: string) {
    const transition = await onAnswer(answer);
    appendEntry(
      "system",
      transition.message ??
        (transition.advanced ? (
          <>
            Ответ зафиксирован. Открыта задача{" "}
            <strong>
              №{String(transition.ordinal).padStart(2, "0")}
            </strong>
            .
          </>
        ) : (
          "Ответ зафиксирован. Для продолжения используйте /next."
        )),
    );
  }

  async function runCommand(rawInput: string) {
    const input = rawInput.trim();
    if (!input || isBusy || inFlight.current) return;
    const [command = "", ...parts] = input.split(/\s+/);
    const payload = input.slice(command.length).trim();

    inFlight.current = true;
    setDraft("");
    appendEntry("participant", input);
    setCommandBusy(true);
    const telemetryInput = telemetryText(input);
    emitTelemetry("client_command_submitted", {
      input: telemetryInput.text,
      command: command.toLocaleLowerCase("ru-RU"),
      input_length: input.length,
      input_byte_length: telemetryInput.originalByteLength,
      input_json_byte_length: telemetryInput.originalJsonByteLength,
      input_truncated: telemetryInput.truncated,
      task_status: task.status,
    });

    try {
      switch (command.toLowerCase()) {
        case "/help":
          appendEntry(
            "system",
            isWiring ? (
              <>
                <code>/op b1+b2</code> — нажать комбинацию из двух кнопок
                <br />
                Кнопки срабатывают только парами; первая проба обучающая
                и не тратит лимит.
                <br />
                <code>/hint</code> — платная подсказка: итоговый балл умножается на 0.7
                <br />
                <code>/skip</code> — пропустить задачу
              </>
            ) : isChessCoverage ? (
              <>
                Выберите фигуру в палитре и нажмите на клетку доски.
                <br />
                <code>/reset</code> — очистить расстановку
                <br />
                <code>done</code> — зафиксировать выбранную расстановку
              </>
            ) : isMachine ? (
              <>
                <code>/op &lt;id&gt;</code> — применить указанную операцию
                <br />
                <code>/undo</code> — отменить последнюю операцию
                <br />
                <code>/reset</code> — вернуть машину в начало
                <br />
                <code>done</code> — зафиксировать достигнутую цель
                <br />
                <code>impossible</code> — заявить, что цель недостижима
              </>
            ) : isZendo ? (
              <>
                <code>/test &lt;код&gt;</code> — проверить одну из карточек-проб
                <br />
                <code>/answer &lt;ответ&gt;</code> — классифицировать целевые
                конфигурации
                <br />
                <code>/hint</code> — платная подсказка о типе правила: итоговый балл умножается на 0.7
                <br />
                <code>/skip</code> — пропустить и открыть следующую задачу
              </>
            ) : (
              <>
                <code>/answer &lt;текст&gt;</code> — зафиксировать ответ
                и открыть следующую задачу
                <br />
                <code>/skip</code> — пропустить и открыть следующую задачу
                <br />
                <code>/next</code> — повторить переход, если он прервался
              </>
            ),
          );
          break;

        case "/probe":
        case "/test":
          if (!isZendo) {
            appendEntry(
              "system",
              "Команда /test доступна только в задачах со скрытым утверждением.",
            );
            break;
          }
          if (task.status !== "active") {
            appendEntry(
              "system",
              "Текущая задача уже закрыта. Используйте /next.",
            );
            break;
          }
          if (!payload) {
            appendEntry(
              "system",
              <>
                Укажите код карточки. Например: <code>/test P1</code>.
              </>,
            );
            break;
          }
          await submitZendoProbe(payload);
          break;

        case "/get":
          if (payload.toLowerCase() !== "answer") {
            appendEntry(
              "system",
              <>
                Неизвестная команда. Возможно, вы имели в виду{" "}
                <code>/get answer</code>.
              </>,
            );
            break;
          }
          if (task.status !== "active") {
            appendEntry(
              "system",
              "Текущая задача уже закрыта. Используйте /next.",
            );
            break;
          }
          if (!onGetAnswer) {
            appendEntry("system", "Эталонный ответ сейчас недоступен.");
            break;
          }
          try {
            const revealed = await onGetAnswer();
            appendEntry(
              "system",
              <>
                Эталонный ответ (режим отладки):{" "}
                <code>{revealed.answer}</code>
                {revealed.commands.length > 0 && (
                  <>
                    <br />
                    Команды:{" "}
                    {revealed.commands.map((command, index) => (
                      <span key={index}>
                        <code>{command}</code>
                        {index < revealed.commands.length - 1 && " · "}
                      </span>
                    ))}
                  </>
                )}
                {revealed.details.map((line, index) => (
                  <span key={`detail-${index}`}>
                    <br />
                    {line}
                  </span>
                ))}
              </>,
            );
          } catch (caught) {
            appendEntry(
              "system",
              caught instanceof Error
                ? caught.message
                : "Не удалось получить эталонный ответ.",
            );
          }
          break;

        case "/hint":
          if (!isZendo && !isWiring) {
            appendEntry(
              "system",
              "Подсказка доступна только в задачах со скрытым правилом.",
            );
            break;
          }
          if (task.status !== "active") {
            appendEntry(
              "system",
              "Текущая задача уже закрыта. Используйте /next.",
            );
            break;
          }
          if (!onHint) {
            appendEntry("system", "Подсказка сейчас недоступна.");
            break;
          }
          {
            const transition = await onHint(createClientActionId());
            appendEntry(
              "system",
              transition.message ??
                (transition.accepted
                  ? "Подсказка получена."
                  : "Подсказка недоступна."),
            );
          }
          break;

        case "/op":
          if (!isMachine && !isWiring && !isChessCoverage) {
            appendEntry(
              "system",
              "Команда /op доступна только в задачах с машиной или панелью.",
            );
            break;
          }
          if (task.status !== "active") {
            appendEntry(
              "system",
              "Текущая машина уже закрыта. Используйте /next.",
            );
            break;
          }
          if (!payload || parts.length !== 1) {
            appendEntry(
              "system",
              <>
                Укажите один идентификатор. Например: <code>/op op1</code>.
              </>,
            );
            break;
          }
          await submitMachineOperation(payload);
          break;

        case "/reset":
          if (!isMachine && !isChessCoverage) {
            appendEntry(
              "system",
              "Команда /reset доступна только в задачах с изменяемым состоянием.",
            );
            break;
          }
          if (task.status !== "active") {
            appendEntry(
              "system",
              "Текущая задача уже закрыта. Используйте /next.",
            );
            break;
          }
          if (parts.length > 0) {
            appendEntry(
              "system",
              "Команда /reset не принимает дополнительных данных.",
            );
            break;
          }
          await submitReset();
          break;

        case "/undo":
          if (!isMachine) {
            appendEntry(
              "system",
              "Команда /undo доступна только в задачах с машиной.",
            );
            break;
          }
          if (task.status !== "active") {
            appendEntry(
              "system",
              "Текущая машина уже закрыта. Используйте /next.",
            );
            break;
          }
          if (parts.length > 0) {
            appendEntry(
              "system",
              "Команда /undo не принимает дополнительных данных.",
            );
            break;
          }
          await submitMachineUndo();
          break;

        case "/answer":
          if (task.status !== "active") {
            appendEntry(
              "system",
              "Текущая задача уже закрыта. Используйте /next.",
            );
            break;
          }
          if (!payload) {
            appendEntry(
              "system",
              <>
                После команды нужен текст ответа. Например:{" "}
                <code>
                  {isMachine || isChessCoverage
                    ? "/answer done"
                    : isDiceChess
                      ? "/answer 5/12"
                      : isClassicMath
                        ? "/answer <развёрнутое решение>"
                        : "/answer да, допустима"}
                </code>
                .
              </>,
            );
            break;
          }
          await submitFinalAnswer(payload);
          break;

        case "/skip":
          if (task.status !== "active") {
            appendEntry(
              "system",
              "Текущая задача уже закрыта. Используйте /next.",
            );
            break;
          }
          if (parts.length > 0) {
            appendEntry("system", "Команда /skip не принимает дополнительных данных.");
            break;
          }
          {
            const transition = await onSkip();
            appendEntry(
              "system",
              transition.message ??
                (transition.advanced ? (
                  <>
                    Пропуск зафиксирован. Открыта задача{" "}
                    <strong>
                      №{String(transition.ordinal).padStart(2, "0")}
                    </strong>
                    .
                  </>
                ) : (
                  "Пропуск зафиксирован. Для продолжения используйте /next."
                )),
            );
          }
          break;

        case "/next":
          if (parts.length > 0) {
            appendEntry("system", "Команда /next не принимает дополнительных данных.");
            break;
          }
          if (task.status === "active") {
            appendEntry(
              "system",
              "Сначала отправьте ответ или пропустите задачу командой /skip.",
            );
            break;
          }
          {
            const transition = await onNext();
            appendEntry(
              "system",
              transition.message ?? (
                <>
                  Открыта задача{" "}
                  <strong>
                    №{String(transition.ordinal).padStart(2, "0")}
                  </strong>
                  .
                </>
              ),
            );
          }
          break;

        default:
          if (command.startsWith("/")) {
            appendEntry(
              "system",
              <>
                Такой команды нет. Введите <code>/help</code> для справки.
              </>,
            );
            break;
          }

          if (
            (isMachine || isChessCoverage) &&
            /^(?:done|impossible|готово?|невозможно|недостижимо)$/iu.test(input)
          ) {
            if (task.status !== "active") {
              appendEntry(
                "system",
                "Текущая машина уже закрыта. Используйте /next.",
              );
              break;
            }
            await submitFinalAnswer(input);
            break;
          }

          if (onAiMessage) {
            if (task.status !== "active") {
              appendEntry(
                "system",
                "Эта задача уже закрыта — ассистент доступен только в активной задаче.",
              );
              break;
            }
            setAiThinking(true);
            try {
              const turn = await onAiMessage(input, createClientActionId());
              setAiRemaining(turn.remaining);
              if (turn.assistantMessage) {
                appendEntry("assistant", turn.assistantMessage);
              } else {
                appendEntry(
                  "system",
                  "Ассистент не вернул ответ. Попробуйте ещё раз.",
                );
              }
              if (turn.remaining.task === 0 || turn.remaining.attempt === 0) {
                appendEntry(
                  "system",
                  "Лимит обращений к ассистенту исчерпан.",
                );
              }
            } catch (error) {
              appendEntry(
                "system",
                error instanceof ApiError
                  ? error.message
                  : "Не удалось связаться с ассистентом.",
              );
            } finally {
              setAiThinking(false);
            }
          } else {
            appendEntry(
              "system",
              <>
                Чтобы сохранить решение, начните сообщение с{" "}
                <code>/answer</code>.
              </>,
            );
          }
      }
    } catch {
    } finally {
      inFlight.current = false;
      setCommandBusy(false);
      window.requestAnimationFrame(() => inputRef.current?.focus());
    }
  }

  function submitCommand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runCommand(draft);
  }

  return (
    <main
      className="participant-workspace"
      data-task-family={task.family}
      data-task-kind={task.kind}
      data-task-difficulty={task.difficulty}
      onCopy={(event: ClipboardEvent<HTMLElement>) => {
        const target = event.target;
        let characterCount = 0;
        if (
          target instanceof HTMLInputElement &&
          target.selectionStart !== null &&
          target.selectionEnd !== null
        ) {
          characterCount = Array.from(
            target.value.slice(target.selectionStart, target.selectionEnd),
          ).length;
        } else {
          characterCount = Array.from(
            window.getSelection()?.toString() ?? "",
          ).length;
        }
        emitTelemetry("client_copy", {
          surface:
            target instanceof Element &&
            target.closest(".participant-console")
              ? "chat"
              : "task",
          character_count: characterCount,
        });
      }}
    >
      <section className="participant-task" aria-label={`Задача ${task.ordinal}`}>
        <header className="participant-task__header">
          <p>Задача {task.ordinal}</p>
          {taskProgress && taskProgress.length > 0 && (
            <ol className="task-progress" aria-label="Статусы задач попытки">
              {taskProgress.length > 15 && (
                <li className="task-progress__more" aria-hidden="true">
                  …
                </li>
              )}
              {taskProgress.slice(-15).map((item) => (
                <li
                  className={`task-progress__dot task-progress__dot--${item.status}`}
                  aria-label={`Задача ${item.ordinal}: ${
                    item.status === "answered"
                      ? "дан ответ"
                      : item.status === "skipped"
                        ? "пропущена"
                        : "текущая"
                  }`}
                  key={item.ordinal}
                >
                  {item.ordinal}
                </li>
              ))}
            </ol>
          )}
        </header>

        <div
          className={`participant-task__stage${
            isClassicMath ? " participant-task__stage--text-only" : ""
          }`}
          ref={stageRef}
          data-tour="task-stage"
        >
          <article
            className={`participant-brief${
              isClassicMath ? " participant-brief--classic" : ""
            }`}
            data-tour="task-statement"
          >
            <div className="participant-brief__statement">
              {isClassicMath && task.classicMath?.title && (
                <h2>{task.classicMath.title}</h2>
              )}
              {statementParagraphs.map((paragraph, index) => (
                <p key={`${task.id}-paragraph-${index}`}>{paragraph}</p>
              ))}
              {statementQuestion && <p>{statementQuestion}</p>}
              {isClassicMath && task.classicMath?.table && (
                <div className="classic-math-table-wrap">
                  <table className="classic-math-table">
                    <thead>
                      <tr>
                        {task.classicMath.table.columns.map((column) => (
                          <th key={column} scope="col">
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {task.classicMath.table.rows.map((row, rowIndex) => (
                        <tr key={`${task.id}-table-row-${rowIndex}`}>
                          {row.map((cell, cellIndex) => (
                            <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div className="participant-brief__answer">
              {!(isWiring && task.wiring?.variant === "reach_target") && (
              <p>
                {isWiring ? (
                  <>
                    Ответ отправьте в чате (пример:{" "}
                    <code>/answer 1101 0000 1000</code> — три битовые
                    строки по лампам экзаменационных комбинаций, 1 —
                    лампа переключится).
                  </>
                ) : isChessCoverage ? (
                  <>
                    Выберите тип фигуры в палитре, расставьте фигуры на доске
                    и зафиксируйте решение кнопкой под доской или командой{" "}
                    <code>/answer done</code>.
                  </>
                ) : isMachine ? (
                  <>
                    Ответ отправьте в чате: <code>done</code> — когда решение
                    найдено, <code>impossible</code> — если цель недостижима.
                  </>
                ) : isZendo ? (
                  <>
                    Ответ отправьте в чате (пример:{" "}
                    <code>{zendoAnswerExample}</code> — по одному значению для
                    каждой из {zendoTargetCount || "показанных"} целей в их
                    порядке, 1 — подходит, 0 — нет).
                  </>
                ) : task.foldPunch ? (
                  <>
                    Кликните клетки на развёрнутом листе и нажмите «Отправить
                    отмеченные клетки», или отправьте ответ в чате (пример:{" "}
                    <code>/answer 2,3 5,8</code> — строка,столбец).
                  </>
                ) : isClassicMath && task.classicMath ? (
                  <>
                    Ответ отправьте в чате одной командой по шаблону:
                    <code className="classic-math-submission-template">
                      {task.classicMath.submissionTemplate.replace(
                        /\s*\n+\s*/gu,
                        " ",
                      )}
                    </code>
                  </>
                ) : (
                  <>
                    Ответ отправьте в чате командой{" "}
                    <code>/answer &lt;ваш ответ&gt;</code>.
                  </>
                )}
              </p>
              )}
              {(isMachine || isZendo || isChessCoverage) && (
                <p>
                  {isChessCoverage ? (
                    <>
                      Нажатие на установленную фигуру убирает её ·{" "}
                      <code>/reset</code> — очистить доску.
                    </>
                  ) : isMachine ? (
                    <>
                      <code>/op &lt;id&gt;</code> — применить операцию ·{" "}
                      <code>/undo</code> — отменить последний шаг.
                    </>
                  ) : task.gridCards ? (
                    <>
                      Пробы рисуются: закрасьте клетки в блоке «Свой узор» и
                      нажмите «Проверить узор», или отправьте{" "}
                      <code>/test &lt;25 нулей и единиц&gt;</code>.{" "}
                      <code>/hint</code> — платная подсказка: итоговый балл умножается на 0.7.
                    </>
                  ) : (
                    <>
                      <code>/test &lt;код&gt;</code> — проверить одну из
                      карточек-проб · <code>/hint</code> — платная подсказка:
                      итоговый балл умножается на 0.7.
                    </>
                  )}
                </p>
              )}
              {transformOptions.length > 0 && (
                <div
                  className="transform-options"
                  role="group"
                  aria-label="Варианты преобразования"
                >
                  {transformOptions.map((option) => (
                    <button
                      type="button"
                      disabled={task.status !== "active" || isBusy}
                      onClick={() => void runCommand(`/answer ${option.id}`)}
                      key={option.id}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              )}
              {briefMetaLines.length > 0 && (
                <p className="participant-brief__meta">
                  <DotSeparated items={briefMetaLines} />
                </p>
              )}
            </div>
          </article>

          <Fragment key={task.id}>
            {task.foldPunch ? (
              <FoldPunchScene
                state={task.foldPunch}
                canAnswer={task.status === "active" && !isBusy}
                onSubmit={(cells) => void runCommand(`/answer ${cells}`)}
              />
            ) : task.wiring ? (
              <WiringPanelScene
                state={task.wiring}
                canAct={task.status === "active" && !isBusy}
                onChord={(opId) => void runCommand(`/op ${opId}`)}
              />
            ) : task.machinePanel ? (
              <MachinePanel
                state={task.machinePanel}
                canAct={task.status === "active" && !isBusy}
                onOp={(opId) => void runCommand(`/op ${opId}`)}
                onReset={() => void runCommand("/reset")}
              />
            ) : task.chessCoverage ? (
              <ChessCoverageScene
                state={task.chessCoverage}
                canAct={task.status === "active" && !isBusy}
                onToggle={(candidateId) =>
                  void runCommand(`/op ${candidateId}`)
                }
                onReset={() => void runCommand("/reset")}
                onSubmit={() => void runCommand("/answer done")}
              />
            ) : isLeaperBoard && task.leaperBoard ? (
              <LeaperBoardScene
                state={task.leaperBoard}
                canAct={task.status === "active" && !isBusy}
                onOp={(opId) => void runCommand(`/op ${opId}`)}
              />
            ) : task.tokenCards ? (
              <TokenShelfScene
                cards={task.tokenCards}
                content={task.geometryContent ?? {}}
                canProbe={task.status === "active" && !isBusy}
                onProbe={(cardId) => void runCommand(`/test ${cardId}`)}
              />
            ) : task.gridCards ? (
              <GridZendoScene
                cards={task.gridCards}
                content={task.geometryContent ?? {}}
                canProbe={task.status === "active" && !isBusy}
                onProbe={(pattern) => void runCommand(`/test ${pattern}`)}
              />
            ) : task.geometryScene ? (
              <GeometryAtlasScene
                scene={task.geometryScene}
                content={task.geometryContent ?? {}}
                showGrid={task.kind === "point_zendo"}
                canProbe={isZendo && task.status === "active" && !isBusy}
                onProbe={(cardId) => void runCommand(`/test ${cardId}`)}
              />
            ) : isDicePosition ? (
              <DicePositionScene
                board={board}
                die={dice[0]}
                sideToMove={task.sideToMove}
              />
            ) : isDiceChess ? (
              <DiceScene dice={dice} />
            ) : isClassicMath ? null : (
              <Chessboard board={board} />
            )}
          </Fragment>
        </div>
      </section>

      <aside className="participant-console" aria-label="Чат и команды">
        <header className="participant-console__header" style={{ justifyContent: "flex-end", gap: "8px" }}>
          {tutorialMode ? (
            <strong>Демонстрационный режим</strong>
          ) : (
            <>
              <strong>До завершения:</strong>
              <time dateTime={deadlineAt ?? undefined}>{remainingTime}</time>
            </>
          )}
        </header>

        <div
          className="participant-console__log"
          role="log"
          aria-live="polite"
          aria-relevant="additions"
          ref={consoleLogRef}
          data-tour="chat-log"
        >
          {entries.map((entry) => (
            <article
              className={`console-entry console-entry--${entry.author}`}
              key={entry.id}
            >
              <span>
                {entry.author === "system"
                  ? "Система"
                  : entry.author === "assistant"
                    ? "Ассистент"
                    : "Вы"}
              </span>
              <p>{entry.content}</p>
            </article>
          ))}
          {aiThinking && (
            <article className="console-entry console-entry--assistant console-entry--thinking">
              <span>Ассистент</span>
              <p>Ассистент думает…</p>
            </article>
          )}
          {error && (
            <article className="console-entry console-entry--error" role="alert">
              <span>Соединение</span>
              <p>{error}</p>
            </article>
          )}
        </div>

        <form
          className="participant-console__form"
          onSubmit={submitCommand}
          data-tour="chat-form"
        >
          <label htmlFor="participantCommand">Команда или сообщение</label>
          {task.status === "active" && !timeIsUp && (
            <div className="participant-console__chips" aria-label="Быстрые команды">
              <button
                type="button"
                disabled={isBusy}
                aria-label="Ввести команду /answer"
                onClick={() => {
                  setDraft((current) =>
                    current.startsWith("/answer")
                      ? current
                      : `/answer ${current}`.trimEnd() + " ",
                  );
                  inputRef.current?.focus();
                }}
              >
                Ответ
              </button>
              {isZendo && (
                <button
                  type="button"
                  disabled={isBusy}
                  aria-label="Ввести команду /test"
                  onClick={() => {
                    setDraft((current) =>
                      current.startsWith("/test")
                        ? current
                        : `/test ${current}`.trimEnd() + " ",
                    );
                    inputRef.current?.focus();
                  }}
                >
                  Проверить
                </button>
              )}
              {!tutorialMode && (
                <button
                  type="button"
                  disabled={isBusy}
                  aria-label="Выполнить команду /skip"
                  onClick={() => void runCommand("/skip")}
                >
                  Пропустить
                </button>
              )}
            </div>
          )}
          <div>
            <span aria-hidden="true">&gt;</span>
            <input
              ref={inputRef}
              id="participantCommand"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              title={task.responseHint ?? undefined}
              placeholder={
                timeIsUp
                  ? "Время попытки завершено"
                  : "Команда (/help) или вопрос ассистенту"
              }
              autoComplete="off"
              spellCheck={false}
              maxLength={MAX_COMMAND_LENGTH}
              disabled={isBusy}
              onPaste={(event) => {
                const pastedText = event.clipboardData.getData("text");
                emitTelemetry("client_chat_paste", {
                  character_count: pastedText.length,
                  line_count: pastedText
                    ? pastedText.split(/\r\n|\r|\n/).length
                    : 0,
                });
              }}
            />
            <button
              type="submit"
              disabled={isBusy || !draft.trim()}
              aria-label="Отправить"
            >
              <SendIcon />
            </button>
          </div>
          <p>
            {timeIsUp
              ? "Время завершено · новые команды не принимаются"
              : busy || commandBusy
                ? "Выполняем команду…"
                : aiRemaining
                  ? `Enter — отправить · /help — команды · ассистент: ${aiRemaining.task} по задаче, ${aiRemaining.attempt} за попытку`
                  : "Enter — отправить · /help — команды"}
          </p>
        </form>
      </aside>
    </main>
  );
}

const GEOMETRY_COLORS: Record<string, string> = {
  cyan: "#4bbecf",
  navy: "#004278",
  grape: "#48304d",
  plum: "#c792df",
  violet: "#765184",
  coral: "#e5857b",
  gold: "#a678c9",
  green: "#4f9d79",
  gray: "#958b98",
};

function geometryColor(value?: string): string {
  if (!value) return GEOMETRY_COLORS.grape;
  return GEOMETRY_COLORS[value] ?? value;
}

function DotSeparated({ items }: { items: string[] }) {
  return (
    <>
      {items.map((item, index) => (
        <Fragment key={index}>
          {index > 0 && (
            <span className="sep-dot" aria-hidden="true">
              ·
            </span>
          )}
          {item}
        </Fragment>
      ))}
    </>
  );
}

function cardIn(content: Record<string, unknown>, key: string, group: string) {
  return (Array.isArray(content[key]) ? (content[key] as unknown[]) : []).some(
    (item) =>
      typeof item === "object" &&
      item !== null &&
      "card_id" in item &&
      (item as { card_id?: unknown }).card_id === group,
  );
}

function geometryGroupOutcome(
  group: string,
  content: Record<string, unknown>,
): "positive" | "negative" | null {
  for (const key of ["examples", "probe_observations"]) {
    const found = (
      Array.isArray(content[key]) ? (content[key] as unknown[]) : []
    ).find(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        "card_id" in item &&
        (item as { card_id?: unknown }).card_id === group,
    );
    if (found && typeof found === "object" && "classification" in found) {
      return (found as { classification?: unknown }).classification ===
        "positive"
        ? "positive"
        : "negative";
    }
  }
  return null;
}

function geometryGroupRole(
  group: string,
  content: Record<string, unknown>,
): string {
  if (group === "source" || group === "image") return group;
  if (cardIn(content, "examples", group)) return "example";
  if (cardIn(content, "targets", group)) return "target";
  // Вскрытая проба ведёт себя как открытая конструкция-пример.
  if (cardIn(content, "probe_observations", group)) return "example";
  if (cardIn(content, "probe_cards", group)) return "probe";
  return "plain";
}

function geometryGroupLabel(
  group: string,
  content: Record<string, unknown>,
): string {
  if (group === "source") return "Исходная фигура";
  if (group === "image") return "Образ";
  const examples = Array.isArray(content.examples) ? content.examples : [];
  const example = examples.find(
    (item) =>
      typeof item === "object" &&
      item !== null &&
      "card_id" in item &&
      item.card_id === group,
  );
  if (example && "classification" in example) {
    return `${group} · ${
      example.classification === "positive" ? "подходит" : "не подходит"
    }`;
  }
  const targetIndex = (Array.isArray(content.targets) ? content.targets : [])
    .findIndex(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        "card_id" in item &&
        item.card_id === group,
    );
  if (targetIndex >= 0) return `${group} · цель ${targetIndex + 1}`;
  const probe = (Array.isArray(content.probe_cards) ? content.probe_cards : [])
    .find(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        "card_id" in item &&
        item.card_id === group,
    );
  if (probe) {
    const observed = (Array.isArray(content.probe_observations)
      ? content.probe_observations
      : []
    ).find(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        "card_id" in item &&
        item.card_id === group,
    );
    if (observed && "classification" in observed) {
      return `${group} · ${
        observed.classification === "positive" ? "подходит" : "не подходит"
      }`;
    }
    return `${group} · доступна проба`;
  }
  return group.replaceAll("_", " ");
}

function GeometryAtlasScene({
  scene,
  content,
  showGrid = false,
  canProbe = false,
  onProbe,
}: {
  scene: GeometryScene;
  content: Record<string, unknown>;
  showGrid?: boolean;
  canProbe?: boolean;
  onProbe?: (cardId: string) => void;
}) {
  const groups = Array.from(
    new Set([
      ...scene.points.map((point) => point.group),
      ...scene.edges.map((edge) => edge.group),
    ]),
  );
  const pointByKey = new Map(
    scene.points.map((point) => [`${point.group}:${point.id}`, point]),
  );
  const width = Math.max(1, scene.bounds.maxX - scene.bounds.minX);
  const height = Math.max(1, scene.bounds.maxY - scene.bounds.minY);
  const flipY = (value: number) => scene.bounds.maxY + scene.bounds.minY - value;
  const viewPadding = Math.max(width, height) * 0.09;
  const radius = showGrid
    ? 0.16
    : Math.max(
        0.48,
        Math.min(0.72, Math.min(width, height) * 0.075),
      );
  const verticalGridLines = Array.from(
    {
      length: Math.max(
        0,
        Math.floor(scene.bounds.maxX) - Math.ceil(scene.bounds.minX) + 1,
      ),
    },
    (_, index) => Math.ceil(scene.bounds.minX) + index,
  );
  const horizontalGridLines = Array.from(
    {
      length: Math.max(
        0,
        Math.floor(scene.bounds.maxY) - Math.ceil(scene.bounds.minY) + 1,
      ),
    },
    (_, index) => Math.ceil(scene.bounds.minY) + index,
  );
  const isTransformPair =
    groups.length === 2 && groups.includes("source") && groups.includes("image");
  return (
    <figure
      className={`geometry-atlas${
        isTransformPair ? " geometry-atlas--pair" : ""
      }${showGrid ? " geometry-atlas--points" : ""}`}
      aria-label="Геометрические конфигурации"
      data-tour="graph-cards"
    >
      <div className="geometry-atlas__cards">
        {groups.map((group) => {
          const points = scene.points.filter((point) => point.group === group);
          const edges = scene.edges.filter((edge) => edge.group === group);
          const role = geometryGroupRole(group, content);
          const outcome = geometryGroupOutcome(group, content);
          const probeable = role === "probe" && canProbe && Boolean(onProbe);
          return (
            <section
              className={`geometry-card${
                probeable ? " geometry-card--probeable" : ""
              }`}
              data-role={role}
              data-outcome={outcome ?? undefined}
              data-tour={
                role === "probe"
                  ? "probe-card"
                  : role === "target"
                    ? "targets"
                    : undefined
              }
              onClick={probeable ? () => onProbe?.(group) : undefined}
              role={probeable ? "button" : undefined}
              tabIndex={probeable ? 0 : undefined}
              onKeyDown={
                probeable
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onProbe?.(group);
                      }
                    }
                  : undefined
              }
              key={group}
            >
              <header>
                {geometryGroupLabel(group, content)}
                {probeable && <span aria-hidden="true"> · нажми, чтобы проверить</span>}
              </header>
              <svg
                viewBox={`${scene.bounds.minX - viewPadding} ${
                  scene.bounds.minY - viewPadding
                } ${width + viewPadding * 2} ${height + viewPadding * 2}`}
                role="img"
                aria-label={`Конфигурация ${group}`}
              >
                <rect
                  className="geometry-card__plane"
                  x={scene.bounds.minX}
                  y={scene.bounds.minY}
                  width={width}
                  height={height}
                />
                {showGrid && (
                  <g className="geometry-card__grid" aria-hidden="true">
                    {verticalGridLines.map((x) => (
                      <line
                        className={x === 0 ? "is-axis" : undefined}
                        x1={x}
                        y1={scene.bounds.minY}
                        x2={x}
                        y2={scene.bounds.maxY}
                        key={`grid-x-${x}`}
                      />
                    ))}
                    {horizontalGridLines.map((y) => (
                      <line
                        className={y === 0 ? "is-axis" : undefined}
                        x1={scene.bounds.minX}
                        y1={flipY(y)}
                        x2={scene.bounds.maxX}
                        y2={flipY(y)}
                        key={`grid-y-${y}`}
                      />
                    ))}
                  </g>
                )}
                {edges.map((edge) => {
                  const source = pointByKey.get(`${group}:${edge.source}`);
                  const target = pointByKey.get(`${group}:${edge.target}`);
                  if (!source || !target) return null;
                  return (
                    <line
                      x1={source.x}
                      y1={flipY(source.y)}
                      x2={target.x}
                      y2={flipY(target.y)}
                      stroke={geometryColor(edge.color)}
                      key={edge.id}
                    />
                  );
                })}
                {points.map((point) => (
                  <g key={point.id}>
                    <circle
                      cx={point.x}
                      cy={flipY(point.y)}
                      r={radius}
                      style={{ fill: geometryColor(point.color) }}
                    />
                    {point.label && (
                      <text
                        className={showGrid ? "geometry-card__point-label" : undefined}
                        x={showGrid ? point.x + 0.28 : point.x}
                        y={showGrid ? flipY(point.y) - 0.28 : flipY(point.y)}
                        dominantBaseline="central"
                        textAnchor={showGrid ? "start" : "middle"}
                        style={{
                          fill: showGrid
                            ? "#48304d"
                            : point.color === "cyan"
                              ? "#004278"
                              : "#ffffff",
                          fontSize: showGrid
                            ? "0.52px"
                            : `${Math.max(radius * 1.05, 0.46)}px`,
                        }}
                      >
                        {point.label}
                      </text>
                    )}
                  </g>
                ))}
              </svg>
            </section>
          );
        })}
      </div>
    </figure>
  );
}

const TOKEN_COLOR_STYLES: Record<TokenCard["color"], { fill: string; label: string }> = {
  R: { fill: "#e5857b", label: "красная" },
  G: { fill: "#4f9d79", label: "зелёная" },
  B: { fill: "#4bbecf", label: "синяя" },
};

function TokenShelfScene({
  cards,
  content,
  canProbe = false,
  onProbe,
}: {
  cards: Record<string, TokenCard[]>;
  content: Record<string, unknown>;
  canProbe?: boolean;
  onProbe?: (cardId: string) => void;
}) {
  return (
    <figure className="token-shelf" aria-label="Полки с фишками">
      <div className="token-shelf__cards">
        {Object.entries(cards).map(([cardId, tokens]) => {
          const role = geometryGroupRole(cardId, content);
          const outcome = geometryGroupOutcome(cardId, content);
          const probeable = role === "probe" && canProbe && Boolean(onProbe);
          return (
          <section
            className={`token-card${probeable ? " token-card--probeable" : ""}`}
            data-role={role}
            data-outcome={outcome ?? undefined}
            onClick={probeable ? () => onProbe?.(cardId) : undefined}
            role={probeable ? "button" : undefined}
            tabIndex={probeable ? 0 : undefined}
            onKeyDown={
              probeable
                ? (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onProbe?.(cardId);
                    }
                  }
                : undefined
            }
            key={cardId}
          >
            <header>
              {geometryGroupLabel(cardId, content)}
              {probeable && <span aria-hidden="true"> · нажми, чтобы проверить</span>}
            </header>
            <ol
              className="token-card__shelf"
              aria-label={`Карточка ${cardId}`}
            >
              {tokens.map((token, index) => (
                <li
                  className={`token-chip token-chip--${token.color.toLowerCase()}`}
                  style={{ background: TOKEN_COLOR_STYLES[token.color].fill }}
                  aria-label={`Фишка ${index + 1}: ${token.num}, ${
                    TOKEN_COLOR_STYLES[token.color].label
                  }`}
                  key={index}
                >
                  {token.num}
                </li>
              ))}
            </ol>
          </section>
          );
        })}
      </div>
    </figure>
  );
}


function GridPatternPreview({ rows }: { rows: readonly string[] }) {
  return (
    <div
      className="grid-pattern"
      style={{ gridTemplateColumns: `repeat(${rows[0]?.length ?? 5}, 1fr)` }}
      aria-hidden="true"
    >
      {rows.flatMap((row, rowIndex) =>
        [...row].map((cell, columnIndex) => (
          <i
            className={cell === "1" ? "is-filled" : ""}
            key={`${rowIndex}-${columnIndex}`}
          />
        )),
      )}
    </div>
  );
}

function GridZendoScene({
  cards,
  content,
  canProbe,
  onProbe,
}: {
  cards: Record<string, string[]>;
  content: Record<string, unknown>;
  canProbe: boolean;
  onProbe: (pattern: string) => void;
}) {
  const size = Object.values(cards)[0]?.length ?? 5;
  const [drawn, setDrawn] = useState<boolean[]>(() =>
    Array(size * size).fill(false),
  );
  const observations = Array.isArray(content.probe_observations)
    ? content.probe_observations
    : [];
  const drawnPattern = drawn
    .map((cell) => (cell ? "1" : "0"))
    .join("");

  return (
    <figure className="grid-zendo" aria-label="Узоры на сетке">
      <div className="grid-zendo__cards">
        {Object.entries(cards).map(([cardId, rows]) => (
          <section
            className="grid-card"
            data-role={geometryGroupRole(cardId, content)}
            data-outcome={geometryGroupOutcome(cardId, content) ?? undefined}
            key={cardId}
          >
            <header>{geometryGroupLabel(cardId, content)}</header>
            <GridPatternPreview rows={rows} />
          </section>
        ))}
        <section className="grid-card grid-card--draw">
          <header>Свой узор</header>
          <div
            className="grid-pattern grid-pattern--editable"
            style={{ gridTemplateColumns: `repeat(${size}, 1fr)` }}
            role="group"
            aria-label="Рисование узора для проверки"
          >
            {drawn.map((cell, index) => (
              <button
                type="button"
                className={cell ? "is-filled" : ""}
                aria-pressed={cell}
                aria-label={`Клетка ${Math.floor(index / size) + 1}-${
                  (index % size) + 1
                }`}
                onClick={() =>
                  setDrawn((current) =>
                    current.map((value, cellIndex) =>
                      cellIndex === index ? !value : value,
                    ),
                  )
                }
                key={index}
              />
            ))}
          </div>
          <button
            type="button"
            className="grid-card__probe"
            disabled={!canProbe}
            onClick={() => onProbe(drawnPattern)}
          >
            Проверить узор
          </button>
        </section>
      </div>
      {observations.length > 0 && (
        <div className="grid-zendo__observations">
          {observations.flatMap((item, index) => {
            if (
              typeof item !== "object" ||
              item === null ||
              !("pattern" in item) ||
              !Array.isArray(item.pattern)
            ) {
              return [];
            }
            return [
              <section className="grid-card" key={index}>
                <header>
                  Проба {index + 1}:{" "}
                  {"classification" in item &&
                  item.classification === "positive"
                    ? "подходит"
                    : "не подходит"}
                </header>
                <GridPatternPreview rows={item.pattern as string[]} />
              </section>,
            ];
          })}
        </div>
      )}
    </figure>
  );
}


function WiringLampRow({
  label,
  lamps,
  current = false,
}: {
  label: string;
  lamps: readonly number[];
  current?: boolean;
}) {
  return (
    <section
      className={`machine-state${current ? " machine-state--current" : ""}`}
    >
      <span>{label}</span>
      <ol className="machine-lamps" aria-label={`${label}: состояние ламп`}>
        {lamps.map((lamp, index) => (
          <li
            className={lamp ? "is-on" : ""}
            aria-label={`Лампа ${index + 1}: ${lamp ? "горит" : "не горит"}`}
            key={index}
          >
            <i aria-hidden="true" />
            <small>{index + 1}</small>
          </li>
        ))}
      </ol>
    </section>
  );
}

function WiringPanelScene({
  state,
  canAct,
  onChord,
}: {
  state: HiddenWiringPublicState;
  canAct: boolean;
  onChord: (opId: string) => void;
}) {
  const [selected, setSelected] = useState<number[]>([]);
  const chordReady = selected.length === 2;
  const chordId = chordReady
    ? `b${Math.min(...selected)}+b${Math.max(...selected)}`
    : null;
  const chordAllowed =
    chordId !== null && state.ops.some((operation) => operation.id === chordId);

  function toggleButton(index: number) {
    setSelected((currentSelection) =>
      currentSelection.includes(index)
        ? currentSelection.filter((value) => value !== index)
        : currentSelection.length < 2
          ? [...currentSelection, index]
          : [currentSelection[1], index],
    );
  }

  return (
    <figure className="wiring-panel" aria-label="Панель со скрытой проводкой">
      <div className="machine-panel__states">
        <WiringLampRow label="Сейчас" lamps={state.current} current />
        {state.target && <WiringLampRow label="Цель" lamps={state.target} />}
      </div>

      <div className="wiring-panel__buttons" role="group" aria-label="Кнопки панели">
        {Array.from({ length: state.buttonCount }, (_, index) => index + 1).map(
          (button) => (
            <button
              type="button"
              className={selected.includes(button) ? "is-selected" : ""}
              aria-pressed={selected.includes(button)}
              onClick={() => toggleButton(button)}
              key={button}
            >
              {button}
            </button>
          ),
        )}
        <button
          type="button"
          className="wiring-panel__fire"
          disabled={!canAct || !chordReady || !chordAllowed}
          onClick={() => {
            if (chordId) {
              onChord(chordId);
              setSelected([]);
            }
          }}
        >
          Нажать комбинацию
        </button>
      </div>
      {chordReady && !chordAllowed && (
        <p className="wiring-panel__warning">
          Эта комбинация недоступна для проб.
        </p>
      )}

      {state.observations.length > 0 && (
        <ol className="wiring-panel__log" aria-label="Наблюдения">
          {state.observations.map((observation, index) => (
            <li key={index}>
              <code>{observation.chord}</code>
              {observation.training && <em> обучающая</em>}
              <span>
                переключились:{" "}
                {observation.effect
                  .map((bit, lamp) => (bit ? lamp + 1 : null))
                  .filter((lamp) => lamp !== null)
                  .join(", ") || "ничего"}
              </span>
            </li>
          ))}
        </ol>
      )}

    </figure>
  );
}


function FoldPunchScene({
  state,
  canAnswer,
  onSubmit,
}: {
  state: FoldPunchPublicState;
  canAnswer: boolean;
  onSubmit: (cells: string) => void;
}) {
  const size = state.sheetSize;
  const [marked, setMarked] = useState<boolean[]>(() =>
    Array(size * size).fill(false),
  );
  const holeSet = new Set(
    state.folded.holes.map(([row, column]) => `${row}:${column}`),
  );
  const markedCells = marked
    .map((cell, index) =>
      cell
        ? `${Math.floor(index / size) + 1},${(index % size) + 1}`
        : null,
    )
    .filter((cell): cell is string => cell !== null);

  return (
    <figure className="fold-punch" aria-label="Дырокол">
      <ol className="fold-punch__folds" aria-label="Порядок сгибов">
        {state.folds.map((fold, index) => (
          <li key={index}>
            <span>{index + 1}</span>
            {fold.label}
          </li>
        ))}
        <li>
          <span>{state.folds.length + 1}</span>
          Пробили {state.folded.holes.length === 1 ? "дырку" : "дырки"}
        </li>
      </ol>

      <div className="fold-punch__panels">
        <section>
          <header>Сложенный лист с дырками</header>
          <div
            className="fold-punch__grid fold-punch__grid--folded"
            style={{
              gridTemplateColumns: `repeat(${state.folded.width}, 18px)`,
            }}
            aria-hidden="true"
          >
            {Array.from(
              { length: state.folded.height * state.folded.width },
              (_, index) => {
                const row = Math.floor(index / state.folded.width);
                const column = index % state.folded.width;
                const outside =
                  state.folded.triangle && column > row;
                return (
                  <i
                    className={[
                      outside ? "is-outside" : "",
                      holeSet.has(`${row}:${column}`) ? "is-hole" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    key={index}
                  />
                );
              },
            )}
          </div>
        </section>
        <section>
          <header>Развёрнутый лист — отметьте дырки</header>
          <div
            className="fold-punch__grid fold-punch__grid--answer"
            style={{ gridTemplateColumns: `repeat(${size}, 1fr)` }}
            role="group"
            aria-label="Отметка дырок на развёрнутом листе"
          >
            {marked.map((cell, index) => (
              <button
                type="button"
                className={cell ? "is-hole" : ""}
                aria-pressed={cell}
                aria-label={`Клетка ${Math.floor(index / size) + 1}-${
                  (index % size) + 1
                }`}
                onClick={() =>
                  setMarked((current) =>
                    current.map((value, cellIndex) =>
                      cellIndex === index ? !value : value,
                    ),
                  )
                }
                key={index}
              />
            ))}
          </div>
          <button
            type="button"
            className="fold-punch__submit"
            disabled={!canAnswer || markedCells.length === 0}
            onClick={() => onSubmit(markedCells.join(" "))}
          >
            Отправить отмеченные клетки
          </button>
        </section>
      </div>

    </figure>
  );
}

function DiceScene({
  dice,
}: {
  dice: readonly ChessDie[];
}) {
  return (
    <figure className="dice-scene" aria-label="Шахматные кубики">
      <div className="dice-set">
        {dice.map((die) => (
          <section className="chess-die" key={die.id}>
            <p>{die.label}</p>
            <ol aria-label={`Грани: ${die.label}`}>
              {die.faces.map((face, faceIndex) => (
                <li
                  title={DICE_FACE_NAMES[face]}
                  aria-label={`Грань ${faceIndex + 1}: ${DICE_FACE_NAMES[face]}`}
                  key={`${die.id}-${faceIndex}`}
                >
                  <span aria-hidden="true">{DICE_GLYPHS[face]}</span>
                  <small>{DICE_FACE_NAMES[face]}</small>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </figure>
  );
}

function DicePositionScene({
  board,
  die,
  sideToMove = "white",
}: {
  board: ChessBoard;
  die: ChessDie;
  sideToMove?: "white" | "black";
}) {
  return (
    <div className="dice-position-scene">
      <Chessboard board={board} compact />

      <section className="position-die" aria-label="Кубик текущего хода">
        <p>Грани кубика</p>
        <ol aria-label={`Грани: ${die.label}`}>
          {die.faces.map((face, faceIndex) => (
            <li
              title={DICE_FACE_NAMES[face]}
              aria-label={`Грань ${faceIndex + 1}: ${DICE_FACE_NAMES[face]}`}
              key={`${die.id}-${faceIndex}`}
            >
              <span aria-hidden="true">
                {sideToMove === "black"
                  ? BLACK_DICE_GLYPHS[face]
                  : DICE_GLYPHS[face]}
              </span>
              <small>{DICE_FACE_NAMES[face]}</small>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

const COVERAGE_GLYPHS: Record<"K" | "Q" | "R" | "B" | "N", string> = {
  K: "♔",
  Q: "♕",
  R: "♖",
  B: "♗",
  N: "♘",
};

function ChessCoverageScene({
  state,
  canAct = false,
  onToggle,
  onReset,
  onSubmit,
}: {
  state: ChessCoveragePublicState;
  canAct?: boolean;
  onToggle?: (candidateId: string) => void;
  onReset?: () => void;
  onSubmit?: () => void;
}) {
  if (state.variant === "custom_jump_placement") {
    return (
      <ChessPlacementScene
        state={state}
        canAct={canAct}
        onAction={onToggle}
        onReset={onReset}
        onSubmit={onSubmit}
      />
    );
  }
  return (
    <LegacyChessCoverageScene
      state={state}
      canAct={canAct}
      onToggle={onToggle}
      onReset={onReset}
      onSubmit={onSubmit}
    />
  );
}

function ChessPlacementScene({
  state,
  canAct = false,
  onAction,
  onReset,
  onSubmit,
}: {
  state: ChessCoveragePublicState;
  canAct?: boolean;
  onAction?: (action: string) => void;
  onReset?: () => void;
  onSubmit?: () => void;
}) {
  const [activePiece, setActivePiece] = useState(
    state.pieceTypes[0]?.id ?? "N",
  );
  const targets = new Set(
    state.targets.map((point) => `${point.row}:${point.col}`),
  );
  const covered = new Set(
    state.coveredTargets.map((point) => `${point.row}:${point.col}`),
  );
  const placements = new Map(
    state.placements.map((placement) => [
      `${placement.row}:${placement.col}`,
      placement,
    ]),
  );
  const activeDefinition = state.pieceTypes.find(
    (piece) => piece.id === activePiece,
  );
  const placementLimitReached = state.placements.length >= state.maxPlacements;

  return (
    <figure className="coverage-scene" aria-label="Задача о покрытии клеток">
      <div className="coverage-placement">
        <section className="coverage-palette" aria-label="Палитра фигур">
          {state.pieceTypes.map((piece) => {
            const count = state.pieceCounts[piece.id] ?? 0;
            const nextCost = piece.baseCost + piece.repeatSurcharge * count;
            const exhausted = count >= piece.limit;
            return (
              <button
                type="button"
                className={[
                  "coverage-piece-card",
                  activePiece === piece.id ? "is-active" : "",
                ].filter(Boolean).join(" ")}
                aria-pressed={activePiece === piece.id}
                disabled={!canAct || exhausted || placementLimitReached}
                onClick={() => setActivePiece(piece.id)}
                key={piece.id}
              >
                <span className="coverage-piece-card__glyph" aria-hidden="true">
                  {COVERAGE_GLYPHS[piece.id]}
                </span>
                <span className="coverage-piece-card__copy">
                  <strong>{piece.label}</strong>
                  <small>{piece.moveLabel}</small>
                </span>
                <span className="coverage-piece-card__cost">
                  {exhausted ? "лимит" : `следующая: ${nextCost}`}
                  <small>{count} / {piece.limit}</small>
                </span>
              </button>
            );
          })}
        </section>

        {activeDefinition && (
          <div className="coverage-move-rule" aria-live="polite">
            <MovePattern piece={activeDefinition} />
            <p>
              <strong>{COVERAGE_GLYPHS[activeDefinition.id]} {activeDefinition.label}</strong>
              атакует только отмеченные клетки и перепрыгивает всё между ними.
              Стоимость: {activeDefinition.baseCost}, затем +
              {activeDefinition.repeatSurcharge} за каждую уже поставленную фигуру
              этого типа.
            </p>
          </div>
        )}

        <div className="coverage-placement-board" role="grid" aria-label="Доска 8 на 8">
          {Array.from({ length: 64 }, (_, index) => {
            const row = Math.floor(index / 8);
            const col = index % 8;
            const key = `${row}:${col}`;
            const placement = placements.get(key);
            const target = targets.has(key);
            const isCovered = covered.has(key);
            const canPlace = Boolean(
              canAct &&
              onAction &&
              activeDefinition &&
              !target &&
              !placement &&
              !placementLimitReached &&
              (state.pieceCounts[activeDefinition.id] ?? 0) < activeDefinition.limit,
            );
            const canRemove = Boolean(canAct && onAction && placement);
            return (
              <button
                type="button"
                role="gridcell"
                className={[
                  "coverage-placement-board__cell",
                  (row + col) % 2 ? "is-dark" : "",
                  target ? "is-target" : "",
                  isCovered ? "is-covered" : "",
                  placement ? "is-occupied" : "",
                ].filter(Boolean).join(" ")}
                disabled={!canPlace && !canRemove}
                aria-label={
                  placement
                    ? `${placement.id}, ${placement.piece}, клетка ${String.fromCharCode(65 + col)}${row + 1}, стоимость ${placement.cost}. Нажмите, чтобы убрать.`
                    : `Клетка ${String.fromCharCode(65 + col)}${row + 1}${target ? ", цель" : ""}`
                }
                onClick={() => {
                  if (placement) {
                    onAction?.(`remove:${placement.id}`);
                  } else if (canPlace && activeDefinition) {
                    onAction?.(`place:${activeDefinition.id}:${row}:${col}`);
                  }
                }}
                key={key}
              >
                {row === 7 && (
                  <span className="coverage-placement-board__file" aria-hidden="true">
                    {String.fromCharCode(65 + col)}
                  </span>
                )}
                {col === 0 && (
                  <span className="coverage-placement-board__rank" aria-hidden="true">
                    {row + 1}
                  </span>
                )}
                {target && (
                  <span className="coverage-placement-board__target" aria-hidden="true">
                    {isCovered ? "●" : "○"}
                  </span>
                )}
                {placement && (
                  <>
                    <span className="coverage-placement-board__piece" aria-hidden="true">
                      {COVERAGE_GLYPHS[placement.piece]}
                    </span>
                    <b aria-hidden="true">{placement.cost}</b>
                  </>
                )}
              </button>
            );
          })}
        </div>

        <div className="coverage-placement-footer">
          <dl>
            <div><dt>Покрыто</dt><dd>{state.coveredTargets.length} / {state.targets.length}</dd></div>
            <div><dt>Стоимость</dt><dd>{state.totalCost}</dd></div>
            <div><dt>Фигур</dt><dd>{state.placements.length} / {state.maxPlacements}</dd></div>
          </dl>
          <div className="coverage-placement-actions">
            <button
              type="button"
              disabled={!canAct || state.placements.length === 0 || !onReset}
              onClick={onReset}
            >
              Вернуть в начало
            </button>
            <button
              type="button"
              className="is-primary"
              disabled={!canAct || !state.allCovered || !onSubmit}
              onClick={onSubmit}
            >
              Зафиксировать расстановку
            </button>
          </div>
        </div>
      </div>
    </figure>
  );
}

function MovePattern({
  piece,
}: {
  piece: ChessCoveragePublicState["pieceTypes"][number];
}) {
  const attacked = new Set(
    piece.offsets.map((offset) => `${offset.row + 3}:${offset.col + 3}`),
  );
  return (
    <span className="coverage-move-pattern" aria-label={`Схема хода: ${piece.moveLabel}`}>
      {Array.from({ length: 49 }, (_, index) => {
        const row = Math.floor(index / 7);
        const col = index % 7;
        return (
          <span
            className={[
              row === 3 && col === 3 ? "is-origin" : "",
              attacked.has(`${row}:${col}`) ? "is-attacked" : "",
            ].filter(Boolean).join(" ")}
            key={`${row}:${col}`}
          />
        );
      })}
    </span>
  );
}

function LegacyChessCoverageScene({
  state,
  canAct = false,
  onToggle,
  onReset,
  onSubmit,
}: {
  state: ChessCoveragePublicState;
  canAct?: boolean;
  onToggle?: (candidateId: string) => void;
  onReset?: () => void;
  onSubmit?: () => void;
}) {
  const targets = new Set(
    state.targets.map((point) => `${point.row}:${point.col}`),
  );
  const covered = new Set(
    state.coveredTargets.map((point) => `${point.row}:${point.col}`),
  );
  const candidates = new Map(
    state.candidates.map((candidate) => [
      `${candidate.row}:${candidate.col}`,
      candidate,
    ]),
  );
  const selected = new Set(state.selectedIds);
  const usedPieces = Array.from(
    new Set(state.candidates.map((candidate) => candidate.piece)),
  );

  return (
    <figure className="coverage-scene" aria-label="Шахматное покрытие">
      <div className="coverage-layout">
        <div
          className="coverage-board"
          role="grid"
          aria-label={`Доска ${state.boardSize} на ${state.boardSize}`}
          style={{
            gridTemplateColumns: `auto repeat(${state.boardSize}, 1fr)`,
          }}
        >
          <span className="coverage-board__axis" aria-hidden="true" />
          {Array.from({ length: state.boardSize }, (_, col) => (
            <span
              className="coverage-board__axis"
              aria-hidden="true"
              key={`col-${col}`}
            >
              {String.fromCharCode(65 + col)}
            </span>
          ))}
          {Array.from({ length: state.boardSize }, (_, row) => (
            <Fragment key={`coverage-row-${row}`}>
              <span className="coverage-board__axis" aria-hidden="true">
                {row + 1}
              </span>
              {Array.from({ length: state.boardSize }, (_, col) => {
                const cellKey = `${row}:${col}`;
                const candidate = candidates.get(cellKey);
                const isTarget = targets.has(cellKey);
                const isCovered = covered.has(cellKey);
                const isSelected = candidate
                  ? selected.has(candidate.id)
                  : false;
                return (
                  <button
                    type="button"
                    className={[
                      "coverage-board__cell",
                      (row + col) % 2 ? "is-dark" : "",
                      isTarget ? "is-target" : "",
                      isCovered ? "is-covered" : "",
                      isSelected ? "is-selected" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    disabled={!candidate || !canAct || !onToggle}
                    aria-pressed={candidate ? isSelected : undefined}
                    aria-label={
                      candidate
                        ? `${candidate.id}, ${candidate.pieceLabel}, стоимость ${candidate.weight}, клетка ${row + 1}${String.fromCharCode(65 + col)}`
                        : `Клетка ${row + 1}${String.fromCharCode(65 + col)}${isTarget ? ", цель" : ""}`
                    }
                    onClick={() => candidate && onToggle?.(candidate.id)}
                    key={cellKey}
                  >
                    {isTarget && (
                      <span className="coverage-board__target" aria-hidden="true">
                        {isCovered ? "●" : "○"}
                      </span>
                    )}
                    {candidate && (
                      <>
                        <span className="coverage-board__piece" aria-hidden="true">
                          {COVERAGE_GLYPHS[candidate.piece]}
                        </span>
                        <small>{candidate.id}</small>
                        <b>{candidate.weight}</b>
                      </>
                    )}
                  </button>
                );
              })}
            </Fragment>
          ))}
        </div>

        <aside className="coverage-summary">
          <div>
            <span>Покрыто</span>
            <strong>
              {state.coveredTargets.length} / {state.targets.length}
            </strong>
          </div>
          <div>
            <span>Стоимость</span>
            <strong>{state.totalWeight}</strong>
          </div>
          <p>
            ○ — цель, ● — уже покрытая цель. Число у фигуры — её стоимость.
          </p>
          <ul aria-label="Доступные типы фигур">
            {usedPieces.map((piece) => {
              const candidate = state.candidates.find(
                (item) => item.piece === piece,
              );
              return (
                <li key={piece}>
                  <span aria-hidden="true">{COVERAGE_GLYPHS[piece]}</span>
                  {candidate?.pieceLabel ?? piece}
                </li>
              );
            })}
          </ul>
          <button
            type="button"
            className="coverage-summary__reset"
            disabled={!canAct || state.selectedIds.length === 0 || !onReset}
            onClick={onReset}
          >
            Вернуть в начало
          </button>
          <button
            type="button"
            className="coverage-summary__submit"
            disabled={!canAct || !state.allCovered || !onSubmit}
            onClick={onSubmit}
          >
            Зафиксировать расстановку
          </button>
        </aside>
      </div>
    </figure>
  );
}

function MachineStateDisplay({
  label,
  state,
  current = false,
}: {
  label: string;
  state: MachineState;
  current?: boolean;
}) {
  return (
    <section
      className={`machine-state${current ? " machine-state--current" : ""}`}
    >
      <span>{label}</span>
      {"lamps" in state ? (
        <ol className="machine-lamps" aria-label={`${label}: состояние ламп`}>
          {state.lamps.map((lamp, index) => (
            <li
              className={lamp ? "is-on" : ""}
              aria-label={`Лампа ${index + 1}: ${lamp ? "горит" : "не горит"}`}
              key={index}
            >
              <i aria-hidden="true" />
              <small>{index + 1}</small>
            </li>
          ))}
        </ol>
      ) : "cards" in state ? (
        <ol className="machine-cards" aria-label={`${label}: порядок карточек`}>
          {state.cards.map((card, index) => (
            <li key={`${card}-${index}`}>{card}</li>
          ))}
        </ol>
      ) : (
        <strong className="machine-number">{state.value}</strong>
      )}
    </section>
  );
}

function MachinePanel({
  state,
  canAct = false,
  onOp,
  onReset,
}: {
  state: MachinePanelPublicState;
  canAct?: boolean;
  onOp?: (opId: string) => void;
  onReset?: () => void;
}) {
  const isLampPanel = state.subKind === "lamps_gf2";
  return (
    <figure className="machine-panel" aria-label="Пульт машины">
      <div
        className={`machine-panel__states${
          isLampPanel ? " machine-panel__states--two" : ""
        }`}
      >
        {!isLampPanel && (
          <MachineStateDisplay label="Старт" state={state.start} />
        )}
        <MachineStateDisplay label="Сейчас" state={state.current} current />
        <MachineStateDisplay label="Цель" state={state.target} />
      </div>

      <ol className="machine-operations" aria-label="Доступные операции">
        {state.ops.map((operation) => (
          <li key={operation.id}>
            <button
              type="button"
              disabled={!canAct || !onOp}
              onClick={() => onOp?.(operation.id)}
            >
              <code>{operation.id}</code>
              <span>{operation.label}</span>
            </button>
          </li>
        ))}
      </ol>

      {isLampPanel && (
        <button
          type="button"
          className="machine-panel__reset"
          disabled={!canAct || !onReset}
          onClick={onReset}
        >
          Вернуть в начало
        </button>
      )}

    </figure>
  );
}

function LeaperBoardScene({
  state,
  canAct = false,
  onOp,
}: {
  state: LeaperBoardPublicState;
  canAct?: boolean;
  onOp?: (opId: string) => void;
}) {
  const blocked = new Set(
    state.blocked.map((cell) => `${cell.row}:${cell.col}`),
  );
  const currentKey = `${state.current.row}:${state.current.col}`;
  const targetKey = `${state.target.row}:${state.target.col}`;
  return (
    <figure className="leaper-scene" aria-label="Доска прыгуна">
      <div
        className="leaper-board"
        role="grid"
        aria-label="Доска прыгуна: нумерация с 1, строка 1 сверху"
        style={{ gridTemplateColumns: `auto repeat(${state.cols}, 1fr)` }}
      >
        <span className="leaper-board__corner" aria-hidden="true" />
        {Array.from({ length: state.cols }, (_, col) => (
          <span
            className="leaper-board__axis"
            aria-hidden="true"
            key={`col-${col}`}
          >
            {col + 1}
          </span>
        ))}
        {Array.from({ length: state.rows }, (_, row) => (
          <Fragment key={`row-${row}`}>
            <span className="leaper-board__axis" aria-hidden="true">
              {row + 1}
            </span>
            {Array.from({ length: state.cols }, (_, col) => {
              const key = `${row}:${col}`;
              const isBlocked = blocked.has(key);
              const isCurrent = key === currentKey;
              const isTarget = key === targetKey;
              return (
                <div
                  className={[
                    "leaper-board__cell",
                    isBlocked ? "is-blocked" : "",
                    isCurrent ? "is-current" : "",
                    isTarget ? "is-target" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  role="gridcell"
                  aria-label={`Строка ${row + 1}, столбец ${col + 1}: ${
                    isBlocked
                      ? "заблокировано"
                      : isCurrent
                        ? "фигура"
                        : isTarget
                          ? "цель"
                          : "пусто"
                  }`}
                  key={key}
                >
                  {isCurrent ? "♞" : isTarget ? "✦" : ""}
                </div>
              );
            })}
          </Fragment>
        ))}
      </div>
      <p className="leaper-scene__legend">
        Координаты — (строка, столбец), нумерация с 1, строка 1 — верхняя.
        Фигура: ({state.current.row + 1}, {state.current.col + 1}), цель ✦: (
        {state.target.row + 1}, {state.target.col + 1}).
      </p>
      <ol className="leaper-operations" aria-label="Разрешённые прыжки">
        {state.ops.map((operation) => (
          <li key={operation.id}>
            <button
              type="button"
              disabled={!canAct || !onOp}
              onClick={() => onOp?.(operation.id)}
            >
              <code>{operation.id}</code>
              <span>{operation.label}</span>
            </button>
          </li>
        ))}
      </ol>
    </figure>
  );
}

function Chessboard({
  board,
  compact = false,
  goalSquare,
}: {
  board: ChessBoard;
  compact?: boolean;
  goalSquare?: string;
}) {
  const rowCount = board.length;
  const colCount = Math.max(1, ...board.map((rank) => rank.length));

  return (
    <div
      className={`chess-position${compact ? " chess-position--compact" : ""}`}
    >
      <div
        className="chessboard"
        role="grid"
        aria-label="Шахматная доска, белые снизу"
        style={{
          gridTemplateColumns: `repeat(${colCount}, 1fr)`,
          gridTemplateRows: `repeat(${Math.max(1, rowCount)}, 1fr)`,
          aspectRatio: `${colCount} / ${Math.max(1, rowCount)}`,
        }}
      >
        {board.flatMap((rank, rankIndex) =>
          rank.map((piece, fileIndex) => {
            const rankNumber = rowCount - rankIndex;
            const coordinate = `${FILES[fileIndex] ?? "?"}${rankNumber}`;
            const isDark = (rankIndex + fileIndex) % 2 === 1;
            const isGoal = coordinate === goalSquare;

            return (
              <div
                className={[
                  "chess-square",
                  isDark ? "chess-square--dark" : "",
                  isGoal ? "chess-square--goal" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                role="gridcell"
                aria-label={`${coordinate}: ${piece ? PIECE_NAMES[piece] : "пусто"}${
                  isGoal ? ", маяк" : ""
                }`}
                key={coordinate}
              >
                {fileIndex === 0 && (
                  <span className="chess-square__rank" aria-hidden="true">
                    {rankNumber}
                  </span>
                )}
                {rankIndex === rowCount - 1 && (
                  <span className="chess-square__file" aria-hidden="true">
                    {FILES[fileIndex]}
                  </span>
                )}
                {piece && (
                  <span
                    className={`chess-piece ${
                      piece.startsWith("w")
                        ? "chess-piece--white"
                        : "chess-piece--black"
                    }`}
                    aria-hidden="true"
                  >
                    {PIECE_GLYPHS[piece]}
                  </span>
                )}
                {isGoal && (
                  <span className="chess-square__goal" aria-hidden="true">
                    ✦
                  </span>
                )}
              </div>
            );
          }),
        )}
      </div>
    </div>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m5 12 13-7-4.5 14-2.4-5.1L5 12Z" />
      <path d="m11.1 13.9 3.4-3.4" />
    </svg>
  );
}
