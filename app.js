"use strict";

const taskCatalog = {
  root: {
    id: "root",
    code: "DC–03",
    stage: "ЭТАП 2 · ВЕРОЯТНОСТЬ",
    overline: "Найдите шанс комбинации",
    title: "Соберите матовую комбинацию",
    description:
      "Бросают два честных кубика. На их гранях изображены шахматные фигуры. Результаты кубиков различимы.",
    condition:
      "Комбинация открывается, если выпал <strong>хотя бы один ферзь</strong> или одновременно выпали <strong>ладья и конь</strong>.",
    question: "Какова вероятность получить матовую комбинацию?",
    hint: "Ответьте дробью, процентом или десятичным числом и коротко объясните расчёт.",
    difficulty: "Средняя сложность",
    expected: 5 / 12,
  },
  advanced: {
    id: "advanced",
    code: "DC–04A",
    stage: "ЭТАП 3 · УСЛОВНАЯ ВЕРОЯТНОСТЬ",
    overline: "Ветка: точный расчёт",
    title: "Продолжите атаку без ферзя",
    description:
      "Используются те же два кубика. Теперь известно, что ни на одном из них не выпал ферзь.",
    condition:
      "Успехом считается только пара <strong>ладья и конь</strong>. Порядок кубиков не важен, но сами кубики различимы.",
    question:
      "Какова вероятность пары «ладья + конь», если известно, что ферзь не выпал?",
    hint: "Сначала определите, сколько исходов осталось после нового условия.",
    difficulty: "Выше средней",
    expected: 4 / 25,
  },
  scaffold: {
    id: "scaffold",
    code: "DC–04B",
    stage: "ЭТАП 3 · ОБЪЕДИНЕНИЕ СОБЫТИЙ",
    overline: "Ветка: уточнение комбинации",
    title: "Посчитайте пару отдельно",
    description:
      "Вернёмся к исходным кубикам и отдельно рассмотрим вторую часть условия.",
    condition:
      "Нужна ровно одна пара: на одном кубике выпала <strong>ладья</strong>, а на другом — <strong>конь</strong>.",
    question: "Какова вероятность получить пару «ладья + конь»?",
    hint: "Учтите оба порядка: A–ладья, B–конь и A–конь, B–ладья.",
    difficulty: "Поддерживающая",
    expected: 1 / 9,
  },
  basics: {
    id: "basics",
    code: "DC–04C",
    stage: "ЭТАП 3 · ПРОСТРАНСТВО ИСХОДОВ",
    overline: "Ветка: карта результатов",
    title: "Постройте поле исходов",
    description:
      "У каждого честного кубика шесть равновероятных граней. Кубики различимы: результат A–ферзь, B–конь отличается от A–конь, B–ферзь.",
    condition:
      "Сейчас не нужно искать матовую комбинацию. Определите только размер полного <strong>пространства исходов</strong>.",
    question: "Сколько различных пар результатов дают два шестигранных кубика?",
    hint: "Ответьте одним числом и при желании добавьте короткое объяснение.",
    difficulty: "Базовая",
    expected: 36,
  },
};

const state = {
  startedAt: null,
  timer: null,
  mode: "assistant",
  currentTask: "root",
  currentResult: null,
  attempts: 0,
  maxAttempts: 3,
  episode: 3,
  soundOn: true,
};

