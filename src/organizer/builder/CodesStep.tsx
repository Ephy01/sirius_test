import type { ContestBuilderState } from "./useContestBuilder";

export function CodesStep({ builder }: { builder: ContestBuilderState }) {
  const {
    contest,
    codes,
    busy,
    error,
    publishContest,
    downloadCodes,
  } = builder;

  return (
    <section className="builder-card" aria-labelledby="codesTitle">
      <span className="builder-section-label">04 · коды</span>
      <h2 id="codesTitle">Коды созданы</h2>
      <p className="builder-intro">
        Скачайте таблицу сейчас. В открытом виде коды возвращаются только
        при выпуске.
      </p>
      <div className="codes-table">
        <div className="codes-table__head">
          <span>Заявка</span>
          <span>Участник</span>
          <span>Персональный код</span>
        </div>
        {codes.map((row) => (
          <div className="codes-row" key={row.enrollmentId}>
            <span>{row.externalRef}</span>
            <strong>{row.displayName}</strong>
            <code>{row.code}</code>
          </div>
        ))}
      </div>
      <p className="builder-error" role="alert">
        {error}
      </p>
      <footer className="builder-actions builder-actions--split">
        <button
          className="secondary-action"
          type="button"
          onClick={downloadCodes}
        >
          Скачать CSV
        </button>
        <button
          className="primary-action primary-action--fit"
          type="button"
          disabled={busy || contest?.status === "published"}
          onClick={publishContest}
        >
          {contest?.status === "published"
            ? "Контест опубликован"
            : busy
              ? "Публикуем…"
              : "Опубликовать контест"}
        </button>
      </footer>
    </section>
  );
}
