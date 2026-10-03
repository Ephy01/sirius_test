import { invalidResponse } from "../api/errors";
import { readString, type UnknownRecord } from "../api/parsing";
import type { PublicStateBase, TaskKind, TaskSubject } from "./kind";
import {
  GeometryAtlasScene,
  parseGeometryScene,
  type GeometryScene,
} from "./shared/geometry";
import { zendoBehaviour } from "./shared/zendo";
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

function hasHiddenRule({ family }: TaskSubject<unknown>): boolean {
  return family === "geo_zendo";
}

export const geometryAtlas: TaskKind<GeometryPublicState> = {
  parse: parseGeometryState,
  renderScene: (task) => (
    <GeometryAtlasScene
      scene={task.state.scene}
      content={task.state.content}
      showGrid={false}
      canProbe={task.canAct && hasHiddenRule(task)}
      onProbe={(cardId) => task.onCommand(`/test ${cardId}`)}
    />
  ),
  ...zendoBehaviour(
    "все рисунки даны в одной системе обозначений",
    hasHiddenRule,
  ),
  statement: (task) =>
    hasHiddenRule(task)
      ? {
          prompt: task.state.prompt
            .replaceAll("Конструкции", "Графы")
            .replaceAll("конструкции", "графы")
            .replaceAll("конструкций", "графов"),
        }
      : {},
};
