import { Vector3, type Camera, type Points } from "three";

type ScreenRect = Pick<DOMRect, "height" | "left" | "top" | "width">;
export type ScreenHit = { depth: number; index: number };

export function hitScreen(
  points: Points,
  camera: Camera,
  rect: ScreenRect,
  clientX: number,
  clientY: number,
  radius = 6,
): ScreenHit | null {
  if (rect.width <= 0 || rect.height <= 0 || radius <= 0) return null;
  const positions = points.geometry.getAttribute("position");
  const start = Math.max(0, points.geometry.drawRange.start);
  const range = points.geometry.drawRange.count;
  const end = Math.min(
    positions.count,
    Number.isFinite(range) ? start + range : positions.count,
  );
  const cursorX = clientX - rect.left;
  const cursorY = clientY - rect.top;
  const point = new Vector3();
  const cameraAt = new Vector3();
  let best = radius * radius;
  let depth = Number.POSITIVE_INFINITY;
  let picked: number | null = null;
  camera.updateMatrixWorld();
  camera.getWorldPosition(cameraAt);
  points.updateWorldMatrix(true, false);
  for (let index = start; index < end; index += 1) {
    point.fromBufferAttribute(positions, index).applyMatrix4(points.matrixWorld);
    const worldDepth = cameraAt.distanceTo(point);
    point.project(camera);
    if (point.z < -1 || point.z > 1) continue;
    const x = ((point.x + 1) * rect.width) / 2;
    const y = ((1 - point.y) * rect.height) / 2;
    const distance = (x - cursorX) ** 2 + (y - cursorY) ** 2;
    if (distance > best || (distance === best && worldDepth >= depth)) continue;
    best = distance;
    depth = worldDepth;
    picked = index;
  }
  return picked == null ? null : { depth, index: picked };
}
