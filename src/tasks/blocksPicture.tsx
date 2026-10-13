import type { KeyboardEvent, ReactNode } from "react";
import { isRecord, parseList, type UnknownRecord } from "../api/parsing";
import { parseOptionalCommand, parseTone, type Tone } from "./blocksParts";

type Pair = [number, number];

type Shape =
  | { shape: "point"; x: number; y: number; label: string }
  | { shape: "line"; x1: number; y1: number; x2: number; y2: number; dashed: boolean }
  | { shape: "polygon"; points: Pair[]; filled: boolean }
  | { shape: "circle"; x: number; y: number; radius: number; filled: boolean }
  | { shape: "ellipse"; x: number; y: number; radiusX: number; radiusY: number; filled: boolean }
  | { shape: "sector" | "arc"; x: number; y: number; radius: number; start: number; end: number }
  | { shape: "label"; x: number; y: number; text: string };

type DrawnShape = Shape & { tone: Tone; command: string | null };

export type PictureBlock = {
  type: "picture";
  x: Pair;
  y: Pair;
  grid: boolean;
  caption: string | null;
  shapes: DrawnShape[];
};

/** Longer side of a drawing in SVG units. */
const SIZE = 480;
const MAX_GRID_LINES = 60;
const POINT_RADIUS = 5;

function numbers(record: UnknownRecord, ...keys: string[]): number[] | null {
  const values = keys.map((key) => record[key]);
  return values.every((value) => typeof value === "number" && Number.isFinite(value))
    ? (values as number[])
    : null;
}

function parsePair(value: unknown): Pair | null {
  return Array.isArray(value) &&
    value.length === 2 &&
    value.every((item) => typeof item === "number" && Number.isFinite(item))
    ? [value[0], value[1]]
    : null;
}

function parseOutline(value: UnknownRecord): Shape | null {
  if (value.shape === "point") {
    const at = numbers(value, "x", "y");
    if (!at || typeof value.label !== "string") return null;
    return { shape: "point", x: at[0], y: at[1], label: value.label };
  }
  if (value.shape === "line") {
    const ends = numbers(value, "x1", "y1", "x2", "y2");
    if (!ends) return null;
    const [x1, y1, x2, y2] = ends;
    return { shape: "line", x1, y1, x2, y2, dashed: value.dashed === true };
  }
  if (value.shape === "polygon") {
    const points = parseList(value.points, parsePair);
    if (!points || points.length < 3) return null;
    return { shape: "polygon", points, filled: value.filled === true };
  }
  if (value.shape === "circle") {
    const at = numbers(value, "x", "y", "radius");
    if (!at || at[2] <= 0) return null;
    return { shape: "circle", x: at[0], y: at[1], radius: at[2], filled: value.filled === true };
  }
  if (value.shape === "ellipse") {
    const at = numbers(value, "x", "y", "radius_x", "radius_y");
    if (!at || at[2] <= 0 || at[3] <= 0) return null;
    const [x, y, radiusX, radiusY] = at;
    return { shape: "ellipse", x, y, radiusX, radiusY, filled: value.filled === true };
  }
  if (value.shape === "sector" || value.shape === "arc") {
    const at = numbers(value, "x", "y", "radius", "start", "end");
    if (!at || at[2] <= 0) return null;
    const [x, y, radius, start, end] = at;
    return { shape: value.shape, x, y, radius, start, end };
  }
  if (value.shape === "label") {
    const at = numbers(value, "x", "y");
    if (!at || typeof value.text !== "string") return null;
    return { shape: "label", x: at[0], y: at[1], text: value.text };
  }
  return null;
}

function parseShape(value: unknown): DrawnShape | null {
  if (!isRecord(value)) return null;
  const outline = parseOutline(value);
  const tone = parseTone(value.tone);
  const command = parseOptionalCommand(value.command);
  if (!outline || !tone || command === undefined) return null;
  return { ...outline, tone, command };
}

export function parsePicture(value: UnknownRecord): PictureBlock | null {
  const x = parsePair(value.x);
  const y = parsePair(value.y);
  const shapes = parseList(value.shapes, parseShape);
  const caption = value.caption ?? null;
  if (!x || !y || x[0] >= x[1] || y[0] >= y[1] || !shapes) return null;
  if (caption !== null && typeof caption !== "string") return null;
  return { type: "picture", x, y, grid: value.grid === true, caption, shapes };
}

/** Maps the coordinates of a task, where the y axis points up, to the units of the drawing. */
function frame({ x, y }: PictureBlock) {
  const unit = SIZE / Math.max(x[1] - x[0], y[1] - y[0]);
  return {
    unit,
    width: (x[1] - x[0]) * unit,
    height: (y[1] - y[0]) * unit,
    left: (value: number) => (value - x[0]) * unit,
    top: (value: number) => (y[1] - value) * unit,
  };
}

type Frame = ReturnType<typeof frame>;

function wholeNumbers([low, high]: Pair): number[] {
  const first = Math.ceil(low);
  const count = Math.floor(high) - first + 1;
  return count > 0 && count <= MAX_GRID_LINES
    ? Array.from({ length: count }, (_, index) => first + index)
    : [];
}

function GridLines({ block, view }: { block: PictureBlock; view: Frame }) {
  return (
    <g className="blocks-picture__grid">
      {wholeNumbers(block.x).map((value) => (
        <line
          className={value === 0 ? "blocks-picture__axis" : undefined}
          x1={view.left(value)}
          x2={view.left(value)}
          y1={0}
          y2={view.height}
          key={`x${value}`}
        />
      ))}
      {wholeNumbers(block.y).map((value) => (
        <line
          className={value === 0 ? "blocks-picture__axis" : undefined}
          x1={0}
          x2={view.width}
          y1={view.top(value)}
          y2={view.top(value)}
          key={`y${value}`}
        />
      ))}
    </g>
  );
}

