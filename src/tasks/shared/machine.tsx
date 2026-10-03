import { isRecord, readString } from "../../api/parsing";
import type { TaskCommand, TaskKind, TaskSubject } from "../kind";
import "./machine.css";

export const MACHINE_RESPONSE_HINT = "/op op1 · /undo · done / impossible";

const MACHINE_COMMANDS: readonly TaskCommand[] = ["op", "undo", "reset", "done"];

const MACHINE_HELP = (
  <>
    <code>/op &lt;id&gt;</code> — применить указанную операцию
    <br />
    <code>/undo</code> — отменить последнюю операцию
    <br />
    <code>/reset</code> — вернуть машину в начало
    <br />
    <code>done</code> — зафиксировать достигнутую цель
    <br />
    <code>impossible</code> — заявить, что цель недостижима
  </>
);

const MACHINE_OPENING_GUIDE = (
  <>
    Применяйте операции командой <code>/op &lt;id&gt;</code>, отменяйте
    последний шаг через <code>/undo</code>. Итог: <code>done</code> или{" "}
    <code>impossible</code>.
  </>
);

const MACHINE_ANSWER_GUIDE = (
  <>
    Ответ отправьте в чате: <code>done</code> — когда решение
    найдено, <code>impossible</code> — если цель недостижима.
  </>
);

const MACHINE_COMMAND_GUIDE = (
  <>
    <code>/op &lt;id&gt;</code> — применить операцию ·{" "}
    <code>/undo</code> — отменить последний шаг.
  </>
);

/**
 * Members shared by the kinds where a state is driven to a target with
 * operations. `applies` limits the machine game to some families of the kind.
 */
export function machineBehaviour(
  applies: (task: TaskSubject<unknown>) => boolean = () => true,
) {
  return {
    commands: (task) => (applies(task) ? MACHINE_COMMANDS : []),
    help: (task) => (applies(task) ? MACHINE_HELP : undefined),
    opening: (task, number) =>
      applies(task)
        ? {
            opened: (
              <>
                Открыта машина {number}. Переведите текущее состояние в целевое.
              </>
            ),
            guide: MACHINE_OPENING_GUIDE,
          }
        : {},
    answerGuide: (task) => (applies(task) ? MACHINE_ANSWER_GUIDE : undefined),
    commandGuide: (task) => (applies(task) ? MACHINE_COMMAND_GUIDE : undefined),
    answerExample: (task) => (applies(task) ? "/answer done" : undefined),
  } satisfies Partial<TaskKind<unknown>>;
}

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
