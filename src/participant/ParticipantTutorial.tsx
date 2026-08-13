import { useEffect, useMemo, useState } from "react";
import type { AiTurn } from "../api";
import {
  ParticipantWorkspace,
  type GeometryEdge,
  type GeometryPoint,
  type ParticipantTask,
  type TaskMoveTransitionResult,
} from "./ParticipantWorkspace";
import "./participant-tutorial.css";

type TourAction = "probe" | "ai" | "answer";

type TourStep = {
  selector: string;
  title: string;
  text: string;
  action?: TourAction;
};

const STEPS: TourStep[] = [
  {
    selector: '[data-tour="task-statement"]',
    title: "Условие задачи",
    text: "Слева всегда находится условие. В этом примере нужно восстановить скрытое правило по графам.",
  },
  {
    selector: '[data-tour="graph-cards"]',
    title: "Известные примеры",
    text: "Карточки с зелёной и красной отметкой уже классифицированы. Сравните их и сформулируйте первую гипотезу.",
  },
  {
    selector: '[data-tour="probe-card"]',
    title: "Проверка гипотезы",
    text: "Нажмите на подсвеченную карточку-пробу. Всего доступно четыре карточки, но проверить можно только три.",
    action: "probe",
  },
  {
    selector: '[data-tour="chat-form"]',
    title: "ИИ-ассистент",
    text: "Напишите обычное сообщение без символа «/», например «На что обратить внимание в примерах?», и отправьте его. Здесь ответ заскриптован и не расходует лимит.",
    action: "ai",
  },
  {
    selector: '[data-tour="targets"]',
    title: "Целевые карточки",
    text: "Когда гипотеза готова, классифицируйте три цели по порядку: подходит или не подходит.",
  },
  {
    selector: '[data-tour="chat-form"]',
    title: "Отправка ответа",
    text: "Нажмите «Ответ», допишите «да нет да» и отправьте команду. В настоящем контесте после ответа откроется следующая задача.",
    action: "answer",
  },
];

const CLASSIFICATIONS: Record<string, "positive" | "negative"> = {
  P01: "positive",
  P02: "negative",
  P03: "positive",
  P04: "negative",
};

function graph(
  group: string,
  coordinates: [number, number][],
  pairs: [number, number][],
): { points: GeometryPoint[]; edges: GeometryEdge[] } {
  const points = coordinates.map(([x, y], index) => ({
    id: `v${index + 1}`,
    group,
    x,
    y,
    label: String.fromCharCode(65 + index),
    color: "cyan",
  }));
  const edges = pairs.map(([source, target], index) => ({
    id: `${group}-e${index + 1}`,
    group,
    source: `v${source}`,
    target: `v${target}`,
    color: "violet",
  }));
  return { points, edges };
}

function tutorialTask(): ParticipantTask {
  const configurations = [
    graph("E01", [[2, 2], [8, 2], [5, 8]], [[1, 2], [2, 3], [3, 1]]),
    graph("E02", [[2, 2], [7, 2], [4, 7], [8, 8]], [[1, 2], [2, 3], [3, 1], [2, 4]]),
    graph("E03", [[2, 2], [5, 5], [8, 8]], [[1, 2], [2, 3]]),
    graph("E04", [[2, 2], [8, 2], [8, 8], [2, 8]], [[1, 2], [2, 3], [3, 4], [4, 1]]),
    graph("P01", [[2, 3], [8, 3], [5, 8]], [[1, 2], [2, 3], [3, 1]]),
    graph("P02", [[5, 5], [2, 2], [8, 2], [5, 9]], [[1, 2], [1, 3], [1, 4]]),
    graph("P03", [[2, 2], [7, 2], [4, 7], [9, 8]], [[1, 2], [2, 3], [3, 1]]),
    graph("P04", [[5, 9], [9, 6], [7, 1], [3, 1], [1, 6]], [[1, 2], [2, 3], [3, 4], [4, 5], [5, 1]]),
    graph("T01", [[2, 2], [8, 2], [5, 8], [5, 5]], [[1, 2], [2, 3], [3, 1], [3, 4]]),
    graph("T02", [[2, 2], [4, 7], [7, 7], [9, 2]], [[1, 2], [2, 3], [3, 4]]),
    graph("T03", [[2, 2], [8, 2], [8, 8], [2, 8]], [[1, 2], [2, 3], [3, 4], [4, 1], [1, 3]]),
  ];
  return {
    id: "tutorial-graph-zendo",
    ordinal: 1,
    family: "geo_zendo",
    kind: "geometry_atlas",
    difficulty: 1,
    status: "active",
    prompt:
      "Некоторые графы подчиняются скрытому правилу. Изучите положительные и отрицательные примеры, используйте не более трёх проб и определите, какие целевые графы подходят.",
    geometryScene: {
      bounds: { minX: 0, maxX: 10, minY: 0, maxY: 10 },
      points: configurations.flatMap((item) => item.points),
      edges: configurations.flatMap((item) => item.edges),
    },
    geometryContent: {
      examples: [
        { card_id: "E01", classification: "positive" },
        { card_id: "E02", classification: "positive" },
        { card_id: "E03", classification: "negative" },
        { card_id: "E04", classification: "negative" },
      ],
      probe_cards: ["P01", "P02", "P03", "P04"].map((card_id) => ({
        card_id,
      })),
      probe_observations: [],
      targets: ["T01", "T02", "T03"].map((card_id) => ({ card_id })),
      probe_budget: 3,
      probes_remaining: 3,
    },
    geometryInteraction: {},
    responseHint: "/answer да нет да",
  };
}

