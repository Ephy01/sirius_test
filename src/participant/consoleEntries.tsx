import type { ReactNode } from "react";
import type { ParticipantTask } from "../api";

export type ConsoleEntry = {
  id: number;
  author: "system" | "participant" | "assistant";
  content: ReactNode;
};

export function TaskNumber({ ordinal }: { ordinal: number }) {
  return <strong>№{String(ordinal).padStart(2, "0")}</strong>;
}

function openingEntries(opened: ReactNode, guide: ReactNode): ConsoleEntry[] {
  return [
    { id: 1, author: "system", content: opened },
    { id: 2, author: "system", content: guide },
  ];
}

export function initialEntries(task: ParticipantTask): ConsoleEntry[] {
  const kind = task.publicState.kind;
  const number = <TaskNumber ordinal={task.ordinal} />;

  if (kind === "chess_coverage") {
    return openingEntries(
      <>Открыта шахматная расстановка {number}.</>,
      "Выберите фигуру в палитре и ставьте её на свободные клетки. Покройте все цели с минимальной стоимостью.",
    );
  }
  if (
    kind === "machine_panel" ||
    (kind === "chess" && task.family === "machine_reach")
  ) {
    return openingEntries(
      <>
        Открыта машина {number}. Переведите текущее состояние в целевое.
      </>,
      <>
        Применяйте операции командой <code>/op &lt;id&gt;</code>, отменяйте
        последний шаг через <code>/undo</code>. Итог: <code>done</code> или{" "}
        <code>impossible</code>.
      </>,
    );
  }
  if (kind === "hidden_wiring") {
    return openingEntries(
      <>
        Открыта панель {number}. Проводка скрыта. Кнопки срабатывают только
        парами.
      </>,
      <>
        Нажимайте комбинации из двух кнопок командой <code>/op b1+b2</code>{" "}
        или кнопками на панели. Первая проба обучающая и не тратит лимит.
      </>,
    );
  }

  const opened = <>Открыта задача {number}.</>;
  if (kind === "grid_zendo") {
    return openingEntries(
      opened,
      <>
        Нарисуйте узор на пустой сетке и проверьте его кнопкой или командой{" "}
        <code>/test</code>, затем отправьте итоговый ответ.
      </>,
    );
  }
  if (
    kind === "token_zendo" ||
    kind === "point_zendo" ||
    (kind === "geometry_atlas" && task.family === "geo_zendo")
  ) {
    return openingEntries(
      opened,
      <>
        Можно проверить доступную карточку командой{" "}
        <code>/test &lt;код&gt;</code>, затем отправить итоговый ответ.
      </>,
    );
  }
  return openingEntries(
    opened,
    <>
      Введите <code>/help</code>, чтобы увидеть доступные команды.
    </>,
  );
}
