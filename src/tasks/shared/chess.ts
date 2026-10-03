import { isRecord, readNumber } from "../../api/parsing";

export type ChessPieceSymbol = "K" | "Q" | "R" | "B" | "N" | "P";
export type ChessBoardPieceSymbol = `w${ChessPieceSymbol}` | `b${ChessPieceSymbol}`;

export type BoardPoint = {
  row: number;
  col: number;
};

export const PIECE_GLYPHS: Record<ChessBoardPieceSymbol, string> = {
  wK: "♔",
  wQ: "♕",
  wR: "♖",
  wB: "♗",
  wN: "♘",
  wP: "♙",
  bK: "♚",
  bQ: "♛",
  bR: "♜",
  bB: "♝",
  bN: "♞",
  bP: "♟",
};

export function pieceGlyph(color: "w" | "b", piece: ChessPieceSymbol): string {
  return PIECE_GLYPHS[`${color}${piece}`];
}

export function parseBoardPoint(value: unknown): BoardPoint | null {
  if (!isRecord(value)) return null;
  const row = readNumber(value, "row");
  const col = readNumber(value, "col");
  if (
    row === undefined ||
    col === undefined ||
    !Number.isInteger(row) ||
    !Number.isInteger(col)
  ) {
    return null;
  }
  return { row, col };
}

export function parseBoardPoints(value: unknown): BoardPoint[] | null {
  if (!Array.isArray(value)) return [];
  const points = value.map(parseBoardPoint);
  return points.every((point): point is BoardPoint => point !== null)
    ? points
    : null;
}