/** The path of an arc drawn counterclockwise, as angles are counted in mathematics. */
function arcPath(shape: Extract<Shape, { shape: "sector" | "arc" }>, view: Frame) {
  const at = (degrees: number) => {
    const angle = (degrees * Math.PI) / 180;
    return `${view.left(shape.x + shape.radius * Math.cos(angle))} ${view.top(
      shape.y + shape.radius * Math.sin(angle),
    )}`;
  };
  const radius = shape.radius * view.unit;
  const turn = (((shape.end - shape.start) % 360) + 360) % 360;
  const middle = shape.start + (turn || 360) / 2;
  // A full turn has equal ends, which an SVG arc cannot draw, so it goes in two halves.
  const curve =
    turn === 0
      ? `A ${radius} ${radius} 0 0 0 ${at(middle)} A ${radius} ${radius} 0 0 0 ${at(shape.end)}`
      : `A ${radius} ${radius} 0 ${turn > 180 ? 1 : 0} 0 ${at(shape.end)}`;
  return shape.shape === "sector"
    ? `M ${view.left(shape.x)} ${view.top(shape.y)} L ${at(shape.start)} ${curve} Z`
    : `M ${at(shape.start)} ${curve}`;
}

function outline(shape: DrawnShape, view: Frame): ReactNode {
  const filled = "filled" in shape && shape.filled ? " blocks-shape--filled" : "";
  if (shape.shape === "point") {
    return (
      <>
        <circle className="blocks-shape--dot" cx={view.left(shape.x)} cy={view.top(shape.y)} r={POINT_RADIUS} />
        {shape.label && (
          <text className="blocks-shape--text" x={view.left(shape.x) + 9} y={view.top(shape.y) - 9}>
            {shape.label}
          </text>
        )}
      </>
    );
  }
  if (shape.shape === "line") {
    return (
      <line
        className={shape.dashed ? "blocks-shape--dashed" : undefined}
        x1={view.left(shape.x1)}
        y1={view.top(shape.y1)}
        x2={view.left(shape.x2)}
        y2={view.top(shape.y2)}
      />
    );
  }
  if (shape.shape === "polygon") {
    const points = shape.points.map(([x, y]) => `${view.left(x)},${view.top(y)}`).join(" ");
    return <polygon className={filled.trim() || undefined} points={points} />;
  }
  if (shape.shape === "circle") {
    return (
      <circle
        className={filled.trim() || undefined}
        cx={view.left(shape.x)}
        cy={view.top(shape.y)}
        r={shape.radius * view.unit}
      />
    );
  }
  if (shape.shape === "ellipse") {
    return (
      <ellipse
        className={filled.trim() || undefined}
        cx={view.left(shape.x)}
        cy={view.top(shape.y)}
        rx={shape.radiusX * view.unit}
        ry={shape.radiusY * view.unit}
      />
    );
  }
  if (shape.shape === "label") {
    return (
      <text className="blocks-shape--text blocks-shape--centered" x={view.left(shape.x)} y={view.top(shape.y)}>
        {shape.text}
      </text>
    );
  }
  return (
    <path
      className={shape.shape === "sector" ? "blocks-shape--filled" : undefined}
      d={arcPath(shape, view)}
    />
  );
}

const SHAPE_NAMES: Record<Shape["shape"], string> = {
  point: "Точка",
  line: "Отрезок",
  polygon: "Многоугольник",
  circle: "Окружность",
  ellipse: "Эллипс",
  sector: "Сектор",
  arc: "Дуга",
  label: "Подпись",
};

function ShapeView({
  shape,
  view,
  canAct,
  onCommand,
}: {
  shape: DrawnShape;
  view: Frame;
  canAct: boolean;
  onCommand: (command: string) => void;
}) {
  const className = `blocks-shape blocks-shape--${shape.tone}`;
  const { command } = shape;
  if (command === null) return <g className={className}>{outline(shape, view)}</g>;

  const name = shape.shape === "point" && shape.label ? `Точка ${shape.label}` : SHAPE_NAMES[shape.shape];
  return (
    <g
      className={`${className} blocks-shape--action`}
      role="button"
      tabIndex={canAct ? 0 : -1}
      aria-label={name}
      aria-disabled={!canAct}
      onClick={canAct ? () => onCommand(command) : undefined}
      onKeyDown={
        canAct
          ? (event: KeyboardEvent) => {
              if (event.key !== "Enter" && event.key !== " ") return;
              event.preventDefault();
              onCommand(command);
            }
          : undefined
      }
    >
      {outline(shape, view)}
    </g>
  );
}

/** A drawing on the coordinate plane assembled from the shapes a task sent. */
export function Picture({
  block,
  canAct,
  onCommand,
}: {
  block: PictureBlock;
  canAct: boolean;
  onCommand: (command: string) => void;
}) {
  const view = frame(block);
  return (
    <figure className="blocks-picture">
      {block.caption && <figcaption>{block.caption}</figcaption>}
      <svg
        viewBox={`0 0 ${view.width} ${view.height}`}
        style={{ maxWidth: view.width }}
        role="group"
        aria-label={block.caption ?? "Рисунок к задаче"}
      >
        {block.grid && <GridLines block={block} view={view} />}
        {block.shapes.map((shape, index) => (
          <ShapeView shape={shape} view={view} canAct={canAct} onCommand={onCommand} key={index} />
        ))}
      </svg>
    </figure>
  );
}
