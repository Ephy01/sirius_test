import { useEffect, useMemo, useRef, useState } from "react";
import starterTask from "../../backend/sirius_gate/examples/two_numbers.py?raw";
import { isRecord } from "../api";
import { Brand } from "../components";
import { AuthorPanel } from "../sandbox/AuthorPanel";
import { SandboxReport } from "../sandbox/SandboxReport";
import { SandboxStage } from "../sandbox/SandboxStage";
import { useTaskSandbox } from "../sandbox/useTaskSandbox";
import { CodeEditor } from "./CodeEditor";
import { EditorControls } from "./EditorControls";
import { editorSandbox } from "./editorSandbox";
import { PreviewFrame } from "./PreviewFrame";
import { PythonRuntime, type PythonStatus } from "./python/runtime";
import "../sandbox/sandbox.css";
import "./task-editor.css";

const DRAFT_KEY = "sirius-gate.task-editor.draft";
const CHECK_TIMEOUT_MS = 90_000;
const STATUS_TEXT: Record<PythonStatus, string> = {
  starting: "Запускаем Python…",
  ready: "Python готов",
  failed: "Python не запустился",
};

type CheckReport = { running: boolean; text: string };

function storedDraft(): string | null {
  try {
    return window.localStorage.getItem(DRAFT_KEY);
  } catch {
    return null;
  }
}

function storeDraft(code: string) {
  try {
    window.localStorage.setItem(DRAFT_KEY, code);
  } catch {
    // The draft is a convenience: without storage the editor still works.
  }
}

function download(code: string, name: string) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([code], { type: "text/x-python" }));
  link.download = `${name}.py`;
  link.click();
  URL.revokeObjectURL(link.href);
}

/** Write a task in Python and see it as a participant will, with the code running in this browser. */
export default function TaskEditor() {
  const [code, setCode] = useState(() => storedDraft() ?? starterTask);
  // Read by a run that may start before the next render, such as Ctrl+Enter right after typing.
  const latestCode = useRef(code);
  const runtime = useMemo(() => new PythonRuntime(), []);
  const backend = useMemo(
    () => editorSandbox(runtime, () => latestCode.current),
    [runtime],
  );
  const sandbox = useTaskSandbox(backend);
  const [status, setStatus] = useState<PythonStatus>("starting");
  const [report, setReport] = useState<CheckReport | null>(null);
  const opened = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => runtime.onStatus(setStatus), [runtime]);
  useEffect(() => () => runtime.dispose(), [runtime]);
  useEffect(() => storeDraft(code), [code]);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    void sandbox.reloadAndGenerate();
  }, []);

  function replaceCode(next: string) {
    latestCode.current = next;
    setCode(next);
  }

  async function check() {
    setReport({ running: true, text: "" });
    const run = await sandbox.reloadAndGenerate();
    if (!run) {
      setReport(null);
      return;
    }
    try {
      const result = await runtime.call(
        "check",
        { family: run.family },
        CHECK_TIMEOUT_MS,
      );
      setReport({
        running: false,
        text: isRecord(result) ? String(result.report) : "",
      });
    } catch (caught) {
      setReport({
        running: false,
        text: caught instanceof Error ? caught.message : "Проверка не выполнена.",
      });
    }
  }

  return (
    <div className="task-editor">
      <header className="task-editor__bar">
        <div className="task-editor__title">
          <Brand />
          <div>
            <p className="eyebrow">Редактор задач</p>
            <p className={`task-editor__status task-editor__status--${status}`}>
              {STATUS_TEXT[status]}
            </p>
          </div>
        </div>
        <EditorControls
          sandbox={sandbox}
          onRun={() => void sandbox.reloadAndGenerate()}
          onCheck={() => void check()}
        />
        <div className="task-editor__files">
          <button
            className="sandbox-button"
            type="button"
            onClick={() => fileInput.current?.click()}
          >
            Открыть файл
          </button>
          <button
            className="sandbox-button"
            type="button"
            onClick={() => download(code, sandbox.family?.key ?? "task")}
          >
            Скачать
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".py,text/x-python"
            hidden
            onChange={async (event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) replaceCode(await file.text());
            }}
          />
        </div>
      </header>
      <div className="task-editor__panes">
        <section className="task-editor__code" aria-label="Код задачи">
          <CodeEditor
            value={code}
            onChange={replaceCode}
            onRun={() => void sandbox.reloadAndGenerate()}
          />
          {report && (
            <div className="task-editor__report" role="status">
              <header>
                <strong>Проверка модуля</strong>
                <button
                  className="sandbox-button"
                  type="button"
                  onClick={() => setReport(null)}
                >
                  Скрыть
                </button>
              </header>
              <pre>
                {report.running
                  ? "Создаём варианты на каждой сложности…"
                  : report.text}
              </pre>
            </div>
          )}
        </section>
        <section className="task-editor__preview" aria-label="Задача">
          <PreviewFrame title="Задача глазами участника">
            <div className="sandbox-page">
              <div className="sandbox-screen sandbox-screen--framed">
                <header className="sandbox-bar">
                  <SandboxReport sandbox={sandbox} />
                </header>
                <SandboxStage
                  sandbox={sandbox}
                  emptyHint={
                    status === "starting"
                      ? "Запускаем Python: в первый раз он загружается около минуты."
                      : "Нажмите «Запустить»: задача откроется так, как её увидит участник."
                  }
                />
              </div>
              <AuthorPanel
                run={sandbox.run}
                problems={sandbox.catalog?.problems ?? []}
              />
            </div>
          </PreviewFrame>
        </section>
      </div>
    </div>
  );
}
