import { useEffect, useState } from "react";
import {
  ApiError,
  api,
  type ContestEnrollmentAccess,
  type ContestSummary,
  type DownloadedFile,
} from "../api";
import "./contest-access-panel.css";

type ActionKind = "rotate" | "grant" | "download-log";

type BusyAction = {
  enrollmentId: string;
  kind: ActionKind;
} | null;

function formatDateTime(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function participantCountLabel(count: number) {
  const modulo100 = count % 100;
  const modulo10 = count % 10;
  if (modulo100 >= 11 && modulo100 <= 14) return `${count} участников`;
  if (modulo10 === 1) return `${count} участник`;
  if (modulo10 >= 2 && modulo10 <= 4) return `${count} участника`;
  return `${count} участников`;
}

function codeState(row: ContestEnrollmentAccess) {
  const code = row.latestCode;
  if (!code) {
    return {
      label: "Не выпущен",
      detail: "Код ещё не создавался",
      tone: "neutral",
    };
  }

  if (code.status === "revoked") {
    return {
      label: "Отозван",
      detail: code.revokedAt
        ? `Отозван ${formatDateTime(code.revokedAt)}`
        : "Этот код больше не принимается",
      tone: "muted",
    };
  }

  if (code.status === "expired") {
    return {
      label: "Срок истёк",
      detail: code.expiresAt
        ? `Истёк ${formatDateTime(code.expiresAt)}`
        : "Этот код больше не принимается",
      tone: "warning",
    };
  }

  return {
    label: "Действует",
    detail: code.expiresAt
      ? `До ${formatDateTime(code.expiresAt)}`
      : "Без ограничения срока",
    tone: "success",
  };
}

function attemptState(row: ContestEnrollmentAccess) {
  const attempt = row.latestAttempt;
  if (!attempt) {
    return {
      label: "Не начата",
      detail: "Первая попытка уже доступна",
      tone: "neutral",
    };
  }

  if (attempt.status === "active") {
    return {
      label: `Попытка ${attempt.number} идёт`,
      detail: attempt.deadlineAt
        ? `До ${formatDateTime(attempt.deadlineAt)}`
        : "Таймер запущен",
      tone: "success",
    };
  }

  if (attempt.status === "completed") {
    return {
      label: `Попытка ${attempt.number} завершена`,
      detail: attempt.finishedAt
        ? formatDateTime(attempt.finishedAt) ?? "Завершена"
        : "Завершена участником",
      tone: "muted",
    };
  }

  return {
    label: `Попытка ${attempt.number} истекла`,
    detail: attempt.deadlineAt
      ? `Таймер закончился ${formatDateTime(attempt.deadlineAt)}`
      : "Отведённое время закончилось",
    tone: "warning",
  };
}

function actionError(caught: unknown, fallback: string) {
  return caught instanceof ApiError || caught instanceof Error
    ? caught.message
    : fallback;
}

function saveDownloadedFile(file: DownloadedFile) {
  const url = URL.createObjectURL(file.blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.filename;
  anchor.hidden = true;
  document.body.append(anchor);

  try {
    anchor.click();
  } finally {
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
  }
}

export function ContestAccessPanel({
  contest,
  token,
  onBack,
}: {
  contest: ContestSummary;
  token: string;
  onBack: () => void;
}) {
  const [rows, setRows] = useState<ContestEnrollmentAccess[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [freshCodes, setFreshCodes] = useState<Record<string, string>>({});

  async function refreshRows(signal?: AbortSignal) {
    const items = await api.listContestEnrollments(contest.id, {
      token,
      signal,
    });
    setRows(items);
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    refreshRows(controller.signal)
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setError(
          actionError(caught, "Не удалось загрузить доступы участников."),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [contest.id, token]);

  async function rotateCode(row: ContestEnrollmentAccess) {
    const confirmed = window.confirm(
      row.latestCode
        ? `Перевыпустить код для «${row.participant.displayName}»? Предыдущий код сразу перестанет работать.`
        : `Выпустить код для «${row.participant.displayName}»?`,
    );
    if (!confirmed) return;

    setBusyAction({ enrollmentId: row.id, kind: "rotate" });
    setError("");
    setNotice("");
    try {
      const result = await api.rotateEnrollmentCode(
        contest.id,
        row.id,
        {},
        { token },
      );
      setFreshCodes((current) => ({
        ...current,
        [row.id]: result.code,
      }));
      await refreshRows();
      setNotice(
        `Новый код для «${row.participant.displayName}» выпущен. Скопируйте его сейчас: после обновления страницы он будет скрыт.`,
      );
    } catch (caught) {
      setError(actionError(caught, "Не удалось перевыпустить код."));
    } finally {
      setBusyAction(null);
    }
  }

  async function grantAttempt(row: ContestEnrollmentAccess) {
    setBusyAction({ enrollmentId: row.id, kind: "grant" });
    setError("");
    setNotice("");
    try {
      const result = await api.grantNextAttempt(contest.id, row.id, { token });
      await refreshRows();
      setNotice(
        result.created
          ? `Новая попытка для «${row.participant.displayName}» разрешена. Час начнётся только после нажатия участником кнопки «Начать».`
          : `Новая попытка для «${row.participant.displayName}» уже была разрешена.`,
      );
    } catch (caught) {
      setError(actionError(caught, "Не удалось разрешить новую попытку."));
    } finally {
      setBusyAction(null);
    }
  }

  async function downloadTelemetry(row: ContestEnrollmentAccess) {
    setBusyAction({ enrollmentId: row.id, kind: "download-log" });
    setError("");
    setNotice("");
    try {
      const file = await api.downloadEnrollmentTelemetry(
        contest.id,
        row.id,
        { token },
      );
      saveDownloadedFile(file);
      setNotice(`Лог действий «${row.participant.displayName}» скачан.`);
    } catch (caught) {
      setError(actionError(caught, "Не удалось скачать лог участника."));
    } finally {
      setBusyAction(null);
    }
  }

  async function copyCode(enrollmentId: string) {
    const code = freshCodes[enrollmentId];
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setError("");
      setNotice("Код скопирован в буфер обмена.");
    } catch {
      setError("Не удалось скопировать код автоматически. Выделите его вручную.");
    }
  }

  return (
    <main className="access-manager">
      <header className="access-manager__heading">
        <button className="access-manager__back" type="button" onClick={onBack}>
          <span aria-hidden="true">←</span>
          Все контесты
        </button>
        <div>
          <p className="eyebrow">Управление доступом</p>
          <h1>{contest.title}</h1>
          <p>
            {contest.durationMinutes} минут ·{" "}
            {contest.status === "published" ? "контест опубликован" : "черновик"}
          </p>
        </div>
      </header>

      <section className="access-roster" aria-labelledby="accessRosterTitle">
        <div className="access-roster__heading">
          <div>
            <h2 id="accessRosterTitle">Участники и доступы</h2>
            <p>{loading ? "Загружаем…" : participantCountLabel(rows.length)}</p>
          </div>
          <button
            className="access-manager__refresh"
            type="button"
            onClick={() => {
              setLoading(true);
              setError("");
              refreshRows()
                .catch((caught) =>
                  setError(
                    actionError(
                      caught,
                      "Не удалось обновить список участников.",
                    ),
                  ),
                )
                .finally(() => setLoading(false));
            }}
            disabled={loading || busyAction !== null}
          >
            Обновить
          </button>
        </div>

        <div className="access-manager__messages" aria-live="polite">
          {error && <p className="access-manager__error">{error}</p>}
          {notice && <p className="access-manager__notice">{notice}</p>}
        </div>

        {!loading && !rows.length && !error ? (
          <div className="access-roster__empty">
            В этом контесте пока нет участников.
          </div>
        ) : (
          <div className="access-roster__table-wrap">
            <table className="access-roster__table">
              <thead>
                <tr>
                  <th>Участник</th>
                  <th>Код</th>
                  <th>Попытка</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const code = codeState(row);
                  const attempt = attemptState(row);
                  const freshCode = freshCodes[row.id];
                  const rotateBusy =
                    busyAction?.enrollmentId === row.id &&
                    busyAction.kind === "rotate";
                  const grantBusy =
                    busyAction?.enrollmentId === row.id &&
                    busyAction.kind === "grant";
                  const downloadBusy =
                    busyAction?.enrollmentId === row.id &&
                    busyAction.kind === "download-log";
                  const hasActiveAttempt =
                    row.latestAttempt?.status === "active";
                  const canGrant =
                    Boolean(row.latestAttempt) &&
                    !hasActiveAttempt &&
                    !row.attemptGrantPending;

                  return (
                    <tr key={row.id}>
                      <td data-label="Участник">
                        <strong className="access-roster__participant">
                          {row.participant.displayName}
                        </strong>
                        <small>
                          {row.participant.externalRef || "Без внешнего ID"}
                        </small>
                      </td>
                      <td data-label="Код">
                        {freshCode ? (
                          <div className="fresh-code">
                            <code>{freshCode}</code>
                            <button
                              type="button"
                              onClick={() => void copyCode(row.id)}
                            >
                              Копировать
                            </button>
                            <small>Показывается только сейчас</small>
                          </div>
                        ) : (
                          <>
                            <div className="access-state">
                              <span
                                className={`access-state__dot access-state__dot--${code.tone}`}
                              />
                              <strong>{code.label}</strong>
                              {row.latestCode && (
                                <code>•••• {row.latestCode.last4}</code>
                              )}
                            </div>
                            <small>{code.detail}</small>
                          </>
                        )}
                      </td>
                      <td data-label="Попытка">
                        <div className="access-state">
                          <span
                            className={`access-state__dot access-state__dot--${attempt.tone}`}
                          />
                          <strong>{attempt.label}</strong>
                        </div>
                        <small>{attempt.detail}</small>
                        {row.attemptGrantPending && (
                          <span className="attempt-grant-badge">
                            Новая попытка разрешена
                          </span>
                        )}
                      </td>
                      <td data-label="Действия">
                        <div className="access-roster__actions">
                          <button
                            type="button"
                            onClick={() => void rotateCode(row)}
                            disabled={
                              busyAction !== null ||
                              row.status === "disabled"
                            }
                          >
                            {rotateBusy
                              ? "Выпускаем…"
                              : row.latestCode
                                ? "Перевыпустить код"
                                : "Выпустить код"}
                          </button>
                          <button
                            type="button"
                            onClick={() => void grantAttempt(row)}
                            disabled={
                              busyAction !== null ||
                              !canGrant ||
                              row.status === "disabled"
                            }
                            title={
                              !row.latestAttempt
                                ? "Первая попытка уже доступна без дополнительного разрешения"
                                : hasActiveAttempt
                                  ? "Текущая попытка ещё идёт"
                                  : row.attemptGrantPending
                                    ? "Новая попытка уже разрешена"
                                    : undefined
                            }
                          >
                            {grantBusy
                              ? "Разрешаем…"
                              : "Разрешить новую попытку"}
                          </button>
                          <button
                            type="button"
                            onClick={() => void downloadTelemetry(row)}
                            disabled={busyAction !== null}
                            aria-label={`Скачать лог действий участника ${row.participant.displayName}`}
                          >
                            {downloadBusy ? "Скачиваем…" : "Скачать лог"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
