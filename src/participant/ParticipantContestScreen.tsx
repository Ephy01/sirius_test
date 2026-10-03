import { useEffect, useState } from "react";
import {
  api,
  type ParticipantTask,
  type ParticipantTelemetryEvent,
  type TaskInteractionInput,
  type TaskProgressEntry,
} from "../api";
import type { AccessSession } from "../auth";
import { AppHeader } from "../components";
import type {
  TaskMoveTransitionResult,
  TaskTransitionResult,
} from "./commands";
import { ParticipantWorkspace } from "./ParticipantWorkspace";

export function ParticipantContestScreen({
  session,
  onLogout,
}: {
  session: AccessSession;
  onLogout: () => void;
}) {
  const [task, setTask] = useState<ParticipantTask | null>(null);
  const [taskProgress, setTaskProgress] = useState<TaskProgressEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");

    api
      .getCurrentTask({
        token: session.token,
        signal: controller.signal,
      })
      .then((response) => setTask(response.task))
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setError(
          caught instanceof Error
            ? caught.message
            : "Не удалось загрузить задачу.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [session.attempt?.id, session.token]);

  useEffect(() => {
    if (!task) return;
    const controller = new AbortController();
    api
      .getTaskProgress({ token: session.token, signal: controller.signal })
      .then(setTaskProgress)
      .catch(() => {});
    return () => controller.abort();
  }, [task?.id, task?.status, session.token]);

  function requireActiveTask(): ParticipantTask {
    if (!task || task.status !== "active") {
      throw new Error("Текущая задача уже закрыта.");
    }
    return task;
  }

  async function runTaskAction<T>(action: () => Promise<T>): Promise<T> {
    setBusy(true);
    setError("");
    try {
      return await action();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Не удалось выполнить команду.",
      );
      throw caught;
    } finally {
      setBusy(false);
    }
  }

  async function openNextTask(
    closedTask: ParticipantTask,
    failureMessage: string,
  ): Promise<TaskTransitionResult> {
    try {
      const next = await api.getNextTask({ token: session.token });
      setTask(next.task);
      return { ordinal: next.task.ordinal, advanced: true };
    } catch {
      return {
        ordinal: closedTask.ordinal,
        advanced: false,
        message: failureMessage,
      };
    }
  }

  async function answerTask(answer: string): Promise<TaskTransitionResult> {
    const activeTask = requireActiveTask();
    return runTaskAction(async () => {
      const response = await api.answerTask(activeTask.id, answer, {
        token: session.token,
      });
      setTask(response.task);
      if (response.task.status === "active") {
        return {
          ordinal: response.task.ordinal,
          advanced: false,
          message: response.message,
        };
      }
      return openNextTask(
        response.task,
        "Ответ зафиксирован, но следующая задача не открылась. Используйте /next.",
      );
    });
  }

  async function skipTask(): Promise<TaskTransitionResult> {
    const activeTask = requireActiveTask();
    return runTaskAction(async () => {
      const response = await api.skipTask(activeTask.id, {
        token: session.token,
      });
      setTask(response.task);
      return openNextTask(
        response.task,
        "Пропуск зафиксирован, но следующая задача не открылась. Используйте /next.",
      );
    });
  }

  async function nextTask(): Promise<TaskTransitionResult> {
    if (!task || task.status === "active") {
      throw new Error("Сначала завершите текущую задачу.");
    }
    return runTaskAction(async () => {
      const response = await api.getNextTask({ token: session.token });
      setTask(response.task);
      return { ordinal: response.task.ordinal, advanced: true };
    });
  }

  async function interact(
    input: TaskInteractionInput,
  ): Promise<TaskMoveTransitionResult> {
    const activeTask = requireActiveTask();
    return runTaskAction(async () => {
      const response = await api.interactWithTask(activeTask.id, input, {
        token: session.token,
      });
      setTask(response.task);
      const result = {
        ordinal: response.task.ordinal,
        advanced: false,
        accepted: response.accepted,
        completed: response.completed,
        message: response.message,
      };
      if (input.actionType !== "apply_op" || !response.completed) return result;

      const transition = await openNextTask(
        response.task,
        `${response.message ?? "Задача завершена."} Следующая задача не открылась. Используйте /next.`,
      );
      return { ...result, ...transition };
    });
  }

  async function getDebugAnswer() {
    return api.getParticipantDebugAnswer(requireActiveTask().id, {
      token: session.token,
    });
  }

  async function sendAiMessage(message: string, clientActionId: string) {
    return api.sendAiTurn(
      requireActiveTask().id,
      { clientActionId, message },
      { token: session.token },
    );
  }

  async function loadAiHistory() {
    if (!task) {
      throw new Error("Задача недоступна.");
    }
    return api.getAiTurns(task.id, { token: session.token });
  }

  async function recordTelemetry(
    event: ParticipantTelemetryEvent,
  ): Promise<void> {
    await api.recordParticipantTelemetry(event, {
      token: session.token,
    });
  }

  return (
    <div className="participant-page">
      <AppHeader
        role="Участник"
        onLogout={onLogout}
        meta={<span className="workspace-label">Контест идёт</span>}
      />

      {task ? (
        <ParticipantWorkspace
          task={task}
          attemptId={session.attempt?.id}
          deadlineAt={session.attempt?.deadlineAt}
          taskProgress={taskProgress}
          busy={busy}
          error={error}
          onAnswer={answerTask}
          onSkip={skipTask}
          onNext={nextTask}
          onProbe={(probe, clientActionId) =>
            interact({ actionType: "probe", probe, clientActionId })
          }
          onHint={(clientActionId) =>
            interact({ actionType: "hint", clientActionId })
          }
          onGetAnswer={getDebugAnswer}
          onApplyOperation={(opId, clientActionId) =>
            interact({ actionType: "apply_op", opId, clientActionId })
          }
          onUndo={(clientActionId) =>
            interact({ actionType: "undo", clientActionId })
          }
          onReset={(clientActionId) =>
            interact({ actionType: "reset", clientActionId })
          }
          onAiMessage={sendAiMessage}
          onLoadAiHistory={loadAiHistory}
          onTelemetry={recordTelemetry}
        />
      ) : (
        <main className="participant-waiting">
          <div className="participant-waiting__status" aria-hidden="true">
            <i />
          </div>
          <p className="eyebrow">
            {loading ? "Готовим среду" : "Задача недоступна"}
          </p>
          <h1>{loading ? "Создаём ваш вариант…" : "Не удалось открыть задачу"}</h1>
          <p>
            {loading
              ? "Задача воспроизводимо создаётся по seed этой попытки."
              : error}
          </p>
        </main>
      )}
    </div>
  );
}
