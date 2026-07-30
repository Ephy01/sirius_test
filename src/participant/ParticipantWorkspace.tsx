import {
  type FormEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  CountersPublicState,
  LeaperBoardPublicState,
  MachinePanelPublicState,
  MachineState,
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
export type PenultimaObservation = {
  from: string;
  to: string;
  accepted: boolean;
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
  points: readonly GeometryPoint[];
  edges: readonly GeometryEdge[];
};

export type ParticipantTask = {
  id: string;
  ordinal: number;
  family: "chess960" | "dice_chess" | "penultima" | (string & {});
  kind:
    | "chess960_validation"
    | "chess960_mission"
    | "dice_chess_probability"
    | "dice_chess_board_inventory_probability"
    | "dice_chess_position_probability"
    | "penultima_induction"
    | (string & {});
  difficulty: number;
  status: "active" | "answered" | "skipped";
  prompt: string;
  board?: ChessBoard;
  backRank?: readonly ChessPieceKind[];
  variant?: string;
  dice?: ChessDiceSet;
  sampleSpaceSize?: number;
  eventDescription?: string;
  sideToMove?: "white" | "black";
  pieceName?: string;
  currentSquare?: string;
  goalSquare?: string;
  chapterStage?: number;
  stageTitle?: string;
  acceptedMoves?: number;
  rejectedMoves?: number;
  observations?: readonly PenultimaObservation[];
  geometryScene?: GeometryScene;
  geometryContent?: Record<string, unknown>;
  geometryInteraction?: Record<string, unknown>;
  machinePanel?: MachinePanelPublicState;
  leaperBoard?: LeaperBoardPublicState;
  counters?: CountersPublicState;
  responseHint?: string;
  worldPhase?: string;
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

export type ParticipantWorkspaceProps = {
  task: ParticipantTask;
  deadlineAt?: string | null;
  contestTitle: string;
  participantName?: string;
  totalTasks?: number;
  busy?: boolean;
  error?: string;
  onAnswer: (answer: string) => Promise<TaskTransitionResult>;
  onSkip: () => Promise<TaskTransitionResult>;
  onNext: () => Promise<TaskTransitionResult>;
  onMove?: (
    move: string,
    clientActionId: string,
  ) => Promise<TaskMoveTransitionResult>;
  onProbe?: (
    probe: string,
    clientActionId: string,
  ) => Promise<TaskMoveTransitionResult>;
  onApplyOperation?: (
    opId: string,
    clientActionId: string,
  ) => Promise<TaskMoveTransitionResult>;
  onUndo?: (clientActionId: string) => Promise<TaskMoveTransitionResult>;
  onMessage?: (message: string) => Promise<unknown> | unknown;
};

type ConsoleEntry = {
  id: number;
  author: "system" | "participant";
  content: ReactNode;
};

const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"] as const;
const DEFAULT_BACK_RANK: readonly ChessPieceKind[] = [
  "B",
  "R",
  "N",
  "Q",
  "K",
  "N",
  "R",
  "B",
];

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

function createStartingBoard(
  requestedBackRank?: readonly ChessPieceKind[],
): ChessBoardCell[][] {
  const backRank =
    requestedBackRank?.length === 8 ? requestedBackRank : DEFAULT_BACK_RANK;
  const emptyRank = () => Array<ChessBoardCell>(8).fill(null);

  return [
    backRank.map((piece) => `b${piece}` as ChessPieceCode),
    Array<ChessBoardCell>(8).fill("bP"),
    emptyRank(),
    emptyRank(),
    emptyRank(),
    emptyRank(),
    Array<ChessBoardCell>(8).fill("wP"),
    backRank.map((piece) => `w${piece}` as ChessPieceCode),
  ];
}

function normalizeBoard(task: ParticipantTask): ChessBoardCell[][] {
  if (!task.board) return createStartingBoard(task.backRank);

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

function initialEntries(task: ParticipantTask): ConsoleEntry[] {
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
  if (task.kind === "counters" || task.family === "nim_like") {
    return [
      {
        id: 1,
        author: "system",
        content: (
          <>
            Открыта позиция{" "}
            <strong>№{String(task.ordinal).padStart(2, "0")}</strong>.
            Найдите один решающий ход.
          </>
        ),
      },
      {
        id: 2,
        author: "system",
        content: (
          <>
            Ответьте <code>take &lt;куча&gt; &lt;число&gt;</code> или{" "}
            <code>проигрышная</code>.
          </>
        ),
      },
    ];
  }
  if (task.kind === "penultima_induction") {
    return [
      {
        id: 1,
        author: "system",
        content: (
          <>
            Открыта цель{" "}
            <strong>№{String(task.ordinal).padStart(2, "0")}</strong>.
            Правило движения фигуры «{task.pieceName ?? "Комета"}» скрыто,
            но не изменится внутри главы.
          </>
        ),
      },
      {
        id: 2,
        author: "system",
        content: (
          <>
            Предлагайте ходы командой <code>/move c2 d3</code>. Арбитр
            сообщит, разрешён ход или нет.
          </>
        ),
      },
    ];
  }
  if (task.kind === "geometry_atlas") {
    return [
      {
        id: 1,
        author: "system",
        content: (
          <>
            Открыта задача{" "}
            <strong>№{String(task.ordinal).padStart(2, "0")}</strong>{" "}
            Геометрического мира.
          </>
        ),
      },
      {
        id: 2,
        author: "system",
        content:
          task.family === "geo_zendo" ? (
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
  deadlineAt,
  contestTitle,
  participantName,
  totalTasks,
  busy = false,
  error = "",
  onAnswer,
  onSkip,
  onNext,
  onMove,
  onProbe,
  onApplyOperation,
  onUndo,
  onMessage,
}: ParticipantWorkspaceProps) {
  const board = useMemo(() => normalizeBoard(task), [task]);
  const dice = useMemo(() => normalizeDice(task), [task]);
  const [draft, setDraft] = useState("");
  const [entries, setEntries] = useState<ConsoleEntry[]>(() =>
    initialEntries(task),
  );
  const [commandBusy, setCommandBusy] = useState(false);
  const [remainingTime, setRemainingTime] = useState(() =>
    formatRemainingTime(deadlineAt),
  );
  const entryId = useRef(3);
  const activeTaskId = useRef(task.id);
  const inFlight = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const consoleLogRef = useRef<HTMLDivElement>(null);

  const timeIsUp = Boolean(deadlineAt) && remainingTime === "00:00";
  const isBusy = busy || commandBusy || timeIsUp;
  const isDiceChess = task.family === "dice_chess";
  const isDicePosition =
    task.kind === "dice_chess_position_probability" ||
    task.kind === "dice_chess_board_inventory_probability";
  const isPenultima = task.kind === "penultima_induction";
  const isGeometry = task.kind === "geometry_atlas";
  const isZendo = isGeometry && task.family === "geo_zendo";
  const isMachine =
    task.kind === "machine_panel" ||
    (task.kind === "chess" && task.family === "machine_reach");
  const isLeaperBoard = task.kind === "chess" && Boolean(task.leaperBoard);
  const isCounters = task.kind === "counters" || task.family === "nim_like";
  const worldPhaseLabel =
    task.worldPhase === "calibration"
      ? "знакомство со средой"
      : task.worldPhase === "chapter"
        ? "связная глава"
        : task.worldPhase === "remediation"
          ? "закрепление"
          : task.worldPhase === "rotation"
            ? "адаптивный маршрут"
            : "";
  const statementPrompt = isDiceChess
    ? task.prompt.replace(
        /\s*Найдите вероятность описанного события\.\s*$/u,
        "",
      )
    : task.prompt;
  const statementQuestion =
    isDiceChess && task.eventDescription
      ? `Найдите вероятность того, что ${task.eventDescription
          .charAt(0)
          .toLocaleLowerCase("ru-RU")}${task.eventDescription.slice(1)}`
      : task.eventDescription;

  useEffect(() => {
    const updateTimer = () => setRemainingTime(formatRemainingTime(deadlineAt));
    updateTimer();
    const interval = window.setInterval(updateTimer, 1000);
    return () => window.clearInterval(interval);
  }, [deadlineAt]);

  useEffect(() => {
    if (activeTaskId.current === task.id) return;
    activeTaskId.current = task.id;
    setDraft("");
  }, [task.id]);

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

  async function submitPenultimaMove(move: string) {
    if (!onMove) {
      appendEntry("system", "Игровой арбитр сейчас недоступен.");
      return;
    }
    const transition = await onMove(move, createClientActionId());
    appendEntry(
      "system",
      transition.message ??
        (transition.accepted
          ? "Арбитр: ход принят. Позиция обновлена."
          : "Арбитр: ход невозможен. Позиция не изменилась."),
    );
  }

  async function submitZendoProbe(probe: string) {
    if (!onProbe) {
      appendEntry("system", "Оракул сейчас недоступен.");
      return;
    }
    const transition = await onProbe(probe, createClientActionId());
    appendEntry(
      "system",
      transition.message ??
        (transition.accepted
          ? "Оракул классифицировал конфигурацию."
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
      transition.message ??
        (transition.accepted
          ? `Операция ${opId} применена.`
          : `Операцию ${opId} применить нельзя.`),
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

    inFlight.current = true;
    setDraft("");
    appendEntry("participant", input);
    setCommandBusy(true);

    const [command = "", ...parts] = input.split(/\s+/);
    const payload = input.slice(command.length).trim();

    try {
      switch (command.toLowerCase()) {
        case "/help":
          appendEntry(
            "system",
            isPenultima ? (
              <>
                <code>/move c2 d3</code> — предложить ход арбитру
                <br />
                <code>/history</code> — показать последние пробы в главе
                <br />
                <code>/skip</code> — пропустить текущую цель
                <br />
                Координаты можно отправить и без слова <code>/move</code>.
              </>
            ) : isMachine ? (
              <>
                <code>/op &lt;id&gt;</code> — применить указанную операцию
                <br />
                <code>/undo</code> — отменить последнюю операцию
                <br />
                <code>done</code> — зафиксировать достигнутую цель
                <br />
                <code>impossible</code> — заявить, что цель недостижима
              </>
            ) : isCounters ? (
              <>
                <code>take &lt;куча&gt; &lt;число&gt;</code> — сделать
                решающий ход
                <br />
                <code>проигрышная</code> — отметить позицию без выигрышного хода
                <br />
                <code>/skip</code> — пропустить текущую позицию
              </>
            ) : isZendo ? (
              <>
                <code>/test &lt;код&gt;</code> — проверить одну из карточек-проб
                <br />
                <code>/answer &lt;ответ&gt;</code> — классифицировать целевые
                конфигурации
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
              "Команда /test доступна только в задачах Геометрического Zendo.",
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

        case "/op":
          if (!isMachine) {
            appendEntry(
              "system",
              "Команда /op доступна только в задачах с машиной.",
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
          if (isPenultima) {
            appendEntry(
              "system",
              <>
                В Penultima нет отдельного ответа. Двигайте фигуру командой{" "}
                <code>/move c2 d3</code>; цель завершится автоматически.
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
          if (!payload) {
            appendEntry(
              "system",
              <>
                После команды нужен текст ответа. Например:{" "}
                <code>
                  {isMachine
                    ? "/answer done"
                    : isCounters
                      ? "/answer take 1 2"
                      : isDiceChess
                      ? "/answer 5/12"
                      : task.variant === "single_swap_repair"
                        ? "/answer a1 b1"
                        : task.variant === "repair_count"
                          ? "/answer 3"
                          : "/answer да, допустима"}
                </code>
                .
              </>,
            );
            break;
          }
          await submitFinalAnswer(payload);
          break;

        case "/move":
          if (!isPenultima) {
            appendEntry(
              "system",
              "Команда /move доступна только в среде Penultima.",
            );
            break;
          }
          if (task.status !== "active") {
            appendEntry(
              "system",
              "Текущая цель уже закрыта. Используйте /next.",
            );
            break;
          }
          if (!payload) {
            appendEntry(
              "system",
              <>
                Укажите исходное и целевое поля. Например:{" "}
                <code>/move c2 d3</code>.
              </>,
            );
            break;
          }
          await submitPenultimaMove(payload);
          break;

        case "/history":
          if (!isPenultima) {
            appendEntry(
              "system",
              "История проб доступна только в среде Penultima.",
            );
            break;
          }
          if (!task.observations?.length) {
            appendEntry("system", "В этой главе ещё не было проб.");
            break;
          }
          appendEntry(
            "system",
            <>
              {task.observations.map((observation, index) => (
                <span key={`${observation.from}-${observation.to}-${index}`}>
                  {observation.from} → {observation.to}:{" "}
                  {observation.accepted ? "разрешено" : "запрещено"}
                  {index < (task.observations?.length ?? 0) - 1 && <br />}
                </span>
              ))}
            </>,
          );
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
            isPenultima &&
            /^[a-h][1-8](?:\s+|[-–—]|→)?[a-h][1-8]$/iu.test(input)
          ) {
            await submitPenultimaMove(input);
            break;
          }

          if (
            isMachine &&
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

          if (
            isCounters &&
            (/^take\s+\S+\s+\d+$/iu.test(input) ||
              /^(?:проигрышная|losing)$/iu.test(input))
          ) {
            if (task.status !== "active") {
              appendEntry(
                "system",
                "Текущая позиция уже закрыта. Используйте /next.",
              );
              break;
            }
            await submitFinalAnswer(input);
            break;
          }

          if (onMessage) {
            await onMessage(input);
            appendEntry("system", "Сообщение принято.");
          } else {
            appendEntry(
              "system",
              isPenultima ? (
                <>
                  Чтобы предложить ход, введите{" "}
                  <code>/move c2 d3</code>.
                </>
              ) : (
                <>
                  Чтобы сохранить решение, начните сообщение с{" "}
                  <code>/answer</code>.
                </>
              ),
            );
          }
      }
    } catch {
      // The parent exposes the concrete API error through the connection entry.
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
    >
      <section className="participant-task" aria-labelledby="participantTaskTitle">
        <header className="participant-task__header">
          <p>
            {contestTitle}
            {worldPhaseLabel && <small> · {worldPhaseLabel}</small>}
          </p>
          <span>
            {task.ordinal}
            {totalTasks ? ` / ${totalTasks}` : ""}
          </span>
        </header>

        <div className="participant-task__stage">
          <article className="participant-brief">
            <h1 id="participantTaskTitle">
              {isPenultima ? "Цель" : "Задача"} {task.ordinal}
            </h1>
            <div className="participant-brief__statement">
              <p>{statementPrompt}</p>
              {statementQuestion && <p>{statementQuestion}</p>}
            </div>
            <p className="participant-brief__answer">
              {isPenultima ? (
                <>
                  Предлагайте ходы в чате командой{" "}
                  <code>/move c2 d3</code>.
                </>
              ) : isMachine ? (
                <>
                  Управляйте средой через <code>/op &lt;id&gt;</code> и{" "}
                  <code>/undo</code>. Когда решение найдено, отправьте{" "}
                  <code>done</code> или <code>impossible</code>.
                </>
              ) : isCounters ? (
                <>
                  Отправьте <code>take &lt;куча&gt; &lt;число&gt;</code> или{" "}
                  <code>проигрышная</code>.
                </>
              ) : isZendo ? (
                <>
                  Проверяйте карточки командой <code>/test &lt;код&gt;</code>,
                  итог отправьте через <code>/answer</code>.
                </>
              ) : (
                <>
                  Ответ введите в чате командой{" "}
                  <code>/answer &lt;ваш ответ&gt;</code>.
                </>
              )}
            </p>
          </article>

          {isPenultima ? (
            <PenultimaScene
              board={board}
              pieceName={task.pieceName ?? "Комета"}
              currentSquare={task.currentSquare}
              goalSquare={task.goalSquare}
              chapterStage={task.chapterStage ?? 1}
              stageTitle={task.stageTitle ?? "Маршрут"}
              acceptedMoves={task.acceptedMoves ?? 0}
              rejectedMoves={task.rejectedMoves ?? 0}
            />
          ) : task.machinePanel ? (
            <MachinePanel state={task.machinePanel} />
          ) : isLeaperBoard && task.leaperBoard ? (
            <LeaperBoardScene state={task.leaperBoard} />
          ) : isCounters && task.counters ? (
            <CountersScene state={task.counters} />
          ) : isGeometry && task.geometryScene ? (
            <GeometryAtlasScene
              scene={task.geometryScene}
              content={task.geometryContent ?? {}}
              family={task.family}
            />
          ) : isDicePosition ? (
            <DicePositionScene
              board={board}
              die={dice[0]}
              sideToMove={task.sideToMove}
            />
          ) : isDiceChess ? (
            <DiceScene dice={dice} />
          ) : (
            <Chessboard board={board} />
          )}
        </div>
      </section>

      <aside className="participant-console" aria-label="Чат и команды">
        <header className="participant-console__header">
          <strong>{participantName ?? "Участник"}</strong>
          <time dateTime={deadlineAt ?? undefined}>{remainingTime}</time>
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
              <span>{entry.author === "system" ? "Система" : "Вы"}</span>
              <p>{entry.content}</p>
            </article>
          ))}
          {error && (
            <article className="console-entry console-entry--error" role="alert">
              <span>Соединение</span>
              <p>{error}</p>
            </article>
          )}
        </div>

        <form className="participant-console__form" onSubmit={submitCommand}>
          <label htmlFor="participantCommand">Команда или сообщение</label>
          <div>
            <span aria-hidden="true">&gt;</span>
            <input
              ref={inputRef}
              id="participantCommand"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={
                timeIsUp
                  ? "Время попытки завершено"
                  : task.responseHint ??
                    (isPenultima ? "/move c2 d3" : "/answer ваш ответ")
              }
              autoComplete="off"
              spellCheck={false}
              disabled={isBusy}
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
  gold: "#d7a62b",
  green: "#4f9d79",
  gray: "#958b98",
};

function geometryColor(value?: string): string {
  if (!value) return GEOMETRY_COLORS.grape;
  return GEOMETRY_COLORS[value] ?? value;
}

function geometryGroupLabel(
  group: string,
  content: Record<string, unknown>,
): string {
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
  family,
}: {
  scene: GeometryScene;
  content: Record<string, unknown>;
  family: ParticipantTask["family"];
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
  const viewPadding = Math.max(width, height) * 0.09;
  const radius = Math.max(
    0.48,
    Math.min(0.72, Math.min(width, height) * 0.075),
  );
  const options = Array.isArray(content.answer_cards)
    ? content.answer_cards
    : Array.isArray(content.options)
      ? content.options
      : [];
  const remaining =
    typeof content.probes_remaining === "number"
      ? content.probes_remaining
      : typeof content.probesRemaining === "number"
        ? content.probesRemaining
        : undefined;

  return (
    <figure className="geometry-atlas" aria-label="Геометрические конфигурации">
      <div className="geometry-atlas__cards">
        {groups.map((group) => {
          const points = scene.points.filter((point) => point.group === group);
          const edges = scene.edges.filter((edge) => edge.group === group);
          return (
            <section className="geometry-card" key={group}>
              <header>{geometryGroupLabel(group, content)}</header>
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
                {edges.map((edge) => {
                  const source = pointByKey.get(`${group}:${edge.source}`);
                  const target = pointByKey.get(`${group}:${edge.target}`);
                  if (!source || !target) return null;
                  return (
                    <line
                      x1={source.x}
                      y1={source.y}
                      x2={target.x}
                      y2={target.y}
                      stroke={geometryColor(edge.color)}
                      key={edge.id}
                    />
                  );
                })}
                {points.map((point) => (
                  <g key={point.id}>
                    <circle
                      cx={point.x}
                      cy={point.y}
                      r={radius}
                      style={{ fill: geometryColor(point.color) }}
                    />
                    {point.label && (
                      <text
                        x={point.x}
                        y={point.y}
                        dominantBaseline="central"
                        textAnchor="middle"
                        style={{
                          fill:
                            point.color === "cyan" ? "#004278" : "#ffffff",
                          fontSize: `${Math.max(radius * 1.05, 0.46)}px`,
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
      {(options.length > 0 || remaining !== undefined) && (
        <figcaption>
          {options.length > 0 && (
            <span>
              Варианты:{" "}
              {options
                .map((option) =>
                  typeof option === "string"
                    ? option
                    : typeof option === "object" &&
                        option !== null &&
                        "id" in option
                      ? `${String(option.id)}${
                          "label" in option ? ` — ${String(option.label)}` : ""
                        }`
                      : "",
                )
                .filter(Boolean)
                .join(" · ")}
            </span>
          )}
          {remaining !== undefined && (
            <span>Проверок у оракула осталось: {remaining}</span>
          )}
          <span>
            {family === "geo_graph"
              ? "Рёбра задаются парами вершин"
              : "Все рисунки даны в одной системе обозначений"}
          </span>
        </figcaption>
      )}
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
                  <small>{face}</small>
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
              <small>{face}</small>
            </li>
          ))}
        </ol>
      </section>
    </div>
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

function MachinePanel({ state }: { state: MachinePanelPublicState }) {
  return (
    <figure className="machine-panel" aria-label="Пульт машины">
      <header>
        <div>
          <span>Пульт машины</span>
          <strong>
            {state.subKind === "lamps_gf2"
              ? "Лампы"
              : state.subKind === "numeric_machine"
                ? "Числовая машина"
                : "Перестановки"}
          </strong>
        </div>
        <small>
          Шагов {state.stepsTaken} / {state.stepsSoftCap}
        </small>
      </header>

      <div className="machine-panel__states">
        <MachineStateDisplay label="Старт" state={state.start} />
        <MachineStateDisplay label="Сейчас" state={state.current} current />
        <MachineStateDisplay label="Цель" state={state.target} />
      </div>

      <ol className="machine-operations" aria-label="Доступные операции">
        {state.ops.map((operation) => (
          <li key={operation.id}>
            <code>{operation.id}</code>
            <span>{operation.label}</span>
          </li>
        ))}
      </ol>

      <figcaption>
        Команда <code>/op &lt;id&gt;</code> применяет операцию к текущему
        состоянию. <code>/undo</code> отменяет один шаг.
      </figcaption>
    </figure>
  );
}

function pointToSquare(point: { row: number; col: number }): string {
  return `${FILES[point.col] ?? "?"}${point.row + 1}`;
}

function LeaperBoardScene({ state }: { state: LeaperBoardPublicState }) {
  return (
    <figure className="leaper-scene" aria-label="Доска прыгуна">
      <div className="leaper-scene__meta">
        <span>
          Сейчас <strong>{pointToSquare(state.current)}</strong>
        </span>
        <span>
          Цель <strong>{pointToSquare(state.target)}</strong>
        </span>
        <span>
          Шагов <strong>{state.stepsTaken} / {state.stepsSoftCap}</strong>
        </span>
      </div>
      <Chessboard
        board={state.board as ChessBoard}
        goalSquare={pointToSquare(state.target)}
      />
      <ol className="leaper-operations" aria-label="Разрешённые прыжки">
        {state.ops.map((operation) => (
          <li key={operation.id}>
            <code>{operation.id}</code>
            <span>{operation.label}</span>
          </li>
        ))}
      </ol>
      <figcaption>
        Белый конь — текущая позиция · чёрный король — цель · пешки —
        препятствия
      </figcaption>
    </figure>
  );
}

function readAllowedTakes(rules: Record<string, unknown>): number[] {
  const candidate =
    rules.allowed_takes ??
    rules.allowedTakes ??
    rules.take ??
    rules.takes ??
    rules.moves;
  return Array.isArray(candidate)
    ? candidate.filter(
        (take): take is number =>
          typeof take === "number" && Number.isInteger(take) && take > 0,
      )
    : [];
}

function CountersScene({ state }: { state: CountersPublicState }) {
  const globalTakes = readAllowedTakes(state.rules);
  const description =
    typeof state.rules.description === "string"
      ? state.rules.description
      : undefined;

  return (
    <figure className="counters-scene" aria-label="Позиция игры с кучами">
      <header>
        <div>
          <span>Правило окончания</span>
          <strong>
            {state.misere
              ? "Последний ход проигрывает"
              : "Последний ход выигрывает"}
          </strong>
        </div>
        {globalTakes.length > 0 && (
          <small>Можно взять: {globalTakes.join(", ")}</small>
        )}
      </header>

      <div className="counter-heaps">
        {state.heaps.map((heap) => {
          const visibleCount = Math.min(heap.count, 28);
          const allowed =
            state.rulesByHeap[heap.id] ??
            state.rulesByHeap[String(state.heaps.indexOf(heap) + 1)];
          return (
            <section className="counter-heap" key={heap.id}>
              <header>
                <div>
                  <code>{heap.id}</code>
                  <strong>{heap.label}</strong>
                </div>
                <span>{heap.count}</span>
              </header>
              <div
                className="counter-heap__tokens"
                aria-label={`${heap.label}: ${heap.count}`}
              >
                {Array.from({ length: visibleCount }, (_, index) => (
                  <i aria-hidden="true" key={index} />
                ))}
                {heap.count > visibleCount && (
                  <b>+{heap.count - visibleCount}</b>
                )}
              </div>
              {allowed && allowed.length > 0 && (
                <small>Можно взять: {allowed.join(", ")}</small>
              )}
            </section>
          );
        })}
      </div>

      <figcaption>
        {description ?? (
          <>
            Формат хода: <code>take &lt;куча&gt; &lt;число&gt;</code>
          </>
        )}
      </figcaption>
    </figure>
  );
}

function PenultimaScene({
  board,
  pieceName,
  currentSquare,
  goalSquare,
  chapterStage,
  stageTitle,
  acceptedMoves,
  rejectedMoves,
}: {
  board: ChessBoard;
  pieceName: string;
  currentSquare?: string;
  goalSquare?: string;
  chapterStage: number;
  stageTitle: string;
  acceptedMoves: number;
  rejectedMoves: number;
}) {
  return (
    <figure className="penultima-scene" aria-label="Игровая доска Penultima">
      <div className="penultima-scene__meta">
        <div>
          <span>Фигура</span>
          <strong>{pieceName}</strong>
        </div>
        <div>
          <span>Этап {chapterStage} / 3</span>
          <strong>{stageTitle}</strong>
        </div>
        <div>
          <span>Маяк</span>
          <strong>{goalSquare ?? "—"}</strong>
        </div>
      </div>

      <Chessboard board={board} goalSquare={goalSquare} />

      <figcaption>
        <span>
          Текущее поле <strong>{currentSquare ?? "—"}</strong>
        </span>
        <span>Тёмные пешки — закрытые клетки</span>
        <span>
          Принято: {acceptedMoves} · отклонено: {rejectedMoves}
        </span>
      </figcaption>
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
