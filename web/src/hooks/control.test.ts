import { describe, expect, it, vi } from "vitest";
import { bindChange } from "./control";

describe("camera change binding", () => {
  it("binds and removes the same listener", () => {
    const source = { addEventListener: vi.fn(), removeEventListener: vi.fn() };
    const listener = vi.fn();
    const drop = bindChange(source, listener);

    expect(source.addEventListener).toHaveBeenCalledWith("change", listener);
    drop();
    expect(source.removeEventListener).toHaveBeenCalledWith("change", listener);
  });
});
