import type { ReactNode, RefObject } from "react";
import {
  ApiError,
  type AiTurn,
  type AiTurnRemaining,
  type DebugAnswerResponse,
  type ParticipantTask,
} from "../api";
import { createClientActionId } from "./clientActionId";
import { TaskNumber, type ConsoleEntry } from "./consoleEntries";
import { taskTraits } from "./taskTraits";
import { telemetryText, type EmitTelemetry } from "./telemetry";

export type TaskTransitionResult = {
  ordinal: number;
  advanced: boolean;
  message?: string;
};

export type TaskMoveTransitionResult = TaskTransitionResult & {
  accepted: boolean;
  completed: boolean;
};

export type TaskCommandHandlers = {
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
};

type CommandContext = TaskCommandHandlers & {
  task: ParticipantTask;
  isBusy: boolean;
  inFlight: { current: boolean };
  inputRef: RefObject<HTMLInputElement | null>;
  appendEntry: (author: ConsoleEntry["author"], content: ReactNode) => void;
  emitTelemetry: EmitTelemetry;
  setDraft: (draft: string) => void;
  setCommandBusy: (busy: boolean) => void;
  setAiThinking: (thinking: boolean) => void;
  setAiRemaining: (remaining: AiTurnRemaining) => void;
};

export async function runTaskCommand(
  rawInput: string,
  {
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
  }: CommandContext,
) {
  const {
    diceChess,
    classicMath,
    isZendo,
    isMachine,
    isWiring,
    isChessCoverage,
  } = taskTraits(task);

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
