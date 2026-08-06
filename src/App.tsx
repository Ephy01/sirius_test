import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ApiError,
  api,
  type ContestSummary as ApiContestSummary,
  type ParticipantTask as ApiParticipantTask,
  type TaskInteractionResponse as ApiTaskInteractionResponse,
} from "./api";
import {
  clearAccessSession,
  loadAccessSession,
  normalizeAccessCode,
  redeemAccessCode,
  saveAccessSession,
  updateAccessSession,
  type AccessSession,
} from "./auth";
import {
  AppHeader,
  ArrowIcon,
  Brand,
  PlusIcon,
} from "./components";
import {
  ContestBuilder,
  type ContestDraftInput,
  type ContestSummary as BuilderContestSummary,
  type GeneratedCodeRow,
  type ParticipantDraft,
} from "./organizer/ContestBuilder";
import { ContestAccessPanel } from "./organizer/ContestAccessPanel";
import {
  ParticipantWorkspace,
  type ParticipantTask as WorkspaceParticipantTask,
  type ParticipantTelemetryEvent,
  type TaskMoveTransitionResult,
  type TaskTransitionResult,
} from "./participant";

type Authenticate = (code: string) => Promise<void>;

export function App() {
  const [session, setSession] = useState<AccessSession | null>(() => loadAccessSession());
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const handleHistoryChange = () => setPath(window.location.pathname);
    window.addEventListener("popstate", handleHistoryChange);
    return () => window.removeEventListener("popstate", handleHistoryChange);
  }, []);

  const expectedPath = session
    ? session.role === "organizer"
      ? "/organizer"
      : "/contest"
    : "/";

  useEffect(() => {
    if (path === expectedPath) return;
    window.history.replaceState(null, "", expectedPath);
    setPath(expectedPath);
  }, [expectedPath, path]);

  useEffect(() => {
    if (!session || session.role !== "participant") return;

    const controller = new AbortController();
    api
      .getParticipantContext({
        token: session.token,
        signal: controller.signal,
      })
      .then((context) => {
        const refreshed: AccessSession = {
          ...session,
          contest: context.contest,
          participant: context.participant,
          enrollment: context.enrollment,
          attempt: context.attempt,
        };
        saveAccessSession(refreshed);
        setSession(refreshed);
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        if (caught instanceof ApiError && caught.status === 401) {
          clearAccessSession();
          setSession(null);
        }
      });

    return () => controller.abort();
  }, [session?.role, session?.token]);

  async function authenticate(code: string) {
    const redeemedSession = await redeemAccessCode(code);
    let nextSession = redeemedSession;

    if (redeemedSession.role === "participant") {
      try {
        const context = await api.getParticipantContext({
          token: redeemedSession.token,
        });
        nextSession = {
          ...redeemedSession,
          contest: context.contest,
          participant: context.participant,
          enrollment: context.enrollment,
          attempt: context.attempt,
        };
        saveAccessSession(nextSession);
      } catch (caught) {
        clearAccessSession();
        throw caught;
      }
    }

    setSession(nextSession);
    const destination =
      nextSession.role === "organizer" ? "/organizer" : "/contest";
    window.history.pushState(null, "", destination);
    setPath(destination);
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }

  function logout() {
    clearAccessSession();
    setSession(null);
    window.history.pushState(null, "", "/");
    setPath("/");
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }

  if (!session) return <AccessScreen onAuthenticate={authenticate} />;
  if (session.role === "organizer") {
    return <OrganizerDashboard session={session} onLogout={logout} />;
  }
  return (
    <ParticipantWaitingScreen
      session={session}
      onSessionChange={setSession}
      onLogout={logout}
    />
  );
}

