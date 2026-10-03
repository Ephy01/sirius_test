import { invalidResponse } from "../api/errors";
import { isRecord, readString, type UnknownRecord } from "../api/parsing";
import type { PublicStateBase, TaskKind } from "./kind";
import {
  PIECE_GLYPHS,
  pieceGlyph,
  type ChessBoardPieceSymbol,
  type ChessPieceSymbol,
} from "./shared/chess";

export type ChessBoardState = (ChessBoardPieceSymbol | null)[][];

export type DiceDefinition = {
  id: string;
  label: string;
  faces: ChessPieceSymbol[];
};

export type DiceChessPositionPublicState = {
  kind: "dice_chess_position_probability";
  prompt: string;
  board: ChessBoardState;
  sideToMove: "white" | "black";
  die: DiceDefinition;
  eventDescription: string;
  responseHint: string;
};

export type DiceChessInventoryPublicState = {
  kind: "dice_chess_board_inventory_probability";
  prompt: string;
  board: ChessBoardState;
  die: DiceDefinition;
  eventDescription: string;
  responseHint: string;
};

const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"] as const;

const PIECE_NAMES: Record<ChessBoardPieceSymbol, string> = {
  wK: "белый король",
  wQ: "белый ферзь",
  wR: "белая ладья",
  wB: "белый слон",
  wN: "белый конь",
  wP: "белая пешка",
  bK: "чёрный король",
  bQ: "чёрный ферзь",
  bR: "чёрная ладья",
  bB: "чёрный слон",
  bN: "чёрный конь",
  bP: "чёрная пешка",
};

const DICE_FACE_NAMES: Record<ChessPieceSymbol, string> = {
  K: "король",
  Q: "ферзь",
  R: "ладья",
  B: "слон",
  N: "конь",
  P: "пешка",
};

function isChessPieceSymbol(value: unknown): value is ChessPieceSymbol {
  return (
    value === "K" ||
    value === "Q" ||
    value === "R" ||
    value === "B" ||
    value === "N" ||
    value === "P"
  );
}

function isChessBoardCell(
  value: unknown,
): value is ChessBoardPieceSymbol | null {
  return (
    value === null ||
    (typeof value === "string" &&
      value.length === 2 &&
      (value[0] === "w" || value[0] === "b") &&
      isChessPieceSymbol(value[1]))
  );
}

function parseDiceDefinition(value: unknown): DiceDefinition | null {
  if (!isRecord(value)) return null;
  const faces: unknown[] =
    typeof value.faces === "string"
      ? Array.from(value.faces)
      : Array.isArray(value.faces)
        ? value.faces
        : [];
  if (faces.length !== 6 || !faces.every(isChessPieceSymbol)) return null;
  return {
    id: readString(value, "id") ?? "die-1",
    label: readString(value, "label") ?? "Кубик 1",
    faces,
  };
}

function parseChessBoard(value: unknown): ChessBoardState | null {
  if (!Array.isArray(value) || value.length !== 8) return null;
  const board: ChessBoardState = [];
  for (const rank of value) {
    if (
      !Array.isArray(rank) ||
      rank.length !== 8 ||
      !rank.every(isChessBoardCell)
    ) {
      return null;
    }
    board.push([...rank]);
  }
  return board;
}

function parseBoardAndDie(state: UnknownRecord) {
  return {
    board: parseChessBoard(state.board),
    die: parseDiceDefinition(state.die),
    eventDescription: readString(
      state,
      "eventDescription",
      "event_description",
    ),
  };
}

function parseInventoryState(
  state: UnknownRecord,
  base: PublicStateBase,
): DiceChessInventoryPublicState {
  const { board, die, eventDescription } = parseBoardAndDie(state);
  if (!board || !die || !eventDescription) {
    throw invalidResponse(
      "Сервер вернул некорректную задачу Dice & Chess.",
      state,
    );
  }
  return {
    kind: "dice_chess_board_inventory_probability",
    ...base,
    board,
    die,
    eventDescription,
  };
}

