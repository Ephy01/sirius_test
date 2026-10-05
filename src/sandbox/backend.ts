import {
  api,
  type SandboxAnswer,
  type SandboxAnswerInput,
  type SandboxInteraction,
  type SandboxInteractionInput,
  type SandboxTask,
  type SandboxTaskInput,
  type TaskFamilyCatalog,
} from "../api";

/** Where sandbox tasks are generated and checked: the server or Python in the author's browser. */
export type SandboxBackend = {
  /** Families that can be opened and the modules that failed to load. */
  catalog(signal?: AbortSignal): Promise<TaskFamilyCatalog>;
  /** Reads the task code again and returns the new catalog. */
  reload(): Promise<TaskFamilyCatalog>;
  generate(input: SandboxTaskInput): Promise<SandboxTask>;
  interact(input: SandboxInteractionInput): Promise<SandboxInteraction>;
  answer(input: SandboxAnswerInput): Promise<SandboxAnswer>;
};

export function serverSandbox(token: string): SandboxBackend {
  return {
    catalog: (signal) => api.listTaskFamilies({ token, signal }),
    reload: () => api.reloadTaskModules({ token }),
    generate: (input) => api.generateSandboxTask(input, { token }),
    interact: (input) => api.interactInSandbox(input, { token }),
    answer: (input) => api.answerInSandbox(input, { token }),
  };
}
