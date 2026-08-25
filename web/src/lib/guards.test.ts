import { describe, expect, it } from "vitest";
import { isPrimaryUrl, isWebUrl } from "./guards";

describe("web sources", () => {
  it("requires credential-free HTTPS on the default port", () => {
    expect(isWebUrl("https://example.com/paper")).toBe(true);
    expect(isWebUrl("http://example.com/paper")).toBe(false);
    expect(isWebUrl("javascript:alert(1)")).toBe(false);
    expect(isWebUrl("data:text/html,unsafe")).toBe(false);
    expect(isWebUrl("https://user@example.com/paper")).toBe(false);
    expect(isWebUrl("https://example.com:8443/paper")).toBe(false);
    expect(isWebUrl("https://localhost/paper")).toBe(false);
    expect(isWebUrl("https://127.0.0.1/paper")).toBe(false);
  });
});

describe("primary sources", () => {
  it("accepts official archives", () => {
    expect(isPrimaryUrl("https://arxiv.org/abs/2401.00001")).toBe(true);
    expect(
      isPrimaryUrl("https://journals.aps.org/pre/abstract/10.1103/PhysRevE.104.034304"),
    ).toBe(true);
    expect(isPrimaryUrl("https://www.ijcai.org/proceedings/2023/406")).toBe(true);
    expect(
      isPrimaryUrl(
        "https://www.sciencedirect.com/science/article/pii/S0045782598000933",
      ),
    ).toBe(true);
    expect(
      isPrimaryUrl(
        "https://proceedings.nips.cc/paper_files/paper/2025/hash/example.html",
      ),
    ).toBe(true);
  });

  it("rejects unsafe hosts", () => {
    expect(isPrimaryUrl("http://arxiv.org/abs/2401.00001")).toBe(false);
    expect(isPrimaryUrl("https://example.com/paper")).toBe(false);
  });
});
