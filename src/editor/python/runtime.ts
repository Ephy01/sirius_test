import { ApiError, isRecord } from "../../api";
import type { WorkerReply } from "./protocol";

export type PythonStatus = "starting" | "ready" | "failed";

const CALL_TIMEOUT_MS = 10_000;
const TASK_CODE_FAILED = "TASK_CODE_FAILED";

type Call = {
  resolve(response: string): void;
  reject(error: Error): void;
};

/**
 * Python in a background thread of the author's browser.
 * Requests run one at a time. A request that takes too long stops the thread,
 * because that is the only way to interrupt a loop in task code.
 */
export class PythonRuntime {
  /** Grows each time the thread is stopped: everything loaded into Python is gone. */
  restarts = 0;
  private worker: Worker | null = null;
  private ready: Promise<void> | null = null;
  private current: Call | null = null;
  private abortStart: ((error: Error) => void) | null = null;
  private queue: Promise<unknown> = Promise.resolve();
  private nextId = 1;
  private status: PythonStatus = "starting";
  private listeners = new Set<(status: PythonStatus) => void>();

  onStatus(listener: (status: PythonStatus) => void) {
    this.listeners.add(listener);
    listener(this.status);
    return () => void this.listeners.delete(listener);
  }

  /** Starts loading Python ahead of the first request. */
  warmUp() {
    void this.start().catch(() => undefined);
  }

  call<Result>(
    op: string,
    args: object,
    timeoutMs = CALL_TIMEOUT_MS,
  ): Promise<Result> {
    const result = this.queue.then(() => this.send(op, args, timeoutMs));
    this.queue = result.catch(() => undefined);
    return result as Promise<Result>;
  }

  dispose() {
    this.stop(new Error("Редактор закрыт."));
    this.listeners.clear();
  }

  private setStatus(status: PythonStatus) {
    this.status = status;
    this.listeners.forEach((listener) => listener(status));
  }

  private start(): Promise<void> {
    if (this.ready) return this.ready;
    const worker = new Worker(new URL("./worker.ts", import.meta.url), {
      type: "module",
    });
    this.worker = worker;
    this.setStatus("starting");
    this.ready = new Promise<void>((resolve, reject) => {
      this.abortStart = reject;
      const fail = (message: string) => {
        this.stop(
          new ApiError(503, {
            code: "python_unavailable",
            message: `Не удалось запустить Python в браузере: ${message}`,
          }),
        );
        this.setStatus("failed");
      };
      worker.onerror = (event) => fail(event.message || "ошибка загрузки");
      worker.onmessage = ({ data }: MessageEvent<WorkerReply>) => {
        if (data.type === "ready") {
          this.abortStart = null;
          this.setStatus("ready");
          resolve();
        } else if (data.type === "boot_failed") {
          fail(data.message);
        } else if (data.failure !== undefined) {
          this.current?.reject(new Error(data.failure));
        } else {
          this.current?.resolve(data.response ?? "");
        }
      };
    });
    return this.ready;
  }

  /** Whoever waits for the thread gets `reason`: a stopped thread answers nobody. */
  private stop(reason: Error) {
    this.worker?.terminate();
    this.worker = null;
    this.ready = null;
    this.restarts += 1;
    this.abortStart?.(reason);
    this.abortStart = null;
    this.current?.reject(reason);
  }

  private async send(op: string, args: object, timeoutMs: number) {
    await this.start();
    const response = await new Promise<string>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        this.stop(
          new ApiError(408, {
            code: TASK_CODE_FAILED,
            message: `Код задачи не ответил за ${timeoutMs / 1000} с и был остановлен. Проверьте, нет ли в нём бесконечного цикла.`,
          }),
        );
        this.warmUp();
      }, timeoutMs);
      const settle = () => {
        window.clearTimeout(timer);
        this.current = null;
      };
      this.current = {
        resolve: (value) => (settle(), resolve(value)),
        reject: (error) => (settle(), reject(error)),
      };
      this.worker?.postMessage({
        id: this.nextId++,
        request: JSON.stringify({ op, args }),
      });
    });
    const reply: unknown = JSON.parse(response);
    if (isRecord(reply) && isRecord(reply.error)) {
      throw new ApiError(422, {
        code: String(reply.error.code),
        message: String(reply.error.message),
      });
    }
    return isRecord(reply) ? reply.result : undefined;
  }
}
