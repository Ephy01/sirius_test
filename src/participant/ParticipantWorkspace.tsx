import {
  type ClipboardEvent,
  type FormEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";
import type {
  AiTurnHistory,
  ParticipantTask,
  ParticipantTelemetryEvent,
  TaskProgressEntry,
} from "../api";
import { TaskScene } from "../tasks/registry";
import { runTaskCommand, type TaskCommandHandlers } from "./commands";
import { initialEntries, type ConsoleEntry } from "./consoleEntries";
import { TaskBrief } from "./TaskBrief";
import { taskTraits } from "./taskTraits";
import { useTelemetryQueue } from "./telemetry";
import "./participant-workspace.css";

type ParticipantWorkspaceProps = TaskCommandHandlers & {
  task: ParticipantTask;
  attemptId?: string;
  deadlineAt?: string | null;
  taskProgress?: readonly TaskProgressEntry[];
  busy?: boolean;
  error?: string;
  tutorialMode?: boolean;
  onLoadAiHistory?: () => Promise<AiTurnHistory>;
  onTelemetry?: (
    event: ParticipantTelemetryEvent,
  ) => Promise<unknown> | unknown;
};

const MAX_COMMAND_LENGTH = 4_000;

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
  const telemetryViewedTasks = useRef(new Set<string>());

  const timeIsUp = Boolean(deadlineAt) && remainingTime === "00:00";
  const isBusy = busy || commandBusy || timeIsUp;
  const canAct = task.status === "active" && !isBusy;
  const { classicMath, isZendo, isChessCoverage } = taskTraits(task);
  const chessCoverageHasPlacement =
    state.kind === "chess_coverage" && state.placements.length > 0;

  useEffect(() => {
    const updateTimer = () => setRemainingTime(formatRemainingTime(deadlineAt));
    updateTimer();
    const interval = window.setInterval(updateTimer, 1000);
    return () => window.clearInterval(interval);
  }, [deadlineAt]);

  const emitTelemetry = useTelemetryQueue(attemptId, onTelemetry, activeTaskId);

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

  function runCommand(rawInput: string) {
    return runTaskCommand(rawInput, {
      task,
      isBusy,
      inFlight,
      inputRef,
      appendEntry,
      emitTelemetry,
      setDraft,
      setCommandBusy,
      setAiThinking,
      setAiRemaining,
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
    });
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
          <TaskBrief
            task={task}
            canAct={canAct}
            onCommand={(command) => void runCommand(command)}
          />

          <TaskScene
            state={state}
            family={task.family}
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

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m5 12 13-7-4.5 14-2.4-5.1L5 12Z" />
      <path d="m11.1 13.9 3.4-3.4" />
    </svg>
  );
}
