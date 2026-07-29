import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  clearAccessSession,
  createAccessSession,
  DEMO_CODES,
  loadAccessSession,
  normalizeAccessCode,
  resolveAccessCode,
  saveAccessSession,
  type AccessRole,
  type AccessSession,
} from "./auth";
import {
  AppHeader,
  ArrowIcon,
  Brand,
  OrbitGlyph,
  PlusIcon,
} from "./components";

type Authenticate = (role: AccessRole, code: string) => void;

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

  function authenticate(role: AccessRole, code: string) {
    const nextSession = createAccessSession(role, code);
    saveAccessSession(nextSession);
    setSession(nextSession);
    const destination = role === "organizer" ? "/organizer" : "/contest";
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
  if (session.role === "organizer") return <OrganizerDashboard onLogout={logout} />;
  return <ParticipantContest onLogout={logout} />;
}

function AccessScreen({ onAuthenticate }: { onAuthenticate: Authenticate }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function selectDemoCode(value: string) {
    setCode(value);
    setError("");
    inputRef.current?.focus();
  }

  function submitAccess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = normalizeAccessCode(code);
    const role = resolveAccessCode(normalized);

    if (!role) {
      setError("Код не найден. Проверьте символы или выберите демо-доступ ниже.");
      inputRef.current?.focus();
      return;
    }

    setBusy(true);
    setError("");

    window.setTimeout(() => {
      onAuthenticate(role, normalized);
    }, 360);
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
        <section className="access-story" aria-labelledby="accessTitle">
          <div className="access-story__copy">
            <p className="eyebrow">Интеллектуальные состязания нового типа</p>
            <h1 id="accessTitle">
              Маршрут,
              <span> которого раньше не было.</span>
            </h1>
            <p className="access-lead">
              Задачи меняются вслед за вашими решениями. Исследуйте правила,
              проверяйте идеи и двигайтесь по собственной траектории.
            </p>
          </div>

          <div className="story-facts" aria-label="Особенности платформы">
            <article>
              <span>01</span>
              <strong>Новый вариант</strong>
              <p>У каждого участника свой маршрут миссии.</p>
            </article>
            <article>
              <span>02</span>
              <strong>ИИ по желанию</strong>
              <p>Навигатор помогает думать, но может ошибаться.</p>
            </article>
            <article>
              <span>03</span>
              <strong>Видимый процесс</strong>
              <p>Организатор видит хронологию решений.</p>
            </article>
          </div>

          <div className="story-visual" aria-hidden="true">
            <OrbitGlyph />
            <span className="story-visual__label story-visual__label--one">
              исследуй
            </span>
            <span className="story-visual__label story-visual__label--two">
              проверяй
            </span>
            <span className="story-visual__label story-visual__label--three">
              решай
            </span>
          </div>
        </section>

        <section className="gate-panel" aria-labelledby="gateTitle">
          <div className="gate-panel__top">
            <span>Единая точка входа</span>
            <span className="secure-label">защищённый доступ</span>
          </div>

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

            <div className="demo-access" aria-label="Демонстрационные коды">
              <div className="demo-access__heading">
                <span>Демо-доступ</span>
                <small>только для прототипа</small>
              </div>
              <button
                type="button"
                onClick={() => selectDemoCode(DEMO_CODES.participant)}
              >
                <span>
                  <i className="demo-role demo-role--participant" />
                  Участник
                </span>
                <code>{DEMO_CODES.participant}</code>
              </button>
              <button
                type="button"
                onClick={() => selectDemoCode(DEMO_CODES.organizer)}
              >
                <span>
                  <i className="demo-role demo-role--organizer" />
                  Организатор
                </span>
                <code>{DEMO_CODES.organizer}</code>
              </button>
            </div>
          </div>

          <footer className="gate-panel__footer">
            <span>© Университет «Сириус»</span>
            <span>Прототип интерфейса</span>
          </footer>
        </section>
      </main>
    </div>
  );
}

