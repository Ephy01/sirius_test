import type { ReactNode } from "react";
import { ApiError } from "../api/errors";
import type { UnknownRecord } from "../api/parsing";

export type PublicStateBase = {
  prompt: string;
  responseHint: string;
};

export type TaskSceneProps<State> = {
  state: State;
  family: string;
  canAct: boolean;
  onCommand: (command: string) => void;
};

export type TaskKind<State> = {
  defaultResponseHint?: string;
  parse(state: UnknownRecord, base: PublicStateBase): State;
  renderScene(props: TaskSceneProps<State>): ReactNode;
};

export function unsupportedTaskKind(state: UnknownRecord): ApiError {
  return new ApiError(502, {
    code: "unsupported_task_kind",
    message: "Этот тип задачи пока не поддерживается интерфейсом.",
    details: state,
  });
}
