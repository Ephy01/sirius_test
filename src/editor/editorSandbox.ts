import {
  ApiError,
  parseSandboxAnswer,
  parseSandboxInteraction,
  parseSandboxTask,
  parseTaskFamilyCatalog,
  sandboxAnswerBody,
  sandboxInteractionBody,
  sandboxTaskBody,
  type TaskFamilyCatalog,
} from "../api";
import type { SandboxBackend } from "../sandbox/backend";
import type { PythonRuntime } from "./python/runtime";

const TASK_CODE_FAILED = "TASK_CODE_FAILED";
const NO_FAMILIES: TaskFamilyCatalog = { items: [], problems: [] };

/**
 * Sandbox backend of the task editor: the code in the editor runs in the author's browser.
 * `source` returns the text that is in the editor now.
 */
export function editorSandbox(
  runtime: PythonRuntime,
  source: () => string,
): SandboxBackend {
  let loaded: { text: string; restarts: number } | null = null;

  async function load(): Promise<TaskFamilyCatalog> {
    const text = source();
    const catalog = parseTaskFamilyCatalog(
      await runtime.call("load", { source: text }),
    );
    loaded = { text, restarts: runtime.restarts };
    return catalog;
  }

  /** Python forgets the task when its thread is stopped, so the last text that worked is loaded again. */
  async function call(op: string, args: object): Promise<unknown> {
    if (loaded && loaded.restarts !== runtime.restarts) {
      await runtime.call("load", { source: loaded.text });
      loaded.restarts = runtime.restarts;
    }
    return runtime.call(op, args);
  }

  return {
    /** Text with an error opens the editor with no families: the error is shown on the first run. */
    catalog: () =>
      load().catch((caught) => {
        if (caught instanceof ApiError && caught.code === TASK_CODE_FAILED) {
          return NO_FAMILIES;
        }
        throw caught;
      }),
    reload: load,
    generate: async (input) =>
      parseSandboxTask(await call("generate", sandboxTaskBody(input))),
    interact: async (input) =>
      parseSandboxInteraction(
        await call("interact", sandboxInteractionBody(input)),
      ),
    answer: async (input) =>
      parseSandboxAnswer(await call("answer", sandboxAnswerBody(input))),
  };
}
