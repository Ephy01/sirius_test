import { isRecord } from "../../api/parsing";
import type {
  TaskAnswerOption,
  TaskCommand,
  TaskKind,
  TaskQuickAction,
  TaskSubject,
} from "../kind";

type ContentState = {
  content: Record<string, unknown>;
};

const ZENDO_COMMANDS: readonly TaskCommand[] = ["probe", "hint"];

const ZENDO_QUICK_ACTIONS: readonly TaskQuickAction[] = [
  {
    label: "Проверить",
    ariaLabel: "Ввести команду /test",
    draftPrefix: "/test",
  },
];

const ZENDO_HELP = (
  <>
    <code>/test &lt;код&gt;</code> — проверить одну из карточек-проб
    <br />
    <code>/answer &lt;ответ&gt;</code> — классифицировать целевые
    конфигурации
    <br />
    <code>/hint</code> — платная подсказка о типе правила: итоговый балл умножается на 0.7
    <br />
    <code>/skip</code> — пропустить и открыть следующую задачу
  </>
);

const ZENDO_OPENING_GUIDE = (
  <>
    Можно проверить доступную карточку командой{" "}
    <code>/test &lt;код&gt;</code>, затем отправить итоговый ответ.
  </>
);

const ZENDO_COMMAND_GUIDE = (
  <>
    <code>/test &lt;код&gt;</code> — проверить одну из
    карточек-проб · <code>/hint</code> — платная подсказка:
    итоговый балл умножается на 0.7.
  </>
);

function zendoAnswerGuide(content: Record<string, unknown>) {
  const targetCount = Array.isArray(content.targets)
    ? content.targets.length
    : 0;
  const example = `/answer ${Array.from(
    { length: Math.max(1, targetCount) },
    (_, index) => (index % 2 === 0 ? "1" : "0"),
  ).join(" ")}`;
  return (
    <>
      Ответ отправьте в чате (пример:{" "}
      <code>{example}</code> — по одному значению для
      каждой из {targetCount || "показанных"} целей в их
      порядке, 1 — подходит, 0 — нет).
    </>
  );
}

function probesLeft(content: Record<string, unknown>): string[] {
  return typeof content.probes_remaining === "number"
    ? [`Осталось проб: ${content.probes_remaining}`]
    : [];
}

export function contentAnswerOptions(
  content: Record<string, unknown>,
): TaskAnswerOption[] {
  return Array.isArray(content.answer_cards)
    ? content.answer_cards.flatMap((option: unknown) =>
        isRecord(option) && "id" in option
          ? [
              {
                id: String(option.id),
                label: String("label" in option ? option.label : option.id),
              },
            ]
          : [],
      )
    : [];
}

/**
 * Members shared by the kinds with a hidden rule: probes through /test,
 * a paid /hint, one 0/1 value per target as the answer.
 * `detail` closes the meta line. `applies` limits the rule game to some
 * families of the kind.
 */
export function zendoBehaviour(
  detail: string,
  applies: (task: TaskSubject<ContentState>) => boolean = () => true,
) {
  return {
    commands: (task) => (applies(task) ? ZENDO_COMMANDS : []),
    help: (task) => (applies(task) ? ZENDO_HELP : undefined),
    opening: (task) => (applies(task) ? { guide: ZENDO_OPENING_GUIDE } : {}),
    answerGuide: (task) =>
      applies(task) ? zendoAnswerGuide(task.state.content) : undefined,
    commandGuide: (task) => (applies(task) ? ZENDO_COMMAND_GUIDE : undefined),
    answerOptions: (task) => contentAnswerOptions(task.state.content),
    metaLines: (task) => [
      ...(applies(task) ? probesLeft(task.state.content) : []),
      detail,
    ],
    quickActions: (task) => (applies(task) ? ZENDO_QUICK_ACTIONS : []),
  } satisfies Partial<TaskKind<ContentState>>;
}
