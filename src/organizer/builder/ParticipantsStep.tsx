import { newParticipant } from "./draft";
import type { ContestBuilderState } from "./useContestBuilder";

export function ParticipantsStep({ builder }: { builder: ContestBuilderState }) {
  const {
    participants,
    setParticipants,
    updateParticipant,
    busy,
    error,
    saveParticipants,
  } = builder;

  return (
    <section className="builder-card" aria-labelledby="participantsTitle">
      <span className="builder-section-label">03 · участники</span>
      <h2 id="participantsTitle">Кому выдать коды</h2>
      <p className="builder-intro">
        Номер заявки создаёт устойчивую связь участника с контестом. ФИО
        используется только в таблице организатора.
      </p>
      <div className="participant-table">
        <div className="participant-table__head" aria-hidden="true">
          <span>Номер заявки</span>
          <span>Участник</span>
          <span />
        </div>
        {participants.map((participant, index) => (
          <div className="participant-row" key={index}>
            <label>
              <span>Номер заявки</span>
              <input
                aria-label={`Номер заявки участника ${index + 1}`}
                value={participant.externalRef}
                onChange={(event) =>
                  updateParticipant(index, "externalRef", event.target.value)
                }
                placeholder="18452"
              />
            </label>
            <label>
              <span>Участник</span>
              <input
                aria-label={`Имя участника ${index + 1}`}
                value={participant.displayName}
                onChange={(event) =>
                  updateParticipant(index, "displayName", event.target.value)
                }
                placeholder="Иванов Иван"
              />
            </label>
            <button
              type="button"
              aria-label={`Удалить участника ${index + 1}`}
              disabled={participants.length === 1}
              onClick={() =>
                setParticipants((current) =>
                  current.filter(
                    (_, participantIndex) => participantIndex !== index,
                  ),
                )
              }
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() =>
          setParticipants((current) => [...current, newParticipant()])
        }
      >
        + Добавить участника
      </button>
      <p className="builder-error" role="alert">
        {error}
      </p>
      <footer className="builder-actions">
        <button
          className="primary-action primary-action--fit"
          type="button"
          disabled={busy}
          onClick={saveParticipants}
        >
          {busy ? "Генерируем…" : "Сохранить и выпустить коды"}
        </button>
      </footer>
    </section>
  );
}
