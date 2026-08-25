import { readingError, isReadingPayload } from "./atlas";
import type { FullReading } from "../types";
import { basePath } from "./paths";

export type ReadingRequest = {
  path: string;
  stableId: string;
  readingDepth: FullReading["reading_depth"];
  signal: AbortSignal;
  base?: string;
};

export async function fetchFullReading(
  request: ReadingRequest,
  fetcher: typeof fetch = fetch,
): Promise<FullReading> {
  const response = await fetcher(basePath(request.path, request.base), {
    signal: request.signal,
  });
  if (!response.ok) {
    throw new Error(`Full reading request failed (${response.status})`);
  }

  const payload: unknown = await response.json();
  const expectation = {
    stableId: request.stableId,
    readingDepth: request.readingDepth,
  };
  if (!isReadingPayload(payload, expectation)) {
    throw new Error(
      `Full reading response is invalid: ${readingError(payload, expectation)}`,
    );
  }
  return payload;
}
