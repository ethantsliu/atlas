import { describe, expect, it, vi } from "vitest";
import { makeFullReading } from "../test/fixtures";
import { basePath } from "./paths";
import { fetchFullReading } from "./readings";

function response(
  payload: unknown,
  options: { ok?: boolean; status?: number } = {},
): Response {
  return {
    ok: options.ok ?? true,
    status: options.status ?? 200,
    json: async () => payload,
  } as Response;
}

describe("fetchFullReading", () => {
  it("loads and validates a detail record against the compact index", async () => {
    const reading = makeFullReading();
    const fetcher = vi.fn(async () => response(reading)) as unknown as typeof fetch;
    const controller = new AbortController();

    await expect(
      fetchFullReading(
        {
          path: "/data/readings/paper--0123456789ab-fedcba987654.json",
          stableId: reading.stable_id,
          readingDepth: reading.reading_depth,
          signal: controller.signal,
        },
        fetcher,
      ),
    ).resolves.toEqual(reading);
    expect(fetcher).toHaveBeenCalledWith(
      basePath("/data/readings/paper--0123456789ab-fedcba987654.json"),
      { signal: controller.signal },
    );
  });

  it("reports HTTP failures without attempting to trust a body", async () => {
    const reading = makeFullReading();
    const fetcher = vi.fn(async () =>
      response(null, { ok: false, status: 404 }),
    ) as unknown as typeof fetch;

    await expect(
      fetchFullReading(
        {
          path: "/data/readings/missing--0123456789ab-fedcba987654.json",
          stableId: reading.stable_id,
          readingDepth: reading.reading_depth,
          signal: new AbortController().signal,
        },
        fetcher,
      ),
    ).rejects.toThrow("Full reading request failed (404)");
  });

  it("honors the configured deployment base", async () => {
    const reading = makeFullReading();
    const fetcher = vi.fn(async () => response(reading)) as unknown as typeof fetch;

    await fetchFullReading(
      {
        path: "/data/readings/paper--0123456789ab-fedcba987654.json",
        stableId: reading.stable_id,
        readingDepth: reading.reading_depth,
        signal: new AbortController().signal,
        base: "/atlas/",
      },
      fetcher,
    );

    expect(fetcher).toHaveBeenCalledWith(
      "/atlas/data/readings/paper--0123456789ab-fedcba987654.json",
      { signal: expect.any(AbortSignal) },
    );
  });

  it("rejects a valid-looking detail for the wrong paper or depth", async () => {
    const reading = makeFullReading();
    const fetcher = vi.fn(async () => response(reading)) as unknown as typeof fetch;

    await expect(
      fetchFullReading(
        {
          path: "/data/readings/paper--0123456789ab-fedcba987654.json",
          stableId: "arxiv:different",
          readingDepth: reading.reading_depth,
          signal: new AbortController().signal,
        },
        fetcher,
      ),
    ).rejects.toThrow("full reading ID mismatch");
  });
});
