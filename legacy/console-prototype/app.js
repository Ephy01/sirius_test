"use strict";

const taskCatalog = {
  root: {
    id: "root",
    code: "DC–03",
    path: "ЭПИЗОД 03 · ОБУЧЕНИЕ",
    overline: "Вероятность составного события",
    title: "Откройте атакующую комбинацию",
    description:
      "Бросают два честных кубика. На их гранях изображены шахматные фигуры. Кубики различимы.",
    condition:
      "Комбинация открывается, если выпал <strong>хотя бы один ферзь</strong> или одновременно выпали <strong>ладья и конь</strong>.",
    question: "Какова вероятность получить атакующую комбинацию?",
    hint: "Ответьте дробью, процентом или десятичным числом. Итог лучше поставить в конце объяснения.",
    expected: 5 / 12,
  },
  advanced: {
    id: "advanced",
    code: "DC–04A",
    path: "ЭПИЗОД 04 · УСЛОВНАЯ ВЕРОЯТНОСТЬ",
    overline: "Ветка: точный расчёт",
    title: "Продолжите атаку без ферзя",
    description:
      "Используются те же два кубика. Теперь известно, что ни на одном из них не выпал ферзь.",
    condition:
      "Успехом считается только пара <strong>ладья и конь</strong>. Порядок кубиков не важен, но сами кубики различимы.",
    question:
      "Какова вероятность пары «ладья + конь», если известно, что ферзь не выпал?",
    hint: "Сначала определите, сколько исходов осталось после нового условия.",
    expected: 4 / 25,
  },
  scaffold: {
    id: "scaffold",
    code: "DC–04B",
    path: "ЭПИЗОД 04 · ОБЪЕДИНЕНИЕ СОБЫТИЙ",
    overline: "Ветка: уточнение комбинации",
    title: "Посчитайте пару отдельно",
    description:
      "Вернёмся к исходным кубикам и отдельно рассмотрим вторую часть условия.",
    condition:
      "Нужна ровно одна пара: на одном кубике выпала <strong>ладья</strong>, а на другом — <strong>конь</strong>.",
    question: "Какова вероятность получить пару «ладья + конь»?",
    hint: "Учтите оба порядка: A–ладья, B–конь и A–конь, B–ладья.",
    expected: 1 / 9,
  },
  basics: {
    id: "basics",
    code: "DC–04C",
    path: "ЭПИЗОД 04 · ПРОСТРАНСТВО ИСХОДОВ",
    overline: "Ветка: карта результатов",
    title: "Постройте поле исходов",
    description:
      "У каждого честного кубика шесть равновероятных граней. Кубики различимы: A–ферзь, B–конь и A–конь, B–ферзь — разные результаты.",
    condition:
      "Сейчас не нужно искать атакующую комбинацию. Определите только размер полного <strong>пространства исходов</strong>.",
    question: "Сколько различных пар результатов дают два шестигранных кубика?",
    hint: "Ответьте одним числом и при желании добавьте короткое объяснение.",
    expected: 36,
  },
};

const diceFaces = {
  A: ["пешка", "пешка", "конь", "конь", "ладья", "ферзь"],
  B: ["пешка", "конь", "конь", "слон", "ладья", "ферзь"],
};

const state = {
  startedAt: Date.now(),
  timer: null,
  phase: "ready",
  currentTask: "root",
  currentResult: null,
  pendingAnswer: null,
  pendingAnswerAt: null,
  attempts: 0,
  maxAttempts: 3,
  episode: 3,
  aiRequests: 0,
  aiBusy: false,
  rollCount: 0,
  route: ["root"],
};

const elements = {
  sessionTime: document.querySelector("#sessionTime"),
  taskPath: document.querySelector("#taskPath"),
  taskCode: document.querySelector("#taskCode"),
  taskOverline: document.querySelector("#taskOverline"),
  taskTitle: document.querySelector("#taskTitle"),
  taskDescription: document.querySelector("#taskDescription"),
  conditionText: document.querySelector("#conditionText"),
  questionText: document.querySelector("#questionText"),
  answerHint: document.querySelector("#answerHint"),
  chessBoard: document.querySelector("#chessBoard"),
  taskScroll: document.querySelector(".task-scroll"),
  consoleLog: document.querySelector("#consoleLog"),
  commandForm: document.querySelector("#commandForm"),
  commandInput: document.querySelector("#commandInput"),
  promptLabel: document.querySelector("#promptLabel"),
  phaseHint: document.querySelector("#phaseHint"),
};

