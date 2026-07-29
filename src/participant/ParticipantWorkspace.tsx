import {
  type FormEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import "./participant-workspace.css";

export type ChessPieceKind = "K" | "Q" | "R" | "B" | "N";
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

export type ParticipantTask = {
  id: string;
  ordinal: number;
  family: "chess960" | "dice_chess" | "penultima" | (string & {});
  difficulty: number;
  status: "active" | "answered" | "skipped";
  prompt: string;
  board?: ChessBoard;
  backRank?: readonly ChessPieceKind[];
  responseHint?: string;
};

export type ParticipantWorkspaceProps = {
  task: ParticipantTask;
  deadlineAt?: string | null;
  contestTitle: string;
  participantName?: string;
  totalTasks?: number;
  busy?: boolean;
  error?: string;
  onAnswer: (answer: string) => Promise<unknown> | unknown;
  onSkip: () => Promise<unknown> | unknown;
  onNext: () => Promise<unknown> | unknown;
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

const FAMILY_LABELS: Record<string, string> = {
  chess960: "Chess960",
  dice_chess: "Dice & Chess",
  penultima: "Penultima",
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

  return Array.from({ length: 8 }, (_, rankIndex) =>
    Array.from(
      { length: 8 },
      (_, fileIndex) => task.board?.[rankIndex]?.[fileIndex] ?? null,
    ),
  );
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

function initialEntries(task: ParticipantTask): ConsoleEntry[] {
  return [
    {
      id: 1,
      author: "system",
      content: (
        <>
          Среда готова. Перед вами задача{" "}
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
  onMessage,
}: ParticipantWorkspaceProps) {
  const board = useMemo(() => normalizeBoard(task), [task]);
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
  const inputRef = useRef<HTMLInputElement>(null);
  const consoleLogRef = useRef<HTMLDivElement>(null);

  const timeIsUp = Boolean(deadlineAt) && remainingTime === "00:00";
  const isBusy = busy || commandBusy || timeIsUp;
  const familyLabel = FAMILY_LABELS[task.family] ?? task.family;

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
    setEntries((current) => [
      ...current,
      {
        id: entryId.current++,
        author: "system",
        content: (
          <>
            Открыта задача{" "}
            <strong>№{String(task.ordinal).padStart(2, "0")}</strong>. Условие
            обновлено слева.
          </>
        ),
      },
    ]);
  }, [task.id, task.ordinal]);

  useEffect(() => {
    const log = consoleLogRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [entries]);

  function appendEntry(author: ConsoleEntry["author"], content: ReactNode) {
    setEntries((current) => [
      ...current,
      { id: entryId.current++, author, content },
    ]);
  }

  async function runCommand(rawInput: string) {
    const input = rawInput.trim();
    if (!input || isBusy) return;

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
            <>
              <code>/answer &lt;текст&gt;</code> — зафиксировать ответ
              <br />
              <code>/skip</code> — пропустить текущую задачу
              <br />
              <code>/next</code> — перейти к следующей задаче
            </>,
          );
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
                <code>/answer c1 и f1</code>.
              </>,
            );
            break;
          }
          await onAnswer(payload);
          appendEntry(
            "system",
            "Ответ зафиксирован. Результат будет доступен организатору после контеста.",
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
          await onSkip();
          appendEntry("system", "Пропуск зафиксирован.");
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
          await onNext();
          appendEntry("system", "Запрос на следующую задачу принят.");
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

          if (onMessage) {
            await onMessage(input);
            appendEntry("system", "Сообщение принято.");
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
      appendEntry(
        "system",
        "Не удалось выполнить команду. Попробуйте ещё раз.",
      );
    } finally {
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
      data-task-difficulty={task.difficulty}
    >
      <section className="participant-task" aria-labelledby="participantTaskTitle">
        <header className="participant-task__header">
          <div>
            <p className="participant-workspace__eyebrow">{contestTitle}</p>
            <h1 id="participantTaskTitle">Шахматный мир</h1>
          </div>
          <div className="participant-task__progress">
            <span>{familyLabel}</span>
            <strong>
              {String(task.ordinal).padStart(2, "0")}
              {totalTasks ? ` / ${String(totalTasks).padStart(2, "0")}` : ""}
            </strong>
          </div>
        </header>

        <div className="participant-task__stage">
          <article className="participant-brief">
            <div>
              <span className="participant-brief__index">
                Задача {String(task.ordinal).padStart(2, "0")}
              </span>
              <span className="participant-brief__turn">
                <i />
                Проверка позиции
              </span>
            </div>
            <h2>Изучите позицию</h2>
            <p>{task.prompt}</p>
            <aside>
              Ответ отправляется в консоли командой{" "}
              <code>/answer &lt;ваш ответ&gt;</code>.
            </aside>
          </article>

          <Chessboard board={board} />
        </div>
      </section>

      <aside className="participant-console" aria-label="Чат и команды">
        <header className="participant-console__header">
          <div>
            <i />
            <span>Канал связи</span>
          </div>
          <time dateTime={deadlineAt ?? undefined}>{remainingTime}</time>
        </header>

        <div className="participant-console__identity">
          <span>Сессия участника</span>
          <strong>{participantName ?? "Персональный доступ"}</strong>
        </div>

        <div
          className="participant-console__log"
          aria-live="polite"
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
                  : task.responseHint ?? "/answer ваш ответ"
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

function Chessboard({ board }: { board: ChessBoard }) {
  return (
    <div className="chess-position">
      <div className="chess-position__meta">
        <span>Позиция Chess960</span>
        <small>Белые снизу</small>
      </div>
      <div
        className="chessboard"
        role="grid"
        aria-label="Шахматная доска, белые снизу"
      >
        {board.flatMap((rank, rankIndex) =>
          rank.map((piece, fileIndex) => {
            const rankNumber = 8 - rankIndex;
            const coordinate = `${FILES[fileIndex]}${rankNumber}`;
            const isDark = (rankIndex + fileIndex) % 2 === 1;

            return (
              <div
                className={`chess-square ${isDark ? "chess-square--dark" : ""}`}
                role="gridcell"
                aria-label={`${coordinate}: ${piece ? PIECE_NAMES[piece] : "пусто"}`}
                key={coordinate}
              >
                {fileIndex === 0 && (
                  <span className="chess-square__rank" aria-hidden="true">
                    {rankNumber}
                  </span>
                )}
                {rankIndex === 7 && (
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
      <div className="chess-position__caption">
        <span>
          <i className="chess-position__marker" /> Исходная позиция
        </span>
        <span>Расстановка создана для этой попытки</span>
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
