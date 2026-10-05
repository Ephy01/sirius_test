import type { TaskFamily } from "../api";
import { numericDraft } from "../organizer/builder/draft";
import type { TaskSandboxState } from "./useTaskSandbox";

function FamilyOptions({ families }: { families: readonly TaskFamily[] }) {
  return families.map((family) => (
    <option key={family.key} value={family.key}>
      {`${family.title} · ${family.key}`}
    </option>
  ));
}

export function SandboxControls({ sandbox }: { sandbox: TaskSandboxState }) {
  const {
    catalog,
    family,
    selectFamily,
    variant,
    setVariant,
    difficulty,
    setDifficulty,
    seed,
    setSeed,
    busy,
    notice,
    generate,
    reloadModules,
  } = sandbox;
  if (!catalog) return null;

  const builtin = catalog.items.filter((item) => item.source === "builtin");
  const modules = catalog.items.filter((item) => item.source === "module");

  return (
    <form
      className="sandbox-controls"
      onSubmit={(event) => {
        event.preventDefault();
        generate(false);
      }}
    >
      <label className="sandbox-field sandbox-field--family">
        <span>Семейство</span>
        <select
          value={family?.key ?? ""}
          disabled={busy}
          onChange={(event) => {
            const next = catalog.items.find(
              (item) => item.key === event.target.value,
            );
            if (next) selectFamily(next);
          }}
        >
          <optgroup label="Встроенные семейства">
            <FamilyOptions families={builtin} />
          </optgroup>
          {modules.length > 0 && (
            <optgroup label="Модули задач">
              <FamilyOptions families={modules} />
            </optgroup>
          )}
        </select>
      </label>
      {family && family.variants.length > 0 && (
        <label className="sandbox-field">
          <span>Вариант</span>
          <select
            value={variant}
            disabled={busy}
            onChange={(event) => setVariant(event.target.value)}
          >
            {!family.scriptedOnly && <option value="">Любой</option>}
            {family.variants.map((item) => (
              <option key={item.key} value={item.key}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="sandbox-field sandbox-field--narrow">
        <span>Сложность</span>
        <input
          type="number"
          min={family?.minDifficulty}
          max={family?.maxDifficulty}
          step={1}
          value={difficulty}
          disabled={busy}
          onChange={(event) => setDifficulty(numericDraft(event.target.value))}
        />
      </label>
      <label className="sandbox-field">
        <span>Сид, пусто — случайный</span>
        <input
          inputMode="numeric"
          value={seed}
          disabled={busy}
          placeholder="случайный"
          onChange={(event) => setSeed(event.target.value)}
        />
      </label>
      <div className="sandbox-controls__actions">
        <button
          className="sandbox-button sandbox-button--primary"
          type="submit"
          disabled={busy || !family}
        >
          Сгенерировать
        </button>
        <button
          className="sandbox-button"
          type="button"
          disabled={busy || !family}
          onClick={() => generate(true)}
        >
          Другой вариант
        </button>
        <button
          className="sandbox-button"
          type="button"
          disabled={busy}
          onClick={reloadModules}
        >
          Перечитать модули
        </button>
      </div>
      <p className="sandbox-controls__notice" role="alert">
        {notice}
      </p>
    </form>
  );
}
