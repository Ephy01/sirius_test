import { createClientActionId } from "../clientActionId";
import { TaskNumber } from "../consoleEntries";
import {
  reportClosedTask,
  type CommandRun,
  type TaskCommandHandlers,
} from "./run";

export function probe(run: CommandRun) {
  if (!run.behaviour.commands.includes("probe")) {
    run.appendEntry(
      "system",
      "Команда /test доступна только в задачах со скрытым утверждением.",
    );
    return;
  }
  if (reportClosedTask(run)) return;
  if (!run.payload) {
    run.appendEntry(
      "system",
      <>
        Укажите код карточки. Например: <code>/test P1</code>.
      </>,
    );
    return;
  }
  return submitProbe(run, run.payload);
}

async function submitProbe(run: CommandRun, card: string) {
  if (!run.onProbe) {
    run.appendEntry("system", "Проверка сейчас недоступна.");
    return;
  }
  const transition = await run.onProbe(card, createClientActionId());
  run.appendEntry(
    "system",
    transition.message ??
      (transition.accepted
        ? "Проверка выполнена."
        : "Эту конфигурацию нельзя проверить."),
  );
}

export function hint(run: CommandRun) {
  if (!run.behaviour.commands.includes("hint")) {
    run.appendEntry(
      "system",
      "Подсказка доступна только в задачах со скрытым правилом.",
    );
    return;
  }
  if (reportClosedTask(run)) return;
  if (!run.onHint) {
    run.appendEntry("system", "Подсказка сейчас недоступна.");
    return;
  }
  return requestHint(run, run.onHint);
}

async function requestHint(
  run: CommandRun,
  onHint: NonNullable<TaskCommandHandlers["onHint"]>,
) {
  const transition = await onHint(createClientActionId());
  run.appendEntry(
    "system",
    transition.message ??
      (transition.accepted ? "Подсказка получена." : "Подсказка недоступна."),
  );
}

export function operation(run: CommandRun) {
  if (!run.behaviour.commands.includes("op")) {
    run.appendEntry(
      "system",
      "Команда /op доступна только в задачах с машиной или панелью.",
    );
    return;
  }
  if (reportClosedTask(run)) return;
  if (!run.payload || run.parts.length !== 1) {
    run.appendEntry(
      "system",
      <>
        Укажите один идентификатор. Например: <code>/op op1</code>.
      </>,
    );
    return;
  }
  return submitOperation(run, run.payload);
}

async function submitOperation(run: CommandRun, opId: string) {
  if (!run.onApplyOperation) {
    run.appendEntry("system", "Пульт машины сейчас недоступен.");
    return;
  }
  const transition = await run.onApplyOperation(opId, createClientActionId());
  run.appendEntry(
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

export function reset(run: CommandRun) {
  if (!run.behaviour.commands.includes("reset")) {
    run.appendEntry(
      "system",
      "Команда /reset доступна только в задачах с изменяемым состоянием.",
    );
    return;
  }
  if (reportClosedTask(run)) return;
  if (run.parts.length > 0) {
    run.appendEntry(
      "system",
      "Команда /reset не принимает дополнительных данных.",
    );
    return;
  }
  return submitReset(run);
}

async function submitReset(run: CommandRun) {
  if (!run.onReset) {
    run.appendEntry("system", "Возврат в начало сейчас недоступен.");
    return;
  }
  const transition = await run.onReset(createClientActionId());
  run.appendEntry(
    "system",
    transition.message ??
      (transition.accepted
        ? "Состояние возвращено в начало."
        : "Состояние уже начальное."),
  );
}

export function undo(run: CommandRun) {
  if (!run.behaviour.commands.includes("undo")) {
    run.appendEntry(
      "system",
      "Команда /undo доступна только в задачах с машиной.",
    );
    return;
  }
  if (reportClosedTask(run)) return;
  if (run.parts.length > 0) {
    run.appendEntry(
      "system",
      "Команда /undo не принимает дополнительных данных.",
    );
    return;
  }
  return submitUndo(run);
}

async function submitUndo(run: CommandRun) {
  if (!run.onUndo) {
    run.appendEntry("system", "Отмена сейчас недоступна.");
    return;
  }
  const transition = await run.onUndo(createClientActionId());
  run.appendEntry(
    "system",
    transition.message ??
      (transition.accepted
        ? "Последняя операция отменена."
        : "Отменять пока нечего."),
  );
}
