import { describe, expect, it, vi } from "vitest";
import type { PickOrder } from "../lib/order";
import { bindBegin } from "./begin";

describe("gesture order reset", () => {
  it("begins every canvas pointer gesture and cleans up", () => {
    let listener: ((event: PointerEvent) => void) | undefined;
    const source = {
      addEventListener: vi.fn((_: string, next: (event: PointerEvent) => void) => {
        listener = next;
      }),
      removeEventListener: vi.fn(),
    };
    const order = { begin: vi.fn() } as unknown as PickOrder;
    const drop = bindBegin(source, order);
    listener?.({ timeStamp: 42 } as PointerEvent);

    expect(order.begin).toHaveBeenCalledWith(42);
    drop();
    expect(source.removeEventListener).toHaveBeenCalledWith("pointerdown", listener);
  });
});
