import type { ReactNode, RefObject } from "react";
import type {
  AiTurn,
  AiTurnRemaining,
  DebugAnswerResponse,
  ParticipantTask,
} from "../../api";
import type { TaskBehaviour } from "../../tasks/registry";
import type { ConsoleEntry } from "../consoleEntries";
import type { EmitTelemetry } from "../telemetry";

export type TaskTransitionResult = {
  ordinal: number;
  advanced: boolean;
  message?: string;
};

export type TaskMoveTransitionResult = TaskTransitionResult & {
  accepted: boolean;
  completed: boolean;
};

export type TaskCommandHandlers = {
  onAnswer: (answer: string) => Promise<TaskTransitionResult>;
  onSkip: () => Promise<TaskTransitionResult>;
  onNext: () => Promise<TaskTransitionResult>;
  onProbe?: (
    probe: string,
    clientActionId: string,
  ) => Promise<TaskMoveTransitionResult>;
  onHint?: (clientActionId: string) => Promise<TaskMoveTransitionResult>;
  onGetAnswer?: () => Promise<DebugAnswerResponse>;
  onApplyOperation?: (
    opId: string,
    clientActionId: string,
  ) => Promise<TaskMoveTransitionResult>;
  onUndo?: (clientActionId: string) => Promise<TaskMoveTransitionResult>;
  onReset?: (clientActionId: string) => Promise<TaskMoveTransitionResult>;
  onAiMessage?: (message: string, clientActionId: string) => Promise<AiTurn>;
  /** Reply to a line that is not a command when no assistant is connected. */
  assistantOffReply?: ReactNode;
};

export type CommandContext = TaskCommandHandlers & {
  task: ParticipantTask;
  isBusy: boolean;
  inFlight: { current: boolean };
  inputRef: RefObject<HTMLInputElement | null>;
  appendEntry: (author: ConsoleEntry["author"], content: ReactNode) => void;
  emitTelemetry: EmitTelemetry;
  setDraft: (draft: string) => void;
  setCommandBusy: (busy: boolean) => void;
  setAiThinking: (thinking: boolean) => void;
  setAiRemaining: (remaining: AiTurnRemaining) => void;
};

/** One submitted chat line: the workspace context plus the parsed input. */
export type CommandRun = CommandContext & {
  input: string;
  command: string;
  parts: string[];
  payload: string;
  behaviour: TaskBehaviour;
};

/**
 * A handler returns nothing when it finishes at once and a promise when it
 * waits for the server. The runner awaits only promises, so local replies
 * leave the input enabled.
 */
export type CommandHandler = (run: CommandRun) => void | Promise<void>;

export function reportClosedTask(run: CommandRun): boolean {
  if (run.task.status === "active") return false;
  run.appendEntry("system", "Текущая задача уже закрыта. Используйте /next.");
  return true;
}
