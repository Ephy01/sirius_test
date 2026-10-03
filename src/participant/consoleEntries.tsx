import type { ReactNode } from "react";
import type { ParticipantTask } from "../api";
import { taskBehaviour } from "../tasks/registry";

export type ConsoleEntry = {
  id: number;
  author: "system" | "participant" | "assistant";
  content: ReactNode;
};

export function TaskNumber({ ordinal }: { ordinal: number }) {
  return <strong>№{String(ordinal).padStart(2, "0")}</strong>;
}

export function initialEntries(task: ParticipantTask): ConsoleEntry[] {
  const number = <TaskNumber ordinal={task.ordinal} />;
  const { opened, guide } = taskBehaviour(task).opening(number);

  return [
    {
      id: 1,
      author: "system",
      content: opened ?? <>Открыта задача {number}.</>,
    },
    {
      id: 2,
      author: "system",
      content: guide ?? (
        <>
          Введите <code>/help</code>, чтобы увидеть доступные команды.
        </>
      ),
    },
  ];
}
