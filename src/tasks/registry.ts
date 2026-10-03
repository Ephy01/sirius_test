import { readString, requiredString, type UnknownRecord } from "../api/parsing";
import { chessCoverage } from "./chessCoverage";
import { classicMath } from "./classicMath";
import { diceChessInventory, diceChessPosition } from "./diceChess";
import { foldPunch } from "./foldPunch";
import { geometryAtlas } from "./geometryAtlas";
import { gridZendo } from "./gridZendo";
import { hiddenWiring } from "./hiddenWiring";
import {
  unsupportedTaskKind,
  type TaskKind,
  type TaskSceneProps,
} from "./kind";
import { leaperBoard } from "./leaperBoard";
import { machinePanel } from "./machinePanel";
import { pointZendo } from "./pointZendo";
import { tokenZendo } from "./tokenZendo";

export const TASK_KINDS = {
  chess_coverage: chessCoverage,
  dice_chess_board_inventory_probability: diceChessInventory,
  dice_chess_position_probability: diceChessPosition,
  geometry_atlas: geometryAtlas,
  hidden_wiring: hiddenWiring,
  fold_punch: foldPunch,
  grid_zendo: gridZendo,
  point_zendo: pointZendo,
  token_zendo: tokenZendo,
  machine_panel: machinePanel,
  chess: leaperBoard,
  classic_math_free_response: classicMath,
};

export type TaskPublicState = ReturnType<
  (typeof TASK_KINDS)[keyof typeof TASK_KINDS]["parse"]
>;

function taskKind(
  kind: string | undefined,
): TaskKind<TaskPublicState> | undefined {
  return kind !== undefined && Object.hasOwn(TASK_KINDS, kind)
    ? TASK_KINDS[kind as keyof typeof TASK_KINDS]
    : undefined;
}

export function parsePublicState(state: UnknownRecord): TaskPublicState {
  const kind = readString(state, "kind");
  const prompt = requiredString(state, "task.prompt", "prompt");
  const definition = taskKind(kind);
  if (!definition) throw unsupportedTaskKind(state);

  return definition.parse(state, {
    prompt,
    responseHint:
      readString(state, "responseHint", "response_hint") ??
      definition.defaultResponseHint ??
      "/answer ваш ответ",
  });
}

export function TaskScene(props: TaskSceneProps<TaskPublicState>) {
  return taskKind(props.state.kind)?.renderScene(props) ?? null;
}
