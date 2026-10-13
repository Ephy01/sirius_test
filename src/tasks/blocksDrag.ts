import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

type Pair = [number, number];

/** The part of a drawing that decides where a dragged shape may land. */
export type DragArea = { x: Pair; y: Pair; snap: number | null };

/** A shape away from its place: the offset is in the coordinates of the task. */
type Carried = { index: number; dx: number; dy: number; dropped: boolean };

const ARROWS: Record<string, Pair> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, 1],
  ArrowDown: [0, -1],
};
/** Share of the width one arrow key moves a shape when the drawing has no step. */
const FREE_STEP = 1 / 40;

function landing(value: number, [low, high]: Pair, snap: number | null) {
  if (!snap) return Math.min(high, Math.max(low, value));
  const first = Math.ceil(low / snap);
  const last = Math.floor(high / snap);
  return Math.min(last, Math.max(first, Math.round(value / snap))) * snap;
}

/**
 * Dragging of shapes inside one drawing, with the mouse, a finger or the arrow keys.
 * `onDrop` gets the new place of the anchor of the shape, `onPress` a press without a move.
 */
export function useShapeDrag({
  area,
  canAct,
  onDrop,
  onPress,
}: {
  area: DragArea;
  canAct: boolean;
  onDrop: (index: number, x: number, y: number) => void;
  onPress: (index: number) => void;
}) {
  const [carried, setCarried] = useState<Carried | null>(null);
  // Read by the handler of the release, which may run before the last move is drawn.
  const latest = useRef<Carried | null>(null);
  const grip = useRef<{ x: number; y: number; unitsPerPixel: number } | null>(null);

  function show(next: Carried | null) {
    latest.current = next;
    setCarried(next);
  }

  // A drop is answered with a new scene or with a refusal. Either way the scene decides where the shape is.
  useEffect(() => {
    if (canAct && latest.current?.dropped) show(null);
  }, [canAct, area]);

  function carry(index: number, anchor: Pair, dx: number, dy: number) {
    show({
      index,
      dx: landing(anchor[0] + dx, area.x, area.snap) - anchor[0],
      dy: landing(anchor[1] + dy, area.y, area.snap) - anchor[1],
      dropped: false,
    });
  }

  function release(index: number, anchor: Pair) {
    grip.current = null;
    const held = latest.current;
    if (held?.index !== index || (held.dx === 0 && held.dy === 0)) {
      show(null);
      onPress(index);
      return;
    }
    show({ ...held, dropped: true });
    onDrop(index, anchor[0] + held.dx, anchor[1] + held.dy);
  }

  return {
    /** Offset of the shape while it is away from its place. */
    offset: (index: number) => (carried?.index === index ? carried : null),
    handlers: (index: number, anchor: Pair) =>
      canAct
        ? {
            onPointerDown(event: PointerEvent<SVGGElement>) {
              const drawing = event.currentTarget.ownerSVGElement;
              if (!drawing) return;
              event.currentTarget.setPointerCapture(event.pointerId);
              grip.current = {
                x: event.clientX,
                y: event.clientY,
                unitsPerPixel:
                  (area.x[1] - area.x[0]) / drawing.getBoundingClientRect().width,
              };
              show({ index, dx: 0, dy: 0, dropped: false });
            },
            onPointerMove(event: PointerEvent<SVGGElement>) {
              const held = grip.current;
              if (!held) return;
              carry(
                index,
                anchor,
                (event.clientX - held.x) * held.unitsPerPixel,
                (held.y - event.clientY) * held.unitsPerPixel,
              );
            },
            onPointerUp() {
              if (grip.current) release(index, anchor);
            },
            onPointerCancel() {
              grip.current = null;
              show(null);
            },
            onKeyDown(event: KeyboardEvent<SVGGElement>) {
              const arrow = ARROWS[event.key];
              if (arrow) {
                event.preventDefault();
                const step = area.snap ?? (area.x[1] - area.x[0]) * FREE_STEP;
                const held = latest.current;
                const from = held?.index === index ? held : { dx: 0, dy: 0 };
                carry(index, anchor, from.dx + arrow[0] * step, from.dy + arrow[1] * step);
              } else if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                release(index, anchor);
              } else if (event.key === "Escape") {
                show(null);
              }
            },
          }
        : {},
  };
}
