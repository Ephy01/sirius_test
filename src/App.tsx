import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ApiError,
  api,
  type ContestSummary as ApiContestSummary,
  type ParticipantTask as ApiParticipantTask,
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
  OrbitGlyph,
  PlusIcon,
} from "./components";
import {
  ContestBuilder,
  type ContestDraftInput,
  type ContestSummary as BuilderContestSummary,
  type GeneratedCodeRow,
  type ParticipantDraft,
} from "./organizer/ContestBuilder";
import {
  ParticipantWorkspace,
  type ParticipantTask as WorkspaceParticipantTask,
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
          <span className="status-dot" />
          <span>Система отбора</span>
          <strong>2026</strong>
        </div>
      </header>

      <main className="access-layout">
        <section className="gate-panel" aria-labelledby="gateTitle">
          <div className="gate-panel__content">
            <p className="eyebrow">Sirius Gate</p>
            <h2 id="gateTitle">Введите код доступа</h2>
            <p className="gate-description">
              Код определит вашу роль и откроет доступное рабочее пространство.
            </p>

            <form className="access-form" onSubmit={submitAccess} noValidate>
              <label htmlFor="accessCode">Персональный код</label>
              <div className={`access-input ${error ? "access-input--error" : ""}`}>
                <span aria-hidden="true">SG</span>
                <input
                  ref={inputRef}
                  id="accessCode"
                  name="accessCode"
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
  const [contests, setContests] = useState<ApiContestSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");

  async function refreshContests() {
    setLoading(true);
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
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshContests();
  }, [session.token]);

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
          families: input.taskConfig.families.map((family) => ({
            key: family.key,
            enabled: family.enabled,
            weight: family.weight,
            initial_difficulty: family.initialDifficulty,
            max_difficulty: family.maxDifficulty,
          })),
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

  const publishedCount = contests.filter(
    (contest) => contest.status === "published",
  ).length;

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
            <button className="side-nav-item" type="button" disabled>
              <span className="side-nav-icon">◎</span>
              Участники
            </button>
            <button className="side-nav-item" type="button" disabled>
              <span className="side-nav-icon">⌁</span>
              Хронология
            </button>
          </nav>

          <div className="sidebar-note">
            <OrbitGlyph small />
            <p>Первая станция готова к настройке.</p>
            <span>Gate / control plane</span>
          </div>
        </aside>

        <main className="dashboard-main">
          <header className="dashboard-heading">
            <div>
              <p className="eyebrow">Рабочее пространство организатора</p>
              <h1>Контесты</h1>
              <p>Создавайте испытания, назначайте среды и выдавайте коды участникам.</p>
            </div>
            <button
              className="primary-action primary-action--fit"
              type="button"
              onClick={() => setBuilderOpen(true)}
            >
              <PlusIcon />
              <span>Создать контест</span>
            </button>
          </header>

          <section className="dashboard-stats" aria-label="Краткая статистика">
            <article>
              <span>Активные контесты</span>
              <strong>{publishedCount}</strong>
              <small>опубликованы и доступны по кодам</small>
            </article>
            <article>
              <span>Всего контестов</span>
              <strong>{loading ? "…" : contests.length}</strong>
              <small>черновики и опубликованные</small>
            </article>
            <article className="dashboard-stats__accent">
              <span>Статус системы</span>
              <strong>Готова</strong>
              <small><i /> все сервисы доступны</small>
            </article>
          </section>

          {contests.length ? (
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
                    <span className="eyebrow">Шахматный мир</span>
                  </div>
                  <h2>{contest.title}</h2>
                  <p>{contest.durationMinutes} минут · персональные коды</p>
                </article>
              ))}
              <p className="dashboard-notice" role="status">
                {notice}
              </p>
            </section>
          ) : (
            <section
              className="empty-dashboard"
              aria-labelledby="emptyDashboardTitle"
            >
              <div className="empty-dashboard__visual" aria-hidden="true">
                <OrbitGlyph />
                <span>+</span>
              </div>
              <div className="empty-dashboard__copy">
                <span className="empty-label">Пустое пространство</span>
                <h2 id="emptyDashboardTitle">Здесь появятся ваши контесты</h2>
                <p>
                  Первый контест начнётся с настройки «Шахматного мира» и
                  выпуска персональных кодов.
                </p>
                <button
                  className="text-action"
                  type="button"
                  onClick={() => setBuilderOpen(true)}
                >
                  Создать первый контест
                  <ArrowIcon />
                </button>
                <p className="dashboard-notice" role="status">
                  {notice}
                </p>
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
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
          <i />
        </div>
        <p className="eyebrow">
          Контест готов
        </p>
        <h1>{session.contest?.title ?? "Шахматный мир"}</h1>
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
            <dd>Шахматный мир</dd>
          </div>
          <div>
            <dt>Длительность</dt>
            <dd>{session.contest?.durationMinutes ?? 60} минут</dd>
          </div>
        </dl>

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

  async function answerTask(answer: string) {
    if (!task || task.status !== "active") return;
    await runTaskAction(async () => {
      const response = await api.answerTask(task.id, answer, {
        token: session.token,
      });
      setTask(response.task);
    });
  }

  async function skipTask() {
    if (!task || task.status !== "active") return;
    await runTaskAction(async () => {
      const response = await api.skipTask(task.id, {
        token: session.token,
      });
      setTask(response.task);
    });
  }

  async function nextTask() {
    if (!task || task.status === "active") return;
    await runTaskAction(async () => {
      const response = await api.getNextTask({ token: session.token });
      setTask(response.task);
    });
  }

  async function runTaskAction(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
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

  const workspaceTask: WorkspaceParticipantTask | null = task
    ? {
        id: task.id,
        ordinal: task.ordinal,
        family: task.family,
        difficulty: task.difficulty,
        status: task.status,
        prompt: task.publicState.prompt,
        backRank: task.publicState.backRank as WorkspaceParticipantTask["backRank"],
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
          deadlineAt={session.attempt?.deadlineAt}
          contestTitle={session.contest?.title ?? "Контест"}
          participantName={session.participant?.displayName}
          busy={busy}
          error={error}
          onAnswer={answerTask}
          onSkip={skipTask}
          onNext={nextTask}
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
