import { useState } from "react";
import { invalidResponse } from "../api/errors";
import {
  isRecord,
  readNumber,
  readString,
  type UnknownRecord,
} from "../api/parsing";
import type { PublicStateBase, TaskKind } from "./kind";
import { zendoBehaviour } from "./shared/zendo";
import {
  classificationLabel,
  readContent,
  ZendoCard,
} from "./shared/zendoCards";
import "./gridZendo.css";

export type GridZendoPublicState = {
  kind: "grid_zendo";
  family: "grid_zendo";
  variant: string;
  prompt: string;
  cards: Record<string, string[]>;
  gridSize: number;
  content: Record<string, unknown>;
  responseHint: string;
};

function parseGridZendoState(
  state: UnknownRecord,
  base: PublicStateBase,
): GridZendoPublicState {
  const variant = readString(state, "variant");
  const gridSize = readNumber(state, "gridSize", "grid_size") ?? 5;
  const cards: Record<string, string[]> = {};
  if (isRecord(state.cards)) {
    for (const [cardId, rows] of Object.entries(state.cards)) {
      if (
        Array.isArray(rows) &&
        rows.length === gridSize &&
        rows.every(
          (row) =>
            typeof row === "string" &&
            row.length === gridSize &&
            [...row].every((cell) => cell === "0" || cell === "1"),
        )
      ) {
        cards[cardId] = rows as string[];
      }
    }
  }
  if (!variant || Object.keys(cards).length === 0) {
    throw invalidResponse("Сервер вернул некорректные узоры grid_zendo.", state);
  }

  return {
    kind: "grid_zendo",
    family: "grid_zendo",
    variant,
    ...base,
    cards,
    gridSize,
    content: readContent(state),
  };
}

function GridPatternPreview({ rows }: { rows: readonly string[] }) {
  return (
    <div
      className="grid-pattern"
      style={{ gridTemplateColumns: `repeat(${rows[0]?.length ?? 5}, 1fr)` }}
      aria-hidden="true"
    >
      {rows.flatMap((row, rowIndex) =>
        [...row].map((cell, columnIndex) => (
          <i
            className={cell === "1" ? "is-filled" : ""}
            key={`${rowIndex}-${columnIndex}`}
          />
        )),
      )}
    </div>
  );
}

function GridZendoScene({
  cards,
  content,
  canProbe,
  onProbe,
}: {
  cards: Record<string, string[]>;
  content: Record<string, unknown>;
  canProbe: boolean;
  onProbe: (pattern: string) => void;
}) {
  const size = Object.values(cards)[0]?.length ?? 5;
  const [drawn, setDrawn] = useState<boolean[]>(() =>
    Array(size * size).fill(false),
  );
  const observations = Array.isArray(content.probe_observations)
    ? content.probe_observations
    : [];
  const drawnPattern = drawn
    .map((cell) => (cell ? "1" : "0"))
    .join("");

  return (
    <figure className="grid-zendo" aria-label="Узоры на сетке">
      <div className="grid-zendo__cards">
        {Object.entries(cards).map(([cardId, rows]) => (
          <ZendoCard
            className="grid-card"
            cardId={cardId}
            content={content}
            key={cardId}
          >
            <GridPatternPreview rows={rows} />
          </ZendoCard>
        ))}
        <section className="grid-card grid-card--draw">
          <header>Свой узор</header>
          <div
            className="grid-pattern grid-pattern--editable"
            style={{ gridTemplateColumns: `repeat(${size}, 1fr)` }}
            role="group"
            aria-label="Рисование узора для проверки"
          >
            {drawn.map((cell, index) => (
              <button
                type="button"
                className={cell ? "is-filled" : ""}
                aria-pressed={cell}
                aria-label={`Клетка ${Math.floor(index / size) + 1}-${
                  (index % size) + 1
                }`}
                onClick={() =>
                  setDrawn((current) =>
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
            className="grid-card__probe"
            disabled={!canProbe}
            onClick={() => onProbe(drawnPattern)}
          >
            Проверить узор
          </button>
        </section>
      </div>
      {observations.length > 0 && (
        <div className="grid-zendo__observations">
          {observations.flatMap((item, index) => {
            if (!isRecord(item) || !Array.isArray(item.pattern)) return [];
            return [
              <section className="grid-card" key={index}>
                <header>
                  Проба {index + 1}: {classificationLabel(item)}
                </header>
                <GridPatternPreview rows={item.pattern} />
              </section>,
            ];
          })}
        </div>
      )}
    </figure>
  );
}

export const gridZendo: TaskKind<GridZendoPublicState> = {
  parse: parseGridZendoState,
  renderScene: ({ state, canAct, onCommand }) => (
    <GridZendoScene
      cards={state.cards}
      content={state.content}
      canProbe={canAct}
      onProbe={(pattern) => onCommand(`/test ${pattern}`)}
    />
  ),
  ...zendoBehaviour("узор проверяется целиком"),
  opening: () => ({
    guide: (
      <>
        Нарисуйте узор на пустой сетке и проверьте его кнопкой или командой{" "}
        <code>/test</code>, затем отправьте итоговый ответ.
      </>
    ),
  }),
  commandGuide: () => (
    <>
      Пробы рисуются: закрасьте клетки в блоке «Свой узор» и
      нажмите «Проверить узор», или отправьте{" "}
      <code>/test &lt;25 нулей и единиц&gt;</code>.{" "}
      <code>/hint</code> — платная подсказка: итоговый балл умножается на 0.7.
    </>
  ),
};