function AccessScreen({ onAuthenticate }: { onAuthenticate: Authenticate }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function submitAccess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = normalizeAccessCode(code);
    if (!normalized) {
      setError("Введите код доступа.");
      inputRef.current?.focus();
      return;
    }

    setBusy(true);
    setError("");

    try {
      await onAuthenticate(normalized);
    } catch (caught) {
      setBusy(false);
      setError(
        caught instanceof ApiError || caught instanceof Error
          ? caught.message
          : "Не удалось проверить код. Повторите попытку.",
      );
      inputRef.current?.focus();
    }
  }

  return (
    <div className="access-page">
      <header className="public-header">
        <Brand />
        <div className="public-header__meta">
          <span>ver. 0.0.1 under development</span>
        </div>
      </header>

      <main className="access-layout">
        <section className="gate-panel" aria-labelledby="gateTitle">
          <div className="gate-panel__content">
            <h2 id="gateTitle">Введите код доступа</h2>

            <form className="access-form" onSubmit={submitAccess} noValidate>
              <div className={`access-input ${error ? "access-input--error" : ""}`}>
                <span aria-hidden="true">SG</span>
                <input
                  ref={inputRef}
                  id="accessCode"
                  name="accessCode"
                  aria-label="Персональный код"
                  value={code}
                  onChange={(event) => {
                    setCode(event.target.value.toUpperCase());
                    setError("");
                  }}
                  autoComplete="one-time-code"
                  autoCapitalize="characters"
                  spellCheck={false}
                  maxLength={24}
                  placeholder="XXXX-XXXX"
                  aria-describedby="accessHint accessError"
                  aria-invalid={Boolean(error)}
                />
              </div>
              <p className="field-hint" id="accessHint">
                Дефисы и регистр не имеют значения
              </p>
              <p className="field-error" id="accessError" role="alert">
                {error}
              </p>
              <button className="primary-action" type="submit" disabled={busy || !code.trim()}>
                <span>{busy ? "Проверяем код…" : "Продолжить"}</span>
                <ArrowIcon />
              </button>
            </form>
          </div>
        </section>
      </main>
    </div>
  );
}

