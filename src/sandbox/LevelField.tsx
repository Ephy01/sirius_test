import { numericDraft } from "../organizer/builder/draft";
import type { TaskSandboxState } from "./useTaskSandbox";

/** Difficulty of the variant: a list of names when the family names its levels, a number otherwise. */
export function LevelField({ sandbox }: { sandbox: TaskSandboxState }) {
  const { family, difficulty, setDifficulty, busy } = sandbox;
  const titles = family?.levelTitles ?? [];

  if (family && titles.length > 0) {
    return (
      <label className="sandbox-field">
        <span>Уровень</span>
        <select
          value={difficulty}
          disabled={busy}
          onChange={(event) => setDifficulty(Number(event.target.value))}
        >
          {titles.map((title, index) => (
            <option key={title} value={family.minDifficulty + index}>
              {title}
            </option>
          ))}
        </select>
      </label>
    );
  }
  return (
    <label className="sandbox-field sandbox-field--narrow">
      <span>Сложность</span>
      <input
        type="number"
        min={family?.minDifficulty ?? 1}
        max={family?.maxDifficulty ?? 5}
        step={1}
        value={difficulty}
        disabled={busy}
        onChange={(event) => setDifficulty(numericDraft(event.target.value))}
      />
    </label>
  );
}
