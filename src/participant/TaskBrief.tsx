import { Fragment } from "react";
import type { ParticipantTask } from "../api";
import { taskBehaviour } from "../tasks/registry";

function DotSeparated({ items }: { items: readonly string[] }) {
  return (
    <>
      {items.map((item, index) => (
        <Fragment key={index}>
          {index > 0 && (
            <span className="sep-dot" aria-hidden="true">
              ·
            </span>
          )}
          {item}
        </Fragment>
      ))}
    </>
  );
}

export function TaskBrief({
  task,
  canAct,
  onCommand,
}: {
  task: ParticipantTask;
  canAct: boolean;
  onCommand: (command: string) => void;
}) {
  const {
    textOnly,
    statement,
    answerGuide,
    commandGuide,
    answerOptions,
    metaLines,
  } = taskBehaviour(task);
  const paragraphs = (statement.prompt ?? task.publicState.prompt)
    .split(/\n{2,}/u)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  return (
    <article
      className={`participant-brief${
        textOnly ? " participant-brief--classic" : ""
      }`}
      data-tour="task-statement"
    >
      <div className="participant-brief__statement">
        {statement.heading !== undefined && <h2>{statement.heading}</h2>}
        {paragraphs.map((paragraph, index) => (
          <p key={`${task.id}-paragraph-${index}`}>{paragraph}</p>
        ))}
        {statement.question && <p>{statement.question}</p>}
        {statement.appendix && (
          <Fragment key={task.id}>{statement.appendix}</Fragment>
        )}
      </div>
      <div className="participant-brief__answer">
        {answerGuide !== null && (
          <p>
            {answerGuide ?? (
              <>
                Ответ отправьте в чате командой{" "}
                <code>/answer &lt;ваш ответ&gt;</code>.
              </>
            )}
          </p>
        )}
        {commandGuide && <p>{commandGuide}</p>}
        {answerOptions.length > 0 && (
          <div
            className="transform-options"
            role="group"
            aria-label="Варианты преобразования"
          >
            {answerOptions.map((option) => (
              <button
                type="button"
                disabled={!canAct}
                onClick={() => onCommand(`/answer ${option.id}`)}
                key={option.id}
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
        {metaLines.length > 0 && (
          <p className="participant-brief__meta">
            <DotSeparated items={metaLines} />
          </p>
        )}
      </div>
    </article>
  );
}
