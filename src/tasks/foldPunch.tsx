import { useState } from "react";
import { invalidResponse } from "../api/errors";
import {
  isRecord,
  readNumber,
  readString,
  type UnknownRecord,
} from "../api/parsing";
import type { PublicStateBase, TaskKind } from "./kind";

export type FoldStep = {
  axis: "vertical" | "horizontal" | "diagonal";
  direction: string;
  label: string;
};

export type FoldPunchPublicState = {
  kind: "fold_punch";
  family: "fold_punch";
  variant: string;
  prompt: string;
  sheetSize: number;
  folds: FoldStep[];
  folded: {
    width: number;
    height: number;
    triangle: boolean;
    holes: [number, number][];
  };
  responseHint: string;
};

function parseFoldPunchState(
  state: UnknownRecord,
  base: PublicStateBase,
): FoldPunchPublicState {
  const sheetSize = readNumber(state, "sheetSize", "sheet_size") ?? 8;
  const folds: FoldStep[] = Array.isArray(state.folds)
    ? state.folds.flatMap((item) => {
        if (!isRecord(item)) return [];
        const axis = readString(item, "axis");
        const direction = readString(item, "direction");
        if (
          (axis !== "vertical" &&
            axis !== "horizontal" &&
            axis !== "diagonal") ||
          !direction
        ) {
          return [];
        }
        return [{
          axis,
          direction,
          label: readString(item, "label") ?? direction,
        }];
      })
    : [];
  const folded = isRecord(state.folded) ? state.folded : {};
  const holes =
    Array.isArray(folded.holes) &&
    folded.holes.every(
      (item) =>
        Array.isArray(item) &&
        item.length === 2 &&
        item.every((part) => typeof part === "number"),
    )
      ? (folded.holes as [number, number][])
      : null;
  const width = readNumber(folded, "width");
  const height = readNumber(folded, "height");
  if (folds.length === 0 || !holes || width === undefined || height === undefined) {
    throw invalidResponse("Сервер вернул некорректную задачу дырокола.", state);
  }

  return {
    kind: "fold_punch",
    family: "fold_punch",
    variant: readString(state, "variant") ?? "unfold_holes",
    ...base,
    sheetSize,
    folds,
    folded: {
      width,
      height,
      triangle: folded.triangle === true,
      holes,
    },
  };
}

function FoldPunchScene({
  state,
  canAnswer,
  onSubmit,
}: {
  state: FoldPunchPublicState;
  canAnswer: boolean;
  onSubmit: (cells: string) => void;
}) {
  const size = state.sheetSize;
  const [marked, setMarked] = useState<boolean[]>(() =>
    Array(size * size).fill(false),
  );
  const holeSet = new Set(
    state.folded.holes.map(([row, column]) => `${row}:${column}`),
  );
  const markedCells = marked
    .map((cell, index) =>
      cell
        ? `${Math.floor(index / size) + 1},${(index % size) + 1}`
        : null,
    )
    .filter((cell): cell is string => cell !== null);

  return (
    <figure className="fold-punch" aria-label="Дырокол">
      <ol className="fold-punch__folds" aria-label="Порядок сгибов">
        {state.folds.map((fold, index) => (
          <li key={index}>
            <span>{index + 1}</span>
            {fold.label}
          </li>
        ))}
        <li>
          <span>{state.folds.length + 1}</span>
          Пробили {state.folded.holes.length === 1 ? "дырку" : "дырки"}
        </li>
      </ol>

      <div className="fold-punch__panels">
        <section>
          <header>Сложенный лист с дырками</header>
          <div
            className="fold-punch__grid fold-punch__grid--folded"
            style={{
              gridTemplateColumns: `repeat(${state.folded.width}, 18px)`,
            }}
            aria-hidden="true"
          >
            {Array.from(
              { length: state.folded.height * state.folded.width },
              (_, index) => {
                const row = Math.floor(index / state.folded.width);
                const column = index % state.folded.width;
                const outside =
                  state.folded.triangle && column > row;
                return (
                  <i
                    className={[
                      outside ? "is-outside" : "",
                      holeSet.has(`${row}:${column}`) ? "is-hole" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    key={index}
                  />
                );
              },
            )}
          </div>
        </section>
        <section>
          <header>Развёрнутый лист — отметьте дырки</header>
          <div
            className="fold-punch__grid fold-punch__grid--answer"
            style={{ gridTemplateColumns: `repeat(${size}, 1fr)` }}
            role="group"
            aria-label="Отметка дырок на развёрнутом листе"
          >
            {marked.map((cell, index) => (
              <button
                type="button"
                className={cell ? "is-hole" : ""}
                aria-pressed={cell}
                aria-label={`Клетка ${Math.floor(index / size) + 1}-${
                  (index % size) + 1
                }`}
                onClick={() =>
                  setMarked((current) =>
                    current.map((value, cellIndex) =>
                      cellIndex === index ? !value : value,
                    ),
                  )
                }
                key={index}
              />
            ))}
          </div>
          <button
            type="button"
            className="fold-punch__submit"
            disabled={!canAnswer || markedCells.length === 0}
            onClick={() => onSubmit(markedCells.join(" "))}
          >
            Отправить отмеченные клетки
          </button>
        </section>
      </div>
    </figure>
  );
}

export const foldPunch: TaskKind<FoldPunchPublicState> = {
  parse: parseFoldPunchState,
  renderScene: ({ state, canAct, onCommand }) => (
    <FoldPunchScene
      state={state}
      canAnswer={canAct}
      onSubmit={(cells) => onCommand(`/answer ${cells}`)}
    />
  ),
  answerGuide: () => (
    <>
      Кликните клетки на развёрнутом листе и нажмите «Отправить
      отмеченные клетки», или отправьте ответ в чате (пример:{" "}
      <code>/answer 2,3 5,8</code> — строка,столбец).
    </>
  ),
  metaLines: () => [
    "сгибы выполняются по порядку; дырки пробиты через все слои сразу",
  ],
};
