import { useEffect } from "react";
import {
  BufferGeometry,
  Float32BufferAttribute,
  Group,
  LineBasicMaterial,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  SphereGeometry,
} from "three";
import type { Theme } from "../../hooks/theme";
import type { CloudMark } from "../../lib/focus";
import type { GraphRef } from "./Driver";

type RouteProps = { graphRef: GraphRef; mark: CloudMark | null; theme: Theme };

export function RouteMark({ graphRef, mark, theme }: RouteProps) {
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || !mark) return;
    const group = new Group();
    group.name = "archive-relations";
    const color = theme === "dark" ? "#83b5bf" : "#4f7f89";
    const dotShape = new SphereGeometry(3.4, 16, 12);
    const dotPaint = new MeshBasicMaterial({ color, depthTest: true });
    const dot = new Mesh(dotShape, dotPaint);
    dot.position.set(...mark.center);
    dot.renderOrder = 4;
    group.add(dot);
    const rows = mark.targets.flatMap(({ point }) => [...mark.center, ...point]);
    const lineShape = new BufferGeometry();
    lineShape.setAttribute("position", new Float32BufferAttribute(rows, 3));
    const linePaint = new LineBasicMaterial({
      color,
      transparent: true,
      opacity: theme === "dark" ? 0.58 : 0.5,
      depthWrite: false,
    });
    const lines = new LineSegments(lineShape, linePaint);
    lines.renderOrder = 3;
    group.add(lines);
    graph.scene().add(group);
    graph.refresh();
    return () => {
      graph.scene().remove(group);
      dotShape.dispose();
      dotPaint.dispose();
      lineShape.dispose();
      linePaint.dispose();
    };
  }, [graphRef, mark, theme]);

  return null;
}