const elements = {
  briefingView: document.querySelector("#briefingView"),
  missionView: document.querySelector("#missionView"),
  missionContext: document.querySelector("#missionContext"),
  sessionTime: document.querySelector("#sessionTime"),
  startMission: document.querySelector("#startMission"),
  soundToggle: document.querySelector("#soundToggle"),
  chessBoard: document.querySelector("#chessBoard"),
  messageList: document.querySelector("#messageList"),
  messageInput: document.querySelector("#messageInput"),
  sendMessage: document.querySelector("#sendMessage"),
  quickActions: document.querySelector("#quickActions"),
  composerHint: document.querySelector("#composerHint"),
  attemptWarning: document.querySelector("#attemptWarning"),
  feedbackCard: document.querySelector("#feedbackCard"),
  feedbackMark: document.querySelector("#feedbackMark"),
  feedbackEyebrow: document.querySelector("#feedbackEyebrow"),
  feedbackTitle: document.querySelector("#feedbackTitle"),
  feedbackText: document.querySelector("#feedbackText"),
  retryButton: document.querySelector("#retryButton"),
  nextEpisode: document.querySelector("#nextEpisode"),
  attemptCounter: document.querySelector("#attemptCounter"),
  attemptDots: document.querySelector(".attempt-dots"),
  adaptiveNote: document.querySelector("#adaptiveNote"),
  routeName: document.querySelector("#routeName"),
  episodeNumber: document.querySelector("#episodeNumber"),
  routeProgress: document.querySelector("#routeProgress"),
  workspace: document.querySelector(".workspace"),
  chatPanel: document.querySelector("#chatPanel"),
  composer: document.querySelector(".composer"),
  collapsedComposerSlot: document.querySelector("#collapsedComposerSlot"),
  collapseChat: document.querySelector("#collapseChat"),
  restoreChat: document.querySelector("#restoreChat"),
  rulesButton: document.querySelector("#rulesButton"),
  rulesDialog: document.querySelector("#rulesDialog"),
  rollDemo: document.querySelector("#rollDemo"),
  toast: document.querySelector("#toast"),
  taskScroll: document.querySelector("#taskScroll"),
};

function buildChessBoard() {
  const pieces = new Map([
    [4, { symbol: "♚", name: "чёрный король", side: "black", target: true }],
    [7, { symbol: "♜", name: "чёрная ладья", side: "black" }],
    [8, { symbol: "♟", name: "чёрная пешка", side: "black" }],
    [11, { symbol: "♟", name: "чёрная пешка", side: "black" }],
    [13, { symbol: "♟", name: "чёрная пешка", side: "black" }],
    [18, { symbol: "♞", name: "чёрный конь", side: "black" }],
    [28, { symbol: "♗", name: "белый слон", side: "white" }],
    [35, { symbol: "♕", name: "белый ферзь", side: "white" }],
    [42, { symbol: "♘", name: "белый конь", side: "white" }],
    [48, { symbol: "♙", name: "белая пешка", side: "white" }],
    [50, { symbol: "♙", name: "белая пешка", side: "white" }],
    [53, { symbol: "♙", name: "белая пешка", side: "white" }],
    [60, { symbol: "♔", name: "белый король", side: "white" }],
    [63, { symbol: "♖", name: "белая ладья", side: "white" }],
  ]);

  const fragment = document.createDocumentFragment();
  for (let index = 0; index < 64; index += 1) {
    const square = document.createElement("span");
    const row = Math.floor(index / 8);
    const column = index % 8;
    const piece = pieces.get(index);

    square.className = `chess-square ${(row + column) % 2 ? "dark" : "light"}`;
    square.setAttribute("aria-hidden", "true");

    if (piece) {
      square.textContent = piece.symbol;
      square.title = piece.name;
      square.classList.add(`${piece.side}-piece`);
      if (piece.target) square.classList.add("target");
    }

    fragment.appendChild(square);
  }
  elements.chessBoard.appendChild(fragment);
}

function startMission() {
  state.startedAt = Date.now();
  state.timer = window.setInterval(updateTimer, 1000);
  elements.briefingView.hidden = true;
  elements.missionView.hidden = false;
  elements.missionContext.hidden = false;
  elements.sessionTime.hidden = false;
  document.title = "DC–03 · Dice & Chess · Сириус";
  logEvent("mission_started", { mission: "dice_chess", version: "demo-0.1" });
  window.scrollTo({ top: 0, behavior: "smooth" });

  window.setTimeout(() => {
    elements.messageInput.focus({ preventScroll: true });
  }, 250);
}

