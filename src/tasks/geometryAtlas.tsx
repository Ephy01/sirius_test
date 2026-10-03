import { invalidResponse } from "../api/errors";
import { readString, type UnknownRecord } from "../api/parsing";
import type { PublicStateBase, TaskKind } from "./kind";
import {
  GeometryAtlasScene,
  parseGeometryScene,
  type GeometryScene,
} from "./shared/geometry";
import { readContent } from "./shared/zendoCards";

export type GeometryPublicState = {
  kind: "geometry_atlas";
  family: "geo_zendo" | "geo_transform" | "geo_probability";
  variant: string;
  prompt: string;
  scene: GeometryScene;
  content: Record<string, unknown>;
  responseHint: string;
};

function parseGeometryState(
  state: UnknownRecord,
  base: PublicStateBase,
): GeometryPublicState {
  const scene = parseGeometryScene(state.scene);
  const family = readString(state, "family");
  const variant = readString(state, "variant");
  if (
    !scene ||
    !variant ||
    (family !== "geo_zendo" &&
      family !== "geo_transform" &&
      family !== "geo_probability")
  ) {
    throw invalidResponse(
      "Сервер вернул некорректную геометрическую сцену.",
      state,
    );
  }
  return {
    kind: "geometry_atlas",
    family,
    variant,
    ...base,
    scene,
    content: readContent(state),
  };
}

export const geometryAtlas: TaskKind<GeometryPublicState> = {
  parse: parseGeometryState,
  renderScene: ({ state, family, canAct, onCommand }) => (
    <GeometryAtlasScene
      scene={state.scene}
      content={state.content}
      showGrid={false}
      canProbe={canAct && family === "geo_zendo"}
      onProbe={(cardId) => onCommand(`/test ${cardId}`)}
    />
  ),
};
