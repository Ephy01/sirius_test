import { useEffect, useState } from "react";
import {
  ApiError,
  type DebugAnswerResponse,
  type ParticipantTask,
  type SandboxMove,
  type SandboxTask,
  type SandboxTaskState,
  type TaskFamily,
  type TaskFamilyCatalog,
  type UnknownRecord,
} from "../api";
import {
  isIntegerInRange,
  type NumericDraft,
} from "../organizer/builder/draft";
import type {
  TaskMoveTransitionResult,
  TaskTransitionResult,
} from "../participant/commands";
import type { SandboxBackend } from "./backend";

/** One generated variant together with what the author did to it. */
export type SandboxRun = {
  number: number;
  family: string;
  subKind: string | null;
  generatorVersion: string;
  seed: number;
  difficulty: number;
  state: SandboxTaskState;
  closed: boolean;
  evaluation: UnknownRecord | null;
};

/** What a variant is generated from. */
type Selection = {
  family: TaskFamily;
  variant: string;
  difficulty: NumericDraft;
};

export type SandboxFailure = {
  /** Task code raised an exception: its text is the message. */
  inTaskCode: boolean;
  message: string;
  /** The public state the client refused to draw. */
  rejectedState?: unknown;
  retry?: () => void;
};

const TASK_CODE_FAILED = "TASK_CODE_FAILED";
const REJECTED_STATE_CODES = ["invalid_api_response", "unsupported_task_kind"];

function failureOf(caught: unknown, retry?: () => void): SandboxFailure {
  if (!(caught instanceof ApiError)) {
    return {
      inTaskCode: false,
      message:
        caught instanceof Error ? caught.message : "Запрос не выполнен.",
      retry,
    };
  }
  return {
    inTaskCode: caught.code === TASK_CODE_FAILED,
    message: caught.message,
    rejectedState: REJECTED_STATE_CODES.includes(caught.code ?? "")
      ? caught.details
      : undefined,
    retry,
  };
}

function taskState(source: SandboxTaskState): SandboxTaskState {
  return {
    publicState: source.publicState,
    stateText: source.stateText,
    referenceAnswer: source.referenceAnswer,
    referenceCommands: source.referenceCommands,
    details: source.details,
  };
}

/** What the check says about the answer, in the words shown to the author. */
export function verdict(evaluation: UnknownRecord) {
  if (evaluation.correct === true) return "верно";
  if (evaluation.correct === false) return "неверно";
  return "без оценки";
}

function defaultVariant(family: TaskFamily) {
  return family.scriptedOnly ? (family.variants[0]?.key ?? "") : "";
}