function updateTimer() {
  if (!state.startedAt) return;
  const elapsedSeconds = Math.floor((Date.now() - state.startedAt) / 1000);
  const minutes = String(Math.floor(elapsedSeconds / 60)).padStart(2, "0");
  const seconds = String(elapsedSeconds % 60).padStart(2, "0");
  const time = elements.sessionTime.querySelector("time");
  time.textContent = `${minutes}:${seconds}`;
  time.dateTime = `PT${Math.floor(elapsedSeconds / 60)}M${elapsedSeconds % 60}S`;
}

function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll(".mode-button").forEach((button) => {
    const isActive = button.dataset.mode === mode;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });

  const isSolution = mode === "solution";
  elements.messageInput.placeholder = isSolution
    ? "Напишите ответ и коротко объясните ход мысли…"
    : "Задайте вопрос или опишите свою идею…";
  elements.sendMessage.querySelector(".send-label").textContent = isSolution
    ? "Зафиксировать"
    : "Отправить";
  elements.attemptWarning.hidden = !isSolution;
  elements.composerHint.textContent = isSolution
    ? "Решение сохранится как оцениваемая попытка"
    : "Enter — отправить · Shift+Enter — новая строка";
  updateAttemptUI();
  logEvent("composer_mode_changed", { mode });
}

function sendCurrentMessage() {
  const text = elements.messageInput.value.trim();
  if (!text) {
    showToast(
      state.mode === "solution"
        ? "Добавьте ответ перед фиксацией попытки."
        : "Напишите вопрос для навигатора.",
    );
    elements.messageInput.focus();
    return;
  }

  if (state.mode === "solution") {
    submitSolution(text);
  } else {
    askNavigator(text);
  }
}

function askNavigator(text) {
  appendMessage("user", text);
  elements.messageInput.value = "";
  elements.sendMessage.disabled = true;
  const typingMessage = appendTypingMessage();
  logEvent("ai_message_sent", {
    task_id: taskCatalog[state.currentTask].code,
    character_count: text.length,
  });

  window.setTimeout(() => {
    typingMessage.remove();
    appendMessage("assistant", getNavigatorReply(text));
    elements.sendMessage.disabled = false;
    elements.messageInput.focus();
    logEvent("ai_message_received", { task_id: taskCatalog[state.currentTask].code });
  }, 720);
}

