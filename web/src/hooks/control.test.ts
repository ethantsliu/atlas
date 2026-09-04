import { describe, expect, it, vi } from "vitest";
import { beginAutoChange, bindChange } from "./control";

describe("camera change binding", () => {
  it("binds and removes one wrapper that ignores idle rotation", () => {
    const source = {
      addEventListener: vi.fn(),
      autoRotate: false,
      removeEventListener: vi.fn(),
    };
    const listener = vi.fn();
    const drop = bindChange(source, listener);
    const change = source.addEventListener.mock.calls[0]?.[1];

    expect(source.addEventListener).toHaveBeenCalledWith("change", change);
    change?.();
    expect(listener).toHaveBeenCalledOnce();

    source.autoRotate = true;
    change?.();
    expect(listener).toHaveBeenCalledTimes(2);
    change?.();
    expect(listener).toHaveBeenCalledTimes(2);

    beginAutoChange(source);
    change?.();
    expect(listener).toHaveBeenCalledTimes(3);
    change?.();
    expect(listener).toHaveBeenCalledTimes(3);

    drop();
    expect(source.removeEventListener).toHaveBeenCalledWith("change", change);
  });
});
