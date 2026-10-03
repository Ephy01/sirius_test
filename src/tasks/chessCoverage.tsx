import { useState } from "react";
import { invalidResponse } from "../api/errors";
import {
  isRecord,
  readNumber,
  readString,
  type UnknownRecord,
} from "../api/parsing";
import type { PublicStateBase, TaskKind } from "./kind";
import { parseBoardPoints, pieceGlyph, type BoardPoint } from "./shared/chess";

export type ChessCoveragePieceId = "N" | "B" | "R" | "Q";

export type ChessCoveragePieceType = {
  id: ChessCoveragePieceId;
  label: string;
  baseCost: number;
  repeatSurcharge: number;
  limit: number;
  moveLabel: string;
  offsets: BoardPoint[];
};

export type ChessCoveragePlacement = {
  id: string;
  piece: ChessCoveragePieceId;
  row: number;
  col: number;
  cost: number;
};

export type ChessCoveragePublicState = {
  kind: "chess_coverage";
  family: "chess_coverage";
  prompt: string;
  targets: BoardPoint[];
  pieceTypes: ChessCoveragePieceType[];
  placements: ChessCoveragePlacement[];
  pieceCounts: Record<string, number>;
  coveredTargets: BoardPoint[];
  totalCost: number;
  maxPlacements: number;
  allCovered: boolean;
  responseHint: string;
};

function isCoveragePieceId(value: unknown): value is ChessCoveragePieceId {
  return value === "N" || value === "B" || value === "R" || value === "Q";
}

function parseChessCoverageState(
  state: UnknownRecord,
  base: PublicStateBase,
): ChessCoveragePublicState {
  const boardSize = readNumber(state, "boardSize", "board_size");
  const targets = parseBoardPoints(state.targets);
  const coveredTargets = parseBoardPoints(
    state.coveredTargets ?? state.covered_targets,
  );
  const pieceTypeValues = state.pieceTypes ?? state.piece_types;
  const pieceCountValue = state.pieceCounts ?? state.piece_counts;
  const pieceTypes = Array.isArray(pieceTypeValues)
    ? pieceTypeValues.flatMap((item): ChessCoveragePieceType[] => {
        if (!isRecord(item)) return [];
        const id = readString(item, "id");
        const baseCost = readNumber(item, "baseCost", "base_cost");
        const repeatSurcharge = readNumber(
          item,
          "repeatSurcharge",
          "repeat_surcharge",
        );
        const limit = readNumber(item, "limit");
        const offsets = parseBoardPoints(item.offsets);
        if (
          !isCoveragePieceId(id) ||
          baseCost === undefined ||
          repeatSurcharge === undefined ||
          limit === undefined ||
          !offsets ||
          offsets.length === 0
        ) {
          return [];
        }
        return [{
          id,
          label: readString(item, "label") ?? id,
          baseCost,
          repeatSurcharge,
          limit,
          moveLabel:
            readString(item, "moveLabel", "move_label") ?? "особый прыжок",
          offsets,
        }];
      })
    : [];
  const placements = Array.isArray(state.placements)
    ? state.placements.flatMap((item): ChessCoveragePlacement[] => {
        if (!isRecord(item)) return [];
        const id = readString(item, "id");
        const piece = readString(item, "piece");
        const row = readNumber(item, "row");
        const col = readNumber(item, "col");
        const cost = readNumber(item, "cost");
        if (
          !id ||
          !isCoveragePieceId(piece) ||
          row === undefined ||
          col === undefined ||
          cost === undefined
        ) {
          return [];
        }
        return [{ id, piece, row, col, cost }];
      })
    : [];
  const pieceCounts = isRecord(pieceCountValue)
    ? Object.fromEntries(
        Object.entries(pieceCountValue).flatMap(([key, item]) =>
          typeof item === "number" && Number.isFinite(item)
            ? [[key, item] as const]
            : [],
        ),
      )
    : {};
  if (
    boardSize !== 8 ||
    pieceTypes.length === 0 ||
    !targets ||
    targets.length === 0 ||
    !coveredTargets
  ) {
    throw invalidResponse(
      "Сервер вернул некорректную шахматную расстановку.",
      state,
    );
  }

  return {
    kind: "chess_coverage",
    family: "chess_coverage",
    ...base,
    targets,
    pieceTypes,
    placements,
    pieceCounts,
    coveredTargets,
    totalCost: readNumber(state, "totalCost", "total_cost") ?? 0,
    maxPlacements: readNumber(state, "maxPlacements", "max_placements") ?? 0,
    allCovered: state.allCovered === true || state.all_covered === true,
  };
}

