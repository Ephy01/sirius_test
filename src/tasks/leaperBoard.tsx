import { Fragment } from "react";
import { invalidResponse } from "../api/errors";
import { readNumber, readString, type UnknownRecord } from "../api/parsing";
import {
  unsupportedTaskKind,
  type PublicStateBase,
  type TaskKind,
} from "./kind";
import {
  parseBoardPoint,
  parseBoardPoints,
  type BoardPoint,
} from "./shared/chess";
import {
  MACHINE_RESPONSE_HINT,
  machineBehaviour,
  parseMachineOperations,
  type MachineOperation,
} from "./shared/machine";

export type LeaperBoardPublicState = {
  kind: "chess";
  subKind: "leaper_board";
  prompt: string;
  ops: MachineOperation[];
  start: BoardPoint;
  target: BoardPoint;
  current: BoardPoint;
  stepsSoftCap: number;
  stepsTaken: number;
  rows: number;
  cols: number;
  blocked: BoardPoint[];
  responseHint: string;
};

function parseLeaperBoardState(
  state: UnknownRecord,
  base: PublicStateBase,
): LeaperBoardPublicState {
  if (readString(state, "subKind", "sub_kind") !== "leaper_board") {
    throw unsupportedTaskKind(state);
  }
  const rows = readNumber(state, "rows");
  const cols = readNumber(state, "cols");
  const operations = parseMachineOperations(state.ops);
  const start = parseBoardPoint(state.start);
  const target = parseBoardPoint(state.target);
  const current = parseBoardPoint(state.current);
  const blocked = parseBoardPoints(state.blocked);
  if (
    rows === undefined ||
    cols === undefined ||
    !Number.isInteger(rows) ||
    !Number.isInteger(cols) ||
    rows < 1 ||
    rows > 8 ||
    cols < 1 ||
    cols > 8 ||
    !operations ||
    !start ||
    !target ||
    !current ||
    !blocked
  ) {
    throw invalidResponse("Сервер вернул некорректную доску прыгуна.", state);
  }

  return {
    kind: "chess",
    subKind: "leaper_board",
    ...base,
    ops: operations,
    start,
    target,
    current,
    stepsSoftCap: readNumber(state, "stepsSoftCap", "steps_soft_cap") ?? 24,
    stepsTaken: readNumber(state, "stepsTaken", "steps_taken") ?? 0,
    rows,
    cols,
    blocked,
  };
}

function LeaperBoardScene({
  state,
  canAct,
  onOp,
}: {
  state: LeaperBoardPublicState;
  canAct: boolean;
  onOp: (opId: string) => void;
}) {
  const blocked = new Set(
    state.blocked.map((cell) => `${cell.row}:${cell.col}`),
  );
  const currentKey = `${state.current.row}:${state.current.col}`;
  const targetKey = `${state.target.row}:${state.target.col}`;
  return (
    <figure className="leaper-scene" aria-label="Доска прыгуна">
      <div
        className="leaper-board"
        role="grid"
        aria-label="Доска прыгуна: нумерация с 1, строка 1 сверху"
        style={{ gridTemplateColumns: `auto repeat(${state.cols}, 1fr)` }}
      >
        <span className="leaper-board__corner" aria-hidden="true" />
        {Array.from({ length: state.cols }, (_, col) => (
          <span
            className="leaper-board__axis"
            aria-hidden="true"
            key={`col-${col}`}
          >
            {col + 1}
          </span>
        ))}
        {Array.from({ length: state.rows }, (_, row) => (
          <Fragment key={`row-${row}`}>
            <span className="leaper-board__axis" aria-hidden="true">
              {row + 1}
            </span>
            {Array.from({ length: state.cols }, (_, col) => {
              const key = `${row}:${col}`;
              const isBlocked = blocked.has(key);
              const isCurrent = key === currentKey;
              const isTarget = key === targetKey;
              return (
                <div
                  className={[
                    "leaper-board__cell",
                    isBlocked ? "is-blocked" : "",
                    isCurrent ? "is-current" : "",
                    isTarget ? "is-target" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  role="gridcell"
                  aria-label={`Строка ${row + 1}, столбец ${col + 1}: ${
                    isBlocked
                      ? "заблокировано"
                      : isCurrent
                        ? "фигура"
                        : isTarget
                          ? "цель"
                          : "пусто"
                  }`}
                  key={key}
                >
                  {isCurrent ? "♞" : isTarget ? "✦" : ""}
                </div>
              );
            })}
          </Fragment>
        ))}
      </div>
      <p className="leaper-scene__legend">
        Координаты — (строка, столбец), нумерация с 1, строка 1 — верхняя.
        Фигура: ({state.current.row + 1}, {state.current.col + 1}), цель ✦: (
        {state.target.row + 1}, {state.target.col + 1}).
      </p>
      <ol className="leaper-operations" aria-label="Разрешённые прыжки">
        {state.ops.map((operation) => (
          <li key={operation.id}>
            <button
              type="button"
              disabled={!canAct}
              onClick={() => onOp(operation.id)}
            >
              <code>{operation.id}</code>
              <span>{operation.label}</span>
            </button>
          </li>
        ))}
      </ol>
    </figure>
  );
}

export const leaperBoard: TaskKind<LeaperBoardPublicState> = {
  defaultResponseHint: MACHINE_RESPONSE_HINT,
  parse: parseLeaperBoardState,
  renderScene: ({ state, canAct, onCommand }) => (
    <LeaperBoardScene
      state={state}
      canAct={canAct}
      onOp={(opId) => onCommand(`/op ${opId}`)}
    />
  ),
  ...machineBehaviour(({ family }) => family === "machine_reach"),
  metaLines: ({ state }) => [
    `Фигура: (${state.current.row + 1}, ${state.current.col + 1})`,
    `Цель: (${state.target.row + 1}, ${state.target.col + 1})`,
    `Шагов: ${state.stepsTaken} / ${state.stepsSoftCap}`,
  ],
};
