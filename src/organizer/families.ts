import type { TaskFamily, TaskFamilyCatalog } from "../api";

export type TaskFamilyConfig = {
  key: string;
  skin: string | null;
  enabled: boolean;
  weight: number;
  initialDifficulty: number;
  maxDifficulty: number;
  subKinds?: string[];
};

/** Rotation settings a family starts with in the builder. */
export function defaultFamilyConfig(family: TaskFamily): TaskFamilyConfig {
  return {
    key: family.key,
    skin: family.defaultSkin,
    enabled: true,
    weight: family.defaultWeight,
    initialDifficulty: family.minDifficulty,
    maxDifficulty: family.maxDifficulty,
    ...(family.variants.length > 0
      ? { subKinds: family.variants.map((variant) => variant.key) }
      : {}),
  };
}

/** The family whose variants are pinned to a position, not rotated. */
export function scriptedFamily(
  catalog: TaskFamilyCatalog,
): TaskFamily | undefined {
  return catalog.items.find(
    (family) => family.scriptedOnly && family.variants.length > 0,
  );
}
