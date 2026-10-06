import { LevelField } from "../sandbox/LevelField";
import type { TaskSandboxState } from "../sandbox/useTaskSandbox";

/** Settings of the variant that is opened from the code in the editor. */
export function EditorControls({
  sandbox,
  onRun,
  onCheck,
}: {
  sandbox: TaskSandboxState;
  onRun: () => void;
  onCheck: () => void;
}) {
  const {
    catalog,
    family,
    selectFamily,
    variant,
    setVariant,
    seed,
    setSeed,
    busy,
    notice,
    generate,
  } = sandbox;
  const families = catalog?.items ?? [];

  return (
    <form
      className="sandbox-controls"
      onSubmit={(event) => {
        event.preventDefault();
        onRun();
      }}
    >
      {families.length > 1 && (
        <label className="sandbox-field">
          <span>Семейство</span>
          <select
            value={family?.key ?? ""}
            disabled={busy}
            onChange={(event) => {
              const next = families.find(
                (item) => item.key === event.target.value,
              );
              if (next) selectFamily(next);
            }}
          >
            {families.map((item) => (
              <option key={item.key} value={item.key}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
      )}
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
      <LevelField sandbox={sandbox} />
      <label className="sandbox-field sandbox-field--narrow">
        <span>Сид</span>
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
          disabled={busy}
          title="Ctrl+Enter в поле кода"
        >
          Запустить
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
          onClick={onCheck}
        >
          Проверить
        </button>
      </div>
      <p className="sandbox-controls__notice" role="alert">
        {notice}
      </p>
    </form>
  );
}