function OrganizerDashboard({
  session,
  onLogout,
}: {
  session: AccessSession;
  onLogout: () => void;
}) {
  const [builderOpen, setBuilderOpen] = useState(false);
  const [managedContest, setManagedContest] =
    useState<ApiContestSummary | null>(null);
  const [contests, setContests] = useState<ApiContestSummary[]>([]);
  const [notice, setNotice] = useState("");
  const [contestPendingDeletion, setContestPendingDeletion] =
    useState<ApiContestSummary | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  async function refreshContests() {
    setNotice("");
    try {
      const items = await api.listContests({ token: session.token });
      setContests(items);
    } catch (caught) {
      setNotice(
        caught instanceof Error
          ? caught.message
          : "Не удалось загрузить контесты.",
      );
    }
  }

  useEffect(() => {
    void refreshContests();
  }, [session.token]);

  useEffect(() => {
    if (!contestPendingDeletion) return;

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !deleteBusy) {
        setContestPendingDeletion(null);
        setDeleteError("");
      }
    }

    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [contestPendingDeletion, deleteBusy]);

  async function createContest(
    input: ContestDraftInput,
  ): Promise<BuilderContestSummary> {
    const created = await api.createContest(
      {
        title: input.title,
        durationMinutes: input.durationMinutes,
        environmentKey: input.environmentKey,
        taskConfig: {
          adaptation_threshold: input.taskConfig.adaptationThreshold,
          cohort_seed: input.taskConfig.cohortSeed,
          debug_reveal_answers: input.taskConfig.debugRevealAnswers === true,
          ...(input.taskConfig.ai
            ? {
                ai: {
                  enabled: input.taskConfig.ai.enabled,
                  mode: input.taskConfig.ai.mode,
                  max_turns_per_attempt:
                    input.taskConfig.ai.maxTurnsPerAttempt,
                  max_turns_per_task: input.taskConfig.ai.maxTurnsPerTask,
                },
              }
            : {}),
          trajectory: {
            mode: "adaptive",
            director_version: "director-v2",
            start_family:
              input.taskConfig.families.find((family) => family.enabled)?.key ??
              "geo_zendo",
          },
          families: input.taskConfig.families.map((family) => ({
            family: family.key,
            skin: family.skin,
            enabled: family.enabled,
            weight: family.weight,
            initial_difficulty: family.initialDifficulty,
            max_difficulty: family.maxDifficulty,
            locked_chapter: family.lockedChapter,
            sub_kinds: family.subKinds,
          })),
          ...(input.taskConfig.scriptedTasks.length > 0
            ? {
                scripted_tasks: input.taskConfig.scriptedTasks.map((task) => ({
                  family: task.family,
                  sub_kind: task.subKind,
                  position: task.position,
                })),
              }
            : {}),
        },
      },
      { token: session.token },
    );
    return {
      id: created.id,
      title: created.title,
      durationMinutes: created.durationMinutes,
      status: created.status === "published" ? "published" : "draft",
    };
  }

  async function addParticipants(
    contestId: string,
    participants: ParticipantDraft[],
  ) {
    await api.addEnrollments(
      contestId,
      {
        participants: participants.map((participant) => ({
          externalRef: participant.externalRef,
          displayName: participant.displayName,
        })),
      },
      { token: session.token },
    );
  }

  async function generateCodes(contestId: string): Promise<GeneratedCodeRow[]> {
    const response = await api.generateCodes(
      contestId,
      {},
      { token: session.token },
    );
    return response.codes.map((item) => ({
      enrollmentId: item.enrollmentId,
      externalRef: item.participantExternalRef ?? "—",
      displayName: item.participantName,
      code: item.code,
    }));
  }

  async function publishContest(
    contestId: string,
  ): Promise<BuilderContestSummary> {
    const published = await api.publishContest(contestId, {
      token: session.token,
    });
    await refreshContests();
    return {
      id: published.id,
      title: published.title,
      durationMinutes: published.durationMinutes,
      status: "published",
    };
  }

  async function deleteContest() {
    const contest = contestPendingDeletion;
    if (!contest) return;

    setDeleteBusy(true);
    setDeleteError("");
    try {
      await api.deleteContest(contest.id, { token: session.token });
      setContests((current) =>
        current.filter((item) => item.id !== contest.id),
      );
      setContestPendingDeletion(null);
      setNotice(`Контест «${contest.title}» удалён.`);
    } catch (caught) {
      setDeleteError(
        caught instanceof Error
          ? caught.message
          : "Не удалось удалить контест.",
      );
    } finally {
      setDeleteBusy(false);
    }
  }

  if (builderOpen) {
    return (
      <div className="dashboard-page">
        <AppHeader
          role="Организатор"
          onLogout={onLogout}
          meta={<span className="workspace-label">Конструктор контеста</span>}
        />
        <ContestBuilder
          onCancel={() => {
            setBuilderOpen(false);
            void refreshContests();
          }}
          onCreateContest={createContest}
          onAddParticipants={addParticipants}
          onGenerateCodes={generateCodes}
          onPublish={publishContest}
        />
      </div>
    );
  }

  if (managedContest) {
    return (
      <div className="dashboard-page">
        <AppHeader
          role="Организатор"
          onLogout={onLogout}
          meta={<span className="workspace-label">Доступы участников</span>}
        />
        <ContestAccessPanel
          contest={managedContest}
          token={session.token}
          onBack={() => {
            setManagedContest(null);
            void refreshContests();
          }}
        />
      </div>
    );
  }

  return (
    <div className="dashboard-page">
      <AppHeader
        role="Организатор"
        onLogout={onLogout}
        meta={<span className="workspace-label">Панель управления</span>}
      />

      <div className="dashboard-layout">
        <aside className="dashboard-sidebar">
          <nav aria-label="Разделы панели организатора">
            <button className="side-nav-item side-nav-item--active" type="button">
              <span className="side-nav-icon">◫</span>
              Контесты
              <small>{contests.length}</small>
            </button>
            <button
              className="side-nav-create"
              type="button"
              aria-label="Создать контест"
              title="Создать контест"
              onClick={() => setBuilderOpen(true)}
            >
              <PlusIcon />
            </button>
            <button className="side-nav-item" type="button" disabled>
              <span className="side-nav-icon">◎</span>
              Участники
            </button>
            <button className="side-nav-item" type="button" disabled>
              <span className="side-nav-icon">⌁</span>
              Хронология
            </button>
          </nav>

        </aside>

        <main className="dashboard-main">
          <section className="contest-list" aria-label="Созданные контесты">
            {contests.map((contest) => (
              <article key={contest.id}>
                <div>
                  <span
                    className={`contest-status contest-status--${contest.status}`}
                  >
                    {contest.status === "published"
                      ? "Опубликован"
                      : "Черновик"}
                  </span>
                  <span className="eyebrow">
                    {contest.environmentKey === "mixed"
                      ? "Смешанный контент"
                      : contest.environmentKey === "geometry_world"
                        ? "Геометрический мир"
                        : "Шахматный мир"}
                  </span>
                </div>
                <h2>{contest.title}</h2>
                <p>{contest.durationMinutes} минут · персональные коды</p>
                <div className="contest-list__actions">
                  <button
                    className="contest-list__manage"
                    type="button"
                    onClick={() => setManagedContest(contest)}
                  >
                    Управлять доступом
                    <ArrowIcon />
                  </button>
                  <button
                    className="contest-list__delete"
                    type="button"
                    onClick={() => {
                      setDeleteError("");
                      setContestPendingDeletion(contest);
                    }}
                  >
                    Удалить контест
                  </button>
                </div>
              </article>
            ))}
            {notice && (
              <p className="dashboard-notice" role="status">
                {notice}
              </p>
            )}
          </section>
        </main>
      </div>

      {contestPendingDeletion && (
        <div
          className="confirm-dialog-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !deleteBusy) {
              setContestPendingDeletion(null);
              setDeleteError("");
            }
          }}
        >
          <section
            className="confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="deleteContestTitle"
            aria-describedby="deleteContestDescription"
          >
            <span className="confirm-dialog__label">Удаление контеста</span>
            <h2 id="deleteContestTitle">
              Удалить «{contestPendingDeletion.title}»?
            </h2>
            <p id="deleteContestDescription">
              Будут безвозвратно удалены персональные коды, попытки, задачи и
              вся хронология этого контеста. Карточки участников сохранятся.
            </p>
            <p className="confirm-dialog__error" role="alert">
              {deleteError}
            </p>
            <footer>
              <button
                className="confirm-dialog__cancel"
                type="button"
                disabled={deleteBusy}
                autoFocus
                onClick={() => {
                  setContestPendingDeletion(null);
                  setDeleteError("");
                }}
              >
                Отмена
              </button>
              <button
                className="confirm-dialog__delete"
                type="button"
                disabled={deleteBusy}
                onClick={() => void deleteContest()}
              >
                {deleteBusy ? "Удаляем…" : "Удалить"}
              </button>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}

