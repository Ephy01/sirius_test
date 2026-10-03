import {
  Fragment,
  type ClipboardEvent,
  type FormEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  ApiError,
  isRecord,
  type AiTurn,
  type AiTurnHistory,
  type ChessBoardPieceSymbol,
  type ChessBoardState,
  type ChessCoveragePieceType,
  type ChessCoveragePublicState,
  type ChessPieceSymbol,
  type DebugAnswerResponse,
  type DiceDefinition,
  type FoldPunchPublicState,
  type GeometryScene,
  type HiddenWiringPublicState,
  type LeaperBoardPublicState,
  type MachinePanelPublicState,
  type MachineState,
  type ParticipantTask,
  type ParticipantTelemetryEvent,
  type ParticipantTelemetryEventType,
  type TaskProgressEntry,
  type TokenCard,
} from "../api";
import "./participant-workspace.css";

export type TaskTransitionResult = {
  ordinal: number;
  advanced: boolean;
  message?: string;
};

export type TaskMoveTransitionResult = TaskTransitionResult & {
  accepted: boolean;
  completed: boolean;
};

type ParticipantWorkspaceProps = {
  task: ParticipantTask;
  attemptId?: string;
  deadlineAt?: string | null;
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
  onGetAnswer?: () => Promise<DebugAnswerResponse>;
  onApplyOperation?: (
    opId: string,
    clientActionId: string,
  ) => Promise<TaskMoveTransitionResult>;
  onUndo?: (clientActionId: string) => Promise<TaskMoveTransitionResult>;
  onReset?: (clientActionId: string) => Promise<TaskMoveTransitionResult>;
  onAiMessage?: (message: string, clientActionId: string) => Promise<AiTurn>;
  onLoadAiHistory?: () => Promise<AiTurnHistory>;
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

const PIECE_GLYPHS: Record<ChessBoardPieceSymbol, string> = {
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

const PIECE_NAMES: Record<ChessBoardPieceSymbol, string> = {
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

const DICE_FACE_NAMES: Record<ChessPieceSymbol, string> = {
  K: "король",
  Q: "ферзь",
  R: "ладья",
  B: "слон",
  N: "конь",
  P: "пешка",
};

function pieceGlyph(color: "w" | "b", piece: ChessPieceSymbol): string {
  return PIECE_GLYPHS[`${color}${piece}`];
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

function TaskNumber({ ordinal }: { ordinal: number }) {
  return <strong>№{String(ordinal).padStart(2, "0")}</strong>;
}

function openingEntries(opened: ReactNode, guide: ReactNode): ConsoleEntry[] {
  return [
    { id: 1, author: "system", content: opened },
    { id: 2, author: "system", content: guide },
  ];
}

function initialEntries(task: ParticipantTask): ConsoleEntry[] {
  const kind = task.publicState.kind;
  const number = <TaskNumber ordinal={task.ordinal} />;

  if (kind === "chess_coverage") {
    return openingEntries(
      <>Открыта шахматная расстановка {number}.</>,
      "Выберите фигуру в палитре и ставьте её на свободные клетки. Покройте все цели с минимальной стоимостью.",
    );
  }
  if (
    kind === "machine_panel" ||
    (kind === "chess" && task.family === "machine_reach")
  ) {
    return openingEntries(
      <>
        Открыта машина {number}. Переведите текущее состояние в целевое.
      </>,
      <>
        Применяйте операции командой <code>/op &lt;id&gt;</code>, отменяйте
        последний шаг через <code>/undo</code>. Итог: <code>done</code> или{" "}
        <code>impossible</code>.
      </>,
    );
  }
  if (kind === "hidden_wiring") {
    return openingEntries(
      <>
        Открыта панель {number}. Проводка скрыта. Кнопки срабатывают только
        парами.
      </>,
      <>
        Нажимайте комбинации из двух кнопок командой <code>/op b1+b2</code>{" "}
        или кнопками на панели. Первая проба обучающая и не тратит лимит.
      </>,
    );
  }

  const opened = <>Открыта задача {number}.</>;
  if (kind === "grid_zendo") {
    return openingEntries(
      opened,
      <>
        Нарисуйте узор на пустой сетке и проверьте его кнопкой или командой{" "}
        <code>/test</code>, затем отправьте итоговый ответ.
      </>,
    );
  }
  if (
    kind === "token_zendo" ||
    kind === "point_zendo" ||
    (kind === "geometry_atlas" && task.family === "geo_zendo")
  ) {
    return openingEntries(
      opened,
      <>
        Можно проверить доступную карточку командой{" "}
        <code>/test &lt;код&gt;</code>, затем отправить итоговый ответ.
      </>,
    );
  }
  return openingEntries(
    opened,
    <>
      Введите <code>/help</code>, чтобы увидеть доступные команды.
    </>,
  );
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
  const state = task.publicState;
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
  const canAct = task.status === "active" && !isBusy;
  const diceChess =
    state.kind === "dice_chess_position_probability" ||
    state.kind === "dice_chess_board_inventory_probability"
      ? state
      : null;
  const classicMath =
    state.kind === "classic_math_free_response" ? state : null;
  const isZendo =
    (state.kind === "geometry_atlas" && task.family === "geo_zendo") ||
    state.kind === "token_zendo" ||
    state.kind === "point_zendo" ||
    state.kind === "grid_zendo";
  const isMachine =
    state.kind === "machine_panel" ||
    (state.kind === "chess" && task.family === "machine_reach");
  const isWiring = state.kind === "hidden_wiring";
  const isChessCoverage = state.kind === "chess_coverage";
  const chessCoverageHasPlacement =
    state.kind === "chess_coverage" && state.placements.length > 0;
  const rawStatementPrompt = diceChess
    ? state.prompt.replace(
        /\s*Найдите вероятность описанного события\.\s*$/u,
        "",
      )
    : state.prompt;
  const statementPrompt = task.family === "geo_zendo"
    ? rawStatementPrompt
        .replaceAll("Конструкции", "Графы")
        .replaceAll("конструкции", "графы")
        .replaceAll("конструкций", "графов")
    : rawStatementPrompt;
  const statementQuestion = diceChess
    ? `Найдите вероятность того, что ${diceChess.eventDescription
        .charAt(0)
        .toLocaleLowerCase("ru-RU")}${diceChess.eventDescription.slice(1)}`
    : undefined;
  const statementParagraphs = statementPrompt
    .split(/\n{2,}/u)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  const zendoContent: Record<string, unknown> =
    "content" in state ? state.content : {};
  const zendoProbesRemaining =
    typeof zendoContent.probes_remaining === "number"
      ? zendoContent.probes_remaining
      : undefined;
  const zendoTargetCount = Array.isArray(zendoContent.targets)
    ? zendoContent.targets.length
    : 0;
  const zendoAnswerExample = `/answer ${Array.from(
    { length: Math.max(1, zendoTargetCount) },
    (_, index) => (index % 2 === 0 ? "1" : "0"),
  ).join(" ")}`;
  const transformOptions = Array.isArray(zendoContent.answer_cards)
    ? zendoContent.answer_cards.flatMap((option: unknown) =>
        isRecord(option) && "id" in option
          ? [
              {
                id: String(option.id),
                label: String("label" in option ? option.label : option.id),
              },
            ]
          : [],
      )
    : [];
  const briefMetaLines: string[] = [];
  if (isZendo && zendoProbesRemaining !== undefined) {
    briefMetaLines.push(`Осталось проб: ${zendoProbesRemaining}`);
  }
  if (state.kind === "hidden_wiring") {
    briefMetaLines.push(
      `Доступно проб: ${state.chordsRemaining} / ${state.chordBudget}`,
    );
    if (state.examChords && state.examChords.length > 0) {
      briefMetaLines.push(
        "экзаменационные комбинации (недоступны для проб): " +
          state.examChords.map((chord) => chord.id).join(", "),
      );
    }
  }
  if (state.kind === "machine_panel") {
    briefMetaLines.push(`Шагов: ${state.stepsTaken} / ${state.stepsSoftCap}`);
  }
  if (state.kind === "chess") {
    briefMetaLines.push(
      `Фигура: (${state.current.row + 1}, ${state.current.col + 1})`,
      `Цель: (${state.target.row + 1}, ${state.target.col + 1})`,
      `Шагов: ${state.stepsTaken} / ${state.stepsSoftCap}`,
    );
  }
  if (state.kind === "chess_coverage") {
    briefMetaLines.push(
      `Выбрано фигур: ${state.placements.length}`,
      `Текущая стоимость: ${state.totalCost}`,
    );
  }
  if (state.kind === "fold_punch") {
    briefMetaLines.push(
      "сгибы выполняются по порядку; дырки пробиты через все слои сразу",
    );
  }
  if (state.kind === "grid_zendo") {
    briefMetaLines.push("узор проверяется целиком");
  }
  if (state.kind === "token_zendo") {
    briefMetaLines.push("цвет и число каждой фишки видны на полке");
  }
  if (state.kind === "geometry_atlas" || state.kind === "point_zendo") {
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
          <TaskNumber ordinal={transition.ordinal} />
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
            <TaskNumber ordinal={transition.ordinal} />
            .
          </>
        ) : (
          "Ответ зафиксирован. Для продолжения используйте /next."
        )),
    );
  }

  function reportClosedTask(): boolean {
    if (task.status === "active") return false;
    appendEntry("system", "Текущая задача уже закрыта. Используйте /next.");
    return true;
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
          if (reportClosedTask()) break;
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
          if (reportClosedTask()) break;
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
          if (reportClosedTask()) break;
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
          if (reportClosedTask()) break;
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
          if (reportClosedTask()) break;
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
          if (reportClosedTask()) break;
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
          if (reportClosedTask()) break;
          if (!payload) {
            appendEntry(
              "system",
              <>
                После команды нужен текст ответа. Например:{" "}
                <code>
                  {isMachine || isChessCoverage
                    ? "/answer done"
                    : diceChess
                      ? "/answer 5/12"
                      : classicMath
                        ? "/answer <развёрнутое решение>"
                        : "/answer <ваш ответ>"}
                </code>
                .
              </>,
            );
            break;
          }
          await submitFinalAnswer(payload);
          break;

        case "/skip":
          if (reportClosedTask()) break;
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
                    <TaskNumber ordinal={transition.ordinal} />
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
                  <TaskNumber ordinal={transition.ordinal} />
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
            if (reportClosedTask()) break;
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
            classicMath ? " participant-task__stage--text-only" : ""
          }`}
          ref={stageRef}
        >
          <article
            className={`participant-brief${
              classicMath ? " participant-brief--classic" : ""
            }`}
            data-tour="task-statement"
          >
            <div className="participant-brief__statement">
              {classicMath && <h2>{classicMath.title}</h2>}
              {statementParagraphs.map((paragraph, index) => (
                <p key={`${task.id}-paragraph-${index}`}>{paragraph}</p>
              ))}
              {statementQuestion && <p>{statementQuestion}</p>}
              {classicMath?.table && (
                <div className="classic-math-table-wrap">
                  <table className="classic-math-table">
                    <thead>
                      <tr>
                        {classicMath.table.columns.map((column) => (
                          <th key={column} scope="col">
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {classicMath.table.rows.map((row, rowIndex) => (
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
              {!(
                state.kind === "hidden_wiring" &&
                state.variant === "reach_target"
              ) && (
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
                  ) : state.kind === "fold_punch" ? (
                    <>
                      Кликните клетки на развёрнутом листе и нажмите «Отправить
                      отмеченные клетки», или отправьте ответ в чате (пример:{" "}
                      <code>/answer 2,3 5,8</code> — строка,столбец).
                    </>
                  ) : classicMath ? (
                    <>
                      Ответ отправьте в чате одной командой по шаблону:
                      <code className="classic-math-submission-template">
                        {classicMath.submissionTemplate.replace(
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
                  ) : state.kind === "grid_zendo" ? (
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
                      disabled={!canAct}
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

          <TaskScene
            task={task}
            canAct={canAct}
            onCommand={(command) => void runCommand(command)}
            key={task.id}
          />
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
              {isChessCoverage && (
                <button
                  type="button"
                  disabled={isBusy || !chessCoverageHasPlacement}
                  aria-label="Сбросить шахматную расстановку"
                  onClick={() => void runCommand("/reset")}
                >
                  Сбросить
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
              title={state.responseHint}
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

function TaskScene({
  task,
  canAct,
  onCommand,
}: {
  task: ParticipantTask;
  canAct: boolean;
  onCommand: (command: string) => void;
}) {
  const state = task.publicState;
  switch (state.kind) {
    case "fold_punch":
      return (
        <FoldPunchScene
          state={state}
          canAnswer={canAct}
          onSubmit={(cells) => onCommand(`/answer ${cells}`)}
        />
      );
    case "hidden_wiring":
      return (
        <WiringPanelScene
          state={state}
          canAct={canAct}
          onChord={(opId) => onCommand(`/op ${opId}`)}
        />
      );
    case "machine_panel":
      return (
        <MachinePanel
          state={state}
          canAct={canAct}
          onOp={(opId) => onCommand(`/op ${opId}`)}
          onReset={() => onCommand("/reset")}
        />
      );
    case "chess_coverage":
      return (
        <ChessCoverageScene
          state={state}
          canAct={canAct}
          onAction={(action) => onCommand(`/op ${action}`)}
          onReset={() => onCommand("/reset")}
          onSubmit={() => onCommand("/answer done")}
        />
      );
    case "chess":
      return (
        <LeaperBoardScene
          state={state}
          canAct={canAct}
          onOp={(opId) => onCommand(`/op ${opId}`)}
        />
      );
    case "token_zendo":
      return (
        <TokenShelfScene
          cards={state.cards}
          content={state.content}
          canProbe={canAct}
          onProbe={(cardId) => onCommand(`/test ${cardId}`)}
        />
      );
    case "grid_zendo":
      return (
        <GridZendoScene
          cards={state.cards}
          content={state.content}
          canProbe={canAct}
          onProbe={(pattern) => onCommand(`/test ${pattern}`)}
        />
      );
    case "geometry_atlas":
    case "point_zendo":
      return (
        <GeometryAtlasScene
          scene={state.scene}
          content={state.content}
          showGrid={state.kind === "point_zendo"}
          canProbe={
            canAct &&
            (state.kind === "point_zendo" || task.family === "geo_zendo")
          }
          onProbe={(cardId) => onCommand(`/test ${cardId}`)}
        />
      );
    case "dice_chess_position_probability":
      return (
        <DicePositionScene
          board={state.board}
          die={state.die}
          sideToMove={state.sideToMove}
        />
      );
    case "dice_chess_board_inventory_probability":
      return <DicePositionScene board={state.board} die={state.die} />;
    case "classic_math_free_response":
      return null;
  }
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

function contentList(content: Record<string, unknown>, key: string): unknown[] {
  const items = content[key];
  return Array.isArray(items) ? items : [];
}

function isCard(item: unknown, cardId: string): item is Record<string, unknown> {
  return isRecord(item) && item.card_id === cardId;
}

function findCard(
  content: Record<string, unknown>,
  key: string,
  cardId: string,
): Record<string, unknown> | undefined {
  return contentList(content, key).find((item) => isCard(item, cardId));
}

function classificationLabel(card: Record<string, unknown>): string {
  return card.classification === "positive" ? "подходит" : "не подходит";
}

function cardOutcome(
  cardId: string,
  content: Record<string, unknown>,
): "positive" | "negative" | null {
  for (const key of ["examples", "probe_observations"]) {
    const card = findCard(content, key, cardId);
    if (card && "classification" in card) {
      return card.classification === "positive" ? "positive" : "negative";
    }
  }
  return null;
}

function cardRole(cardId: string, content: Record<string, unknown>): string {
  if (cardId === "source" || cardId === "image") return cardId;
  if (findCard(content, "examples", cardId)) return "example";
  if (findCard(content, "targets", cardId)) return "target";
  // Вскрытая проба ведёт себя как открытая конструкция-пример.
  if (findCard(content, "probe_observations", cardId)) return "example";
  if (findCard(content, "probe_cards", cardId)) return "probe";
  return "plain";
}

function cardLabel(cardId: string, content: Record<string, unknown>): string {
  if (cardId === "source") return "Исходная фигура";
  if (cardId === "image") return "Образ";
  const example = findCard(content, "examples", cardId);
  if (example && "classification" in example) {
    return `${cardId} · ${classificationLabel(example)}`;
  }
  const targetIndex = contentList(content, "targets").findIndex((item) =>
    isCard(item, cardId),
  );
  if (targetIndex >= 0) return `${cardId} · цель ${targetIndex + 1}`;
  if (findCard(content, "probe_cards", cardId)) {
    const observed = findCard(content, "probe_observations", cardId);
    return observed && "classification" in observed
      ? `${cardId} · ${classificationLabel(observed)}`
      : `${cardId} · доступна проба`;
  }
  return cardId.replaceAll("_", " ");
}

function ZendoCard({
  className,
  probeableClassName = "",
  cardId,
  content,
  canProbe = false,
  onProbe,
  children,
}: {
  className: string;
  probeableClassName?: string;
  cardId: string;
  content: Record<string, unknown>;
  canProbe?: boolean;
  onProbe?: (cardId: string) => void;
  children: ReactNode;
}) {
  const role = cardRole(cardId, content);
  const probe =
    role === "probe" && canProbe && onProbe ? () => onProbe(cardId) : undefined;
  return (
    <section
      className={probe ? `${className} ${probeableClassName}` : className}
      data-role={role}
      data-outcome={cardOutcome(cardId, content) ?? undefined}
      data-tour={
        role === "probe"
          ? "probe-card"
          : role === "target"
            ? "targets"
            : undefined
      }
      role={probe ? "button" : undefined}
      tabIndex={probe ? 0 : undefined}
      onClick={probe}
      onKeyDown={
        probe
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                probe();
              }
            }
          : undefined
      }
    >
      <header>
        {cardLabel(cardId, content)}
        {probe && <span aria-hidden="true"> · нажми, чтобы проверить</span>}
      </header>
      {children}
    </section>
  );
}

function GeometryAtlasScene({
  scene,
  content,
  showGrid,
  canProbe,
  onProbe,
}: {
  scene: GeometryScene;
  content: Record<string, unknown>;
  showGrid: boolean;
  canProbe: boolean;
  onProbe: (cardId: string) => void;
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
          return (
            <ZendoCard
              className="geometry-card"
              probeableClassName="geometry-card--probeable"
              cardId={group}
              content={content}
              canProbe={canProbe}
              onProbe={onProbe}
              key={group}
            >
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
            </ZendoCard>
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
  canProbe,
  onProbe,
}: {
  cards: Record<string, TokenCard[]>;
  content: Record<string, unknown>;
  canProbe: boolean;
  onProbe: (cardId: string) => void;
}) {
  return (
    <figure className="token-shelf" aria-label="Полки с фишками">
      <div className="token-shelf__cards">
        {Object.entries(cards).map(([cardId, tokens]) => (
          <ZendoCard
            className="token-card"
            probeableClassName="token-card--probeable"
            cardId={cardId}
            content={content}
            canProbe={canProbe}
            onProbe={onProbe}
            key={cardId}
          >
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
          </ZendoCard>
        ))}
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
          <ZendoCard
            className="grid-card"
            cardId={cardId}
            content={content}
            key={cardId}
          >
            <GridPatternPreview rows={rows} />
          </ZendoCard>
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
            if (!isRecord(item) || !Array.isArray(item.pattern)) return [];
            return [
              <section className="grid-card" key={index}>
                <header>
                  Проба {index + 1}: {classificationLabel(item)}
                </header>
                <GridPatternPreview rows={item.pattern} />
              </section>,
            ];
          })}
        </div>
      )}
    </figure>
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
        <MachineStateDisplay
          label="Сейчас"
          state={{ lamps: state.current }}
          current
        />
        {state.target && (
          <MachineStateDisplay label="Цель" state={{ lamps: state.target }} />
        )}
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

function DicePositionScene({
  board,
  die,
  sideToMove = "white",
}: {
  board: ChessBoardState;
  die: DiceDefinition;
  sideToMove?: "white" | "black";
}) {
  return (
    <div className="dice-position-scene">
      <Chessboard board={board} />

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
                {pieceGlyph(sideToMove === "black" ? "b" : "w", face)}
              </span>
              <small>{DICE_FACE_NAMES[face]}</small>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function ChessCoverageScene({
  state,
  canAct,
  onAction,
  onReset,
  onSubmit,
}: {
  state: ChessCoveragePublicState;
  canAct: boolean;
  onAction: (action: string) => void;
  onReset: () => void;
  onSubmit: () => void;
}) {
  const [activePiece, setActivePiece] = useState(state.pieceTypes[0].id);
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
                  {pieceGlyph("w", piece.id)}
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
              <strong>{pieceGlyph("w", activeDefinition.id)} {activeDefinition.label}</strong>
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
              activeDefinition &&
              !target &&
              !placement &&
              !placementLimitReached &&
              (state.pieceCounts[activeDefinition.id] ?? 0) < activeDefinition.limit,
            );
            const canRemove = canAct && Boolean(placement);
            return (
              <button
                type="button"
                role="gridcell"
                className={[
                  "coverage-placement-board__cell",
                  (row + col) % 2 ? "is-dark" : "",
                  target ? "is-target" : "",
                  isCovered ? "is-covered" : "",
                ].filter(Boolean).join(" ")}
                disabled={!canPlace && !canRemove}
                aria-label={
                  placement
                    ? `${placement.id}, ${placement.piece}, клетка ${String.fromCharCode(65 + col)}${row + 1}, стоимость ${placement.cost}. Нажмите, чтобы убрать.`
                    : `Клетка ${String.fromCharCode(65 + col)}${row + 1}${target ? ", цель" : ""}`
                }
                onClick={() => {
                  if (placement) {
                    onAction(`remove:${placement.id}`);
                  } else if (canPlace && activeDefinition) {
                    onAction(`place:${activeDefinition.id}:${row}:${col}`);
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
                      {pieceGlyph("w", placement.piece)}
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
              disabled={!canAct || state.placements.length === 0}
              onClick={onReset}
            >
              Вернуть в начало
            </button>
            <button
              type="button"
              className="is-primary"
              disabled={!canAct || !state.allCovered}
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

function MovePattern({ piece }: { piece: ChessCoveragePieceType }) {
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
  canAct,
  onOp,
  onReset,
}: {
  state: MachinePanelPublicState;
  canAct: boolean;
  onOp: (opId: string) => void;
  onReset: () => void;
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
              disabled={!canAct}
              onClick={() => onOp(operation.id)}
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
          disabled={!canAct}
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
  canAct,
  onOp,
}: {
  state: LeaperBoardPublicState;
  canAct: boolean;
  onOp: (opId: string) => void;
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
              disabled={!canAct}
              onClick={() => onOp(operation.id)}
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

function Chessboard({ board }: { board: ChessBoardState }) {
  const rowCount = board.length;
  const colCount = Math.max(1, ...board.map((rank) => rank.length));

  return (
    <div className="chess-position chess-position--compact">
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

            return (
              <div
                className={`chess-square${isDark ? " chess-square--dark" : ""}`}
                role="gridcell"
                aria-label={`${coordinate}: ${piece ? PIECE_NAMES[piece] : "пусто"}`}
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
