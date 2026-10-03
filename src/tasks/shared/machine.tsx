import { isRecord, readString } from "../../api/parsing";

export const MACHINE_RESPONSE_HINT = "/op op1 · /undo · done / impossible";

export type MachineState =
  | { lamps: number[] }
  | { value: number }
  | { cards: number[] };

export type MachineOperation = {
  id: string;
  label: string;
  spec: Record<string, unknown>;
};

export function parseMachineOperations(value: unknown): MachineOperation[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const operations = value.flatMap((item): MachineOperation[] => {
    if (!isRecord(item)) return [];
    const id = readString(item, "id");
    const label = readString(item, "label");
    if (!id || !label) return [];
    return [{
      id,
      label,
      spec: isRecord(item.spec) ? item.spec : {},
    }];
  });
  return operations.length === value.length ? operations : null;
}

export function MachineStateDisplay({
  label,
  state,
  current = false,
}: {
  label: string;
  state: MachineState;
  current?: boolean;
}) {
  return (
    <section
      className={`machine-state${current ? " machine-state--current" : ""}`}
    >
      <span>{label}</span>
      {"lamps" in state ? (
        <ol className="machine-lamps" aria-label={`${label}: состояние ламп`}>
          {state.lamps.map((lamp, index) => (
            <li
              className={lamp ? "is-on" : ""}
              aria-label={`Лампа ${index + 1}: ${lamp ? "горит" : "не горит"}`}
              key={index}
            >
              <i aria-hidden="true" />
              <small>{index + 1}</small>
            </li>
          ))}
        </ol>
      ) : "cards" in state ? (
        <ol className="machine-cards" aria-label={`${label}: порядок карточек`}>
          {state.cards.map((card, index) => (
            <li key={`${card}-${index}`}>{card}</li>
          ))}
        </ol>
      ) : (
        <strong className="machine-number">{state.value}</strong>
      )}
    </section>
  );
}
