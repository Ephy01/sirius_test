import { isRecord, readNumber, readString } from "../../api/parsing";
import { ZendoCard } from "./zendoCards";
import "./geometry.css";

export type GeometryPoint = {
  id: string;
  group: string;
  x: number;
  y: number;
  label?: string;
  color?: string;
};

export type GeometryEdge = {
  id: string;
  group: string;
  source: string;
  target: string;
  color?: string;
};

export type GeometryScene = {
  bounds: {
    minX: number;
    maxX: number;
    minY: number;
    maxY: number;
  };
  points: GeometryPoint[];
  edges: GeometryEdge[];
};

export function parseGeometryScene(value: unknown): GeometryScene | null {
  if (!isRecord(value) || !isRecord(value.bounds)) return null;
  const minX = readNumber(value.bounds, "minX", "min_x");
  const maxX = readNumber(value.bounds, "maxX", "max_x");
  const minY = readNumber(value.bounds, "minY", "min_y");
  const maxY = readNumber(value.bounds, "maxY", "max_y");
  if (
    minX === undefined ||
    maxX === undefined ||
    minY === undefined ||
    maxY === undefined ||
    !Array.isArray(value.points) ||
    !Array.isArray(value.edges)
  ) {
    return null;
  }

  const points = value.points.flatMap((item): GeometryPoint[] => {
    if (!isRecord(item)) return [];
    const id = readString(item, "id");
    const x = readNumber(item, "x");
    const y = readNumber(item, "y");
    if (!id || x === undefined || y === undefined) return [];
    return [{
      id,
      group: readString(item, "group") ?? "main",
      x,
      y,
      label: readString(item, "label"),
      color: readString(item, "color"),
    }];
  });
  const pointIds = new Set(points.map((point) => point.id));
  const edges = value.edges.flatMap((item): GeometryEdge[] => {
    if (!isRecord(item)) return [];
    const source = readString(item, "source");
    const target = readString(item, "target");
    if (!source || !target || !pointIds.has(source) || !pointIds.has(target)) {
      return [];
    }
    return [{
      id: readString(item, "id") ?? `${source}-${target}`,
      group: readString(item, "group") ?? "main",
      source,
      target,
      color: readString(item, "color"),
    }];
  });

  return {
    bounds: { minX, maxX, minY, maxY },
    points,
    edges,
  };
}

const GEOMETRY_COLORS: Record<string, string> = {
  cyan: "#4bbecf",
  navy: "#004278",
  grape: "#48304d",
  plum: "#c792df",
  violet: "#765184",
  coral: "#e5857b",
  gold: "#a678c9",
  green: "#4f9d79",
  gray: "#958b98",
};

function geometryColor(value?: string): string {
  if (!value) return GEOMETRY_COLORS.grape;
  return GEOMETRY_COLORS[value] ?? value;
}