function getNavigatorReply(text) {
  const normalized = text.toLowerCase();
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

  if (state.currentTask === "advanced") {
    if (asksAboutSpace) {
      return "После условия «ферзь не выпал» у каждого кубика остаётся по пять допустимых граней. Значит, новое пространство содержит 5 × 5 = 25 равновероятных пар.";
    }
    if (asksAboutOverlap) {
      return "Два порядка пары — A–ладья, B–конь и A–конь, B–ладья — несовместны. Их можно сложить, а пересечения между ними нет.";
    }
    if (asksForSimplification) {
      return "Сначала уберите из каждого кубика грань с ферзём. Среди оставшихся 25 пар найдите оба порядка сочетания «ладья + конь».";
    }
    return "В этой ветке знаменатель уже не равен 36: условие исключило все исходы с ферзём. Посчитайте число оставшихся пар и оба порядка «ладья + конь».";
  }

  if (state.currentTask === "scaffold") {
    if (asksAboutSpace) {
      return "Здесь сохраняются все 36 пар двух кубиков. Отметьте только два несовместных случая: A–ладья, B–конь и A–конь, B–ладья.";
    }
    if (asksAboutOverlap) {
      return "Два порядка пары не пересекаются: один требует ладью на A, второй — ладью на B. Их количества можно сложить.";
    }
    if (asksForSimplification) {
      return "Посчитайте отдельно два порядка пары «ладья + конь», сложите их и разделите на 36 возможных бросков.";
    }
    return "Разделите событие на два несовместных случая: ладья на A и конь на B; конь на A и ладья на B. Для каждого случая учитывайте число соответствующих граней.";
  }

  if (state.currentTask === "basics") {
    if (asksForSimplification) {
      return "Выберите одну грань первого кубика. С ней можно получить шесть разных пар — по одной для каждой грани второго. Повторите это для всех шести граней первого кубика.";
    }
    return "Результат задаётся парой: одна из шести граней кубика A и одна из шести граней кубика B. Используйте правило произведения 6 × 6.";
  }

  if (asksAboutSpace) {
    return "Начните с таблицы 6 × 6: строка — грань кубика A, столбец — грань кубика B. Получится 36 равновероятных пар. Затем отметьте пары, которые подходят под условие.";
  }

  if (asksAboutOverlap) {
    return "Событие «выпал ферзь на A» и событие «выпал ферзь на B» пересекаются в одном исходе: ферзь–ферзь. При сложении этот исход нужно вычесть один раз.";
  }

  if (asksForSimplification) {
    return "Ищите два типа удачных бросков: 1) на любом кубике есть ферзь; 2) ферзя нет, но вместе выпали ладья и конь. Все остальные пары не подходят.";
  }

  if (
    normalized.includes("ответ") ||
    normalized.includes("реши") ||
    normalized.includes("посчитай")
  ) {
    return "Я не буду подменять ваш ответ, но помогу проверить способ. Посчитайте отдельно исходы с ферзём и исходы «ладья + конь», затем проверьте, пересекаются ли эти две группы.";
  }

  return "Опишите, какие исходы вы считаете благоприятными. Я помогу проверить, все ли случаи учтены и нет ли повторного подсчёта.";
}

function submitSolution(text) {
  if (state.attempts >= state.maxAttempts) {
    showToast("Все три попытки использованы. Перейдите к следующему эпизоду.");
    return;
  }

  state.attempts += 1;
  appendMessage("user", text, "Решение");
  elements.messageInput.value = "";
  const result = evaluateSolution(text, taskCatalog[state.currentTask]);
  state.currentResult = result;
  updateAttemptUI();
  showFeedback(result);
  appendSystemMessage(result.chatSummary);
  logEvent("solution_submitted", {
    task_id: taskCatalog[state.currentTask].code,
    attempt: state.attempts,
    result: result.kind,
    error_code: result.errorCode,
    next_node: result.nextTask,
    character_count: text.length,
  });
}