const SIRIUS_DOTS: readonly [number, number, number][] = [
  [-97.6, -21.4, 3.6], [-94.6, 2.2, 4.1], [-95.1, 26.7, 3.9], [-70.1, -61.9, 3.3], [-70.6, -35.7, 5.8],
  [-71.8, -11.2, 6.9], [-70.2, 8.6, 7.4], [-72.1, 38.8, 6.4], [-73.7, 60.8, 3.9], [-48.1, -70.2, 3.3],
  [-51.1, -50.6, 5.6], [-48.4, -25.9, 7.6], [-50.3, 1.6, 9.3], [-45.4, 26.3, 9.0], [-48.2, 51.4, 6.8],
  [-47.5, 71.2, 4.0], [-22.0, -80.6, 2.9], [-25.7, -62.0, 5.0], [-20.9, -35.6, 7.0], [-27.4, -10.8, 9.5],
  [-21.6, 11.7, 10.6], [-24.9, 35.6, 8.6], [-27.0, 63.1, 6.1], [-23.8, 84.7, 3.5], [-2.6, -98.8, 2.2],
  [-2.3, -71.2, 4.2], [-2.5, -44.6, 5.8], [-2.9, -21.3, 7.4], [-2.3, -3.3, 8.4], [3.2, 26.3, 7.6],
  [-3.4, 46.3, 6.8], [-3.0, 70.6, 5.2], [2.6, 92.5, 2.9], [22.3, -83.3, 2.4], [24.8, -61.1, 4.0],
  [22.3, -38.9, 5.0], [23.7, -14.0, 5.9], [20.7, 10.4, 6.5], [22.0, 37.5, 5.8], [24.8, 62.8, 4.6],
  [26.1, 86.0, 2.7], [47.3, -70.0, 2.3], [48.8, -49.0, 3.5], [44.7, -27.1, 4.3], [46.9, -2.7, 4.6],
  [45.8, 21.8, 4.6], [45.9, 50.0, 4.0], [44.5, 71.3, 2.6], [69.5, -62.4, 2.0], [69.8, -35.3, 3.0],
  [75.5, -12.4, 3.1], [75.0, 14.9, 3.2], [71.6, 36.0, 3.2], [70.5, 61.7, 2.1], [95.1, -25.9, 1.8],
  [97.9, -0.2, 1.9], [92.9, 25.7, 1.9],
];

