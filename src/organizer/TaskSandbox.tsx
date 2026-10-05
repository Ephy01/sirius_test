import { useMemo } from "react";
import { AuthorPanel } from "../sandbox/AuthorPanel";
import { serverSandbox } from "../sandbox/backend";
import { SandboxControls } from "../sandbox/SandboxControls";
import { SandboxReport } from "../sandbox/SandboxReport";
import { SandboxStage } from "../sandbox/SandboxStage";
import { useTaskSandbox } from "../sandbox/useTaskSandbox";
import "../sandbox/sandbox.css";

/** Lets an author generate a task and play it as a participant would, without a contest. */
export function TaskSandbox({
  token,
  onClose,
}: {
  token: string;
  onClose: () => void;
}) {
  const sandbox = useTaskSandbox(useMemo(() => serverSandbox(token), [token]));
  const { catalog, catalogError, reloadCatalog, run } = sandbox;

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
          <SandboxReport sandbox={sandbox} />
        </header>
        <SandboxStage
          sandbox={sandbox}
          emptyHint="Выберите семейство и нажмите «Сгенерировать»: задача откроется так, как её увидит участник."
        />
      </div>
      <AuthorPanel run={run} problems={catalog?.problems ?? []} />
    </div>
  );
}
