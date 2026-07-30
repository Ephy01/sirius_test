import { FormEvent, useMemo, useState } from "react";
import "./contest-builder.css";

export type EnvironmentKey = "chess_world" | "geometry_world";
export type TaskFamilyKey =
  | "chess960"
  | "dice_chess"
  | "penultima"
  | "geo_zendo"
  | "geo_transform"
  | "geo_probability"
  | "geo_graph";

export type TaskFamilyConfig = {
  key: TaskFamilyKey;
  enabled: boolean;
  weight: number;
  initialDifficulty: number;
  maxDifficulty: number;
};

export type ContestDraftInput = {
  title: string;
  durationMinutes: number;
  environmentKey: EnvironmentKey;
  taskConfig: {
    adaptationThreshold: number;
    families: TaskFamilyConfig[];
  };
};

export type ContestSummary = {
  id: string;
  title: string;
  status: "draft" | "published";
  durationMinutes: number;
};

export type ParticipantDraft = {
  externalRef: string;
  displayName: string;
};

export type GeneratedCodeRow = ParticipantDraft & {
  enrollmentId: string;
  code: string;
};

type ContestBuilderProps = {
  onCancel: () => void;
  onCreateContest: (input: ContestDraftInput) => Promise<ContestSummary>;
  onAddParticipants: (
    contestId: string,
    participants: ParticipantDraft[],
  ) => Promise<void>;
  onGenerateCodes: (contestId: string) => Promise<GeneratedCodeRow[]>;
  onPublish: (contestId: string) => Promise<ContestSummary>;
};

const FAMILY_LABELS: Record<
  TaskFamilyKey,
  { title: string; description: string }
> = {
  chess960: {
    title: "Chess960",
    description:
      "Проверка и исправление расстановок, логические ограничения и подсчёт вариантов.",
  },
  dice_chess: {
    title: "Dice & Chess",
    description:
      "Вероятностные события на доске и решения, зависящие от кубика фигур.",
  },
  penultima: {
    title: "Penultima",
    description:
      "Связная глава: неизвестная фигура, скрытое правило и последовательность маяков.",
  },
  geo_zendo: {
    title: "Геометрический Zendo",
    description:
      "Восстановление скрытого закона по положительным и отрицательным конфигурациям.",
  },
  geo_transform: {
    title: "Инварианты",
    description:
      "Преобразования фигур и графов: найти то, что сохраняется, или распознать действие.",
  },
  geo_probability: {
    title: "Комбинаторика",
    description:
      "Подсчёт конфигураций и вероятностей на сетях из точек, рёбер и областей.",
  },
  geo_graph: {
    title: "Графы и конструкции",
    description:
      "Построить или исправить сеть с заданными степенями, связностью и пересечениями.",
  },
};

const CHESS_FAMILIES: TaskFamilyConfig[] = [
  {
    key: "chess960",
    enabled: true,
    weight: 1,
    initialDifficulty: 1,
    maxDifficulty: 10,
  },
  {
    key: "dice_chess",
    enabled: true,
    weight: 1,
    initialDifficulty: 1,
    maxDifficulty: 10,
  },
  {
    key: "penultima",
    enabled: true,
    weight: 1,
    initialDifficulty: 1,
    maxDifficulty: 10,
  },
];

const GEOMETRY_FAMILIES: TaskFamilyConfig[] = [
  {
    key: "geo_zendo",
    enabled: true,
    weight: 30,
    initialDifficulty: 1,
    maxDifficulty: 10,
  },
  {
    key: "geo_transform",
    enabled: true,
    weight: 25,
    initialDifficulty: 1,
    maxDifficulty: 10,
  },
  {
    key: "geo_probability",
    enabled: true,
    weight: 25,
    initialDifficulty: 1,
    maxDifficulty: 10,
  },
  {
    key: "geo_graph",
    enabled: true,
    weight: 20,
    initialDifficulty: 1,
    maxDifficulty: 10,
  },
];

const WORLD_COPY: Record<
  EnvironmentKey,
  { title: string; description: string }
