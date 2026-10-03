import type { ParticipantTask } from "../api";

export function taskTraits(task: ParticipantTask) {
  const state = task.publicState;
  const diceChess =
    state.kind === "dice_chess_position_probability" ||
    state.kind === "dice_chess_board_inventory_probability"
      ? state
      : null;
  const classicMath =
    state.kind === "classic_math_free_response" ? state : null;
  const isZendo =
    (state.kind === "geometry_atlas" && task.family === "geo_zendo") ||
    state.kind === "token_zendo" ||
    state.kind === "point_zendo" ||
    state.kind === "grid_zendo";
  const isMachine =
    state.kind === "machine_panel" ||
    (state.kind === "chess" && task.family === "machine_reach");
  const isWiring = state.kind === "hidden_wiring";
  const isChessCoverage = state.kind === "chess_coverage";

  return {
    diceChess,
    classicMath,
    isZendo,
    isMachine,
    isWiring,
    isChessCoverage,
  };
}
