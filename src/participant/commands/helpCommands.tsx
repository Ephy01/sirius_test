import type { DebugAnswerResponse } from "../../api";
import { reportClosedTask, type CommandRun } from "./run";

const DEFAULT_HELP = (
  <>
    <code>/answer &lt;текст&gt;</code> — зафиксировать ответ
    и открыть следующую задачу
    <br />
    <code>/skip</code> — пропустить и открыть следующую задачу
    <br />
    <code>/next</code> — повторить переход, если он прервался
  </>
);

export function help(run: CommandRun) {
  run.appendEntry("system", run.behaviour.help ?? DEFAULT_HELP);
}

export function unknownCommand(run: CommandRun) {
  run.appendEntry(
    "system",
    <>
      Такой команды нет. Введите <code>/help</code> для справки.
    </>,
  );
}

export function getAnswer(run: CommandRun) {
  if (run.payload.toLowerCase() !== "answer") {
    run.appendEntry(
      "system",
      <>
        Неизвестная команда. Возможно, вы имели в виду{" "}
        <code>/get answer</code>.
      </>,
    );
    return;
  }
  if (reportClosedTask(run)) return;
  if (!run.onGetAnswer) {
    run.appendEntry("system", "Эталонный ответ сейчас недоступен.");
    return;
  }
  return revealAnswer(run, run.onGetAnswer);
}

async function revealAnswer(
  run: CommandRun,
  onGetAnswer: () => Promise<DebugAnswerResponse>,
) {
  try {
    const revealed = await onGetAnswer();
    run.appendEntry(
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
    run.appendEntry(
      "system",
      caught instanceof Error
        ? caught.message
        : "Не удалось получить эталонный ответ.",
    );
  }
}
