import type { TaskFamily } from "../../api";
import { numericDraft } from "./draft";
import type { ContestBuilderState } from "./useContestBuilder";

function ScriptedFamily({
  family,
  builder,
}: {
  family: TaskFamily;
  builder: ContestBuilderState;
}) {
  const {
    scriptedEnabled,
    setScriptedEnabled,
    scriptedVariant,
    setScriptedVariant,
    scriptedPosition,
    setScriptedPosition,
    setError,
  } = builder;
  const description = family.variants.find(
    (variant) => variant.key === scriptedVariant,
  )?.description;

  return (
    <article
      className={`scripted-family${scriptedEnabled ? " is-enabled" : ""}`}
    >
      <header>
        <label>
          <input
            type="checkbox"
            checked={scriptedEnabled}
            onChange={(event) => {
              setScriptedEnabled(event.target.checked);
              setError("");
            }}
          />
          <span>{family.title}</span>
        </label>
        <small>{`${family.key} · ровно один раз`}</small>
      </header>
      <p>
        Задача с развёрнутым ответом появится на указанной позиции и
        не участвует в случайной ротации семейств.
      </p>
      <div className="scripted-family__settings">
        <label>
          <span>Задача</span>
          <select
            value={scriptedVariant}
            disabled={!scriptedEnabled}
            onChange={(event) => setScriptedVariant(event.target.value)}
          >
            {family.variants.map((variant) => (
              <option key={variant.key} value={variant.key}>
                {variant.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Позиция в траектории</span>
          <input
            type="number"
            min={1}
            max={100}
            step={1}
            value={scriptedPosition}
            disabled={!scriptedEnabled}
            onChange={(event) => {
              setScriptedPosition(numericDraft(event.target.value));
              setError("");
            }}
          />
        </label>
      </div>
      {scriptedEnabled && description && (
        <p className="scripted-family__selection">{description}</p>
      )}
    </article>
  );
}

export function FamiliesStep({ builder }: { builder: ContestBuilderState }) {
  const {
    catalog,
    catalogError,
    reloadCatalog,
    scripted,
    families,
    updateFamily,
  } = builder;

  return (
    <section aria-labelledby="builderFamiliesTitle">
      <span className="builder-section-label">02 · семейства</span>
      <h2 id="builderFamiliesTitle">Контент траектории</h2>
      {catalogError ? (
        <div className="family-catalog-state" role="alert">
          <p>{catalogError}</p>
          <button
            className="secondary-action"
            type="button"
            onClick={reloadCatalog}
          >
            Повторить
          </button>
        </div>
      ) : !catalog ? (
        <p className="family-catalog-state" role="status">
          Загружаем семейства задач…
        </p>
      ) : (
        <>
          {catalog.problems.length > 0 && (
            <aside className="family-problems" role="status">
              <strong>Модули задач не загружены</strong>
              <ul>
                {catalog.problems.map((problem) => (
                  <li key={problem.module}>
                    <code>{problem.module}</code> — {problem.error}
                  </li>
                ))}
              </ul>
            </aside>
          )}
          {scripted && <ScriptedFamily family={scripted} builder={builder} />}
          <div className="family-list">
            {families.map((family) => {
              const { card } = family;
              return (
                <article
                  className={family.enabled ? "is-enabled" : ""}
                  key={family.key}
                >
                  <header>
                    <label>
                      <input
                        type="checkbox"
                        checked={family.enabled}
                        onChange={(event) =>
                          updateFamily(family.key, {
                            enabled: event.target.checked,
                          })
                        }
                      />
                      <span>{card.title}</span>
                      {card.source === "module" && (
                        <em className="family-module-mark">модуль</em>
                      )}
                    </label>
                    <small>
                      {family.key}
                      {family.skin !== null && <> · {family.skin}</>}
                    </small>
                  </header>
                  <p>
                    {card.description}
                    {card.author && (
                      <span className="family-author">Автор: {card.author}</span>
                    )}
                  </p>
                  <div>
                    <label>
                      Вес
                      <input
                        type="number"
                        aria-label={`Вес семейства ${card.title}`}
                        min={1}
                        max={100}
                        disabled={!family.enabled}
                        value={family.weight}
                        onChange={(event) =>
                          updateFamily(family.key, {
                            weight: numericDraft(event.target.value),
                          })
                        }
                      />
                    </label>
                    <label>
                      Старт
                      <input
                        type="number"
                        aria-label={`Начальная сложность ${card.title}`}
                        min={card.minDifficulty}
                        max={card.maxDifficulty}
                        disabled={!family.enabled}
                        value={family.initialDifficulty}
                        onChange={(event) =>
                          updateFamily(family.key, {
                            initialDifficulty: numericDraft(
                              event.target.value,
                            ),
                          })
                        }
                      />
                    </label>
                    <label>
                      Максимум
                      <input
                        type="number"
                        aria-label={`Максимальная сложность ${card.title}`}
                        min={card.minDifficulty}
                        max={card.maxDifficulty}
                        disabled={!family.enabled}
                        value={family.maxDifficulty}
                        onChange={(event) =>
                          updateFamily(family.key, {
                            maxDifficulty: numericDraft(event.target.value),
                          })
                        }
                      />
                    </label>
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}