const commandAliases = new Map([
  ["help", "help"],
  ["commands", "help"],
  ["помощь", "help"],
  ["ask", "ask"],
  ["ai", "ask"],
  ["вопрос", "ask"],
  ["answer", "answer"],
  ["ответ", "answer"],
  ["confidence", "confidence"],
  ["уверенность", "confidence"],
  ["next", "next"],
  ["далее", "next"],
  ["status", "status"],
  ["статус", "status"],
  ["task", "task"],
  ["задача", "task"],
  ["rules", "rules"],
  ["правила", "rules"],
  ["roll", "roll"],
  ["бросок", "roll"],
  ["clear", "clear"],
  ["очистить", "clear"],
  ["cancel", "cancel"],
  ["отмена", "cancel"],
]);

const primaryCommands = [
  "help",
  "ask",
  "answer",
  "confidence",
  "next",
  "status",
  "task",
  "rules",
  "roll",
  "clear",
  "cancel",
];

function initializeMission() {
  buildChessBoard();
  loadTask(taskCatalog[state.currentTask]);
  updateTimer();
  state.timer = window.setInterval(updateTimer, 1000);

  appendEntry(
    "system",
    "СИСТЕМА",
    "Сессия 7F2A запущена. Слева находится условие, справа — единственная точка управления миссией.",
  );
  appendEntry(
    "system",
    "СИСТЕМА",
    "Введите /help, чтобы увидеть команды. Обычный текст без команды будет отправлен ИИ-навигатору.",
  );
  appendEntry(
    "system",
    "МЕТОДИКА",
    "Ответ проверяется только после двух команд: /answer, затем /confidence. Так уверенность фиксируется до обратной связи.",
  );

  updatePhaseUI();
  logEvent("mission_started", {
    mission: "dice_chess",
    version: "console-demo-0.2",
    chess_variant: "chess960",
    seed: "7F2A",
  });

  window.requestAnimationFrame(() => {
    elements.commandInput.focus({ preventScroll: true });
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  });
}

function buildChessBoard() {
  const blackBackRank = ["♝", "♞", "♜", "♚", "♛", "♝", "♜", "♞"];
  const whiteBackRank = ["♗", "♘", "♖", "♔", "♕", "♗", "♖", "♘"];
  const fragment = document.createDocumentFragment();

  for (let index = 0; index < 64; index += 1) {
    const row = Math.floor(index / 8);
    const column = index % 8;
    const square = document.createElement("span");
    square.className = `chess-square ${(row + column) % 2 ? "dark" : "light"}`;
    square.setAttribute("aria-hidden", "true");

    if (row === 0) {
      square.textContent = blackBackRank[column];
      square.classList.add("black-piece");
    } else if (row === 1) {
      square.textContent = "♟";
      square.classList.add("black-piece");
    } else if (row === 6) {
      square.textContent = "♙";
      square.classList.add("white-piece");
    } else if (row === 7) {
      square.textContent = whiteBackRank[column];
      square.classList.add("white-piece");
    }

    fragment.appendChild(square);
  }

  elements.chessBoard.replaceChildren(fragment);
}

function updateTimer() {
  const elapsedSeconds = getElapsedSeconds();
  const minutes = String(Math.floor(elapsedSeconds / 60)).padStart(2, "0");
  const seconds = String(elapsedSeconds % 60).padStart(2, "0");
  elements.sessionTime.textContent = `${minutes}:${seconds}`;
  elements.sessionTime.dateTime = `PT${Math.floor(elapsedSeconds / 60)}M${elapsedSeconds % 60}S`;
}

function getElapsedSeconds() {
  return Math.max(0, Math.floor((Date.now() - state.startedAt) / 1000));
}

