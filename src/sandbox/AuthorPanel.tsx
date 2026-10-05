import type { TaskModuleProblem, UnknownRecord } from "../api";
import { verdict, type SandboxRun } from "./useTaskSandbox";

function Json({ value }: { value: unknown }) {
  return <pre className="sandbox-json">{JSON.stringify(value, null, 2)}</pre>;
}

function Evaluation({ evaluation }: { evaluation: UnknownRecord | null }) {
  if (!evaluation) {
    return (
      <p className="sandbox-card__empty">
        Появится после ответа или хода, который завершает задачу.
      </p>
    );
  }
  const { correct } = evaluation;
  return (
    <>
      <p
        className={`sandbox-verdict${
          correct === true
            ? " sandbox-verdict--correct"
            : correct === false
              ? " sandbox-verdict--wrong"
              : ""
        }`}
      >
        {verdict(evaluation)}
      </p>
      <Json value={evaluation} />
    </>
  );
}

export function AuthorPanel({
  run,
  problems,
}: {
  run: SandboxRun | null;
  problems: readonly TaskModuleProblem[];
}) {
  if (!run && problems.length === 0) return null;
  return (
    <section className="sandbox-author" aria-label="Панель автора">
      {problems.length > 0 && (
        <article className="sandbox-card sandbox-card--problems">
          <h2>Модули задач не загружены</h2>
          <ul>
            {problems.map((problem) => (
              <li key={problem.module}>
                <code>{problem.module}</code> — {problem.error}
              </li>
            ))}
          </ul>
        </article>
      )}
      {run && (
        <>
          <article className="sandbox-card">
            <h2>Эталон</h2>
            {run.state.referenceAnswer === null ? (
              <p className="sandbox-card__empty">
                Семейство не сообщает эталонный ответ.
              </p>
            ) : (
              <p>
                <code>{run.state.referenceAnswer}</code>
              </p>
            )}
            {run.state.referenceCommands.length > 0 && (
              <ol className="sandbox-commands" aria-label="Команды решения">
                {run.state.referenceCommands.map((command, index) => (
                  <li key={index}>
                    <code>{command}</code>
                  </li>
                ))}
              </ol>
            )}
            {run.state.details.map((line, index) => (
              <p className="sandbox-card__detail" key={index}>
                {line}
              </p>
            ))}
          </article>
          <article className="sandbox-card">
            <h2>Последняя проверка</h2>
            <Evaluation evaluation={run.evaluation} />
          </article>
          <article className="sandbox-card sandbox-card--wide">
            <h2>Состояние задачи: закрытое и открытое</h2>
            <pre className="sandbox-json">{run.state.stateText}</pre>
          </article>
        </>
      )}
    </section>
  );
}
