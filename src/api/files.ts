import { ApiError } from "./errors";
import { send, type AuthenticatedRequestOptions } from "./http";

export type DownloadedFile = {
  blob: Blob;
  filename: string;
};

function decodeFilename(value: string): string | undefined {
  try {
    return decodeURIComponent(value);
  } catch {
    return undefined;
  }
}

function contentDispositionFilename(value: string | null): string | undefined {
  if (!value) return undefined;

  const encodedMatch = value.match(
    /(?:^|;)\s*filename\*\s*=\s*(?:"([^"]+)"|([^;]+))/i,
  );
  if (encodedMatch) {
    const encodedValue = (encodedMatch[1] ?? encodedMatch[2] ?? "").trim();
    const decoded = decodeFilename(
      encodedValue.match(/^[^']*'[^']*'(.*)$/)?.[1] ?? encodedValue,
    );
    if (decoded !== undefined) return decoded;
  }

  const quotedMatch = value.match(
    /(?:^|;)\s*filename\s*=\s*"((?:[^"\\]|\\.)*)"/i,
  );
  if (quotedMatch) {
    return quotedMatch[1].replace(/\\(["\\])/g, "$1");
  }

  return value
    .match(/(?:^|;)\s*filename\s*=\s*([^;]+)/i)?.[1]
    ?.trim();
}

function sanitizeFilename(value: string): string {
  return Array.from(
    value.replace(/[\u0000-\u001f\u007f/\\]/g, "_").trim(),
  )
    .slice(0, 180)
    .join("")
    .replace(/^\.+$/, "");
}

function safeDownloadFilename(
  candidate: string | undefined,
  fallback: string,
): string {
  return (
    (candidate ? sanitizeFilename(candidate) : "") ||
    sanitizeFilename(fallback) ||
    "download.txt"
  );
}

export async function requestFile(
  path: string,
  fallbackFilename: string,
  options: AuthenticatedRequestOptions,
): Promise<DownloadedFile> {
  const response = await send(path, {
    method: "GET",
    headers: new Headers({
      Accept: "text/plain, application/octet-stream",
      Authorization: `Bearer ${options.token}`,
    }),
    signal: options.signal,
  });

  let blob: Blob;
  try {
    blob = await response.blob();
  } catch (error) {
    throw new ApiError(502, {
      code: "invalid_file_response",
      message: "Не удалось прочитать файл, полученный от сервера.",
      details: error,
    });
  }

  return {
    blob,
    filename: safeDownloadFilename(
      contentDispositionFilename(response.headers.get("content-disposition")),
      fallbackFilename,
    ),
  };
}

export function saveDownloadedFile(file: DownloadedFile): void {
  const url = URL.createObjectURL(file.blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.filename;
  anchor.hidden = true;
  document.body.append(anchor);

  try {
    anchor.click();
  } finally {
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
  }
}