function formatElapsed() {
  const elapsedSeconds = getElapsedSeconds();
  const minutes = String(Math.floor(elapsedSeconds / 60)).padStart(2, "0");
  const seconds = String(elapsedSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function parseCommand(rawInput) {
  const raw = rawInput.trim();
  if (!raw) return null;

  if (!raw.startsWith("/")) {
    return { raw, name: "ask", args: raw, implicit: true };
  }

  const match = raw.match(/^\/([^\s]+)\s*([\s\S]*)$/);
  if (!match) return { raw, name: "unknown", args: "", implicit: false };

  const enteredName = match[1].toLowerCase();
  return {
    raw,
    enteredName,
    name: commandAliases.get(enteredName) || "unknown",
    args: match[2].trim(),
    implicit: false,
  };
}

function executeCommand(rawInput) {
  const command = parseCommand(rawInput);
  if (!command) return;

  appendEntry(
    "command",
    command.implicit ? "ВЫ · ВОПРОС" : "ВЫ · КОМАНДА",
    command.raw,
  );
  logEvent("command_entered", {
    command: command.name,
    entered_name: command.enteredName || null,
    implicit: command.implicit,
    character_count: command.raw.length,
  });

  if (
    state.phase === "complete" &&
    !["help", "status", "task", "rules", "clear"].includes(command.name)
  ) {
    appendError("Фрагмент завершён. Доступны /status, /task, /rules, /clear и /help.");
    return;
  }

  switch (command.name) {
    case "help":
      showHelp();
      break;
    case "ask":
      askNavigator(command.args);
      break;
    case "answer":
      draftAnswer(command.args);
      break;
    case "confidence":
      submitConfidence(command.args);
      break;
    case "next":
      goToNextEpisode();
      break;
    case "status":
      showStatus();
      break;
    case "task":
      showTaskSummary();
      break;
    case "rules":
      showRules();
      break;
    case "roll":
      runRollDemo();
      break;
    case "clear":
      clearVisibleConsole();
      break;
    case "cancel":
      cancelDraft();
      break;
    default:
      showUnknownCommand(command.enteredName);
  }
}

function showHelp() {
  const phaseLine =
    state.phase === "awaiting_confidence"
      ? "\nСейчас: ответ подготовлен. Зафиксируйте /confidence <0–100> или отмените /cancel."
      : state.phase === "feedback"
        ? "\nСейчас: обратная связь получена. Продолжите командой /next."
        : "";

  appendEntry(
    "system",
    "СПРАВКА",
    [
      "/ask <вопрос>           спросить ИИ-навигатора",
      "/answer <решение>       подготовить оцениваемый ответ",
      "/confidence <0–100>     зафиксировать уверенность и проверить ответ",
      "/next                   перейти по подготовленной ветке",
      "/task                   повторить текущий вопрос",
      "/rules                  показать правила среды",
      "/roll                   выполнить демонстрационный бросок",
      "/status                 показать состояние сессии",
      "/cancel                 отменить неподтверждённый ответ",
      "/clear                  очистить только видимую консоль",
      "",
      "Пример:",
      "/answer Ответ: 5/12. Учёл пересечение событий.",
      "/confidence 75",
      "",
      "Обычный текст без /ask также считается вопросом к ИИ.",
    ].join("\n") + phaseLine,
  );
  logEvent("help_requested");
}

function showTaskSummary() {
  const task = taskCatalog[state.currentTask];
  appendEntry(
    "system",
    "ТЕКУЩАЯ ЗАДАЧА",
    `${task.code} · ${task.title}\n${task.question}\n${task.hint}`,
  );
  logEvent("task_summary_requested");
}

function showRules() {
  appendEntry(
    "system",
    "ПРАВИЛА",
    [
      "• Кубики A и B различимы; каждая из шести граней равновероятна.",
      "• Одинаковые фигуры на разных гранях остаются разными равновероятными исходами.",
      "• В Chess960 начальная расстановка меняется: король находится между ладьями, слоны — на полях разных цветов.",
      "• ИИ доступен по желанию через /ask и не отправляет ответ на проверку.",
      "• Только пара /answer → /confidence создаёт оцениваемую попытку.",
    ].join("\n"),
  );
  logEvent("rules_requested", { task_id: taskCatalog[state.currentTask].code });
}

function showStatus() {
  const phaseNames = {
    ready: "ожидается команда",
    awaiting_confidence: "ответ подготовлен, ожидается уверенность",
    feedback: "получена обратная связь, готов переход",
    complete: "демо-фрагмент завершён",
  };
  const task = taskCatalog[state.currentTask];

  appendEntry(
    "system",
    "СТАТУС",
    [
      `Задача: ${task.code} · эпизод ${state.episode}`,
      `Состояние: ${phaseNames[state.phase]}`,
      `Оцениваемые попытки: ${state.attempts} из ${state.maxAttempts}`,
      `Ответ ожидает фиксации: ${state.pendingAnswer ? "да" : "нет"}`,
      `Обращения к ИИ: ${state.aiRequests}`,
      `Время сессии: ${formatElapsed()}`,
    ].join("\n"),
  );
  logEvent("status_requested");
}

function draftAnswer(answerText) {
  if (!answerText) {
    appendError(
      "После /answer нужен ответ и, желательно, короткое объяснение. Пример: /answer Ответ: 5/12.",
    );
    return;
  }

  if (state.phase === "feedback") {
    appendError("Сначала выполните /next. Система откроет следующую задачу или новую попытку.");
    return;
  }

  if (state.attempts >= state.maxAttempts) {
    appendError("Лимит попыток в этом эпизоде исчерпан. Выполните /next.");
    return;
  }

  const replaced = Boolean(state.pendingAnswer);
  state.pendingAnswer = answerText;
  state.pendingAnswerAt = Date.now();
  state.phase = "awaiting_confidence";
  updatePhaseUI();

  appendEntry(
    "system",
    "СИСТЕМА",
    `${replaced ? "Черновик заменён" : "Ответ подготовлен"}, но ещё не проверен. Укажите уверенность командой /confidence <0–100>.`,
  );
  logEvent("answer_drafted", {
    task_id: taskCatalog[state.currentTask].code,
    replaced,
    answer_text: answerText,
    character_count: answerText.length,
  });
}

function submitConfidence(rawConfidence) {
  if (state.phase !== "awaiting_confidence" || !state.pendingAnswer) {
    appendError("Сначала подготовьте решение командой /answer <ответ>.");
    return;
  }

  const confidence = parseConfidence(rawConfidence);
  if (confidence === null) {
    appendError("Уверенность должна быть числом от 0 до 100. Например: /confidence 75.");
    return;
  }

  const answer = state.pendingAnswer;
  const answerLatencyMs = Date.now() - state.pendingAnswerAt;
  state.pendingAnswer = null;
  state.pendingAnswerAt = null;
  state.attempts += 1;

  logEvent("confidence_submitted", {
    task_id: taskCatalog[state.currentTask].code,
    attempt: state.attempts,
    confidence,
    answer_latency_ms: answerLatencyMs,
  });

  const result = evaluateSolution(answer, taskCatalog[state.currentTask]);
  state.currentResult = result;
  state.phase = "feedback";

  appendEntry(
    `feedback ${result.kind}`,
    `ПРОВЕРКА · ${result.status}`,
    `${result.title}\n${result.text}\n\nУверенность до обратной связи: ${formatConfidence(confidence)}%.`,
  );

  const repeatsCurrentTask = result.nextTask === state.currentTask;
  const reachesAttemptLimit = repeatsCurrentTask && state.attempts >= state.maxAttempts;
  const nextMessage =
    result.nextTask === "complete" || reachesAttemptLimit
      ? "Фрагмент готов к завершению. Введите /next."
      : repeatsCurrentTask
        ? "Для новой попытки в этом эпизоде введите /next."
        : "Следующая ветка подготовлена по вашему ответу. Введите /next.";

  appendEntry("system", "МАРШРУТ", nextMessage);
  updatePhaseUI();

  logEvent("solution_evaluated", {
    task_id: taskCatalog[state.currentTask].code,
    attempt: state.attempts,
    result: result.kind,
    error_code: result.errorCode,
    next_node: result.nextTask,
    confidence,
    character_count: answer.length,
  });
  logEvent("feedback_shown", {
    task_id: taskCatalog[state.currentTask].code,
    result: result.kind,
  });
}

function parseConfidence(rawConfidence) {
  const normalized = rawConfidence.trim().replace(",", ".");
  if (!/^\d{1,3}(?:\.\d+)?%?$/.test(normalized)) return null;

  const value = Number(normalized.replace("%", ""));
  return Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
}

function formatConfidence(value) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(".", ",");
}

function cancelDraft() {
  if (state.phase !== "awaiting_confidence" || !state.pendingAnswer) {
    appendError("Сейчас нет неподтверждённого ответа.");
    return;
  }

  state.pendingAnswer = null;
  state.pendingAnswerAt = null;
  state.phase = "ready";
  updatePhaseUI();
  appendEntry("system", "СИСТЕМА", "Черновик отменён. Оцениваемая попытка не создана.");
  logEvent("answer_draft_cancelled", { task_id: taskCatalog[state.currentTask].code });
}

function goToNextEpisode() {
  if (state.phase !== "feedback" || !state.currentResult) {
    appendError("Переход ещё не подготовлен. Сначала отправьте /answer и /confidence.");
    return;
  }

  const nextTask = state.currentResult.nextTask;
  const repeatsCurrentTask = nextTask === state.currentTask;

  if (
    nextTask === "complete" ||
    (repeatsCurrentTask && state.attempts >= state.maxAttempts)
  ) {
    completeDemoFragment();
    return;
  }

  state.currentResult = null;

  if (repeatsCurrentTask) {
    state.phase = "ready";
    updatePhaseUI();
    appendEntry(
      "system",
      "СИСТЕМА",
      `Открыта попытка ${state.attempts + 1} из ${state.maxAttempts}. Используйте обратную связь и снова введите /answer.`,
    );
    logEvent("revision_started", {
      task_id: taskCatalog[state.currentTask].code,
      next_attempt: state.attempts + 1,
    });
    return;
  }

  state.currentTask = nextTask;
  state.attempts = 0;
  state.episode += 1;
  state.route.push(nextTask);
  state.phase = "ready";
  loadTask(taskCatalog[nextTask]);
  updatePhaseUI();

  appendEntry(
    "system",
    "МАРШРУТ",
    `Открыт эпизод ${state.episode}: ${taskCatalog[nextTask].code}. Ветка выбрана по предыдущему решению; причина сохранена в журнале.`,
  );
  appendEntry(
    "system",
    "СИСТЕМА",
    `Новый вопрос уже показан слева. Когда будете готовы, используйте /answer.`,
  );
  logEvent("branch_opened", {
    node_id: taskCatalog[nextTask].code,
    episode: state.episode,
    route: [...state.route],
  });
}

function completeDemoFragment() {
  state.currentResult = null;
  state.phase = "complete";
  elements.taskPath.textContent = "ДЕМО-ФРАГМЕНТ ЗАВЕРШЁН";
  updatePhaseUI();

  appendEntry(
    "feedback correct",
    "СИСТЕМА · ЗАВЕРШЕНО",
    "Маршрут и история команд сохранены локально. В полной миссии после этой ветки появились бы новые эквивалентные задачи и финальная проверка переноса.",
  );
  logEvent("demo_fragment_completed", {
    last_node: taskCatalog[state.currentTask].code,
    elapsed_seconds: getElapsedSeconds(),
    route: [...state.route],
    ai_requests: state.aiRequests,
  });
}

function askNavigator(question) {
  if (!question) {
    appendError("После /ask нужен вопрос. Можно также просто написать вопрос без команды.");
    return;
  }

  if (state.aiBusy) {
    appendError("Навигатор ещё отвечает на предыдущий вопрос.");
    return;
  }

  state.aiBusy = true;
  state.aiRequests += 1;
  elements.commandInput.disabled = true;
  const typingEntry = appendTypingEntry();

  logEvent("ai_request", {
    task_id: taskCatalog[state.currentTask].code,
    phase: state.phase,
    question_text: question,
    character_count: question.length,
    before_first_answer: state.attempts === 0 && !state.pendingAnswer,
  });

  window.setTimeout(() => {
    typingEntry.remove();
    const reply = getNavigatorReply(question);
    appendEntry("assistant", "ИИ · НАВИГАТОР", reply);
    state.aiBusy = false;
    elements.commandInput.disabled = false;
    elements.commandInput.focus({ preventScroll: true });
    logEvent("ai_response", {
      task_id: taskCatalog[state.currentTask].code,
      character_count: reply.length,
    });
  }, 620);
}

function getNavigatorReply(question) {
  const normalized = question.toLowerCase();
  const asksAboutSpace =
    normalized.includes("пространств") || normalized.includes("исход");
  const asksAboutOverlap =
    normalized.includes("пересеч") ||
    normalized.includes("дважды") ||
    normalized.includes("два раза");
  const asksForSimplification =
    normalized.includes("проще") ||
    normalized.includes("услов") ||
    normalized.includes("не понял") ||
    normalized.includes("не понимаю");
  const asksForAnswer =
    normalized.includes("дай ответ") ||
    normalized.includes("реши") ||
    normalized.includes("посчитай за меня") ||
    normalized.includes("готовый ответ");

  if (asksForAnswer) {
    return "Я не подменяю итоговый ответ, но могу проверить способ. Опишите, какие исходы вы считаете благоприятными, и я помогу найти пропуск или повторный подсчёт.";
  }

  if (state.currentTask === "advanced") {
    if (asksAboutSpace) {
      return "После условия «ферзь не выпал» у каждого кубика остаётся по пять допустимых граней. Новое пространство содержит 5 × 5 равновероятных пар.";
    }
    if (asksAboutOverlap) {
      return "Два порядка пары — A–ладья, B–конь и A–конь, B–ладья — несовместны. Их количества можно сложить.";
    }
    if (asksForSimplification) {
      return "Сначала уберите из каждого кубика грань с ферзём. Затем среди оставшихся пар найдите оба порядка сочетания «ладья + конь».";
    }
    return "Проверьте, как условие «ферзь не выпал» меняет знаменатель, а затем посчитайте оба порядка пары «ладья + конь».";
  }

  if (state.currentTask === "scaffold") {
    if (asksAboutSpace) {
      return "Здесь сохраняются все пары двух кубиков. Отметьте два случая: A–ладья, B–конь и A–конь, B–ладья.";
    }
    if (asksAboutOverlap) {
      return "Два порядка не пересекаются: один требует ладью на A, другой — ладью на B. Поэтому их количества можно сложить.";
    }
    if (asksForSimplification) {
      return "Посчитайте отдельно два порядка пары «ладья + конь», сложите их и разделите на размер полного пространства исходов.";
    }
    return "Разделите событие на два несовместных порядка и учтите, сколько граней с конём есть на каждом кубике.";
  }

  if (state.currentTask === "basics") {
    if (asksForSimplification) {
      return "Выберите одну грань кубика A. С ней можно получить по одной паре с каждой гранью кубика B. Повторите для всех граней A.";
    }
    return "Результат задаётся упорядоченной парой: одна грань кубика A и одна грань кубика B. Здесь работает правило произведения.";
  }

  if (asksAboutSpace) {
    return "Представьте таблицу: строки — грани кубика A, столбцы — грани кубика B. Каждая клетка является отдельным равновероятным результатом.";
  }

  if (asksAboutOverlap) {
    return "События «ферзь на A» и «ферзь на B» пересекаются в исходе ферзь–ферзь. При сложении этот исход нельзя считать дважды.";
  }

  if (asksForSimplification) {
    return "Разбейте успех на две группы: броски хотя бы с одним ферзём и броски без ферзя, где вместе появились ладья и конь.";
  }

  return "Опишите пространство исходов или назовите группы благоприятных бросков. Я помогу проверить полноту рассуждения, не фиксируя ответ за вас.";
}

function runRollDemo() {
  document.querySelectorAll(".face-list > span").forEach((face) => {
    face.classList.remove("rolled");
  });

  const roll = {};
  for (const die of ["A", "B"]) {
    const index = Math.floor(Math.random() * diceFaces[die].length);
    roll[die] = { face: diceFaces[die][index], index };
    document
      .querySelector(`.die-row[data-die="${die}"] .face-list`)
      .children[index].classList.add("rolled");
  }

  state.rollCount += 1;
  const success =
    roll.A.face === "ферзь" ||
    roll.B.face === "ферзь" ||
    new Set([roll.A.face, roll.B.face]).has("ладья") &&
      new Set([roll.A.face, roll.B.face]).has("конь");

  appendEntry(
    "system",
    "БРОСОК",
    `Демо ${state.rollCount}: A — ${roll.A.face}; B — ${roll.B.face}. ${success ? "Комбинация открыта." : "Условие успеха не выполнено."}`,
  );
  logEvent("dice_demo_rolled", {
    roll_number: state.rollCount,
    die_a: roll.A.face,
    die_b: roll.B.face,
    success,
  });
}

function clearVisibleConsole() {
  elements.consoleLog.replaceChildren();
  appendEntry(
    "system",
    "СИСТЕМА",
    "Видимая история очищена. Исследовательский журнал событий не изменён.",
  );
  logEvent("console_cleared");
}

function showUnknownCommand(enteredName = "") {
  const suggestion = findClosestCommand(enteredName);
  appendError(
    suggestion
      ? `Неизвестная команда /${enteredName}. Возможно, вы имели в виду /${suggestion}?`
      : `Неизвестная команда /${enteredName}. Введите /help.`,
  );
}

function findClosestCommand(enteredName) {
  if (!enteredName) return null;
  let best = null;
  let bestDistance = Infinity;

  for (const command of primaryCommands) {
    const distance = levenshteinDistance(enteredName, command);
    if (distance < bestDistance) {
      best = command;
      bestDistance = distance;
    }
  }

  return bestDistance <= 2 ? best : null;
}

function levenshteinDistance(left, right) {
  const row = Array.from({ length: right.length + 1 }, (_, index) => index);

  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    let diagonal = row[0];
    row[0] = leftIndex;

    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      const previous = row[rightIndex];
      const substitution = diagonal + (left[leftIndex - 1] === right[rightIndex - 1] ? 0 : 1);
      row[rightIndex] = Math.min(
        row[rightIndex] + 1,
        row[rightIndex - 1] + 1,
        substitution,
      );
      diagonal = previous;
    }
  }

  return row[right.length];
}

