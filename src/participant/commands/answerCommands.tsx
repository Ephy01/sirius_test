import { TaskNumber } from "../consoleEntries";
import { reportClosedTask, type CommandRun } from "./run";

export function answer(run: CommandRun) {
  if (reportClosedTask(run)) return;
  if (!run.payload) {
    run.appendEntry(
      "system",
      <>
        После команды нужен текст ответа. Например:{" "}
        <code>{run.behaviour.answerExample ?? "/answer <ваш ответ>"}</code>
        .
      </>,
    );
    return;
  }
  return submitFinalAnswer(run, run.payload);
}

/** `done`, `impossible` and their Russian forms typed without a slash. */
export function bareAnswer(run: CommandRun) {
  if (reportClosedTask(run)) return;
  return submitFinalAnswer(run, run.input);
}

async function submitFinalAnswer(run: CommandRun, value: string) {
  const transition = await run.onAnswer(value);
  run.appendEntry(
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

export function skip(run: CommandRun) {
  if (reportClosedTask(run)) return;
  if (run.parts.length > 0) {
    run.appendEntry("system", "Команда /skip не принимает дополнительных данных.");
    return;
  }
  return skipTask(run);
}

async function skipTask(run: CommandRun) {
  const transition = await run.onSkip();
  run.appendEntry(
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

export function next(run: CommandRun) {
  if (run.parts.length > 0) {
    run.appendEntry("system", "Команда /next не принимает дополнительных данных.");
    return;
  }
  if (run.task.status === "active") {
    run.appendEntry(
      "system",
      "Сначала отправьте ответ или пропустите задачу командой /skip.",
    );
    return;
  }
  return openNextTask(run);
}

async function openNextTask(run: CommandRun) {
  const transition = await run.onNext();
  run.appendEntry(
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
