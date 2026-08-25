import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeFullReading, makePaper } from "../../test/fixtures";
import { PaperDetailModal } from "./Paper";

const useFullReadingMock = vi.hoisted(() => vi.fn());

vi.mock("../shared/Portal", () => ({
  DialogPortal: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("../../hooks/dialog", () => ({
  useDialog: () => ({ current: null }),
}));

vi.mock("../../hooks/reading", () => ({
  useFullReading: useFullReadingMock,
}));

describe("PaperDetailModal", () => {
  beforeEach(() => {
    useFullReadingMock.mockReturnValue({
      state: { status: "idle", reading: null, error: null },
      retry: vi.fn(),
    });
  });

  it("labels metadata-only evidence without implying an abstract was read", () => {
    const markup = renderToStaticMarkup(
      <PaperDetailModal
        paper={makePaper({ reading_depth: "metadata" })}
        close={vi.fn()}
      />,
    );

    expect(markup).toContain("<b>Metadata</b>");
    expect(markup).toContain("Collection preview · Metadata evidence");
    expect(markup).not.toContain("<b>Abstract</b>");
  });

  it("keeps contextual records explicitly outside the paper corpus", () => {
    const markup = renderToStaticMarkup(
      <PaperDetailModal
        paper={makePaper({
          record_kind: "non_paper_context",
          reading_depth: "context",
        })}
        close={vi.fn()}
      />,
    );

    expect(markup).toContain("<b>Context</b>");
    expect(markup).toContain("excluded from the paper corpus");
  });

  it("renders full provenance, attribution, verification, and linked PDF anchors", () => {
    const fullReading = makeFullReading();
    useFullReadingMock.mockReturnValue({
      state: { status: "loaded", reading: fullReading, error: null },
      retry: vi.fn(),
    });
    const markup = renderToStaticMarkup(
      <PaperDetailModal
        paper={makePaper({
          stable_id: fullReading.stable_id,
          reading_depth: fullReading.reading_depth,
          full_reading_path:
            "/data/readings/arxiv-0001-00001--0123456789ab-fedcba987654.json",
        })}
        close={vi.fn()}
      />,
    );

    expect(markup).toContain('aria-label="Pinned reading source"');
    expect(markup).toContain("Source locator");
    expect(markup).toContain(fullReading.source_provenance.source_locator);
    expect(markup).toContain(fullReading.source_provenance.pdf_sha256);
    expect(markup).toContain(fullReading.source_provenance.text_sha256);
    expect(markup).toContain("Attribution · Author Reported");
    expect(markup).toContain("Verification lineage");
    expect(markup).toContain(fullReading.verification!.passage_check);
    expect(markup).toContain('href="https://arxiv.org/pdf/0001.00001#page=4"');
    expect(markup).toContain('aria-label="Open pinned source at page 4, 3.2 Results"');
    expect(markup).toContain(
      'aria-label="Source verification for Primary competitor 1"',
    );
    expect(markup).toContain("<dt>Version</dt><dd>v1</dd>");
    expect(markup).toContain("<dt>Checked</dt><dd><time");
  });

  it("keeps anchors as text when the source is not a PDF endpoint", () => {
    const fullReading = makeFullReading({
      source_provenance: {
        ...makeFullReading().source_provenance,
        source_locator: "https://openreview.net/forum?id=paper",
      },
    });
    useFullReadingMock.mockReturnValue({
      state: { status: "loaded", reading: fullReading, error: null },
      retry: vi.fn(),
    });
    const markup = renderToStaticMarkup(
      <PaperDetailModal
        paper={makePaper({
          stable_id: fullReading.stable_id,
          reading_depth: fullReading.reading_depth,
          full_reading_path:
            "/data/readings/arxiv-0001-00001--0123456789ab-fedcba987654.json",
        })}
        close={vi.fn()}
      />,
    );

    expect(markup).toContain("<span>p. 4 · 3.2 Results</span>");
    expect(markup).not.toContain("#page=4");
    expect(markup).not.toContain("Open pinned source at page 4");
  });

  it("labels an alternate HTML source hash explicitly", () => {
    const original = makeFullReading();
    const fullReading = makeFullReading({
      source_provenance: {
        source_locator: "https://scholar.googleusercontent.com/scholar?q=cache:abc",
        source_format: "html",
        source_sha256: "c".repeat(64),
        text_sha256: original.source_provenance.text_sha256,
        page_count: original.source_provenance.page_count,
        extracted_at: original.source_provenance.extracted_at,
        review_pass: original.source_provenance.review_pass,
      },
    });
    useFullReadingMock.mockReturnValue({
      state: { status: "loaded", reading: fullReading, error: null },
      retry: vi.fn(),
    });

    const markup = renderToStaticMarkup(
      <PaperDetailModal paper={makePaper()} close={vi.fn()} />,
    );

    expect(markup).toContain("HTML source SHA-256");
    expect(markup).toContain("c".repeat(64));
    expect(markup).not.toContain("PDF SHA-256");
  });

  it("announces loading before any full-reading evidence is rendered", () => {
    useFullReadingMock.mockReturnValue({
      state: { status: "loading", reading: null, error: null },
      retry: vi.fn(),
    });
    const markup = renderToStaticMarkup(
      <PaperDetailModal
        paper={makePaper({
          reading_depth: "full_text",
          full_reading_path:
            "/data/readings/arxiv-0001-00001--0123456789ab-fedcba987654.json",
        })}
        close={vi.fn()}
      />,
    );

    expect(markup).toContain('role="status"');
    expect(markup).toContain('aria-live="polite"');
    expect(markup).toContain("Loading full review");
    expect(markup).not.toContain("Pinned reading source");
  });

  it("announces a failure and exposes a retry action", () => {
    useFullReadingMock.mockReturnValue({
      state: {
        status: "error",
        reading: null,
        error: "Full reading request failed (503)",
      },
      retry: vi.fn(),
    });
    const markup = renderToStaticMarkup(
      <PaperDetailModal
        paper={makePaper({
          reading_depth: "verified",
          full_reading_path:
            "/data/readings/arxiv-0001-00001--0123456789ab-fedcba987654.json",
        })}
        close={vi.fn()}
      />,
    );

    expect(markup).toContain('role="alert"');
    expect(markup).toContain("Full reading request failed (503)");
    expect(markup).toContain("Retry full review");
    expect(markup).not.toContain("Evidence boundary");
  });
});