function evaluateSolution(text, task) {
  const candidate = extractFinalValue(text);
  const isCorrect = candidate !== null && nearlyEqual(candidate, task.expected);

  if (isCorrect) {
    if (task.id === "root") {
      return {
        kind: "correct",
        status: "ТОЧНЫЙ ОТВЕТ",
        errorCode: "NONE",
        nextTask: "advanced",
        title: "Расчёт принят",
        text: "Исходы с ферзём дают 11 из 36 вариантов: 6 + 6 − 1. Пара «ладья + конь» добавляет ещё 4 варианта. Итого 15/36 = 5/12 ≈ 41,7%.",
      };
    }

    return {
      kind: "correct",
      status: "ВЕТКА ПРОЙДЕНА",
      errorCode: "NONE",
      nextTask: "complete",
      title: "Решение принято",
      text: getCorrectExplanation(task.id),
    };
  }

  if (task.id === "root" && candidate !== null && nearlyEqual(candidate, 11 / 36)) {
    return {
      kind: "partial",
      status: "ЧАСТИЧНО ВЕРНО",
      errorCode: "ROOK_KNIGHT_OMITTED",
      nextTask: "scaffold",
      title: "Ферзи посчитаны верно",
      text: "Вы нашли 11 исходов с ферзём. В условии есть ещё один тип успеха: ладья и конь могут выпасть в двух порядках. Следующий эпизод поможет досчитать эту часть.",
    };
  }

  if (
    task.id === "root" &&
    candidate !== null &&
    (nearlyEqual(candidate, 4 / 36) || nearlyEqual(candidate, 4 / 25))
  ) {
    return {
      kind: "partial",
      status: "ЧАСТИЧНО ВЕРНО",
      errorCode: "QUEEN_EVENT_OMITTED",
      nextTask: "scaffold",
      title: "Пара фигур найдена",
      text: "Вы посчитали сочетания «ладья + конь», но условие также принимает любой бросок с ферзём. Эти группы не пересекаются, поэтому их вероятности нужно сложить.",
    };
  }

  if (task.id === "advanced" && candidate !== null && nearlyEqual(candidate, 4 / 36)) {
    return {
      kind: "partial",
      status: "НУЖНА КОРРЕКТИРОВКА",
      errorCode: "CONDITIONAL_DENOMINATOR",
      nextTask: "advanced",
      title: "Пересчитайте знаменатель",
      text: "Четыре благоприятных исхода найдены верно. Но после условия «ферзь не выпал» полное пространство стало меньше: осталось 5 × 5 пар.",
    };
  }

  if (task.id === "scaffold" && candidate !== null && nearlyEqual(candidate, 2 / 36)) {
    return {
      kind: "partial",
      status: "НУЖНА КОРРЕКТИРОВКА",
      errorCode: "ORDER_OMITTED",
      nextTask: "scaffold",
      title: "Учтите второй порядок",
      text: "Вы нашли случай «A–ладья, B–конь». Есть ещё симметричный случай «A–конь, B–ладья». Эти случаи несовместны и складываются.",
    };
  }

  return {
    kind: "incorrect",
    status: "НУЖНО УТОЧНЕНИЕ",
    errorCode: "SAMPLE_SPACE",
    nextTask: task.id === "root" ? "basics" : task.id,
    title: "Проверьте пространство исходов",
    text:
      task.id === "basics"
        ? "На кубике A шесть возможных граней, и для каждой из них есть шесть вариантов кубика B. Используйте правило произведения."
        : "У двух различимых шестигранных кубиков результаты образуют пары. Повторяющиеся названия фигур не отменяют того, что отдельные грани равновероятны.",
  };
}

