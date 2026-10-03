import { Fragment } from "react";
import { isRecord, type ParticipantTask } from "../api";
import { taskTraits } from "./taskTraits";

function DotSeparated({ items }: { items: string[] }) {
  return (
    <>
      {items.map((item, index) => (
        <Fragment key={index}>
          {index > 0 && (
            <span className="sep-dot" aria-hidden="true">
              ·
            </span>
          )}
          {item}
        </Fragment>
      ))}
    </>
  );
}

export function TaskBrief({
  task,
  canAct,
  onCommand,
}: {
  task: ParticipantTask;
  canAct: boolean;
  onCommand: (command: string) => void;
}) {
  const state = task.publicState;
  const {
    diceChess,
    classicMath,
    isZendo,
    isMachine,
    isWiring,
    isChessCoverage,
  } = taskTraits(task);
  const rawStatementPrompt = diceChess
    ? state.prompt.replace(
        /\s*Найдите вероятность описанного события\.\s*$/u,
        "",
      )
    : state.prompt;
  const statementPrompt = task.family === "geo_zendo"
    ? rawStatementPrompt
        .replaceAll("Конструкции", "Графы")
        .replaceAll("конструкции", "графы")
        .replaceAll("конструкций", "графов")
    : rawStatementPrompt;
  const statementQuestion = diceChess
    ? `Найдите вероятность того, что ${diceChess.eventDescription
        .charAt(0)
        .toLocaleLowerCase("ru-RU")}${diceChess.eventDescription.slice(1)}`
    : undefined;
  const statementParagraphs = statementPrompt
    .split(/\n{2,}/u)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  const zendoContent: Record<string, unknown> =
    "content" in state ? state.content : {};
  const zendoProbesRemaining =
    typeof zendoContent.probes_remaining === "number"
      ? zendoContent.probes_remaining
      : undefined;
  const zendoTargetCount = Array.isArray(zendoContent.targets)
    ? zendoContent.targets.length
    : 0;
  const zendoAnswerExample = `/answer ${Array.from(
    { length: Math.max(1, zendoTargetCount) },
    (_, index) => (index % 2 === 0 ? "1" : "0"),
  ).join(" ")}`;
  const transformOptions = Array.isArray(zendoContent.answer_cards)
    ? zendoContent.answer_cards.flatMap((option: unknown) =>
        isRecord(option) && "id" in option
          ? [
              {
                id: String(option.id),
                label: String("label" in option ? option.label : option.id),
              },
            ]
          : [],
      )
    : [];
  const briefMetaLines: string[] = [];
  if (isZendo && zendoProbesRemaining !== undefined) {
    briefMetaLines.push(`Осталось проб: ${zendoProbesRemaining}`);
  }
  if (state.kind === "hidden_wiring") {
    briefMetaLines.push(
      `Доступно проб: ${state.chordsRemaining} / ${state.chordBudget}`,
    );
    if (state.examChords && state.examChords.length > 0) {
      briefMetaLines.push(
        "экзаменационные комбинации (недоступны для проб): " +
          state.examChords.map((chord) => chord.id).join(", "),
      );
    }
  }
  if (state.kind === "machine_panel") {
    briefMetaLines.push(`Шагов: ${state.stepsTaken} / ${state.stepsSoftCap}`);
  }
  if (state.kind === "chess") {
    briefMetaLines.push(
      `Фигура: (${state.current.row + 1}, ${state.current.col + 1})`,
      `Цель: (${state.target.row + 1}, ${state.target.col + 1})`,
      `Шагов: ${state.stepsTaken} / ${state.stepsSoftCap}`,
    );
  }
  if (state.kind === "chess_coverage") {
    briefMetaLines.push(
      `Выбрано фигур: ${state.placements.length}`,
      `Текущая стоимость: ${state.totalCost}`,
    );
  }
  if (state.kind === "fold_punch") {
    briefMetaLines.push(
      "сгибы выполняются по порядку; дырки пробиты через все слои сразу",
    );
  }
  if (state.kind === "grid_zendo") {
    briefMetaLines.push("узор проверяется целиком");
  }
  if (state.kind === "token_zendo") {
    briefMetaLines.push("цвет и число каждой фишки видны на полке");
  }
  if (state.kind === "geometry_atlas" || state.kind === "point_zendo") {
    briefMetaLines.push("все рисунки даны в одной системе обозначений");
  }

  return (
    <article
      className={`participant-brief${
        classicMath ? " participant-brief--classic" : ""
      }`}
      data-tour="task-statement"
    >
      <div className="participant-brief__statement">
        {classicMath && <h2>{classicMath.title}</h2>}
        {statementParagraphs.map((paragraph, index) => (
          <p key={`${task.id}-paragraph-${index}`}>{paragraph}</p>
        ))}
        {statementQuestion && <p>{statementQuestion}</p>}
        {classicMath?.table && (
          <div className="classic-math-table-wrap">
            <table className="classic-math-table">
              <thead>
                <tr>
                  {classicMath.table.columns.map((column) => (
                    <th key={column} scope="col">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {classicMath.table.rows.map((row, rowIndex) => (
                  <tr key={`${task.id}-table-row-${rowIndex}`}>
                    {row.map((cell, cellIndex) => (
                      <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="participant-brief__answer">
        {!(
          state.kind === "hidden_wiring" &&
          state.variant === "reach_target"
        ) && (
          <p>
            {isWiring ? (
              <>
                Ответ отправьте в чате (пример:{" "}
                <code>/answer 1101 0000 1000</code> — три битовые
                строки по лампам экзаменационных комбинаций, 1 —
                лампа переключится).
              </>
            ) : isChessCoverage ? (
              <>
                Выберите тип фигуры в палитре, расставьте фигуры на доске
                и зафиксируйте решение кнопкой под доской или командой{" "}
                <code>/answer done</code>.
              </>
            ) : isMachine ? (
              <>
                Ответ отправьте в чате: <code>done</code> — когда решение
                найдено, <code>impossible</code> — если цель недостижима.
              </>
            ) : isZendo ? (
              <>
                Ответ отправьте в чате (пример:{" "}
                <code>{zendoAnswerExample}</code> — по одному значению для
                каждой из {zendoTargetCount || "показанных"} целей в их
                порядке, 1 — подходит, 0 — нет).
              </>
            ) : state.kind === "fold_punch" ? (
              <>
                Кликните клетки на развёрнутом листе и нажмите «Отправить
                отмеченные клетки», или отправьте ответ в чате (пример:{" "}
                <code>/answer 2,3 5,8</code> — строка,столбец).
              </>
            ) : classicMath ? (
              <>
                Ответ отправьте в чате одной командой по шаблону:
                <code className="classic-math-submission-template">
                  {classicMath.submissionTemplate.replace(
                    /\s*\n+\s*/gu,
                    " ",
                  )}
                </code>
              </>
            ) : (
              <>
                Ответ отправьте в чате командой{" "}
                <code>/answer &lt;ваш ответ&gt;</code>.
              </>
            )}
          </p>
        )}
        {(isMachine || isZendo || isChessCoverage) && (
          <p>
            {isChessCoverage ? (
              <>
                Нажатие на установленную фигуру убирает её ·{" "}
                <code>/reset</code> — очистить доску.
              </>
            ) : isMachine ? (
              <>
                <code>/op &lt;id&gt;</code> — применить операцию ·{" "}
                <code>/undo</code> — отменить последний шаг.
              </>
            ) : state.kind === "grid_zendo" ? (
              <>
                Пробы рисуются: закрасьте клетки в блоке «Свой узор» и
                нажмите «Проверить узор», или отправьте{" "}
                <code>/test &lt;25 нулей и единиц&gt;</code>.{" "}
                <code>/hint</code> — платная подсказка: итоговый балл умножается на 0.7.
              </>
            ) : (
              <>
                <code>/test &lt;код&gt;</code> — проверить одну из
                карточек-проб · <code>/hint</code> — платная подсказка:
                итоговый балл умножается на 0.7.
              </>
            )}
          </p>
        )}
        {transformOptions.length > 0 && (
          <div
            className="transform-options"
            role="group"
            aria-label="Варианты преобразования"
          >
            {transformOptions.map((option) => (
              <button
                type="button"
                disabled={!canAct}
                onClick={() => onCommand(`/answer ${option.id}`)}
                key={option.id}
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
        {briefMetaLines.length > 0 && (
          <p className="participant-brief__meta">
            <DotSeparated items={briefMetaLines} />
          </p>
        )}
      </div>
    </article>
  );
}
