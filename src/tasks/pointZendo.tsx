import { invalidResponse } from "../api/errors";
import { readString, type UnknownRecord } from "../api/parsing";
import type { PublicStateBase, TaskKind } from "./kind";
import {
  GeometryAtlasScene,
  parseGeometryScene,
  type GeometryScene,
} from "./shared/geometry";
import { zendoBehaviour } from "./shared/zendo";
import { readContent } from "./shared/zendoCards";

export type PointZendoPublicState = {
  kind: "point_zendo";
  family: "point_zendo";
  variant: string;
  prompt: string;
  scene: GeometryScene;
  content: Record<string, unknown>;
  responseHint: string;
};

function parsePointZendoState(
  state: UnknownRecord,
  base: PublicStateBase,
): PointZendoPublicState {
  const scene = parseGeometryScene(state.scene);
  const variant = readString(state, "variant");
  if (!scene || !variant) {
    throw invalidResponse("Сервер вернул некорректную сцену point_zendo.", state);
  }

  return {
    kind: "point_zendo",
    family: "point_zendo",
    variant,
    ...base,
    scene,
    content: readContent(state),
  };
}

export const pointZendo: TaskKind<PointZendoPublicState> = {
  parse: parsePointZendoState,
  renderScene: ({ state, canAct, onCommand }) => (
    <GeometryAtlasScene
      scene={state.scene}
      content={state.content}
      showGrid
      canProbe={canAct}
      onProbe={(cardId) => onCommand(`/test ${cardId}`)}
    />
  ),
  ...zendoBehaviour("все рисунки даны в одной системе обозначений"),
};