function ChessCoverageScene({
  state,
  canAct,
  onAction,
  onReset,
  onSubmit,
}: {
  state: ChessCoveragePublicState;
  canAct: boolean;
  onAction: (action: string) => void;
  onReset: () => void;
  onSubmit: () => void;
}) {
  const [activePiece, setActivePiece] = useState(state.pieceTypes[0].id);
  const targets = new Set(
    state.targets.map((point) => `${point.row}:${point.col}`),
  );
  const covered = new Set(
    state.coveredTargets.map((point) => `${point.row}:${point.col}`),
  );
  const placements = new Map(
    state.placements.map((placement) => [
      `${placement.row}:${placement.col}`,
      placement,
    ]),
  );
  const activeDefinition = state.pieceTypes.find(
    (piece) => piece.id === activePiece,
  );
  const placementLimitReached = state.placements.length >= state.maxPlacements;

  return (
    <figure className="coverage-scene" aria-label="Задача о покрытии клеток">
      <div className="coverage-placement">
        <section className="coverage-palette" aria-label="Палитра фигур">
          {state.pieceTypes.map((piece) => {
            const count = state.pieceCounts[piece.id] ?? 0;
            const nextCost = piece.baseCost + piece.repeatSurcharge * count;
            const exhausted = count >= piece.limit;
            return (
              <button
                type="button"
                className={[
                  "coverage-piece-card",
                  activePiece === piece.id ? "is-active" : "",
                ].filter(Boolean).join(" ")}
                aria-pressed={activePiece === piece.id}
                disabled={!canAct || exhausted || placementLimitReached}
                onClick={() => setActivePiece(piece.id)}
                key={piece.id}
              >
                <span className="coverage-piece-card__glyph" aria-hidden="true">
                  {pieceGlyph("w", piece.id)}
                </span>
                <span className="coverage-piece-card__copy">
                  <strong>{piece.label}</strong>
                  <small>{piece.moveLabel}</small>
                </span>
                <span className="coverage-piece-card__cost">
                  {exhausted ? "лимит" : `следующая: ${nextCost}`}
                  <small>{count} / {piece.limit}</small>
                </span>
              </button>
            );
          })}
        </section>

        {activeDefinition && (
          <div className="coverage-move-rule" aria-live="polite">
            <MovePattern piece={activeDefinition} />
            <p>
              <strong>{pieceGlyph("w", activeDefinition.id)} {activeDefinition.label}</strong>
              атакует только отмеченные клетки и перепрыгивает всё между ними.
              Стоимость: {activeDefinition.baseCost}, затем +
              {activeDefinition.repeatSurcharge} за каждую уже поставленную фигуру
              этого типа.
            </p>
          </div>
        )}

        <div className="coverage-placement-board" role="grid" aria-label="Доска 8 на 8">
          {Array.from({ length: 64 }, (_, index) => {
            const row = Math.floor(index / 8);
            const col = index % 8;
            const key = `${row}:${col}`;
            const placement = placements.get(key);
            const target = targets.has(key);
            const isCovered = covered.has(key);
            const canPlace = Boolean(
              canAct &&
              activeDefinition &&
              !target &&
              !placement &&
              !placementLimitReached &&
              (state.pieceCounts[activeDefinition.id] ?? 0) < activeDefinition.limit,
            );
            const canRemove = canAct && Boolean(placement);
            return (
              <button
                type="button"
                role="gridcell"
                className={[
                  "coverage-placement-board__cell",
                  (row + col) % 2 ? "is-dark" : "",
                  target ? "is-target" : "",
                  isCovered ? "is-covered" : "",
                ].filter(Boolean).join(" ")}
                disabled={!canPlace && !canRemove}
                aria-label={
                  placement
                    ? `${placement.id}, ${placement.piece}, клетка ${String.fromCharCode(65 + col)}${row + 1}, стоимость ${placement.cost}. Нажмите, чтобы убрать.`
                    : `Клетка ${String.fromCharCode(65 + col)}${row + 1}${target ? ", цель" : ""}`
                }
                onClick={() => {
                  if (placement) {
                    onAction(`remove:${placement.id}`);
                  } else if (canPlace && activeDefinition) {
                    onAction(`place:${activeDefinition.id}:${row}:${col}`);
                  }
                }}
                key={key}
              >
                {row === 7 && (
                  <span className="coverage-placement-board__file" aria-hidden="true">
                    {String.fromCharCode(65 + col)}
                  </span>
                )}
                {col === 0 && (
                  <span className="coverage-placement-board__rank" aria-hidden="true">
                    {row + 1}
                  </span>
                )}
                {target && (
                  <span className="coverage-placement-board__target" aria-hidden="true">
                    {isCovered ? "●" : "○"}
                  </span>
                )}
                {placement && (
                  <>
                    <span className="coverage-placement-board__piece" aria-hidden="true">
                      {pieceGlyph("w", placement.piece)}
                    </span>
                    <b aria-hidden="true">{placement.cost}</b>
                  </>
                )}
              </button>
            );
          })}
        </div>

        <div className="coverage-placement-footer">
          <dl>
            <div><dt>Покрыто</dt><dd>{state.coveredTargets.length} / {state.targets.length}</dd></div>
            <div><dt>Стоимость</dt><dd>{state.totalCost}</dd></div>
            <div><dt>Фигур</dt><dd>{state.placements.length} / {state.maxPlacements}</dd></div>
          </dl>
          <div className="coverage-placement-actions">
            <button
              type="button"
              disabled={!canAct || state.placements.length === 0}
              onClick={onReset}
            >
              Вернуть в начало
            </button>
            <button
              type="button"
              className="is-primary"
              disabled={!canAct || !state.allCovered}
              onClick={onSubmit}
            >
              Зафиксировать расстановку
            </button>
          </div>
        </div>
      </div>
    </figure>
  );
}