function getCorrectExplanation(taskId) {
  if (taskId === "advanced") {
    return "После исключения ферзей осталось 25 равновероятных пар. Успешных пар четыре, поэтому вероятность равна 4/25 = 16%.";
  }
  if (taskId === "scaffold") {
    return "Два коня на B дают 2 исхода с ладьёй A, а два коня на A — ещё 2 исхода с ладьёй B. Получаем 4/36 = 1/9.";
  }
  return "Для каждой из шести граней кубика A возможны шесть граней кубика B: 6 × 6 = 36 пар.";
}

function extractFinalValue(text) {
  const normalized = text.toLowerCase();
  const answerMarkerPattern =
    /(?:ответ|итог(?:о)?|получа(?:ю|ем|ется)|получил(?:а|и)?|вероятность(?:\s+равна)?|p\s*=)\s*[:=—-]?/gi;
  let lastMarker = null;

  for (const match of normalized.matchAll(answerMarkerPattern)) {
    lastMarker = { index: match.index, length: match[0].length };
  }

  if (lastMarker) {
    const answerClause = normalized
      .slice(lastMarker.index + lastMarker.length)
      .split(
        /;\s*|\n+|[!?](?=\s|$)|\.(?=\s|$)|,\s*(?=так\s+как|потому|поскольку)/i,
        1,
      )[0];
    const markedValues = extractNumericValues(answerClause);
    if (markedValues.length) return markedValues.at(-1);
  }

  const values = extractNumericValues(normalized);
  return values.length ? values.at(-1) : null;
}

