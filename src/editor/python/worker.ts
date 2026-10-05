// Runs the `sirius_gate` package in Python compiled to WebAssembly, off the page thread.
import type { loadPyodide as LoadPyodide } from "pyodide";
import type { WorkerReply, WorkerRequest } from "./protocol";

type Scope = {
  location: Location;
  onmessage: ((event: MessageEvent<WorkerRequest>) => void) | null;
  postMessage(reply: WorkerReply): void;
};

const scope = self as unknown as Scope;
const PACKAGE_DIRECTORY = "/platform/sirius_gate";
const RUNTIME_URL = new URL(
  `${import.meta.env.BASE_URL}pyodide/`,
  scope.location.origin,
).href;
/** The same files the server imports, so a task behaves the same in both places. */
const PACKAGE_SOURCES = import.meta.glob<string>(
  "../../../backend/sirius_gate/*.py",
  { query: "?raw", import: "default", eager: true },
);

async function boot(): Promise<(request: string) => string> {
  const { loadPyodide } = (await import(
    /* @vite-ignore */ `${RUNTIME_URL}pyodide.mjs`
  )) as { loadPyodide: typeof LoadPyodide };
  const python = await loadPyodide({ indexURL: RUNTIME_URL });
  python.FS.mkdirTree(PACKAGE_DIRECTORY);
  for (const [path, source] of Object.entries(PACKAGE_SOURCES)) {
    python.FS.writeFile(`${PACKAGE_DIRECTORY}/${path.split("/").pop()}`, source);
  }
  python.runPython("import sys; sys.path.insert(0, '/platform')");
  return python.pyimport("sirius_gate.editor").handle;
}

const handle = boot();
handle.then(
  () => scope.postMessage({ type: "ready" }),
  (caught: unknown) =>
    scope.postMessage({
      type: "boot_failed",
      message: caught instanceof Error ? caught.message : String(caught),
    }),
);

scope.onmessage = async ({ data }) => {
  try {
    scope.postMessage({
      type: "reply",
      id: data.id,
      response: (await handle)(data.request),
    });
  } catch (caught) {
    scope.postMessage({
      type: "reply",
      id: data.id,
      failure: caught instanceof Error ? caught.message : String(caught),
    });
  }
};
