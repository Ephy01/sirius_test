import type { CSSProperties } from "react";
import { invalidResponse } from "../api/errors";
import { isRecord, parseList, type UnknownRecord } from "../api/parsing";
import {
  TASK_COMMANDS,
  type PublicStateBase,
  type TaskCommand,
  type TaskKind,
} from "./kind";
import "./blocks.css";

const TONES = ["plain", "accent", "muted", "good", "bad"] as const;

type BlockCell = {
  text: string;
  tone: (typeof TONES)[number];
  command: string | null;
};

type BlockButton = {
  label: string;
  command: string;
};

type TextBlock = { type: "text"; text: string };
type TableBlock = { type: "table"; columns: string[]; rows: string[][] };
type GridBlock = { type: "grid"; caption: string | null; cells: BlockCell[][] };
type ButtonsBlock = { type: "buttons"; items: BlockButton[] };
type FactsBlock = { type: "facts"; items: string[] };

type Block = TextBlock | TableBlock | GridBlock | ButtonsBlock | FactsBlock;

/** A scene the server describes as data, so a task module needs no client code. */
export type BlocksPublicState = {
  kind: "blocks";
  prompt: string;
  responseHint: string;
  commands: TaskCommand[];
  help: string[];
  blocks: Block[];
};

function parseText(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function parseChatCommand(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function parseCell(value: unknown): BlockCell | null {
  if (!isRecord(value)) return null;
  const tone = TONES.find((name) => name === value.tone);
  const given = value.command ?? null;
  const command = parseChatCommand(given);
  if (typeof value.text !== "string" || !tone) return null;
  if (given !== null && !command) return null;
  return { text: value.text, tone, command };
}

function parseButton(value: unknown): BlockButton | null {
  if (!isRecord(value)) return null;
  const command = parseChatCommand(value.command);
  if (typeof value.label !== "string" || !value.label.trim() || !command) {
    return null;
  }
  return { label: value.label, command };
}

function parseTable(value: UnknownRecord): TableBlock | null {
  const columns = parseList(value.columns, parseText);
  const rows = parseList(value.rows, (row) => parseList(row, parseText));
  if (!columns || !rows?.every((row) => row.length === columns.length)) {
    return null;
  }
  return { type: "table", columns, rows };
}

function parseGrid(value: UnknownRecord): GridBlock | null {
  const caption = value.caption ?? null;
  const cells = parseList(value.cells, (row) => parseList(row, parseCell));
  if (caption !== null && typeof caption !== "string") return null;
  if (!cells?.[0]?.length) return null;
  if (cells.some((row) => row.length !== cells[0].length)) return null;
  return { type: "grid", caption, cells };
}

function parseBlock(value: unknown): Block | null {
  if (!isRecord(value)) return null;
  if (value.type === "text") {
    const text = parseText(value.text);
    return text === null ? null : { type: "text", text };
  }
  if (value.type === "table") return parseTable(value);
  if (value.type === "grid") return parseGrid(value);
  if (value.type === "buttons") {
    const items = parseList(value.items, parseButton);
    return items && { type: "buttons", items };
  }
  if (value.type === "facts") {
    const items = parseList(value.items, parseText);
    return items && { type: "facts", items };
  }
  return null;
}

function parseBlocksState(
  state: UnknownRecord,
  base: PublicStateBase,
): BlocksPublicState {
  const commands = parseList(
    state.commands,
    (name) => TASK_COMMANDS.find((command) => command === name) ?? null,
  );
  const help = parseList(state.help, parseText);
  const blocks = parseList(state.blocks, parseBlock);
  const responseHint = state.response_hint;
  if (
    !commands ||
    !help ||
    !blocks ||
    (responseHint !== undefined && typeof responseHint !== "string")
  ) {
    throw invalidResponse("Сервер вернул некорректную сцену задачи.", state);
  }

  return { kind: "blocks", ...base, commands, help, blocks };
}

function Grid({
  block,
  canAct,
  onCommand,
}: {
  block: GridBlock;
  canAct: boolean;
  onCommand: (command: string) => void;
}) {
  const columns = block.cells[0].length;
  return (
    <figure
      className="blocks-grid"
      aria-label={
        block.caption ? undefined : `Поле ${block.cells.length} на ${columns}`
      }
    >
      {block.caption && <figcaption>{block.caption}</figcaption>}
      <div
        className="blocks-grid__cells"
        style={{ "--blocks-columns": columns } as CSSProperties}
      >
        {block.cells.map((row, rowIndex) =>
          row.map((cell, columnIndex) => {
            const className = `blocks-cell blocks-cell--${cell.tone}`;
            const key = `${rowIndex}:${columnIndex}`;
            const { command } = cell;
            if (command === null) {
              return (
                <span className={className} key={key}>
                  {cell.text}
                </span>
              );
            }
            const position = `Строка ${rowIndex + 1}, столбец ${
              columnIndex + 1
            }`;
            return (
              <button
                type="button"
                className={className}
                disabled={!canAct}
                aria-label={cell.text ? `${position}: ${cell.text}` : position}
                onClick={() => onCommand(command)}
                key={key}
              >
                {cell.text}
              </button>
            );
          }),
        )}
      </div>
    </figure>
  );
}

function Table({ block }: { block: TableBlock }) {
  return (
    <div className="blocks-table-wrap">
      <table className="blocks-table">
        <thead>
          <tr>
            {block.columns.map((column, index) => (
              <th key={index} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BlockView({
  block,
  canAct,
  onCommand,
}: {
  block: Block;
  canAct: boolean;
  onCommand: (command: string) => void;
}) {
  if (block.type === "text") return <p className="blocks-text">{block.text}</p>;
  if (block.type === "table") return <Table block={block} />;
  if (block.type === "grid") {
    return <Grid block={block} canAct={canAct} onCommand={onCommand} />;
  }
  if (block.type === "buttons") {
    return (
      <div className="blocks-buttons" role="group" aria-label="Действия">
        {block.items.map((item, index) => (
          <button
            type="button"
            disabled={!canAct}
            onClick={() => onCommand(item.command)}
            key={index}
          >
            {item.label}
          </button>
        ))}
      </div>
    );
  }
  return (
    <ul className="blocks-facts">
      {block.items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}

/** A block with nothing to show, such as `facts()` without lines, leaves no gap. */
function hasContent(block: Block): boolean {
  if (block.type === "text") return block.text !== "";
  if (block.type === "table") return block.columns.length > 0;
  return block.type === "grid" || block.items.length > 0;
}

export const blocks: TaskKind<BlocksPublicState> = {
  parse: parseBlocksState,
  renderScene: ({ state, canAct, onCommand }) => {
    const visible = state.blocks.filter(hasContent);
    if (visible.length === 0) return null;
    return (
      <div className="blocks-scene">
        {visible.map((block, index) => (
          <BlockView
            block={block}
            canAct={canAct}
            onCommand={onCommand}
            key={index}
          />
        ))}
      </div>
    );
  },
  commands: ({ state }) => state.commands,
  help: ({ state }) =>
    state.help.length > 0
      ? state.help.map((line, index) => (
          <span key={index}>
            {index > 0 && <br />}
            {line}
          </span>
        ))
      : undefined,
};