function GuidedTourOverlay({
  step,
  onBack,
  onNext,
  onClose,
}: {
  step: number;
  onBack: () => void;
  onNext: () => void;
  onClose: () => void;
}) {
  const current = STEPS[step];
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    const update = () => {
      const elements = Array.from(
        document.querySelectorAll<HTMLElement>(current.selector),
      );
      if (elements.length === 0) {
        setRect(null);
        return;
      }
      const rectangles = elements.map((element) => element.getBoundingClientRect());
      const left = Math.min(...rectangles.map((item) => item.left));
      const top = Math.min(...rectangles.map((item) => item.top));
      const right = Math.max(...rectangles.map((item) => item.right));
      const bottom = Math.max(...rectangles.map((item) => item.bottom));
      setRect(DOMRect.fromRect({
        x: left,
        y: top,
        width: right - left,
        height: bottom - top,
      }));
    };
    const elements = Array.from(
      document.querySelectorAll<HTMLElement>(current.selector),
    );
    elements[0]?.scrollIntoView({ block: "center", inline: "nearest" });
    update();
    const observer = new ResizeObserver(update);
    elements.forEach((element) => observer.observe(element));
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [current.selector]);

  if (!rect) return null;
  const gap = 8;
  const target = {
    top: Math.max(0, rect.top - gap),
    left: Math.max(0, rect.left - gap),
    right: Math.min(window.innerWidth, rect.right + gap),
    bottom: Math.min(window.innerHeight, rect.bottom + gap),
  };
  const tooltipWidth = Math.min(340, window.innerWidth - 28);
  const canPlaceRight = target.right + tooltipWidth + 18 < window.innerWidth;
  const canPlaceLeft = target.left - tooltipWidth - 18 > 0;
  const tooltipLeft = canPlaceRight
    ? target.right + 14
    : canPlaceLeft
      ? target.left - tooltipWidth - 14
      : Math.max(14, Math.min(target.left, window.innerWidth - tooltipWidth - 14));
  const tooltipTop = canPlaceRight || canPlaceLeft
    ? Math.max(14, Math.min(target.top, window.innerHeight - 270))
    : target.bottom + 250 < window.innerHeight
      ? target.bottom + 14
      : Math.max(14, target.top - 230);

  return (
    <div className="guided-tour" aria-live="polite">
      <div className="guided-tour__shade" style={{ inset: `0 0 auto 0`, height: target.top }} />
      <div className="guided-tour__shade" style={{ top: target.top, left: 0, width: target.left, height: target.bottom - target.top }} />
      <div className="guided-tour__shade" style={{ top: target.top, left: target.right, right: 0, height: target.bottom - target.top }} />
      <div className="guided-tour__shade" style={{ top: target.bottom, right: 0, bottom: 0, left: 0 }} />
      <div
        className="guided-tour__focus"
        style={{
          top: target.top,
          left: target.left,
          width: target.right - target.left,
          height: target.bottom - target.top,
        }}
      />
      <section
        className="guided-tour__card"
        role="dialog"
        aria-label={`Шаг ${step + 1} из ${STEPS.length}`}
        style={{ top: tooltipTop, left: tooltipLeft, width: tooltipWidth }}
      >
        <div className="guided-tour__progress">
          Шаг {step + 1} из {STEPS.length}
          <button type="button" onClick={onClose} aria-label="Закрыть инструктаж">
            ×
          </button>
        </div>
        <h2>{current.title}</h2>
        <p>{current.text}</p>
        {current.action && (
          <p className="guided-tour__action">Выполните действие в подсвеченной области.</p>
        )}
        <div className="guided-tour__buttons">
          <button type="button" onClick={onBack} disabled={step === 0}>
            Назад
          </button>
          {!current.action && (
            <button type="button" onClick={onNext}>
              Далее
            </button>
          )}
        </div>
      </section>
    </div>
  );
}

