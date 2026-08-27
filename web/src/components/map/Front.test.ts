import { describe, expect, it, vi } from "vitest";
import type { GraphNode } from "../../types";
import { pickFront } from "./Front";

const node = { id: "foreground" } as GraphNode;

describe("foreground overlap", () => {
  it("lets a visible foreground node outrank a historical paper", () => {
    const choose = vi.fn();
    const block = vi.fn();
    const drop = vi.fn();
    const open = { current: true };

    pickFront({ block, drop }, open, choose, node);

    expect(choose).toHaveBeenCalledWith(node);
    expect(block).toHaveBeenCalledOnce();
    expect(drop).toHaveBeenCalledOnce();
    expect(open.current).toBe(false);
  });

  it("allows a deliberate foreground selection without a bound paper", () => {
    const choose = vi.fn();
    const block = vi.fn();
    const drop = vi.fn();
    const open = { current: true };

    pickFront({ block, drop }, open, choose, node);

    expect(choose).toHaveBeenCalledWith(node);
    expect(block).toHaveBeenCalledOnce();
    expect(drop).toHaveBeenCalledOnce();
    expect(open.current).toBe(false);
  });
});