function evaluateSolution(text, task) {
  const candidate = extractFinalValue(text);
  const isCorrect = candidate !== null && nearlyEqual(candidate, task.expected);

  if (isCorrect) {
    if (task.id === "root") {
      return {
        kind: "correct",
        errorCode: "NONE",
        nextTask: "advanced",
        mark: "✓",
        eyebrow: "РЕШЕНИЕ ПРИНЯТО · 100 / 100",
        title: "Точный расчёт",
        text: "Исходы с ферзём дают 11 из 36 вариантов: 6 + 6 − 1. Пара «ладья + конь» добавляет ещё 4 варианта. Итого 15/36 = 5/12 ≈ 41,7%.",
        chatSummary:
          "Решение зафиксировано. Следующий эпизод усложнит найденную закономерность.",
      };
    }

    return {
      kind: "correct",
      errorCode: "NONE",
      nextTask: "complete",
      mark: "✓",
      eyebrow: "РЕШЕНИЕ ПРИНЯТО",
      title: "Ветка пройдена",
      text: getCorrectExplanation(task.id),
      chatSummary:
        "Решение зафиксировано. Вы успешно применили обратную связь в новой задаче.",
    };
  }

  if (task.id === "root" && candidate !== null && nearlyEqual(candidate, 11 / 36)) {
    return {
      kind: "partial",
      errorCode: "ROOK_KNIGHT_OMITTED",
      nextTask: "scaffold",
      mark: "↗",
      eyebrow: "ЧАСТЬ РЕШЕНИЯ ВЕРНА · 64 / 100",
      title: "Ферзи посчитаны верно",
      text: "Вы нашли 11 исходов с ферзём. В условии есть ещё один тип успеха: ладья и конь могут выпасть в двух порядках. Следующий эпизод поможет аккуратно досчитать эту часть.",
      chatSummary:
        "Попытка сохранена. Маршрут подготовил короткую ветку на объединение событий.",
    };
  }

  if (
    task.id === "root" &&
    candidate !== null &&
    (nearlyEqual(candidate, 4 / 36) || nearlyEqual(candidate, 4 / 25))
  ) {
    return {
      kind: "partial",
      errorCode: "QUEEN_EVENT_OMITTED",
      nextTask: "scaffold",
      mark: "↗",
      eyebrow: "ЧАСТЬ РЕШЕНИЯ ВЕРНА · 58 / 100",
      title: "Пара фигур найдена",
      text: "Вы посчитали сочетания «ладья + конь», но условие также принимает любой бросок с ферзём. Эти группы не пересекаются, поэтому их вероятности нужно сложить.",
      chatSummary:
        "Попытка сохранена. Следующая задача разделит составное событие на понятные части.",
    };
  }

  if (
    task.id === "advanced" &&
    candidate !== null &&
    nearlyEqual(candidate, 4 / 36)
  ) {
    return {
      kind: "partial",
      errorCode: "CONDITIONAL_DENOMINATOR",
      nextTask: "advanced",
      mark: "↗",
      eyebrow: "ПОЧТИ ГОТОВО",
      title: "Пересчитайте знаменатель",
      text: "Четыре благоприятных исхода найдены верно. Но после условия «ферзь не выпал» полное пространство стало меньше: осталось 5 × 5 пар.",
      chatSummary:
        "Попытка сохранена. Проверьте новое число допустимых исходов и отправьте исправление.",
    };
  }

  if (
    task.id === "scaffold" &&
    candidate !== null &&
    nearlyEqual(candidate, 2 / 36)
  ) {
    return {
      kind: "partial",
      errorCode: "ORDER_OMITTED",
      nextTask: "scaffold",
      mark: "↗",
      eyebrow: "ПОЧТИ ГОТОВО",
      title: "Учтите второй порядок",
      text: "Вы нашли случай «A–ладья, B–конь». Есть ещё симметричный случай «A–конь, B–ладья». Эти случаи несовместны и складываются.",
      chatSummary:
        "Попытка сохранена. Добавьте второй порядок пары и зафиксируйте решение ещё раз.",
    };
  }

  return {
    kind: "incorrect",
    errorCode: "SAMPLE_SPACE",
    nextTask: task.id === "root" ? "basics" : task.id,
    mark: "!",
    eyebrow: "НУЖНО УТОЧНЕНИЕ",
    title: "Проверьте пространство исходов",
    text:
      task.id === "basics"
        ? "На первом кубике 6 возможных граней, и для каждой из них есть 6 вариантов второго кубика. Используйте правило произведения."
        : "У двух различимых шестигранных кубиков 6 × 6 = 36 равновероятных пар. Названия фигур могут повторяться, но равновероятны именно грани.",
    chatSummary:
      task.id === "root"
        ? "Попытка сохранена. Система подготовила поддерживающий шаг по пространству исходов."
        : "Попытка сохранена. Используйте обратную связь и попробуйте ещё раз в этом эпизоде.",
  };
}