function OrganizerDashboard({ onLogout }: { onLogout: () => void }) {
  const [notice, setNotice] = useState("");

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
              <small>0</small>
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
              onClick={() => setNotice("Конструктор контеста станет следующим экраном разработки.")}
            >
              <PlusIcon />
              <span>Создать контест</span>
            </button>
          </header>

          <section className="dashboard-stats" aria-label="Краткая статистика">
            <article>
              <span>Активные контесты</span>
              <strong>0</strong>
              <small>пока ничего не запущено</small>
            </article>
            <article>
              <span>Выданные коды</span>
              <strong>0</strong>
              <small>участники ещё не добавлены</small>
            </article>
            <article className="dashboard-stats__accent">
              <span>Статус системы</span>
              <strong>Готова</strong>
              <small><i /> все сервисы доступны</small>
            </article>
          </section>

          <section className="empty-dashboard" aria-labelledby="emptyDashboardTitle">
            <div className="empty-dashboard__visual" aria-hidden="true">
              <OrbitGlyph />
              <span>+</span>
            </div>
            <div className="empty-dashboard__copy">
              <span className="empty-label">Пустое пространство</span>
              <h2 id="emptyDashboardTitle">Здесь появятся ваши контесты</h2>
              <p>
                Первый контест начнётся с выбора игровых сред, начальной сложности
                и количества доступных кодов.
              </p>
              <button
                className="text-action"
                type="button"
                onClick={() => setNotice("Конструктор контеста станет следующим экраном разработки.")}
              >
                Создать первый контест
                <ArrowIcon />
              </button>
              <p className="dashboard-notice" role="status">
                {notice}
              </p>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

type ConsoleEntry = {
  id: number;
  author: "Система" | "Вы" | "ИИ-навигатор";
  tone: "system" | "user" | "ai";
  text: string;
};

const INITIAL_CONSOLE: ConsoleEntry[] = [
  {
    id: 1,
    author: "Система",
    tone: "system",
    text: "Миссия DC–03 запущена. Все действия выполняются через эту консоль.",
  },
  {
    id: 2,
    author: "Система",
    tone: "system",
    text: "Введите /help, чтобы увидеть доступные команды.",
  },
];

function ParticipantContest({ onLogout }: { onLogout: () => void }) {
  const [input, setInput] = useState("");
  const [entries, setEntries] = useState<ConsoleEntry[]>(INITIAL_CONSOLE);
  const [secondsLeft, setSecondsLeft] = useState(() => getInitialSecondsLeft());
  const nextId = useRef(3);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setSecondsLeft(getInitialSecondsLeft());
    }, 1000);
    return () => window.clearInterval(interval);
  }, []);

  const timer = useMemo(() => {
    const minutes = String(Math.floor(secondsLeft / 60)).padStart(2, "0");
    const seconds = String(secondsLeft % 60).padStart(2, "0");
    return `${minutes}:${seconds}`;
  }, [secondsLeft]);

  function appendEntry(author: ConsoleEntry["author"], tone: ConsoleEntry["tone"], text: string) {
    setEntries((current) => [
      ...current,
      { id: nextId.current++, author, tone, text },
    ]);
  }

  function submitCommand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const command = input.trim();
    if (!command) return;

    setInput("");
    appendEntry("Вы", "user", command);

    window.setTimeout(() => {
      const normalized = command.toLowerCase();
      if (normalized === "/help") {
        appendEntry(
          "Система",
          "system",
          "/ask <вопрос> · /check <черновик> · /answer <ответ> · /skip",
        );
      } else if (normalized.startsWith("/ask")) {
        appendEntry(
          "ИИ-навигатор",
          "ai",
          "Начните с пространства исходов: сколько различных пар могут образовать два шестигранных кубика?",
        );
      } else if (normalized.startsWith("/check")) {
        appendEntry(
          "ИИ-навигатор",
          "ai",
          "Я могу ошибаться, но в черновике стоит отдельно проверить пересечение событий с двумя ферзями.",
        );
      } else if (normalized.startsWith("/answer")) {
        appendEntry(
          "Система",
          "system",
          "Ответ зафиксирован. Официальная правильность будет скрыта до завершения контеста.",
        );
      } else if (normalized === "/skip") {
        appendEntry(
          "Система",
          "system",
          "Задача сохранена в маршруте. Переход к следующему эпизоду будет подключён на следующем этапе.",
        );
      } else {
        appendEntry(
          "Система",
          "system",
          "Команда не распознана. Используйте /help.",
        );
      }
    }, 280);
  }

  return (
    <div className="contest-page">
      <AppHeader
        role="Участник"
        onLogout={onLogout}
        meta={
          <div className="contest-meta">
            <span>Dice &amp; Chess</span>
            <time dateTime={`PT${secondsLeft}S`}>{timer}</time>
          </div>
        }
      />

      <main className="contest-main">
        <section className="mission-route" aria-label="Маршрут миссии">
          <div>
            <span className="eyebrow">Маршрут миссии</span>
            <strong>Вероятности на доске</strong>
          </div>
          <ol>
            <li className="mission-route__done"><i>✓</i><span>Разведка</span></li>
            <li className="mission-route__active"><i>02</i><span>Комбинации</span></li>
            <li><i>03</i><span>Стратегия</span></li>
            <li><i>04</i><span>Финал</span></li>
          </ol>
          <span className="mission-route__code">SESSION 7F2A</span>
        </section>

        <div className="mission-workspace">
          <article className="task-panel">
            <header className="panel-heading">
              <div>
                <p className="eyebrow">Эпизод 02 · обучение</p>
                <span>DC–03</span>
              </div>
              <span className="difficulty-label">уровень 3 / 10</span>
            </header>

            <div className="task-panel__body">
              <div className="task-copy">
                <p className="task-subject">Вероятность составного события</p>
                <h1>Откройте атакующую комбинацию</h1>
                <p>
                  Бросают два честных кубика. На их гранях изображены шахматные
                  фигуры. Кубики различимы.
                </p>
              </div>

              <section className="success-condition">
                <span>Условие успеха</span>
                <p>
                  Выпал <strong>хотя бы один ферзь</strong> или одновременно
                  выпали <strong>ладья и конь</strong>.
                </p>
              </section>

              <section className="task-question">
                <span>Вопрос</span>
                <h2>Какова вероятность получить атакующую комбинацию?</h2>
                <p>Ответьте через консоль справа. Объяснение можно добавить после числа.</p>
              </section>

              <div className="game-board">
                <ChessBoard />
                <DicePanel />
              </div>
            </div>
          </article>

          <section className="terminal-panel" aria-labelledby="terminalTitle">
            <header className="terminal-heading">
              <div>
                <p className="eyebrow">Единая точка управления</p>
                <h2 id="terminalTitle">Консоль миссии</h2>
              </div>
              <span className="online-state"><i /> online</span>
            </header>

            <div className="terminal-log" role="log" aria-live="polite">
              {entries.map((entry) => (
                <article className={`terminal-entry terminal-entry--${entry.tone}`} key={entry.id}>
                  <header>
                    <span>{entry.author}</span>
                    <time>сейчас</time>
                  </header>
                  <p>{entry.text}</p>
                </article>
              ))}
            </div>

            <form className="terminal-form" onSubmit={submitCommand}>
              <label htmlFor="missionCommand">
                <span>pilot@dc03:~$</span>
                <input
                  id="missionCommand"
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key !== "Enter") return;
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }}
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="Введите /help…"
                />
              </label>
              <button className="visually-hidden" type="submit">
                Выполнить команду
              </button>
              <div>
                <span>Enter — выполнить</span>
                <span>ИИ может ошибаться</span>
              </div>
            </form>
          </section>
        </div>
      </main>
    </div>
  );
}