function extractNumericValues(text) {
  const values = [];
  const tokenPattern =
    /-?\d+(?:[.,]\d+)?\s*\/\s*-?\d+(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?\s+(?:из|of)\s+-?\d+(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?\s*%|-?\d+(?:[.,]\d+)?/gi;

  for (const match of text.matchAll(tokenPattern)) {
    const token = match[0].toLowerCase().replaceAll(",", ".").trim();

    if (token.includes("/")) {
      const [numerator, denominator] = token.split("/").map(Number);
      if (denominator !== 0) values.push(numerator / denominator);
      continue;
    }

    if (/\s(?:из|of)\s/.test(token)) {
      const [numerator, denominator] = token.split(/\s+(?:из|of)\s+/).map(Number);
      if (denominator !== 0) values.push(numerator / denominator);
      continue;
    }

    if (token.endsWith("%")) {
      values.push(Number(token.slice(0, -1).trim()) / 100);
      continue;
    }

    values.push(Number(token));
  }

  return values.filter(Number.isFinite);
}

function nearlyEqual(actual, expected) {
  const tolerance = expected > 1 ? 0.01 : 0.006;
  return Math.abs(actual - expected) <= tolerance;
}

function loadTask(task) {
  elements.taskPath.textContent = task.path;
  elements.taskCode.textContent = task.code;
  elements.taskOverline.textContent = task.overline;
  elements.taskTitle.textContent = task.title;
  elements.taskDescription.textContent = task.description;
  elements.conditionText.innerHTML = task.condition;
  elements.questionText.textContent = task.question;
  elements.answerHint.textContent = task.hint;
  elements.promptLabel.textContent = `pilot@${task.code.toLowerCase().replaceAll("–", "")}:~$`;
  document.title = `${task.code} · Dice & Chess · Сириус`;

  document.querySelectorAll(".face-list > span").forEach((face) => {
    face.classList.remove("rolled");
  });
  elements.taskScroll.scrollTop = 0;
}

function updatePhaseUI() {
  const hints = {
    ready: "Ожидаю команду",
    awaiting_confidence: "Нужна /confidence",
    feedback: "Введите /next",
    complete: "Фрагмент завершён",
  };
  const placeholders = {
    ready: "Введите /help или задайте вопрос…",
    awaiting_confidence: "Например: /confidence 75",
    feedback: "Введите /next",
    complete: "Доступны /status и /help",
  };

  elements.phaseHint.textContent = hints[state.phase];
  elements.commandInput.placeholder = placeholders[state.phase];
}

function appendEntry(typeClasses, label, text) {
  const entry = document.createElement("div");
  entry.className = `console-entry ${typeClasses}`;

  const meta = document.createElement("div");
  meta.className = "entry-meta";

  const author = document.createElement("span");
  author.textContent = label;

  const time = document.createElement("time");
  time.textContent = formatElapsed();
  time.dateTime = elements.sessionTime.dateTime;

  const body = document.createElement("div");
  body.className = "entry-body";
  body.textContent = text;

  meta.append(author, time);
  entry.append(meta, body);
  elements.consoleLog.appendChild(entry);
  scrollConsole();
  return entry;
}

function appendError(text) {
  appendEntry("error", "СИСТЕМА · ОШИБКА КОМАНДЫ", text);
  logEvent("command_rejected", { reason: text });
}

function appendTypingEntry() {
  const entry = document.createElement("div");
  entry.className = "console-entry assistant typing";

  const meta = document.createElement("div");
  meta.className = "entry-meta";
  meta.textContent = "ИИ · НАВИГАТОР";

  const body = document.createElement("div");
  body.className = "entry-body";
  body.append("Формирует ответ");

  const dots = document.createElement("span");
  dots.className = "typing-dots";
  dots.setAttribute("aria-label", "Навигатор печатает");
  dots.innerHTML = "<i></i><i></i><i></i>";
  body.appendChild(dots);

  entry.append(meta, body);
  elements.consoleLog.appendChild(entry);
  scrollConsole();
  return entry;
}

function scrollConsole() {
  window.requestAnimationFrame(() => {
    elements.consoleLog.scrollTop = elements.consoleLog.scrollHeight;
  });
}

function resizeCommandInput() {
  elements.commandInput.style.height = "auto";
  elements.commandInput.style.height = `${Math.min(elements.commandInput.scrollHeight, 118)}px`;
}

function logEvent(type, payload = {}) {
  const event = {
    type,
    timestamp: new Date().toISOString(),
    elapsed_ms: Date.now() - state.startedAt,
    mission_id: "dice_chess_console_demo",
    session_id: getSessionId(),
    task_id: taskCatalog[state.currentTask]?.code ?? null,
    phase: state.phase,
    ...payload,
  };

  try {
    const storageKey = "sirius:dice-chess-console:events";
    const events = JSON.parse(window.localStorage.getItem(storageKey) || "[]");
    events.push(event);
    window.localStorage.setItem(storageKey, JSON.stringify(events.slice(-250)));
  } catch {
    // The interface remains usable when browser storage is unavailable.
  }
}

function getSessionId() {
  const storageKey = "sirius:dice-chess-console:session";
  try {
    let id = window.sessionStorage.getItem(storageKey);
    if (!id) {
      id =
        typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `demo-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      window.sessionStorage.setItem(storageKey, id);
    }
    return id;
  } catch {
    return "storage-disabled";
  }
}

elements.commandForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.aiBusy) return;

  const rawInput = elements.commandInput.value;
  elements.commandInput.value = "";
  resizeCommandInput();
  executeCommand(rawInput);
});

elements.commandInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.commandForm.requestSubmit();
  }
});

elements.commandInput.addEventListener("input", resizeCommandInput);

initializeMission();
