import { ApiError } from "../../api";
import { createClientActionId } from "../clientActionId";
import type { CommandRun, TaskCommandHandlers } from "./run";

/** Any line that is not a command goes to the assistant. */
export function assistantMessage(run: CommandRun) {
  if (!run.onAiMessage) {
    run.appendEntry(
      "system",
      run.assistantOffReply ?? (
        <>
          Чтобы сохранить решение, начните сообщение с{" "}
          <code>/answer</code>.
        </>
      ),
    );
    return;
  }
  if (run.task.status !== "active") {
    run.appendEntry(
      "system",
      "Эта задача уже закрыта — ассистент доступен только в активной задаче.",
    );
    return;
  }
  return askAssistant(run, run.onAiMessage);
}

async function askAssistant(
  run: CommandRun,
  onAiMessage: NonNullable<TaskCommandHandlers["onAiMessage"]>,
) {
  run.setAiThinking(true);
  try {
    const turn = await onAiMessage(run.input, createClientActionId());
    run.setAiRemaining(turn.remaining);
    if (turn.assistantMessage) {
      run.appendEntry("assistant", turn.assistantMessage);
    } else {
      run.appendEntry(
        "system",
        "Ассистент не вернул ответ. Попробуйте ещё раз.",
      );
    }
    if (turn.remaining.task === 0 || turn.remaining.attempt === 0) {
      run.appendEntry("system", "Лимит обращений к ассистенту исчерпан.");
    }
  } catch (error) {
    run.appendEntry(
      "system",
      error instanceof ApiError
        ? error.message
        : "Не удалось связаться с ассистентом.",
    );
  } finally {
    run.setAiThinking(false);
  }
}