export function useTaskSandbox(backend: SandboxBackend) {
  const [catalog, setCatalog] = useState<TaskFamilyCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [familyKey, setFamilyKey] = useState("");
  const [variant, setVariant] = useState("");
  const [difficulty, setDifficulty] = useState<NumericDraft>(1);
  const [seed, setSeed] = useState("");
  const [run, setRun] = useState<SandboxRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [failure, setFailure] = useState<SandboxFailure | null>(null);

  const family = catalog?.items.find((item) => item.key === familyKey);

  function select(next: Selection): Selection {
    setFamilyKey(next.family.key);
    setVariant(next.variant);
    setDifficulty(next.difficulty);
    return next;
  }

  function selectFamily(next: TaskFamily) {
    select({
      family: next,
      variant: defaultVariant(next),
      difficulty: next.minDifficulty,
    });
    setNotice("");
  }

  /** Keeps the author's settings when the family survived the reload. */
  function adoptCatalog(loaded: TaskFamilyCatalog): Selection | null {
    setCatalog(loaded);
    const kept = loaded.items.find((item) => item.key === familyKey);
    if (!kept) {
      const first = loaded.items.at(0);
      if (!first) return null;
      setNotice("");
      return select({
        family: first,
        variant: defaultVariant(first),
        difficulty: first.minDifficulty,
      });
    }
    return select({
      family: kept,
      variant: kept.variants.some((item) => item.key === variant)
        ? variant
        : defaultVariant(kept),
      difficulty: isIntegerInRange(
        difficulty,
        kept.minDifficulty,
        kept.maxDifficulty,
      )
        ? difficulty
        : kept.minDifficulty,
    });
  }

  async function loadCatalog(signal?: AbortSignal) {
    setCatalogError("");
    try {
      const loaded = await backend.catalog(signal);
      if (signal?.aborted) return;
      adoptCatalog(loaded);
    } catch (caught) {
      if (signal?.aborted) return;
      setCatalogError(
        caught instanceof Error
          ? caught.message
          : "Не удалось загрузить семейства задач.",
      );
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void loadCatalog(controller.signal);
    return () => controller.abort();
  }, [backend]);

  async function fromControls<Result>(
    action: () => Promise<Result>,
    retry: () => void,
  ): Promise<Result | null> {
    setBusy(true);
    setNotice("");
    setFailure(null);
    try {
      return await action();
    } catch (caught) {
      setFailure(failureOf(caught, retry));
      return null;
    } finally {
      setBusy(false);
    }
  }

  function openRun(task: SandboxTask, subKind: string | null): SandboxRun {
    const opened = {
      number: (run?.number ?? 0) + 1,
      family: task.family,
      subKind,
      generatorVersion: task.generatorVersion,
      seed: task.seed,
      difficulty: task.difficulty,
      state: taskState(task),
      closed: false,
      evaluation: null,
    };
    setRun(opened);
    return opened;
  }

  /** The request for a variant, or `null` with a notice when the settings are wrong. */
  function taskInput(selection: Selection, anotherSeed: boolean) {
    const { minDifficulty, maxDifficulty } = selection.family;
    if (!isIntegerInRange(selection.difficulty, minDifficulty, maxDifficulty)) {
      setNotice(
        `Сложность должна быть целым числом от ${minDifficulty} до ${maxDifficulty}.`,
      );
      return null;
    }
    const fixedSeed = anotherSeed ? "" : seed.trim();
    if (
      fixedSeed &&
      !(/^\d+$/.test(fixedSeed) && Number.isSafeInteger(Number(fixedSeed)))
    ) {
      setNotice(
        `Сид должен быть целым числом от 0 до ${Number.MAX_SAFE_INTEGER}.`,
      );
      return null;
    }
    return {
      family: selection.family.key,
      difficulty: selection.difficulty,
      seed: fixedSeed ? Number(fixedSeed) : null,
      subKind: selection.variant || null,
    };
  }

  /** `anotherSeed` ignores the seed field: same settings, a new random variant. */
  async function generate(anotherSeed: boolean): Promise<SandboxRun | null> {
    if (!family) return null;
    const input = taskInput({ family, variant, difficulty }, anotherSeed);
    if (!input) return null;
    return fromControls(
      async () => openRun(await backend.generate(input), input.subKind),
      () => void generate(anotherSeed),
    );
  }

  function reloadModules() {
    return fromControls(
      async () => adoptCatalog(await backend.reload()),
      () => void reloadModules(),
    );
  }

  /** Reads the task code again and opens a variant of what it now defines. */
  function reloadAndGenerate() {
    return fromControls(
      async () => {
        const selection = adoptCatalog(await backend.reload());
        const input = selection && taskInput(selection, false);
        if (!input) return null;
        return openRun(await backend.generate(input), input.subKind);
      },
      () => void reloadAndGenerate(),
    );
  }

  function activeRun(): SandboxRun {
    if (!run || run.closed) throw new Error("Текущая задача уже закрыта.");
    return run;
  }

  /** A slow answer must not overwrite a variant generated in the meantime. */
  function updateRun(number: number, patch: Partial<SandboxRun>) {
    setRun((latest) =>
      latest?.number === number ? { ...latest, ...patch } : latest,
    );
  }

  async function answer(value: string): Promise<TaskTransitionResult> {
    const current = activeRun();
    const reply = { ordinal: current.number, advanced: false };
    try {
      const { evaluation, finalized } = await backend.answer({
        family: current.family,
        answer: value,
        stateText: current.state.stateText,
      });
      setFailure(null);
      updateRun(current.number, { closed: finalized, evaluation });
      if (finalized) {
        return {
          ...reply,
          message: `Ответ проверен: ${verdict(evaluation)}. Задача закрыта, /next откроет другой вариант.`,
        };
      }
      return {
        ...reply,
        message:
          typeof evaluation.feedback === "string" && evaluation.feedback
            ? evaluation.feedback
            : "Ответ не принят как окончательный, задача остаётся открытой.",
      };
    } catch (caught) {
      const failed = failureOf(caught);
      setFailure(failed);
      return { ...reply, message: `Ответ не проверен: ${failed.message}` };
    }
  }

  async function move(action: SandboxMove): Promise<TaskMoveTransitionResult> {
    const current = activeRun();
    const reply = { ordinal: current.number, advanced: false };
    try {
      const result = await backend.interact({
        ...action,
        family: current.family,
        stateText: current.state.stateText,
      });
      setFailure(null);
      updateRun(current.number, {
        state: taskState(result),
        closed: result.completed,
        evaluation: result.completed ? result.evaluation : current.evaluation,
      });
      return {
        ...reply,
        accepted: result.accepted,
        completed: result.completed,
        message: result.completed
          ? `${result.message || "Задача завершена."} Задача закрыта, /next откроет другой вариант.`
          : result.message || undefined,
      };
    } catch (caught) {
      const failed = failureOf(caught);
      setFailure(failed);
      return {
        ...reply,
        accepted: false,
        completed: false,
        message: `Ход не выполнен: ${failed.message}`,
      };
    }
  }

  async function anotherVariant(): Promise<TaskTransitionResult> {
    const opened = await generate(true);
    return opened
      ? { ordinal: opened.number, advanced: true }
      : {
          ordinal: run?.number ?? 1,
          advanced: false,
          message: "Другой вариант не создан: причина показана над задачей.",
        };
  }

  async function referenceAnswer(): Promise<DebugAnswerResponse> {
    const { family: key, state } = activeRun();
    if (state.referenceAnswer === null) {
      throw new Error("У этого семейства нет эталонного ответа.");
    }
    return {
      family: key,
      answer: state.referenceAnswer,
      commands: state.referenceCommands,
      details: state.details,
    };
  }

  const task: ParticipantTask | null = run && {
    id: `sandbox-${run.number}`,
    ordinal: run.number,
    family: run.family,
    difficulty: run.difficulty,
    status: run.closed ? "answered" : "active",
    publicState: run.state.publicState,
  };

  return {
    catalog,
    catalogError,
    reloadCatalog: () => void loadCatalog(),
    family,
    selectFamily,
    variant,
    setVariant,
    difficulty,
    setDifficulty,
    seed,
    setSeed,
    run,
    task,
    busy,
    notice,
    failure,
    generate: (anotherSeed: boolean) => void generate(anotherSeed),
    reloadModules: () => void reloadModules(),
    reloadAndGenerate: () => void reloadAndGenerate(),
    handlers: {
      onAnswer: answer,
      onSkip: anotherVariant,
      onNext: anotherVariant,
      onProbe: (probe: string) => move({ actionType: "probe", probe }),
      onHint: () => move({ actionType: "hint" }),
      onApplyOperation: (opId: string) =>
        move({ actionType: "apply_op", opId }),
      onUndo: () => move({ actionType: "undo" }),
      onReset: () => move({ actionType: "reset" }),
      onGetAnswer: referenceAnswer,
    },
  };
}

export type TaskSandboxState = ReturnType<typeof useTaskSandbox>;