function getCorrectExplanation(taskId) {
  if (taskId === "advanced") {
    return "После исключения ферзей осталось 25 равновероятных пар. Успешных пар четыре, поэтому вероятность равна 4/25 = 16%.";
  }
  if (taskId === "scaffold") {
    return "Два коня на B дают 2 исхода с ладьёй A, а два коня на A — ещё 2 исхода с ладьёй B. Получаем 4/36 = 1/9.";
  }
  return "Для каждой из шести граней первого кубика возможны шесть граней второго: 6 × 6 = 36 пар.";
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

function showFeedback(result) {
  elements.feedbackCard.hidden = false;
  elements.feedbackCard.classList.remove("partial", "incorrect");
  if (result.kind !== "correct") elements.feedbackCard.classList.add(result.kind);

  elements.feedbackMark.textContent = result.mark;
  elements.feedbackEyebrow.textContent = result.eyebrow;
  elements.feedbackTitle.textContent = result.title;
  elements.feedbackText.textContent = result.text;
  elements.retryButton.hidden = result.kind === "correct" || state.attempts >= state.maxAttempts;
  const repeatsCurrentTask = result.nextTask === state.currentTask;
  const shouldFinish =
    result.nextTask === "complete" ||
    (repeatsCurrentTask && state.attempts >= state.maxAttempts);

  elements.nextEpisode.textContent = shouldFinish
    ? "Завершить фрагмент →"
    : repeatsCurrentTask
      ? "Продолжить работу →"
      : "Следующий эпизод →";

  elements.adaptiveNote.firstChild.textContent = repeatsCurrentTask
    ? "Используйте обратную связь в следующей попытке "
    : result.kind === "correct"
      ? "Следующий эпизод подготовлен по вашему решению "
      : "Можно исправить ответ или перейти в поддерживающую ветку ";

  elements.feedbackCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function retrySolution() {
  elements.feedbackCard.hidden = true;
  setMode("solution");
  elements.messageInput.focus();
  logEvent("solution_retry_started", {
    task_id: taskCatalog[state.currentTask].code,
    next_attempt: state.attempts + 1,
  });
}

function goToNextEpisode() {
  if (!state.currentResult) return;
  const nextTask = state.currentResult.nextTask;

  if (nextTask === "complete") {
    completeDemoFragment();
    return;
  }

  if (nextTask === state.currentTask) {
    if (state.attempts >= state.maxAttempts) {
      completeDemoFragment();
    } else {
      retrySolution();
    }
    return;
  }

  state.currentTask = nextTask;
  state.currentResult = null;
  state.attempts = 0;
  state.episode += 1;
  loadTask(taskCatalog[nextTask]);
  advanceRoute();
  appendSystemMessage(
    `Маршрут перестроен: открыт эпизод ${state.episode}. Причина выбора ветки сохранена для преподавателя.`,
  );
  setMode("assistant");
  logEvent("branch_opened", {
    node_id: taskCatalog[nextTask].code,
    episode: state.episode,
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
  showToast("Новый эпизод подготовлен по предыдущему решению.");
}

function loadTask(task) {
  document.querySelector("#taskStage").textContent = task.stage;
  document.querySelector("#taskCode").textContent = `ЗАДАЧА ${task.code}`;
  document.querySelector("#taskOverline").textContent = task.overline;
  document.querySelector("#taskTitle").textContent = task.title;
  document.querySelector("#taskDescription").textContent = task.description;
  document.querySelector("#conditionText").innerHTML = task.condition;
  document.querySelector("#questionText").textContent = task.question;
  document.querySelector("#answerHint").textContent = task.hint;
  document.querySelector("#difficultyBadge").textContent = task.difficulty;
  document.querySelector("#chatContextName").textContent = `Задача ${task.code}`;
  elements.episodeNumber.textContent = `ЭПИЗОД ${state.episode}`;
  elements.routeProgress.textContent = String(state.episode);
  elements.feedbackCard.hidden = true;
  elements.adaptiveNote.firstChild.textContent =
    "Следующий эпизод будет выбран по вашему решению ";
  updateAttemptUI();
}

function advanceRoute() {
  const routeSteps = [...document.querySelectorAll(".route-step")];
  const routeLines = [...document.querySelectorAll(".route-line")];
  routeSteps[1].classList.remove("current");
  routeSteps[1].classList.add("complete");
  routeSteps[1].querySelector("span").textContent = "✓";
  routeSteps[1].removeAttribute("aria-current");
  routeLines[1].classList.add("complete");
  routeSteps[2].classList.add("current");
  routeSteps[2].setAttribute("aria-current", "step");
  elements.routeName.textContent =
    state.currentTask === "advanced"
      ? "Условная вероятность"
      : state.currentTask === "scaffold"
        ? "Границы события"
        : "Карта исходов";
}

function completeDemoFragment() {
  const task = taskCatalog[state.currentTask];
  elements.feedbackCard.classList.remove("partial", "incorrect");
  elements.feedbackMark.textContent = "✦";
  elements.feedbackEyebrow.textContent = "ДЕМО-ФРАГМЕНТ ЗАВЕРШЁН";
  elements.feedbackTitle.textContent = "Маршрут продолжится";
  elements.feedbackText.textContent =
    "В полной миссии система соберёт ещё несколько эквивалентных эпизодов и финальную задачу на перенос. Для прототипа показаны ключевые состояния интерфейса и адаптивная развилка.";
  elements.retryButton.hidden = true;
  elements.nextEpisode.hidden = true;
  elements.adaptiveNote.firstChild.textContent =
    "Результаты фрагмента готовы для просмотра преподавателем ";
  appendSystemMessage("Демо-фрагмент завершён. Спасибо — маршрут и история решений сохранены локально.");
  logEvent("demo_fragment_completed", {
    last_node: task.code,
    elapsed_seconds: Math.floor((Date.now() - state.startedAt) / 1000),
  });
  showToast("Демо-фрагмент завершён.");
}

function updateAttemptUI() {
  const shownAttempt = Math.min(state.attempts + 1, state.maxAttempts);
  elements.attemptCounter.textContent = `${shownAttempt} из ${state.maxAttempts}`;
  elements.attemptWarning.querySelector("strong").textContent =
    `${shownAttempt} из ${state.maxAttempts}`;
  elements.attemptDots.setAttribute(
    "aria-label",
    `Попытка ${shownAttempt} из ${state.maxAttempts}`,
  );

  [...elements.attemptDots.children].forEach((dot, index) => {
    dot.classList.toggle("used", index < state.attempts);
    dot.classList.toggle("active", index === state.attempts && state.attempts < state.maxAttempts);
  });
}

function appendMessage(type, text, authorOverride) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${type === "user" ? "user-message" : "assistant-message"}`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = type === "user" ? "АК" : "✦";

  const body = document.createElement("div");
  body.className = "message-body";

  const author = document.createElement("span");
  author.className = "message-author";
  author.textContent = authorOverride || (type === "user" ? "Вы" : "Навигатор");

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = text;

  body.append(author, bubble);
  wrapper.append(avatar, body);
  elements.messageList.appendChild(wrapper);
  scrollMessages();
  return wrapper;
}

function appendSystemMessage(text) {
  const message = document.createElement("div");
  message.className = "system-message";
  message.textContent = text;
  elements.messageList.appendChild(message);
  scrollMessages();
}

function appendTypingMessage() {
  const wrapper = appendMessage("assistant", "");
  const bubble = wrapper.querySelector(".message-bubble");
  bubble.classList.add("typing-bubble");
  bubble.setAttribute("aria-label", "Навигатор печатает");
  bubble.innerHTML = "<i></i><i></i><i></i>";
  return wrapper;
}

function scrollMessages() {
  window.requestAnimationFrame(() => {
    elements.messageList.scrollTop = elements.messageList.scrollHeight;
  });
}

function runRollDemo() {
  const rows = [...document.querySelectorAll(".face-list")];
  const selected = rows.map((row) => {
    const faces = [...row.children];
    return faces[Math.floor(Math.random() * faces.length)];
  });

  document.querySelectorAll(".face-list span").forEach((face) => {
    face.classList.remove("rolled");
    face.classList.add("rolling");
  });

  elements.rollDemo.disabled = true;
  window.setTimeout(() => {
    document.querySelectorAll(".face-list span").forEach((face) => {
      face.classList.remove("rolling");
    });
    selected.forEach((face) => face.classList.add("rolled"));
    elements.rollDemo.disabled = false;
    const result = selected.map((face) => face.title.toLowerCase()).join(" + ");
    showToast(`Демонстрационный бросок: ${result}.`);
    logEvent("dice_demo_rolled", { result });
  }, 520);
}

function toggleChat(collapsed) {
  if (collapsed) {
    setMode("solution");
    elements.collapsedComposerSlot.hidden = false;
    elements.collapsedComposerSlot.appendChild(elements.composer);
  } else {
    elements.chatPanel.appendChild(elements.composer);
    elements.collapsedComposerSlot.hidden = true;
  }

  elements.workspace.classList.toggle("chat-collapsed", collapsed);
  elements.restoreChat.hidden = !collapsed;
  elements.collapseChat.setAttribute("aria-expanded", String(!collapsed));
  logEvent(collapsed ? "ai_panel_collapsed" : "ai_panel_opened");
  window.setTimeout(() => elements.messageInput.focus({ preventScroll: true }), 50);
}

function toggleSound() {
  state.soundOn = !state.soundOn;
  elements.soundToggle.setAttribute(
    "aria-label",
    state.soundOn ? "Выключить звук" : "Включить звук",
  );
  elements.soundToggle.querySelector("span").textContent = state.soundOn ? "◖))" : "◖×";
  showToast(state.soundOn ? "Звук интерфейса включён." : "Звук интерфейса выключен.");
}

function showRules() {
  if (typeof elements.rulesDialog.showModal === "function") {
    elements.rulesDialog.showModal();
  } else {
    elements.rulesDialog.setAttribute("open", "");
  }
  logEvent("rules_opened", { task_id: taskCatalog[state.currentTask].code });
}

let toastTimer;
function showToast(text) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = text;
  elements.toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 3200);
}

function logEvent(type, payload = {}) {
  const event = {
    type,
    timestamp: new Date().toISOString(),
    mission_id: "dice_chess_demo",
    session_id: getSessionId(),
    task_id: taskCatalog[state.currentTask]?.code ?? null,
    ...payload,
  };

  try {
    const storageKey = "sirius:dice-chess-demo:events";
    const events = JSON.parse(window.localStorage.getItem(storageKey) || "[]");
    events.push(event);
    window.localStorage.setItem(storageKey, JSON.stringify(events.slice(-250)));
  } catch {
    // The interface remains usable when browser storage is unavailable.
  }
}

function getSessionId() {
  const storageKey = "sirius:dice-chess-demo:session";
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

elements.startMission.addEventListener("click", startMission);
elements.sendMessage.addEventListener("click", sendCurrentMessage);
elements.retryButton.addEventListener("click", retrySolution);
elements.nextEpisode.addEventListener("click", goToNextEpisode);
elements.rollDemo.addEventListener("click", runRollDemo);
elements.collapseChat.addEventListener("click", () => toggleChat(true));
elements.restoreChat.addEventListener("click", () => toggleChat(false));
elements.rulesButton.addEventListener("click", showRules);
elements.soundToggle.addEventListener("click", toggleSound);

document.querySelectorAll(".mode-button").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});

elements.quickActions.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-prompt]");
  if (!button) return;
  setMode("assistant");
  elements.messageInput.value = button.dataset.prompt;
  sendCurrentMessage();
});

elements.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendCurrentMessage();
  }
});

document.querySelector(".brand").addEventListener("click", (event) => {
  if (!state.startedAt) return;
  event.preventDefault();
  showToast("Завершите текущий демо-фрагмент, чтобы вернуться к списку миссий.");
});

buildChessBoard();
updateAttemptUI();