> = {
  chess_world: {
    title: "Шахматный мир",
    description:
      "Chess960, Dice & Chess и Penultima образуют одну адаптивную траекторию на шахматной доске.",
  },
  geometry_world: {
    title: "Геометрический мир",
    description:
      "Скрытые правила Zendo, преобразования, вероятность и конструкции используют общий язык точек, рёбер и фигур.",
  },
};

function cloneFamilies(families: readonly TaskFamilyConfig[]) {
  return families.map((family) => ({ ...family }));
}

function newParticipant(): ParticipantDraft {
  return { externalRef: "", displayName: "" };
}

function EnvironmentSelector({
  value,
  onChange,
}: {
  value: EnvironmentKey;
  onChange: (environment: EnvironmentKey) => void;
}) {
  return (
    <div className="world-selector" aria-label="Выбор среды контеста">
      {(Object.keys(WORLD_COPY) as EnvironmentKey[]).map((world) => (
        <button
          className={value === world ? "is-selected" : ""}
          type="button"
          aria-pressed={value === world}
          onClick={() => onChange(world)}
          key={world}
        >
          <strong>{WORLD_COPY[world].title}</strong>
          <span>{WORLD_COPY[world].description}</span>
        </button>
      ))}
    </div>
  );
}

export function ContestBuilder({
  onCancel,
  onCreateContest,
  onAddParticipants,
  onGenerateCodes,
  onPublish,
}: ContestBuilderProps) {
  const [step, setStep] = useState(1);
  const [title, setTitle] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [environmentKey, setEnvironmentKey] =
    useState<EnvironmentKey>("chess_world");
  const [families, setFamilies] =
    useState<TaskFamilyConfig[]>(() => cloneFamilies(CHESS_FAMILIES));
  const [participants, setParticipants] = useState<ParticipantDraft[]>([
    newParticipant(),
  ]);
  const [contest, setContest] = useState<ContestSummary | null>(null);
  const [codes, setCodes] = useState<GeneratedCodeRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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

  function updateFamily(
    key: TaskFamilyKey,
    patch: Partial<TaskFamilyConfig>,
  ) {
    setFamilies((current) =>
      current.map((family) =>
        family.key === key ? { ...family, ...patch } : family,
      ),
    );
  }

  function selectEnvironment(nextEnvironment: EnvironmentKey) {
    setEnvironmentKey(nextEnvironment);
    setFamilies(
      cloneFamilies(
        nextEnvironment === "geometry_world"
          ? GEOMETRY_FAMILIES
          : CHESS_FAMILIES,
      ),
    );
    setError("");
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

  async function createContest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim()) {
      setError("Введите название контеста.");
      return;
    }
    if (!activeFamilies.length) {
      setError("Выберите хотя бы одно семейство задач.");
      return;
    }
    if (
      activeFamilies.some(
        (family) =>
          family.initialDifficulty < 1 ||
          family.maxDifficulty > 10 ||
          family.initialDifficulty > family.maxDifficulty,
      )
    ) {
      setError(
        "Начальная сложность не может быть выше максимальной.",
      );
      return;
    }

    setBusy(true);
    setError("");
    try {
      const created = await onCreateContest({
        title: title.trim(),
        durationMinutes,
        environmentKey,
        taskConfig: {
          adaptationThreshold: 3,
          families,
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
    const blob = new Blob([`\uFEFF${csv}`], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${contest?.title || "contest"}-codes.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="builder-page">
      <header className="builder-heading">
        <div>
          <p className="eyebrow">Конструктор контеста</p>
          <h1>{contest?.title || "Новый контест"}</h1>
          <p>
            Выберите мир, настройте адаптивную траекторию и выпустите
            персональные коды.
          </p>
        </div>
        <button className="builder-close" type="button" onClick={onCancel}>
          Закрыть
        </button>
      </header>

      <ol className="builder-progress" aria-label="Этапы создания контеста">
        {["Параметры", "Среда", "Участники", "Коды"].map((label, index) => (
          <li
            className={step === index + 1 ? "is-active" : ""}
            key={label}
            aria-current={step === index + 1 ? "step" : undefined}
          >
            <i>{String(index + 1).padStart(2, "0")}</i>
            <span>{label}</span>
          </li>
        ))}
      </ol>

      {step <= 2 && (
        <form className="builder-card" onSubmit={createContest}>
          {step === 1 ? (
            <section aria-labelledby="builderBasicsTitle">
              <span className="builder-section-label">01 · параметры</span>
              <h2 id="builderBasicsTitle">Основная информация</h2>
              <div className="builder-fields">
                <label>
                  <span>Название контеста</span>
                  <input
                    value={title}
                    onChange={(event) => {
                      setTitle(event.target.value);
                      setError("");
                    }}
                    placeholder="Отбор на программу специалитета"
                    autoFocus
                  />
                </label>
                <label>
                  <span>Продолжительность, минут</span>
                  <input
                    type="number"
                    min={15}
                    max={240}
                    value={durationMinutes}
                    onChange={(event) =>
                      setDurationMinutes(Number(event.target.value))
                    }
                  />
                </label>
              </div>
              <div className="builder-world-choice">
                <span>Среда контеста</span>
                <p>
                  Выберите мир, из семейств которого будет строиться
                  индивидуальная траектория участника.
                </p>
                <EnvironmentSelector
                  value={environmentKey}
                  onChange={selectEnvironment}
                />
              </div>
            </section>
          ) : (
            <section aria-labelledby="builderWorldTitle">
              <span className="builder-section-label">02 · задачи среды</span>
              <h2 id="builderWorldTitle">{WORLD_COPY[environmentKey].title}</h2>
              <p className="builder-intro">
                Семейства образуют единую адаптивную траекторию. Система
                сначала познакомит участника с выбранными механиками, затем
                будет менять их порядок и сложность по истории прохождения.
              </p>
              <div className="family-list">
                {families.map((family) => {
                  const copy = FAMILY_LABELS[family.key];
                  return (
                    <article
                      className={family.enabled ? "is-enabled" : ""}
                      key={family.key}
                    >
                      <header>
                        <label>
                          <input
                            type="checkbox"
                            checked={family.enabled}
                            onChange={(event) =>
                              updateFamily(family.key, {
                                enabled: event.target.checked,
                              })
                            }
                          />
                          <span>{copy.title}</span>
                        </label>
                        <small>{family.key}</small>
                      </header>
                      <p>{copy.description}</p>
                      <div>
                        <label>
                          Вес
                          <input
                            type="number"
                            aria-label={`Вес семейства ${copy.title}`}
                            min={1}
                            max={100}
                            disabled={!family.enabled}
                            value={family.weight}
                            onChange={(event) =>
                              updateFamily(family.key, {
                                weight: Number(event.target.value),
                              })
                            }
                          />
                        </label>
                        <label>
                          Старт
                          <input
                            type="number"
                            aria-label={`Начальная сложность ${copy.title}`}
                            min={1}
                            max={10}
                            disabled={!family.enabled}
                            value={family.initialDifficulty}
                            onChange={(event) =>
                              updateFamily(family.key, {
                                initialDifficulty: Number(event.target.value),
                              })
                            }
                          />
                        </label>
                        <label>
                          Максимум
                          <input
                            type="number"
                            aria-label={`Максимальная сложность ${copy.title}`}
                            min={1}
                            max={10}
                            disabled={!family.enabled}
                            value={family.maxDifficulty}
                            onChange={(event) =>
                              updateFamily(family.key, {
                                maxDifficulty: Number(event.target.value),
                              })
                            }
                          />
                        </label>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          )}

          <p className="builder-error" role="alert">
            {error}
          </p>
          <footer className="builder-actions">
            {step === 2 && (
              <button
                className="secondary-action"
                type="button"
                onClick={() => setStep(1)}
              >
                Назад
              </button>
            )}
            {step === 1 ? (
              <button
                className="primary-action primary-action--fit"
                type="button"
                onClick={() => {
                  if (!title.trim()) {
                    setError("Введите название контеста.");
                    return;
                  }
                  if (
                    !Number.isFinite(durationMinutes) ||
                    durationMinutes < 15 ||
                    durationMinutes > 240
                  ) {
                    setError(
                      "Продолжительность должна быть от 15 до 240 минут.",
                    );
                    return;
                  }
                  setError("");
                  setStep(2);
                }}
              >
                Настроить среду
              </button>
            ) : (
              <button
                className="primary-action primary-action--fit"
                type="submit"
                disabled={busy}
              >
                {busy ? "Создаём…" : "Создать контест"}
              </button>
            )}
          </footer>
        </form>
      )}

      {step === 3 && (
        <section className="builder-card" aria-labelledby="participantsTitle">
          <span className="builder-section-label">03 · участники</span>
          <h2 id="participantsTitle">Кому выдать коды</h2>
          <p className="builder-intro">
            Номер заявки создаёт устойчивую связь участника с контестом. ФИО
            используется только в таблице организатора.
          </p>
          <div className="participant-table">
            <div className="participant-table__head" aria-hidden="true">
              <span>Номер заявки</span>
              <span>Участник</span>
              <span />
            </div>
            {participants.map((participant, index) => (
              <div className="participant-row" key={index}>
                <label>
                  <span>Номер заявки</span>
                  <input
                    aria-label={`Номер заявки участника ${index + 1}`}
                    value={participant.externalRef}
                    onChange={(event) =>
                      updateParticipant(index, "externalRef", event.target.value)
                    }
                    placeholder="18452"
                  />
                </label>
                <label>
                  <span>Участник</span>
                  <input
                    aria-label={`Имя участника ${index + 1}`}
                    value={participant.displayName}
                    onChange={(event) =>
                      updateParticipant(index, "displayName", event.target.value)
                    }
                    placeholder="Иванов Иван"
                  />
                </label>
                <button
                  type="button"
                  aria-label={`Удалить участника ${index + 1}`}
                  disabled={participants.length === 1}
                  onClick={() =>
                    setParticipants((current) =>
                      current.filter(
                        (_, participantIndex) => participantIndex !== index,
                      ),
                    )
                  }
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <button
            className="text-action"
            type="button"
            onClick={() =>
              setParticipants((current) => [...current, newParticipant()])
            }
          >
            + Добавить участника
          </button>
          <p className="builder-error" role="alert">
            {error}
          </p>
          <footer className="builder-actions">
            <button
              className="primary-action primary-action--fit"
              type="button"
              disabled={busy}
              onClick={saveParticipants}
            >
              {busy ? "Генерируем…" : "Сохранить и выпустить коды"}
            </button>
          </footer>
        </section>
      )}

      {step === 4 && (
        <section className="builder-card" aria-labelledby="codesTitle">
          <span className="builder-section-label">04 · коды</span>
          <h2 id="codesTitle">Коды созданы</h2>
          <p className="builder-intro">
            Скачайте таблицу сейчас. В открытом виде коды возвращаются только
            при выпуске.
          </p>
          <div className="codes-table">
            <div className="codes-table__head">
              <span>Заявка</span>
              <span>Участник</span>
              <span>Персональный код</span>
            </div>
            {codes.map((row) => (
              <div className="codes-row" key={row.enrollmentId}>
                <span>{row.externalRef}</span>
                <strong>{row.displayName}</strong>
                <code>{row.code}</code>
              </div>
            ))}
          </div>
          <p className="builder-error" role="alert">
            {error}
          </p>
          <footer className="builder-actions builder-actions--split">
            <button
              className="secondary-action"
              type="button"
              onClick={downloadCodes}
            >
              Скачать CSV
            </button>
            <button
              className="primary-action primary-action--fit"
              type="button"
              disabled={busy || contest?.status === "published"}
              onClick={publishContest}
            >
              {contest?.status === "published"
                ? "Контест опубликован"
                : busy
                  ? "Публикуем…"
                  : "Опубликовать контест"}
            </button>
          </footer>
        </section>
      )}
    </main>
  );
}
