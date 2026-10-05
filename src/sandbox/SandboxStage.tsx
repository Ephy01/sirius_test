import { ParticipantWorkspace } from "../participant/ParticipantWorkspace";
import type { TaskSandboxState } from "./useTaskSandbox";

/** The open variant in the workspace a participant gets. */
export function SandboxStage({
  sandbox,
  emptyHint,
}: {
  sandbox: TaskSandboxState;
  emptyHint: string;
}) {
  const { task, busy } = sandbox;
  return (
    <div className="sandbox-stage">
      {task ? (
        <ParticipantWorkspace
          task={task}
          busy={busy}
          modeLabel="Песочница"
          assistantOffReply="В песочнице ассистент выключен. Команды работают как в попытке."
          {...sandbox.handlers}
          key={task.id}
        />
      ) : (
        <p className="sandbox-stage__empty">
          {busy ? "Генерируем вариант…" : emptyHint}
        </p>
      )}
    </div>
  );
}
