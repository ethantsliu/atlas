import { describe, expect, it, vi } from "vitest";
import { copyLink } from "./Share";

describe("copyLink", () => {
  it("copies the complete share URL", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const url = "https://example.com/atlas/#?q=world+models&l=c";
    await expect(copyLink(url, { writeText })).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith(url);
  });

  it("reports unavailable or rejected clipboard access", async () => {
    await expect(copyLink("https://example.com/atlas/")).resolves.toBe(false);
    const writeText = vi.fn().mockRejectedValue(new Error("permission denied"));
    await expect(copyLink("https://example.com/atlas/", { writeText })).resolves.toBe(
      false,
    );
  });
});
