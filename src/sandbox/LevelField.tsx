import { numericDraft } from "../organizer/builder/draft";
import type { TaskSandboxState } from "./useTaskSandbox";

/** Difficulty of the variant the author asks for. */
export function LevelField({ sandbox }: { sandbox: TaskSandboxState }) {
  const { family, difficulty, setDifficulty, busy } = sandbox;
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
