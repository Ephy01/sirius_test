import { taskBehaviour } from "../../tasks/registry";
import { telemetryText } from "../telemetry";
import { answer, bareAnswer, next, skip } from "./answerCommands";
import { assistantMessage } from "./assistantCommand";
import { getAnswer, help, unknownCommand } from "./helpCommands";
import { hint, operation, probe, reset, undo } from "./interactionCommands";
import type { CommandContext, CommandHandler, CommandRun } from "./run";

export type {
  TaskCommandHandlers,
  TaskMoveTransitionResult,
  TaskTransitionResult,
} from "./run";

const COMMANDS: Record<string, CommandHandler> = {
  "/help": help,
  "/probe": probe,
  "/test": probe,
  "/get": getAnswer,
  "/hint": hint,
  "/op": operation,
  "/reset": reset,
  "/undo": undo,
  "/answer": answer,
  "/skip": skip,
  "/next": next,
};

const BARE_ANSWER = /^(?:done|impossible|готово?|невозможно|недостижимо)$/iu;

function commandHandler(run: CommandRun): CommandHandler {
  const name = run.command.toLowerCase();
  if (Object.hasOwn(COMMANDS, name)) return COMMANDS[name];
  if (run.command.startsWith("/")) return unknownCommand;
  if (run.behaviour.commands.includes("done") && BARE_ANSWER.test(run.input)) {
    return bareAnswer;
  }
  return assistantMessage;
}

export async function runTaskCommand(
  rawInput: string,
  context: CommandContext,
) {
  const {
    task,
    isBusy,
    inFlight,
    inputRef,
    appendEntry,
    emitTelemetry,
    setDraft,
    setCommandBusy,
  } = context;
  const input = rawInput.trim();
  if (!input || isBusy || inFlight.current) return;
  const [command = "", ...parts] = input.split(/\s+/);
  const payload = input.slice(command.length).trim();

  inFlight.current = true;
  setDraft("");
  appendEntry("participant", input);
  setCommandBusy(true);
  const telemetryInput = telemetryText(input);
  emitTelemetry("client_command_submitted", {
    input: telemetryInput.text,
    command: command.toLocaleLowerCase("ru-RU"),
    input_length: input.length,
    input_byte_length: telemetryInput.originalByteLength,
    input_json_byte_length: telemetryInput.originalJsonByteLength,
    input_truncated: telemetryInput.truncated,
    task_status: task.status,
  });

  try {
    const run: CommandRun = {
      ...context,
      input,
      command,
      parts,
      payload,
      behaviour: taskBehaviour(task),
    };
    const pending = commandHandler(run)(run);
    if (pending) await pending;
  } catch {
  } finally {
    inFlight.current = false;
    setCommandBusy(false);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }
}
