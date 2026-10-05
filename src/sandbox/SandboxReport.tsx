import { verdict, type TaskSandboxState } from "./useTaskSandbox";

/** What the author is told above the task: which variant is open and what went wrong. */
export function SandboxReport({ sandbox }: { sandbox: TaskSandboxState }) {
  const { catalog, run, busy, failure } = sandbox;
  const source = catalog?.items.find((item) => item.key === run?.family);
  const problems = catalog?.problems ?? [];

  return (
    <>
      {run && (
        <p className="sandbox-run">
          <span>Вариант {run.number}</span>
          <span>
            {run.family}
            {source?.source === "module" && " (модуль)"}
          </span>
          <span>версия {run.generatorVersion}</span>
          {run.subKind && <span>вариант {run.subKind}</span>}
          <span>сложность {run.difficulty}</span>
          <span>
            сид <b>{run.seed}</b>
          </span>
          {run.closed && <span>задача закрыта</span>}
          {run.evaluation && <span>проверка: {verdict(run.evaluation)}</span>}
        </p>
      )}
      {problems.length > 0 && (
        <p className="sandbox-bar__problems">
          Не загружены модули:{" "}
          {problems.map((problem) => problem.module).join(", ")}. Причины — в
          панели автора под задачей.
        </p>
      )}
      {failure && (
        <div
          className={`sandbox-failure${
            failure.inTaskCode || failure.rejectedState !== undefined
              ? " sandbox-failure--task"
              : ""
          }`}
          role="alert"
        >
          <strong>
            {failure.inTaskCode
              ? "Код задачи завершился ошибкой"
              : failure.rejectedState !== undefined
                ? "Клиент не смог показать состояние задачи"
                : "Запрос не выполнен"}
          </strong>
          <pre>{failure.message}</pre>
          {failure.rejectedState !== undefined && (
            <details>
              <summary>Состояние, которое клиент не смог показать</summary>
              <pre>{JSON.stringify(failure.rejectedState, null, 2)}</pre>
            </details>
          )}
          {failure.retry && (
            <button
              className="sandbox-button"
              type="button"
              disabled={busy}
              onClick={failure.retry}
            >
              Повторить
            </button>
          )}
        </div>
      )}
    </>
  );
}