export function GeometryAtlasScene({
  scene,
  content,
  showGrid,
  canProbe,
  onProbe,
}: {
  scene: GeometryScene;
  content: Record<string, unknown>;
  showGrid: boolean;
  canProbe: boolean;
  onProbe: (cardId: string) => void;
}) {
  const groups = Array.from(
    new Set([
      ...scene.points.map((point) => point.group),
      ...scene.edges.map((edge) => edge.group),
    ]),
  );
  const pointByKey = new Map(
    scene.points.map((point) => [`${point.group}:${point.id}`, point]),
  );
  const width = Math.max(1, scene.bounds.maxX - scene.bounds.minX);
  const height = Math.max(1, scene.bounds.maxY - scene.bounds.minY);
  const flipY = (value: number) => scene.bounds.maxY + scene.bounds.minY - value;
  const viewPadding = Math.max(width, height) * 0.09;
  const radius = showGrid
    ? 0.16
    : Math.max(
        0.48,
        Math.min(0.72, Math.min(width, height) * 0.075),
      );
  const verticalGridLines = Array.from(
    {
      length: Math.max(
        0,
        Math.floor(scene.bounds.maxX) - Math.ceil(scene.bounds.minX) + 1,
      ),
    },
    (_, index) => Math.ceil(scene.bounds.minX) + index,
  );
  const horizontalGridLines = Array.from(
    {
      length: Math.max(
        0,
        Math.floor(scene.bounds.maxY) - Math.ceil(scene.bounds.minY) + 1,
      ),
    },
    (_, index) => Math.ceil(scene.bounds.minY) + index,
  );
  const isTransformPair =
    groups.length === 2 && groups.includes("source") && groups.includes("image");
  return (
    <figure
      className={`geometry-atlas${
        isTransformPair ? " geometry-atlas--pair" : ""
      }${showGrid ? " geometry-atlas--points" : ""}`}
      aria-label="Геометрические конфигурации"
      data-tour="graph-cards"
    >
      <div className="geometry-atlas__cards">
        {groups.map((group) => {
          const points = scene.points.filter((point) => point.group === group);
          const edges = scene.edges.filter((edge) => edge.group === group);
          return (
            <ZendoCard
              className="geometry-card"
              probeableClassName="geometry-card--probeable"
              cardId={group}
              content={content}
              canProbe={canProbe}
              onProbe={onProbe}
              key={group}
            >
              <svg
                viewBox={`${scene.bounds.minX - viewPadding} ${
                  scene.bounds.minY - viewPadding
                } ${width + viewPadding * 2} ${height + viewPadding * 2}`}
                role="img"
                aria-label={`Конфигурация ${group}`}
              >
                <rect
                  className="geometry-card__plane"
                  x={scene.bounds.minX}
                  y={scene.bounds.minY}
                  width={width}
                  height={height}
                />
                {showGrid && (
                  <g className="geometry-card__grid" aria-hidden="true">
                    {verticalGridLines.map((x) => (
                      <line
                        className={x === 0 ? "is-axis" : undefined}
                        x1={x}
                        y1={scene.bounds.minY}
                        x2={x}
                        y2={scene.bounds.maxY}
                        key={`grid-x-${x}`}
                      />
                    ))}
                    {horizontalGridLines.map((y) => (
                      <line
                        className={y === 0 ? "is-axis" : undefined}
                        x1={scene.bounds.minX}
                        y1={flipY(y)}
                        x2={scene.bounds.maxX}
                        y2={flipY(y)}
                        key={`grid-y-${y}`}
                      />
                    ))}
                  </g>
                )}
                {edges.map((edge) => {
                  const source = pointByKey.get(`${group}:${edge.source}`);
                  const target = pointByKey.get(`${group}:${edge.target}`);
                  if (!source || !target) return null;
                  return (
                    <line
                      x1={source.x}
                      y1={flipY(source.y)}
                      x2={target.x}
                      y2={flipY(target.y)}
                      stroke={geometryColor(edge.color)}
                      key={edge.id}
                    />
                  );
                })}
                {points.map((point) => (
                  <g key={point.id}>
                    <circle
                      cx={point.x}
                      cy={flipY(point.y)}
                      r={radius}
                      style={{ fill: geometryColor(point.color) }}
                    />
                    {point.label && (
                      <text
                        className={showGrid ? "geometry-card__point-label" : undefined}
                        x={showGrid ? point.x + 0.28 : point.x}
                        y={showGrid ? flipY(point.y) - 0.28 : flipY(point.y)}
                        dominantBaseline="central"
                        textAnchor={showGrid ? "start" : "middle"}
                        style={{
                          fill: showGrid
                            ? "#48304d"
                            : point.color === "cyan"
                              ? "#004278"
                              : "#ffffff",
                          fontSize: showGrid
                            ? "0.52px"
                            : `${Math.max(radius * 1.05, 0.46)}px`,
                        }}
                      >
                        {point.label}
                      </text>
                    )}
                  </g>
                ))}
              </svg>
            </ZendoCard>
          );
        })}
      </div>
    </figure>
  );
}
