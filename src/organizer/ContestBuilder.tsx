import { BasicsStep } from "./builder/BasicsStep";
import { CodesStep } from "./builder/CodesStep";
import type { ContestBuilderProps } from "./builder/draft";
import { FamiliesStep } from "./builder/FamiliesStep";
import { ParticipantsStep } from "./builder/ParticipantsStep";
import { useContestBuilder } from "./builder/useContestBuilder";
import "./contest-builder.css";

export function ContestBuilder(props: ContestBuilderProps) {
  const { onCancel } = props;
  const builder = useContestBuilder(props);
  const { step, setStep, contest, busy, error, submitCurrentStep } = builder;

  return (
    <main className="builder-page">
      <header className="builder-heading">
        <div>
          <p className="eyebrow">Конструктор контеста</p>
          <h1>{contest?.title || "Новый контест"}</h1>
          <p>
            Выберите семейства, настройте адаптивную траекторию и выпустите
            персональные коды.
          </p>
        </div>
        <button className="builder-close" type="button" onClick={onCancel}>
          Закрыть
        </button>
      </header>

      <ol className="builder-progress" aria-label="Этапы создания контеста">
        {["Параметры", "Семейства", "Участники", "Коды"].map((label, index) => (
          <li
            className={step === index + 1 ? "is-active" : ""}
            key={label}
            aria-current={step === index + 1 ? "step" : undefined}
          >
            <i>{String(index + 1).padStart(2, "0")}</i>
            <span>{label}</span>
          </li>
        ))}
      </ol>

      {step <= 2 && (
        <form className="builder-card" onSubmit={submitCurrentStep}>
          {step === 1 ? (
            <BasicsStep builder={builder} />
          ) : (
            <FamiliesStep builder={builder} />
          )}

          <p className="builder-error" role="alert">
            {error}
          </p>
          <footer className="builder-actions">
            {step === 2 && (
              <button
                className="secondary-action"
                type="button"
                onClick={() => setStep(1)}
              >
                Назад
              </button>
            )}
            {step === 1 ? (
              <button
                className="primary-action primary-action--fit"
                type="submit"
              >
                Настроить семейства
              </button>
            ) : (
              <button
                className="primary-action primary-action--fit"
                type="submit"
                disabled={busy}
              >
                {busy ? "Создаём…" : "Создать контест"}
              </button>
            )}
          </footer>
        </form>
      )}

      {step === 3 && <ParticipantsStep builder={builder} />}

      {step === 4 && <CodesStep builder={builder} />}
    </main>
  );
}
