/** A request to `sirius_gate.editor.handle`, as JSON text. */
export type WorkerRequest = { id: number; request: string };

export type WorkerReply =
  | { type: "ready" }
  | { type: "boot_failed"; message: string }
  /** `response` is the JSON text Python returned, `failure` an error outside task code. */
  | { type: "reply"; id: number; response?: string; failure?: string };
