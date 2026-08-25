/// <reference types="vite/client" />

import { describe, expect, it } from "vitest";
import app from "../App.tsx?raw";
import graph from "./map/Graph.tsx?raw";
import space from "./map/Space.tsx?raw";

describe("lazy runtime boundaries", () => {
  it("keeps the 3D engine behind the capability-gated import", () => {
    expect(graph).toContain('import("./Space")');
    expect(graph).not.toContain('from "react-force-graph-3d"');
    expect(graph).not.toContain('from "three"');
    expect(space).toContain('from "react-force-graph-3d"');
  });

  it("keeps major views out of the application shell", () => {
    expect(app).toContain('from "./views/Load"');
    expect(app).not.toContain('from "./views/Map"');
    expect(app).not.toContain('from "./views/Library"');
    expect(app).not.toContain('from "./views/Daily"');
  });
});
