import { useEffect, useState } from "react";
import { api, type ContestSummary } from "../api";
import type { AccessSession } from "../auth";
import {
  AppHeader,
  ArrowIcon,
  ENVIRONMENT_LABEL,
  PlusIcon,
} from "../components";
import type {
  ContestDraftInput,
  GeneratedCodeRow,
  ParticipantDraft,
} from "./builder/draft";
import { ContestBuilder } from "./ContestBuilder";
import { ContestAccessPanel } from "./ContestAccessPanel";

export function OrganizerDashboard({
  session,
  onLogout,
}: {
  session: AccessSession;
  onLogout: () => void;
}) {
  const [builderOpen, setBuilderOpen] = useState(false);
  const [managedContest, setManagedContest] =
    useState<ContestSummary | null>(null);
  const [contests, setContests] = useState<ContestSummary[]>([]);
  const [notice, setNotice] = useState("");
  const [contestPendingDeletion, setContestPendingDeletion] =
    useState<ContestSummary | null>(null);
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

  function createContest(input: ContestDraftInput): Promise<ContestSummary> {
    const { taskConfig } = input;
    return api.createContest(
      {
        title: input.title,
        durationMinutes: input.durationMinutes,
        taskConfig: {
          adaptation_threshold: taskConfig.adaptationThreshold,
          cohort_seed: taskConfig.cohortSeed,
          debug_reveal_answers: taskConfig.debugRevealAnswers === true,
          ...(taskConfig.ai
            ? {
                ai: {
                  enabled: taskConfig.ai.enabled,
                  mode: taskConfig.ai.mode,
                  max_turns_per_attempt: taskConfig.ai.maxTurnsPerAttempt,
                  max_turns_per_task: taskConfig.ai.maxTurnsPerTask,
                },
              }
            : {}),
          trajectory: {
            mode: "adaptive",
            director_version: "director-v2",
            start_family: (
              taskConfig.families.find((family) => family.enabled) ??
              taskConfig.families[0]
            )?.key,
          },
          families: taskConfig.families.map((family) => ({
            family: family.key,
            skin: family.skin,
            enabled: family.enabled,
            weight: family.weight,
            initial_difficulty: family.initialDifficulty,
            max_difficulty: family.maxDifficulty,
            sub_kinds: family.subKinds,
          })),
          ...(taskConfig.scriptedTasks.length > 0
            ? {
                scripted_tasks: taskConfig.scriptedTasks.map((task) => ({
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
    const response = await api.generateCodes(contestId, {
      token: session.token,
    });
    return response.codes.map((item) => ({
      enrollmentId: item.enrollmentId,
      externalRef: item.participantExternalRef ?? "—",
      displayName: item.participantName,
      code: item.code,
    }));
  }

  async function publishContest(contestId: string): Promise<ContestSummary> {
    const published = await api.publishContest(contestId, {
      token: session.token,
    });
    await refreshContests();
    return published;
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
          onLoadFamilies={(signal) =>
            api.listTaskFamilies({ token: session.token, signal })
          }
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
                  <span className="eyebrow">{ENVIRONMENT_LABEL}</span>
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
