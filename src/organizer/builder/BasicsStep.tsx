import { numericDraft } from "./draft";
import type { ContestBuilderState } from "./useContestBuilder";

export function BasicsStep({ builder }: { builder: ContestBuilderState }) {
  const {
    title,
    setTitle,
    durationMinutes,
    setDurationMinutes,
    cohortSeed,
    setCohortSeed,
    debugRevealAnswers,
    setDebugRevealAnswers,
    aiEnabled,
    setAiEnabled,
    aiMode,
    setAiMode,
    aiTurnsPerAttempt,
    setAiTurnsPerAttempt,
    aiTurnsPerTask,
    setAiTurnsPerTask,
    setError,
  } = builder;

  return (
    <section aria-labelledby="builderBasicsTitle">
      <span className="builder-section-label">01 · параметры</span>
      <h2 id="builderBasicsTitle">Основная информация</h2>
      <div className="builder-fields">
        <label>
          <span>Название контеста</span>
          <input
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              setError("");
            }}
            placeholder="Отбор на программу специалитета"
            autoFocus
          />
        </label>
        <label>
          <span>Продолжительность, минут</span>
          <input
            type="number"
            min={15}
            max={240}
            value={durationMinutes}
            onChange={(event) =>
              setDurationMinutes(numericDraft(event.target.value))
            }
          />
        </label>
        <label>
          <span>Сид когорты, необязательно</span>
          <input
            value={cohortSeed}
            onChange={(event) => setCohortSeed(event.target.value)}
            placeholder="Волна-2026-01"
          />
        </label>
        <label className="builder-debug-toggle">
          <input
            type="checkbox"
            checked={debugRevealAnswers}
            onChange={(event) =>
              setDebugRevealAnswers(event.target.checked)
            }
          />
          <span>
            Режим отладки: разрешить участникам команду{" "}
            <code>/get answer</code> (эталонный ответ задачи)
          </span>
        </label>
        <label className="builder-debug-toggle">
          <input
            type="checkbox"
            checked={aiEnabled}
            onChange={(event) => setAiEnabled(event.target.checked)}
          />
          <span>
            ИИ-ассистент: обычные сообщения в чате отвечает Alice AI
          </span>
        </label>
        {aiEnabled && (
          <div className="builder-ai-settings">
            <label>
              <span>Режим ассистента</span>
              <select
                value={aiMode}
                onChange={(event) =>
                  setAiMode(
                    event.target.value === "open"
                      ? "open"
                      : "socratic",
                  )
                }
              >
                <option value="socratic">Наводящие вопросы</option>
                <option value="open">Открытый диалог</option>
              </select>
            </label>
            <label>
              <span>Лимит на попытку</span>
              <input
                type="number"
                min={1}
                max={200}
                value={aiTurnsPerAttempt}
                onChange={(event) =>
                  setAiTurnsPerAttempt(numericDraft(event.target.value))
                }
              />
            </label>
            <label>
              <span>Лимит на задачу</span>
              <input
                type="number"
                min={1}
                max={50}
                value={aiTurnsPerTask}
                onChange={(event) =>
                  setAiTurnsPerTask(numericDraft(event.target.value))
                }
              />
            </label>
          </div>
        )}
      </div>
    </section>
  );
}