function parsePositionState(
  state: UnknownRecord,
  base: PublicStateBase,
): DiceChessPositionPublicState {
  const { board, die, eventDescription } = parseBoardAndDie(state);
  const sideToMove = readString(state, "sideToMove", "side_to_move");
  if (
    !board ||
    !die ||
    !eventDescription ||
    (sideToMove !== "white" && sideToMove !== "black")
  ) {
    throw invalidResponse(
      "Сервер вернул некорректную позицию Dice & Chess.",
      state,
    );
  }
  return {
    kind: "dice_chess_position_probability",
    ...base,
    board,
    sideToMove,
    die,
    eventDescription,
  };
}

function DicePositionScene({
  board,
  die,
  sideToMove = "white",
}: {
  board: ChessBoardState;
  die: DiceDefinition;
  sideToMove?: "white" | "black";
}) {
  return (
    <div className="dice-position-scene">
      <Chessboard board={board} />

      <section className="position-die" aria-label="Кубик текущего хода">
        <p>Грани кубика</p>
        <ol aria-label={`Грани: ${die.label}`}>
          {die.faces.map((face, faceIndex) => (
            <li
              title={DICE_FACE_NAMES[face]}
              aria-label={`Грань ${faceIndex + 1}: ${DICE_FACE_NAMES[face]}`}
              key={`${die.id}-${faceIndex}`}
            >
              <span aria-hidden="true">
                {pieceGlyph(sideToMove === "black" ? "b" : "w", face)}
              </span>
              <small>{DICE_FACE_NAMES[face]}</small>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function Chessboard({ board }: { board: ChessBoardState }) {
  const rowCount = board.length;
  const colCount = Math.max(1, ...board.map((rank) => rank.length));

  return (
    <div className="chess-position chess-position--compact">
      <div
        className="chessboard"
        role="grid"
        aria-label="Шахматная доска, белые снизу"
        style={{
          gridTemplateColumns: `repeat(${colCount}, 1fr)`,
          gridTemplateRows: `repeat(${Math.max(1, rowCount)}, 1fr)`,
          aspectRatio: `${colCount} / ${Math.max(1, rowCount)}`,
        }}
      >
        {board.flatMap((rank, rankIndex) =>
          rank.map((piece, fileIndex) => {
            const rankNumber = rowCount - rankIndex;
            const coordinate = `${FILES[fileIndex] ?? "?"}${rankNumber}`;
            const isDark = (rankIndex + fileIndex) % 2 === 1;

            return (
              <div
                className={`chess-square${isDark ? " chess-square--dark" : ""}`}
                role="gridcell"
                aria-label={`${coordinate}: ${piece ? PIECE_NAMES[piece] : "пусто"}`}
                key={coordinate}
              >
                {fileIndex === 0 && (
                  <span className="chess-square__rank" aria-hidden="true">
                    {rankNumber}
                  </span>
                )}
                {rankIndex === rowCount - 1 && (
                  <span className="chess-square__file" aria-hidden="true">
                    {FILES[fileIndex]}
                  </span>
                )}
                {piece && (
                  <span
                    className={`chess-piece ${
                      piece.startsWith("w")
                        ? "chess-piece--white"
                        : "chess-piece--black"
                    }`}
                    aria-hidden="true"
                  >
                    {PIECE_GLYPHS[piece]}
                  </span>
                )}
              </div>
            );
          }),
        )}
      </div>
    </div>
  );
}

const DICE_BEHAVIOUR = {
  statement: ({ state }) => ({
    prompt: state.prompt.replace(
      /\s*Найдите вероятность описанного события\.\s*$/u,
      "",
    ),
    question: `Найдите вероятность того, что ${state.eventDescription
      .charAt(0)
      .toLocaleLowerCase("ru-RU")}${state.eventDescription.slice(1)}`,
  }),
  answerExample: () => "/answer 5/12",
} satisfies Partial<
  TaskKind<DiceChessInventoryPublicState | DiceChessPositionPublicState>
>;

export const diceChessInventory: TaskKind<DiceChessInventoryPublicState> = {
  parse: parseInventoryState,
  renderScene: ({ state }) => (
    <DicePositionScene board={state.board} die={state.die} />
  ),
  ...DICE_BEHAVIOUR,
};

export const diceChessPosition: TaskKind<DiceChessPositionPublicState> = {
  parse: parsePositionState,
  renderScene: ({ state }) => (
    <DicePositionScene
      board={state.board}
      die={state.die}
      sideToMove={state.sideToMove}
    />
  ),
  ...DICE_BEHAVIOUR,
};
