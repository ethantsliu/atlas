import { describe, expect, it, vi } from "vitest";
import type { GraphNode } from "../../types";
import { pickFront } from "./Front";

const node = { id: "foreground" } as GraphNode;

describe("foreground overlap", () => {
  it("keeps a bound historical paper when foreground selection follows", () => {
    const choose = vi.fn();
    const block = vi.fn();
    const drop = vi.fn();
    const open = { current: true };

    pickFront({ block, drop, take: () => true }, open, choose, node);

    expect(choose).not.toHaveBeenCalled();
    expect(block).not.toHaveBeenCalled();
    expect(drop).not.toHaveBeenCalled();
    expect(open.current).toBe(true);
  });

  it("allows a deliberate foreground selection without a bound paper", () => {
    const choose = vi.fn();
    const block = vi.fn();
    const drop = vi.fn();
    const open = { current: true };

    pickFront({ block, drop, take: () => false }, open, choose, node);

    expect(choose).toHaveBeenCalledWith(node);
    expect(block).toHaveBeenCalledOnce();
    expect(drop).toHaveBeenCalledOnce();
    expect(open.current).toBe(false);
  });
});
