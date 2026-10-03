import { invalidResponse } from "../api/errors";
import {
  isRecord,
  readString,
  readStringList,
  type UnknownRecord,
} from "../api/parsing";
import type { PublicStateBase, TaskKind } from "./kind";
import "./classicMath.css";

export type ClassicMathSubKind = "share_paradox" | "bar_seating";

export type ClassicMathTable = {
  columns: string[];
  rows: string[][];
};

export type ClassicMathPublicState = {
  kind: "classic_math_free_response";
  family: "classic_math";
  subKind: ClassicMathSubKind;
  title: string;
  prompt: string;
  responseHint: string;
  submissionTemplate: string;
  answerFormat: "free_response";
  scripted: true;
  table?: ClassicMathTable;
};

function parseClassicMathState(
  state: UnknownRecord,
  base: PublicStateBase,
): ClassicMathPublicState {
  const family = readString(state, "family");
  const subKind = readString(state, "subKind", "sub_kind");
  const title = readString(state, "title");
  const answerFormat = readString(state, "answerFormat", "answer_format");
  const submissionTemplate = readString(
    state,
    "submissionTemplate",
    "submission_template",
  );
  if (
    family !== "classic_math" ||
    (subKind !== "share_paradox" && subKind !== "bar_seating") ||
    !title ||
    !submissionTemplate ||
    answerFormat !== "free_response"
  ) {
    throw invalidResponse("Сервер вернул некорректную классическую задачу.", state);
  }

  let table: ClassicMathTable | undefined;
  if (isRecord(state.table) && Array.isArray(state.table.columns)) {
    const columns = readStringList(state.table.columns);
    const rows = Array.isArray(state.table.rows)
      ? state.table.rows.flatMap((row): string[][] =>
          Array.isArray(row) &&
          row.length === columns.length &&
          row.every((cell) => typeof cell === "string")
            ? [row as string[]]
            : [],
        )
      : [];
    if (
      columns.length === state.table.columns.length &&
      columns.length > 0 &&
      rows.length > 0
    ) {
      table = { columns, rows };
    }
  }

  return {
    kind: "classic_math_free_response",
    family,
    subKind,
    title,
    ...base,
    submissionTemplate,
    answerFormat,
    scripted: true,
    table,
  };
}

export const classicMath: TaskKind<ClassicMathPublicState> = {
  textOnly: () => true,
  parse: parseClassicMathState,
  renderScene: () => null,
  statement: ({ state }) => ({
    heading: state.title,
    appendix: state.table && (
      <div className="classic-math-table-wrap">
        <table className="classic-math-table">
          <thead>
            <tr>
              {state.table.columns.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {state.table.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ),
  }),
  answerGuide: ({ state }) => (
    <>
      Ответ отправьте в чате одной командой по шаблону:
      <code className="classic-math-submission-template">
        {state.submissionTemplate.replace(/\s*\n+\s*/gu, " ")}
      </code>
    </>
  ),
  answerExample: () => "/answer <развёрнутое решение>",
};
