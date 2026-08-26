import type { MutableRefObject } from "react";
import type { LayoutGraph } from "../../hooks/layout";
import type { GraphNode } from "../../types";
import type { Camera3d } from "../../lib/camera";
import type { Camera, Scene, WebGLRenderer } from "three";

export type GraphApi = LayoutGraph &
  Camera3d & {
    graph2ScreenCoords: (x: number, y: number, z: number) => { x: number; y: number };
    refresh: () => unknown;
    scene: () => Scene;
    camera: () => Camera;
    renderer: () => WebGLRenderer;
    zoomToFit: (
      duration?: number,
      padding?: number,
      filter?: (node: GraphNode) => boolean,
    ) => unknown;
  };

export type GraphRef = MutableRefObject<GraphApi | undefined>;
