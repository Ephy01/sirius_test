import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  saveDownloadedFile,
  type ContestSummary,
  type TaskFamilyCatalog,
} from "../../api";
import {
  defaultFamilyConfig,
  scriptedFamily,
  type TaskFamilyConfig,
} from "../families";
import {
  draftNumber,
  isIntegerInRange,
  newParticipant,
  type ContestBuilderProps,
  type GeneratedCodeRow,
  type NumericDraft,
  type ParticipantDraft,
  type TaskFamilyDraftConfig,
} from "./draft";

export function useContestBuilder({
  onLoadFamilies,
  onCreateContest,
  onAddParticipants,
  onGenerateCodes,
  onPublish,
}: ContestBuilderProps) {
  const [step, setStep] = useState(1);
  const [title, setTitle] = useState("");
  const [durationMinutes, setDurationMinutes] = useState<NumericDraft>(60);
  const [cohortSeed, setCohortSeed] = useState("");
  const [debugRevealAnswers, setDebugRevealAnswers] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiMode, setAiMode] = useState<"socratic" | "open">("socratic");
  const [aiTurnsPerAttempt, setAiTurnsPerAttempt] =
    useState<NumericDraft>(15);
  const [aiTurnsPerTask, setAiTurnsPerTask] = useState<NumericDraft>(5);
  const [catalog, setCatalog] = useState<TaskFamilyCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [scriptedEnabled, setScriptedEnabled] = useState(false);
  const [scriptedVariant, setScriptedVariant] = useState("");
  const [scriptedPosition, setScriptedPosition] = useState<NumericDraft>(1);
  const [families, setFamilies] = useState<TaskFamilyDraftConfig[]>([]);
  const [participants, setParticipants] = useState<ParticipantDraft[]>([
    newParticipant(),
  ]);
  const [contest, setContest] = useState<ContestSummary | null>(null);
  const [codes, setCodes] = useState<GeneratedCodeRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const scripted = useMemo(
    () => (catalog ? scriptedFamily(catalog) : undefined),
    [catalog],
  );
  const activeFamilies = useMemo(
    () => families.filter((family) => family.enabled),
    [families],
  );
  const validParticipants = useMemo(
    () =>
      participants.filter(
        (participant) =>
          participant.externalRef.trim() && participant.displayName.trim(),
      ),
    [participants],
  );

  async function loadCatalog(signal?: AbortSignal) {
    setCatalog(null);
    setCatalogError("");
    try {
      const loaded = await onLoadFamilies(signal);
      if (signal?.aborted) return;
      setFamilies(
        loaded.items
          .filter((family) => family.listed)
          .map((family) => ({ ...defaultFamilyConfig(family), card: family })),
      );
      setScriptedVariant(scriptedFamily(loaded)?.variants[0].key ?? "");
      setCatalog(loaded);
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
  }, []);

  function updateFamily(key: string, patch: Partial<TaskFamilyDraftConfig>) {
    setFamilies((current) =>
      current.map((family) =>
        family.key === key ? { ...family, ...patch } : family,
      ),
    );
  }

  function updateParticipant(
    index: number,
    field: keyof ParticipantDraft,
    value: string,
  ) {
    setParticipants((current) =>
      current.map((participant, participantIndex) =>
        participantIndex === index
          ? { ...participant, [field]: value }
          : participant,
      ),
    );
  }

  function openFamiliesStep() {
    if (!title.trim()) {
      setError("Введите название контеста.");
      return;
    }
    if (!isIntegerInRange(durationMinutes, 15, 240)) {
      setError("Продолжительность должна быть от 15 до 240 минут.");
      return;
    }

    setError("");
    setStep(2);
  }

  async function createContest() {
    if (!isIntegerInRange(durationMinutes, 15, 240)) {
      setError("Продолжительность должна быть от 15 до 240 минут.");
      return;
    }
    if (!activeFamilies.length) {
      setError("Выберите хотя бы одно семейство задач.");
      return;
    }
    if (
      activeFamilies.some(
        (family) => !isIntegerInRange(family.weight, 1, 100),
      )
    ) {
      setError(
        "Вес каждого выбранного семейства должен быть целым числом от 1 до 100.",
      );
      return;
    }
    const outOfBounds = activeFamilies.find(({ card, ...family }) =>
      [family.initialDifficulty, family.maxDifficulty].some(
        (value) =>
          !isIntegerInRange(value, card.minDifficulty, card.maxDifficulty),
      ),
    );
    if (outOfBounds) {
      const { minDifficulty, maxDifficulty } = outOfBounds.card;
      setError(
        `Сложность каждого выбранного семейства должна быть целым числом от ${minDifficulty} до ${maxDifficulty}.`,
      );
      return;
    }
    if (
      activeFamilies.some(
        (family) =>
          family.initialDifficulty !== "" &&
          family.maxDifficulty !== "" &&
          family.initialDifficulty > family.maxDifficulty,
      )
    ) {
      setError(
        "Начальная сложность не может быть выше максимальной.",
      );
      return;
    }
    if (
      aiEnabled &&
      (!isIntegerInRange(aiTurnsPerAttempt, 1, 200) ||
        !isIntegerInRange(aiTurnsPerTask, 1, 50))
    ) {
      setError(
        "Лимиты ИИ должны быть заполнены целыми числами в допустимых пределах.",
      );
      return;
    }
    if (scriptedEnabled && !isIntegerInRange(scriptedPosition, 1, 100)) {
      setError(
        "Позиция классической задачи должна быть целым числом от 1 до 100.",
      );
      return;
    }

    const normalizedFamilies: TaskFamilyConfig[] = families.map(
      ({ card, ...family }) => ({
        ...family,
        weight: draftNumber(family.weight, 1),
        initialDifficulty: draftNumber(
          family.initialDifficulty,
          card.minDifficulty,
        ),
        maxDifficulty: draftNumber(family.maxDifficulty, card.maxDifficulty),
      }),
    );

    setBusy(true);
    setError("");
    try {
      const created = await onCreateContest({
        title: title.trim(),
        durationMinutes,
        taskConfig: {
          adaptationThreshold: 3,
          cohortSeed: cohortSeed.trim() || undefined,
          debugRevealAnswers,
          ai: {
            enabled: aiEnabled,
            mode: aiMode,
            maxTurnsPerAttempt: draftNumber(aiTurnsPerAttempt, 15),
            maxTurnsPerTask: draftNumber(aiTurnsPerTask, 5),
          },
          families: normalizedFamilies,
          scriptedTasks:
            scriptedEnabled && scripted
              ? [
                  {
                    family: scripted.key,
                    subKind: scriptedVariant,
                    position: draftNumber(scriptedPosition, 1),
                  },
                ]
              : [],
        },
      });
      setContest(created);
      setStep(3);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Не удалось создать контест.",
      );
    } finally {
      setBusy(false);
    }
  }

  function submitCurrentStep(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (step === 1) {
      openFamiliesStep();
      return;
    }
    void createContest();
  }

  async function saveParticipants() {
    if (!contest) return;
    if (!validParticipants.length) {
      setError("Добавьте хотя бы одного участника.");
      return;
    }
    const participantRefs = validParticipants.map((participant) =>
      participant.externalRef.trim(),
    );
    if (new Set(participantRefs).size !== participantRefs.length) {
      setError("Номера заявок участников не должны повторяться.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      await onAddParticipants(contest.id, validParticipants);
      const generatedCodes = await onGenerateCodes(contest.id);
      setCodes(generatedCodes);
      setStep(4);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Не удалось сохранить участников.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function publishContest() {
    if (!contest) return;
    setBusy(true);
    setError("");
    try {
      const published = await onPublish(contest.id);
      setContest(published);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Не удалось опубликовать контест.",
      );
    } finally {
      setBusy(false);
    }
  }

  function downloadCodes() {
    const rows = [
      ["Номер заявки", "Участник", "Код"],
      ...codes.map((row) => [row.externalRef, row.displayName, row.code]),
    ];
    const csv = rows
      .map((row) =>
        row
          .map((cell) => `"${String(cell).replaceAll('"', '""')}"`)
          .join(";"),
      )
      .join("\n");
    saveDownloadedFile({
      blob: new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }),
      filename: `${contest?.title || "contest"}-codes.csv`,
    });
  }

  return {
    step,
    setStep,
    title,
    setTitle,
    durationMinutes,
    setDurationMinutes,
    cohortSeed,
    setCohortSeed,
    debugRevealAnswers,
    setDebugRevealAnswers,
    aiEnabled,
    setAiEnabled,
    aiMode,
    setAiMode,
    aiTurnsPerAttempt,
    setAiTurnsPerAttempt,
    aiTurnsPerTask,
    setAiTurnsPerTask,
    catalog,
    catalogError,
    reloadCatalog: () => void loadCatalog(),
    scripted,
    scriptedEnabled,
    setScriptedEnabled,
    scriptedVariant,
    setScriptedVariant,
    scriptedPosition,
    setScriptedPosition,
    families,
    updateFamily,
    participants,
    setParticipants,
    updateParticipant,
    contest,
    codes,
    busy,
    error,
    setError,
    submitCurrentStep,
    saveParticipants,
    publishContest,
    downloadCodes,
  };
}

export type ContestBuilderState = ReturnType<typeof useContestBuilder>;
