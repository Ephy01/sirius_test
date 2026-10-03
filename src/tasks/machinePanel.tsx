import { invalidResponse } from "../api/errors";
import {
  isRecord,
  readNumber,
  readString,
  type UnknownRecord,
} from "../api/parsing";
import type { PublicStateBase, TaskKind } from "./kind";
import {
  MACHINE_RESPONSE_HINT,
  MachineStateDisplay,
  parseMachineOperations,
  type MachineOperation,
  type MachineState,
} from "./shared/machine";

export type MachineSubKind =
  | "lamps_gf2"
  | "numeric_machine"
  | "perm_puzzle";

export type MachinePanelPublicState = {
  kind: "machine_panel";
  subKind: MachineSubKind;
  prompt: string;
  ops: MachineOperation[];
  start: MachineState;
  target: MachineState;
  current: MachineState;
  stepsSoftCap: number;
  stepsTaken: number;
  responseHint: string;
};

function parseMachineState(
  value: unknown,
  subKind: MachineSubKind,
): MachineState | null {
  if (!isRecord(value)) return null;
  if (subKind === "lamps_gf2") {
    const lamps = value.lamps;
    if (
      !Array.isArray(lamps) ||
      lamps.length === 0 ||
      !lamps.every((lamp) => lamp === 0 || lamp === 1)
    ) {
      return null;
    }
    return { lamps: [...lamps] as number[] };
  }
  if (subKind === "numeric_machine") {
    const number = readNumber(value, "value");
    return number === undefined ? null : { value: number };
  }
  const cards = value.cards;
  if (
    !Array.isArray(cards) ||
    cards.length === 0 ||
    !cards.every((card) => Number.isInteger(card))
  ) {
    return null;
  }
  return { cards: [...cards] as number[] };
}

function parseMachinePanelState(
  state: UnknownRecord,
  base: PublicStateBase,
): MachinePanelPublicState {
  const subKindValue = readString(state, "subKind", "sub_kind");
  const subKind =
    subKindValue === "lamps_gf2" ||
    subKindValue === "numeric_machine" ||
    subKindValue === "perm_puzzle"
      ? subKindValue
      : undefined;
  const operations = parseMachineOperations(state.ops);
  const start = subKind ? parseMachineState(state.start, subKind) : null;
  const target = subKind ? parseMachineState(state.target, subKind) : null;
  const current = subKind ? parseMachineState(state.current, subKind) : null;
  if (!subKind || !operations || !start || !target || !current) {
    throw invalidResponse("Сервер вернул некорректное состояние машины.", state);
  }

  return {
    kind: "machine_panel",
    subKind,
    ...base,
    ops: operations,
    start,
    target,
    current,
    stepsSoftCap: readNumber(state, "stepsSoftCap", "steps_soft_cap") ?? 24,
    stepsTaken: readNumber(state, "stepsTaken", "steps_taken") ?? 0,
  };
}

function MachinePanel({
  state,
  canAct,
  onOp,
  onReset,
}: {
  state: MachinePanelPublicState;
  canAct: boolean;
  onOp: (opId: string) => void;
  onReset: () => void;
}) {
  const isLampPanel = state.subKind === "lamps_gf2";
  return (
    <figure className="machine-panel" aria-label="Пульт машины">
      <div
        className={`machine-panel__states${
          isLampPanel ? " machine-panel__states--two" : ""
        }`}
      >
        {!isLampPanel && (
          <MachineStateDisplay label="Старт" state={state.start} />
        )}
        <MachineStateDisplay label="Сейчас" state={state.current} current />
        <MachineStateDisplay label="Цель" state={state.target} />
      </div>

      <ol className="machine-operations" aria-label="Доступные операции">
        {state.ops.map((operation) => (
          <li key={operation.id}>
            <button
              type="button"
              disabled={!canAct}
              onClick={() => onOp(operation.id)}
            >
              <code>{operation.id}</code>
              <span>{operation.label}</span>
            </button>
          </li>
        ))}
      </ol>

      {isLampPanel && (
        <button
          type="button"
          className="machine-panel__reset"
          disabled={!canAct}
          onClick={onReset}
        >
          Вернуть в начало
        </button>
      )}
    </figure>
  );
}

export const machinePanel: TaskKind<MachinePanelPublicState> = {
  defaultResponseHint: MACHINE_RESPONSE_HINT,
  parse: parseMachinePanelState,
  renderScene: ({ state, canAct, onCommand }) => (
    <MachinePanel
      state={state}
      canAct={canAct}
      onOp={(opId) => onCommand(`/op ${opId}`)}
      onReset={() => onCommand("/reset")}
    />
  ),
};
