import { useState } from "react";
import { invalidResponse } from "../api/errors";
import {
  isRecord,
  readNumber,
  readString,
  type UnknownRecord,
} from "../api/parsing";
import type { PublicStateBase, TaskKind } from "./kind";
import {
  MachineStateDisplay,
  parseMachineOperations,
  type MachineOperation,
} from "./shared/machine";

export type WiringObservation = {
  chord: string;
  training: boolean;
  effect: number[];
  lampsAfter: number[];
};

export type HiddenWiringPublicState = {
  kind: "hidden_wiring";
  family: "hidden_wiring";
  variant: "reach_target" | "predict_chords";
  prompt: string;
  lampCount: number;
  buttonCount: number;
  ops: MachineOperation[];
  current: number[];
  target?: number[];
  examChords?: { id: string; label: string }[];
  chordBudget: number;
  chordsRemaining: number;
  observations: WiringObservation[];
  responseHint: string;
};

function parseLamps(value: unknown): number[] | null {
  return Array.isArray(value) && value.every((item) => item === 0 || item === 1)
    ? (value as number[])
    : null;
}

function parseHiddenWiringState(
  state: UnknownRecord,
  base: PublicStateBase,
): HiddenWiringPublicState {
  const variant = readString(state, "variant");
  const lampCount = readNumber(state, "lampCount", "lamp_count");
  const buttonCount = readNumber(state, "buttonCount", "button_count");
  const operations = parseMachineOperations(state.ops);
  const current = parseLamps(state.current);
  if (
    (variant !== "reach_target" && variant !== "predict_chords") ||
    lampCount === undefined ||
    buttonCount === undefined ||
    !operations ||
    !current
  ) {
    throw invalidResponse(
      "Сервер вернул некорректную панель скрытой проводки.",
      state,
    );
  }
  const examChordsValue = state.examChords ?? state.exam_chords;
  const examChords = Array.isArray(examChordsValue)
    ? examChordsValue.flatMap((item) => {
        if (!isRecord(item)) return [];
        const id = readString(item, "id");
        if (!id) return [];
        return [{ id, label: readString(item, "label") ?? id }];
      })
    : undefined;
  const observations = Array.isArray(state.observations)
    ? state.observations.flatMap((item): WiringObservation[] => {
        if (!isRecord(item)) return [];
        const chord = readString(item, "chord");
        const effect = parseLamps(item.effect);
        const lampsAfter = parseLamps(item.lampsAfter ?? item.lamps_after);
        if (!chord || !effect || !lampsAfter) return [];
        return [{
          chord,
          training: item.training === true,
          effect,
          lampsAfter,
        }];
      })
    : [];

  return {
    kind: "hidden_wiring",
    family: "hidden_wiring",
    variant,
    ...base,
    lampCount,
    buttonCount,
    ops: operations,
    current,
    target: parseLamps(state.target) ?? undefined,
    examChords,
    chordBudget: readNumber(state, "chordBudget", "chord_budget") ?? 8,
    chordsRemaining:
      readNumber(state, "chordsRemaining", "chords_remaining") ?? 8,
    observations,
  };
}

function WiringPanelScene({
  state,
  canAct,
  onChord,
}: {
  state: HiddenWiringPublicState;
  canAct: boolean;
  onChord: (opId: string) => void;
}) {
  const [selected, setSelected] = useState<number[]>([]);
  const chordReady = selected.length === 2;
  const chordId = chordReady
    ? `b${Math.min(...selected)}+b${Math.max(...selected)}`
    : null;
  const chordAllowed =
    chordId !== null && state.ops.some((operation) => operation.id === chordId);

  function toggleButton(index: number) {
    setSelected((currentSelection) =>
      currentSelection.includes(index)
        ? currentSelection.filter((value) => value !== index)
        : currentSelection.length < 2
          ? [...currentSelection, index]
          : [currentSelection[1], index],
    );
  }

  return (
    <figure className="wiring-panel" aria-label="Панель со скрытой проводкой">
      <div className="machine-panel__states">
        <MachineStateDisplay
          label="Сейчас"
          state={{ lamps: state.current }}
          current
        />
        {state.target && (
          <MachineStateDisplay label="Цель" state={{ lamps: state.target }} />
        )}
      </div>

      <div className="wiring-panel__buttons" role="group" aria-label="Кнопки панели">
        {Array.from({ length: state.buttonCount }, (_, index) => index + 1).map(
          (button) => (
            <button
              type="button"
              className={selected.includes(button) ? "is-selected" : ""}
              aria-pressed={selected.includes(button)}
              onClick={() => toggleButton(button)}
              key={button}
            >
              {button}
            </button>
          ),
        )}
        <button
          type="button"
          className="wiring-panel__fire"
          disabled={!canAct || !chordReady || !chordAllowed}
          onClick={() => {
            if (chordId) {
              onChord(chordId);
              setSelected([]);
            }
          }}
        >
          Нажать комбинацию
        </button>
      </div>
      {chordReady && !chordAllowed && (
        <p className="wiring-panel__warning">
          Эта комбинация недоступна для проб.
        </p>
      )}

      {state.observations.length > 0 && (
        <ol className="wiring-panel__log" aria-label="Наблюдения">
          {state.observations.map((observation, index) => (
            <li key={index}>
              <code>{observation.chord}</code>
              {observation.training && <em> обучающая</em>}
              <span>
                переключились:{" "}
                {observation.effect
                  .map((bit, lamp) => (bit ? lamp + 1 : null))
                  .filter((lamp) => lamp !== null)
                  .join(", ") || "ничего"}
              </span>
            </li>
          ))}
        </ol>
      )}
    </figure>
  );
}

export const hiddenWiring: TaskKind<HiddenWiringPublicState> = {
  parse: parseHiddenWiringState,
  renderScene: ({ state, canAct, onCommand }) => (
    <WiringPanelScene
      state={state}
      canAct={canAct}
      onChord={(opId) => onCommand(`/op ${opId}`)}
    />
  ),
};