function SiriusDotsMark() {
  return (
    <svg
      className="sirius-dots"
      viewBox="-110 -110 220 220"
      role="img"
      aria-hidden="true"
    >
      {SIRIUS_DOTS.map(([x, y, radius], index) => (
        <circle cx={x} cy={y} r={radius} key={index} />
      ))}
    </svg>
  );
}

function ParticipantWaitingScreen({
  session,
  onSessionChange,
  onLogout,
}: {
  session: AccessSession;
  onSessionChange: (session: AccessSession) => void;
  onLogout: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const attempt = session.attempt;
  const worldName =
    session.contest?.environmentKey === "mixed"
      ? "Смешанный контент"
      : session.contest?.environmentKey === "geometry_world"
        ? "Геометрический мир"
        : "Шахматный мир";

  if (attempt) {
    return (
      <ParticipantContestScreen
        session={session}
        onLogout={onLogout}
      />
    );
  }

  async function startAttempt() {
    setBusy(true);
    setError("");
    try {
      const response = await api.startAttempt(
        {},
        { token: session.token },
      );
      const next =
        updateAccessSession({ attempt: response.attempt }) ?? {
          ...session,
          attempt: response.attempt,
        };
      onSessionChange(next);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Не удалось запустить попытку.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="participant-page">
      <AppHeader
        role="Участник"
        onLogout={onLogout}
        meta={<span className="workspace-label">Контест</span>}
      />

      <main className="participant-waiting">
        <div className="participant-waiting__status" aria-hidden="true">
          <SiriusDotsMark />
        </div>
        <p className="eyebrow">
          Контест готов
        </p>
        <h1>{session.contest?.title ?? worldName}</h1>
        <p>
          После старта у вас будет {session.contest?.durationMinutes ?? 60} минут.
          Таймер запускается только по кнопке.
        </p>

        <dl className="participant-context">
          <div>
            <dt>Участник</dt>
            <dd>{session.participant?.displayName ?? "Персональный код"}</dd>
          </div>
          <div>
            <dt>Среда</dt>
            <dd>{worldName}</dd>
          </div>
          <div>
            <dt>Длительность</dt>
            <dd>{session.contest?.durationMinutes ?? 60} минут</dd>
          </div>
        </dl>

        <section className="participant-rules" aria-label="Общие правила">
          <h2>Общие правила</h2>
          <ul>
            <li>
              Задачи открываются по одной. Управление — команды в чате;{" "}
              <code>/help</code> покажет их список в любой момент.
            </li>
            <li>
              Ответ отправляется командой <code>/answer</code>. Задачу можно
              пропустить: <code>/skip</code> — но вернуться к ней уже нельзя.
            </li>
            <li>
              В задачах со скрытым правилом есть ограниченный запас проб (
              <code>/test</code>) — проверяйте гипотезы до ответа, пробы
              бесплатны.
            </li>
            <li>
              <code>/hint</code> — платная подсказка: итоговый балл за задачу
              умножается на 0.7.
            </li>
            <li>
              Обычное сообщение без «/» уходит ИИ-ассистенту. Ассистент
              помогает рассуждать, но не знает ответов; число обращений
              ограничено.
            </li>
            <li>Таймер запускается кнопкой ниже и не останавливается.</li>
          </ul>
        </section>

        <button
          className="primary-action participant-start"
          type="button"
          disabled={busy}
          onClick={startAttempt}
        >
          <span>{busy ? "Запускаем…" : "Начать попытку"}</span>
          <ArrowIcon />
        </button>
        <p className="participant-error" role="alert">
          {error}
        </p>
      </main>
    </div>
  );
}

function ParticipantContestScreen({
  session,
  onLogout,
}: {
  session: AccessSession;
  onLogout: () => void;
}) {
  const [task, setTask] = useState<ApiParticipantTask | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");

    api
      .getCurrentTask({
        token: session.token,
        signal: controller.signal,
      })
      .then((response) => setTask(response.task))
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setError(
          caught instanceof Error
            ? caught.message
            : "Не удалось загрузить задачу.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [session.attempt?.id, session.token]);

  async function answerTask(answer: string): Promise<TaskTransitionResult> {
    if (!task || task.status !== "active") {
      throw new Error("Текущая задача уже закрыта.");
    }
    return runTaskAction(async () => {
      const response = await api.answerTask(task.id, answer, {
        token: session.token,
      });
      setTask(response.task);
      if (response.task.status === "active") {
        return {
          ordinal: response.task.ordinal,
          advanced: false,
          message: response.message,
        };
      }
      try {
        const next = await api.getNextTask({ token: session.token });
        setTask(next.task);
        return { ordinal: next.task.ordinal, advanced: true };
      } catch {
        return {
          ordinal: response.task.ordinal,
          advanced: false,
          message:
            "Ответ зафиксирован, но следующая задача не открылась. Используйте /next.",
        };
      }
    });
  }

  async function resolveCompletedOperation(
    response: ApiTaskInteractionResponse,
  ): Promise<TaskMoveTransitionResult> {
    setTask(response.task);
    if (!response.completed) {
      return {
        ordinal: response.task.ordinal,
        advanced: false,
        accepted: response.accepted,
        completed: response.completed,
        message: response.message,
      };
    }
    try {
      const next = await api.getNextTask({ token: session.token });
      setTask(next.task);
      return {
        ordinal: next.task.ordinal,
        advanced: true,
        accepted: response.accepted,
        completed: true,
        message: response.message,
      };
    } catch {
      return {
        ordinal: response.task.ordinal,
        advanced: false,
        accepted: response.accepted,
        completed: true,
        message:
          `${response.message} Следующая задача не открылась. ` +
          "Используйте /next.",
      };
    }
  }

  async function probeTask(
    probe: string,
    clientActionId: string,
  ): Promise<TaskMoveTransitionResult> {
    if (!task || task.status !== "active") {
      throw new Error("Текущая задача уже закрыта.");
    }
    return runTaskAction(async () => {
      const response = await api.interactWithTask(
        task.id,
        {
          actionType: "probe",
          probe,
          clientActionId,
        },
        { token: session.token },
      );
      setTask(response.task);
      return {
        ordinal: response.task.ordinal,
        advanced: false,
        accepted: response.accepted,
        completed: response.completed,
        message: response.message,
      };
    });
  }

  async function getAnswerTask(): Promise<{
    answer: string;
    commands: string[];
    details: string[];
  }> {
    if (!task || task.status !== "active") {
      throw new Error("Текущая задача уже закрыта.");
    }
    return api.getParticipantDebugAnswer(task.id, { token: session.token });
  }

  async function sendAiMessage(message: string, clientActionId: string) {
    if (!task || task.status !== "active") {
      throw new Error("Текущая задача уже закрыта.");
    }
    return api.sendAiTurn(
      task.id,
      { clientActionId, message },
      { token: session.token },
    );
  }

  async function loadAiHistory() {
    if (!task) {
      throw new Error("Задача недоступна.");
    }
    return api.getAiTurns(task.id, { token: session.token });
  }

  async function hintTask(
    clientActionId: string,
  ): Promise<TaskMoveTransitionResult> {
    if (!task || task.status !== "active") {
      throw new Error("Текущая задача уже закрыта.");
    }
    return runTaskAction(async () => {
      const response = await api.interactWithTask(
        task.id,
        {
          actionType: "hint",
          clientActionId,
        },
        { token: session.token },
      );
      setTask(response.task);
      return {
        ordinal: response.task.ordinal,
        advanced: false,
        accepted: response.accepted,
        completed: response.completed,
        message: response.message,
      };
    });
  }

  async function applyOperationTask(
    opId: string,
    clientActionId: string,
  ): Promise<TaskMoveTransitionResult> {
    if (!task || task.status !== "active") {
      throw new Error("Текущая машина уже закрыта.");
    }
    return runTaskAction(async () => {
      const response = await api.interactWithTask(
        task.id,
        {
          actionType: "apply_op",
          opId,
          clientActionId,
        },
        { token: session.token },
      );
      return resolveCompletedOperation(response);
    });
  }

  async function undoMachineTask(
    clientActionId: string,
  ): Promise<TaskMoveTransitionResult> {
    if (!task || task.status !== "active") {
      throw new Error("Текущая машина уже закрыта.");
    }
    return runTaskAction(async () => {
      const response = await api.interactWithTask(
        task.id,
        {
          actionType: "undo",
          clientActionId,
        },
        { token: session.token },
      );
      setTask(response.task);
      return {
        ordinal: response.task.ordinal,
        advanced: false,
        accepted: response.accepted,
        completed: response.completed,
        message: response.message,
      };
    });
  }

  async function skipTask(): Promise<TaskTransitionResult> {
    if (!task || task.status !== "active") {
      throw new Error("Текущая задача уже закрыта.");
    }
    return runTaskAction(async () => {
      const response = await api.skipTask(task.id, {
        token: session.token,
      });
      setTask(response.task);
      try {
        const next = await api.getNextTask({ token: session.token });
        setTask(next.task);
        return { ordinal: next.task.ordinal, advanced: true };
      } catch {
        return {
          ordinal: response.task.ordinal,
          advanced: false,
          message:
            "Пропуск зафиксирован, но следующая задача не открылась. Используйте /next.",
        };
      }
    });
  }

  async function nextTask(): Promise<TaskTransitionResult> {
    if (!task || task.status === "active") {
      throw new Error("Сначала завершите текущую задачу.");
    }
    return runTaskAction(async () => {
      const response = await api.getNextTask({ token: session.token });
      setTask(response.task);
      return { ordinal: response.task.ordinal, advanced: true };
    });
  }

  async function runTaskAction<T>(action: () => Promise<T>): Promise<T> {
    setBusy(true);
    setError("");
    try {
      return await action();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Не удалось выполнить команду.",
      );
      throw caught;
    } finally {
      setBusy(false);
    }
  }

  async function recordTelemetry(
    event: ParticipantTelemetryEvent,
  ): Promise<void> {
    await api.recordParticipantTelemetry(event, {
      token: session.token,
    });
  }

  const workspaceTask: WorkspaceParticipantTask | null = task
    ? {
        id: task.id,
        ordinal: task.ordinal,
        family: task.family,
        kind: task.publicState.kind,
        difficulty: task.difficulty,
        status: task.status,
        prompt: task.publicState.prompt,
        dice:
          task.publicState.kind === "dice_chess_probability"
            ? (task.publicState.dice as unknown as WorkspaceParticipantTask["dice"])
            : task.publicState.kind === "dice_chess_position_probability" ||
                task.publicState.kind === "dice_chess_board_inventory_probability"
              ? ([task.publicState.die] as unknown as WorkspaceParticipantTask["dice"])
              : undefined,
        sampleSpaceSize:
          task.publicState.kind === "dice_chess_probability" ||
          task.publicState.kind === "dice_chess_board_inventory_probability" ||
          task.publicState.kind === "dice_chess_position_probability"
            ? task.publicState.sampleSpaceSize
            : undefined,
        eventDescription:
          task.publicState.kind === "dice_chess_probability" ||
          task.publicState.kind === "dice_chess_board_inventory_probability" ||
          task.publicState.kind === "dice_chess_position_probability"
            ? task.publicState.eventDescription
            : undefined,
        board:
          task.publicState.kind === "dice_chess_board_inventory_probability" ||
          task.publicState.kind === "dice_chess_position_probability"
            ? (task.publicState.board as WorkspaceParticipantTask["board"])
            : undefined,
        sideToMove:
          task.publicState.kind === "dice_chess_position_probability"
            ? task.publicState.sideToMove
            : undefined,
        geometryScene:
          task.publicState.kind === "geometry_atlas" ||
          task.publicState.kind === "point_zendo"
            ? task.publicState.scene
            : undefined,
        geometryContent:
          task.publicState.kind === "geometry_atlas" ||
          task.publicState.kind === "token_zendo" ||
          task.publicState.kind === "point_zendo" ||
          task.publicState.kind === "grid_zendo"
            ? task.publicState.content
            : undefined,
        geometryInteraction:
          task.publicState.kind === "geometry_atlas" ||
          task.publicState.kind === "token_zendo" ||
          task.publicState.kind === "point_zendo" ||
          task.publicState.kind === "grid_zendo"
            ? task.publicState.interaction
            : undefined,
        tokenCards:
          task.publicState.kind === "token_zendo"
            ? task.publicState.cards
            : undefined,
        gridCards:
          task.publicState.kind === "grid_zendo"
            ? task.publicState.cards
            : undefined,
        machinePanel:
          task.publicState.kind === "machine_panel"
            ? task.publicState
            : undefined,
        wiring:
          task.publicState.kind === "hidden_wiring"
            ? task.publicState
            : undefined,
        foldPunch:
          task.publicState.kind === "fold_punch"
            ? task.publicState
            : undefined,
        leaperBoard:
          task.publicState.kind === "chess"
            ? task.publicState
            : undefined,
        classicMath:
          task.publicState.kind === "classic_math_free_response"
            ? task.publicState
            : undefined,
        worldPhase: task.publicState.worldContext?.phase,
        responseHint: task.publicState.responseHint,
      }
    : null;

  return (
    <div className="participant-page">
      <AppHeader
        role="Участник"
        onLogout={onLogout}
        meta={<span className="workspace-label">Контест идёт</span>}
      />

      {workspaceTask ? (
        <ParticipantWorkspace
          task={workspaceTask}
          attemptId={session.attempt?.id}
          deadlineAt={session.attempt?.deadlineAt}
          contestTitle={session.contest?.title ?? "Контест"}
          participantName={session.participant?.displayName}
          busy={busy}
          error={error}
          onAnswer={answerTask}
          onSkip={skipTask}
          onNext={nextTask}
          onProbe={probeTask}
          onHint={hintTask}
          onGetAnswer={getAnswerTask}
          onApplyOperation={applyOperationTask}
          onUndo={undoMachineTask}
          onAiMessage={sendAiMessage}
          onLoadAiHistory={loadAiHistory}
          onTelemetry={recordTelemetry}
        />
      ) : (
        <main className="participant-waiting">
          <div className="participant-waiting__status" aria-hidden="true">
            <i />
          </div>
          <p className="eyebrow">
            {loading ? "Готовим среду" : "Задача недоступна"}
          </p>
          <h1>{loading ? "Создаём ваш вариант…" : "Не удалось открыть задачу"}</h1>
          <p>
            {loading
              ? "Расстановка воспроизводимо создаётся по seed этой попытки."
              : error}
          </p>
        </main>
      )}
    </div>
  );
}
