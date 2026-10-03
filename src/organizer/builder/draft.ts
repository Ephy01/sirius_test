import type {
  ContestSummary,
  TaskFamily,
  TaskFamilyCatalog,
} from "../../api";
import type { TaskFamilyConfig } from "../families";

export type NumericDraft = number | "";

export type TaskFamilyDraftConfig = Omit<
  TaskFamilyConfig,
  "weight" | "initialDifficulty" | "maxDifficulty"
> & {
  card: TaskFamily;
  weight: NumericDraft;
  initialDifficulty: NumericDraft;
  maxDifficulty: NumericDraft;
};

export type ContestAiConfig = {
  enabled: boolean;
  mode: "socratic" | "open";
  maxTurnsPerAttempt: number;
  maxTurnsPerTask: number;
};

export type ScriptedTaskConfig = {
  family: string;
  subKind: string;
  position: number;
};

export type ContestDraftInput = {
  title: string;
  durationMinutes: number;
  taskConfig: {
    adaptationThreshold: number;
    cohortSeed?: string;
    debugRevealAnswers?: boolean;
    ai?: ContestAiConfig;
    families: TaskFamilyConfig[];
    scriptedTasks: ScriptedTaskConfig[];
  };
};

export type ParticipantDraft = {
  externalRef: string;
  displayName: string;
};

export type GeneratedCodeRow = ParticipantDraft & {
  enrollmentId: string;
  code: string;
};

export type ContestBuilderProps = {
  onCancel: () => void;
  onLoadFamilies: (signal?: AbortSignal) => Promise<TaskFamilyCatalog>;
  onCreateContest: (input: ContestDraftInput) => Promise<ContestSummary>;
  onAddParticipants: (
    contestId: string,
    participants: ParticipantDraft[],
  ) => Promise<void>;
  onGenerateCodes: (contestId: string) => Promise<GeneratedCodeRow[]>;
  onPublish: (contestId: string) => Promise<ContestSummary>;
};

export function numericDraft(value: string): NumericDraft {
  if (value === "") return "";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : "";
}

export function isIntegerInRange(
  value: NumericDraft,
  minimum: number,
  maximum: number,
): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= minimum &&
    value <= maximum
  );
}

export function draftNumber(value: NumericDraft, fallback: number): number {
  return typeof value === "number" ? value : fallback;
}

export function newParticipant(): ParticipantDraft {
  return { externalRef: "", displayName: "" };
}
