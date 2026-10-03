import { useState } from "react";
import { api } from "../api";
import { updateAccessSession, type AccessSession } from "../auth";
import { AppHeader, ArrowIcon, ENVIRONMENT_LABEL } from "../components";
import { ParticipantContestScreen } from "./ParticipantContestScreen";
import { ParticipantTutorial } from "./ParticipantTutorial";

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

export function ParticipantWaitingScreen({
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
  const [showTutorial, setShowTutorial] = useState(false);

  if (session.attempt) {
    return (
      <ParticipantContestScreen
        session={session}
        onLogout={onLogout}
      />
    );
  }

  if (showTutorial) {
    return (
      <div className="participant-page">
        <AppHeader
          role="Участник"
          onLogout={onLogout}
          meta={<span className="workspace-label">Инструктаж</span>}
        />
        <ParticipantTutorial onClose={() => setShowTutorial(false)} />
      </div>
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
        <h1>{session.contest?.title ?? ENVIRONMENT_LABEL}</h1>
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
            <dd>{ENVIRONMENT_LABEL}</dd>
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

        <div className="participant-waiting__actions">
          <button
            className="secondary-action participant-instruction"
            type="button"
            disabled={busy}
            onClick={() => setShowTutorial(true)}
          >
            Инструктаж
          </button>
          <button
            className="primary-action participant-start"
            type="button"
            disabled={busy}
            onClick={startAttempt}
          >
            <span>{busy ? "Запускаем…" : "Начать попытку"}</span>
            <ArrowIcon />
          </button>
        </div>
        <p className="participant-error" role="alert">
          {error}
        </p>
      </main>
    </div>
  );
}