function MovePattern({ piece }: { piece: ChessCoveragePieceType }) {
  const attacked = new Set(
    piece.offsets.map((offset) => `${offset.row + 3}:${offset.col + 3}`),
  );
  return (
    <span className="coverage-move-pattern" aria-label={`Схема хода: ${piece.moveLabel}`}>
      {Array.from({ length: 49 }, (_, index) => {
        const row = Math.floor(index / 7);
        const col = index % 7;
        return (
          <span
            className={[
              row === 3 && col === 3 ? "is-origin" : "",
              attacked.has(`${row}:${col}`) ? "is-attacked" : "",
            ].filter(Boolean).join(" ")}
            key={`${row}:${col}`}
          />
        );
      })}
    </span>
  );
}

export const chessCoverage: TaskKind<ChessCoveragePublicState> = {
  parse: parseChessCoverageState,
  renderScene: ({ state, canAct, onCommand }) => (
    <ChessCoverageScene
      state={state}
      canAct={canAct}
      onAction={(action) => onCommand(`/op ${action}`)}
      onReset={() => onCommand("/reset")}
      onSubmit={() => onCommand("/answer done")}
    />
  ),
  commands: () => ["op", "reset", "done"],
  help: () => (
    <>
      Выберите фигуру в палитре и нажмите на клетку доски.
      <br />
      <code>/reset</code> — очистить расстановку
      <br />
      <code>done</code> — зафиксировать выбранную расстановку
    </>
  ),
  opening: (_task, number) => ({
    opened: <>Открыта шахматная расстановка {number}.</>,
    guide:
      "Выберите фигуру в палитре и ставьте её на свободные клетки. Покройте все цели с минимальной стоимостью.",
  }),
  answerGuide: () => (
    <>
      Выберите тип фигуры в палитре, расставьте фигуры на доске
      и зафиксируйте решение кнопкой под доской или командой{" "}
      <code>/answer done</code>.
    </>
  ),
  commandGuide: () => (
    <>
      Нажатие на установленную фигуру убирает её ·{" "}
      <code>/reset</code> — очистить доску.
    </>
  ),
  answerExample: () => "/answer done",
  metaLines: ({ state }) => [
    `Выбрано фигур: ${state.placements.length}`,
    `Текущая стоимость: ${state.totalCost}`,
  ],
  quickActions: ({ state }) => [
    {
      label: "Сбросить",
      ariaLabel: "Сбросить шахматную расстановку",
      command: "/reset",
      disabled: state.placements.length === 0,
    },
  ],
};
