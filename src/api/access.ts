import { invalidResponse } from "./errors";
import { request } from "./http";
import {
  expectRecord,
  isRecord,
  readNullableString,
  readString,
  requiredString,
} from "./parsing";

export type AccessRole = "organizer" | "participant";

export type RedeemCodeResponse = {
  accessToken: string;
  role: AccessRole;
  expiresAt?: string | null;
};

export async function redeemCode(code: string): Promise<RedeemCodeResponse> {
  const body = await request("/access/redeem", {
    method: "POST",
    body: { code },
  });
  const response = expectRecord(
    isRecord(body) && isRecord(body.session) ? body.session : body,
    "Сервер вернул некорректную сессию доступа.",
  );

  const role = readString(response, "role");
  if (role !== "organizer" && role !== "participant") {
    throw invalidResponse("Сервер вернул неизвестную роль доступа.", body);
  }

  return {
    accessToken: requiredString(
      response,
      "accessToken",
      "accessToken",
      "access_token",
      "token",
    ),
    role,
    expiresAt: readNullableString(response, "expiresAt", "expires_at"),
  };
}
