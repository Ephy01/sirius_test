import { ParticipantWorkspace } from "../participant/ParticipantWorkspace";
import { AuthorPanel } from "./sandbox/AuthorPanel";
import { SandboxControls } from "./sandbox/SandboxControls";
import { useTaskSandbox, verdict } from "./sandbox/useTaskSandbox";
import "./task-sandbox.css";

/** Lets an author generate a task and play it as a participant would, without a contest. */
export function TaskSandbox({
  token,
  onClose,
}: {
  token: string;
  onClose: () => void;
}) {
  const sandbox = useTaskSandbox(token);
  const { catalog, catalogError, reloadCatalog, run, task, busy, failure } =
    sandbox;
  const source = catalog?.items.find((item) => item.key === run?.family);
  const problems = catalog?.problems ?? [];

  return (
    <div className="sandbox-page">
      <div className="sandbox-screen">
        <header className="sandbox-bar">
          <div className="sandbox-bar__heading">
            <div>
              <p className="eyebrow">Песочница автора</p>
              <h1>Проверка задачи</h1>
            </div>
            <button className="sandbox-button" type="button" onClick={onClose}>
              Закрыть
            </button>
          </div>
          {catalogError ? (
            <div className="sandbox-state" role="alert">
              <p>{catalogError}</p>
              <button
                className="sandbox-button"
                type="button"
                onClick={reloadCatalog}
              >
                Повторить
              </button>
            </div>
          ) : !catalog ? (
            <p className="sandbox-state" role="status">
              Загружаем семейства задач…
            </p>
          ) : (
            <SandboxControls sandbox={sandbox} />
          )}
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
              {run.evaluation && (
                <span>проверка: {verdict(run.evaluation)}</span>
              )}
            </p>
          )}
          {problems.length > 0 && (
            <p className="sandbox-bar__problems">
              Не загружены модули:{" "}
              {problems.map((problem) => problem.module).join(", ")}. Причины —
              в панели автора под задачей.
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
        </header>
        <div className="sandbox-stage">
          {task ? (
            <ParticipantWorkspace
              task={task}
              busy={busy}
              modeLabel="Песочница"
              assistantOffReply="В песочнице ассистент выключен. Команды работают как в попытке."
              {...sandbox.handlers}
              key={task.id}
            />
          ) : (
            <p className="sandbox-stage__empty">
              {busy
                ? "Генерируем вариант…"
                : "Выберите семейство и нажмите «Сгенерировать»: задача откроется так, как её увидит участник."}
            </p>
          )}
        </div>
      </div>
      <AuthorPanel run={run} problems={problems} />
    </div>
  );
}
