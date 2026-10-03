import { CLASSIC_MATH_TASKS, FAMILY_LABELS } from "../families";
import { numericDraft } from "./draft";
import type { ContestBuilderState } from "./useContestBuilder";

export function FamiliesStep({ builder }: { builder: ContestBuilderState }) {
  const {
    classicMathEnabled,
    setClassicMathEnabled,
    classicMathTask,
    setClassicMathTask,
    classicMathPosition,
    setClassicMathPosition,
    families,
    updateFamily,
    setError,
  } = builder;

  return (
    <section aria-labelledby="builderFamiliesTitle">
      <span className="builder-section-label">02 · семейства</span>
      <h2 id="builderFamiliesTitle">Контент траектории</h2>
      <article
        className={`scripted-family${
          classicMathEnabled ? " is-enabled" : ""
        }`}
      >
        <header>
          <label>
            <input
              type="checkbox"
              checked={classicMathEnabled}
              onChange={(event) => {
                setClassicMathEnabled(event.target.checked);
                setError("");
              }}
            />
            <span>Классическая задача</span>
          </label>
          <small>classic_math · ровно один раз</small>
        </header>
        <p>
          Задача с развёрнутым ответом появится на указанной позиции и
          не участвует в случайной ротации семейств.
        </p>
        <div className="scripted-family__settings">
          <label>
            <span>Задача</span>
            <select
              value={classicMathTask}
              disabled={!classicMathEnabled}
              onChange={(event) =>
                setClassicMathTask(
                  event.target.value === "bar_seating"
                    ? "bar_seating"
                    : "share_paradox",
                )
              }
            >
              {Object.entries(CLASSIC_MATH_TASKS).map(
                ([key, task]) => (
                  <option key={key} value={key}>
                    {task.title}
                  </option>
                ),
              )}
            </select>
          </label>
          <label>
            <span>Позиция в траектории</span>
            <input
              type="number"
              min={1}
              max={100}
              step={1}
              value={classicMathPosition}
              disabled={!classicMathEnabled}
              onChange={(event) => {
                setClassicMathPosition(numericDraft(event.target.value));
                setError("");
              }}
            />
          </label>
        </div>
        {classicMathEnabled && (
          <p className="scripted-family__selection">
            {CLASSIC_MATH_TASKS[classicMathTask].description}
          </p>
        )}
      </article>
      <div className="family-list">
        {families.map((family) => {
          const copy = FAMILY_LABELS[family.key];
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
                  <span>{copy.title}</span>
                </label>
                <small>
                  {family.key} · {family.skin}
                </small>
              </header>
              <p>{copy.description}</p>
              <div>
                <label>
                  Вес
                  <input
                    type="number"
                    aria-label={`Вес семейства ${copy.title}`}
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
                    aria-label={`Начальная сложность ${copy.title}`}
                    min={1}
                    max={5}
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
                    aria-label={`Максимальная сложность ${copy.title}`}
                    min={1}
                    max={5}
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
    </section>
  );
}