function getInitialSecondsLeft() {
  const key = "sirius-gate:participant-deadline";
  const now = Date.now();
  const stored = Number(window.sessionStorage.getItem(key));
  const deadline = Number.isFinite(stored) && stored > now ? stored : now + 60 * 60 * 1000;
  window.sessionStorage.setItem(key, String(deadline));
  return Math.max(0, Math.ceil((deadline - now) / 1000));
}

function ChessBoard() {
  const pieces = [
    "♝", "♞", "♜", "♚", "♛", "♝", "♜", "♞",
    ...Array(8).fill("♟"),
    ...Array(32).fill(""),
    ...Array(8).fill("♙"),
    "♗", "♘", "♖", "♔", "♕", "♗", "♖", "♘",
  ];

  return (
    <figure className="chess-card">
      <figcaption>
        <span>Позиция Chess960</span>
        <small>seed 7F2A</small>
      </figcaption>
      <div className="chess-grid" role="img" aria-label="Стартовая позиция Chess960">
        {pieces.map((piece, index) => (
          <span
            className={(Math.floor(index / 8) + index) % 2 ? "dark" : "light"}
            key={index}
            aria-hidden="true"
          >
            {piece}
          </span>
        ))}
      </div>
    </figure>
  );
}

function DicePanel() {
  const dice = [
    { name: "Кубик A", faces: ["♙", "♙", "♘", "♘", "♖", "♕"] },
    { name: "Кубик B", faces: ["♙", "♘", "♘", "♗", "♖", "♕"] },
  ];

  return (
    <section className="dice-panel" aria-label="Грани кубиков">
      <header>
        <span>Грани кубиков</span>
        <small>все грани равновероятны</small>
      </header>
      {dice.map((die, dieIndex) => (
        <div className="dice-row" key={die.name}>
          <strong>
            <i>{dieIndex ? "B" : "A"}</i>
            {die.name}
          </strong>
          <div>
            {die.faces.map((face, index) => (
              <span key={`${die.name}-${index}`}>{face}</span>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
