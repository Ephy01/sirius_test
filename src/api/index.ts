import { redeemCode } from "./access";
import { getAiTurns, sendAiTurn } from "./assistant";
import {
  addEnrollments,
  createContest,
  deleteContest,
  downloadEnrollmentTelemetry,
  downloadEnrollmentTelemetrySummary,
  generateCodes,
  grantNextAttempt,
  listContestEnrollments,
  listContests,
  listTaskFamilies,
  publishContest,
  recoverCodes,
  rotateEnrollmentCode,
} from "./organizer";
import {
  answerTask,
  getCurrentTask,
  getNextTask,
  getParticipantContext,
  getParticipantDebugAnswer,
  getTaskProgress,
  interactWithTask,
  recordParticipantTelemetry,
  skipTask,
  startAttempt,
} from "./participant";

export type * from "./access";
export type * from "./assistant";
export type * from "./errors";
export type * from "./files";
export type * from "./http";
export type * from "./models";
export type * from "./organizer";
export type * from "./parsing";
export type * from "./participant";
export { ApiError } from "./errors";
export { saveDownloadedFile } from "./files";
export {
  parseAttempt,
  parseContestSummary,
  parseEnrollment,
  parseParticipant,
} from "./models";
export { isRecord, readNullableString, readString } from "./parsing";

export const api = {
  redeemCode,
  listContests,
  listTaskFamilies,
  deleteContest,
  createContest,
  addEnrollments,
  listContestEnrollments,
  downloadEnrollmentTelemetry,
  downloadEnrollmentTelemetrySummary,
  rotateEnrollmentCode,
  grantNextAttempt,
  generateCodes,
  recoverCodes,
  publishContest,
  getParticipantContext,
  getTaskProgress,
  recordParticipantTelemetry,
  startAttempt,
  getCurrentTask,
  getNextTask,
  answerTask,
  interactWithTask,
  getParticipantDebugAnswer,
  sendAiTurn,
  getAiTurns,
  skipTask,
};