export function ParticipantTutorial({ onClose }: { onClose: () => void }) {
  const [task, setTask] = useState<ParticipantTask>(() => tutorialTask());
  const [step, setStep] = useState(0);
  const [finished, setFinished] = useState(false);
  const correctAnswer = useMemo(() => ["да", "нет", "да"], []);

  function advance(action: TourAction) {
    if (STEPS[step]?.action === action) {
      setStep((current) => Math.min(STEPS.length - 1, current + 1));
    }
  }

  async function probe(cardId: string): Promise<TaskMoveTransitionResult> {
    const normalized = cardId.trim().toUpperCase();
    const content = task.geometryContent ?? {};
    const observations = Array.isArray(content.probe_observations)
      ? content.probe_observations
      : [];
    const remaining =
      typeof content.probes_remaining === "number"
        ? content.probes_remaining
        : 0;
    if (!(normalized in CLASSIFICATIONS) || remaining <= 0) {
      return {
        ordinal: 1,
        advanced: false,
        accepted: false,
        completed: false,
        message: "Эта карточка недоступна для проверки.",
      };
    }
    if (
      observations.some(
        (item) =>
          typeof item === "object" &&
          item !== null &&
          "card_id" in item &&
          item.card_id === normalized,
      )
    ) {
      return {
        ordinal: 1,
        advanced: false,
        accepted: false,
        completed: false,
        message: "Эта карточка уже проверена.",
      };
    }
    setTask((current) => ({
      ...current,
      geometryContent: {
        ...(current.geometryContent ?? {}),
        probe_observations: [
          ...observations,
          { card_id: normalized, classification: CLASSIFICATIONS[normalized] },
        ],
        probes_remaining: remaining - 1,
      },
    }));
    advance("probe");
    return {
      ordinal: 1,
      advanced: false,
      accepted: true,
      completed: false,
      message: `${normalized}: ${CLASSIFICATIONS[normalized] === "positive" ? "подходит" : "не подходит"}.`,
    };
  }

  async function aiMessage(message: string): Promise<AiTurn> {
    void message;
    advance("ai");
    return {
      id: "tutorial-ai-turn",
      status: "completed",
      assistantMessage:
        "Сравните, какие циклы встречаются в положительных примерах и отсутствуют в отрицательных. Затем проверьте гипотезу на одной карточке-пробе.",
      model: "scripted-tutorial",
      usage: { inputTokens: 0, outputTokens: 0, totalTokens: 0 },
      remaining: { task: 5, attempt: 15 },
    };
  }

  async function answer(value: string) {
    if (STEPS[step]?.action !== "answer") {
      return {
        ordinal: 1,
        advanced: false,
        message: "Сначала выполните текущий шаг инструктажа.",
      };
    }
    const normalized = value
      .trim()
      .toLocaleLowerCase("ru-RU")
      .split(/[\s,;]+/u)
      .filter(Boolean)
      .map((item) => (item === "1" ? "да" : item === "0" ? "нет" : item));
    const correct =
      normalized.length === correctAnswer.length &&
      normalized.every((item, index) => item === correctAnswer[index]);
    if (correct) {
      setFinished(true);
      advance("answer");
    }
    return {
      ordinal: 1,
      advanced: false,
      message: correct
        ? "Демонстрационная задача решена. Инструктаж завершён."
        : "Для демонстрации нужен ответ «да нет да». Попробуйте ещё раз.",
    };
  }

  return (
    <div className="participant-tutorial">
      <ParticipantWorkspace
        task={task}
        contestTitle="Демонстрационный вариант"
        participantName="Инструктаж"
        tutorialMode
        onAnswer={answer}
        onSkip={async () => ({ ordinal: 1, advanced: false })}
        onNext={async () => ({ ordinal: 1, advanced: false })}
        onProbe={(cardId) => probe(cardId)}
        onAiMessage={(message) => aiMessage(message)}
      />
      {finished ? (
        <div className="tutorial-complete" role="dialog" aria-modal="true">
          <section>
            <span aria-hidden="true">✓</span>
            <h2>Инструктаж завершён</h2>
            <p>
              Вы проверили гипотезу, обратились к ассистенту и отправили ответ.
              Время основной попытки ещё не запускалось.
            </p>
            <button type="button" onClick={onClose}>
              Вернуться к правилам
            </button>
          </section>
        </div>
      ) : (
        <GuidedTourOverlay
          step={step}
          onBack={() => setStep((current) => Math.max(0, current - 1))}
          onNext={() =>
            setStep((current) => Math.min(STEPS.length - 1, current + 1))
          }
          onClose={onClose}
        />
      )}
    </div>
  );
}
