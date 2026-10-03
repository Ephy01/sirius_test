import type { ReactNode } from "react";
import { ApiError } from "../api/errors";
import type { UnknownRecord } from "../api/parsing";

export type PublicStateBase = {
  prompt: string;
  responseHint: string;
};

export type TaskSubject<State> = {
  state: State;
  family: string;
};

export type TaskSceneProps<State> = TaskSubject<State> & {
  canAct: boolean;
  onCommand: (command: string) => void;
};

/** Chat commands a kind can switch on in addition to /answer, /skip and /next. */
export const TASK_COMMANDS = [
  "probe",
  "hint",
  "op",
  "undo",
  "reset",
  "done",
] as const;

export type TaskCommand = (typeof TASK_COMMANDS)[number];

export type TaskOpening = {
  opened?: ReactNode;
  guide?: ReactNode;
};

export type TaskStatement = {
  heading?: string;
  prompt?: string;
  question?: string;
  appendix?: ReactNode;
};

export type TaskAnswerOption = {
  id: string;
  label: string;
};

export type TaskQuickAction = {
  label: string;
  ariaLabel: string;
  disabled?: boolean;
} & ({ command: string } | { draftPrefix: string });

/**
 * Everything the client knows about one task kind.
 * Only `parse` and `renderScene` are required: a kind without the optional
 * members is a plain task answered with `/answer <text>`.
 */
export type TaskKind<State> = {
  /** Response hint used when the server sends none. */
  defaultResponseHint?: string;
  /** The task has no scene and the statement takes the whole stage. */
  textOnly?(task: TaskSubject<State>): boolean;
  parse(state: UnknownRecord, base: PublicStateBase): State;
  renderScene(props: TaskSceneProps<State>): ReactNode;
  /** Commands the task accepts: /test, /hint, /op, /undo, /reset, bare done or impossible. */
  commands?(task: TaskSubject<State>): readonly TaskCommand[];
  /** Reply to /help. */
  help?(task: TaskSubject<State>): ReactNode;
  /** The two chat messages shown when the task opens. */
  opening?(task: TaskSubject<State>, number: ReactNode): TaskOpening;
  /** Statement details: heading, rewritten prompt, closing question, block after the text. */
  statement?(task: TaskSubject<State>): TaskStatement;
  /** How to answer. `null` hides the paragraph. */
  answerGuide?(task: TaskSubject<State>): ReactNode;
  /** Commands worth knowing besides /answer. */
  commandGuide?(task: TaskSubject<State>): ReactNode;
  /** Example printed when /answer comes without a value. */
  answerExample?(task: TaskSubject<State>): string | undefined;
  /** Ready answers shown as buttons. A click sends `/answer <id>`. */
  answerOptions?(task: TaskSubject<State>): readonly TaskAnswerOption[];
  /** Short facts under the guides: counters, limits, reminders. */
  metaLines?(task: TaskSubject<State>): readonly string[];
  /** Extra buttons above the chat input. */
  quickActions?(task: TaskSubject<State>): readonly TaskQuickAction[];
};

export function unsupportedTaskKind(state: UnknownRecord): ApiError {
  return new ApiError(502, {
    code: "unsupported_task_kind",
    message: "Этот тип задачи пока не поддерживается интерфейсом.",
    details: state,
  });
}
